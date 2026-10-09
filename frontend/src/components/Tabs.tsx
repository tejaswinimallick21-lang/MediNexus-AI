import { motion } from "framer-motion";
import { useId } from "react";

import styles from "./Tabs.module.css";

/** Accessible tab bar with an animated active indicator. */
export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string }[]; value: T; onChange: (id: T) => void }) {
  const layoutId = useId();
  return (
    <div className={styles.bar} role="tablist">
      {tabs.map((t) => (
        <button key={t.id} type="button" role="tab" aria-selected={t.id === value} className={styles.tab} onClick={() => onChange(t.id)}>
          {t.label}
          {t.id === value && <motion.span layoutId={layoutId} className={styles.indicator} transition={{ type: "spring", stiffness: 420, damping: 36 }} />}
        </button>
      ))}
    </div>
  );
}
