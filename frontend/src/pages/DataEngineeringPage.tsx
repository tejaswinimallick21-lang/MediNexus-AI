import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";

import { ApiError } from "../api/client";
import { dataApi } from "../api/dataPlatform";
import type { Forecast, Prediction, Profile, UploadDetail, UploadSummary } from "../api/schemas/dataPlatform";
import { AreaTrend } from "../components/Charts";
import { Badge, Button, SelectField } from "../components/Controls";
import { DataTable, type Column } from "../components/DataTable";
import { Icon } from "../components/Icons";
import { PageHeader, Panel } from "../components/Panel";
import { Skeleton, SkeletonText } from "../components/Skeleton";
import { EmptyState, ErrorState } from "../components/StateViews";
import { Tabs } from "../components/Tabs";
import { useApi } from "../hooks/useApi";
import { useJob } from "../hooks/useJob";
import { formatCompact, formatDate, formatNumber, formatPercent } from "../lib/format";
import styles from "./DataEngineeringPage.module.css";

const ACCEPT = ".csv,.parquet,.json,.jsonl,.ndjson";
const MAX_MB = 50;

function formatBytes(n: number): string {
  return n >= 1024 * 1024 ? `${formatNumber(n / 1024 / 1024, 1)} MB` : `${formatNumber(n / 1024, 0)} KB`;
}

