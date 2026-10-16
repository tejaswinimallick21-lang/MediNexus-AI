import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { executiveApi } from "../api/operations";
import type { ModelScore, SurvivalOverview } from "../api/schemas/operations";
import { BarLineChart, RankedBars, SERIES } from "../components/Charts";
import { Badge, SelectField } from "../components/Controls";
import { DataTable, type Column } from "../components/DataTable";
import { ForecastNote } from "../components/ForecastNote";
import { KpiGrid } from "../components/Kpi";
import { Grid, PageHeader, Panel } from "../components/Panel";
import { Skeleton, SkeletonText } from "../components/Skeleton";
import { ErrorState } from "../components/StateViews";
import { useApi } from "../hooks/useApi";
import { formatDate, formatMonth, formatNumber, formatPercent, formatUSD } from "../lib/format";
import { Stat } from "./LaboratoryPage";

const VERDICT_TONE = (v: string): "good" | "warn" | "bad" | "neutral" =>
  v.startsWith("Beats") ? "good" : v.startsWith("Marginal") ? "warn" : v.startsWith("Baseline") ? "bad" : "neutral";

const MODEL_COLUMNS: Column<ModelScore>[] = [
  { key: "model", header: "Model", render: (r) => <strong>{r.model}</strong> },
  { key: "purpose", header: "Scope", render: (r) => r.purpose },
  { key: "metric", header: "Held-out score", render: (r) => r.primary_metric },
  { key: "baseline", header: "Baseline", render: (r) => r.baseline },
  { key: "verdict", header: "Verdict", render: (r) => <Badge tone={VERDICT_TONE(r.verdict)}>{r.verdict}</Badge> },
];

type SurvivalRow = SurvivalOverview["by_type"][number];
const pct = (v: number | null) => (v == null ? "—" : formatPercent(v));
const SURVIVAL_COLUMNS: Column<SurvivalRow>[] = [
  { key: "type", header: "Cancer type", render: (r) => <strong>{r.cancer_type}</strong> },
  { key: "n", header: "Patients", numeric: true, render: (r) => formatNumber(r.patients) },
  { key: "y1", header: "1-year", numeric: true, render: (r) => pct(r.one_year_pct) },
  { key: "y3", header: "3-year", numeric: true, render: (r) => pct(r.three_year_pct) },
  { key: "y5", header: "5-year", numeric: true, render: (r) => pct(r.five_year_pct) },
  { key: "s1", header: "Stage I · 5-year", numeric: true, render: (r) => pct(r.stage_i_five_year_pct) },
  { key: "s4", header: "Stage IV · 5-year", numeric: true, render: (r) => pct(r.stage_iv_five_year_pct) },
];
const STAGE_COLORS = ["#14b8a6", "#0284c7", "#f59e0b", "#ef4444"];

