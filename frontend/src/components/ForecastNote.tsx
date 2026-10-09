import type { ForecastMeta } from "../api/schemas/operations";
import { formatNumber } from "../lib/format";
import { Badge } from "./Controls";

/** States which forecasting method is being served and how it scored on held-out data. */
export function ForecastNote({ meta }: { meta: ForecastMeta }) {
  const baselineServed = meta.serving_method !== "model";
  return (
    <p style={{ margin: "12px 0 0", fontSize: 12, color: "var(--color-text-muted)", display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
      <Badge tone={baselineServed ? "warn" : "good"}>{meta.method_label}</Badge>
      {meta.holdout_mae != null && meta.holdout_baseline_mae != null && (
        <span>
          Held-out error ({meta.test_period}): model {formatNumber(meta.holdout_mae, 2)} vs baseline {formatNumber(meta.holdout_baseline_mae, 2)}.
          {baselineServed && " The baseline was more accurate, so it is served."}
        </span>
      )}
    </p>
  );
}
