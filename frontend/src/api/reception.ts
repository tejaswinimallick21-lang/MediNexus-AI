import { request } from "./client";
import {
  AppointmentPageSchema,
  ReceptionFiltersSchema,
  ReceptionKpisSchema,
  StatusDistributionSchema,
  WaitInsightsSchema,
} from "./schemas/reception";

export interface AppointmentQuery {
  status?: string;
  department?: string;
  visit_type?: string;
  limit?: number;
  cursor?: string | null;
}

export const receptionApi = {
  kpis: (signal?: AbortSignal) => request("/reception/kpis", ReceptionKpisSchema, { signal }),
  statusDistribution: (signal?: AbortSignal) => request("/reception/status-distribution", StatusDistributionSchema, { signal }),
  waitInsights: (signal?: AbortSignal) => request("/reception/wait-insights", WaitInsightsSchema, { signal }),
  filters: (signal?: AbortSignal) => request("/reception/filters", ReceptionFiltersSchema, { signal }),
  appointments: (q: AppointmentQuery, signal?: AbortSignal) =>
    request("/reception/appointments", AppointmentPageSchema, { query: { ...q }, signal }),
};
