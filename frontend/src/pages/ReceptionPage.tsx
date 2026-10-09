import { useState } from "react";

import { receptionApi } from "../api/reception";
import type { AppointmentRow } from "../api/schemas/reception";
import { BarLineChart, DonutChart } from "../components/Charts";
import { Badge, Button, FieldRow, SelectField } from "../components/Controls";
import { DataTable, type Column } from "../components/DataTable";
import { KpiGrid } from "../components/Kpi";
import { Grid, Notice, PageHeader, Panel } from "../components/Panel";
import { Skeleton, SkeletonText } from "../components/Skeleton";
import { EmptyState, ErrorState } from "../components/StateViews";
import { useApi } from "../hooks/useApi";
import { useCursorPager } from "../hooks/useCursorPager";
import { formatDate, formatNumber, formatPercent } from "../lib/format";

const PAGE_SIZE = 25;
const STATUS_TONE: Record<string, "good" | "warn" | "bad" | "neutral"> = {
  Completed: "good",
  Cancelled: "warn",
  "No-Show": "bad",
};

const COLUMNS: Column<AppointmentRow>[] = [
  { key: "id", header: "Appointment", render: (r) => <code>{r.appointment_id}</code> },
  { key: "patient", header: "Patient ref.", render: (r) => <code>{r.patient_id}</code> },
  { key: "date", header: "Date", render: (r) => formatDate(r.appointment_date) },
  { key: "time", header: "Time", render: (r) => r.appointment_time ?? "—", numeric: true },
  { key: "doctor", header: "Clinician", render: (r) => r.doctor_name ?? "—" },
  { key: "visit", header: "Visit type", render: (r) => r.visit_type ?? "—" },
  { key: "status", header: "Status", render: (r) => <Badge tone={STATUS_TONE[r.status] ?? "neutral"}>{r.status}</Badge> },
  {
    key: "wait",
    header: "Wait",
    numeric: true,
    render: (r) => (r.status === "Completed" && r.waiting_time_minutes !== null ? `${formatNumber(r.waiting_time_minutes)} min` : "—"),
  },
];

