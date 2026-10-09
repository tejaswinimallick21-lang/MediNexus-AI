import { motion } from "framer-motion";
import { Link } from "react-router-dom";

import { systemApi } from "../api/auth";
import { EcgTrace } from "../components/EcgTrace";
import { Icon } from "../components/Icons";
import { Reveal, Stagger, TiltCard } from "../components/Motion";
import { NeuralGlobe } from "../components/NeuralGlobe";
import { Skeleton } from "../components/Skeleton";
import { ErrorState } from "../components/StateViews";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { CONSOLE_ROUTES } from "../routes";
import styles from "./WelcomePage.module.css";

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
            {overview.data?.tagline ?? "Role-Based Healthcare Data-to-Decision Intelligence Platform"}: from raw records to audited
            insight, validated prediction and clear next actions for every role.
          </p>
          <div className={styles.ctaRow}>
            {user ? (
              <Link to={user.default_route} className={styles.cta}>
                Open my workspace <Icon.Arrow size={16} />
              </Link>
            ) : (
              <Link to="/login" className={styles.cta}>
                Sign in <Icon.Arrow size={16} />
              </Link>
            )}
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

      <div className={styles.sectionHead}>
        <h2>Workspaces</h2>
        <p>Each role sees only the data it needs; access is enforced on every request.</p>
      </div>

      {overview.loading || !overview.data ? (
        <div className={styles.personas}>
          {Array.from({ length: 7 }, (_, i) => (
            <Skeleton key={i} height={150} radius={16} />
          ))}
        </div>
      ) : (
        <Stagger className={styles.personas}>
          {overview.data.personas.map((p) => {
            const allowed = user?.allowed_routes.includes(p.route);
            const Glyph = Icon[CONSOLE_ROUTES.find((r) => r.path === p.route)?.icon ?? "Logo"];
            return (
              <Reveal key={p.persona}>
                <Link
                  to={user ? (allowed ? p.route : "/") : "/login"}
                  className={`${styles.personaLink} ${user && !allowed ? styles.locked : ""}`}
                  aria-disabled={user ? !allowed : undefined}
                >
                  <TiltCard className={styles.persona}>
                    <div className={styles.personaTop}>
                      <span className={styles.personaIcon}>
                        <Glyph size={20} />
                      </span>
                      {user && !allowed ? <Icon.Lock size={16} /> : <Icon.Arrow size={16} />}
                    </div>
                    <span className={styles.personaName}>{p.persona}</span>
                    <span className={styles.personaDesc}>{p.description}</span>
                    <span className={styles.personaRole}>{p.role}</span>
                  </TiltCard>
                </Link>
              </Reveal>
            );
          })}
        </Stagger>
      )}
    </div>
  );
}
