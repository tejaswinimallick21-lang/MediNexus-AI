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
export const STATUS_TONE: Record<string, "bad" | "warn" | "good" | "info" | "neutral"> = {
  "In treatment": "info",
  "Awaiting treatment": "warn",
  "Watchful waiting": "neutral",
  Surveillance: "good",
  Hospice: "bad",
  Deceased: "neutral",
};
export const TREND_ARROW: Record<string, string> = { Rising: "↑", Falling: "↓", Stable: "→" };
const CANCER_TYPES = ["Breast", "Prostate", "Lung", "Colon", "Melanoma", "Leukemia (CLL)", "Lymphoma (NHL)", "Pancreas"];

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
  const worklist = useApi((s) => clinicalApi.worklist(12, s), []);
  const gapSummary = useApi((s) => clinicalApi.careGapSummary(s), []);
  const [gap, setGap] = useState("treatment_delay");
  const gapPager = useCursorPager();
  const gaps = useApi((s) => clinicalApi.careGaps({ gap, limit: 8, cursor: gapPager.cursor }, s), [gap, gapPager.cursor]);

  const [search, setSearch] = useState("");
  const [cancerType, setCancerType] = useState("");
  const [stage, setStage] = useState("");
  const debounced = useDebounced(search);
  const pager = useCursorPager();
  useEffect(() => pager.reset(), [debounced, cancerType, stage]); // eslint-disable-line react-hooks/exhaustive-deps
  const patients = useApi(
    (s) => patientApi.search({ search: debounced, cancer_type: cancerType || undefined, stage: stage || undefined, limit: 10, cursor: pager.cursor }, s),
    [debounced, cancerType, stage, pager.cursor],
  );

  const k = kpis.data;
  const patientColumns: Column<PatientSummary>[] = [
    { key: "id", header: "Patient", render: (r) => <Link to={`patients/${r.patient_id}`}><code>{r.patient_id}</code></Link> },
    { key: "name", header: "Name", render: (r) => <Link to={`patients/${r.patient_id}`} className={styles.nameLink}>{r.name}</Link> },
    { key: "age", header: "Age", numeric: true, render: (r) => formatNumber(r.age) },
    { key: "cancer", header: "Cancer", render: (r) => r.cancer_type ?? "Not yet diagnosed" },
    { key: "stage", header: "Stage", render: (r) => r.cancer_stage ?? "—" },
    {
      key: "status",
      header: "Status",
      render: (r) =>
        r.is_deceased ? <Badge>Deceased</Badge> : r.treatment_status ? <Badge tone={STATUS_TONE[r.treatment_status]}>{r.treatment_status}</Badge> : "—",
    },
    { key: "tier", header: "Acuity", render: (r) => <Badge tone={TIER_TONE[r.clinical_risk_tier]}>{r.clinical_risk_tier}</Badge> },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Healthcare professional"
        title="Oncology Workstation"
        subtitle={k ? `Tumour board, care gaps and patient 360 · data through ${formatDate(k.data_through)}` : "Tumour board, care gaps and patient 360"}
      />

      <KpiGrid
        loading={kpis.loading}
        error={kpis.error}
        onRetry={kpis.reload}
        items={
          k && [
            { label: "Active cancer patients", value: k.active_patients, format: (n) => formatNumber(n), icon: "Users", hint: "Living, with a diagnosis" },
            { label: "In treatment", value: k.in_treatment, format: (n) => formatNumber(n), icon: "Pulse", hint: "Treatment in the last 30 days" },
            { label: "Awaiting treatment", value: k.awaiting_treatment, format: (n) => formatNumber(n), icon: "Clock", tone: "warn", hint: "Diagnosed ≤ 90 days, untreated" },
            { label: "High 12-month risk", value: k.high_mortality_risk, format: (n) => formatNumber(n), icon: "Alert", tone: "bad", hint: `${formatNumber(k.open_care_gaps)} open care gaps` },
          ]
        }
      />

      <Grid>
        <Panel title="Tumour-board worklist" subtitle="Living patients ranked by predicted 12-month mortality risk" icon="Stethoscope">
          {worklist.error ? (
            <ErrorState error={worklist.error} onRetry={worklist.reload} />
          ) : !worklist.data ? (
            <SkeletonText lines={10} />
          ) : worklist.data.length === 0 ? (
            <EmptyState title="No scored patients" />
          ) : (
            <ul className={styles.huddle}>
              {worklist.data.map((p, i) => (
                <motion.li key={p.patient_id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}>
                  <button type="button" className={styles.huddleCard} onClick={() => navigate(`patients/${p.patient_id}`)}>
                    <div className={styles.huddleTop}>
                      <div>
                        <strong>{p.name}</strong>
                        <span className={styles.meta}>
                          {p.patient_id} · {p.age} y · {p.cancer_type}
                          {p.cancer_stage ? ` stage ${p.cancer_stage}` : ""}
                          {p.days_since_diagnosis != null ? ` · diagnosed ${formatNumber(p.days_since_diagnosis)} days ago` : ""}
                        </span>
                      </div>
                      <div className={styles.prob}>
                        <span>{p.mortality_risk_pct.toFixed(1)}%</span>
                        <Badge tone={TIER_TONE[p.risk_level]}>{p.risk_level}</Badge>
                      </div>
                    </div>
                    <div className={styles.bar}>
                      <span style={{ width: `${Math.min(100, p.mortality_risk_pct)}%` }} />
                    </div>
                    <div className={styles.chips}>
                      <Badge tone={STATUS_TONE[p.treatment_status]}>{p.treatment_status}</Badge>
                      {p.systemic_regimen && <span className={styles.reason}>{p.systemic_regimen}</span>}
                      {p.drivers.map((d) => (
                        <span key={d} className={styles.chip}>{d}</span>
                      ))}
                      {p.tumor_marker && p.marker_trend && (
                        <span className={styles.chip}>
                          {p.tumor_marker} {TREND_ARROW[p.marker_trend] ?? ""} {p.marker_value != null ? formatNumber(p.marker_value, 1) : ""}
                        </span>
                      )}
                    </div>
                  </button>
                </motion.li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Care-gap radar" subtitle="Patients missing a step of the oncology pathway" icon="Pulse">
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
        subtitle="Search by name or patient ID; filter by cancer type and stage"
        icon="Users"
        actions={
          <FieldRow>
            <label className={styles.search}>
              <span>Search</span>
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="e.g. P_00016 or Walker" />
            </label>
            <SelectField
              id="cancer-type"
              label="Cancer"
              value={cancerType}
              onChange={setCancerType}
              options={[{ value: "", label: "All" }, ...CANCER_TYPES.map((t) => ({ value: t, label: t }))]}
            />
            <SelectField
              id="stage"
              label="Stage"
              value={stage}
              onChange={setStage}
              options={[{ value: "", label: "All" }, ...["I", "II", "III", "IV"].map((s) => ({ value: s, label: `Stage ${s}` }))]}
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
                <Button onClick={() => pager.next(patients.data?.next_cursor ?? null)} disabled={!patients.data?.next_cursor || patients.loading}>
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
