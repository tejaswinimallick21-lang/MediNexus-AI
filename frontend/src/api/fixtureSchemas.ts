import type { ZodTypeAny } from "zod";

import { PlatformOverviewSchema, SystemStatusSchema, UserSchema } from "./schemas/auth";
import {
  AppointmentPageSchema,
  ReceptionFiltersSchema,
  ReceptionKpisSchema,
  StatusDistributionSchema,
  WaitInsightsSchema,
} from "./schemas/reception";

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
};
