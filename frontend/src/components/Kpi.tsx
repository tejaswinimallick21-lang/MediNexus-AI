import type { ReactNode } from "react";

import type { ApiError } from "../api/client";
import { Skeleton } from "./Skeleton";
import { ErrorState } from "./StateViews";
import styles from "./Kpi.module.css";

export interface KpiItem {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "good" | "warn" | "bad";
}

export function KpiCard({ label, value, hint, tone = "neutral" }: KpiItem) {
  return (
    <div className={styles.card}>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>{value}</span>
      {hint && <span className={`${styles.hint} ${styles[tone]}`}>{hint}</span>}
    </div>
  );
}

/** KPI row with its own loading (skeleton) and error state. */
export function KpiGrid({
  items,
  loading,
  error,
  onRetry,
  count = 4,
}: {
  items?: KpiItem[];
  loading?: boolean;
  error?: ApiError;
  onRetry?: () => void;
  count?: number;
}): ReactNode {
  if (error) return <div className={styles.wrap}><ErrorState error={error} onRetry={onRetry} /></div>;
  if (loading || !items) {
    return (
      <div className={styles.grid} aria-busy="true">
        {Array.from({ length: count }, (_, i) => (
          <div key={i} className={styles.card}>
            <Skeleton width="55%" height={12} />
            <Skeleton width="40%" height={28} />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className={styles.grid}>
      {items.map((item) => (
        <KpiCard key={item.label} {...item} />
      ))}
    </div>
  );
}
