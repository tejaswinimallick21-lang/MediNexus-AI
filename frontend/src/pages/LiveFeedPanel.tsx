import { useState } from "react";

import { ApiError } from "../api/client";
import { dataApi } from "../api/dataPlatform";
import { Badge, Button } from "../components/Controls";
import { Panel } from "../components/Panel";
import { SkeletonText } from "../components/Skeleton";
import { useApi } from "../hooks/useApi";
import { useJob } from "../hooks/useJob";
import { formatDate } from "../lib/format";
import styles from "./LiveFeedPanel.module.css";

const when = (iso?: string | null) => (iso ? `${formatDate(iso)} ${iso.slice(11, 16)}` : "—");

/** The live lakehouse feed: Synthea re-dated to today and released day by day. */
export function LiveFeedPanel() {
  const feed = useApi((s) => dataApi.feed(s), []);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string>();
  const job = useJob(jobId, (j) => {
    if (j.status === "failed") setError(j.error ?? "The refresh failed.");
    setJobId(null);
    feed.reload();
  }, 2000);

  async function refresh() {
    setError(undefined);
    try {
      setJobId((await dataApi.refreshFeed()).job_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not start the refresh.");
    }
  }

  const f = feed.data;
  const last = f?.runs[0];
  return (
    <Panel
      title="Live data feed"
      subtitle="Synthea records re-dated to today (records before 2020, so no COVID-19 period) and released day by day"
      icon="Pulse"
      actions={
        <Button variant="primary" disabled={!!jobId} onClick={() => void refresh()}>
          {jobId ? `Refreshing… ${job?.progress_pct ?? 0}%` : "Refresh now"}
        </Button>
      }
    >
      {!f ? (
        <SkeletonText lines={3} />
      ) : (
        <div className={styles.grid}>
          <div>
            <span className={styles.label}>Released through</span>
            <strong>{when(f.released_through)}</strong>
          </div>
          <div>
            <span className={styles.label}>Held back for the coming days</span>
            <strong>{f.held_back_days ?? "—"} days</strong>
            <span className={styles.muted}>until {f.redated_end ? formatDate(f.redated_end) : "—"}</span>
          </div>
          <div>
            <span className={styles.label}>Last refresh</span>
            <strong>{when(last?.finished_at ?? last?.started_at)}</strong>
            {last && <Badge tone={last.status === "succeeded" ? "good" : last.status === "failed" ? "bad" : "info"}>{last.status}</Badge>}
          </div>
          <div>
            <span className={styles.label}>Next automatic refresh</span>
            <strong>{f.enabled ? when(f.next_run_at) : "Disabled"}</strong>
          </div>
        </div>
      )}
      {jobId && job && <p className={styles.muted}>{job.stage}</p>}
      {error && <p className={styles.error}>{error}</p>}
      <p className={styles.muted}>
        Every date was moved forward by {f?.shift_days ? `${Math.round(f.shift_days / 7)} weeks` : "a whole number of weeks"} so weekdays and ages stay consistent. Each night the next
        day's records are released and Bronze → Silver → Gold is rebuilt; models are retrained separately.
      </p>
    </Panel>
  );
}
