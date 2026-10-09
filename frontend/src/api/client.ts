import type { ZodType } from "zod";

/** Base URL from VITE_API_BASE (defaults to the Vite dev proxy at /api). */
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

/** Mirrors the backend error shape: { detail, code }. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

type Query = Record<string, string | number | null | undefined>;

export function buildQuery(params?: Query): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
}

/** Fetch JSON and validate it against a schema; throws ApiError for non-2xx responses. */
export async function request<T>(path: string, schema: ZodType<T>, opts: RequestOptions = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}${buildQuery(opts.query)}`, {
      method: opts.method ?? "GET",
      credentials: "include",
      headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "Cannot reach the MediNexus API. Is the backend running?");
  }

  const text = await response.text();
  const payload: unknown = text ? safeJson(text) : undefined;

  if (!response.ok) {
    const body = (payload ?? {}) as { detail?: unknown; code?: unknown };
    throw new ApiError(
      response.status,
      typeof body.code === "string" ? body.code : "http_error",
      typeof body.detail === "string" ? body.detail : response.statusText || "Request failed",
    );
  }
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError(response.status, "invalid_response", `Unexpected response from ${path}: ${parsed.error.issues[0]?.message}`);
  }
  return parsed.data;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}
