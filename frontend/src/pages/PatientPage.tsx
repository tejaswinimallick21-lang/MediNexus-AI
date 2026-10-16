import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { patientApi } from "../api/clinical";
import type { Encounter, LabResult, Medication, Patient360, TreatmentEvent } from "../api/schemas/clinical";
import { Badge, Button, SelectField } from "../components/Controls";
import { DataTable, type Column } from "../components/DataTable";
import { Icon } from "../components/Icons";
import { Grid, Panel } from "../components/Panel";
import { Skeleton, SkeletonText } from "../components/Skeleton";
import { EmptyState, ErrorState } from "../components/StateViews";
import { Tabs } from "../components/Tabs";
import { useApi } from "../hooks/useApi";
import { useCursorPager } from "../hooks/useCursorPager";
import { formatDate, formatNumber, formatUSD } from "../lib/format";
import { STATUS_TONE, TIER_TONE, TREND_ARROW } from "./ClinicalPage";
import { Stat } from "./LaboratoryPage";
import styles from "./PatientPage.module.css";

type TabId = "risk" | "treatment" | "labs" | "meds" | "encounters";
const FLAG_TONE: Record<string, "bad" | "warn" | "good"> = { Critical: "bad", High: "warn", Low: "warn", Normal: "good" };
const FLAG_LABEL: Record<string, string> = {
  has_hypertension: "Hypertension",
  has_diabetes: "Diabetes",
  has_copd: "COPD",
  has_heart_failure: "Heart failure",
  has_ckd: "CKD",
  has_obesity: "Obesity",
};

export function PatientPage() {
  const { patientId = "" } = useParams();
  const patient = useApi((s) => patientApi.get(patientId, s), [patientId]);
  const [tab, setTab] = useState<TabId>("risk");
  const p = patient.data;

  return (
    <div>
      <Link to="/doctor" className={styles.back}>
        <Icon.Arrow size={14} style={{ transform: "rotate(180deg)" }} /> Oncology Workstation
      </Link>

      {patient.error ? (
        <ErrorState error={patient.error} onRetry={patient.reload} />
      ) : !p ? (
        <Skeleton height={150} radius={16} />
      ) : (
        <section className={styles.header}>
          <div className={styles.avatar}>{p.name.split(" ").map((w) => w[0]).join("").slice(0, 2)}</div>
          <div className={styles.identity}>
            <h1>{p.name}</h1>
            <span>
              <code>{p.patient_id}</code> · {p.age} y · {p.gender} · {p.blood_group ?? "—"} · {p.insurance_provider ?? "—"} · {p.city ?? "—"}
            </span>
            <div className={styles.flags}>
              {p.cancer_type && (
                <Badge tone="bad">
                  {p.cancer_type}
                  {p.cancer_stage ? ` · stage ${p.cancer_stage}` : ""}
                </Badge>
              )}
              {p.is_deceased ? (
                <Badge>Deceased {p.death_date ? formatDate(p.death_date) : ""}</Badge>
              ) : (
                p.treatment_status && <Badge tone={STATUS_TONE[p.treatment_status]}>{p.treatment_status}</Badge>
              )}
              <Badge tone={TIER_TONE[p.clinical_risk_tier]}>{p.clinical_risk_tier} acuity</Badge>
              {Object.entries(p.flags)
                .filter(([, on]) => on)
                .map(([k]) => (
                  <Badge key={k} tone="info">{FLAG_LABEL[k] ?? k}</Badge>
                ))}
            </div>
          </div>
          <div className={styles.stats}>
            <Stat label="Diagnosed" value={p.diagnosis_date ? formatDate(p.diagnosis_date) : "—"} />
            <Stat label="Days to treatment" value={p.days_to_treatment != null ? formatNumber(p.days_to_treatment) : "—"} />
            <Stat
              label={p.tumor_marker ?? "Tumour marker"}
              value={p.marker_value != null ? `${formatNumber(p.marker_value, 1)} ${p.marker_trend ? TREND_ARROW[p.marker_trend] ?? "" : ""}` : "—"}
            />
            <Stat label="Lifetime billing" value={formatUSD(p.lifetime_billing, { whole: true })} />
          </div>
        </section>
      )}

      {p && p.care_gaps.length > 0 && (
        <div className={styles.gapAlert} role="status">
          <Icon.Alert size={18} />
          <div>
            <strong>Open care gaps:</strong> {p.care_gaps.map((g) => `${g.label}: ${g.detail}`).join(" · ")}
          </div>
        </div>
      )}

      <Tabs<TabId>
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "risk", label: "Risk & care plan" },
          { id: "treatment", label: "Treatment timeline" },
          { id: "labs", label: "Labs & tumour markers" },
          { id: "meds", label: "Medications" },
          { id: "encounters", label: "Surgical stays" },
        ]}
      />

      {tab === "risk" && <RiskTab patientId={patientId} patient={p} />}
      {tab === "treatment" && <TreatmentTab patientId={patientId} />}
      {tab === "labs" && <LabsTab patientId={patientId} preferred={p?.tumor_marker ?? undefined} />}
      {tab === "meds" && <MedsTab patientId={patientId} />}
      {tab === "encounters" && <EncountersTab patientId={patientId} />}
    </div>
  );
}

