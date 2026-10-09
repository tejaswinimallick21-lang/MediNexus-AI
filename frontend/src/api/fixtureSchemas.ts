import type { ZodTypeAny } from "zod";

import { PlatformOverviewSchema, SystemStatusSchema, UserSchema } from "./schemas/auth";
import {
  AppointmentPageSchema,
  ReceptionFiltersSchema,
  ReceptionKpisSchema,
  StatusDistributionSchema,
  WaitInsightsSchema,
} from "./schemas/reception";
import {
  AgentReplySchema,
  CapacityPlanSchema,
  CategoryWorkloadListSchema,
  CriticalAlertPageSchema,
  DemandForecastSchema,
  ExecutiveForecastsSchema,
  ExecutiveKpisSchema,
  LabCapacityPlanSchema,
  LabKpisSchema,
  PharmacyKpisSchema,
  PurchaseOrderSchema,
  ReadmissionDriversSchema,
  RevenueListSchema,
  StockPageSchema,
  TrendListSchema,
} from "./schemas/operations";

/**
 * Golden fixture name (written by the backend pytest contract tests into __fixtures__/)
 * → the zod schema the frontend uses for that endpoint. Each page migration registers its endpoints here.
 */
export const fixtureSchemas: Record<string, ZodTypeAny> = {
  auth_me: UserSchema,
  system_status: SystemStatusSchema,
  platform_overview: PlatformOverviewSchema,
  reception_kpis: ReceptionKpisSchema,
  reception_status_distribution: StatusDistributionSchema,
  reception_wait_insights: WaitInsightsSchema,
  reception_filters: ReceptionFiltersSchema,
  reception_appointments: AppointmentPageSchema,
  lab_kpis: LabKpisSchema,
  lab_workload: CategoryWorkloadListSchema,
  lab_daily_volume: TrendListSchema,
  lab_critical_alerts: CriticalAlertPageSchema,
  lab_capacity_plan: LabCapacityPlanSchema,
  pharmacy_kpis: PharmacyKpisSchema,
  pharmacy_stock: StockPageSchema,
  pharmacy_forecast: DemandForecastSchema,
  pharmacy_purchase_order: PurchaseOrderSchema,
  executive_kpis: ExecutiveKpisSchema,
  executive_admissions_trend: TrendListSchema,
  executive_revenue: RevenueListSchema,
  executive_forecasts: ExecutiveForecastsSchema,
  executive_readmission_drivers: ReadmissionDriversSchema,
  executive_capacity_plan: CapacityPlanSchema,
  agent_reply: AgentReplySchema,
};
