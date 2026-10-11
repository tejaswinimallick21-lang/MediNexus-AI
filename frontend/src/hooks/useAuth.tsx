import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { authApi } from "../api/auth";
import { ApiError } from "../api/client";
import type { User } from "../api/schemas/auth";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  /** Replace the signed-in user (e.g. after a password change). */
  refresh: (user: User) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    const controller = new AbortController();
    authApi
      .me(controller.signal)
      .then((u) => {
        setUser(u);
        setStatus("authenticated");
      })
      .catch((err) => {
        if ((err as Error)?.name === "AbortError") return;
        // 401 just means "not signed in"; any other failure also lands on the sign-in page.
        setUser(null);
        setStatus("anonymous");
        if (!(err instanceof ApiError) || err.status !== 401) console.warn("Session check failed", err);
      });
    return () => controller.abort();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const u = await authApi.login(email, password);
    setUser(u);
    setStatus("authenticated");
    return u;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  const refresh = useCallback((u: User) => setUser(u), []);

  const value = useMemo(() => ({ status, user, login, logout, refresh }), [status, user, login, logout, refresh]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
