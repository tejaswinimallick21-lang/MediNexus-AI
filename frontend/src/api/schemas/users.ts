import { z } from "zod";

/** People management (Security & Infrastructure → People). */
export const UserAdminRowSchema = z.object({
  email: z.string(),
  name: z.string(),
  role: z.enum(["admin", "hcp", "analyst"]),
  role_title: z.string(),
  department: z.string(),
  active: z.boolean(),
  must_change_password: z.boolean(),
  created_at: z.string().nullable().optional(),
  created_by: z.string(),
  last_login_at: z.string().nullable().optional(),
  is_you: z.boolean(),
});
export type UserAdminRow = z.infer<typeof UserAdminRowSchema>;

export const UserDirectorySchema = z.object({
  users: z.array(UserAdminRowSchema),
  active_count: z.number(),
  admin_count: z.number(),
});
export type UserDirectory = z.infer<typeof UserDirectorySchema>;

export const TemporaryPasswordSchema = z.object({
  user: UserAdminRowSchema,
  temporary_password: z.string(),
});
export type TemporaryPassword = z.infer<typeof TemporaryPasswordSchema>;
