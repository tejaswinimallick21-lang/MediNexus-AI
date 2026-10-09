import { useEffect, useState } from "react";

import { labApi } from "../api/operations";
import type { CriticalAlert } from "../api/schemas/operations";
import { AreaTrend, RankedBars } from "../components/Charts";
import { Badge, Button, SelectField } from "../components/Controls";
import { DataTable, type Column } from "../components/DataTable";
import { ForecastNote } from "../components/ForecastNote";
import { KpiGrid } from "../components/Kpi";
import { Grid, PageHeader, Panel } from "../components/Panel";
import { Skeleton, SkeletonText } from "../components/Skeleton";
import { ErrorState } from "../components/StateViews";
import { useApi } from "../hooks/useApi";
import { useCursorPager } from "../hooks/useCursorPager";
import { formatDate, formatNumber, formatPercent } from "../lib/format";

const STATUS_TONE: Record<string, "good" | "warn" | "bad"> = { STABLE: "good", HIGH_WORKLOAD: "warn", CRITICAL_OVERLOAD: "bad" };

const ALERT_COLUMNS: Column<CriticalAlert>[] = [
  { key: "date", header: "Date", render: (r) => formatDate(r.test_date) },
  { key: "patient", header: "Patient", render: (r) => <code>{r.patient_id}</code> },
  { key: "test", header: "Test", render: (r) => r.test_name },
  {
    key: "value",
    header: "Result",
    numeric: true,
    render: (r) => (
      <strong style={{ color: "var(--color-danger-text)" }}>
        {r.test_value != null ? formatNumber(r.test_value, 2) : "—"} {r.unit ?? ""}
      </strong>
    ),
  },
  { key: "range", header: "Reference", render: (r) => r.reference_range ?? "—" },
  { key: "dept", header: "Department", render: (r) => r.department_name ?? "Outpatient" },
  { key: "action", header: "Action", render: () => <Badge tone="bad">Notify within 15 min</Badge> },
];

export function LaboratoryPage() {
  const kpis = useApi((s) => labApi.kpis(s), []);
  const workload = useApi((s) => labApi.workload(s), []);
  const volume = useApi((s) => labApi.dailyVolume(120, s), []);
  const categories = useApi((s) => labApi.categories(s), []);
  const [category, setCategory] = useState("");
  useEffect(() => {
    if (!category && categories.data?.length) setCategory(categories.data.includes("Hematology") ? "Hematology" : categories.data[0]);
  }, [categories.data, category]);
  const plan = useApi((s) => labApi.capacityPlan(category, s), [category], { enabled: !!category });

  const pager = useCursorPager();
  const alerts = useApi((s) => labApi.criticalAlerts({ limit: 10, cursor: pager.cursor }, s), [pager.cursor]);
  const k = kpis.data;

  return (
    <div>
      <PageHeader
        eyebrow="Healthcare professional"
        title="Laboratory Operations"
        subtitle="Investigation volumes, critical-value escalation and bench capacity planning across the network."
      />

      <KpiGrid
        loading={kpis.loading}
        error={kpis.error}
        onRetry={kpis.reload}
        items={
          k && [
            { label: "Investigations", value: k.total_tests, format: (n) => formatNumber(n), icon: "Flask", hint: `${formatNumber(k.tests_last_30d)} in the last 30 days` },
            { label: "Abnormal results", value: k.abnormal_pct, format: (n) => formatPercent(n), icon: "Pulse", tone: "warn", hint: `${formatNumber(k.abnormal_tests)} results` },
            { label: "Critical values", value: k.critical_tests, format: (n) => formatNumber(n), icon: "Alert", tone: "bad", hint: `${formatPercent(k.critical_pct)} of all results` },
            { label: "Test disciplines", value: workload.data?.length ?? 0, format: (n) => formatNumber(n), icon: "Clipboard", hint: "Reported categories" },
          ]
        }
      />

      <Grid>
        <Panel title="Daily test volume" subtitle="Last 120 days of data · critical values overlaid" icon="Pulse">
          {volume.error ? (
            <ErrorState error={volume.error} onRetry={volume.reload} />
          ) : volume.data ? (
            <AreaTrend
              data={volume.data}
              x="period"
              series={[
                { key: "value", name: "Tests" },
                { key: "secondary", name: "Critical" },
              ]}
              xFormatter={(d) => formatDate(d).slice(0, 6)}
            />
          ) : (
            <Skeleton height={280} radius={12} />
          )}
        </Panel>
        <Panel title="Volume by discipline" subtitle="All results to date" icon="Flask">
          {workload.error ? (
            <ErrorState error={workload.error} onRetry={workload.reload} />
          ) : workload.data ? (
            <RankedBars data={workload.data.map((w) => ({ label: w.category, value: w.total }))} height={290} />
          ) : (
            <SkeletonText lines={8} />
          )}
        </Panel>
      </Grid>

        <Panel
          title="Capacity planner"
          subtitle="Next 7 days vs estimated bench capacity"
          icon="Building"
          actions={
            <SelectField
              id="lab-category"
              label="Discipline"
              value={category}
              onChange={setCategory}
              disabled={!categories.data}
              options={(categories.data ?? []).map((c) => ({ value: c, label: c }))}
            />
          }
        >
          {plan.error ? (
            <ErrorState error={plan.error} onRetry={plan.reload} />
          ) : plan.data && !plan.loading ? (
            <div style={{ display: "grid", gap: 14 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 12 }}>
                <Stat label="Forecast tests / day" value={formatNumber(plan.data.forecast_daily_tests, 0)} />
                <Stat label="Est. capacity / day" value={formatNumber(plan.data.estimated_capacity_daily)} />
                <Stat label="Utilization" value={formatPercent(plan.data.utilization_pct, 0)} />
              </div>
              <div>
                <Badge tone={STATUS_TONE[plan.data.operational_status] ?? "neutral"}>{plan.data.operational_status.replace("_", " ")}</Badge>
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6, fontSize: 14 }}>
                {plan.data.actions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
              <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>{plan.data.assessment}</p>
              <ForecastNote meta={plan.data.forecast} />
            </div>
          ) : (
            <SkeletonText lines={7} />
          )}
        </Panel>


      <Panel title="Critical value escalation feed" subtitle="Most recent first · POL-LAB-001 requires verbal physician notification" icon="Alert">
        <DataTable
          columns={ALERT_COLUMNS}
          rows={alerts.data?.items}
          rowKey={(r) => r.lab_id}
          loading={alerts.loading}
          error={alerts.error}
          onRetry={alerts.reload}
          emptyTitle="No critical values recorded"
          caption="Critical laboratory values"
          footer={
            <>
              <span>Page {pager.page}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <Button onClick={pager.prev} disabled={!pager.hasPrev || alerts.loading}>Previous</Button>
                <Button onClick={() => pager.next(alerts.data?.next_cursor ?? null)} disabled={!alerts.data?.next_cursor || alerts.loading}>Next</Button>
              </span>
            </>
          }
        />
      </Panel>
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: "var(--color-surface-2)", border: "1px solid var(--color-border)", borderRadius: 10, padding: "10px 12px" }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.5, textTransform: "uppercase", color: "var(--color-text-muted)" }}>{label}</div>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: 22, color: "var(--color-ink)" }}>{value}</div>
    </div>
  );
}
