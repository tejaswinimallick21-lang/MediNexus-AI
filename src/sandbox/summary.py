"""
Plain-English summary of an upload's cleaning, profile and model results.

Rule-based for now: every sentence is computed from the stored results, so nothing is invented.
(When ANTHROPIC_API_KEY is configured, the Nexa agents can phrase the same facts more fluently.)
"""

from typing import Any, Dict, List, Optional


def _n(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.4g}"


def summarise(manifest: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    cleaning: Dict[str, Any] = manifest.get("cleaning") or {}
    profile: Dict[str, Any] = manifest.get("profile") or {}
    q = cleaning.get("quality") or {}

    lin = manifest.get("lineage") or {}
    if manifest.get("kind") == "consolidated" and lin.get("steps") is not None:
        joined = [s["table"] for s in lin["steps"]]
        pit = [s["table"] for s in lin["steps"] if s.get("point_in_time")]
        out.append(
            f"{len(lin.get('sources', []))} tables were linked into one row per {lin.get('base')} ({_n(lin.get('rows', 0))} rows, {lin.get('columns')} columns): "
            + ", ".join(joined) + " joined" + (f"; {', '.join(pit)} counted point-in-time (no future rows)" if pit else "") + "."
        )
        out += list(lin.get("warnings", []))

    if cleaning:
        removed = cleaning.get("rows_in", 0) - cleaning.get("rows_out", 0)
        fixes = [s for s in cleaning.get("steps", []) if s.get("affected") and s["step"] not in ("Report missing values",)]
        out.append(
            f"{manifest.get('filename')} arrived with {_n(cleaning.get('rows_in', 0))} rows and {len(cleaning.get('columns', []))} usable columns; "
            f"quality score {q.get('overall', 0):.0f}/100 (completeness {q.get('completeness', 0):.0f}%, validity {q.get('validity', 0):.0f}%)."
        )
        if removed:
            out.append(f"Cleaning removed {_n(removed)} duplicate rows and made {len(fixes)} kinds of fixes.")
        pii = [c["name"] for c in cleaning.get("columns", []) if c.get("pii_masked")]
        if pii:
            out.append(f"Personal identifiers were pseudonymised before analysis: {', '.join(pii)}.")
        gappy = sorted((c for c in cleaning.get("columns", []) if c["missing_pct"] >= 20), key=lambda c: -c["missing_pct"])[:3]
        if gappy:
            out.append("Most incomplete columns: " + ", ".join(f"{c['name']} ({c['missing_pct']:.0f}% missing)" for c in gappy) + ".")

    corr = profile.get("correlations") or []
    if corr:
        c = corr[0]
        out.append(f"Strongest relationship: {c['a']} and {c['b']} move {'together' if c['rho'] > 0 else 'in opposite directions'} (Spearman ρ = {c['rho']:.2f}); correlation is not causation.")
    seg = profile.get("segments") or {}
    if seg.get("available"):
        biggest = seg["clusters"][0]
        out.append(
            f"The rows form {seg['k']} segments ({seg['structure']} separation, silhouette {seg['silhouette']:.2f}); the largest ({biggest['share_pct']:.0f}%) has "
            + "; ".join(biggest["traits"][:2]) + "."
        )
        if seg.get("anomaly_share_pct", 0) > 0:
            out.append(f"{seg['anomaly_share_pct']:.1f}% of rows look unusual compared with the rest and are worth a manual check.")
    drift = profile.get("drift") or {}
    if drift.get("available"):
        moved = [d for d in drift["columns"] if d["shift"] != "stable"]
        if moved:
            out.append(f"Compared with the live {drift['reference_table']} table, " + ", ".join(f"{d['column']} ({d['shift']} shift)" for d in moved[:3]) + " differ noticeably.")
        else:
            out.append(f"Shared columns match the live {drift['reference_table']} table closely (no material drift).")

    for p in (manifest.get("predictions") or {}).values():
        verdict = "beats" if p.get("beats_baseline") else "does not beat"
        drivers = ", ".join(d["feature"] for d in p.get("drivers", [])[:3])
        out.append(
            f"Predicting {p['target']}: the model scores {p['primary_metric']} {p['score']:.3g} vs {p['baseline_score']:.3g} for the baseline ({p['baseline_label']}), so it {verdict} the baseline"
            + (f"; top drivers are {drivers}." if drivers and p.get("beats_baseline") else ".")
        )
        if p.get("selected_model"):
            out.append(f"For {p['target']}, {p['selected_model'].lower()} was selected over the alternative on a validation slice of the training data.")
        for e in p.get("effects", [])[:3]:
            out.append(e["detail"])
        for w in p.get("timing_warnings", []):
            out.append("Check: " + w["note"])
        leaks = [e["column"] for e in p.get("excluded", []) if e["reason"].startswith(("suspected leakage", "name overlaps", "sibling outcome"))]
        if leaks:
            one = len(leaks) == 1
            out.append(f"{', '.join(leaks)} {'was' if one else 'were'} excluded as suspected leakage: {'it gives' if one else 'they give'} away {p['target']} rather than predict it.")

    f: Optional[Dict[str, Any]] = manifest.get("forecast")
    if f:
        change = (f["next_total"] - f["last_total"]) / f["last_total"] * 100 if f["last_total"] else 0.0
        method = "the model" if f["serving_method"] == "model" else "the seasonal baseline (it was more accurate in the backtest)"
        out.append(
            f"Forecast ({f['frequency']} {'row count' if not f['value_column'] else f['aggregation'] + ' of ' + f['value_column']}): the next {f['horizon']} periods total {_n(f['next_total'])}, "
            f"{change:+.0f}% vs the last {f['horizon']}; served by {method}."
        )
    return out
