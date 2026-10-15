import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { patientApi } from "../api/clinical";
import type { Encounter, LabResult, Medication } from "../api/schemas/clinical";
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
import { TIER_TONE } from "./ClinicalPage";
import { Stat } from "./LaboratoryPage";
import styles from "./PatientPage.module.css";

type TabId = "risk" | "labs" | "meds" | "encounters";
const FLAG_TONE: Record<string, "bad" | "warn" | "good"> = { Critical: "bad", High: "warn", Low: "warn", Normal: "good" };
const FLAG_LABEL: Record<string, string> = {
  has_hypertension: "Hypertension",
  has_diabetes: "Diabetes",
  has_copd: "COPD",
  has_heart_failure: "Heart failure",
  has_ckd: "CKD",
  has_cancer: "Cancer",
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
        <Icon.Arrow size={14} style={{ transform: "rotate(180deg)" }} /> Clinical Workstation
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
              {p.is_deceased && <Badge>Deceased {p.death_date ? formatDate(p.death_date) : ""}</Badge>}
              <Badge tone={TIER_TONE[p.clinical_risk_tier]}>{p.clinical_risk_tier} acuity</Badge>
              {Object.entries(p.flags)
                .filter(([, on]) => on)
                .map(([k]) => (
                  <Badge key={k} tone="info">{FLAG_LABEL[k] ?? k}</Badge>
                ))}
            </div>
          </div>
          <div className={styles.stats}>
            <Stat label="Admissions" value={formatNumber(p.total_admissions)} />
            <Stat label="Unplanned readmits" value={formatNumber(p.unplanned_readmissions)} />
            <Stat label="Critical labs" value={formatNumber(p.critical_lab_count)} />
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
          { id: "labs", label: "Labs & vitals" },
          { id: "meds", label: "Medications" },
          { id: "encounters", label: "Hospital stays" },
        ]}
      />

      {tab === "risk" && <RiskTab patientId={patientId} comorbidities={p?.comorbidities} />}
      {tab === "labs" && <LabsTab patientId={patientId} />}
      {tab === "meds" && <MedsTab patientId={patientId} />}
      {tab === "encounters" && <EncountersTab patientId={patientId} />}
    </div>
  );
}

function RiskTab({ patientId, comorbidities }: { patientId: string; comorbidities?: string[] }) {
  const risk = useApi((s) => patientApi.risk(patientId, s), [patientId]);
  const [done, setDone] = useState<Record<string, boolean>>({});
  if (risk.error) return <ErrorState error={risk.error} onRetry={risk.reload} />;
  if (!risk.data) return <SkeletonText lines={10} />;
  const r = risk.data;

  return (
    <>
      <Grid columns={3}>
        <Panel title="Unplanned readmission" subtitle={r.readmission_admission_date ? `Most recent stay · ${formatDate(r.readmission_admission_date)}` : "No inpatient stay"} icon="Alert">
          {r.readmission_available && r.readmission_probability_pct != null ? (
            <div className={styles.riskBig}>
              <strong>{r.readmission_probability_pct.toFixed(1)}%</strong>
              <Badge tone={TIER_TONE[r.readmission_risk_level ?? "LOW"]}>{r.readmission_risk_level}</Badge>
              <span>Network base rate {r.readmission_base_rate_pct}%</span>
              <ul>{r.readmission_drivers.map((d) => <li key={d}>{d}</li>)}</ul>
            </div>
          ) : (
            <EmptyState title="Not applicable" hint="The patient has no inpatient admission to score." />
          )}
        </Panel>
        <Panel title="Expected length of stay" subtitle="Admission-time model" icon="Clock">
          {r.los_predicted_days != null ? (
            <div className={styles.riskBig}>
              <strong>{formatNumber(r.los_predicted_days, 1)} d</strong>
              <span>Interval {r.los_interval}</span>
              {r.los_observed_days != null && <span>Observed on that stay: {formatNumber(r.los_observed_days, 1)} d</span>}
            </div>
          ) : (
            <EmptyState title="Not applicable" />
          )}
        </Panel>
        <Panel title="Chronic conditions" subtitle="Moderate / severe diagnoses" icon="Pulse">
          {comorbidities?.length ? (
            <div className={styles.conditions}>{comorbidities.map((c) => <span key={c}>{c}</span>)}</div>
          ) : (
            <EmptyState title="None recorded" />
          )}
        </Panel>
      </Grid>

      <Panel title="12-month outcome risk" subtitle={`Scored on history up to ${r.outcome_scored_as_of ?? "today"}`} icon="Shield">
        <div className={styles.outlookGrid}>
          {r.outcome_risks.map((o) => (
            <div key={o.outcome} className={styles.outlookCard}>
              <span className={styles.outlookLabel}>{o.label}</span>
              <strong>{o.probability_pct.toFixed(1)}%</strong>
              <Badge tone={TIER_TONE[o.risk_level]}>{o.risk_level}</Badge>
              <span className={styles.outlookMeta}>
                Population rate {o.cohort_rate_pct}%{o.observed != null ? ` · observed: ${o.observed ? "yes" : "no"}` : ""}
              </span>
            </div>
          ))}
        </div>
        <p className={styles.note}>Main drivers: {r.outcome_drivers.join(", ")}</p>
      </Panel>

      <div style={{ height: 20 }} />
      <Panel title={r.care_plan.primary_recommendation} subtitle={r.care_plan.pathway} icon="Check">
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
        <p className={styles.note}>{r.care_plan.rationale.join(" ")}</p>
        <p className={styles.note}>
          <Icon.Shield size={12} /> {r.disclaimer}
        </p>
      </Panel>
    </>
  );
}

function parseRange(range: string | null): [number, number] | null {
  const m = range ? /([\d.]+)\s*-\s*([\d.]+)/.exec(range) : null;
  return m ? [Number(m[1]), Number(m[2])] : null;
}

function LabsTab({ patientId }: { patientId: string }) {
  const tests = useApi((s) => patientApi.labTests(patientId, s), [patientId]);
  const [test, setTest] = useState("");
  useEffect(() => {
    if (!test && tests.data?.length) setTest(tests.data.includes("HbA1c") ? "HbA1c" : tests.data[0]);
  }, [tests.data, test]);
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
  if (enc.data.length === 0) return <EmptyState title="No hospital stays" hint="This patient has outpatient care only." />;
  return (
    <ol className={styles.timeline}>
      {enc.data.map((e: Encounter) => (
        <li key={e.admission_id}>
          <span className={styles.dot} />
          <div className={styles.encCard}>
            <div className={styles.encTop}>
              <strong>{e.admission_reason ?? "Inpatient stay"}</strong>
              <span>
                {formatDate(e.admission_date)} → {formatDate(e.discharge_date)} · {e.length_of_stay_days != null ? `${formatNumber(e.length_of_stay_days, 1)} d` : "—"}
              </span>
            </div>
            <div className={styles.flags}>
              <Badge tone="info">{e.department_name ?? "—"}</Badge>
              <Badge>{e.admission_type}</Badge>
              <Badge tone={e.discharge_disposition === "Deceased" ? "bad" : "neutral"}>{e.discharge_disposition}</Badge>
              {e.is_icu && <Badge tone="bad">ICU</Badge>}
              {e.readmitted_30d && <Badge tone="warn">Unplanned readmission followed</Badge>}
            </div>
            {e.diagnoses.length > 0 && <p className={styles.note}>{e.diagnoses.join(" · ")}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
