import { motion } from "framer-motion";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { DnaHelix } from "../components/DnaHelix";
import { EcgTrace } from "../components/EcgTrace";
import { Icon } from "../components/Icons";
import { useAuth } from "../hooks/useAuth";
import styles from "./LoginPage.module.css";

const CAPABILITIES = [
  { title: "Data Intelligence", text: "Medallion lakehouse with audited data quality", icon: "Database" },
  { title: "Predictive Analytics", text: "Validated risk, stay and demand models", icon: "Pulse" },
  { title: "Healthcare Analytics", text: "Role-aware clinical and operational consoles", icon: "Stethoscope" },
  { title: "Generative AI", text: "Grounded copilots with cited evidence", icon: "Sparkle" },
] as const;

// Demo environment only: seeded local accounts by auth role (stripped from production builds via import.meta.env.DEV)
const DEMO_ROLES: { role: string; title: string; email: string; scope: string }[] = import.meta.env.DEV
  ? [
      { role: "admin", title: "Admin", email: "admin@medinexus.org", scope: "Data Engineering, Security" },
      { role: "hcp", title: "HCP", email: "hcp@medinexus.org", scope: "Clinical, Pharmacy, Laboratory" },
      { role: "analyst", title: "Analyst", email: "analyst@medinexus.org", scope: "Executive, Patient Access" },
    ]
  : [];
const DEMO_PASSWORD = import.meta.env.DEV ? "MediNexus@2026" : "";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    <div className={styles.page}>
      <section className={styles.brandPanel}>
        <div className={styles.helix}>
          <DnaHelix width={380} height={620} />
        </div>
        <div className={styles.brandInner}>
          <div className={styles.logoRow}>
            <span className={styles.logo}>M</span>
            <div>
              <div className={styles.logoName}>MediNexus AI</div>
              <div className={styles.logoTag}>Healthcare Intelligence</div>
            </div>
          </div>

          <motion.h1
            className={styles.headline}
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          >
            Transform Healthcare Data Into <span>Actionable Intelligence</span>
          </motion.h1>
          <motion.p className={styles.lede} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.25, duration: 0.6 }}>
            Unify clinical data, population analytics, predictive insights and AI-powered decision support in one enterprise platform.
          </motion.p>

          <div className={styles.capabilities}>
            {CAPABILITIES.map((c, i) => {
              const Glyph = Icon[c.icon];
              return (
                <motion.div
                  key={c.title}
                  className={styles.capability}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.35 + i * 0.08, duration: 0.5 }}
                >
                  <Glyph size={18} />
                  <div>
                    <strong>{c.title}</strong>
                    <span>{c.text}</span>
                  </div>
                </motion.div>
              );
            })}
          </div>

          <div className={styles.ecg}>
            <EcgTrace width={440} height={70} />
            <span className={styles.ecgLabel}>
              <span className={styles.liveDot} /> Live clinical signal
            </span>
          </div>
        </div>
      </section>

      <section className={styles.formPanel}>
        <motion.form
          className={styles.card}
          onSubmit={onSubmit}
          noValidate
          initial={{ opacity: 0, y: 20, rotateX: 8 }}
          animate={{ opacity: 1, y: 0, rotateX: 0 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        >
          <h2 className={styles.welcome}>Welcome back</h2>
          <p className={styles.sub}>Sign in to MediNexus AI</p>

          {DEMO_ROLES.length > 0 && (
            <label className={styles.field}>
              <span>
                Demo role <em className={styles.demoTag}>Demo environment</em>
              </span>
              <select
                className={styles.roleSelect}
                value={DEMO_ROLES.some((r) => r.email === email) ? email : ""}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setPassword(e.target.value ? DEMO_PASSWORD : "");
                  setError(undefined);
                }}
              >
                <option value="">Choose a role to fill in credentials…</option>
                {DEMO_ROLES.map((r) => (
                  <option key={r.role} value={r.email}>
                    {r.title} — {r.scope}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className={styles.field}>
            <span>Work Email</span>
            <input
              type="email"
              autoComplete="username"
              placeholder="name@medinexus.org"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label className={styles.field}>
            <span>Password</span>
            <div className={styles.passwordWrap}>
              <input
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button type="button" className={styles.reveal} onClick={() => setShowPassword((s) => !s)}>
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </label>

          {error && (
            <p className={styles.error} role="alert">
              <Icon.Alert size={16} /> {error}
            </p>
          )}

          <button type="submit" className={styles.submit} disabled={submitting || !email || !password}>
            {submitting ? "Signing in…" : "Sign In"}
          </button>

          <div className={styles.footer}>
            <span>
              <Icon.Lock size={13} /> {import.meta.env.DEV ? "Demo environment" : "Secured session"}
            </span>
            <span>Forgot password? Contact your administrator</span>
          </div>

        </motion.form>
      </section>
    </div>
  );
}
