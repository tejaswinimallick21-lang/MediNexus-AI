import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { commandApi } from "../api/command";
import type { ModelMonitorRow, WhatIfInput, WhatIfPeriod } from "../api/schemas/command";
import { AreaTrend } from "../components/Charts";
import { Badge, SelectField } from "../components/Controls";
import { DataTable, type Column } from "../components/DataTable";
import { Icon } from "../components/Icons";
import { PageHeader, Panel } from "../components/Panel";
import { Skeleton, SkeletonText } from "../components/Skeleton";
import { ErrorState } from "../components/StateViews";
import { Tabs } from "../components/Tabs";
import { useApi } from "../hooks/useApi";
import { formatCompact, formatDate, formatNumber, formatPercent, formatUSDCompact } from "../lib/format";
import styles from "./CommandCenterPage.module.css";

type TabId = "what-if" | "models";
const TABS: { id: TabId; label: string }[] = [
  { id: "what-if", label: "Capacity what-if" },
  { id: "models", label: "Model monitor" },
];

export function CommandCenterPage() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.id === params.get("tab"))?.id ?? "what-if") as TabId;
  return (
    <div>
      <PageHeader
        eyebrow="Oncology analyst"
        title="Analyst Command Center"
        subtitle="Test a decision before you make it: outpatient staffing and demand what-ifs, and the health of every model."
      />
      <Tabs tabs={TABS} value={tab} onChange={(id) => setParams(id === "what-if" ? {} : { tab: id }, { replace: true })} />
      {tab === "what-if" && <WhatIfTab />}
      {tab === "models" && <ModelMonitorTab />}
    </div>
  );
}

// ---- Capacity what-if --------------------------------------------------------------------------

