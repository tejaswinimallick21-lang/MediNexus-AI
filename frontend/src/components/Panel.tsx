import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icons";
import { Reveal } from "./Motion";
import styles from "./Panel.module.css";

interface PanelProps {
  title?: string;
  subtitle?: string;
  icon?: IconName;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Panel({ title, subtitle, icon, actions, children, className }: PanelProps) {
  const Glyph = icon ? Icon[icon] : null;
  return (
    <Reveal className={`${styles.panel} ${className ?? ""}`}>
      {(title || actions) && (
        <header className={styles.header}>
          <div className={styles.headingRow}>
            {Glyph && (
              <span className={styles.icon}>
                <Glyph size={18} />
              </span>
            )}
            <div>
              {title && <h3 className={styles.title}>{title}</h3>}
              {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
            </div>
          </div>
          {actions && <div className={styles.actions}>{actions}</div>}
        </header>
      )}
      {children}
    </Reveal>
  );
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  badge,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  badge?: string;
}) {
  return (
    <header className={styles.pageHeader}>
      <div>
        {eyebrow && <span className={styles.eyebrow}>{eyebrow}</span>}
        <h1 className={styles.pageTitle}>{title}</h1>
        {subtitle && <p className={styles.pageSubtitle}>{subtitle}</p>}
      </div>
      {badge && (
        <span className={styles.pageBadge}>
          <Icon.Lock size={14} /> {badge}
        </span>
      )}
    </header>
  );
}

export function Notice({ tone = "neutral", children }: { tone?: "neutral" | "info"; children: ReactNode }) {
  return (
    <div className={`${styles.notice} ${tone === "info" ? styles.noticeInfo : ""}`}>
      <Icon.Shield size={18} />
      <div>{children}</div>
    </div>
  );
}

export function Grid({ columns = 2, children }: { columns?: 2 | 3; children: ReactNode }) {
  return <div className={columns === 3 ? styles.grid3 : styles.grid2}>{children}</div>;
}