export function DataEngineeringPage() {
  const uploads = useApi((s) => dataApi.uploads({ limit: 50 }, s), []);
  const [selected, setSelected] = useState<string | null>(null);
  const items = uploads.data?.items;

  useEffect(() => {
    if (!selected && items?.length) setSelected(items[0].upload_id);
  }, [items, selected]);

  return (
    <div>
      <PageHeader
        eyebrow="Platform administrator"
        title="Data Engineering"
        subtitle="Upload a dataset and watch it move through Bronze → Silver → Gold, then get ML insights. Each upload runs in its own sandbox."
      />
      <div className={styles.top}>
        <UploadPanel
          onUploaded={(id) => {
            setSelected(id);
            uploads.reload();
          }}
        />
        <Panel title="Upload sandboxes" subtitle="Most recent first" icon="Database">
          {uploads.error ? (
            <ErrorState error={uploads.error} onRetry={uploads.reload} />
          ) : !items ? (
            <SkeletonText lines={5} />
          ) : items.length === 0 ? (
            <EmptyState title="No uploads yet" hint="Drop a CSV, Parquet or JSON file to start." />
          ) : (
            <ul className={styles.uploadList}>
              {items.map((u) => (
                <li key={u.upload_id}>
                  <button type="button" className={u.upload_id === selected ? styles.uploadOn : ""} onClick={() => setSelected(u.upload_id)}>
                    <span className={styles.fileIcon}>
                      <Icon.Database size={16} />
                    </span>
                    <span className={styles.uploadText}>
                      <strong title={u.filename}>{u.filename}</strong>
                      <span>
                        {formatDate(u.created_at)} · {formatBytes(u.size_bytes)}
                        {u.rows != null && ` · ${formatNumber(u.rows)} rows`}
                      </span>
                    </span>
                    <StatusBadge u={u} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {selected ? (
        <UploadView
          key={selected}
          uploadId={selected}
          onChanged={uploads.reload}
          onDeleted={() => {
            setSelected(null);
            uploads.reload();
          }}
        />
      ) : null}
    </div>
  );
}

function StatusBadge({ u }: { u: UploadSummary }) {
  if (u.status === "ready") return <Badge tone="good">{u.quality_score != null ? `Quality ${formatNumber(u.quality_score, 0)}` : "Ready"}</Badge>;
  if (u.status === "failed") return <Badge tone="bad">Failed</Badge>;
  return <Badge tone="info">Processing</Badge>;
}

// ---- Upload --------------------------------------------------------------------------------

const MAX_FILES = 20;

type Staged = { file: File; state: "waiting" | "uploading" | "done" | "error"; message?: string };

function UploadPanel({ onUploaded }: { onUploaded: (id: string) => void }) {
  const [staged, setStaged] = useState<Staged[]>([]);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const input = useRef<HTMLInputElement>(null);

  /** Adds files to the queue; each one becomes its own sandbox. */
  function pick(list: FileList | null | undefined) {
    setError(undefined);
    if (!list?.length) return;
    const rejected: string[] = [];
    const next: Staged[] = [];
    for (const f of Array.from(list)) {
      const ext = f.name.toLowerCase().split(".").pop() ?? "";
      if (!["csv", "parquet", "json", "jsonl", "ndjson"].includes(ext)) rejected.push(`${f.name} (type)`);
      else if (f.size > MAX_MB * 1024 * 1024) rejected.push(`${f.name} (over ${MAX_MB} MB)`);
      else next.push({ file: f, state: "waiting" });
    }
    setStaged((s) => {
      const keep = s.filter((x) => x.state !== "done");
      const names = new Set(keep.map((x) => x.file.name + x.file.size));
      const merged = [...keep, ...next.filter((x) => !names.has(x.file.name + x.file.size))];
      if (merged.length > MAX_FILES) setError(`Up to ${MAX_FILES} files at a time.`);
      return merged.slice(0, MAX_FILES);
    });
    if (rejected.length) setError(`Skipped: ${rejected.join(", ")}. Use .csv, .parquet or .json up to ${MAX_MB} MB.`);
    if (input.current) input.current.value = "";
  }

  async function submit() {
    setBusy(true);
    setError(undefined);
    let first: string | null = null;
    for (let i = 0; i < staged.length; i++) {
      if (staged[i].state === "done") continue;
      setStaged((s) => s.map((x, j) => (j === i ? { ...x, state: "uploading", message: undefined } : x)));
      try {
        const res = await dataApi.upload(staged[i].file);
        first ??= res.upload.upload_id;
        setStaged((s) => s.map((x, j) => (j === i ? { ...x, state: "done" } : x)));
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : "Upload failed.";
        setStaged((s) => s.map((x, j) => (j === i ? { ...x, state: "error", message } : x)));
      }
    }
    setBusy(false);
    if (first) onUploaded(first);
  }

  const pending = staged.filter((s) => s.state !== "done").length;
  return (
    <Panel title="Upload datasets" subtitle={`CSV, Parquet or JSON · up to ${MAX_FILES} files · ${MAX_MB} MB each`} icon="Sparkle">
      <div
        className={`${styles.drop} ${drag ? styles.dropOn : ""}`}
        onDragOver={(e: DragEvent) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e: DragEvent) => {
          e.preventDefault();
          setDrag(false);
          pick(e.dataTransfer.files);
        }}
        onClick={() => input.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        aria-label="Choose files to upload"
      >
        <input ref={input} type="file" accept={ACCEPT} multiple hidden onChange={(e) => pick(e.target.files)} />
        <span className={styles.dropIcon}>
          <Icon.Database size={26} />
        </span>
        <strong>Drop files here or click to browse</strong>
        <span>Select several tables at once (Ctrl/Shift-click) · each file gets its own sandbox</span>
      </div>

      {staged.length > 0 && (
        <ul className={styles.staged}>
          {staged.map((s, i) => (
            <li key={s.file.name + s.file.size} className={styles[`staged_${s.state}`]}>
              <span className={styles.stagedName} title={s.file.name}>
                {s.file.name}
              </span>
              <span className={styles.stagedMeta}>{s.message ?? formatBytes(s.file.size)}</span>
              {s.state === "waiting" || s.state === "error" ? (
                <button type="button" aria-label={`Remove ${s.file.name}`} onClick={() => setStaged((x) => x.filter((_, j) => j !== i))} disabled={busy}>
                  <Icon.Close size={14} />
                </button>
              ) : s.state === "uploading" ? (
                <Badge tone="info">Uploading</Badge>
              ) : (
                <Badge tone="good">Uploaded</Badge>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <p className={styles.error}>{error}</p>}
      <div className={styles.uploadActions}>
        <Button variant="primary" onClick={submit} disabled={!pending || busy}>
          {busy ? "Uploading…" : pending > 1 ? `Upload and process ${pending} files` : "Upload and process"}
        </Button>
        {staged.length > 0 && (
          <Button variant="ghost" onClick={() => setStaged([])} disabled={busy}>
            Clear
          </Button>
        )}
      </div>
      <p className={styles.sandboxNote}>
        <Icon.Shield size={14} /> Sandboxed: uploads never change live lakehouse data. Personal identifiers are pseudonymised during cleaning.
      </p>
    </Panel>
  );
}

// ---- One upload -----------------------------------------------------------------------------

type TabId = "cleaning" | "profile" | "predict" | "forecast" | "summary";
const TABS: { id: TabId; label: string }[] = [
  { id: "cleaning", label: "Cleaning report" },
  { id: "profile", label: "Data profile" },
  { id: "predict", label: "Predict a column" },
  { id: "forecast", label: "Forecast" },
  { id: "summary", label: "Summary" },
];

function UploadView({ uploadId, onChanged, onDeleted }: { uploadId: string; onChanged: () => void; onDeleted: () => void }) {
  const detail = useApi((s) => dataApi.detail(uploadId, s), [uploadId]);
  const [tab, setTab] = useState<TabId>("cleaning");
  const [confirm, setConfirm] = useState(false);
  const d = detail.data;
  const reload = detail.reload;
  const job = useJob(
    d?.job_id,
    useCallback(() => {
      reload();
      onChanged();
    }, [reload, onChanged]),
  );

  if (detail.error) return <ErrorState error={detail.error} onRetry={detail.reload} />;
  if (!d) return <SkeletonText lines={10} />;

  const processing = d.status === "processing";
  return (
    <section className={styles.view} aria-label={`Upload ${d.filename}`}>
      <div className={styles.viewHead}>
        <div>
          <h2>{d.filename}</h2>
          <p>
            Uploaded {formatDate(d.created_at)} by {d.uploaded_by} · {formatBytes(d.size_bytes)} · SHA-256 <code>{d.sha256.slice(0, 12)}…</code>
          </p>
        </div>
        <div className={styles.viewActions}>
          {d.status === "ready" && (
            <a className={styles.download} href={dataApi.cleanCsvUrl(d.upload_id)} download>
              <Icon.Arrow size={14} style={{ transform: "rotate(90deg)" }} /> Download clean CSV
            </a>
          )}
          {confirm ? (
            <span className={styles.confirm}>
              Delete this sandbox?
              <Button
                variant="primary"
                onClick={async () => {
                  await dataApi.remove(d.upload_id);
                  onDeleted();
                }}
              >
                Delete
              </Button>
              <Button variant="ghost" onClick={() => setConfirm(false)}>
                Cancel
              </Button>
            </span>
          ) : (
            <Button variant="ghost" onClick={() => setConfirm(true)} disabled={processing}>
              <Icon.Trash size={14} /> Delete
            </Button>
          )}
        </div>
      </div>

      <MedallionStepper d={d} progress={job?.progress_pct} />

      {processing && (
        <Panel title="Processing" subtitle={job?.stage ?? d.stage} icon="Pulse">
          <div className={styles.progress} role="progressbar" aria-valuenow={job?.progress_pct ?? 0} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${job?.progress_pct ?? 5}%` }} />
          </div>
          <pre className={styles.log}>{(job?.logs ?? []).join("\n") || "Queued…"}</pre>
        </Panel>
      )}
      {d.status === "failed" && (
        <Panel title="Processing failed" icon="Alert">
          <p className={styles.error}>{d.error ?? "The file could not be processed."}</p>
        </Panel>
      )}

      {d.status === "ready" && d.cleaning && (
        <>
          <Tabs tabs={TABS} value={tab} onChange={setTab} />
          {tab === "cleaning" && <CleaningTab d={d} />}
          {tab === "profile" && d.profile && <ProfileTab p={d.profile} />}
          {tab === "predict" && <PredictTab d={d} busy={!!d.job_id} job={job} onStarted={reload} />}
          {tab === "forecast" && <ForecastTab d={d} busy={!!d.job_id} job={job} onStarted={reload} />}
          {tab === "summary" && <SummaryTab d={d} />}
        </>
      )}
    </section>
  );
}

function MedallionStepper({ d, progress }: { d: UploadDetail; progress?: number }) {
  const c = d.cleaning;
  const pct = d.status === "ready" ? 100 : progress ?? 0;
  const stages = [
    { name: "Bronze", what: "Raw file preserved", value: formatBytes(d.size_bytes), done: pct >= 10 },
    { name: "Silver", what: "Cleaned & validated", value: c ? `${formatNumber(c.rows_out)} rows` : "—", done: pct >= 55 },
    { name: "Gold", what: "Analysis-ready", value: c ? `${c.columns.length} columns` : "—", done: pct >= 70 },
    { name: "Insights", what: "Profile & ML", value: d.quality_score != null ? `Quality ${formatNumber(d.quality_score, 0)}/100` : "—", done: d.status === "ready" },
  ];
  return (
    <ol className={styles.stepper} aria-label="Medallion stages">
      {stages.map((s, i) => (
        <li key={s.name} className={`${styles.stage} ${styles[`stage${s.name}`]} ${s.done ? styles.stageDone : ""} ${d.status === "failed" && !s.done ? styles.stageFailed : ""}`}>
          <span className={styles.stageNum}>{s.done ? <Icon.Check size={14} /> : i + 1}</span>
          <span className={styles.stageName}>{s.name}</span>
          <span className={styles.stageWhat}>{s.what}</span>
          <strong>{s.value}</strong>
        </li>
      ))}
    </ol>
  );
}

// ---- Cleaning -------------------------------------------------------------------------------

const KIND_TONE: Record<string, "good" | "info" | "warn" | "neutral" | "bad"> = {
  numeric: "info",
  datetime: "good",
  category: "neutral",
  boolean: "neutral",
  identifier: "warn",
  text: "neutral",
};

function CleaningTab({ d }: { d: UploadDetail }) {
  const c = d.cleaning!;
  const q = c.quality;
  const cols: Column<(typeof c.columns)[number]>[] = [
    { key: "name", header: "Column", render: (r) => <code>{r.name}</code> },
    { key: "kind", header: "Type", render: (r) => <Badge tone={KIND_TONE[r.kind] ?? "neutral"}>{r.kind}</Badge> },
    { key: "missing", header: "Missing", numeric: true, render: (r) => formatPercent(r.missing_pct) },
    { key: "unique", header: "Distinct", numeric: true, render: (r) => formatNumber(r.unique) },
    { key: "pii", header: "Privacy", render: (r) => (r.pii_masked ? <Badge tone="warn">Pseudonymised</Badge> : "—") },
    { key: "example", header: "Example", render: (r) => <span className={styles.example}>{r.example ?? "—"}</span> },
  ];
  return (
    <div className={styles.stack}>
      <div className={styles.qualityRow}>
        <div className={styles.scoreRing} style={{ ["--score" as string]: `${q.overall}` }}>
          <strong>{formatNumber(q.overall, 0)}</strong>
          <span>quality score</span>
        </div>
        {(
          [
            ["Completeness", q.completeness, "Share of cells with a value"],
            ["Validity", q.validity, "Values that parsed and passed range checks"],
            ["Uniqueness", q.uniqueness, "Rows that were not exact duplicates"],
            ["Consistency", q.consistency, "Values already in a standard spelling"],
          ] as const
        ).map(([label, v, hint]) => (
          <div key={label} className={styles.subScore}>
            <span>{label}</span>
            <strong>{formatPercent(v)}</strong>
            <div className={styles.bar}>
              <span style={{ width: `${v}%` }} />
            </div>
            <em>{hint}</em>
          </div>
        ))}
      </div>

      <Panel title="What cleaning changed" subtitle={`${formatNumber(c.rows_in)} rows in → ${formatNumber(c.rows_out)} rows out`} icon="Check">
        <ol className={styles.steps}>
          {c.steps.map((s) => (
            <li key={s.step} className={s.affected ? styles.stepChanged : ""}>
              <span className={styles.stepCount}>{formatCompact(s.affected)}</span>
              <div>
                <strong>{s.step}</strong>
                <span>
                  {s.detail}
                  {s.note ? ` · ${s.note}` : ""}
                </span>
              </div>
            </li>
          ))}
        </ol>
      </Panel>

      <Panel title="Gold schema" subtitle="Inferred type, completeness and privacy treatment per column" icon="Database">
        <DataTable columns={cols} rows={c.columns} rowKey={(r) => r.name} caption="Columns" />
      </Panel>

      <Panel title="Preview" subtitle={`First ${d.preview_rows.length} rows of the cleaned table`} icon="Clipboard">
        <div className={styles.previewWrap}>
          <table className={styles.preview}>
            <thead>
              <tr>
                {d.preview_columns.map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.preview_rows.map((r, i) => (
                <tr key={i}>
                  {r.map((v, j) => (
                    <td key={j} className={v == null ? styles.nullCell : ""}>
                      {v ?? "∅"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

// ---- Profile --------------------------------------------------------------------------------

function ProfileTab({ p }: { p: Profile }) {
  const seg = p.segments;
  return (
    <div className={styles.stack}>
      {p.numeric.length > 0 && (
        <Panel title="Numeric distributions" subtitle="Median, spread and extreme outliers (beyond 3 × IQR)" icon="Pulse">
          <div className={styles.histGrid}>
            {p.numeric.map((n) => (
              <div key={n.column} className={styles.hist}>
                <div className={styles.histHead}>
                  <code>{n.column}</code>
                  {n.extreme_outliers > 0 && <Badge tone="warn">{formatNumber(n.extreme_outliers)} outliers</Badge>}
                </div>
                <ResponsiveContainer width="100%" height={90}>
                  <BarChart data={n.histogram} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                    <XAxis dataKey="bin" hide />
                    <Tooltip cursor={{ fill: "rgba(2,132,199,0.06)" }} contentStyle={{ fontSize: 12 }} />
                    <Bar dataKey="count" fill="#0ea5e9" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
                <div className={styles.histStats}>
                  <span>min {formatCompact(n.min)}</span>
                  <span>median {formatCompact(n.median)}</span>
                  <span>max {formatCompact(n.max)}</span>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <div className={styles.twoCol}>
        <Panel title="Segments" subtitle="Natural groups in the numeric columns (k-means, k chosen by silhouette)" icon="Users">
          {seg.available ? (
            <>
              <p className={styles.muted}>
                {seg.k} segments · {seg.structure} separation (silhouette {formatNumber(seg.silhouette, 2)}) · {formatNumber(seg.rows_used)} rows analysed
              </p>
              <ul className={styles.segments}>
                {seg.clusters.map((c) => (
                  <li key={c.cluster}>
                    <div className={styles.segHead}>
                      <strong>Segment {c.cluster}</strong>
                      <span>{formatPercent(c.share_pct, 0)}</span>
                    </div>
                    <div className={styles.bar}>
                      <span style={{ width: `${c.share_pct}%` }} />
                    </div>
                    <span className={styles.muted}>{c.traits.join(" · ")}</span>
                  </li>
                ))}
              </ul>
              <p className={styles.anomaly}>
                <Icon.Alert size={14} /> {formatPercent(seg.anomaly_share_pct ?? 0, 1)} of rows ({formatNumber(seg.anomalies)}) look unusual (isolation forest) and are worth a manual check.
              </p>
            </>
          ) : (
            <EmptyState title="Segments not available" hint={seg.reason ?? undefined} />
          )}
        </Panel>

        <Panel title="Relationships" subtitle="Strongest Spearman correlations between numeric columns" icon="Sparkle">
          {p.correlations.length ? (
            <ul className={styles.corr}>
              {p.correlations.map((c) => (
                <li key={`${c.a}-${c.b}`}>
                  <span>
                    <code>{c.a}</code> ↔ <code>{c.b}</code>
                  </span>
                  <Badge tone={Math.abs(c.rho) >= 0.7 ? "warn" : "info"}>ρ {formatNumber(c.rho, 2)}</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No notable correlations" hint="No pair of numeric columns has |ρ| ≥ 0.2." />
          )}
          <p className={styles.muted}>Correlation is not causation.</p>
        </Panel>
      </div>

      <div className={styles.twoCol}>
        <Panel title="Top categories" subtitle="Most frequent values per categorical column" icon="Clipboard">
          {p.categories.length ? (
            <div className={styles.catGrid}>
              {p.categories.slice(0, 6).map((c) => (
                <div key={c.column}>
                  <div className={styles.histHead}>
                    <code>{c.column}</code>
                    <span className={styles.muted}>{formatNumber(c.distinct)} values</span>
                  </div>
                  <ul className={styles.catList}>
                    {c.top.slice(0, 5).map((v) => (
                      <li key={v.value}>
                        <span title={v.value}>{v.value}</span>
                        <div className={styles.bar}>
                          <span style={{ width: `${v.share_pct}%` }} />
                        </div>
                        <em>{formatPercent(v.share_pct, 0)}</em>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No categorical columns" />
          )}
        </Panel>

        <Panel title="Compared with the live lakehouse" subtitle="Population stability index (PSI) on shared columns" icon="Shield">
          {p.drift.available ? (
            <>
              <p className={styles.muted}>
                Closest live table: <code>{p.drift.reference_table}</code>
              </p>
              <ul className={styles.corr}>
                {p.drift.columns.map((c) => (
                  <li key={c.column}>
                    <span>
                      <code>{c.column}</code> median {formatCompact(c.upload_median)} vs {formatCompact(c.lakehouse_median)}
                    </span>
                    <Badge tone={c.shift === "stable" ? "good" : c.shift === "moderate" ? "warn" : "bad"}>
                      {c.shift} · PSI {formatNumber(c.psi, 2)}
                    </Badge>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <EmptyState title="No comparison" hint={p.drift.reason ?? undefined} />
          )}
        </Panel>
      </div>
    </div>
  );
}

// ---- Predict ---------------------------------------------------------------------------------

type JobState = ReturnType<typeof useJob>;

function PredictTab({ d, busy, job, onStarted }: { d: UploadDetail; busy: boolean; job: JobState; onStarted: () => void }) {
  const targets = useMemo(() => (d.cleaning?.columns ?? []).filter((c) => ["numeric", "category", "boolean"].includes(c.kind) && !c.pii_masked), [d.cleaning]);
  const [target, setTarget] = useState(d.predictions[0]?.target ?? targets[0]?.name ?? "");
  const [error, setError] = useState<string>();
  const shown = d.predictions.find((p) => p.target === target) ?? d.predictions[0];

  async function run() {
    setError(undefined);
    try {
      await dataApi.predict(d.upload_id, target);
      onStarted();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not start training.");
    }
  }

  return (
    <div className={styles.stack}>
      <Panel title="Predict a column" subtitle="Trains a gradient-boosting model and compares it with a simple baseline on held-out rows" icon="Radar">
        <div className={styles.formRow}>
          <SelectField id="pred-target" label="Column to predict" value={target} onChange={setTarget} options={targets.map((c) => ({ value: c.name, label: `${c.name} (${c.kind})` }))} />
          <Button variant="primary" onClick={run} disabled={busy || !target}>
            {busy ? "Running…" : "Train and evaluate"}
          </Button>
        </div>
        {busy && job && <p className={styles.muted}>{job.stage} · {job.progress_pct}%</p>}
        {job?.status === "failed" && job.error && <p className={styles.error}>{job.error}</p>}
        {error && <p className={styles.error}>{error}</p>}
        <p className={styles.muted}>
          Identifiers, pseudonymised columns and any column that alone predicts the target almost perfectly (likely leakage) are excluded automatically.
        </p>
      </Panel>
      {shown ? <PredictionResult p={shown} /> : !busy && <EmptyState title="No model trained yet" hint="Pick a column and train." />}
    </div>
  );
}

function PredictionResult({ p }: { p: Prediction }) {
  const max = Math.max(...p.drivers.map((x) => x.importance), 1e-9);
  return (
    <div className={styles.twoCol}>
      <Panel title={`Predicting ${p.target}`} subtitle={`${p.task} · ${formatNumber(p.train_rows)} train / ${formatNumber(p.test_rows)} test rows`} icon="Radar">
        <div className={`${styles.verdict} ${p.beats_baseline ? styles.verdictGood : styles.verdictWarn}`}>
          <span>{p.primary_metric}</span>
          <strong>
            {formatNumber(p.score, p.primary_metric === "MAE" ? 2 : 3)} <em>vs {formatNumber(p.baseline_score, p.primary_metric === "MAE" ? 2 : 3)} baseline</em>
          </strong>
          <p>{p.verdict}</p>
        </div>
        <dl className={styles.dl}>
          <dt>Baseline</dt>
          <dd>{p.baseline_label}</dd>
          <dt>Validation</dt>
          <dd>{p.split}</dd>
          {p.accuracy != null && (
            <>
              <dt>Accuracy</dt>
              <dd>
                {formatPercent(p.accuracy * 100)} (baseline {formatPercent((p.baseline_accuracy ?? 0) * 100)})
              </dd>
            </>
          )}
          {p.r2 != null && (
            <>
              <dt>R²</dt>
              <dd>{formatNumber(p.r2, 3)}</dd>
            </>
          )}
          <dt>Features used</dt>
          <dd>{p.features_used.length}</dd>
        </dl>
        <h4 className={styles.subhead}>Top drivers (permutation importance on test rows)</h4>
        {p.drivers.length ? (
          <ul className={styles.drivers}>
            {p.drivers.map((x) => (
              <li key={x.feature}>
                <code>{x.feature}</code>
                <div className={styles.bar}>
                  <span style={{ width: `${(x.importance / max) * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.muted}>No feature improved on random shuffling.</p>
        )}
      </Panel>
      <Panel title="Excluded columns" subtitle="Kept out of the model, and why" icon="Shield">
        <ul className={styles.excluded}>
          {p.excluded.map((e) => (
            <li key={e.column} className={e.reason.startsWith("suspected leakage") ? styles.leak : ""}>
              <code>{e.column}</code>
              <span>{e.reason}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

// ---- Forecast -------------------------------------------------------------------------------

function ForecastTab({ d, busy, job, onStarted }: { d: UploadDetail; busy: boolean; job: JobState; onStarted: () => void }) {
  const cols = d.cleaning?.columns ?? [];
  const dates = cols.filter((c) => c.kind === "datetime");
  const values = cols.filter((c) => c.kind === "numeric");
  const [dateCol, setDateCol] = useState(d.forecast?.date_column ?? dates[0]?.name ?? "");
  const [valueCol, setValueCol] = useState(d.forecast?.value_column ?? "");
  const [agg, setAgg] = useState<"sum" | "mean">("sum");
  const [error, setError] = useState<string>();

  if (!dates.length) return <EmptyState title="No date column" hint="Forecasting needs a column of dates (e.g. admission or order date)." />;

  async function run() {
    setError(undefined);
    try {
      await dataApi.forecast(d.upload_id, { date_column: dateCol, value_column: valueCol || null, aggregation: agg });
      onStarted();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not start the forecast.");
    }
  }

  return (
    <div className={styles.stack}>
      <Panel title="Forecast over time" subtitle="Backtested against a seasonal-naive baseline; the more accurate method is served" icon="Pulse">
        <div className={styles.formRow}>
          <SelectField id="fc-date" label="Date column" value={dateCol} onChange={setDateCol} options={dates.map((c) => ({ value: c.name, label: c.name }))} />
          <SelectField
            id="fc-value"
            label="What to forecast"
            value={valueCol}
            onChange={setValueCol}
            options={[{ value: "", label: "Number of rows per period" }, ...values.map((c) => ({ value: c.name, label: c.name }))]}
          />
          {valueCol && (
            <SelectField id="fc-agg" label="Aggregate" value={agg} onChange={(v) => setAgg(v as "sum" | "mean")} options={[{ value: "sum", label: "Sum" }, { value: "mean", label: "Average" }]} />
          )}
          <Button variant="primary" onClick={run} disabled={busy || !dateCol}>
            {busy ? "Running…" : "Run forecast"}
          </Button>
        </div>
        {busy && job && <p className={styles.muted}>{job.stage} · {job.progress_pct}%</p>}
        {job?.status === "failed" && job.error && <p className={styles.error}>{job.error}</p>}
        {error && <p className={styles.error}>{error}</p>}
      </Panel>
      {d.forecast ? <ForecastResult f={d.forecast} /> : !busy && <EmptyState title="No forecast yet" hint="Choose a date column and run." />}
    </div>
  );
}

function ForecastResult({ f }: { f: Forecast }) {
  const data = [
    ...f.history.map((h) => ({ date: h.date, actual: h.value, forecast: null as number | null })),
    ...f.forecast.map((p) => ({ date: p.date, actual: null as number | null, forecast: p.value })),
  ];
  const change = f.last_total ? ((f.next_total - f.last_total) / f.last_total) * 100 : 0;
  return (
    <Panel
      title={`${f.frequency === "daily" ? "Daily" : "Weekly"} ${f.value_column ? `${f.aggregation} of ${f.value_column}` : "row count"}`}
      subtitle={`Next ${f.horizon} ${f.frequency === "daily" ? "days" : "weeks"} · ${f.history_points} periods of history`}
      icon="Pulse"
      actions={<Badge tone={f.serving_method === "model" ? "good" : "warn"}>{f.serving_method === "model" ? "Model served" : "Baseline served"}</Badge>}
    >
      <AreaTrend
        data={data}
        x="date"
        series={[
          { key: "actual", name: "Actual" },
          { key: "forecast", name: "Forecast" },
        ]}
        height={260}
        xFormatter={(v) => formatDate(v).slice(0, 6)}
      />
      <div className={styles.fcStats}>
        <div>
          <span>Next {f.horizon} total</span>
          <strong>{formatCompact(f.next_total)}</strong>
          <em>
            {change >= 0 ? "+" : ""}
            {formatNumber(change, 0)}% vs last {f.horizon}
          </em>
        </div>
        <div>
          <span>Backtest error (MAE)</span>
          <strong>{formatCompact(f.model_mae)}</strong>
          <em>
            baseline {formatCompact(f.baseline_mae)} ({f.baseline_label})
          </em>
        </div>
        <div>
          <span>Skill vs baseline</span>
          <strong>{formatNumber(f.skill_pct, 1)}%</strong>
          <em>{f.backtest_folds} rolling-origin folds</em>
        </div>
      </div>
    </Panel>
  );
}

// ---- Summary -------------------------------------------------------------------------------

function SummaryTab({ d }: { d: UploadDetail }) {
  return (
    <Panel title="Plain-English summary" subtitle="Every sentence is computed from the results above" icon="Sparkle">
      {d.summary.length ? (
        <ul className={styles.summary}>
          {d.summary.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      ) : (
        <Skeleton height={60} />
      )}
      <p className={styles.muted}>Run a prediction or forecast to add their findings here.</p>
    </Panel>
  );
}
