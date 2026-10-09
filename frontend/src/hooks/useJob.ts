import { useEffect, useState } from "react";

import { systemApi } from "../api/auth";
import type { Job } from "../api/schemas/auth";

/** Polls a background job until it succeeds or fails, then calls `onDone` once. */
export function useJob(jobId: string | null | undefined, onDone?: (job: Job) => void, intervalMs = 1000): Job | undefined {
  const [job, setJob] = useState<Job>();

  useEffect(() => {
    setJob(undefined);
    if (!jobId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const j = await systemApi.job(jobId);
        if (stopped) return;
        setJob(j);
        if (j.status === "succeeded" || j.status === "failed") {
          onDone?.(j);
          return;
        }
      } catch {
        if (stopped) return;
        // A restarted API forgets in-memory jobs; let the caller reload state from the server
        onDone?.({ job_id: jobId, kind: "", status: "failed", progress_pct: 0, stage: "Unknown", logs: [], created_at: "", finished_at: null, result: null, error: null });
        return;
      }
      timer = setTimeout(tick, intervalMs);
    };
    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, intervalMs]);

  return job;
}
