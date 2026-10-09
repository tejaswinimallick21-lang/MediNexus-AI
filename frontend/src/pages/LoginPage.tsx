import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { Button } from "../components/Controls";
import { useAuth } from "../hooks/useAuth";
import styles from "./LoginPage.module.css";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to={from && user.allowed_routes.includes(from) ? from : user.default_route} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(undefined);
    try {
      const u = await login(email, password);
      navigate(from && u.allowed_routes.includes(from) ? from : u.default_route, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Sign-in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <form className={styles.card} onSubmit={onSubmit} noValidate>
        <h1 className={styles.title}>MediNexus Access Portal</h1>
        <p className={styles.subtitle}>Sign in with your work email. Your role decides which consoles you can open.</p>

        <label className={styles.field}>
          <span>Email</span>
          <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className={styles.field}>
          <span>Password</span>
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>

        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}

        <Button type="submit" variant="primary" disabled={submitting || !email || !password}>
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
        <p className={styles.help}>Accounts come from the seeded user file (see README › Authentication).</p>
      </form>
    </div>
  );
}
