import { request } from "./client";
import { EmptySchema } from "./schemas/common";
import {
  AccessMatrixSchema,
  AiGovernanceSchema,
  AuditPageSchema,
  AuditSummarySchema,
  BenchmarkSchema,
  InfraHealthSchema,
  KnowledgeLibrarySchema,
  PostureSchema,
  SearchComparisonSchema,
} from "./schemas/security";

export const securityApi = {
  posture: (s?: AbortSignal) => request("/security/posture", PostureSchema, { signal: s }),
  audit: (q: { limit?: number; cursor?: string | null; action?: string; status?: string; user?: string; days?: number }, s?: AbortSignal) =>
    request("/security/audit", AuditPageSchema, { query: q, signal: s }),
  auditSummary: (days: number, s?: AbortSignal) => request("/security/audit/summary", AuditSummarySchema, { query: { days }, signal: s }),
  access: (s?: AbortSignal) => request("/security/access", AccessMatrixSchema, { signal: s }),
  infra: (s?: AbortSignal) => request("/security/infra", InfraHealthSchema, { signal: s }),
  ai: (s?: AbortSignal) => request("/security/ai", AiGovernanceSchema, { signal: s }),
};

export const knowledgeApi = {
  library: (s?: AbortSignal) => request("/knowledge/documents", KnowledgeLibrarySchema, { signal: s }),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request("/knowledge/documents", KnowledgeLibrarySchema, { method: "POST", form });
  },
  remove: (docId: string) => request(`/knowledge/documents/${encodeURIComponent(docId)}`, EmptySchema, { method: "DELETE" }),
  search: (query: string, k = 3) => request("/knowledge/search", SearchComparisonSchema, { method: "POST", body: { query, k } }),
  benchmark: (s?: AbortSignal) => request("/knowledge/benchmark", BenchmarkSchema, { signal: s }),
  runBenchmark: () => request("/knowledge/benchmark", BenchmarkSchema, { method: "POST" }),
};
