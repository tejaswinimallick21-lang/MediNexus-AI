import { z } from "zod";

export const UserSchema = z.object({
  email: z.string(),
  name: z.string(),
  role: z.enum(["admin", "hcp", "analyst"]),
  persona: z.string(),
  department: z.string(),
  allowed_routes: z.array(z.string()),
  default_route: z.string(),
});
export type User = z.infer<typeof UserSchema>;

export const SystemStatusSchema = z.object({
  gold_ready: z.boolean(),
  ml_ready: z.boolean(),
  llm_provider: z.string(),
  version: z.string(),
});
export type SystemStatus = z.infer<typeof SystemStatusSchema>;

export const PlatformOverviewSchema = z.object({
  app_name: z.string(),
  tagline: z.string(),
  version: z.string(),
  pipeline_stages: z.array(z.string()),
  personas: z.array(
    z.object({ persona: z.string(), role: z.string(), title: z.string(), description: z.string(), route: z.string() }),
  ),
});
export type PlatformOverview = z.infer<typeof PlatformOverviewSchema>;

export const JobSchema = z.object({
  job_id: z.string(),
  kind: z.string(),
  status: z.enum(["queued", "running", "succeeded", "failed"]),
  progress_pct: z.number(),
  stage: z.string(),
  logs: z.array(z.string()),
  created_at: z.string(),
  finished_at: z.string().nullable(),
  result: z.record(z.unknown()).nullable(),
  error: z.string().nullable(),
});
export type Job = z.infer<typeof JobSchema>;
