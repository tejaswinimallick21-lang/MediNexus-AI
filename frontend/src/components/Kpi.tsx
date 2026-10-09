import type { ReactNode } from "react";

import type { ApiError } from "../api/client";
import { Icon, type IconName } from "./Icons";
import { CountUp, Reveal, Stagger, TiltCard } from "./Motion";
import { Skeleton } from "./Skeleton";
import { ErrorState } from "./StateViews";
import styles from "./Kpi.module.css";

export interface KpiItem {
  label: string;
  value: number;
  format: (n: number) => string;
  hint?: string;
  tone?: "neutral" | "good" | "warn" | "bad";
  icon?: IconName;
}

export function KpiCard({ label, value, format, hint, tone = "neutral", icon }: KpiItem) {
  const Glyph = icon ? Icon[icon] : null;
  return (
    <TiltCard className={styles.card} max={6}>
      <div className={styles.top}>
        <span className={styles.label}>{label}</span>
        {Glyph && (
          <span className={`${styles.icon} ${styles[`icon_${tone}`]}`}>
            <Glyph size={18} />
          </span>
        )}
      </div>
      <span className={styles.value}>
        <CountUp value={value} format={format} />
      </span>
      {hint && <span className={`${styles.hint} ${styles[tone]}`}>{hint}</span>}
      <span className={`${styles.bar} ${styles[`bar_${tone}`]}`} aria-hidden="true" />
    </TiltCard>
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
            <Skeleton width="45%" height={32} />
            <Skeleton width="35%" height={10} />
          </div>
        ))}
      </div>
    );
  }
  return (
    <Stagger className={styles.grid}>
      {items.map((item) => (
        <Reveal key={item.label}>
          <KpiCard {...item} />
        </Reveal>
      ))}
    </Stagger>
  );
}