const DEFAULTS: WhatIfInput = { hospital_id: null, period: "last_365", extra_visits_per_physician: 5, extra_physicians: 0, demand_change_pct: 0 };
const PRESETS: { label: string; patch: Partial<WhatIfInput> }[] = [
  { label: "Each doctor sees +5 patients/day", patch: { extra_visits_per_physician: 5, extra_physicians: 0, demand_change_pct: 0 } },
  { label: "Hire 10 physicians per hospital", patch: { extra_visits_per_physician: 0, extra_physicians: 10, demand_change_pct: 0 } },
  { label: "Respiratory season: demand +20%", patch: { extra_visits_per_physician: 0, extra_physicians: 0, demand_change_pct: 20 } },
  { label: "Surge + 3 visits/doctor", patch: { extra_visits_per_physician: 3, extra_physicians: 0, demand_change_pct: 20 } },
];
const PERIODS: { value: WhatIfPeriod; label: string }[] = [
  { value: "last_365", label: "Last 365 days of data" },
  { value: "last_90", label: "Last 90 days of data" },
];

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function WhatIfTab() {
  const [input, setInput] = useState<WhatIfInput>(DEFAULTS);
  const query = useDebounced(input, 350);
  const hospitals = useApi((s) => commandApi.hospitals(s), []);
  const result = useApi((s) => commandApi.whatIf(query, s), [JSON.stringify(query)]);
  const set = (patch: Partial<WhatIfInput>) => setInput((i) => ({ ...i, ...patch }));
  const r = result.data;
  const changed = input.extra_physicians || input.extra_visits_per_physician || input.demand_change_pct;

  return (
    <div className={styles.whatIf}>
      <Panel title="Scenario" subtitle="Change staffing or demand; results update as you move the sliders" icon="Sliders" className={styles.controls}>
        <div className={styles.controlStack}>
          <SelectField
            id="wi-scope"
            label="Scope"
            value={input.hospital_id ?? ""}
            onChange={(v) => set({ hospital_id: v || null })}
            disabled={!hospitals.data}
            options={[
              { value: "", label: "Whole network (all hospitals)" },
              ...(hospitals.data ?? []).map((h) => ({ value: h.hospital_id, label: `${h.hospital_name} · ${formatPercent(h.served_pct, 0)} served` })),
            ]}
          />
          <SelectField id="wi-period" label="Replay period" value={input.period} onChange={(v) => set({ period: v as WhatIfPeriod })} options={PERIODS} />
          <Slider label="Extra visits per doctor per day" value={input.extra_visits_per_physician} min={0} max={15} step={1} format={(v) => `+${v}`} onChange={(v) => set({ extra_visits_per_physician: v })} />
          <Slider label="Additional physicians per hospital" value={input.extra_physicians} min={0} max={50} step={1} format={(v) => `+${v}`} onChange={(v) => set({ extra_physicians: v })} />
          <Slider label="Outpatient demand change" value={input.demand_change_pct} min={-50} max={100} step={5} format={(v) => `${v > 0 ? "+" : ""}${v}%`} onChange={(v) => set({ demand_change_pct: v })} />
          <div>
            <span className={styles.presetLabel}>Quick scenarios</span>
            <div className={styles.presets}>
              {PRESETS.map((p) => (
                <button key={p.label} type="button" onClick={() => set(p.patch)}>
                  {p.label}
                </button>
              ))}
              {!!changed && (
                <button type="button" className={styles.reset} onClick={() => set({ extra_visits_per_physician: 0, extra_physicians: 0, demand_change_pct: 0 })}>
                  Reset
                </button>
              )}
            </div>
          </div>
          {hospitals.data && (
            <p className={styles.hint}>
              <Icon.Alert size={14} /> Most pressured site: <strong>{hospitals.data[0].hospital_name}</strong> serves {formatPercent(hospitals.data[0].served_pct, 0)} of demand with a{" "}
              {formatNumber(hospitals.data[0].avg_wait_days, 1)}-day average wait.{" "}
              <button type="button" className={styles.link} onClick={() => set({ hospital_id: hospitals.data![0].hospital_id })}>
                Model it
              </button>
            </p>
          )}
        </div>
      </Panel>

      <div className={styles.results}>
        {result.error ? (
          <Panel>
            <ErrorState error={result.error} onRetry={result.reload} />
          </Panel>
        ) : !r ? (
          <Panel>
            <SkeletonText lines={10} />
          </Panel>
        ) : (
          <>
            <Panel
              title={r.scope}
              subtitle={`${formatDate(r.period_start)} – ${formatDate(r.period_end)} · ${r.days} days replayed`}
              icon="Radar"
              actions={<Badge tone="info">Simulated operations data</Badge>}
            >
              <div className={`${styles.net} ${r.net_impact_per_month >= 0 ? styles.netGood : styles.netBad}`} aria-busy={result.loading}>
                <span>Net impact per month</span>
                <strong>
                  {r.net_impact_per_month >= 0 ? "+" : "−"}
                  {formatUSDCompact(Math.abs(r.net_impact_per_month))}
                </strong>
                <em>revenue change minus staffing change</em>
              </div>
              <div className={styles.compareGrid}>
                <Compare label="Average wait" base={r.baseline.avg_wait_days} scen={r.scenario.avg_wait_days} format={(v) => `${formatNumber(v, 2)} d`} better="lower" />
                <Compare label="Waiting list (avg)" base={r.baseline.avg_backlog} scen={r.scenario.avg_backlog} format={(v) => formatCompact(v)} better="lower" />
                <Compare label="Lost to follow-up" base={r.baseline.lost_to_follow_up} scen={r.scenario.lost_to_follow_up} format={(v) => formatCompact(v)} better="lower" />
                <Compare label="Visits served" base={r.baseline.served} scen={r.scenario.served} format={(v) => formatCompact(v)} better="higher" />
                <Compare label="Clinic utilization" base={r.baseline.utilization_pct} scen={r.scenario.utilization_pct} format={(v) => formatPercent(v)} better="neutral" />
                <Compare label="Visits / doctor / day" base={r.baseline.visits_per_physician_day} scen={r.scenario.visits_per_physician_day} format={(v) => formatNumber(v, 1)} better="neutral" />
                <Compare label="Revenue" base={r.baseline.revenue} scen={r.scenario.revenue} format={(v) => formatUSDCompact(v)} better="higher" />
                <Compare label="Staffing cost" base={r.baseline.staffing_cost} scen={r.scenario.staffing_cost} format={(v) => formatUSDCompact(v)} better="lower" />
              </div>
            </Panel>
            <Panel title="Waiting list over the period" subtitle="Patients waiting for an outpatient slot at the end of each day" icon="Pulse">
              <AreaTrend
                data={r.daily}
                x="date"
                series={[
                  { key: "baseline_backlog", name: "As run" },
                  { key: "scenario_backlog", name: "Scenario" },
                ]}
                height={240}
                xFormatter={(v) => formatDate(v).slice(3)}
              />
            </Panel>
            <Panel title="What this means" icon="Sparkle">
              <ul className={styles.insights}>
                {r.insights.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
              <details className={styles.assumptions}>
                <summary>Assumptions</summary>
                <ul>
                  {r.assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </details>
            </Panel>
          </>
        )}
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step, format, onChange }: { label: string; value: number; min: number; max: number; step: number; format: (v: number) => string; onChange: (v: number) => void }) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <label className={styles.slider}>
      <span className={styles.sliderHead}>
        <span>{label}</span>
        <strong>{format(value)}</strong>
      </span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} style={{ ["--fill" as string]: `${pct}%` }} />
    </label>
  );
}

