"""
Self-contained HTML insights report for one sandbox (upload or consolidated table).

Every value is HTML-escaped; the report has no scripts or external resources, so it can be
opened offline, printed to PDF or attached to an email.
"""

from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional

CSS = """
:root{--ink:#0f172a;--muted:#5b6b82;--line:#e2e8f0;--soft:#f8fafc;--brand:#0284c7;--good:#047857;--goodbg:#ecfdf5;--warn:#b45309;--warnbg:#fffbeb;--bad:#b91c1c;--badbg:#fef2f2}
*{box-sizing:border-box}body{margin:0;background:#eef3f8;color:var(--ink);font:15px/1.6 Inter,Segoe UI,system-ui,sans-serif}
main{max-width:980px;margin:32px auto;background:#fff;border-radius:16px;box-shadow:0 10px 40px rgba(15,23,42,.08);overflow:hidden}
header{padding:36px 44px;background:linear-gradient(135deg,#0b1d3a,#050b18);color:#fff}
header small{color:#5eead4;font-weight:700;letter-spacing:1px;text-transform:uppercase;font-size:12px}
header h1{margin:6px 0 4px;font-size:28px;letter-spacing:-.02em}header p{margin:0;color:#b9c7da;font-size:13px}
section{padding:28px 44px;border-top:1px solid var(--line)}h2{margin:0 0 14px;font-size:19px}h3{margin:22px 0 8px;font-size:15px}
ul{margin:0;padding-left:20px}li{margin:4px 0}table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}
th{text-align:left;color:var(--muted);font-weight:600;border-bottom:2px solid var(--line);padding:8px 6px}td{border-bottom:1px solid var(--line);padding:7px 6px;vertical-align:top}
code{font:12px ui-monospace,Consolas,monospace;background:var(--soft);padding:1px 5px;border-radius:4px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.kpi{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.kpi span{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;font-weight:600}.kpi strong{font-size:22px}
.callout{border-radius:12px;padding:14px 16px;margin:10px 0}.good{background:var(--goodbg);color:var(--good)}.warn{background:var(--warnbg);color:var(--warn)}.bad{background:var(--badbg);color:var(--bad)}
.tag{display:inline-block;border-radius:999px;padding:1px 9px;font-size:12px;font-weight:600;background:var(--soft);border:1px solid var(--line)}
.muted{color:var(--muted);font-size:13px}footer{padding:20px 44px;background:var(--soft);color:var(--muted);font-size:12px}
@media print{body{background:#fff}main{box-shadow:none;margin:0}}
"""


def _e(v: Any) -> str:
    return escape("" if v is None else str(v))


def _n(v: Optional[float], d: int = 0) -> str:
    if v is None:
        return "—"
    return f"{v:,.{d}f}"


def _table(headers: List[str], rows: List[List[Any]]) -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _prediction(p: Dict[str, Any]) -> str:
    good = p.get("beats_baseline")
    dec = 2 if p["primary_metric"] == "MAE" else 3
    out = [f"<h3>Predicting <code>{_e(p['target'])}</code> · {_e(p['task'])}</h3>"]
    out.append(f"<div class='callout {'good' if good else 'warn'}'><strong>{_e(p['primary_metric'])} {_n(p['score'], dec)}</strong> vs "
               f"{_n(p['baseline_score'], dec)} for the baseline ({_e(p['baseline_label'])}). {_e(p['verdict'])}.</div>")
    facts = [f"Validation: {_e(p['split'])}.", f"{_n(p['train_rows'])} training rows, {_n(p['test_rows'])} test rows, {len(p.get('features_used', []))} features."]
    if p.get("selected_model"):
        comp = ", ".join(f"{_e(c['model'])} {_n(c.get('validation_score'), dec)}" for c in p.get("model_comparison", []))
        facts.append(f"Model selected on a validation slice of the training rows: <strong>{_e(p['selected_model'])}</strong> ({comp}). The test rows were used once, for the score above.")
    if p.get("positive_rate_pct") is not None:
        facts.append(f"Base rate of '{_e(p.get('positive_class'))}': {_n(p['positive_rate_pct'], 1)}%.")
    out.append("<ul>" + "".join(f"<li>{f}</li>" for f in facts) + "</ul>")
    if p.get("effects"):
        out.append("<h3>What drives the prediction</h3><ul>" + "".join(f"<li>{_e(e['detail'])}</li>" for e in p["effects"]) + "</ul>")
        out.append("<p class='muted'>These are associations the model learned from the data, not proof of cause and effect.</p>")
    elif p.get("drivers"):
        out.append("<h3>Most important columns</h3><ul>" + "".join(f"<li><code>{_e(d['feature'])}</code></li>" for d in p["drivers"]) + "</ul>")
    for w in p.get("timing_warnings", []):
        out.append(f"<div class='callout warn'>⚠ {_e(w['note'])}</div>")
    if p.get("excluded"):
        out.append("<h3>Columns left out, and why</h3>" + _table(["Column", "Reason"], [[f"<code>{_e(x['column'])}</code>", _e(x["reason"])] for x in p["excluded"]]))
    return "".join(out)


