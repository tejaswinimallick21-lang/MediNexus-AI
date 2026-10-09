import { AnimatePresence, motion } from "framer-motion";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { systemApi } from "../api/auth";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { CONSOLE_ROUTES } from "../routes";
import { Icon } from "./Icons";
import styles from "./AppShell.module.css";

const ROLE_LABEL = { admin: "Administrator", hcp: "Healthcare Professional", analyst: "Analyst" } as const;

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const status = useApi((signal) => systemApi.status(signal), []);

  // Full-bleed pages (sign-in) render without the console chrome
  if (location.pathname === "/login") {
    return (
      <AnimatePresence mode="wait">
        <motion.div key="login" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <Outlet />
        </motion.div>
      </AnimatePresence>
    );
  }

  const routes = CONSOLE_ROUTES.filter((r) => user?.allowed_routes.includes(r.path));
  const current = CONSOLE_ROUTES.find((r) => location.pathname.startsWith(r.path));
  const healthy = status.data?.gold_ready && status.data?.ml_ready;

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.logo}>
            <Icon.Logo size={22} />
          </span>
          <div>
            <div className={styles.brandName}>MediNexus<span>AI</span></div>
            <div className={styles.brandTag}>Clinical Intelligence Cloud</div>
          </div>
        </div>

        {user ? (
          <>
            <div className={styles.sectionLabel}>Workspaces</div>
            <nav className={styles.nav} aria-label="Consoles">
              {routes.map((r) => {
                const Glyph = Icon[r.icon];
                return (
                  <NavLink key={r.path} to={r.path} className={({ isActive }) => `${styles.navLink} ${isActive ? styles.active : ""}`}>
                    {({ isActive }) => (
                      <>
                        {isActive && <motion.span layoutId="nav-active" className={styles.activeBg} transition={{ type: "spring", stiffness: 400, damping: 34 }} />}
                        <Glyph size={18} />
                        <span>{r.label}</span>
                      </>
                    )}
                  </NavLink>
                );
              })}
              <NavLink to="/" end className={({ isActive }) => `${styles.navLink} ${isActive ? styles.active : ""}`}>
                {({ isActive }) => (
                  <>
                    {isActive && <motion.span layoutId="nav-active" className={styles.activeBg} transition={{ type: "spring", stiffness: 400, damping: 34 }} />}
                    <Icon.Home size={18} />
                    <span>Platform Overview</span>
                  </>
                )}
              </NavLink>
            </nav>
          </>
        ) : (
          <NavLink to="/login" className={styles.signInCta}>
            <Icon.Key size={18} /> Sign in to your workspace
          </NavLink>
        )}

        <div className={styles.statusCard} aria-live="polite">
          <div className={styles.sectionLabel}>Platform health</div>
          {status.data ? (
            <ul className={styles.statusList}>
              <li><span className={status.data.gold_ready ? styles.dotOk : styles.dotBad} />Lakehouse Gold</li>
              <li><span className={status.data.ml_ready ? styles.dotOk : styles.dotBad} />Model registry</li>
              <li><span className={styles.dotInfo} />{status.data.llm_provider}</li>
            </ul>
          ) : (
            <span className={styles.muted}>{status.error ? "API unreachable" : "Checking…"}</span>
          )}
          <span className={styles.version}>v{status.data?.version ?? "—"}</span>
        </div>
      </aside>

      <div className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.crumbs}>
            <span>MediNexus</span>
            <Icon.Arrow size={14} />
            <strong>{current?.label ?? "Platform Overview"}</strong>
          </div>
          <div className={styles.topRight}>
            <span className={`${styles.pill} ${healthy ? styles.pillOk : styles.pillWarn}`}>
              <span className={styles.pulse} />
              {healthy ? "All systems operational" : status.data ? "Pipeline attention needed" : "Connecting"}
            </span>
            {user && (
              <div className={styles.userChip}>
                <span className={styles.avatar}>{initials(user.name)}</span>
                <span className={styles.userText}>
                  <strong>{user.persona}</strong>
                  <span>{ROLE_LABEL[user.role]}</span>
                </span>
                <button
                  type="button"
                  className={styles.iconButton}
                  aria-label="Sign out"
                  title="Sign out"
                  onClick={async () => {
                    await logout();
                    navigate("/login");
                  }}
                >
                  <Icon.Logout size={18} />
                </button>
              </div>
            )}
          </div>
        </header>

        <main className={styles.content}>
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
