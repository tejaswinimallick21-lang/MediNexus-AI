import { z } from "zod";

const num = z.number();

export const HospitalOptionSchema = z.object({
  hospital_id: z.string(),
  hospital_name: z.string(),
  beds: num,
  physicians: num,
  avg_daily_demand: num,
  served_pct: num,
  avg_wait_days: num,
});
export type HospitalOption = z.infer<typeof HospitalOptionSchema>;
export const HospitalOptionListSchema = z.array(HospitalOptionSchema);

export type WhatIfPeriod = "last_90" | "last_365";
export interface WhatIfInput {
  hospital_id: string | null;
  period: WhatIfPeriod;
  extra_visits_per_physician: number;
  extra_physicians: number;
  demand_change_pct: number;
}

const WhatIfSideSchema = z.object({
  demand: num,
  served: num,
  lost_to_follow_up: num,
  avg_backlog: num,
  avg_wait_days: num,
  utilization_pct: num,
  visits_per_physician_day: num,
  revenue: num,
  staffing_cost: num,
});
export type WhatIfSide = z.infer<typeof WhatIfSideSchema>;

export const WhatIfResultSchema = z.object({
  simulated_data: z.boolean(),
  scope: z.string(),
  period_start: z.string(),
  period_end: z.string(),
  days: num,
  baseline: WhatIfSideSchema,
  scenario: WhatIfSideSchema,
  net_impact: num,
  net_impact_per_month: num,
  insights: z.array(z.string()),
  assumptions: z.array(z.string()),
  daily: z.array(z.object({ date: z.string(), baseline_backlog: num, scenario_backlog: num, baseline_served: num, scenario_served: num })),
});
export type WhatIfResult = z.infer<typeof WhatIfResultSchema>;

export const ModelMonitorRowSchema = z.object({
  model_name: z.string(),
  label: z.string(),
  version: z.string(),
  trained_at: z.string(),
  age_days: num,
  data_source: z.string(),
  primary_metric: z.string(),
  baseline: z.string(),
  verdict: z.string(),
  serving: z.string(),
  health: z.enum(["healthy", "baseline", "low_evidence"]),
  note: z.string(),
  versions: num,
});
export type ModelMonitorRow = z.infer<typeof ModelMonitorRowSchema>;
export const ModelMonitorListSchema = z.array(ModelMonitorRowSchema);
