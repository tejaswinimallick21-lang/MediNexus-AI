import { AnimatePresence, motion } from "framer-motion";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { systemApi } from "../api/auth";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { CONSOLE_ROUTES } from "../routes";
import { ApprovalInbox } from "./ApprovalInbox";
import { AssistantDock } from "./AssistantDock";
import { Icon } from "./Icons";
import styles from "./AppShell.module.css";

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
            <nav className={styles.nav} aria-label="Consoles">
              <NavLink to="/" end className={({ isActive }) => `${styles.navLink} ${isActive ? styles.active : ""}`}>
                {({ isActive }) => (
                  <>
                    {isActive && <motion.span layoutId="nav-active" className={styles.activeBg} transition={{ type: "spring", stiffness: 400, damping: 34 }} />}
                    <Icon.Home size={18} />
                    <span>Platform Overview</span>
                  </>
                )}
              </NavLink>
              <div className={styles.sectionLabel}>Workspaces</div>
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
            </nav>
          </>
        ) : (
          <NavLink to="/login" className={styles.signInCta}>
            <Icon.Key size={18} /> Sign in to your workspace
          </NavLink>
        )}

      </aside>

      <div className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.crumbs}>
            {location.pathname !== "/" && (
              <button
                type="button"
                className={styles.backButton}
                onClick={() => {
                  // Step back within the app when there is history; otherwise return to the overview
                  const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
                  if (idx > 0) navigate(-1);
                  else navigate("/");
                }}
                aria-label="Go back"
                title="Back"
              >
                <Icon.Arrow size={16} style={{ transform: "rotate(180deg)" }} />
                <span>Back</span>
              </button>
            )}
            {location.pathname === "/" ? (
              <strong>Platform Overview</strong>
            ) : (
              <>
                <NavLink to="/" className={styles.crumbLink}>
                  Platform Overview
                </NavLink>
                <Icon.Arrow size={14} />
                <strong>{current?.label ?? "Page"}</strong>
              </>
            )}
          </div>
          <div className={styles.topRight}>
            {(() => {
              // One status pill replaces the old sidebar health card; details on hover, and admins can open the full overview
              const label = healthy ? "All systems operational" : status.data ? "Pipeline attention needed" : status.error ? "API unreachable" : "Connecting";
              const detail = status.data
                ? `Lakehouse Gold: ${status.data.gold_ready ? "ready" : "missing"} · Model registry: ${status.data.ml_ready ? "ready" : "missing"} · ${status.data.llm_provider} · v${status.data.version}`
                : label;
              const cls = `${styles.pill} ${healthy ? styles.pillOk : styles.pillWarn}`;
              const body = (
                <>
                  <span className={styles.pulse} />
                  {label}
                </>
              );
              return user?.allowed_routes.includes("/it") ? (
                <NavLink to="/it" className={`${cls} ${styles.pillLink}`} title={`${detail} — open Security & Infrastructure`} aria-live="polite">
                  {body}
                </NavLink>
              ) : (
                <span className={cls} title={detail} aria-live="polite">
                  {body}
                </span>
              );
            })()}
            {user && !user.must_change_password && <ApprovalInbox />}
            {user && (
              <div className={styles.userChip}>
                <span className={styles.avatar}>{initials(user.name)}</span>
                <NavLink to="/account" className={styles.userText} title="Your account and password">
                  <strong>{user.name}</strong>
                  <span>{user.role_title}</span>
                </NavLink>
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
      {user && <AssistantDock />}
    </div>
  );
}
