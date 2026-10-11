import { request } from "./client";
import { EmptySchema } from "./schemas/common";
import { JobSchema, PlatformOverviewSchema, SystemStatusSchema, UserSchema } from "./schemas/auth";

export const authApi = {
  login: (email: string, password: string) => request("/auth/login", UserSchema, { method: "POST", body: { email, password } }),
  logout: () => request("/auth/logout", EmptySchema, { method: "POST" }),
  me: (signal?: AbortSignal) => request("/auth/me", UserSchema, { signal }),
  changePassword: (current_password: string, new_password: string) =>
    request("/auth/password", UserSchema, { method: "POST", body: { current_password, new_password } }),
};

export const systemApi = {
  status: (signal?: AbortSignal) => request("/system/status", SystemStatusSchema, { signal }),
  overview: (signal?: AbortSignal) => request("/platform/overview", PlatformOverviewSchema, { signal }),
  job: (jobId: string, signal?: AbortSignal) => request(`/jobs/${encodeURIComponent(jobId)}`, JobSchema, { signal }),
};