function Compare({ label, base, scen, format, better }: { label: string; base: number; scen: number; format: (v: number) => string; better: "lower" | "higher" | "neutral" }) {
  const delta = base ? ((scen - base) / Math.abs(base)) * 100 : 0;
  const same = Math.abs(delta) < 0.05;
  const good = better === "neutral" || same ? null : better === "lower" ? delta < 0 : delta > 0;
  return (
    <div className={styles.compare}>
      <span className={styles.compareLabel}>{label}</span>
      <strong>{format(scen)}</strong>
      <span className={styles.compareBase}>
        was {format(base)}
        {!same && (
          <span className={good === null ? styles.deltaNeutral : good ? styles.deltaGood : styles.deltaBad}>
            {delta > 0 ? "▲" : "▼"} {formatNumber(Math.abs(delta), Math.abs(delta) < 10 ? 1 : 0)}%
          </span>
        )}
      </span>
    </div>
  );
}

function Fact({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className={styles.fact}>
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <em>{hint}</em>}
    </div>
  );
}

// ---- Model monitor ----------------------------------------------------------------------------

const HEALTH: Record<ModelMonitorRow["health"], { tone: "good" | "warn" | "info"; label: string }> = {
  healthy: { tone: "good", label: "Healthy" },
  baseline: { tone: "warn", label: "Baseline served" },
  low_evidence: { tone: "info", label: "Low evidence" },
};
const VERDICT_TONE = (v: string): "good" | "warn" | "bad" | "neutral" =>
  v.startsWith("Beats") ? "good" : v.startsWith("Marginal") ? "warn" : v.startsWith("Baseline") ? "bad" : "neutral";

const MODEL_COLUMNS: Column<ModelMonitorRow>[] = [
  {
    key: "model",
    header: "Model",
    render: (r) => (
      <div style={{ display: "grid", gap: 4 }}>
        <strong>{r.label}</strong>
        <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          v{r.version} · trained {r.age_days === 0 ? "today" : `${r.age_days} d ago`} · {r.versions} version{r.versions === 1 ? "" : "s"}
        </span>
      </div>
    ),
  },
  { key: "source", header: "Data", render: (r) => <Badge tone={r.data_source === "Synthea" ? "neutral" : "info"}>{r.data_source}</Badge> },
  { key: "metric", header: "Held-out score", render: (r) => r.primary_metric },
  { key: "baseline", header: "Baseline", render: (r) => r.baseline },
  { key: "verdict", header: "Verdict", render: (r) => <Badge tone={VERDICT_TONE(r.verdict)}>{r.verdict}</Badge> },
  { key: "serving", header: "Serving", render: (r) => r.serving },
  { key: "health", header: "Health", render: (r) => <Badge tone={HEALTH[r.health].tone}>{HEALTH[r.health].label}</Badge> },
  { key: "note", header: "Notes", render: (r) => <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{r.note}</span> },
];

function ModelMonitorTab() {
  const models = useApi((s) => commandApi.models(s), []);
  const counts = useMemo(() => {
    const rows = models.data ?? [];
    return {
      total: rows.length,
      model: rows.filter((r) => r.serving === "Model").length,
      simpler: rows.filter((r) => r.serving !== "Model").length,
      low: rows.filter((r) => r.health === "low_evidence").length,
    };
  }, [models.data]);
  return (
    <div className={styles.stack}>
      <div className={styles.factRow}>
        {models.data ? (
          <>
            <Fact label="Active models" value={formatNumber(counts.total)} />
            <Fact label="Serving the model" value={formatNumber(counts.model)} hint="Beat a simple baseline out of sample" />
            <Fact label="Serving a simpler method" value={formatNumber(counts.simpler)} hint="A baseline or surge-aware average beat the ML model out of sample" />
            <Fact label="Low evidence" value={formatNumber(counts.low)} hint="Too few held-out events for tight estimates" />
          </>
        ) : (
          Array.from({ length: 4 }, (_, i) => <Skeleton key={i} height={92} radius={14} />)
        )}
      </div>
      <Panel title="Model registry" subtitle="Every score is out-of-sample and compared with a simple baseline" icon="Shield">
        <DataTable
          columns={MODEL_COLUMNS}
          rows={models.data}
          rowKey={(r) => r.model_name}
          loading={models.loading}
          error={models.error}
          onRetry={models.reload}
          emptyTitle="No trained models registered"
          caption="Model monitor"
        />
      </Panel>
    </div>
  );
}
