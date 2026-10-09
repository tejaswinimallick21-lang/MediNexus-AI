import { z } from "zod";

import { pageOf } from "./common";

const num = z.number();
const optNum = z.number().nullable().optional();
const optStr = z.string().nullable().optional();

export const UploadSummarySchema = z.object({
  upload_id: z.string(),
  filename: z.string(),
  size_bytes: num,
  sha256: z.string(),
  uploaded_by: z.string(),
  created_at: z.string(),
  status: z.enum(["processing", "ready", "failed"]),
  stage: z.string(),
  rows: optNum,
  columns: optNum,
  quality_score: optNum,
});
export type UploadSummary = z.infer<typeof UploadSummarySchema>;
export const UploadPageSchema = pageOf(UploadSummarySchema);

const CleaningReportSchema = z.object({
  rows_in: num,
  rows_out: num,
  steps: z.array(z.object({ step: z.string(), detail: z.string(), affected: num, note: optStr })),
  columns: z.array(z.object({ name: z.string(), kind: z.string(), missing_pct: num, unique: num, pii_masked: z.boolean(), example: optStr })),
  quality: z.object({ completeness: num, validity: num, uniqueness: num, consistency: num, overall: num }),
});
export type CleaningReport = z.infer<typeof CleaningReportSchema>;

const ProfileSchema = z.object({
  rows: num,
  columns: num,
  numeric: z.array(
    z.object({
      column: z.string(),
      mean: num,
      std: num,
      min: num,
      p25: num,
      median: num,
      p75: num,
      max: num,
      missing_pct: num,
      extreme_outliers: num,
      histogram: z.array(z.object({ bin: z.string(), count: num })),
    }),
  ),
  categories: z.array(z.object({ column: z.string(), distinct: num, top: z.array(z.object({ value: z.string(), count: num, share_pct: num })) })),
  correlations: z.array(z.object({ a: z.string(), b: z.string(), rho: num })),
  date_coverage: z.object({ column: z.string(), start: z.string(), end: z.string() }).nullable().optional(),
  segments: z.object({
    available: z.boolean(),
    reason: optStr,
    rows_used: optNum,
    k: optNum,
    silhouette: optNum,
    structure: optStr,
    clusters: z.array(z.object({ cluster: num, size: num, share_pct: num, traits: z.array(z.string()) })),
    anomaly_share_pct: optNum,
    anomalies: optNum,
  }),
  drift: z.object({
    available: z.boolean(),
    reason: optStr,
    reference_table: optStr,
    columns: z.array(z.object({ column: z.string(), upload_median: num, lakehouse_median: num, psi: num, shift: z.string() })),
  }),
});
export type Profile = z.infer<typeof ProfileSchema>;

export const PredictionSchema = z.object({
  target: z.string(),
  task: z.enum(["classification", "regression"]),
  rows_used: num,
  train_rows: num,
  test_rows: num,
  split: z.string(),
  features_used: z.array(z.string()),
  excluded: z.array(z.object({ column: z.string(), reason: z.string() })),
  primary_metric: z.string(),
  score: num,
  baseline_score: num,
  baseline_label: z.string(),
  beats_baseline: z.boolean(),
  verdict: z.string(),
  drivers: z.array(z.object({ feature: z.string(), importance: num })),
  classes: optNum,
  accuracy: optNum,
  baseline_accuracy: optNum,
  macro_f1: optNum,
  roc_auc: optNum,
  positive_class: optStr,
  mae: optNum,
  baseline_mae: optNum,
  r2: optNum,
});
export type Prediction = z.infer<typeof PredictionSchema>;

const PointSchema = z.object({ date: z.string(), value: num });
export const ForecastSchema = z.object({
  date_column: z.string(),
  value_column: optStr,
  aggregation: z.string(),
  frequency: z.enum(["daily", "weekly"]),
  horizon: num,
  history_points: num,
  backtest_folds: num,
  model_mae: num,
  baseline_mae: num,
  baseline_label: z.string(),
  serving_method: z.enum(["model", "baseline"]),
  skill_pct: num,
  history: z.array(PointSchema),
  forecast: z.array(PointSchema),
  next_total: num,
  last_total: num,
});
export type Forecast = z.infer<typeof ForecastSchema>;

export const UploadDetailSchema = UploadSummarySchema.extend({
  error: optStr,
  job_id: optStr,
  cleaning: CleaningReportSchema.nullable().optional(),
  profile: ProfileSchema.nullable().optional(),
  predictions: z.array(PredictionSchema),
  forecast: ForecastSchema.nullable().optional(),
  summary: z.array(z.string()),
  preview_columns: z.array(z.string()),
  preview_rows: z.array(z.array(z.string().nullable())),
});
export type UploadDetail = z.infer<typeof UploadDetailSchema>;

export const UploadAcceptedSchema = z.object({ upload: UploadSummarySchema, job_id: z.string() });
export const JobAcceptedSchema = z.object({ job_id: z.string() });
