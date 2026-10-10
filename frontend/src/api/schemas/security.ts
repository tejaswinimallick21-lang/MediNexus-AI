import { z } from "zod";

import { pageOf } from "./common";

const num = z.number();
const CountRow = z.object({ label: z.string(), count: num });

export const PostureSchema = z.object({
  score: num,
  passed: num,
  warnings: num,
  failures: num,
  environment: z.string(),
  checks: z.array(
    z.object({ id: z.string(), area: z.string(), title: z.string(), status: z.enum(["pass", "warn", "fail"]), detail: z.string(), fix: z.string().nullable().optional() }),
  ),
});
export type Posture = z.infer<typeof PostureSchema>;

export const AuditEventSchema = z.object({
  log_id: z.string(),
  timestamp: z.string(),
  username: z.string(),
  role: z.string(),
  action: z.string(),
  resource: z.string(),
  status: z.string(),
  details: z.string(),
});
export type AuditEvent = z.infer<typeof AuditEventSchema>;
export const AuditPageSchema = pageOf(AuditEventSchema);

export const AuditSummarySchema = z.object({
  window_days: num,
  total_events: num,
  failed_logins: num,
  access_denied: num,
  lockouts: num,
  patient_record_views: num,
  by_action: z.array(CountRow),
  by_day: z.array(z.object({ day: z.string(), events: num, failed_logins: num, denied: num })),
  failed_login_accounts: z.array(CountRow),
  denied_resources: z.array(CountRow),
  locked_now: z.record(num),
  actions: z.array(z.string()),
});
export type AuditSummary = z.infer<typeof AuditSummarySchema>;

export const AccessMatrixSchema = z.object({
  roles: z.array(z.object({ role: z.string(), title: z.string() })),
  workspaces: z.array(z.object({ page: z.string(), route: z.string(), label: z.string(), roles: z.array(z.string()) })),
  agents: z.array(z.object({ agent: z.string(), name: z.string(), roles: z.array(z.string()), tools: z.array(z.string()) })),
  approvals: z.array(z.object({ kind: z.string(), label: z.string(), requires_page: z.string(), roles: z.array(z.string()) })),
});
export type AccessMatrix = z.infer<typeof AccessMatrixSchema>;

export const InfraHealthSchema = z.object({
  api_version: z.string(),
  environment: z.string(),
  python: z.string(),
  platform: z.string(),
  uptime_minutes: num,
  database_path: z.string(),
  database_size_mb: num,
  tables: z.array(z.object({ name: z.string(), layer: z.string(), rows: num })),
  layer_rows: z.record(num),
  storage: z.array(z.object({ label: z.string(), path: z.string(), size_mb: num, files: num })),
  active_models: num,
  models_last_trained: z.string().nullable().optional(),
  active_jobs: z.array(z.string()),
  sweep_next_run: z.string(),
  sweep_last_status: z.string().nullable().optional(),
  llm_provider: z.string(),
  embeddings: z.string(),
  knowledge_documents: num,
  knowledge_chunks: num,
});
export type InfraHealth = z.infer<typeof InfraHealthSchema>;

export const AiGovernanceSchema = z.object({
  provider: z.string(),
  caps: z.record(z.unknown()),
  embeddings: z.string(),
  window_days: num,
  usage: z.array(z.object({ agent: z.string(), queries: num, fallbacks: num, avg_latency_ms: num, tool_calls: num })),
  top_tools: z.array(CountRow),
  proposals: z.array(z.object({ kind: z.string(), label: z.string(), status: z.string(), count: num })),
  approval_rate_pct: num.nullable().optional(),
  sweep_runs: z.array(z.record(z.unknown())),
  guardrails: z.array(z.string()),
});
export type AiGovernance = z.infer<typeof AiGovernanceSchema>;

export const KnowledgeLibrarySchema = z.object({
  documents: z.array(
    z.object({
      doc_id: z.string(),
      title: z.string(),
      policy_id: z.string(),
      category: z.string(),
      filename: z.string(),
      source: z.enum(["library", "uploaded"]),
      sections: num,
      words: num,
    }),
  ),
  chunks: num,
  dense_model: z.string(),
  dense_error: z.string().nullable().optional(),
});
export type KnowledgeLibrary = z.infer<typeof KnowledgeLibrarySchema>;

const SearchHitSchema = z.object({
  title: z.string(),
  policy_id: z.string(),
  section: z.string(),
  filename: z.string(),
  source: z.string(),
  text: z.string(),
  score: num,
  bm25: num,
  dense: num,
  bm25_rank: num.nullable().optional(),
  dense_rank: num.nullable().optional(),
});
export type SearchHit = z.infer<typeof SearchHitSchema>;
export const SearchComparisonSchema = z.object({
  query: z.string(),
  identifier_query: z.boolean(),
  dense_model: z.string(),
  results: z.record(z.array(SearchHitSchema)),
});
export type SearchComparison = z.infer<typeof SearchComparisonSchema>;

const SuiteSchema = z.object({
  questions: num,
  hit1_pct: num.optional(),
  hit3_pct: num.optional(),
  mrr: num.optional(),
  false_refusal_pct: num.optional(),
  abstained_pct: num.optional(),
});
export const BenchmarkSchema = z.object({
  run_at: z.string(),
  dense_model: z.string(),
  dense_error: z.string().nullable().optional(),
  documents: num,
  chunks: num,
  questions: num,
  modes: z.array(z.object({ mode: z.string(), summary: z.record(SuiteSchema), avg_latency_ms: num, rows: z.array(z.record(z.unknown())) })),
});
export type Benchmark = z.infer<typeof BenchmarkSchema>;
