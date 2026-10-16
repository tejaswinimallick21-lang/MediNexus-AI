import { z } from "zod";

import { request } from "./client";
import {
  AgentReplySchema,
  CategoryWorkloadListSchema,
  ClassOutlookSchema,
  CostByTypeListSchema,
  CriticalAlertPageSchema,
  DemandForecastSchema,
  ExecutiveForecastsSchema,
  ExecutiveKpisSchema,
  LabCapacityPlanSchema,
  LabKpisSchema,
  PharmacyKpisSchema,
  PurchaseOrderSchema,
  StageMixListSchema,
  StockPageSchema,
  SurvivalOverviewSchema,
  TrendListSchema,
} from "./schemas/operations";

const enc = encodeURIComponent;

export const labApi = {
  kpis: (s?: AbortSignal) => request("/lab/kpis", LabKpisSchema, { signal: s }),
  workload: (s?: AbortSignal) => request("/lab/workload-by-category", CategoryWorkloadListSchema, { signal: s }),
  dailyVolume: (days: number, s?: AbortSignal) => request("/lab/daily-volume", TrendListSchema, { query: { days }, signal: s }),
  categories: (s?: AbortSignal) => request("/lab/categories", z.array(z.string()), { signal: s }),
  criticalAlerts: (q: { limit?: number; cursor?: string | null; category?: string }, s?: AbortSignal) =>
    request("/lab/critical-alerts", CriticalAlertPageSchema, { query: q, signal: s }),
  capacityPlan: (category: string, s?: AbortSignal) => request(`/lab/categories/${enc(category)}/capacity-plan`, LabCapacityPlanSchema, { signal: s }),
};

export const pharmacyApi = {
  kpis: (s?: AbortSignal) => request("/pharmacy/kpis", PharmacyKpisSchema, { signal: s }),
  stock: (q: { limit?: number; cursor?: string | null; risk?: string; search?: string }, s?: AbortSignal) =>
    request("/pharmacy/stock", StockPageSchema, { query: q, signal: s }),
  riskByCategory: (s?: AbortSignal) =>
    request("/pharmacy/risk-by-category", z.array(z.object({ category: z.string(), high: z.number(), moderate: z.number(), safe: z.number() })), { signal: s }),
  classOutlook: (s?: AbortSignal) => request("/pharmacy/class-outlook", ClassOutlookSchema, { signal: s }),
  forecast: (inventoryId: string, s?: AbortSignal) => request(`/pharmacy/stock/${enc(inventoryId)}/forecast`, DemandForecastSchema, { signal: s }),
  purchaseOrder: (inventory_id: string, quantity: number) =>
    request("/pharmacy/purchase-orders", PurchaseOrderSchema, { method: "POST", body: { inventory_id, quantity } }),
};

export const executiveApi = {
  kpis: (s?: AbortSignal) => request("/executive/kpis", ExecutiveKpisSchema, { signal: s }),
  diagnosesTrend: (months: number, s?: AbortSignal) => request("/executive/diagnoses-trend", TrendListSchema, { query: { months }, signal: s }),
  survival: (s?: AbortSignal) => request("/executive/survival", SurvivalOverviewSchema, { signal: s }),
  stageMix: (s?: AbortSignal) => request("/executive/stage-mix", StageMixListSchema, { signal: s }),
  costByType: (s?: AbortSignal) => request("/executive/cost-by-type", CostByTypeListSchema, { signal: s }),
  forecasts: (s?: AbortSignal) => request("/executive/forecasts", ExecutiveForecastsSchema, { signal: s }),
};

export type AgentKey = "medicare" | "pharmalab" | "healthanalyst" | "ops";
export const agentApi = {
  chat: (agent: AgentKey, message: string) => request(`/agents/${agent}/chat`, AgentReplySchema, { method: "POST", body: { message } }),
};
