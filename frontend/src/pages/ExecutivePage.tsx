import { executiveApi } from "../api/operations";
import type { ModelScore } from "../api/schemas/operations";
import { BarLineChart, RankedBars } from "../components/Charts";
import { Badge } from "../components/Controls";
import { CopilotPanel } from "../components/CopilotPanel";
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

export function ExecutivePage() {
  const kpis = useApi((s) => executiveApi.kpis(s), []);
  const trend = useApi((s) => executiveApi.admissionsTrend(36, s), []);
  const revenue = useApi((s) => executiveApi.revenue(s), []);
  const forecasts = useApi((s) => executiveApi.forecasts(s), []);
  const drivers = useApi((s) => executiveApi.readmissionDrivers(s), []);
  const capacity = useApi((s) => executiveApi.capacityPlan(s), []);
  const k = kpis.data;

  return (
    <div>
      <PageHeader
        eyebrow="Operations analyst"
        title="Executive Operations"
        subtitle={k ? `Network performance across ${formatNumber(k.hospitals)} hospitals · data through ${formatDate(k.data_through)}` : "Network performance across all hospitals"}
      />

      <KpiGrid
        count={8}
        loading={kpis.loading}
        error={kpis.error}
        onRetry={kpis.reload}
        items={
          k && [
            { label: "Inpatient admissions", value: k.total_admissions, format: (n) => formatNumber(n), icon: "Building", hint: `${formatNumber(k.patients_admitted)} patients` },
            { label: "Unplanned readmissions", value: k.unplanned_readmission_rate_pct, format: (n) => formatPercent(n, 2), icon: "Alert", tone: "warn", hint: "Within 30 days of discharge" },
            { label: "Average length of stay", value: k.average_los_days, format: (n) => `${formatNumber(n, 1)} d`, icon: "Clock", hint: "Observed" },
            { label: "Bed occupancy", value: k.occupancy_rate_pct ?? 0, format: (n) => (k.occupancy_rate_pct == null ? "—" : formatPercent(n)), icon: "Users", hint: "Last 90 days · estimated capacity" },
            { label: "Billed revenue", value: k.total_revenue, format: (n) => formatUSD(n, { whole: true }), icon: "Sparkle", tone: "good", hint: "All inpatient claims" },
            { label: "Collection rate", value: k.collection_rate_pct, format: (n) => formatPercent(n), icon: "Check", tone: k.collection_rate_pct >= 70 ? "good" : "warn", hint: "Payer-covered share" },
          ]
        }
      />

      <Grid>
        <Panel title="Admissions & unplanned readmissions" subtitle="Monthly · last 36 months of data" icon="Pulse">
          {trend.error ? (
            <ErrorState error={trend.error} onRetry={trend.reload} />
          ) : trend.data ? (
            <BarLineChart
              data={trend.data}
              x="period"
              bar="value"
              line="secondary"
              barName="Admissions"
              lineName="Unplanned readmissions"
              xFormatter={formatMonth}
              formatLine={(n) => formatNumber(n)}
            />
          ) : (
            <Skeleton height={260} radius={12} />
          )}
        </Panel>
        <Panel title="Revenue by department" subtitle="Billed, all inpatient claims" icon="Building">
          {revenue.error ? (
            <ErrorState error={revenue.error} onRetry={revenue.reload} />
          ) : revenue.data ? (
            <RankedBars data={revenue.data.map((r) => ({ label: r.department, value: r.revenue }))} format={(n) => formatUSD(n, { whole: true })} height={270} />
          ) : (
            <SkeletonText lines={8} />
          )}
        </Panel>
      </Grid>

      <Grid>
        <Panel title="Why patients are readmitted" subtitle="Computed from Gold admissions (associations, not causes)" icon="Alert">
          {drivers.error ? (
            <ErrorState error={drivers.error} onRetry={drivers.reload} />
          ) : drivers.data ? (
            <div style={{ display: "grid", gap: 14 }}>
              <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6, fontSize: 14 }}>
                {drivers.data.findings.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
              <RankedBars
                data={drivers.data.by_reason.slice(0, 8).map((r) => ({ label: r.label, value: r.rate_pct }))}
                format={(n) => formatPercent(n)}
                height={240}
              />
            </div>
          ) : (
            <SkeletonText lines={9} />
          )}
        </Panel>
        <Panel title="Capacity outlook" subtitle="Next 7 days" icon="Users">
          {capacity.error ? (
            <ErrorState error={capacity.error} onRetry={capacity.reload} />
          ) : capacity.data && forecasts.data ? (
            <div style={{ display: "grid", gap: 14 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 12 }}>
                <Stat label="Admissions / day" value={formatNumber(capacity.data.projected_daily_admissions, 1)} />
                <Stat label="Occupancy" value={capacity.data.occupancy_pct == null ? "—" : formatPercent(capacity.data.occupancy_pct)} />
                <Stat label="Avg stay" value={`${formatNumber(capacity.data.average_los_days, 1)} d`} />
              </div>
              <Badge tone={capacity.data.surge_tier.includes("LEVEL 1") ? "good" : capacity.data.surge_tier.includes("LEVEL 2") ? "warn" : "bad"}>
                {capacity.data.surge_tier}
              </Badge>
              <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6, fontSize: 14 }}>
                {capacity.data.directives.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
              <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>{capacity.data.occupancy_note}</p>
              <ForecastNote meta={forecasts.data.admissions_forecast} />
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

      <CopilotPanel
          agent="healthanalyst"
          name="Nexa Insight"
          tagline="Executive analytics assistant grounded in Gold marts and hospital policy"
          prompts={["Why did readmissions increase across inpatient wards?", "Provide bed capacity and surge forecast", "What are the inpatient discharge guidelines?"]}
        />
    </div>
  );
}
