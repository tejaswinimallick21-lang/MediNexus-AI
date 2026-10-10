import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";

import { ACTIONS_CHANGED, actionsApi } from "../api/actions";
import { ApiError } from "../api/client";
import type { ActionInbox, AgentAction } from "../api/schemas/actions";
import { formatDate } from "../lib/format";
import { Badge, Button } from "./Controls";
import { Icon } from "./Icons";
import styles from "./ApprovalInbox.module.css";

const STATUS_TONE: Record<AgentAction["status"], "warn" | "good" | "bad" | "neutral"> = {
  pending: "warn",
  executed: "good",
  failed: "bad",
  rejected: "neutral",
};

/** Bell + drawer: actions proposed by Nexa agents wait here until a person approves or rejects them. */
export function ApprovalInbox() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<ActionInbox>();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      setData(await actionsApi.inbox());
    } catch {
      /* the badge simply stays as it was */
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(load, 30_000);
    const onChange = () => void load();
    const onOpen = () => {
      setOpen(true);
      void load();
    };
    window.addEventListener(ACTIONS_CHANGED, onChange);
    window.addEventListener("nexa:open-inbox", onOpen);
    return () => {
      clearInterval(t);
      window.removeEventListener(ACTIONS_CHANGED, onChange);
      window.removeEventListener("nexa:open-inbox", onOpen);
    };
  }, [load]);

  async function decide(a: AgentAction, approve: boolean) {
    setBusy(a.action_id);
    setError(undefined);
    try {
      await (approve ? actionsApi.approve(a.action_id) : actionsApi.reject(a.action_id));
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not record the decision.");
    } finally {
      setBusy(null);
    }
  }

  const pending = data?.pending ?? 0;
  return (
    <>
      <button type="button" className={styles.bell} onClick={() => setOpen((v) => !v)} aria-label={`Approval inbox, ${pending} pending`} title="Approval inbox">
        <Icon.Check size={18} />
        {pending > 0 && <span className={styles.count}>{pending > 99 ? "99+" : pending}</span>}
      </button>
      <AnimatePresence>
        {open && (
          <>
            <motion.div className={styles.scrim} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setOpen(false)} />
            <motion.aside
              className={styles.drawer}
              role="dialog"
              aria-label="Approval inbox"
              initial={{ x: 40, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 40, opacity: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 34 }}
            >
              <header className={styles.head}>
                <div>
                  <h3>Approval inbox</h3>
                  <p>Agents propose; nothing runs until a person approves. Every decision is audited.</p>
                </div>
                <button type="button" className={styles.close} onClick={() => setOpen(false)} aria-label="Close inbox">
                  <Icon.Close size={18} />
                </button>
              </header>
              {error && <p className={styles.error}>{error}</p>}
              <div className={styles.list}>
                {!data ? (
                  <p className={styles.muted}>Loading…</p>
                ) : data.items.length === 0 ? (
                  <p className={styles.muted}>No proposed actions yet. Ask a Nexa assistant, e.g. “Which medicines are at high stock-out risk? Propose an order for the worst one.”</p>
                ) : (
                  data.items.map((a) => (
                    <article key={a.action_id} className={`${styles.item} ${a.status === "pending" ? styles.pending : ""}`}>
                      <div className={styles.itemHead}>
                        <Badge tone={STATUS_TONE[a.status]}>{a.status === "executed" ? "Approved & done" : a.status}</Badge>
                        <span>{a.kind_label}</span>
                        <em>{formatDate(a.created_at)}</em>
                      </div>
                      <strong>{a.summary}</strong>
                      {a.reason && <p className={styles.reason}>Why: {a.reason}</p>}
                      <p className={styles.meta}>
                        Proposed by {a.agent} for {a.requested_by}
                        {a.decided_by ? ` · decided by ${a.decided_by}` : ""}
                      </p>
                      {a.result && <p className={styles.result}>{a.result}</p>}
                      {a.status === "pending" &&
                        (a.can_decide ? (
                          <div className={styles.actions}>
                            <Button variant="primary" onClick={() => decide(a, true)} disabled={busy === a.action_id}>
                              Approve
                            </Button>
                            <Button variant="ghost" onClick={() => decide(a, false)} disabled={busy === a.action_id}>
                              Reject
                            </Button>
                          </div>
                        ) : (
                          <p className={styles.meta}>Waiting for a colleague with approval rights.</p>
                        ))}
                    </article>
                  ))
                )}
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
