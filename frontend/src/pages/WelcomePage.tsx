import { motion } from "framer-motion";
import { Link } from "react-router-dom";

import { systemApi } from "../api/auth";
import { clinicalApi } from "../api/clinical";
import { commandApi } from "../api/command";
import { executiveApi, labApi, pharmacyApi } from "../api/operations";
import { receptionApi } from "../api/reception";
import { EcgTrace } from "../components/EcgTrace";
import { Icon, type IconName } from "../components/Icons";
import { Reveal, Stagger, TiltCard } from "../components/Motion";
import { NeuralGlobe } from "../components/NeuralGlobe";
import { Skeleton } from "../components/Skeleton";
import { ErrorState } from "../components/StateViews";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { formatNumber, formatPercent } from "../lib/format";
import { CONSOLE_ROUTES, type ConsoleRoute } from "../routes";
import styles from "./WelcomePage.module.css";

const ROLE_ICON: Record<string, IconName> = { admin: "Database", hcp: "Stethoscope", analyst: "Building" };

export function WelcomePage() {
  const { user } = useAuth();
  const overview = useApi((signal) => systemApi.overview(signal), []);

  return (
    <div>
      <section className={styles.hero}>
        <div className={styles.heroText}>
          <span className={styles.badge}>
            <Icon.Sparkle size={14} /> Role-aware clinical intelligence
          </span>
          <motion.h1
            className={styles.title}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          >
            One care network.<br />
            <span>Every decision, informed.</span>
          </motion.h1>
          <p className={styles.lede}>
            From raw clinical records to audited insight, validated prediction and clear next actions for administrators,
            clinicians and operations teams.
          </p>
          <div className={styles.ctaRow}>
            <Link to={user ? (user.default_route === "/" ? user.allowed_routes[0] ?? "/" : user.default_route) : "/login"} className={styles.cta}>
              {user ? "Open my workspace" : "Sign in"} <Icon.Arrow size={16} />
            </Link>
            <span className={styles.ecgWrap}>
              <EcgTrace width={220} height={44} />
            </span>
          </div>
        </div>
        <div className={styles.globe}>
          <NeuralGlobe size={400} />
        </div>
      </section>

      {overview.error && <ErrorState error={overview.error} onRetry={overview.reload} />}

      <section className={styles.flow} aria-label="Pipeline stages">
        {overview.data
          ? overview.data.pipeline_stages.map((stage, i) => (
              <motion.div
                key={stage}
                className={styles.stage}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 + i * 0.07 }}
              >
                <span className={styles.stageNum}>{String(i + 1).padStart(2, "0")}</span>
                <span className={styles.stageName}>{stage}</span>
              </motion.div>
            ))
          : Array.from({ length: 6 }, (_, i) => <Skeleton key={i} height={56} radius={12} />)}
      </section>

      {user ? (
        <WorkspaceTiles routes={CONSOLE_ROUTES.filter((r) => user.allowed_routes.includes(r.path))} roleTitle={user.role_title} />
      ) : (
        <>
          <div className={styles.sectionHead}>
            <h2>Roles & workspaces</h2>
            <p>Three roles, each owning its workspaces. Access is enforced by the API on every request.</p>
          </div>

          {overview.loading || !overview.data ? (
            <div className={styles.personas}>
              {Array.from({ length: 3 }, (_, i) => (
                <Skeleton key={i} height={210} radius={16} />
              ))}
            </div>
          ) : (
            <Stagger className={styles.personas}>
              {overview.data.roles.map((r) => {
                const Glyph = Icon[ROLE_ICON[r.role]];
                return (
                  <Reveal key={r.role}>
                    <Link to="/login" className={styles.personaLink}>
                      <TiltCard className={styles.persona}>
                        <div className={styles.personaTop}>
                          <span className={styles.personaIcon}>
                            <Glyph size={20} />
                          </span>
                          <Icon.Arrow size={16} />
                        </div>
                        <span className={styles.personaName}>{r.title}</span>
                        <span className={styles.personaDesc}>{r.description}</span>
                        <ul className={styles.workspaces}>
                          {r.routes.map((path) => {
                            const route = CONSOLE_ROUTES.find((c) => c.path === path);
                            if (!route) return null;
                            const RouteGlyph = Icon[route.icon];
                            return (
                              <li key={path}>
                                <RouteGlyph size={14} /> {route.label}
                              </li>
                            );
                          })}
                        </ul>
                        <span className={styles.personaRole}>{r.role}</span>
                      </TiltCard>
                    </Link>
                  </Reveal>
                );
              })}
            </Stagger>
          )}
        </>
      )}
    </div>
  );
}

