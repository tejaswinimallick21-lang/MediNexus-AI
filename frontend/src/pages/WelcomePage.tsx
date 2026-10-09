import { Link } from "react-router-dom";

import { systemApi } from "../api/auth";
import { Skeleton } from "../components/Skeleton";
import { ErrorState } from "../components/StateViews";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import styles from "./WelcomePage.module.css";

export function WelcomePage() {
  const { user } = useAuth();
  const overview = useApi((signal) => systemApi.overview(signal), []);

  return (
    <div>
      <section className={styles.hero}>
        <span className={styles.heroBadge}>ROLE-AWARE HEALTHCARE INTELLIGENCE PLATFORM</span>
        {overview.data ? (
          <>
            <h1 className={styles.heroTitle}>{overview.data.app_name}</h1>
            <p className={styles.heroText}>{overview.data.tagline}</p>
          </>
        ) : (
          <Skeleton height={64} width="60%" />
        )}
      </section>

      {overview.error && <ErrorState error={overview.error} onRetry={overview.reload} />}

      {overview.data && (
        <ol className={styles.flow} aria-label="Pipeline stages">
          {overview.data.pipeline_stages.map((stage) => (
            <li key={stage}>{stage}</li>
          ))}
        </ol>
      )}

      <h2 className={styles.sectionTitle}>Role consoles</h2>
      <div className={styles.personas}>
        {overview.loading || !overview.data
          ? Array.from({ length: 7 }, (_, i) => (
              <div key={i} className={styles.persona}>
                <Skeleton width="50%" height={16} />
                <Skeleton height={36} />
              </div>
            ))
          : overview.data.personas.map((p) => {
              const allowed = user?.allowed_routes.includes(p.route);
              return (
                <Link
                  key={p.persona}
                  to={user ? (allowed ? p.route : "/") : "/login"}
                  state={user ? undefined : { persona: p.persona }}
                  className={`${styles.persona} ${user && !allowed ? styles.locked : ""}`}
                  aria-disabled={user ? !allowed : undefined}
                >
                  <span className={styles.personaName}>{p.persona}</span>
                  <span className={styles.personaTitle}>{p.title}</span>
                  <span className={styles.personaDesc}>{p.description}</span>
                  <span className={styles.personaRole}>Role: {p.role}</span>
                </Link>
              );
            })}
      </div>
    </div>
  );
}
