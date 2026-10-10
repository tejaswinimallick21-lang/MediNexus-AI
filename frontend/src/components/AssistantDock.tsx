import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useLocation } from "react-router-dom";

import { ACTIONS_CHANGED } from "../api/actions";
import { assistantApi } from "../api/assistant";
import { ApiError } from "../api/client";
import type { AssistantAgent, AssistantMessage, AssistantSession } from "../api/schemas/assistant";
import type { AgentReply } from "../api/schemas/operations";
import { useAuth } from "../hooks/useAuth";
import { Icon } from "./Icons";
import { Skeleton } from "./Skeleton";
import styles from "./AssistantDock.module.css";

const SECTIONS: { key: keyof Pick<AgentReply, "facts" | "predictions" | "recommendations">; label: string }[] = [
  { key: "facts", label: "Facts" },
  { key: "predictions", label: "Predictions" },
  { key: "recommendations", label: "Recommended actions" },
];

/** Per-viewer convenience only (open state, last conversation); history itself lives on the server. */
function stored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function store(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable */
  }
}

/** Groups conversations like ChatGPT / Claude: Today, Yesterday, Previous 7 days, Older. */
export function groupSessions(sessions: AssistantSession[], now = new Date()): { label: string; items: AssistantSession[] }[] {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 86_400_000;
  const buckets: Record<string, AssistantSession[]> = { Today: [], Yesterday: [], "Previous 7 days": [], Older: [] };
  for (const s of sessions) {
    const t = new Date(s.updated_at).getTime();
    if (t >= startOfToday) buckets.Today.push(s);
    else if (t >= startOfToday - day) buckets.Yesterday.push(s);
    else if (t >= startOfToday - 7 * day) buckets["Previous 7 days"].push(s);
    else buckets.Older.push(s);
  }
  return Object.entries(buckets)
    .filter(([, items]) => items.length)
    .map(([label, items]) => ({ label, items }));
}

type Pending = { text: string } | null;

