import { AnimatePresence, motion } from "framer-motion";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { systemApi } from "../api/auth";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { CONSOLE_ROUTES } from "../routes";
import { Skeleton } from "./Skeleton";
import styles from "./AppShell.module.css";

const ROLE_LABEL = { admin: "Admin", hcp: "Healthcare Professional", analyst: "Analyst" } as const;

export function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const status = useApi((signal) => systemApi.status(signal), []);

  const routes = CONSOLE_ROUTES.filter((r) => user?.allowed_routes.includes(r.path));

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.logo} aria-hidden="true">🏥</span>
          <div>
            <div className={styles.brandName}>MediNexus AI</div>
            <div className={styles.brandTag}>HEALTHCARE DECISION PLATFORM</div>
          </div>
        </div>

        {user ? (
          <>
            <div className={styles.card}>
              <div className={styles.cardLabel}>Active role</div>
              <div className={styles.cardTitle}>{user.persona}</div>
              <div className={styles.cardMeta}>{ROLE_LABEL[user.role]} · {user.department}</div>
            </div>
            <div className={styles.sectionLabel}>Authorized consoles</div>
            <nav className={styles.nav} aria-label="Consoles">
              {routes.map((r) => (
                <NavLink key={r.path} to={r.path} className={({ isActive }) => `${styles.navLink} ${isActive ? styles.active : ""}`}>
                  <span aria-hidden="true">{r.icon}</span> {r.label}
                </NavLink>
              ))}
              <NavLink to="/" end className={({ isActive }) => `${styles.navLink} ${isActive ? styles.active : ""}`}>
                <span aria-hidden="true">🏠</span> Platform Overview
              </NavLink>
            </nav>
            <button
              type="button"
              className={styles.signOut}
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
            >
              🚪 Sign out
            </button>
          </>
        ) : (
          <div className={styles.card}>
            <div className={styles.cardLabel}>Guest session</div>
            <div className={styles.cardMeta}>Sign in to open your role console.</div>
            <NavLink to="/login" className={`${styles.navLink} ${styles.active} ${styles.signIn}`}>
              🔑 Sign in
            </NavLink>
          </div>
        )}

        <div className={styles.status} aria-live="polite">
          <div className={styles.cardLabel}>Platform readiness</div>
          {status.data ? (
            <>
              <div>Lakehouse Gold: <b className={status.data.gold_ready ? styles.ok : styles.bad}>{status.data.gold_ready ? "Ready ✓" : "Uninitialized"}</b></div>
              <div>ML Registry: <b className={status.data.ml_ready ? styles.ok : styles.bad}>{status.data.ml_ready ? "Active ✓" : "Untrained"}</b></div>
              <div>AI Engine: <b className={styles.info}>{status.data.llm_provider}</b></div>
              <div className={styles.version}>Version {status.data.version}</div>
            </>
          ) : status.error ? (
            <div className={styles.bad}>API unreachable</div>
          ) : (
            <Skeleton height={48} />
          )}
        </div>
      </aside>

      <main className={styles.main}>
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className={styles.content}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
