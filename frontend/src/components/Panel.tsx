import type { ReactNode } from "react";

import styles from "./Panel.module.css";

interface PanelProps {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Panel({ title, subtitle, actions, children, className }: PanelProps) {
  return (
    <section className={`${styles.panel} ${className ?? ""}`}>
      {(title || actions) && (
        <header className={styles.header}>
          <div>
            {title && <h3 className={styles.title}>{title}</h3>}
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
          {actions && <div className={styles.actions}>{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, badge }: { title: string; subtitle?: string; badge?: string }) {
  return (
    <header className={styles.pageHeader}>
      <div>
        <h1 className={styles.pageTitle}>{title}</h1>
        {subtitle && <p className={styles.pageSubtitle}>{subtitle}</p>}
      </div>
      {badge && <span className={styles.pageBadge}>{badge}</span>}
    </header>
  );
}

export function Notice({ tone = "neutral", children }: { tone?: "neutral" | "info"; children: ReactNode }) {
  return <div className={`${styles.notice} ${tone === "info" ? styles.noticeInfo : ""}`}>{children}</div>;
}

export function Grid({ columns = 2, children }: { columns?: 2 | 3; children: ReactNode }) {
  return <div className={columns === 3 ? styles.grid3 : styles.grid2}>{children}</div>;
}
