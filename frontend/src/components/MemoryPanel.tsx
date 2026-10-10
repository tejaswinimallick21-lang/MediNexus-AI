import { useEffect, useState, type FormEvent } from "react";

import { assistantApi } from "../api/assistant";
import { ApiError } from "../api/client";
import type { MemoryItem } from "../api/schemas/assistant";
import { Icon } from "./Icons";
import styles from "./MemoryPanel.module.css";

/** "What Nexa remembers": the signed-in user's long-term memory, visible and deletable. */
export function MemoryPanel({ onClose }: { onClose: () => void }) {
  const [items, setItems] = useState<MemoryItem[] | null>(null);
  const [error, setError] = useState<string>();
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    assistantApi
      .memory(controller.signal)
      .then(setItems)
      .catch((err: unknown) => {
        if ((err as Error)?.name !== "AbortError")
          setError(
            err instanceof ApiError ? err.detail : "Could not load memories.",
          );
      });
    return () => controller.abort();
  }, []);

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!text.trim() || saving) return;
    setSaving(true);
    setError(undefined);
    try {
      const saved = await assistantApi.remember(text.trim());
      setItems((m) => [
        saved,
        ...(m ?? []).filter((x) => x.memory_id !== saved.memory_id),
      ]);
      setText("");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  async function forget(id: string) {
    try {
      await assistantApi.forget(id);
      setItems((m) => (m ?? []).filter((x) => x.memory_id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not delete.");
    }
  }

  async function forgetAll() {
    setConfirmClear(false);
    try {
      await assistantApi.forgetAll();
      setItems([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not delete.");
    }
  }

  return (
    <div className={styles.panel} aria-label="What Nexa remembers">
      <div className={styles.head}>
        <h4>What Nexa remembers</h4>
        <button type="button" className={styles.back} onClick={onClose}>
          Back to chat
        </button>
      </div>
      <p className={styles.note}>
        Preferences you asked Nexa to keep, used by all your assistants. Say
        "remember …" in chat or add one here. Nexa never stores patient or
        personal data, and these are never used as a source for figures.
      </p>

      <form className={styles.add} onSubmit={add}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={300}
          placeholder="e.g. I manage the north region hospitals"
          aria-label="New memory"
        />
        <button type="submit" disabled={!text.trim() || saving}>
          Remember
        </button>
      </form>
      {error && <p className={styles.error}>{error}</p>}

      {items === null && !error && <p className={styles.note}>Loading…</p>}
      {items?.length === 0 && <p className={styles.note}>Nothing yet.</p>}
      <ul className={styles.list}>
        {items?.map((m) => (
          <li key={m.memory_id}>
            <span>
              {m.text}
              <small>
                {m.source === "chat" ? "from chat" : "added here"} ·{" "}
                {new Date(m.created_at).toLocaleDateString()}
              </small>
            </span>
            <button
              type="button"
              aria-label={`Forget: ${m.text}`}
              title="Forget"
              onClick={() => void forget(m.memory_id)}
            >
              <Icon.Trash size={14} />
            </button>
          </li>
        ))}
      </ul>

      {!!items?.length &&
        (confirmClear ? (
          <div className={styles.clear}>
            <span>Forget all {items.length}?</span>
            <button
              type="button"
              className={styles.danger}
              onClick={() => void forgetAll()}
            >
              Forget all
            </button>
            <button type="button" onClick={() => setConfirmClear(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            className={styles.clearBtn}
            onClick={() => setConfirmClear(true)}
          >
            Forget everything
          </button>
        ))}
    </div>
  );
}
