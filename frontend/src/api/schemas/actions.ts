import { z } from "zod";

export const AgentActionSchema = z.object({
  action_id: z.string(),
  kind: z.string(),
  kind_label: z.string(),
  summary: z.string(),
  reason: z.string(),
  payload: z.record(z.unknown()),
  agent: z.string(),
  session_id: z.string().nullable().optional(),
  requested_by: z.string(),
  status: z.enum(["pending", "rejected", "executed", "failed"]),
  created_at: z.string(),
  decided_by: z.string().nullable().optional(),
  decided_at: z.string().nullable().optional(),
  decision_note: z.string().nullable().optional(),
  result: z.string().nullable().optional(),
  can_decide: z.boolean(),
});
export type AgentAction = z.infer<typeof AgentActionSchema>;

export const ActionInboxSchema = z.object({ pending: z.number(), items: z.array(AgentActionSchema) });
export type ActionInbox = z.infer<typeof ActionInboxSchema>;

export const SweepStatusSchema = z.object({
  schedule: z.string(),
  next_run_at: z.string(),
  running_job_id: z.string().nullable().optional(),
  runs: z.array(
    z.object({
      run_id: z.string(),
      trigger: z.string(),
      started_at: z.string(),
      finished_at: z.string().nullable().optional(),
      status: z.string(),
      found: z.number(),
      proposed: z.number(),
      ai_used: z.boolean(),
      by_kind: z.record(z.number()),
      error: z.string().nullable().optional(),
      suppressed: z.number().optional(),
    }),
  ),
});
export type SweepStatus = z.infer<typeof SweepStatusSchema>;