def render_report(m: Dict[str, Any]) -> str:
    c = m.get("cleaning") or {}
    q = c.get("quality") or {}
    prof = m.get("profile") or {}
    lin = m.get("lineage") or {}
    parts: List[str] = []

    parts.append(f"""<header><small>MediNexus AI · Insights report</small><h1>{_e(m['filename'])}</h1>
<p>Generated {datetime.now():%d %b %Y %H:%M} · sandbox {_e(m['upload_id'][:12])} · by {_e(m['uploaded_by'])} · not part of the live hospital data</p></header>""")

    parts.append("<section><h2>Key findings</h2><ul>" + "".join(f"<li>{_e(s)}</li>" for s in m.get("summary") or []) + "</ul></section>")

    if m.get("kind") == "consolidated" and lin:
        rows = [[_e(s["filename"]), _n(s["rows"])] for s in lin.get("sources", [])]
        steps = [[_e(s["table"]), _e(s["relation"]), f"<code>{_e(s['on'])}</code>", f"{_n(s['matched_pct'], 1)}%", _n(s["columns_added"]),
                  "yes" if s.get("point_in_time") else ("—" if s.get("point_in_time") is None else "no"), _e(s.get("note"))] for s in lin.get("steps", [])]
        warn = "".join(f"<div class='callout warn'>{_e(w)}</div>" for w in lin.get("warnings", []))
        parts.append(f"""<section><h2>How the tables were linked</h2>
<p>One row per row of <code>{_e(lin.get('base'))}</code>{f" (dated by <code>{_e(lin['base_date'])}</code>)" if lin.get('base_date') else ''}: {_n(lin.get('rows'))} rows × {_n(lin.get('columns'))} columns.</p>
{_table(['Source file', 'Rows'], rows)}{_table(['Table', 'Relation', 'Join', 'Matched', 'Columns', 'Point-in-time', 'Note'], steps)}{warn}
<p class="muted">Point-in-time: child rows are only counted when dated on or before the base row, so features never use information from the future.</p></section>""")

    if c:
        changed = [[_e(s["step"]), _n(s["affected"]), _e(s["detail"])] for s in c.get("steps", []) if s.get("affected")]
        pii = [x["name"] for x in c.get("columns", []) if x.get("pii_masked")]
        parts.append(f"""<section><h2>Data quality and cleaning</h2>
<div class="kpis"><div class="kpi"><span>Quality score</span><strong>{_n(q.get('overall'))}/100</strong></div>
<div class="kpi"><span>Rows in → out</span><strong>{_n(c.get('rows_in'))} → {_n(c.get('rows_out'))}</strong></div>
<div class="kpi"><span>Completeness</span><strong>{_n(q.get('completeness'), 1)}%</strong></div><div class="kpi"><span>Validity</span><strong>{_n(q.get('validity'), 1)}%</strong></div></div>
<h3>Changes made</h3>{_table(['Step', 'Affected', 'Detail'], changed) if changed else '<p class="muted">No changes were needed.</p>'}
<p class="muted">Personal identifiers pseudonymised: {_e(', '.join(pii) or 'none detected')}. Missing values are reported, not silently filled.</p></section>""")

    if prof:
        items = []
        for r in prof.get("correlations", [])[:5]:
            items.append(f"<code>{_e(r['a'])}</code> and <code>{_e(r['b'])}</code>: Spearman ρ = {_n(r['rho'], 2)}")
        seg = prof.get("segments") or {}
        if seg.get("available"):
            items.append(f"{seg['k']} segments ({_e(seg['structure'])} separation); {_n(seg.get('anomaly_share_pct'), 1)}% of rows look unusual.")
            items += [f"Segment {g['cluster']} ({_n(g['share_pct'])}%): {_e('; '.join(g['traits']))}" for g in seg.get("clusters", [])]
        drift = prof.get("drift") or {}
        if drift.get("available"):
            items += [f"vs live <code>{_e(drift['reference_table'])}</code>: <code>{_e(d['column'])}</code> {_e(d['shift'])} shift (PSI {_n(d['psi'], 2)})" for d in drift["columns"]]
        if items:
            parts.append("<section><h2>Patterns in the data</h2><ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul></section>")

    preds = list((m.get("predictions") or {}).values())
    if preds:
        parts.append("<section><h2>Predictions</h2>" + "".join(_prediction(p) for p in preds) + "</section>")

    f = m.get("forecast")
    if f:
        parts.append(f"""<section><h2>Forecast</h2><p>{_e(f['frequency'].capitalize())} {_e('row count' if not f.get('value_column') else f"{f['aggregation']} of {f['value_column']}")}
by <code>{_e(f['date_column'])}</code>: next {f['horizon']} periods total <strong>{_n(f['next_total'], 1)}</strong> (last {f['horizon']}: {_n(f['last_total'], 1)}).
Backtest error {_n(f['model_mae'], 2)} vs {_n(f['baseline_mae'], 2)} for the baseline ({_e(f['baseline_label'])}) over {f['backtest_folds']} folds;
the <strong>{'model' if f['serving_method'] == 'model' else 'baseline'}</strong> is served.</p></section>""")

    parts.append("""<section><h2>How to read this report</h2><ul>
<li>Every number is computed from the uploaded data in an isolated sandbox; nothing here changed the live hospital data.</li>
<li>Models are always compared with a simple baseline on rows they never saw. A model that does not beat the baseline is reported as such.</li>
<li>Drivers and effects are associations learned by the model, not causes. Check timing warnings before acting on a prediction.</li>
<li>Decision support only: a qualified person should review findings before they change care or operations.</li></ul></section>""")
    parts.append("<footer>MediNexus AI · Data Engineering sandbox report</footer>")
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Insights report · {_e(m['filename'])}</title><style>{CSS}</style></head><body><main>{''.join(parts)}</main></body></html>"
