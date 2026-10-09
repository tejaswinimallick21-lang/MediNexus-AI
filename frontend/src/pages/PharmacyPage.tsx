import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import { pharmacyApi } from "../api/operations";
import type { StockLine } from "../api/schemas/operations";
import { Badge, Button, FieldRow, SelectField } from "../components/Controls";
import { CopilotPanel } from "../components/CopilotPanel";
import { DataTable, type Column } from "../components/DataTable";
import { ForecastNote } from "../components/ForecastNote";
import { KpiGrid } from "../components/Kpi";
import { Grid, PageHeader, Panel } from "../components/Panel";
import { SkeletonText } from "../components/Skeleton";
import { EmptyState, ErrorState } from "../components/StateViews";
import { useApi } from "../hooks/useApi";
import { useCursorPager } from "../hooks/useCursorPager";
import { formatNumber, formatUSD } from "../lib/format";
import { Stat } from "./LaboratoryPage";

const RISK_TONE: Record<string, "bad" | "warn" | "good"> = { "High Risk": "bad", "Moderate Risk": "warn", Safe: "good" };
const URGENCY_TONE: Record<string, "bad" | "warn" | "good"> = { URGENT: "bad", ELEVATED: "warn", NORMAL: "good", LOW: "good" };

export function PharmacyPage() {
  const kpis = useApi((s) => pharmacyApi.kpis(s), []);
  const riskByCat = useApi((s) => pharmacyApi.riskByCategory(s), []);
  const [risk, setRisk] = useState("High Risk");
  const pager = useCursorPager();
  const stock = useApi((s) => pharmacyApi.stock({ limit: 12, cursor: pager.cursor, risk }, s), [risk, pager.cursor]);
  const [selected, setSelected] = useState<string>();
  useEffect(() => {
    if (!selected && stock.data?.items.length) setSelected(stock.data.items[0].inventory_id);
  }, [stock.data, selected]);
  const forecast = useApi((s) => pharmacyApi.forecast(selected!, s), [selected], { enabled: !!selected });
  const [po, setPo] = useState<{ state: "idle" | "busy" | "done" | "error"; text?: string }>({ state: "idle" });
  useEffect(() => setPo({ state: "idle" }), [selected]);

  const columns: Column<StockLine>[] = [
    {
      key: "med",
      header: "Medication",
      render: (r) => (
        <button
          type="button"
          onClick={() => setSelected(r.inventory_id)}
          style={{ all: "unset", cursor: "pointer", fontWeight: r.inventory_id === selected ? 700 : 500, color: r.inventory_id === selected ? "var(--color-primary-strong)" : undefined }}
        >
          {r.medication_name}
        </button>
      ),
    },
    { key: "site", header: "Site", render: (r) => r.hospital_name ?? "—" },
    { key: "stock", header: "On hand", numeric: true, render: (r) => formatNumber(r.stock_quantity) },
    { key: "reorder", header: "Reorder at", numeric: true, render: (r) => formatNumber(r.reorder_level) },
    { key: "dos", header: "Days of supply", numeric: true, render: (r) => (r.days_of_supply != null ? formatNumber(r.days_of_supply, 1) : "No demand") },
    { key: "risk", header: "Risk", render: (r) => <Badge tone={RISK_TONE[r.stockout_risk] ?? "neutral"}>{r.stockout_risk}</Badge> },
  ];

  async function submitPo() {
    if (!forecast.data || !selected) return;
    setPo({ state: "busy" });
    try {
      const order = await pharmacyApi.purchaseOrder(selected, forecast.data.recommended_order_quantity);
      setPo({ state: "done", text: `${order.po_id} submitted: ${formatNumber(order.quantity)} units (${formatUSD(order.estimated_cost)}). Recorded in the audit trail.` });
    } catch (err) {
      setPo({ state: "error", text: err instanceof ApiError ? err.detail : "Could not create the purchase order." });
    }
  }

  const k = kpis.data;
  const f = forecast.data;

  return (
    <div>
      <PageHeader eyebrow="Healthcare professional" title="Pharmacy & Supply Chain" subtitle="Stock-out prevention, 30-day demand and one-click procurement across every site." />

      <KpiGrid
        loading={kpis.loading}
        error={kpis.error}
        onRetry={kpis.reload}
        items={
          k && [
            { label: "Stock lines", value: k.stock_lines, format: (n) => formatNumber(n), icon: "Pill", hint: "Site × medication" },
            { label: "High stock-out risk", value: k.high_risk_lines, format: (n) => formatNumber(n), icon: "Alert", tone: "bad", hint: "At or below reorder level" },
            { label: "Units dispensed", value: k.dispensed_units_180d, format: (n) => formatNumber(n), icon: "Pulse", hint: "Last 180 days" },
            { label: "Active prescriptions", value: k.active_prescriptions, format: (n) => formatNumber(n), icon: "Clipboard", tone: "good", hint: "Network-wide" },
          ]
        }
      />

      <div style={{ marginBottom: 20 }}>
        <Panel
          title="Stock lines"
          subtitle="Select a line to forecast and order"
          icon="Pill"
          actions={
            <FieldRow>
              <SelectField
                id="risk"
                label="Risk"
                value={risk}
                onChange={(v) => {
                  setRisk(v);
                  pager.reset();
                  setSelected(undefined);
                }}
                options={[
                  { value: "High Risk", label: "High risk" },
                  { value: "Moderate Risk", label: "Moderate risk" },
                  { value: "Safe", label: "Safe" },
                  { value: "", label: "All lines" },
                ]}
              />
            </FieldRow>
          }
        >
          <DataTable
            columns={columns}
            rows={stock.data?.items}
            rowKey={(r) => r.inventory_id}
            loading={stock.loading}
            error={stock.error}
            onRetry={stock.reload}
            emptyTitle="No stock lines in this risk band"
            caption="Pharmacy stock lines"
            footer={
              <>
                <span>Page {pager.page}</span>
                <span style={{ display: "flex", gap: 8 }}>
                  <Button onClick={pager.prev} disabled={!pager.hasPrev || stock.loading}>Previous</Button>
                  <Button onClick={() => pager.next(stock.data?.next_cursor ?? null)} disabled={!stock.data?.next_cursor || stock.loading}>Next</Button>
                </span>
              </>
            }
          />
        </Panel>

      </div>

      <Grid>
        <Panel title="30-day demand & procurement" subtitle={f ? `${f.medication_name} · ${f.hospital_name ?? ""}` : "Select a stock line"} icon="Sparkle">
          {!selected ? (
            <EmptyState title="Select a stock line" hint="Choose a medication on the left." />
          ) : forecast.error ? (
            <ErrorState error={forecast.error} onRetry={forecast.reload} />
          ) : f && !forecast.loading ? (
            <div style={{ display: "grid", gap: 14 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 12 }}>
                <Stat label="On hand" value={formatNumber(f.current_stock)} />
                <Stat label="Forecast · 30 days" value={formatNumber(f.predicted_30d_demand)} />
                <Stat label="Shortfall" value={formatNumber(f.projected_shortfall)} />
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <Badge tone={URGENCY_TONE[f.urgency] ?? "neutral"}>{f.urgency}</Badge>
                <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{f.buffer_assessment}</span>
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6, fontSize: 14 }}>
                {f.actions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
              {f.recommended_order_quantity > 0 ? (
                <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                  <Button variant="primary" onClick={submitPo} disabled={po.state === "busy" || po.state === "done"}>
                    {po.state === "busy" ? "Submitting…" : `Raise PO · ${formatNumber(f.recommended_order_quantity)} units (${formatUSD(f.estimated_procurement_cost)})`}
                  </Button>
                  {po.text && <span style={{ fontSize: 13, color: po.state === "error" ? "var(--color-danger-text)" : "var(--color-success-text)" }}>{po.text}</span>}
                </div>
              ) : (
                <Badge tone="good">No order needed</Badge>
              )}
              <ForecastNote meta={f.forecast} />
            </div>
          ) : (
            <SkeletonText lines={8} />
          )}
        </Panel>
        <CopilotPanel
          agent="pharmalab"
          name="Nexa Care · Pharmacy"
          tagline="Formulary, stock and cold-chain policy assistant"
          prompts={["Which medicines require immediate replenishment?", "What are the temperature standards for refrigerated medications?", "What is our inventory reorder policy?"]}
        />
      </Grid>

      <Panel title="Risk by therapeutic category" subtitle="High-risk stock lines first" icon="Alert">
          {riskByCat.error ? (
            <ErrorState error={riskByCat.error} onRetry={riskByCat.reload} />
          ) : riskByCat.data ? (
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10 }}>
              {riskByCat.data.map((c) => {
                const total = Math.max(1, c.high + c.moderate + c.safe);
                return (
                  <li key={c.category} style={{ display: "grid", gridTemplateColumns: "180px 1fr auto", gap: 12, alignItems: "center", fontSize: 13 }}>
                    <span>{c.category}</span>
                    <span style={{ display: "flex", height: 10, borderRadius: 999, overflow: "hidden", background: "var(--color-surface-3)" }}>
                      <span style={{ width: `${(c.high / total) * 100}%`, background: "var(--color-danger)" }} />
                      <span style={{ width: `${(c.moderate / total) * 100}%`, background: "var(--color-warning)" }} />
                      <span style={{ width: `${(c.safe / total) * 100}%`, background: "var(--color-success)" }} />
                    </span>
                    <strong>{formatNumber(c.high)} high</strong>
                  </li>
                );
              })}
            </ul>
          ) : (
            <SkeletonText lines={8} />
          )}
        </Panel>
    </div>
  );
}
