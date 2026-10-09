import { z } from "zod";

import { LabelCountSchema, pageOf } from "./common";

export const ReceptionKpisSchema = z.object({
  total_appointments: z.number().int(),
  completed: z.number().int(),
  no_shows: z.number().int(),
  cancelled: z.number().int(),
  no_show_rate_pct: z.number(),
  cancellation_rate_pct: z.number(),
  avg_wait_minutes: z.number(),
});
export type ReceptionKpis = z.infer<typeof ReceptionKpisSchema>;

export const StatusDistributionSchema = z.object({ items: z.array(LabelCountSchema) });

export const WaitInsightsSchema = z.object({
  summary: z.string(),
  findings: z.array(z.string()),
  by_hour: z.array(z.object({ hour: z.string(), volume: z.number().int(), avg_wait_min: z.number() })),
  wait_times_simulated: z.boolean(),
  target_wait_minutes: z.number().int(),
});
export type WaitInsights = z.infer<typeof WaitInsightsSchema>;

export const ReceptionFiltersSchema = z.object({
  statuses: z.array(z.string()),
  departments: z.array(z.string()),
  visit_types: z.array(z.string()),
});

export const AppointmentRowSchema = z.object({
  appointment_id: z.string(),
  patient_id: z.string(),
  appointment_date: z.string(),
  appointment_time: z.string().nullable(),
  doctor_name: z.string().nullable(),
  department_name: z.string().nullable(),
  visit_type: z.string().nullable(),
  status: z.string(),
  waiting_time_minutes: z.number().int().nullable(),
});
export type AppointmentRow = z.infer<typeof AppointmentRowSchema>;

export const AppointmentPageSchema = pageOf(AppointmentRowSchema);
