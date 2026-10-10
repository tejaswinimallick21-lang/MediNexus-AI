import { request } from "./client";
import { ActionInboxSchema, AgentActionSchema } from "./schemas/actions";

const path = (id: string) => `/actions/${encodeURIComponent(id)}`;

export const actionsApi = {
  inbox: (status?: "pending", s?: AbortSignal) => request("/actions", ActionInboxSchema, { query: { status }, signal: s }),
  approve: (id: string, note?: string) => request(`${path(id)}/approve`, AgentActionSchema, { method: "POST", body: { note: note ?? null } }),
  reject: (id: string, note?: string) => request(`${path(id)}/reject`, AgentActionSchema, { method: "POST", body: { note: note ?? null } }),
};

/** Fired when an agent proposes an action, so the inbox badge refreshes immediately. */
export const ACTIONS_CHANGED = "nexa:actions-changed";