function SurvivalChart({ data, kind }: { data: SurvivalOverview; kind: "stage" | "cancer_type" }) {
  const curves = data.curves.filter((c) => c.kind === kind);
  const rows = useMemo(() => {
    const months = Array.from(new Set(curves.flatMap((c) => c.points.map((p) => p.month)))).sort((a, b) => a - b).filter((m) => m <= 120);
    return months.map((m) => {
      const row: Record<string, number> = { month: m };
      curves.forEach((c) => {
        const p = c.points.find((x) => x.month === m);
        if (p) row[c.label] = p.survival_pct;
      });
      return row;
    });
  }, [curves]);
  const colors = kind === "stage" ? STAGE_COLORS : SERIES.concat(["#a855f7", "#64748b"]);
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
        <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
        <XAxis dataKey="month" tickFormatter={(m) => `${Math.round(Number(m) / 12)}y`} ticks={[0, 12, 24, 36, 48, 60, 72, 84, 96, 108, 120]} tick={{ fontSize: 12, fill: "#5b6b82" }} tickLine={false} axisLine={false} />
        <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12, fill: "#5b6b82" }} tickLine={false} axisLine={false} />
        <Tooltip labelFormatter={(m) => `${m} months after diagnosis`} formatter={(v: number, name: string) => [`${formatNumber(v, 1)}%`, name]} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {curves.map((c, i) => (
          <Line key={c.label} type="stepAfter" dataKey={c.label} stroke={colors[i % colors.length]} strokeWidth={2.2} dot={false} animationDuration={900} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ExecutivePage() {
  const kpis = useApi((s) => executiveApi.kpis(s), []);
  const trend = useApi((s) => executiveApi.diagnosesTrend(36, s), []);
  const survival = useApi((s) => executiveApi.survival(s), []);
  const stageMix = useApi((s) => executiveApi.stageMix(s), []);
  const cost = useApi((s) => executiveApi.costByType(s), []);
  const forecasts = useApi((s) => executiveApi.forecasts(s), []);
  const [curveKind, setCurveKind] = useState<"stage" | "cancer_type">("stage");
  const k = kpis.data;

  return (
    <div>
      <PageHeader
        eyebrow="Oncology analyst"
        title="Oncology outcomes"
        subtitle={k ? `Survival, diagnoses, treatment and cost across ${formatNumber(k.hospitals)} cancer centres · data through ${formatDate(k.data_through)}` : "Survival, diagnoses, treatment and cost"}
      />

      <KpiGrid
        count={6}
        loading={kpis.loading}
        error={kpis.error}
        onRetry={kpis.reload}
        items={
          k && [
            { label: "Cancer patients", value: k.patients, format: (n) => formatNumber(n), icon: "Users", hint: `${formatNumber(k.living_patients)} living` },
            { label: "New diagnoses · 12 months", value: k.new_diagnoses_12m, format: (n) => formatNumber(n), icon: "Building", hint: "First recorded diagnosis" },
            { label: "5-year survival", value: k.five_year_survival_pct ?? 0, format: (n) => (k.five_year_survival_pct == null ? "—" : formatPercent(n)), icon: "Sparkle", tone: "good", hint: "Kaplan-Meier, all patients" },
            { label: "Median time to treatment", value: k.median_days_to_treatment ?? 0, format: (n) => (k.median_days_to_treatment == null ? "—" : `${formatNumber(n)} d`), icon: "Clock", tone: (k.median_days_to_treatment ?? 0) > 30 ? "warn" : "good", hint: "Diagnosis to first treatment" },
            { label: "Treatment sessions · 30 days", value: k.treatment_sessions_30d, format: (n) => formatNumber(n), icon: "Pulse", hint: "Surgery, systemic, radiation" },
            { label: "Recorded cost of care", value: k.cost_of_care, format: (n) => formatUSD(n, { whole: true }), icon: "Check", hint: "Claims, visits and medicines" },
          ]
        }
      />

      <Panel
        title="Survival from diagnosis"
        subtitle={survival.data?.note ?? "Kaplan-Meier survival curves"}
        icon="Shield"
        actions={
          <SelectField
            id="curve-kind"
            label="Curves by"
            value={curveKind}
            onChange={(v) => setCurveKind(v as "stage" | "cancer_type")}
            options={[
              { value: "stage", label: "Stage" },
              { value: "cancer_type", label: "Cancer type" },
            ]}
          />
        }
      >
        {survival.error ? (
          <ErrorState error={survival.error} onRetry={survival.reload} />
        ) : survival.data ? (
          <SurvivalChart data={survival.data} kind={curveKind} />
        ) : (
          <Skeleton height={300} radius={12} />
        )}
      </Panel>
      <div style={{ height: 20 }} />

      <Panel title="Survival by cancer type" subtitle="Share of patients alive 1, 3 and 5 years after diagnosis" icon="Pulse">
        <DataTable
          columns={SURVIVAL_COLUMNS}
          rows={survival.data?.by_type}
          rowKey={(r) => r.cancer_type}
          loading={survival.loading}
          error={survival.error}
          onRetry={survival.reload}
          caption="Survival by cancer type"
        />
      </Panel>
      <div style={{ height: 20 }} />

      <Grid>
        <Panel title="New diagnoses and deaths" subtitle="Monthly · last 36 months of data" icon="Pulse">
          {trend.error ? (
            <ErrorState error={trend.error} onRetry={trend.reload} />
          ) : trend.data ? (
            <BarLineChart
              data={trend.data}
              x="period"
              bar="value"
              line="secondary"
              barName="New diagnoses"
              lineName="Deaths"
              xFormatter={formatMonth}
              formatLine={(n) => formatNumber(n)}
            />
          ) : (
            <Skeleton height={260} radius={12} />
          )}
        </Panel>
        <Panel title="Stage at diagnosis" subtitle="Patients per cancer type and stage" icon="Building">
          {stageMix.error ? (
            <ErrorState error={stageMix.error} onRetry={stageMix.reload} />
          ) : stageMix.data ? (
            <ResponsiveContainer width="100%" height={270}>
              <BarChart data={stageMix.data} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 24 }}>
                <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
                <XAxis type="number" tick={{ fontSize: 12, fill: "#5b6b82" }} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="cancer_type" width={110} tick={{ fontSize: 12, fill: "#5b6b82" }} tickLine={false} axisLine={false} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="stage_i" name="Stage I" stackId="s" fill={STAGE_COLORS[0]} />
                <Bar dataKey="stage_ii" name="Stage II" stackId="s" fill={STAGE_COLORS[1]} />
                <Bar dataKey="stage_iii" name="Stage III" stackId="s" fill={STAGE_COLORS[2]} />
                <Bar dataKey="stage_iv" name="Stage IV" stackId="s" fill={STAGE_COLORS[3]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <SkeletonText lines={8} />
          )}
        </Panel>
      </Grid>

      <Grid>
        <Panel title="Cost of care per patient" subtitle="Recorded claims, visits and medicines (synthetic costs)" icon="Building">
          {cost.error ? (
            <ErrorState error={cost.error} onRetry={cost.reload} />
          ) : cost.data ? (
            <RankedBars data={cost.data.map((r) => ({ label: r.cancer_type, value: r.cost_per_patient }))} format={(n) => formatUSD(n, { whole: true })} height={270} />
          ) : (
            <SkeletonText lines={8} />
          )}
        </Panel>
        <Panel title="Treatment capacity outlook" subtitle="Average sessions per day over the next 7 days" icon="Users">
          {forecasts.error ? (
            <ErrorState error={forecasts.error} onRetry={forecasts.reload} />
          ) : forecasts.data ? (
            <div style={{ display: "grid", gap: 14 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 12 }}>
                {forecasts.data.treatment.map((t) => (
                  <Stat key={t.service} label={t.service} value={`${formatNumber(t.forecast_daily, 1)} / day`} />
                ))}
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6, fontSize: 14 }}>
                {forecasts.data.treatment.map((t) => (
                  <li key={t.service}>
                    {t.service}: {formatNumber(t.last_7d_daily, 1)} a day over the last 7 days.
                  </li>
                ))}
              </ul>
              <ForecastNote meta={forecasts.data.treatment_forecast} />
            </div>
          ) : (
            <SkeletonText lines={9} />
          )}
        </Panel>
      </Grid>

      <div style={{ marginBottom: 20 }}>
        <Panel title="Model performance scorecard" subtitle="Every score is out-of-sample and compared with a simple baseline" icon="Shield">
          <DataTable
            columns={MODEL_COLUMNS}
            rows={forecasts.data?.models}
            rowKey={(r) => r.model}
            loading={forecasts.loading}
            error={forecasts.error}
            onRetry={forecasts.reload}
            emptyTitle="No trained models registered"
            caption="Model scorecard"
          />
        </Panel>
      </div>
    </div>
  );
}
