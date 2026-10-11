import type { ButtonHTMLAttributes, ReactNode } from "react";

import styles from "./Controls.module.css";

type Variant = "primary" | "secondary" | "ghost";

export function Button({
  variant = "secondary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button type="button" className={`${styles.button} ${styles[variant]} ${className ?? ""}`} {...props} />;
}

interface SelectFieldProps {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  disabled?: boolean;
  id: string;
}

export function SelectField({ label, value, options, onChange, disabled, id }: SelectFieldProps) {
  return (
    <label className={styles.field} htmlFor={id}>
      <span className={styles.label}>{label}</span>
      <select id={id} className={styles.select} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  id: string;
  type?: "text" | "email" | "password";
  placeholder?: string;
  autoComplete?: string;
  maxLength?: number;
  required?: boolean;
}

export function TextField({ label, value, onChange, id, type = "text", placeholder, autoComplete, maxLength, required }: TextFieldProps) {
  return (
    <label className={styles.field} htmlFor={id}>
      <span className={styles.label}>{label}</span>
      <input
        id={id}
        className={styles.select}
        type={type}
        value={value}
        placeholder={placeholder}
        autoComplete={autoComplete}
        maxLength={maxLength}
        required={required}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

export function FieldRow({ children }: { children: ReactNode }) {
  return <div className={styles.row}>{children}</div>;
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "good" | "warn" | "bad" | "info"; children: ReactNode }) {
  return <span className={`${styles.badge} ${styles[`badge_${tone}`]}`}>{children}</span>;
}
