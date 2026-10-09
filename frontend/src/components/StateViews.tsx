import type { ApiError } from "../api/client";
import styles from "./StateViews.module.css";

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const hint =
    error.code === "data_unavailable"
      ? "The Gold layer isn't built yet. A Data Engineer can run the Medallion pipeline."
      : error.code === "network_error"
        ? "Start the backend with `npm run backend`."
        : undefined;
  return (
    <div className={styles.error} role="alert">
      <div>
        <p className={styles.title}>Couldn't load this section</p>
        <p className={styles.detail}>{error.detail}</p>
        {hint && <p className={styles.hint}>{hint}</p>}
      </div>
      {onRetry && (
        <button type="button" className={styles.retry} onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className={styles.empty}>
      <p className={styles.title}>{title}</p>
      {hint && <p className={styles.detail}>{hint}</p>}
    </div>
  );
}
