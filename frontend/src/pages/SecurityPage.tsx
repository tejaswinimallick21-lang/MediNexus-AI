import { useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ApiError } from "../api/client";
import type { AuditEvent, Posture, SearchHit } from "../api/schemas/security";
import { knowledgeApi, securityApi } from "../api/security";
import { Badge, Button, SelectField } from "../components/Controls";
import { DataTable, type Column } from "../components/DataTable";
import { Icon } from "../components/Icons";
import { KpiGrid } from "../components/Kpi";
import { Grid, PageHeader, Panel } from "../components/Panel";
import { SkeletonText } from "../components/Skeleton";
import { EmptyState, ErrorState } from "../components/StateViews";
import { Tabs } from "../components/Tabs";
import { useApi } from "../hooks/useApi";
import { useCursorPager } from "../hooks/useCursorPager";
import { formatDate, formatNumber } from "../lib/format";
import { PeopleTab } from "./PeopleTab";
import styles from "./SecurityPage.module.css";

type TabId = "overview" | "people" | "audit" | "access" | "ai" | "knowledge";
const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "people", label: "People" },
  { id: "audit", label: "Audit trail" },
  { id: "access", label: "Access control" },
  { id: "ai", label: "AI governance" },
  { id: "knowledge", label: "Knowledge base" },
];
const STATUS_TONE = { pass: "good", warn: "warn", fail: "bad" } as const;

export function SecurityPage() {
  const [tab, setTab] = useState<TabId>("overview");
  return (
    <div>
      <PageHeader
        eyebrow="Platform administrator"
        title="Security & Infrastructure"
        subtitle="Live security posture, people and their sign-ins, audit trail, access control, AI governance and the knowledge library behind the assistants. Every figure is measured from the running system."
      />
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      {tab === "overview" && <OverviewTab />}
      {tab === "people" && <PeopleTab />}
      {tab === "audit" && <AuditTab />}
      {tab === "access" && <AccessTab />}
      {tab === "ai" && <AiTab />}
      {tab === "knowledge" && <KnowledgeTab />}
    </div>
  );
}

// ---- overview ---------------------------------------------------------------------------------

