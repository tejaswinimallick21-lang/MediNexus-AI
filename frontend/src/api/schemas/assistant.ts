import { z } from "zod";

import { pageOf } from "./common";
import { AgentReplySchema } from "./operations";

export const AssistantAgentSchema = z.object({
  key: z.enum(["medicare", "pharmalab", "healthanalyst", "ops"]),
  name: z.string(),
  tagline: z.string(),
  prompts: z.array(z.string()),
  routes: z.array(z.string()),
});
export type AssistantAgent = z.infer<typeof AssistantAgentSchema>;
export const AssistantAgentListSchema = z.array(AssistantAgentSchema);

export const AssistantSessionSchema = z.object({
  session_id: z.string(),
  agent: z.string(),
  title: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  message_count: z.number(),
});
export type AssistantSession = z.infer<typeof AssistantSessionSchema>;
export const AssistantSessionPageSchema = pageOf(AssistantSessionSchema);

export const AssistantMessageSchema = z.object({
  message_id: z.string(),
  role: z.enum(["user", "assistant"]),
  text: z.string().nullable().optional(),
  reply: AgentReplySchema.nullable().optional(),
  created_at: z.string(),
});
export type AssistantMessage = z.infer<typeof AssistantMessageSchema>;
export const AssistantMessageListSchema = z.array(AssistantMessageSchema);

export const AssistantExchangeSchema = z.object({
  session: AssistantSessionSchema,
  messages: z.array(AssistantMessageSchema),
});

/** Long-term memory: what the signed-in user asked Nexa to remember. */
export const MemoryItemSchema = z.object({
  memory_id: z.string(),
  text: z.string(),
  source: z.enum(["chat", "panel"]),
  created_at: z.string(),
});
export type MemoryItem = z.infer<typeof MemoryItemSchema>;
export const MemoryListSchema = z.array(MemoryItemSchema);
