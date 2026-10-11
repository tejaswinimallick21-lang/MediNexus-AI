import { request } from "./client";
import { TemporaryPasswordSchema, UserAdminRowSchema, UserDirectorySchema } from "./schemas/users";

const path = (email: string) => `/users/${encodeURIComponent(email)}`;

export type NewUser = {
  email: string;
  name: string;
  role: "admin" | "hcp" | "analyst";
  department: string;
};
export type UserChanges = Partial<{
  name: string;
  role: "admin" | "hcp" | "analyst";
  department: string;
  active: boolean;
}>;

export const usersApi = {
  list: (s?: AbortSignal) => request("/users", UserDirectorySchema, { signal: s }),
  create: (body: NewUser) => request("/users", TemporaryPasswordSchema, { method: "POST", body }),
  update: (email: string, body: UserChanges) => request(path(email), UserAdminRowSchema, { method: "PATCH", body }),
  resetPassword: (email: string) =>
    request(`${path(email)}/reset-password`, TemporaryPasswordSchema, {
      method: "POST",
    }),
};
