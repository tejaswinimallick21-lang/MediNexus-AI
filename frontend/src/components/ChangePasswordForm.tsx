import { useState, type FormEvent } from "react";

import { authApi } from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { Button, TextField } from "./Controls";
import styles from "./ChangePasswordForm.module.css";

/** Change your own password. Signs out your other sessions; this one stays signed in. */
export function ChangePasswordForm({ onDone }: { onDone?: () => void }) {
  const { refresh } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string>();
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(undefined);
    setSaved(false);
    if (next !== confirm) {
      setError("The two new passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const user = await authApi.changePassword(current, next);
      setCurrent("");
      setNext("");
      setConfirm("");
      setSaved(true);
      refresh(user);
      onDone?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not change the password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={submit}>
      <TextField id="pw-current" label="Current password" type="password" value={current} onChange={setCurrent} autoComplete="current-password" required />
      <TextField id="pw-new" label="New password" type="password" value={next} onChange={setNext} autoComplete="new-password" required />
      <TextField id="pw-confirm" label="Repeat new password" type="password" value={confirm} onChange={setConfirm} autoComplete="new-password" required />
      <p className={styles.hint}>At least 10 characters, with a letter and a number. Your other sessions will be signed out.</p>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {saved && (
        <p className={styles.ok} role="status">
          Password changed.
        </p>
      )}
      <div>
        <Button type="submit" variant="primary" disabled={busy || !current || !next || !confirm}>
          {busy ? "Saving…" : "Change password"}
        </Button>
      </div>
    </form>
  );
}
