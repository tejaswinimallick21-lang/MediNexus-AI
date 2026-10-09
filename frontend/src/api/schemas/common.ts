import { z } from "zod";

export const ErrorSchema = z.object({ detail: z.string(), code: z.string() });

export const LabelCountSchema = z.object({ label: z.string(), count: z.number().int() });
export type LabelCount = z.infer<typeof LabelCountSchema>;

/** Generic cursor page: { items, next_cursor }. */
export const pageOf = <T extends z.ZodTypeAny>(item: T) =>
  z.object({ items: z.array(item), next_cursor: z.string().nullable() });

export type Page<T> = { items: T[]; next_cursor: string | null };

export const EmptySchema = z.undefined();
