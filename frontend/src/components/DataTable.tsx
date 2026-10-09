import type { ReactNode } from "react";

import type { ApiError } from "../api/client";
import { Skeleton } from "./Skeleton";
import { EmptyState, ErrorState } from "./StateViews";
import styles from "./DataTable.module.css";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  numeric?: boolean;
  width?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows?: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  error?: ApiError;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyHint?: string;
  skeletonRows?: number;
  caption?: string;
  footer?: ReactNode;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  onRetry,
  emptyTitle = "No records found",
  emptyHint,
  skeletonRows = 6,
  caption,
  footer,
}: DataTableProps<T>) {
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (!loading && rows && rows.length === 0) return <EmptyState title={emptyTitle} hint={emptyHint} />;

  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        {caption && <caption className="visually-hidden">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.numeric ? styles.num : undefined} style={{ width: c.width }} scope="col">
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody aria-busy={loading || undefined}>
          {loading || !rows
            ? Array.from({ length: skeletonRows }, (_, i) => (
                <tr key={`sk-${i}`}>
                  {columns.map((c) => (
                    <td key={c.key}>
                      <Skeleton width={c.numeric ? "50%" : "80%"} />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row) => (
                <tr key={rowKey(row)}>
                  {columns.map((c) => (
                    <td key={c.key} className={c.numeric ? styles.num : undefined}>
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
      {footer && <div className={styles.footer}>{footer}</div>}
    </div>
  );
}