/** The signed-in role's workspaces as large clickable tiles; one click opens the workspace. */
function WorkspaceTiles({ routes, roleTitle }: { routes: ConsoleRoute[]; roleTitle: string }) {
  return (
    <section aria-label="Your workspaces" id="workspaces">
      <div className={styles.sectionHead}>
        <h2>Your workspaces</h2>
        <p>
          {routes.length} workspace{routes.length === 1 ? "" : "s"} for the {roleTitle} role. Select one to open it.
        </p>
      </div>
      <Stagger className={styles.tiles}>
        {routes.map((r) => {
          const Glyph = Icon[r.icon];
          return (
            <Reveal key={r.path}>
              <Link to={r.path} className={styles.tileLink} aria-label={`Open ${r.label}`}>
                <TiltCard className={styles.tile} max={5}>
                  <div className={styles.tileTop}>
                    <span className={styles.tileIcon}>
                      <Glyph size={22} />
                    </span>
                    <span className={styles.tileArrow} aria-hidden="true">
                      <Icon.Arrow size={18} />
                    </span>
                  </div>
                  <h3>{r.label}</h3>
                  <p>{r.description}</p>
                  <div className={styles.tileStat}>
                    <Headline path={r.path} />
                  </div>
                </TiltCard>
              </Link>
            </Reveal>
          );
        })}
      </Stagger>
    </section>
  );
}

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <>
      <strong>{value}</strong>
      <span>{label}</span>
    </>
  );
}

/** One live figure per workspace, loaded independently so a slow endpoint never blocks the page. */
function Headline({ path }: { path: string }) {
  switch (path) {
    case "/doctor":
      return <ClinicalHeadline />;
    case "/executive":
      return <ExecutiveHeadline />;
    case "/command-center":
      return <CommandHeadline />;
    case "/pharmacy":
      return <PharmacyHeadline />;
    case "/laboratory":
      return <LabHeadline />;
    case "/reception":
      return <ReceptionHeadline />;
    case "/data":
      return <PlatformHeadline />;
    default:
      return <Metric value="Audit" label="Access and agent governance" />;
  }
}

function ClinicalHeadline() {
  const k = useApi((s) => clinicalApi.kpis(s), []).data;
  return k ? <Metric value={formatNumber(k.high_risk_recent_discharges)} label="high-risk recent discharges" /> : <Skeleton width="60%" height={20} />;
}

function ExecutiveHeadline() {
  const k = useApi((s) => executiveApi.kpis(s), []).data;
  return k ? <Metric value={formatPercent(k.unplanned_readmission_rate_pct, 2)} label="unplanned 30-day readmissions" /> : <Skeleton width="60%" height={20} />;
}

function CommandHeadline() {
  const h = useApi((s) => commandApi.hospitals(s), []).data;
  return h ? <Metric value={formatNumber(h.filter((x) => x.served_pct < 95).length)} label="hospitals under outpatient access pressure" /> : <Skeleton width="60%" height={20} />;
}

function PharmacyHeadline() {
  const k = useApi((s) => pharmacyApi.kpis(s), []).data;
  return k ? <Metric value={formatNumber(k.high_risk_lines)} label="stock lines at high stock-out risk" /> : <Skeleton width="60%" height={20} />;
}

function LabHeadline() {
  const k = useApi((s) => labApi.kpis(s), []).data;
  return k ? <Metric value={formatNumber(k.tests_last_30d)} label="tests in the last 30 days" /> : <Skeleton width="60%" height={20} />;
}

function ReceptionHeadline() {
  const k = useApi((s) => receptionApi.kpis(s), []).data;
  return k ? <Metric value={formatPercent(k.no_show_rate_pct)} label="appointment no-show rate" /> : <Skeleton width="60%" height={20} />;
}

function PlatformHeadline() {
  const s = useApi((sig) => systemApi.status(sig), []).data;
  return s ? <Metric value={s.gold_ready && s.ml_ready ? "Healthy" : "Attention"} label="lakehouse and model registry" /> : <Skeleton width="60%" height={20} />;
}
