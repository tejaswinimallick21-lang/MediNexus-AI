import { dataApi } from "../api/dataPlatform";
import { Badge } from "../components/Controls";
import { Panel } from "../components/Panel";
import { SkeletonText } from "../components/Skeleton";
import { useApi } from "../hooks/useApi";
import { formatDate, formatNumber } from "../lib/format";
import styles from "./DatasetPanel.module.css";

const REPAIR_LABELS: Record<string, string> = {
  encounters_after_as_of_dropped: "visits dated after the as-of date removed",
  encounters_after_death_dropped: "visits after the patient's death removed",
  impossible_lab_values_dropped: "impossible lab values removed",
};

/** The fixed oncology dataset behind every workspace, and what was repaired when it was prepared. */
export function DatasetPanel() {
  const ds = useApi((s) => dataApi.dataset(s), []);
  const d = ds.data;
  const repairs = d ? Object.entries(d.repairs).filter(([k]) => k in REPAIR_LABELS) : [];
  return (
    <Panel title="Dataset" subtitle="Synthetic oncology records (Synthea format), fixed as of one date; every workspace reads this data" icon="Pulse">
      {!d ? (
        <SkeletonText lines={3} />
      ) : (
        <>
          <div className={styles.grid}>
            <div>
              <span className={styles.label}>Data as of</span>
              <strong>{d.as_of ? formatDate(d.as_of) : "—"}</strong>
              <Badge tone="info">fixed dataset</Badge>
            </div>
            <div>
              <span className={styles.label}>Patients</span>
              <strong>{formatNumber(d.patients)}</strong>
              <span className={styles.muted}>
                {formatNumber(d.living)} living · {formatNumber(d.deceased)} deceased
              </span>
            </div>
            <div>
              <span className={styles.label}>Cancer types</span>
              <strong>{d.cancer_types.filter((c) => c.label !== "Not yet diagnosed").length}</strong>
              <span className={styles.muted}>{d.cancer_types.slice(0, 3).map((c) => `${c.label} ${formatNumber(c.count)}`).join(" · ")}</span>
            </div>
            <div>
              <span className={styles.label}>Stage mix</span>
              <strong>{d.stages.map((s) => s.label.replace("Stage ", "")).join(" / ")}</strong>
              <span className={styles.muted}>{d.stages.map((s) => formatNumber(s.count)).join(" / ")} patients</span>
            </div>
          </div>
          {repairs.length > 0 && (
            <p className={styles.muted}>
              Repaired on preparation: {repairs.map(([k, v]) => `${formatNumber(v)} ${REPAIR_LABELS[k]}`).join("; ")}.
            </p>
          )}
          {d.known_limitations.length > 0 && (
            <p className={styles.muted}>Known limits of this synthetic data: {d.known_limitations.join(" ")}</p>
          )}
        </>
      )}
    </Panel>
  );
}
