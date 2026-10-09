import { API_BASE, request } from "./client";
import { EmptySchema } from "./schemas/common";
import { JobAcceptedSchema, LinkDiscoverySchema, UploadAcceptedSchema, UploadDetailSchema, UploadPageSchema, type Relationship } from "./schemas/dataPlatform";

const path = (id: string) => `/data/uploads/${encodeURIComponent(id)}`;

export const dataApi = {
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request("/data/uploads", UploadAcceptedSchema, { method: "POST", form });
  },
  uploads: (q: { limit?: number; cursor?: string | null } = {}, s?: AbortSignal) => request("/data/uploads", UploadPageSchema, { query: q, signal: s }),
  detail: (id: string, s?: AbortSignal) => request(path(id), UploadDetailSchema, { signal: s }),
  remove: (id: string) => request(path(id), EmptySchema, { method: "DELETE" }),
  predict: (id: string, target: string, exclude: string[] = []) => request(`${path(id)}/predict`, JobAcceptedSchema, { method: "POST", body: { target, exclude } }),
  discoverLinks: (uploadIds: string[]) => request("/data/links/discover", LinkDiscoverySchema, { method: "POST", body: { upload_ids: uploadIds } }),
  consolidate: (uploadIds: string[], baseTable: string, relationships: Relationship[]) =>
    request("/data/links/consolidate", UploadAcceptedSchema, { method: "POST", body: { upload_ids: uploadIds, base_table: baseTable, relationships } }),
  reportUrl: (id: string) => `${API_BASE}${path(id)}/report.html`,
  forecast: (id: string, body: { date_column: string; value_column: string | null; aggregation: "sum" | "mean" }) =>
    request(`${path(id)}/forecast`, JobAcceptedSchema, { method: "POST", body }),
  /** Same-origin link; the session cookie authorises the download. */
  cleanCsvUrl: (id: string) => `${API_BASE}${path(id)}/clean.csv`,
};