export function ReceptionPage() {
  const kpis = useApi((s) => receptionApi.kpis(s), []);
  const dist = useApi((s) => receptionApi.statusDistribution(s), []);
  const waits = useApi((s) => receptionApi.waitInsights(s), []);
  const filters = useApi((s) => receptionApi.filters(s), []);

  const [status, setStatus] = useState("");
  const [department, setDepartment] = useState("");
  const [visitType, setVisitType] = useState("");
  const pager = useCursorPager();
  const appointments = useApi(
    (s) => receptionApi.appointments({ status, department, visit_type: visitType, limit: PAGE_SIZE, cursor: pager.cursor }, s),
    [status, department, visitType, pager.cursor],
  );

  const setFilter = (setter: (v: string) => void) => (v: string) => {
    setter(v);
    pager.reset();
  };
  const k = kpis.data;

  return (
    <div>
      <PageHeader
        eyebrow="Operations"
        title="Patient Access"
        subtitle="Outpatient volumes, attendance, no-shows and waiting-room performance across the network."
        badge="De-identified operational data"
      />
      <Notice>
        <strong>Minimum necessary (POL-HOSP-003).</strong> Operations analysts see pseudonymous patient references only: names,
        contact details, diagnoses and visit reasons are withheld. The log shows the non-clinical visit type.
      </Notice>

      <KpiGrid
        loading={kpis.loading}
        error={kpis.error}
        onRetry={kpis.reload}
        items={
          k && [
            { label: "Clinic visits", value: k.total_appointments, format: (n) => formatNumber(n), icon: "Calendar", hint: `${formatNumber(k.completed)} completed` },
            { label: "Completion rate", value: (k.completed / Math.max(1, k.total_appointments)) * 100, format: (n) => formatPercent(n), icon: "Check", tone: "good", hint: "Attended consultations" },
            { label: "No-show rate", value: k.no_show_rate_pct, format: (n) => formatPercent(n), icon: "Alert", tone: "bad", hint: `${formatPercent(k.cancellation_rate_pct)} cancelled` },
            {
              label: "Average wait",
              value: k.avg_wait_minutes,
              format: (n) => `${formatNumber(n, 1)} min`,
              icon: "Clock",
              tone: k.avg_wait_minutes <= 20 ? "good" : "warn",
              hint: "Target ≤ 20 min",
            },
          ]
        }
      />

      <Grid>
        <Panel title="Attendance distribution" subtitle="All appointments by outcome" icon="Users">
          {dist.error ? (
            <ErrorState error={dist.error} onRetry={dist.reload} />
          ) : dist.data ? (
            <DonutChart data={dist.data.items} centerLabel="Appointments" />
          ) : (
            <Skeleton height={240} radius={12} />
          )}
        </Panel>

        <Panel title="Arrivals & waiting time by hour" subtitle="Completed visits" icon="Clock">
          {waits.error ? (
            <ErrorState error={waits.error} onRetry={waits.reload} />
          ) : waits.data ? (
            waits.data.by_hour.length ? (
              <>
                <BarLineChart
                  data={waits.data.by_hour}
                  x="hour"
                  bar="volume"
                  line="avg_wait_min"
                  barName="Visits"
                  lineName="Avg wait (min)"
                  xFormatter={(h) => `${h}:00`}
                  height={200}
                />
                <ul style={{ margin: "12px 0 0", paddingLeft: 18, fontSize: 13, color: "var(--color-ink-3)", display: "grid", gap: 4 }}>
                  {waits.data.findings.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
                <p style={{ margin: "10px 0 0", fontSize: 12, color: "var(--color-text-muted)" }}>{waits.data.summary}</p>
              </>
            ) : (
              <EmptyState title="No completed visits yet" />
            )
          ) : (
            <SkeletonText lines={6} />
          )}
        </Panel>
      </Grid>

      <Panel
        title="Appointment log"
        subtitle="Most recent first"
        icon="Clipboard"
        actions={
          <FieldRow>
            <SelectField
              id="status"
              label="Status"
              value={status}
              onChange={setFilter(setStatus)}
              disabled={!filters.data}
              options={[{ value: "", label: "All statuses" }, ...(filters.data?.statuses ?? []).map((s) => ({ value: s, label: s }))]}
            />
            <SelectField
              id="visit-type"
              label="Visit type"
              value={visitType}
              onChange={setFilter(setVisitType)}
              disabled={!filters.data}
              options={[
                { value: "", label: "All visit types" },
                ...(filters.data?.visit_types ?? []).map((s) => ({ value: s, label: s.charAt(0).toUpperCase() + s.slice(1) })),
              ]}
            />
            <SelectField
              id="department"
              label="Department"
              value={department}
              onChange={setFilter(setDepartment)}
              disabled={!filters.data}
              options={[{ value: "", label: "All departments" }, ...(filters.data?.departments ?? []).map((s) => ({ value: s, label: s }))]}
            />
          </FieldRow>
        }
      >
        <DataTable
          columns={COLUMNS}
          rows={appointments.data?.items}
          rowKey={(r) => r.appointment_id}
          loading={appointments.loading}
          error={appointments.error}
          onRetry={appointments.reload}
          emptyTitle="No appointments match these filters"
          emptyHint="Clear a filter to widen the search."
          skeletonRows={8}
          caption="Appointment queue"
          footer={
            <>
              <span>Page {pager.page} · {PAGE_SIZE} per page</span>
              <span style={{ display: "flex", gap: 8 }}>
                <Button onClick={pager.prev} disabled={!pager.hasPrev || appointments.loading}>Previous</Button>
                <Button
                  onClick={() => pager.next(appointments.data?.next_cursor ?? null)}
                  disabled={!appointments.data?.next_cursor || appointments.loading}
                >
                  Next
                </Button>
              </span>
            </>
          }
        />
      </Panel>
    </div>
  );
}
