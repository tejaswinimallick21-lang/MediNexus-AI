import { z } from "zod";

import { pageOf } from "./common";

const num = z.number();
const nullableNum = z.number().nullable();

export const ForecastMetaSchema = z.object({
  serving_method: z.string(),
  method_label: z.string(),
  holdout_mae: nullableNum.optional(),
  holdout_baseline_mae: nullableNum.optional(),
  holdout_surge_mae: nullableNum.optional(),
  holdout_served_mae: nullableNum.optional(),
  beats_baseline: z.boolean().nullable().optional(),
  test_period: z.string().nullable().optional(),
  data_through: z.string().nullable().optional(),
});
export type ForecastMeta = z.infer<typeof ForecastMetaSchema>;

export const TrendPointSchema = z.object({ period: z.string(), value: num, secondary: nullableNum.optional() });
export type TrendPoint = z.infer<typeof TrendPointSchema>;
export const TrendListSchema = z.array(TrendPointSchema);

// ---- Laboratory ----
export const LabKpisSchema = z.object({
  total_tests: num,
  abnormal_tests: num,
  critical_tests: num,
  abnormal_pct: num,
  critical_pct: num,
  tests_last_30d: num,
});
export const CategoryWorkloadListSchema = z.array(z.object({ category: z.string(), total: num, abnormal: num, critical: num }));
export const CriticalAlertSchema = z.object({
  lab_id: z.string(),
  patient_id: z.string(),
  test_name: z.string(),
  test_value: nullableNum,
  unit: z.string().nullable(),
  reference_range: z.string().nullable(),
  test_date: z.string(),
  department_name: z.string().nullable(),
});
export type CriticalAlert = z.infer<typeof CriticalAlertSchema>;
export const CriticalAlertPageSchema = pageOf(CriticalAlertSchema);
export const LabCapacityPlanSchema = z.object({
  category: z.string(),
  forecast_daily_tests: num,
  last_7d_daily: num,
  estimated_capacity_daily: num,
  utilization_pct: num,
  critical_rate_pct: num,
  operational_status: z.string(),
  actions: z.array(z.string()),
  assessment: z.string(),
  forecast: ForecastMetaSchema,
});
export type LabCapacityPlan = z.infer<typeof LabCapacityPlanSchema>;

// ---- Pharmacy ----
export const PharmacyKpisSchema = z.object({
  stock_lines: num,
  high_risk_lines: num,
  moderate_risk_lines: num,
  dispensed_units_180d: num,
  active_prescriptions: num,
});
export const StockLineSchema = z.object({
  inventory_id: z.string(),
  medication_id: z.string(),
  medication_name: z.string().nullable(),
  category: z.string().nullable(),
  hospital_id: z.string().nullable(),
  hospital_name: z.string().nullable(),
  stock_quantity: num,
  reorder_level: num,
  days_of_supply: nullableNum,
  stockout_risk: z.string(),
});
export type StockLine = z.infer<typeof StockLineSchema>;
export const StockPageSchema = pageOf(StockLineSchema);
export const DemandForecastSchema = z.object({
  inventory_id: z.string(),
  medication_name: z.string(),
  hospital_name: z.string().nullable(),
  current_stock: num,
  dispensed_last_30d: num,
  predicted_30d_demand: num,
  projected_shortfall: num,
  urgency: z.string(),
  recommended_order_quantity: num,
  estimated_procurement_cost: num,
  actions: z.array(z.string()),
  buffer_assessment: z.string(),
  forecast: ForecastMetaSchema,
});
export type DemandForecast = z.infer<typeof DemandForecastSchema>;
export const ClassOutlookSchema = z.object({
  simulated_data: z.boolean(),
  as_of: z.string(),
  items: z.array(z.object({ drug_class: z.string(), forecast_daily_units: num, last_7d_daily_units: num, change_pct: num })),
  forecast: ForecastMetaSchema,
});
export const PurchaseOrderSchema = z.object({
  po_id: z.string(),
  inventory_id: z.string(),
  medication_name: z.string(),
  quantity: num,
  estimated_cost: num,
  status: z.string(),
  created_at: z.string(),
});

// ---- Executive ----
export const ExecutiveKpisSchema = z.object({
  total_admissions: num,
  patients_admitted: num,
  unplanned_readmission_rate_pct: num,
  average_los_days: num,
  occupancy_rate_pct: nullableNum,
  total_revenue: num,
  collection_rate_pct: num,
  hospitals: num,
  data_through: z.string(),
});
export const RevenueListSchema = z.array(z.object({ department: z.string(), revenue: num, admissions: num }));
export const ModelScoreSchema = z.object({
  model: z.string(),
  purpose: z.string(),
  primary_metric: z.string(),
  baseline: z.string(),
  verdict: z.string(),
});
export type ModelScore = z.infer<typeof ModelScoreSchema>;
export const ExecutiveForecastsSchema = z.object({
  admissions_next_7d_daily: num,
  admissions_last_7d_daily: num,
  admissions_forecast: ForecastMetaSchema,
  models: z.array(ModelScoreSchema),
});
const BreakdownRow = z.object({ label: z.string(), count: num, rate_pct: num });
export const ReadmissionDriversSchema = z.object({
  summary: z.string(),
  findings: z.array(z.string()),
  by_admission_type: z.array(BreakdownRow),
  by_reason: z.array(BreakdownRow),
});
export const CapacityPlanSchema = z.object({
  surge_tier: z.string(),
  occupancy_pct: nullableNum,
  projected_daily_admissions: num,
  average_los_days: num,
  directives: z.array(z.string()),
  assessment: z.string(),
  occupancy_note: z.string(),
});

// ---- Copilots ----
export const AgentReplySchema = z.object({
  agent: z.string(),
  answer: z.string().nullable().optional(),
  facts: z.array(z.string()),
  predictions: z.array(z.string()),
  recommendations: z.array(z.string()),
  evidence: z.array(z.string()),
  notes: z.string(),
  latency_ms: num,
  // Added with the tool-using agents; absent on replies stored before then
  engine: z.string().optional(),
  tool_calls: z.array(z.object({ name: z.string(), args: z.record(z.unknown()).optional(), ok: z.boolean(), error: z.string().nullable().optional() })).optional(),
  proposed_actions: z.array(z.object({ action_id: z.string(), summary: z.string(), status: z.string() })).optional(),
});
export type AgentReply = z.infer<typeof AgentReplySchema>;
