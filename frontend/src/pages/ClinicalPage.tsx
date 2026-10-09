import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Link, Route, Routes, useNavigate } from "react-router-dom";

import { clinicalApi, patientApi } from "../api/clinical";
import type { PatientSummary } from "../api/schemas/clinical";
import { Badge, Button, FieldRow, SelectField } from "../components/Controls";
import { DataTable, type Column } from "../components/DataTable";
import { Icon } from "../components/Icons";
import { KpiGrid } from "../components/Kpi";
import { Grid, PageHeader, Panel } from "../components/Panel";
import { SkeletonText } from "../components/Skeleton";
import { EmptyState, ErrorState } from "../components/StateViews";
import { useApi } from "../hooks/useApi";
import { useCursorPager } from "../hooks/useCursorPager";
import { formatDate, formatNumber } from "../lib/format";
import { PatientPage } from "./PatientPage";
import styles from "./ClinicalPage.module.css";

export const TIER_TONE: Record<string, "bad" | "warn" | "good"> = { High: "bad", Moderate: "warn", Low: "good", HIGH: "bad", MODERATE: "warn", LOW: "good" };

/** /doctor/* : workstation home and nested patient pages. */
export function ClinicalWorkspace() {
  return (
    <Routes>
      <Route index element={<ClinicalHome />} />
      <Route path="patients/:patientId" element={<PatientPage />} />
    </Routes>
  );
}

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function ClinicalHome() {
  const navigate = useNavigate();
  const kpis = useApi((s) => clinicalApi.kpis(s), []);
  const huddle = useApi((s) => clinicalApi.huddle(12, s), []);
  const gapSummary = useApi((s) => clinicalApi.careGapSummary(s), []);
  const [gap, setGap] = useState("high_risk_no_follow_up");
  const gapPager = useCursorPager();
  const gaps = useApi((s) => clinicalApi.careGaps({ gap, limit: 8, cursor: gapPager.cursor }, s), [gap, gapPager.cursor]);

  const [search, setSearch] = useState("");
  const [tier, setTier] = useState("");
  const debounced = useDebounced(search);
  const pager = useCursorPager();
  useEffect(() => pager.reset(), [debounced, tier]); // eslint-disable-line react-hooks/exhaustive-deps
  const patients = useApi((s) => patientApi.search({ search: debounced, tier, limit: 10, cursor: pager.cursor }, s), [debounced, tier, pager.cursor]);

  const k = kpis.data;
  const patientColumns: Column<PatientSummary>[] = [
    { key: "id", header: "Patient", render: (r) => <Link to={`patients/${r.patient_id}`}><code>{r.patient_id}</code></Link> },
    { key: "name", header: "Name", render: (r) => <Link to={`patients/${r.patient_id}`} className={styles.nameLink}>{r.name}</Link> },
    { key: "age", header: "Age", numeric: true, render: (r) => formatNumber(r.age) },
    { key: "gender", header: "Sex", render: (r) => r.gender },
    { key: "adm", header: "Admissions", numeric: true, render: (r) => formatNumber(r.total_admissions) },
    {
      key: "tier",
      header: "Acuity",
      render: (r) => (r.is_deceased ? <Badge>Deceased</Badge> : <Badge tone={TIER_TONE[r.clinical_risk_tier]}>{r.clinical_risk_tier}</Badge>),
    },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Healthcare professional"
        title="Clinical Workstation"
        subtitle={k ? `Morning huddle, care gaps and patient 360 · data through ${formatDate(k.data_through)}` : "Morning huddle, care gaps and patient 360"}
      />

      <KpiGrid
        loading={kpis.loading}
        error={kpis.error}
        onRetry={kpis.reload}
        items={
          k && [
            { label: "Living patients", value: k.living_patients, format: (n) => formatNumber(n), icon: "Users", hint: `${formatNumber(k.high_tier_patients)} high acuity` },
            { label: "Discharged · 30 days", value: k.recent_discharges, format: (n) => formatNumber(n), icon: "Home", hint: "Latest stay per patient" },
            { label: "High readmission risk", value: k.high_risk_recent_discharges, format: (n) => formatNumber(n), icon: "Alert", tone: "bad", hint: "Top decile of the model" },
            { label: "Open care gaps", value: k.open_care_gaps, format: (n) => formatNumber(n), icon: "Clipboard", tone: "warn", hint: "Guideline monitoring overdue" },
          ]
        }
      />

      <Grid>
        <Panel title="Morning huddle" subtitle="Recent discharges ranked by unplanned 30-day readmission risk" icon="Stethoscope">
          {huddle.error ? (
            <ErrorState error={huddle.error} onRetry={huddle.reload} />
          ) : !huddle.data ? (
            <SkeletonText lines={10} />
          ) : huddle.data.length === 0 ? (
            <EmptyState title="No recent discharges" />
          ) : (
            <ul className={styles.huddle}>
              {huddle.data.map((p, i) => (
                <motion.li key={p.patient_id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}>
                  <button type="button" className={styles.huddleCard} onClick={() => navigate(`patients/${p.patient_id}`)}>
                    <div className={styles.huddleTop}>
                      <div>
                        <strong>{p.name}</strong>
                        <span className={styles.meta}>
                          {p.patient_id} · {p.age} y · {p.gender} · discharged {formatDate(p.discharge_date)}
                        </span>
                      </div>
                      <div className={styles.prob}>
                        <span>{p.readmission_probability_pct.toFixed(1)}%</span>
                        <Badge tone={TIER_TONE[p.risk_level]}>{p.risk_level}</Badge>
                      </div>
                    </div>
                    <div className={styles.bar}>
                      <span style={{ width: `${Math.min(100, p.readmission_probability_pct)}%` }} />
                    </div>
                    <div className={styles.chips}>
                      {p.admission_reason && <span className={styles.reason}>{p.admission_reason}</span>}
                      {p.drivers.map((d) => (
                        <span key={d} className={styles.chip}>{d}</span>
                      ))}
                      {!p.has_follow_up && p.risk_level === "HIGH" && <Badge tone="bad">No follow-up booked</Badge>}
                    </div>
                  </button>
                </motion.li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Care-gap radar" subtitle="Patients overdue for guideline monitoring" icon="Pulse">
          {gapSummary.error ? (
            <ErrorState error={gapSummary.error} onRetry={gapSummary.reload} />
          ) : !gapSummary.data ? (
            <SkeletonText lines={4} />
          ) : (
            <div className={styles.gapCards}>
              {gapSummary.data.map((g) => (
                <button
                  key={g.gap}
                  type="button"
                  className={`${styles.gapCard} ${g.gap === gap ? styles.gapActive : ""}`}
                  onClick={() => {
                    setGap(g.gap);
                    gapPager.reset();
                  }}
                >
                  <strong>{formatNumber(g.patients)}</strong>
                  <span>{g.label}</span>
                  <em>{g.guideline}</em>
                </button>
              ))}
            </div>
          )}
          <div style={{ marginTop: 16 }}>
            {gaps.error ? (
              <ErrorState error={gaps.error} onRetry={gaps.reload} />
            ) : !gaps.data || gaps.loading ? (
              <SkeletonText lines={5} />
            ) : gaps.data.items.length === 0 ? (
              <EmptyState title="No open gaps of this type" />
            ) : (
              <ul className={styles.gapList}>
                {gaps.data.items.map((g) => (
                  <li key={`${g.patient_id}-${g.gap}`}>
                    <Link to={`patients/${g.patient_id}`}>
                      <strong>{g.name}</strong> <span className={styles.meta}>{g.patient_id} · {g.age} y</span>
                    </Link>
                    <span className={styles.meta}>{g.detail}</span>
                  </li>
                ))}
              </ul>
            )}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
              <Button onClick={gapPager.prev} disabled={!gapPager.hasPrev}>Previous</Button>
              <Button onClick={() => gapPager.next(gaps.data?.next_cursor ?? null)} disabled={!gaps.data?.next_cursor}>Next</Button>
            </div>
          </div>
        </Panel>
      </Grid>

        <Panel
          title="Patient finder"
          subtitle="Search by name or patient ID"
          icon="Users"
          actions={
            <FieldRow>
              <label className={styles.search}>
                <span>Search</span>
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="e.g. P_00016 or Barrows" />
              </label>
              <SelectField
                id="tier"
                label="Acuity"
                value={tier}
                onChange={setTier}
                options={[
                  { value: "", label: "All" },
                  { value: "High", label: "High" },
                  { value: "Moderate", label: "Moderate" },
                  { value: "Low", label: "Low" },
                ]}
              />
            </FieldRow>
          }
        >
          <DataTable
            columns={patientColumns}
            rows={patients.data?.items}
            rowKey={(r) => r.patient_id}
            loading={patients.loading}
            error={patients.error}
            onRetry={patients.reload}
            emptyTitle="No matching patients"
            caption="Patients"
            footer={
              <>
                <span>
                  <Icon.Lock size={12} /> Every patient record you open is recorded in the audit trail.
                </span>
                <span style={{ display: "flex", gap: 8 }}>
                  <Button onClick={pager.prev} disabled={!pager.hasPrev || patients.loading}>Previous</Button>
                  <Button onClick={() => pager.next(patients.data?.next_cursor ?? null)} disabled={!patients.data?.next_cursor || patients.loading}>Next</Button>
                </span>
              </>
            }
          />
        </Panel>
    </div>
  );
}
