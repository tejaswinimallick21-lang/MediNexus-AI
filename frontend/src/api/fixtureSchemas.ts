import type { ZodTypeAny } from "zod";

import { PlatformOverviewSchema, SystemStatusSchema, UserSchema } from "./schemas/auth";

/**
 * Golden fixture name (written by the backend pytest contract tests into __fixtures__/)
 * → the zod schema the frontend uses for that endpoint. Each page migration registers its endpoints here.
 */
export const fixtureSchemas: Record<string, ZodTypeAny> = {
  auth_me: UserSchema,
  system_status: SystemStatusSchema,
  platform_overview: PlatformOverviewSchema,
};
