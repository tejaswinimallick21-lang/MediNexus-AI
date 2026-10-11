import { useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import type { TemporaryPassword, UserAdminRow } from "../api/schemas/users";
import { usersApi, type NewUser } from "../api/users";
import { Badge, Button, SelectField, TextField } from "../components/Controls";
import { Panel } from "../components/Panel";
import { SkeletonText } from "../components/Skeleton";
import { ErrorState } from "../components/StateViews";
import { useApi } from "../hooks/useApi";
import { formatDate } from "../lib/format";
import styles from "./PeopleTab.module.css";

const ROLE_OPTIONS = [
  { value: "hcp", label: "Healthcare professional" },
  { value: "analyst", label: "Operations analyst" },
  { value: "admin", label: "Platform administrator" },
];
const EMPTY: NewUser = { email: "", name: "", role: "hcp", department: "" };

/** One account per person: add people, change roles, disable, reset passwords. */
export function PeopleTab() {
  const dir = useApi((s) => usersApi.list(s), []);
  const [form, setForm] = useState<NewUser>(EMPTY);
  const [issued, setIssued] = useState<{
    kind: "created" | "reset";
    result: TemporaryPassword;
  } | null>(null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError(undefined);
    try {
      await fn();
      dir.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "That change could not be saved.");
    } finally {
      setBusy(null);
    }
  }

  function add(e: FormEvent) {
    e.preventDefault();
    void run("add", async () => {
      const result = await usersApi.create({
        ...form,
        email: form.email.trim(),
      });
      setIssued({ kind: "created", result });
      setCopied(false);
      setForm(EMPTY);
    });
  }

  const reset = (u: UserAdminRow) =>
    run(`reset:${u.email}`, async () => {
      setIssued({
        kind: "reset",
        result: await usersApi.resetPassword(u.email),
      });
      setCopied(false);
    });

  if (dir.error) return <ErrorState error={dir.error} onRetry={dir.reload} />;
  const users = dir.data?.users ?? [];
  const waiting = users.filter((u) => u.active && u.must_change_password).length;

  return (
    <div className={styles.stack}>
      {issued && (
        <div className={styles.issued} role="status">
          <div>
            <strong>{issued.kind === "created" ? `${issued.result.user.name} can now sign in` : `Password reset for ${issued.result.user.name}`}</strong>
            <p>
              Give them this temporary password privately. It is shown only once, and they must choose their own at first sign-in
              {issued.kind === "reset" ? "; their open sessions have been signed out" : ""}.
            </p>
            <code className={styles.password}>{issued.result.temporary_password}</code>
            <span className={styles.muted}>Sign-in email: {issued.result.user.email}</span>
          </div>
          <div className={styles.issuedActions}>
            <Button
              onClick={() => {
                void navigator.clipboard?.writeText(issued.result.temporary_password).then(() => setCopied(true));
              }}
            >
              {copied ? "Copied" : "Copy password"}
            </Button>
            <Button variant="ghost" onClick={() => setIssued(null)}>
              Done
            </Button>
          </div>
        </div>
      )}

      <Panel title="Add a person" subtitle="They get their own sign-in, so the audit trail and Nexa's memory show who did what" icon="Users">
        <form className={styles.addForm} onSubmit={add}>
          <TextField id="new-name" label="Full name" value={form.name} onChange={(name) => setForm({ ...form, name })} maxLength={80} required />
          <TextField
            id="new-email"
            label="Work email"
            type="email"
            value={form.email}
            onChange={(email) => setForm({ ...form, email })}
            maxLength={254}
            required
          />
          <SelectField
            id="new-role"
            label="Role"
            value={form.role}
            options={ROLE_OPTIONS}
            onChange={(role) => setForm({ ...form, role: role as NewUser["role"] })}
          />
          <TextField
            id="new-dept"
            label="Department (optional)"
            value={form.department}
            onChange={(department) => setForm({ ...form, department })}
            maxLength={80}
          />
          <div className={styles.addButton}>
            <Button type="submit" variant="primary" disabled={busy === "add" || !form.name.trim() || !form.email.trim()}>
              {busy === "add" ? "Adding…" : "Add person"}
            </Button>
          </div>
        </form>
      </Panel>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <Panel
        title="People"
        subtitle={
          dir.data
            ? `${dir.data.active_count} active · ${dir.data.admin_count} administrator${dir.data.admin_count === 1 ? "" : "s"}${waiting ? ` · ${waiting} yet to set a password` : ""}`
            : undefined
        }
        icon="Shield"
      >
        {!dir.data ? (
          <SkeletonText lines={6} />
        ) : (
          <div className={styles.scroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Last sign-in</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.email} className={u.active ? undefined : styles.inactive}>
                    <td>
                      <strong>{u.name}</strong>
                      {u.is_you && <span className={styles.you}>you</span>}
                      <span className={styles.muted}>
                        {u.email}
                        {u.department ? ` · ${u.department}` : ""}
                      </span>
                    </td>
                    <td>
                      {u.is_you ? (
                        u.role_title
                      ) : (
                        <select
                          className={styles.roleSelect}
                          aria-label={`Role for ${u.name}`}
                          value={u.role}
                          disabled={!!busy}
                          onChange={(e) =>
                            void run(`role:${u.email}`, () =>
                              usersApi.update(u.email, {
                                role: e.target.value as NewUser["role"],
                              }),
                            )
                          }
                        >
                          {ROLE_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                      )}
                    </td>
                    <td>
                      {!u.active ? (
                        <Badge tone="bad">Disabled</Badge>
                      ) : u.must_change_password ? (
                        <Badge tone="warn">Must set password</Badge>
                      ) : (
                        <Badge tone="good">Active</Badge>
                      )}
                    </td>
                    <td className={styles.nowrap}>{u.last_login_at ? `${formatDate(u.last_login_at)} ${u.last_login_at.slice(11, 16)}` : "Never"}</td>
                    <td className={styles.actions}>
                      {!u.is_you && (
                        <>
                          {u.active && (
                            <Button variant="ghost" disabled={!!busy} onClick={() => void reset(u)}>
                              Reset password
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            disabled={!!busy}
                            onClick={() => void run(`active:${u.email}`, () => usersApi.update(u.email, { active: !u.active }))}
                          >
                            {u.active ? "Disable" : "Enable"}
                          </Button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className={styles.muted}>
          Disabling someone or resetting their password signs them out everywhere at once. You cannot change your own role or disable yourself, and at least one
          administrator always remains. Every change is in the audit trail.
        </p>
      </Panel>
    </div>
  );
}