function OverviewTab() {
  const posture = useApi((s) => securityApi.posture(s), []);
  const infra = useApi((s) => securityApi.infra(s), []);
  const i = infra.data;
  return (
    <div className={styles.stack}>
      {posture.error ? <ErrorState error={posture.error} onRetry={posture.reload} /> : posture.data ? <PosturePanel p={posture.data} /> : <SkeletonText lines={8} />}
      <KpiGrid
        count={4}
        loading={infra.loading}
        error={infra.error}
        onRetry={infra.reload}
        items={
          i && [
            { label: "Database", value: i.database_size_mb, format: (n) => `${formatNumber(n, 0)} MB`, icon: "Database", hint: `${i.tables.length} tables · ${i.database_path}` },
            { label: "Active models", value: i.active_models, format: (n) => formatNumber(n), icon: "Pulse", hint: i.models_last_trained ? `Last trained ${formatDate(i.models_last_trained)}` : "Not trained" },
            { label: "Knowledge library", value: i.knowledge_documents, format: (n) => `${formatNumber(n)} docs`, icon: "Clipboard", hint: `${i.knowledge_chunks} sections · ${i.embeddings}` },
            { label: "API uptime", value: i.uptime_minutes, format: (n) => (n >= 60 ? `${formatNumber(n / 60, 1)} h` : `${formatNumber(n)} min`), icon: "Clock", hint: `v${i.api_version} · ${i.environment} · Python ${i.python}` },
          ]
        }
      />
      {i && (
        <Grid>
          <Panel title="Lakehouse layers" subtitle="Rows per Medallion layer (DuckDB estimates)" icon="Database">
            <ul className={styles.bars}>
              {Object.entries(i.layer_rows)
                .sort((a, b) => b[1] - a[1])
                .map(([layer, rows]) => (
                  <li key={layer}>
                    <span className={styles.layer} data-layer={layer}>
                      {layer}
                    </span>
                    <div className={styles.track}>
                      <span style={{ width: `${(rows / Math.max(...Object.values(i.layer_rows))) * 100}%` }} />
                    </div>
                    <strong>{formatNumber(rows)}</strong>
                  </li>
                ))}
            </ul>
            <p className={styles.muted}>
              AI engine: {i.llm_provider} · next morning sweep {formatDate(i.sweep_next_run)} {i.sweep_next_run.slice(11, 16)}
              {i.sweep_last_status ? ` (last: ${i.sweep_last_status})` : ""} · background jobs running: {i.active_jobs.join(", ") || "none"} · {i.platform}
            </p>
          </Panel>
          <Panel title="Storage" subtitle="Disk used by each data area" icon="Clipboard">
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Area</th>
                  <th>Path</th>
                  <th className={styles.num}>Files</th>
                  <th className={styles.num}>Size</th>
                </tr>
              </thead>
              <tbody>
                {i.storage.map((s) => (
                  <tr key={s.path}>
                    <td>{s.label}</td>
                    <td>
                      <code>{s.path}</code>
                    </td>
                    <td className={styles.num}>{formatNumber(s.files)}</td>
                    <td className={styles.num}>{formatNumber(s.size_mb, 1)} MB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </Grid>
      )}
    </div>
  );
}

function PosturePanel({ p }: { p: Posture }) {
  const areas = useMemo(() => [...new Set(p.checks.map((c) => c.area))], [p]);
  return (
    <Panel title="Security posture" subtitle={`${p.checks.length} checks against the live configuration · environment: ${p.environment}`} icon="Shield">
      <div className={styles.postureHead}>
        <div className={styles.ring} style={{ ["--score" as string]: `${p.score}` }}>
          <strong>{p.score}</strong>
          <span>of 100</span>
        </div>
        <div className={styles.postureCounts}>
          <Badge tone="good">{p.passed} passed</Badge>
          <Badge tone="warn">{p.warnings} warnings</Badge>
          <Badge tone="bad">{p.failures} failures</Badge>
          <p className={styles.muted}>Warnings are expected in development; each one says what to change before going live.</p>
        </div>
      </div>
      <div className={styles.areas}>
        {areas.map((area) => (
          <section key={area}>
            <h4>{area}</h4>
            <ul className={styles.checks}>
              {p.checks
                .filter((c) => c.area === area)
                .map((c) => (
                  <li key={c.id} className={styles[`check_${c.status}`]}>
                    <span className={styles.checkIcon}>{c.status === "pass" ? <Icon.Check size={14} /> : <Icon.Alert size={14} />}</span>
                    <div>
                      <div className={styles.checkHead}>
                        <strong>{c.title}</strong>
                        <Badge tone={STATUS_TONE[c.status]}>{c.status}</Badge>
                      </div>
                      <p>{c.detail}</p>
                      {c.fix && <p className={styles.fix}>Fix: {c.fix}</p>}
                    </div>
                  </li>
                ))}
            </ul>
          </section>
        ))}
      </div>
    </Panel>
  );
}

// ---- audit --------------------------------------------------------------------------------------

const AUDIT_COLUMNS: Column<AuditEvent>[] = [
  { key: "ts", header: "When", render: (r) => <span className={styles.nowrap}>{formatDate(r.timestamp)} {r.timestamp.slice(11, 19)}</span> },
  { key: "user", header: "User", render: (r) => r.username },
  { key: "role", header: "Role", render: (r) => r.role },
  { key: "action", header: "Action", render: (r) => <code>{r.action}</code> },
  { key: "resource", header: "Resource", render: (r) => <span className={styles.clip}>{r.resource}</span> },
  {
    key: "status",
    header: "Status",
    render: (r) => <Badge tone={r.status === "SUCCESS" ? "good" : r.status === "FAILED" || r.status === "BLOCKED" ? "bad" : "neutral"}>{r.status}</Badge>,
  },
  { key: "details", header: "Details", render: (r) => <span className={styles.details}>{r.details}</span> },
];

function AuditTab() {
  const [days, setDays] = useState(7);
  const [action, setAction] = useState("");
  const [status, setStatus] = useState("");
  const [user, setUser] = useState("");
  const [debouncedUser, setDebouncedUser] = useState("");
  const pager = useCursorPager();
  useEffect(() => {
    const t = setTimeout(() => setDebouncedUser(user), 300);
    return () => clearTimeout(t);
  }, [user]);
  useEffect(() => pager.reset(), [days, action, status, debouncedUser]); // eslint-disable-line react-hooks/exhaustive-deps
  const summary = useApi((s) => securityApi.auditSummary(days, s), [days]);
  const events = useApi(
    (s) => securityApi.audit({ limit: 15, cursor: pager.cursor, days, action: action || undefined, status: status || undefined, user: debouncedUser || undefined }, s),
    [days, action, status, debouncedUser, pager.cursor],
  );
  const d = summary.data;
  return (
    <div className={styles.stack}>
      <KpiGrid
        count={4}
        loading={summary.loading}
        error={summary.error}
        onRetry={summary.reload}
        items={
          d && [
            { label: "Events", value: d.total_events, format: (n) => formatNumber(n), icon: "Clipboard", hint: `Last ${d.window_days} days` },
            { label: "Failed sign-ins", value: d.failed_logins, format: (n) => formatNumber(n), icon: "Key", tone: d.failed_logins > 20 ? "warn" : "neutral", hint: `${d.lockouts} lockouts · ${Object.keys(d.locked_now).length} locked now` },
            { label: "Blocked by access control", value: d.access_denied, format: (n) => formatNumber(n), icon: "Shield", hint: "Requests outside the user's role" },
            { label: "Patient-record views", value: d.patient_record_views, format: (n) => formatNumber(n), icon: "Stethoscope", hint: "Every view is attributable" },
          ]
        }
      />
      {d && (
        <Grid>
          <Panel title="Activity by day" subtitle="All events, failed sign-ins and blocked requests" icon="Pulse">
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={d.by_day} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                <XAxis dataKey="day" tickFormatter={(v: string) => formatDate(v).slice(0, 6)} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="events" name="Events" fill="#0ea5e9" radius={[3, 3, 0, 0]} />
                <Bar dataKey="failed_logins" name="Failed sign-ins" fill="#f59e0b" radius={[3, 3, 0, 0]} />
                <Bar dataKey="denied" name="Blocked" fill="#ef4444" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Panel>
          <Panel title="Where attention is needed" subtitle="Accounts with failed sign-ins and the most-blocked resources" icon="Alert">
            <div className={styles.twoLists}>
              <div>
                <h4>Failed sign-ins by account</h4>
                <CountList rows={d.failed_login_accounts} empty="None" />
              </div>
              <div>
                <h4>Blocked requests by resource</h4>
                <CountList rows={d.denied_resources} empty="None" />
              </div>
            </div>
            <p className={styles.muted}>Note: automated test runs share this database, so part of this activity comes from tests exercising the access rules.</p>
          </Panel>
        </Grid>
      )}
      <Panel
        title="Audit trail"
        subtitle="Newest first · question text from assistants is never stored"
        icon="Clipboard"
        actions={
          <div className={styles.filters}>
            <SelectField id="aud-days" label="Period" value={String(days)} onChange={(v) => setDays(Number(v))} options={[1, 7, 30, 90].map((x) => ({ value: String(x), label: `${x} day${x > 1 ? "s" : ""}` }))} />
            <SelectField id="aud-action" label="Action" value={action} onChange={setAction} options={[{ value: "", label: "All actions" }, ...(d?.actions ?? []).map((a) => ({ value: a, label: a }))]} />
            <SelectField
              id="aud-status"
              label="Status"
              value={status}
              onChange={setStatus}
              options={[{ value: "", label: "Any" }, ...["SUCCESS", "FAILED", "BLOCKED", "PENDING", "FALLBACK"].map((x) => ({ value: x, label: x }))]}
            />
            <label className={styles.search}>
              <span>User</span>
              <input value={user} onChange={(e) => setUser(e.target.value)} placeholder="email contains…" />
            </label>
          </div>
        }
      >
        <DataTable
          columns={AUDIT_COLUMNS}
          rows={events.data?.items}
          rowKey={(r) => r.log_id}
          loading={events.loading}
          error={events.error}
          onRetry={events.reload}
          emptyTitle="No events match these filters"
          caption="Audit trail"
          footer={
            <>
              <span>Page {pager.page}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <Button onClick={pager.prev} disabled={!pager.hasPrev || events.loading}>
                  Previous
                </Button>
                <Button onClick={() => pager.next(events.data?.next_cursor ?? null)} disabled={!events.data?.next_cursor || events.loading}>
                  Next
                </Button>
              </span>
            </>
          }
        />
      </Panel>
    </div>
  );
}

function CountList({ rows, empty }: { rows: { label: string; count: number }[]; empty: string }) {
  if (!rows.length) return <p className={styles.muted}>{empty}</p>;
  const max = Math.max(...rows.map((r) => r.count));
  return (
    <ul className={styles.bars}>
      {rows.map((r) => (
        <li key={r.label}>
          <span className={styles.clip} title={r.label}>
            {r.label}
          </span>
          <div className={styles.track}>
            <span style={{ width: `${(r.count / max) * 100}%` }} />
          </div>
          <strong>{formatNumber(r.count)}</strong>
        </li>
      ))}
    </ul>
  );
}

// ---- access ------------------------------------------------------------------------------------

function AccessTab() {
  const m = useApi((s) => securityApi.access(s), []);
  if (m.error) return <ErrorState error={m.error} onRetry={m.reload} />;
  if (!m.data) return <SkeletonText lines={10} />;
  const { roles, workspaces, agents, approvals } = m.data;
  const tick = (ok: boolean) => (ok ? <span className={styles.yes}>✓</span> : <span className={styles.no}>—</span>);
  return (
    <div className={styles.stack}>
      <Panel title="Workspace access by role" subtitle="Enforced by the API on every request (the menu only reflects it)" icon="Shield">
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Workspace</th>
              {roles.map((r) => (
                <th key={r.role} className={styles.center}>
                  {r.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {workspaces.map((w) => (
              <tr key={w.page}>
                <td>
                  {w.label} <code>{w.route}</code>
                </td>
                {roles.map((r) => (
                  <td key={r.role} className={styles.center}>
                    {tick(w.roles.includes(r.role))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Grid>
        <Panel title="Assistants and their tools" subtitle="Each assistant can only call these tools, and only for users whose role allows the matching workspace" icon="Sparkle">
          <ul className={styles.agents}>
            {agents.map((a) => (
              <li key={a.agent}>
                <div className={styles.checkHead}>
                  <strong>{a.name}</strong>
                  <span className={styles.muted}>{a.roles.join(", ")}</span>
                </div>
                <div className={styles.tools}>
                  {a.tools.map((t) => (
                    <code key={t} className={t.startsWith("propose_") ? styles.proposeTool : undefined}>
                      {t}
                    </code>
                  ))}
                </div>
              </li>
            ))}
          </ul>
          <p className={styles.muted}>Highlighted tools only create proposals; nothing runs until a person approves it.</p>
        </Panel>
        <Panel title="Who can approve agent actions" subtitle="Approval rights follow workspace access" icon="Check">
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Action</th>
                <th>Needs workspace</th>
                <th>Roles</th>
              </tr>
            </thead>
            <tbody>
              {approvals.map((a) => (
                <tr key={a.kind}>
                  <td>{a.label}</td>
                  <td>
                    <code>{a.requires_page}</code>
                  </td>
                  <td>{a.roles.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </Grid>
    </div>
  );
}

// ---- AI governance ------------------------------------------------------------------------------

function AiTab() {
  const g = useApi((s) => securityApi.ai(s), []);
  if (g.error) return <ErrorState error={g.error} onRetry={g.reload} />;
  if (!g.data) return <SkeletonText lines={10} />;
  const d = g.data;
  const queries = d.usage.reduce((a, u) => a + u.queries, 0);
  const fallbacks = d.usage.reduce((a, u) => a + u.fallbacks, 0);
  return (
    <div className={styles.stack}>
      <KpiGrid
        count={4}
        items={[
          { label: "Assistant questions", value: queries, format: (n) => formatNumber(n), icon: "Sparkle", hint: `Last ${d.window_days} days` },
          { label: "Rules fallbacks", value: fallbacks, format: (n) => formatNumber(n), icon: "Alert", tone: fallbacks ? "warn" : "neutral", hint: "AI engine unavailable" },
          { label: "Approval rate", value: d.approval_rate_pct ?? 0, format: (n) => (d.approval_rate_pct == null ? "—" : `${formatNumber(n, 0)}%`), icon: "Check", hint: "Of decided proposals" },
          { label: "Engine", value: 0, format: () => d.provider.split(" ")[0], icon: "Pulse", hint: d.provider },
        ]}
      />
      <Grid>
        <Panel title="Guardrails in force" subtitle="How the assistants are kept grounded and safe" icon="Shield">
          <ul className={styles.guardrails}>
            {d.guardrails.map((x) => (
              <li key={x}>
                <Icon.Check size={14} /> {x}
              </li>
            ))}
          </ul>
          <h4 className={styles.subhead}>Cost and safety caps</h4>
          <div className={styles.tools}>
            {Object.entries(d.caps).map(([k, v]) => (
              <code key={k}>
                {k.replace(/_/g, " ")}: {String(v)}
              </code>
            ))}
            <code>embeddings: {d.embeddings}</code>
          </div>
        </Panel>
        <Panel title="Usage by assistant" subtitle={`Last ${d.window_days} days`} icon="Users">
          {d.usage.length ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Assistant</th>
                  <th className={styles.num}>Questions</th>
                  <th className={styles.num}>Tool calls</th>
                  <th className={styles.num}>Fallbacks</th>
                  <th className={styles.num}>Avg time</th>
                </tr>
              </thead>
              <tbody>
                {d.usage.map((u) => (
                  <tr key={u.agent}>
                    <td>{u.agent}</td>
                    <td className={styles.num}>{formatNumber(u.queries)}</td>
                    <td className={styles.num}>{formatNumber(u.tool_calls)}</td>
                    <td className={styles.num}>{formatNumber(u.fallbacks)}</td>
                    <td className={styles.num}>{u.avg_latency_ms ? `${formatNumber(u.avg_latency_ms / 1000, 1)} s` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState title="No assistant questions yet" />
          )}
          <h4 className={styles.subhead}>Most-used tools</h4>
          <CountList rows={d.top_tools} empty="No tool calls recorded yet" />
        </Panel>
      </Grid>
      <Panel title="Agent proposals" subtitle="From chat assistants and the morning sweep" icon="Check">
        {d.proposals.length ? (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Action</th>
                <th>Status</th>
                <th className={styles.num}>Count</th>
              </tr>
            </thead>
            <tbody>
              {d.proposals.map((p) => (
                <tr key={`${p.kind}-${p.status}`}>
                  <td>{p.label}</td>
                  <td>
                    <Badge tone={p.status === "executed" ? "good" : p.status === "pending" ? "warn" : p.status === "failed" ? "bad" : "neutral"}>{p.status}</Badge>
                  </td>
                  <td className={styles.num}>{formatNumber(p.count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="No proposals yet" />
        )}
      </Panel>
    </div>
  );
}

// ---- knowledge base -----------------------------------------------------------------------------

const MODE_LABEL: Record<string, string> = { bm25: "Keyword (BM25)", dense: "Meaning (embeddings)", hybrid: "Hybrid (used by assistants)" };

function KnowledgeTab() {
  const lib = useApi((s) => knowledgeApi.library(s), []);
  const bench = useApi((s) => knowledgeApi.benchmark(s), []);
  const [query, setQuery] = useState("How cold does insulin need to be kept?");
  const [result, setResult] = useState<Awaited<ReturnType<typeof knowledgeApi.search>>>();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string>();
  const file = useRef<HTMLInputElement>(null);

  async function act(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    setError(undefined);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={styles.stack}>
      <Panel
        title="Search playground"
        subtitle="Compare keyword, meaning and hybrid search on the same question"
        icon="Sparkle"
        actions={lib.data && <Badge tone="info">{lib.data.dense_model}</Badge>}
      >
        <form
          className={styles.searchRow}
          onSubmit={(e) => {
            e.preventDefault();
            void act("search", async () => setResult(await knowledgeApi.search(query)));
          }}
        >
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ask about a policy…" aria-label="Search question" maxLength={500} />
          <Button variant="primary" type="submit" disabled={busy === "search" || query.trim().length < 2}>
            {busy === "search" ? "Searching…" : "Compare"}
          </Button>
        </form>
        <div className={styles.examples}>
          {["POL-IT-002", "Someone spilled a little blood on the bench", "Can a doctor start meropenem without asking anyone?", "What is the weather tomorrow?"].map((x) => (
            <button key={x} type="button" onClick={() => setQuery(x)}>
              {x}
            </button>
          ))}
        </div>
        {error && <p className={styles.error}>{error}</p>}
        {result && (
          <>
            <p className={styles.muted}>
              {result.identifier_query ? "Identifier or figure detected: hybrid leans on keyword matches." : "Everyday question: hybrid leans on meaning."}
            </p>
            <div className={styles.compare}>
              {(["bm25", "dense", "hybrid"] as const).map((m) => (
                <div key={m} className={m === "hybrid" ? styles.hybridCol : undefined}>
                  <h4>{MODE_LABEL[m]}</h4>
                  {(result.results[m] ?? []).length === 0 ? (
                    <p className={styles.abstain}>Nothing relevant found — the assistant would say the library does not cover this.</p>
                  ) : (
                    <ol>
                      {result.results[m].map((h: SearchHit, i) => (
                        <li key={i}>
                          <strong>
                            {h.policy_id || h.title} · {h.section}
                          </strong>
                          <span className={styles.muted}>{h.title}</span>
                          <p>{h.text.slice(0, 220)}…</p>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </Panel>

      <Panel
        title="Retrieval benchmark"
        subtitle={bench.data ? `${bench.data.questions} questions · ${bench.data.documents} documents · ${bench.data.dense_model} · run ${formatDate(bench.data.run_at)}` : "Keyword vs meaning vs hybrid"}
        icon="Pulse"
        actions={
          <Button onClick={() => act("bench", async () => { await knowledgeApi.runBenchmark(); bench.reload(); })} disabled={busy === "bench"}>
            {busy === "bench" ? "Running…" : "Run again"}
          </Button>
        }
      >
        {bench.error ? (
          <ErrorState error={bench.error} onRetry={bench.reload} />
        ) : !bench.data ? (
          <SkeletonText lines={5} />
        ) : (
          <>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Search</th>
                  <th className={styles.num}>Keyword questions</th>
                  <th className={styles.num}>Paraphrased</th>
                  <th className={styles.num}>Codes &amp; figures</th>
                  <th className={styles.num}>Off-topic refused</th>
                </tr>
              </thead>
              <tbody>
                {bench.data.modes.map((m) => (
                  <tr key={m.mode} className={m.mode === "hybrid" ? styles.hybridRow : undefined}>
                    <td>{MODE_LABEL[m.mode] ?? m.mode}</td>
                    <td className={styles.num}>{formatNumber(m.summary.keyword?.hit1_pct ?? 0, 0)}%</td>
                    <td className={styles.num}>{formatNumber(m.summary.paraphrase?.hit1_pct ?? 0, 0)}%</td>
                    <td className={styles.num}>{formatNumber(m.summary.exact?.hit1_pct ?? 0, 0)}%</td>
                    <td className={styles.num}>{formatNumber(m.summary.out_scope?.abstained_pct ?? 0, 0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className={styles.muted}>
              Share of questions where the right document is ranked first (hit@1); for off-topic questions, the share correctly answered with "nothing found". The questions were
              written alongside the documents and the hybrid weights were tuned on them, so treat these as an upper bound and add your own documents and questions to test further.
            </p>
          </>
        )}
      </Panel>

      <Panel
        title="Document library"
        subtitle={lib.data ? `${lib.data.documents.length} documents · ${lib.data.chunks} searchable sections` : "Policies and guidelines the assistants can cite"}
        icon="Clipboard"
        actions={
          <>
            <input ref={file} type="file" accept=".txt,.md" hidden onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void act("upload", async () => { await knowledgeApi.upload(f); lib.reload(); });
              e.target.value = "";
            }} />
            <Button variant="primary" onClick={() => file.current?.click()} disabled={busy === "upload"}>
              {busy === "upload" ? "Uploading…" : "Add document (.txt / .md)"}
            </Button>
          </>
        }
      >
        {lib.error ? (
          <ErrorState error={lib.error} onRetry={lib.reload} />
        ) : !lib.data ? (
          <SkeletonText lines={8} />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Document</th>
                <th>Code</th>
                <th>Category</th>
                <th className={styles.num}>Sections</th>
                <th className={styles.num}>Words</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {lib.data.documents.map((d) => (
                <tr key={d.doc_id}>
                  <td>
                    {d.title} {d.source === "uploaded" && <Badge tone="info">uploaded</Badge>}
                  </td>
                  <td>
                    <code>{d.policy_id || "—"}</code>
                  </td>
                  <td>{d.category}</td>
                  <td className={styles.num}>{d.sections}</td>
                  <td className={styles.num}>{formatNumber(d.words)}</td>
                  <td className={styles.num}>
                    {d.source === "uploaded" && (
                      <button type="button" className={styles.iconBtn} aria-label={`Remove ${d.title}`} onClick={() => act(`del-${d.doc_id}`, async () => { await knowledgeApi.remove(d.doc_id); lib.reload(); })}>
                        <Icon.Trash size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className={styles.muted}>Library documents are synthetic demo policies kept in version control; documents you add are stored in data/knowledge (not committed) and searchable immediately.</p>
      </Panel>
    </div>
  );
}
