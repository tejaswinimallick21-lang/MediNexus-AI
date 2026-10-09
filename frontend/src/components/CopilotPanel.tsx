import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { agentApi, type AgentKey } from "../api/operations";
import type { AgentReply } from "../api/schemas/operations";
import { Icon } from "./Icons";
import { Skeleton } from "./Skeleton";
import styles from "./CopilotPanel.module.css";

type Message = { id: number; role: "user"; text: string } | { id: number; role: "assistant"; reply: AgentReply } | { id: number; role: "error"; text: string };

const SECTIONS: { key: keyof Pick<AgentReply, "facts" | "predictions" | "recommendations">; label: string }[] = [
  { key: "facts", label: "Facts" },
  { key: "predictions", label: "Predictions" },
  { key: "recommendations", label: "Recommended actions" },
];

export function CopilotPanel({
  agent,
  name,
  tagline,
  prompts,
}: {
  agent: AgentKey;
  name: string;
  tagline: string;
  prompts: string[];
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const idRef = useRef(0);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function ask(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setInput("");
    setMessages((m) => [...m, { id: ++idRef.current, role: "user", text: question }]);
    setBusy(true);
    try {
      const reply = await agentApi.chat(agent, question);
      setMessages((m) => [...m, { id: ++idRef.current, role: "assistant", reply }]);
    } catch (err) {
      setMessages((m) => [...m, { id: ++idRef.current, role: "error", text: err instanceof ApiError ? err.detail : "The assistant is unavailable." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-label={`${name} assistant`}>
      <header className={styles.header}>
        <span className={styles.orb} aria-hidden="true">
          <Icon.Sparkle size={18} />
        </span>
        <div>
          <h3>{name}</h3>
          <p>{tagline}</p>
        </div>
        {messages.length > 0 && (
          <button type="button" className={styles.clear} onClick={() => setMessages([])}>
            Clear
          </button>
        )}
      </header>

      <div className={styles.messages} ref={listRef} aria-live="polite">
        {messages.length === 0 && (
          <div className={styles.empty}>
            <p>Ask a question in plain language. Answers are grounded in the lakehouse and cite their sources.</p>
            <div className={styles.prompts}>
              {prompts.map((p) => (
                <button key={p} type="button" onClick={() => ask(p)}>
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}
        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <motion.div
              key={m.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={m.role === "user" ? styles.user : m.role === "error" ? styles.error : styles.assistant}
            >
              {m.role === "assistant" ? (
                <>
                  {m.reply.answer && <p className={styles.answer}>{m.reply.answer}</p>}
                  {SECTIONS.map(({ key, label }) =>
                    m.reply[key].length ? (
                      <div key={key} className={styles.section}>
                        <span className={styles.sectionLabel}>{label}</span>
                        <ul>
                          {m.reply[key].map((line, i) => (
                            <li key={i}>{line}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null,
                  )}
                  {m.reply.evidence.length > 0 && (
                    <details className={styles.evidence}>
                      <summary>
                        Evidence & sources · {m.reply.latency_ms.toFixed(0)} ms
                      </summary>
                      <ul>
                        {m.reply.evidence.map((e, i) => (
                          <li key={i}>{e}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </>
              ) : (
                m.text
              )}
            </motion.div>
          ))}
        </AnimatePresence>
        {busy && (
          <div className={styles.assistant} aria-busy="true">
            <Skeleton width="80%" />
            <Skeleton width="60%" />
            <Skeleton width="70%" />
          </div>
        )}
      </div>

      <form
        className={styles.composer}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          void ask(input);
        }}
      >
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={`Ask ${name}…`} maxLength={2000} aria-label={`Message ${name}`} />
        <button type="submit" disabled={busy || !input.trim()} aria-label="Send">
          <Icon.Arrow size={18} />
        </button>
      </form>
    </section>
  );
}
