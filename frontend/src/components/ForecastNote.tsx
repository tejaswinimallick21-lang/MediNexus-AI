import type { ForecastMeta } from "../api/schemas/operations";
import { formatNumber } from "../lib/format";
import { Badge } from "./Controls";

/** States which forecasting method is being served and how the candidates scored on held-out data. */
export function ForecastNote({ meta }: { meta: ForecastMeta }) {
  const baselineServed = meta.serving_method.startsWith("baseline");
  const tried = [
    meta.holdout_mae != null && `model ${formatNumber(meta.holdout_mae, 2)}`,
    meta.holdout_surge_mae != null && `surge-aware average ${formatNumber(meta.holdout_surge_mae, 2)}`,
    meta.holdout_baseline_mae != null && `naive baseline ${formatNumber(meta.holdout_baseline_mae, 2)}`,
  ].filter(Boolean);
  return (
    <p style={{ margin: "12px 0 0", fontSize: 12, color: "var(--color-text-muted)", display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
      <Badge tone={baselineServed ? "warn" : "good"}>{meta.method_label}</Badge>
      {tried.length > 1 && (
        <span>
          Backtest error ({meta.test_period}): {tried.join(" · ")}. The most accurate method is served.
        </span>
      )}
    </p>
  );
}
