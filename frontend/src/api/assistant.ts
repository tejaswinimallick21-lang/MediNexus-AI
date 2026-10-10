import { request } from "./client";
import { EmptySchema } from "./schemas/common";
import {
  AssistantAgentListSchema,
  AssistantExchangeSchema,
  AssistantMessageListSchema,
  AssistantSessionPageSchema,
  AssistantSessionSchema,
  MemoryItemSchema,
  MemoryListSchema,
} from "./schemas/assistant";

const path = (id: string) => `/assistant/sessions/${encodeURIComponent(id)}`;

export const assistantApi = {
  agents: (s?: AbortSignal) =>
    request("/assistant/agents", AssistantAgentListSchema, { signal: s }),
  sessions: (
    q: { limit?: number; cursor?: string | null } = {},
    s?: AbortSignal,
  ) =>
    request("/assistant/sessions", AssistantSessionPageSchema, {
      query: q,
      signal: s,
    }),
  create: (agent: string) =>
    request("/assistant/sessions", AssistantSessionSchema, {
      method: "POST",
      body: { agent },
    }),
  rename: (id: string, title: string) =>
    request(path(id), AssistantSessionSchema, {
      method: "PATCH",
      body: { title },
    }),
  remove: (id: string) => request(path(id), EmptySchema, { method: "DELETE" }),
  messages: (id: string, s?: AbortSignal) =>
    request(`${path(id)}/messages`, AssistantMessageListSchema, { signal: s }),
  send: (id: string, message: string) =>
    request(`${path(id)}/messages`, AssistantExchangeSchema, {
      method: "POST",
      body: { message },
    }),
  memory: (s?: AbortSignal) =>
    request("/assistant/memory", MemoryListSchema, { signal: s }),
  remember: (text: string) =>
    request("/assistant/memory", MemoryItemSchema, {
      method: "POST",
      body: { text },
    }),
  forget: (id: string) =>
    request(`/assistant/memory/${encodeURIComponent(id)}`, EmptySchema, {
      method: "DELETE",
    }),
  forgetAll: () =>
    request("/assistant/memory", EmptySchema, { method: "DELETE" }),
};