export function AssistantDock() {
  const { user } = useAuth();
  const location = useLocation();
  const prefix = user ? `nexa:${user.email}` : "nexa";

  const [open, setOpen] = useState(() => stored(`${prefix}:open`) === "1");
  const [expanded, setExpanded] = useState(false);
  const [showHistory, setShowHistory] = useState(() => typeof window === "undefined" || window.innerWidth > 720);
  const [agents, setAgents] = useState<AssistantAgent[]>([]);
  const [agentKey, setAgentKey] = useState<string | null>(null);
  const [sessions, setSessions] = useState<AssistantSession[]>([]);
  const [sessionsError, setSessionsError] = useState<string>();
  const [activeId, setActiveId] = useState<string | null>(() => stored(`${prefix}:session`));
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [pending, setPending] = useState<Pending>(null);
  const [error, setError] = useState<string>();
  const [input, setInput] = useState("");
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const routeAgent = useMemo(
    () => agents.find((a) => a.routes.some((r) => location.pathname.startsWith(r)))?.key ?? agents[0]?.key ?? null,
    [agents, location.pathname],
  );
  const active = sessions.find((s) => s.session_id === activeId) ?? null;
  const currentKey = active?.agent ?? agentKey ?? routeAgent;
  const agent = agents.find((a) => a.key === currentKey) ?? agents[0];

  // A different account signs in: start from that user's own history
  useEffect(() => {
    setAgents([]);
    setSessions([]);
    setMessages([]);
    setAgentKey(null);
    setActiveId(stored(`${prefix}:session`));
    setOpen(stored(`${prefix}:open`) === "1");
  }, [prefix]);

  useEffect(() => store(`${prefix}:open`, open ? "1" : null), [open, prefix]);
  useEffect(() => store(`${prefix}:session`, activeId), [activeId, prefix]);

  // Catalogue + history load once the panel is first opened
  const loadSessions = useCallback(async () => {
    try {
      const page = await assistantApi.sessions({ limit: 100 });
      setSessions(page.items);
      setSessionsError(undefined);
    } catch (err) {
      setSessionsError(err instanceof ApiError ? err.detail : "Could not load conversations.");
    }
  }, []);

  useEffect(() => {
    if (!user || !open || agents.length) return;
    assistantApi.agents().then(setAgents).catch(() => setAgents([]));
    void loadSessions();
  }, [user, open, agents.length, loadSessions]);

  // Load the selected conversation
  useEffect(() => {
    if (!open || !activeId) {
      setMessages([]);
      return;
    }
    const controller = new AbortController();
    setLoadingMessages(true);
    setError(undefined);
    assistantApi
      .messages(activeId, controller.signal)
      .then((m) => setMessages(m))
      .catch((err: unknown) => {
        if ((err as Error)?.name === "AbortError") return;
        if (err instanceof ApiError && err.status === 404) setActiveId(null);
        else setError(err instanceof ApiError ? err.detail : "Could not load this conversation.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingMessages(false);
      });
    return () => controller.abort();
  }, [activeId, open]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    inputRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!user || location.pathname === "/login") return null;

  /** On phones the history rail overlays the chat, so close it once a choice is made. */
  const closeRailOnPhone = () => {
    if (window.innerWidth <= 720) setShowHistory(false);
  };

  function openSession(id: string) {
    setActiveId(id);
    closeRailOnPhone();
  }

  function newChat(key?: string) {
    closeRailOnPhone();
    setActiveId(null);
    setAgentKey(key ?? routeAgent);
    setMessages([]);
    setError(undefined);
    inputRef.current?.focus();
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || pending || !agent) return;
    setInput("");
    setError(undefined);
    setPending({ text: question });
    try {
      let id = activeId;
      if (!id) {
        const created = await assistantApi.create(agent.key);
        id = created.session_id;
        setSessions((s) => [created, ...s]);
        setActiveId(id);
      }
      const exchange = await assistantApi.send(id, question);
      setMessages((m) => [...m, ...exchange.messages]);
      if (exchange.messages.some((x) => x.reply?.proposed_actions?.length)) window.dispatchEvent(new Event(ACTIONS_CHANGED));
      setSessions((s) => [exchange.session, ...s.filter((x) => x.session_id !== exchange.session.session_id)]);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "The assistant is unavailable.");
      setInput(question);
    } finally {
      setPending(null);
    }
  }

  async function rename(id: string, title: string) {
    setRenaming(null);
    if (!title.trim()) return;
    try {
      const updated = await assistantApi.rename(id, title.trim());
      setSessions((s) => s.map((x) => (x.session_id === id ? updated : x)));
    } catch {
      /* keep the old title */
    }
  }

  async function remove(id: string) {
    setConfirmDelete(null);
    try {
      await assistantApi.remove(id);
      setSessions((s) => s.filter((x) => x.session_id !== id));
      if (activeId === id) newChat();
    } catch (err) {
      setSessionsError(err instanceof ApiError ? err.detail : "Could not delete the conversation.");
    }
  }

  const groups = groupSessions(sessions);

  return (
    <>
      <AnimatePresence>
        {!open && (
          <motion.button
            key="launcher"
            type="button"
            className={styles.launcher}
            onClick={() => setOpen(true)}
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.6, opacity: 0 }}
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.95 }}
            aria-label="Open Nexa assistant"
          >
            <span className={styles.launcherRing} aria-hidden="true" />
            <Icon.Sparkle size={24} />
            <span className={styles.launcherLabel}>Ask Nexa</span>
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {open && (
          <motion.section
            key="window"
            className={`${styles.window} ${expanded ? styles.expanded : ""}`}
            role="dialog"
            aria-label="Nexa assistant"
            initial={{ opacity: 0, y: 24, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 360, damping: 32 }}
          >
            {showHistory && (
              <aside className={styles.history} aria-label="Conversation history">
                <button type="button" className={styles.newChat} onClick={() => newChat()}>
                  <Icon.Plus size={16} /> New conversation
                </button>
                {agents.length > 1 && (
                  <div className={styles.agentPicker} role="radiogroup" aria-label="Assistant">
                    {agents.map((a) => (
                      <button
                        key={a.key}
                        type="button"
                        role="radio"
                        aria-checked={a.key === currentKey}
                        className={a.key === currentKey ? styles.agentOn : ""}
                        onClick={() => newChat(a.key)}
                        title={a.tagline}
                      >
                        {a.name}
                      </button>
                    ))}
                  </div>
                )}
                <div className={styles.sessionList}>
                  {sessionsError && <p className={styles.historyNote}>{sessionsError}</p>}
                  {!sessionsError && sessions.length === 0 && <p className={styles.historyNote}>Your conversations will appear here.</p>}
                  {groups.map((g) => (
                    <div key={g.label}>
                      <span className={styles.groupLabel}>{g.label}</span>
                      <ul>
                        {g.items.map((s) => (
                          <li key={s.session_id} className={s.session_id === activeId ? styles.sessionOn : ""}>
                            {renaming?.id === s.session_id ? (
                              <input
                                className={styles.renameInput}
                                autoFocus
                                value={renaming.title}
                                maxLength={80}
                                aria-label="Conversation title"
                                onChange={(e) => setRenaming({ id: s.session_id, title: e.target.value })}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") void rename(s.session_id, renaming.title);
                                  if (e.key === "Escape") {
                                    e.stopPropagation();
                                    setRenaming(null);
                                  }
                                }}
                                onBlur={() => void rename(s.session_id, renaming.title)}
                              />
                            ) : confirmDelete === s.session_id ? (
                              <div className={styles.confirm}>
                                <span>Delete?</span>
                                <button type="button" className={styles.danger} onClick={() => void remove(s.session_id)}>
                                  Delete
                                </button>
                                <button type="button" onClick={() => setConfirmDelete(null)}>
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <>
                                <button type="button" className={styles.sessionTitle} onClick={() => openSession(s.session_id)} title={s.title}>
                                  {s.title}
                                </button>
                                <span className={styles.sessionActions}>
                                  <button type="button" aria-label={`Rename ${s.title}`} onClick={() => setRenaming({ id: s.session_id, title: s.title })}>
                                    <Icon.Pencil size={14} />
                                  </button>
                                  <button type="button" aria-label={`Delete ${s.title}`} onClick={() => setConfirmDelete(s.session_id)}>
                                    <Icon.Trash size={14} />
                                  </button>
                                </span>
                              </>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </aside>
            )}

            <div className={styles.chat}>
              <header className={styles.header}>
                <button type="button" className={styles.iconBtn} onClick={() => setShowHistory((v) => !v)} aria-label={showHistory ? "Hide history" : "Show history"} title="History">
                  <Icon.Sidebar size={18} />
                </button>
                <span className={styles.orb} aria-hidden="true">
                  <Icon.Sparkle size={16} />
                </span>
                <div className={styles.headText}>
                  <h3>{agent?.name ?? "Nexa"}</h3>
                  <p>{active ? active.title : agent?.tagline ?? "Loading assistants…"}</p>
                </div>
                <button type="button" className={styles.iconBtn} onClick={() => setExpanded((v) => !v)} aria-label={expanded ? "Restore size" : "Expand"} title={expanded ? "Restore" : "Expand"}>
                  {expanded ? <Icon.Collapse size={18} /> : <Icon.Expand size={18} />}
                </button>
                <button type="button" className={styles.iconBtn} onClick={() => setOpen(false)} aria-label="Close assistant" title="Close (Esc)">
                  <Icon.Close size={18} />
                </button>
              </header>

              <div className={styles.messages} ref={listRef} aria-live="polite">
                {loadingMessages && (
                  <div className={styles.assistant}>
                    <Skeleton width="70%" />
                    <Skeleton width="50%" />
                  </div>
                )}
                {!loadingMessages && messages.length === 0 && !pending && (
                  <div className={styles.empty}>
                    <span className={styles.emptyOrb} aria-hidden="true">
                      <Icon.Sparkle size={26} />
                    </span>
                    <h4>How can {agent?.name ?? "Nexa"} help?</h4>
                    <p>Answers are grounded in the lakehouse and hospital policy, and cite their sources.</p>
                    <div className={styles.prompts}>
                      {agent?.prompts.map((p) => (
                        <button key={p} type="button" onClick={() => void send(p)}>
                          {p}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {messages.map((m) => (
                  <motion.div key={m.message_id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className={m.role === "user" ? styles.user : styles.assistant}>
                    {m.role === "assistant" && m.reply ? <Reply reply={m.reply} /> : m.text}
                  </motion.div>
                ))}
                {pending && (
                  <>
                    <div className={styles.user}>{pending.text}</div>
                    <div className={styles.assistant} aria-busy="true">
                      <span className={styles.typing} aria-label="Nexa is thinking">
                        <i />
                        <i />
                        <i />
                      </span>
                    </div>
                  </>
                )}
                {error && <div className={styles.error}>{error}</div>}
              </div>

              <form
                className={styles.composer}
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  void send(input);
                }}
              >
                <textarea
                  ref={inputRef}
                  rows={1}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send(input);
                    }
                  }}
                  placeholder={`Message ${agent?.name ?? "Nexa"}…`}
                  maxLength={2000}
                  aria-label="Message"
                />
                <button type="submit" disabled={!!pending || !input.trim() || !agent} aria-label="Send">
                  <Icon.Arrow size={18} />
                </button>
              </form>
              <p className={styles.disclaimer}>Decision support only. Verify before acting; actions require human approval.</p>
            </div>
          </motion.section>
        )}
      </AnimatePresence>
    </>
  );
}

/** Minimal, safe formatting for model text: paragraphs, "- " bullets and **bold** (no HTML injection). */
function RichText({ text }: { text: string }) {
  const blocks: { list: boolean; lines: string[] }[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) {
      blocks.push({ list: false, lines: [] });
      continue;
    }
    const isItem = /^([-*•]|\d+[.)])\s+/.test(line);
    const last = blocks[blocks.length - 1];
    const content = isItem ? line.replace(/^([-*•]|\d+[.)])\s+/, "") : line.replace(/^#{1,4}\s+/, "");
    if (last && last.list === isItem && last.lines.length) last.lines.push(content);
    else blocks.push({ list: isItem, lines: [content] });
  }
  const inline = (s: string) =>
    s.split(/(\*\*[^*]+\*\*)/g).map((part, i) => (part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part));
  return (
    <>
      {blocks
        .filter((b) => b.lines.length)
        .map((b, i) =>
          b.list ? (
            <ul key={i}>
              {b.lines.map((l, j) => (
                <li key={j}>{inline(l)}</li>
              ))}
            </ul>
          ) : (
            <p key={i} className={styles.answer}>
              {b.lines.map((l, j) => (
                <span key={j}>
                  {j > 0 && <br />}
                  {inline(l)}
                </span>
              ))}
            </p>
          ),
        )}
    </>
  );
}

function Reply({ reply }: { reply: AgentReply }) {
  const tools = reply.tool_calls ?? [];
  return (
    <>
      {reply.engine && <span className={styles.engine}>{reply.engine}</span>}
      {reply.answer && <RichText text={reply.answer} />}
      {SECTIONS.map(({ key, label }) =>
        reply[key].length ? (
          <div key={key}>
            <span className={styles.sectionLabel}>{label}</span>
            <ul>
              {reply[key].map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          </div>
        ) : null,
      )}
      {(reply.proposed_actions ?? []).map((a) => (
        <div key={a.action_id} className={styles.proposal}>
          <Icon.Clock size={14} />
          <span>
            <strong>Awaiting approval:</strong> {a.summary}
          </span>
          <button type="button" onClick={() => window.dispatchEvent(new Event("nexa:open-inbox"))}>
            Review
          </button>
        </div>
      ))}
      {reply.notes && <p className={styles.note}>{reply.notes}</p>}
      {(reply.evidence.length > 0 || tools.length > 0) && (
        <details className={styles.evidence}>
          <summary>
            Evidence & sources{tools.length ? ` · ${tools.length} data tool${tools.length === 1 ? "" : "s"}` : ""} · {reply.latency_ms.toFixed(0)} ms
          </summary>
          <ul>
            {reply.evidence.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