function RiskTab({ patientId, patient }: { patientId: string; patient?: Patient360 }) {
  const risk = useApi((s) => patientApi.risk(patientId, s), [patientId]);
  const [done, setDone] = useState<Record<string, boolean>>({});
  if (risk.error) return <ErrorState error={risk.error} onRetry={risk.reload} />;
  if (!risk.data) return <SkeletonText lines={10} />;
  const r = risk.data;
  const b = r.survival_benchmark;

  return (
    <>
      <Grid columns={3}>
        <Panel title="12-month mortality risk" subtitle={r.scored_as_of ? `Scored on history up to ${r.scored_as_of}` : "Living cancer patients only"} icon="Alert">
          {r.available && r.mortality_12m_pct != null ? (
            <div className={styles.riskBig}>
              <strong>{r.mortality_12m_pct.toFixed(1)}%</strong>
              <Badge tone={TIER_TONE[r.risk_level ?? "LOW"]}>{r.risk_level}</Badge>
              <span>
                Population rate {r.cohort_rate_pct}% · method: {r.method}
              </span>
              <ul>{r.drivers.map((d) => <li key={d}>{d}</li>)}</ul>
            </div>
          ) : (
            <EmptyState title="Not scored" hint="Only living patients with a cancer diagnosis are scored." />
          )}
        </Panel>
        <Panel title="Survival benchmark" subtitle={b ? `${b.group} · ${formatNumber(b.patients)} patients` : "Same cancer type and stage"} icon="Shield">
          {b ? (
            <div className={styles.riskBig}>
              <strong>{b.five_year_pct != null ? `${formatNumber(b.five_year_pct, 1)}%` : "—"}</strong>
              <span>5-year survival from diagnosis (Kaplan-Meier)</span>
              <span>1-year survival {b.one_year_pct != null ? `${formatNumber(b.one_year_pct, 1)}%` : "—"}</span>
            </div>
          ) : (
            <EmptyState title="No benchmark" hint="Too few patients with this cancer type and stage." />
          )}
        </Panel>
        <Panel title="Treatment so far" subtitle={patient?.first_treatment_date ? `Started ${formatDate(patient.first_treatment_date)}` : "No treatment recorded"} icon="Pulse">
          {patient ? (
            <div className={styles.conditions}>
              {patient.surgery_procedure && <span>Surgery: {patient.surgery_procedure}</span>}
              {patient.systemic_regimen && <span>Regimen: {patient.systemic_regimen}</span>}
              {patient.chemo_cycles > 0 && <span>{patient.chemo_cycles} chemotherapy cycles</span>}
              {patient.immunotherapy_cycles > 0 && <span>{patient.immunotherapy_cycles} immunotherapy cycles</span>}
              {patient.targeted_therapy_cycles > 0 && <span>{patient.targeted_therapy_cycles} targeted-therapy cycles</span>}
              {patient.radiation_sessions > 0 && <span>{patient.radiation_sessions} radiation sessions</span>}
              {patient.comorbidities.slice(0, 4).map((c) => <span key={c}>{c}</span>)}
            </div>
          ) : (
            <SkeletonText lines={4} />
          )}
        </Panel>
      </Grid>

      <div style={{ height: 20 }} />
      <Panel title={r.care_plan.primary_recommendation} subtitle={r.care_plan.pathway} icon="Check">
        {r.care_plan.checklist.length > 0 ? (
          <ul className={styles.checklist}>
            {r.care_plan.checklist.map((item) => (
              <li key={item}>
                <label>
                  <input type="checkbox" checked={!!done[item]} onChange={(e) => setDone((d) => ({ ...d, [item]: e.target.checked }))} />
                  <span className={done[item] ? styles.doneItem : undefined}>{item}</span>
                </label>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No active care plan" />
        )}
        <p className={styles.note}>{r.care_plan.rationale.join(" ")}</p>
        <p className={styles.note}>
          <Icon.Shield size={12} /> {r.disclaimer}
        </p>
      </Panel>
    </>
  );
}

const EVENT_TONE: Record<string, "bad" | "warn" | "good" | "info" | "neutral"> = {
  Surgery: "bad",
  Chemotherapy: "info",
  Immunotherapy: "good",
  "Targeted therapy": "good",
  Radiation: "warn",
  Hospice: "neutral",
};

function TreatmentTab({ patientId }: { patientId: string }) {
  const tx = useApi((s) => patientApi.treatments(patientId, s), [patientId]);
  if (tx.error) return <ErrorState error={tx.error} onRetry={tx.reload} />;
  if (!tx.data) return <SkeletonText lines={8} />;
  if (tx.data.length === 0) return <EmptyState title="No treatment recorded" hint="No surgery, systemic therapy or radiation yet." />;
  return (
    <ol className={styles.timeline}>
      {tx.data.map((e: TreatmentEvent, i) => (
        <li key={`${e.event_date}-${e.event_type}-${i}`}>
          <span className={styles.dot} />
          <div className={styles.encCard}>
            <div className={styles.encTop}>
              <strong>
                {e.event_type}
                {e.cycle != null ? ` · cycle ${e.cycle}` : ""}
              </strong>
              <span>{formatDate(e.event_date)}</span>
            </div>
            <div className={styles.flags}>
              <Badge tone={EVENT_TONE[e.event_type] ?? "neutral"}>{e.detail ?? e.event_type}</Badge>
              {e.hospital_name && <Badge>{e.hospital_name}</Badge>}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function parseRange(range: string | null): [number, number] | null {
  const m = range ? /([\d.]+)\s*-\s*([\d.]+)/.exec(range) : null;
  return m ? [Number(m[1]), Number(m[2])] : null;
}

function LabsTab({ patientId, preferred }: { patientId: string; preferred?: string }) {
  const tests = useApi((s) => patientApi.labTests(patientId, s), [patientId]);
  const [test, setTest] = useState("");
  useEffect(() => {
    if (!test && tests.data?.length) setTest(preferred && tests.data.includes(preferred) ? preferred : tests.data[0]);
  }, [tests.data, test, preferred]);
  const series = useApi((s) => patientApi.labSeries(patientId, test, s), [patientId, test], { enabled: !!test });
  const pager = useCursorPager();
  const labs = useApi((s) => patientApi.labs(patientId, { limit: 15, cursor: pager.cursor }, s), [patientId, pager.cursor]);
  const range = parseRange(series.data?.reference_range ?? null);

  const columns: Column<LabResult>[] = [
    { key: "date", header: "Date", render: (r) => formatDate(r.test_date) },
    { key: "test", header: "Test", render: (r) => r.test_name },
    { key: "value", header: "Result", numeric: true, render: (r) => `${r.test_value != null ? formatNumber(r.test_value, 2) : "—"} ${r.unit ?? ""}` },
    { key: "range", header: "Reference", render: (r) => r.reference_range ?? "—" },
    { key: "flag", header: "Flag", render: (r) => <Badge tone={FLAG_TONE[r.abnormal_flag] ?? "neutral"}>{r.abnormal_flag}</Badge> },
  ];

  if (tests.data && tests.data.length === 0) return <EmptyState title="No laboratory results for this patient" />;
  return (
    <>
      <Panel
        title={series.data ? `${series.data.test_name} trend` : "Biomarker trend"}
        subtitle={series.data?.reference_range ? `Shaded band = reference range ${series.data.reference_range} ${series.data.unit ?? ""}` : undefined}
        icon="Pulse"
        actions={
          <SelectField id="lab-test" label="Test" value={test} onChange={setTest} disabled={!tests.data} options={(tests.data ?? []).map((t) => ({ value: t, label: t }))} />
        }
      >
        {series.error ? (
          <ErrorState error={series.error} onRetry={series.reload} />
        ) : !series.data || series.loading ? (
          <Skeleton height={260} radius={12} />
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={series.data.points} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              {range && <ReferenceArea y1={range[0]} y2={range[1]} fill="#14b8a6" fillOpacity={0.08} />}
              <XAxis dataKey="test_date" tickFormatter={(d) => formatDate(d)} tick={{ fontSize: 12, fill: "#5b6b82" }} tickLine={false} axisLine={false} minTickGap={30} />
              <YAxis tick={{ fontSize: 12, fill: "#5b6b82" }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
              <Tooltip labelFormatter={(d) => formatDate(String(d))} formatter={(v: number) => [`${formatNumber(v, 2)} ${series.data?.unit ?? ""}`, series.data?.test_name]} />
              <Line type="monotone" dataKey="test_value" stroke="#0284c7" strokeWidth={2.4} dot={{ r: 3, fill: "#0284c7" }} animationDuration={900} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Panel>
      <div style={{ height: 20 }} />
      <Panel title="All results" subtitle="Most recent first" icon="Flask">
        <DataTable
          columns={columns}
          rows={labs.data?.items}
          rowKey={(r) => `${r.test_date}-${r.test_name}-${r.test_value}`}
          loading={labs.loading}
          error={labs.error}
          onRetry={labs.reload}
          caption="Laboratory results"
          footer={
            <>
              <span>Page {pager.page}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <Button onClick={pager.prev} disabled={!pager.hasPrev}>Previous</Button>
                <Button onClick={() => pager.next(labs.data?.next_cursor ?? null)} disabled={!labs.data?.next_cursor}>Next</Button>
              </span>
            </>
          }
        />
      </Panel>
    </>
  );
}

function MedsTab({ patientId }: { patientId: string }) {
  const pager = useCursorPager();
  const meds = useApi((s) => patientApi.medications(patientId, { limit: 20, cursor: pager.cursor }, s), [patientId, pager.cursor]);
  const columns: Column<Medication>[] = [
    { key: "name", header: "Medication", render: (r) => r.medication_name ?? "—" },
    { key: "cat", header: "Class", render: (r) => r.category ?? "—" },
    { key: "dose", header: "Strength", render: (r) => r.dosage ?? "—" },
    { key: "for", header: "Indication", render: (r) => r.indication ?? "—" },
    { key: "start", header: "Started", render: (r) => formatDate(r.prescription_date) },
    { key: "end", header: "Ended", render: (r) => (r.end_date ? formatDate(r.end_date) : "Ongoing") },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.status === "Active" ? "good" : "neutral"}>{r.status}</Badge> },
  ];
  return (
    <Panel title="Prescriptions" subtitle="Active first" icon="Pill">
      <DataTable
        columns={columns}
        rows={meds.data?.items}
        rowKey={(r) => `${r.prescription_date}-${r.medication_name}-${r.status}`}
        loading={meds.loading}
        error={meds.error}
        onRetry={meds.reload}
        emptyTitle="No prescriptions recorded"
        caption="Prescriptions"
        footer={
          <>
            <span>Page {pager.page}</span>
            <span style={{ display: "flex", gap: 8 }}>
              <Button onClick={pager.prev} disabled={!pager.hasPrev}>Previous</Button>
              <Button onClick={() => pager.next(meds.data?.next_cursor ?? null)} disabled={!meds.data?.next_cursor}>Next</Button>
            </span>
          </>
        }
      />
    </Panel>
  );
}

function EncountersTab({ patientId }: { patientId: string }) {
  const enc = useApi((s) => patientApi.encounters(patientId, s), [patientId]);
  if (enc.error) return <ErrorState error={enc.error} onRetry={enc.reload} />;
  if (!enc.data) return <SkeletonText lines={8} />;
  if (enc.data.length === 0) return <EmptyState title="No surgical stays" hint="This patient has outpatient care only." />;
  return (
    <ol className={styles.timeline}>
      {enc.data.map((e: Encounter) => (
        <li key={e.admission_id}>
          <span className={styles.dot} />
          <div className={styles.encCard}>
            <div className={styles.encTop}>
              <strong>{e.surgery_procedure ?? e.admission_reason ?? "Inpatient stay"}</strong>
              <span>
                {formatDate(e.admission_date)} → {formatDate(e.discharge_date)} · {e.length_of_stay_days != null ? `${formatNumber(e.length_of_stay_days, 1)} d` : "—"}
              </span>
            </div>
            <div className={styles.flags}>
              <Badge tone="info">{e.department_name ?? "—"}</Badge>
              <Badge>{e.admission_type}</Badge>
              <Badge tone={e.discharge_disposition === "Deceased" ? "bad" : "neutral"}>{e.discharge_disposition}</Badge>
              {e.admission_reason && <Badge>{e.admission_reason}</Badge>}
            </div>
            {e.diagnoses.length > 0 && <p className={styles.note}>{e.diagnoses.join(" · ")}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
