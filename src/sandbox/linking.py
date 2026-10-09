"""
Link several cleaned tables and consolidate them into one analytical table at a chosen grain.

Discovery: a relationship A.a → B.b is proposed when the values of A.a are (mostly) contained in
B.b and B.b is unique in B (so B is the "one" side). Matching column names raise confidence; the
values decide.

Consolidation, starting from the base table (one output row per base row):
- many-to-one / one-to-one parents are joined on (their columns prefixed `table__`), up to two hops;
- one-to-many children are aggregated per base row (row count, numeric sum/mean/max, top-category
  counts). When the child and the base both have dates, only child rows dated on or before the base
  row's date are counted (point-in-time), so features never use information from the future.
"""

import re
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

MIN_CONTAINMENT = 0.5
UNIQUE_RATIO = 0.99
MAX_NUMERIC_AGG = 8
MAX_CATEGORY_LEVELS = 30
TOP_LEVELS = 5
MAX_PIT_ROWS = 5_000_000  # above this a point-in-time merge is too large; aggregate without it and warn

Table = Dict[str, Any]  # {"name", "df", "kinds", "upload_id"}


def table_name(filename: str, taken: set) -> str:
    stem = re.sub(r"[^0-9a-z]+", "_", filename.lower().rsplit(".", 1)[0]).strip("_") or "table"
    name, i = stem, 2
    while name in taken:
        name, i = f"{stem}_{i}", i + 1
    return name


def _singular(name: str) -> str:
    return name[:-3] + "y" if name.endswith("ies") else name[:-1] if name.endswith("s") and not name.endswith("ss") else name


def _key_like(df: pd.DataFrame, kinds: Dict[str, str]) -> List[str]:
    out = []
    for c, k in kinds.items():
        if c not in df or df[c].notna().sum() == 0:
            continue
        if k == "identifier" or re.search(r"(^|_)(id|key|code)$", c) or (k == "category" and df[c].nunique() > 20):
            out.append(c)
    return out


def _values(s: pd.Series) -> pd.Index:
    s = s.dropna()
    if pd.api.types.is_float_dtype(s) and np.allclose(s % 1, 0):
        s = s.astype("int64")
    return pd.Index(s.astype(str).unique())


def _name_score(ta: str, a: str, tb: str, b: str) -> float:
    if a == b:
        return 1.0
    sa, sb = _singular(ta), _singular(tb)
    if a in (f"{sb}_id", sb, f"{sb}id") and b in ("id", f"{sb}_id"):
        return 1.0
    if b in (f"{sa}_id", sa) and a == "id":
        return 0.6
    return 0.0


def discover(tables: List[Table]) -> Dict[str, Any]:
    """Propose relationships between every pair of tables and suggest a base (grain) table."""
    cache: Dict[Tuple[str, str], pd.Index] = {}
    unique: Dict[Tuple[str, str], float] = {}
    keys = {t["name"]: _key_like(t["df"], t["kinds"]) for t in tables}
    by_name = {t["name"]: t for t in tables}

    def vals(t: str, c: str) -> pd.Index:
        if (t, c) not in cache:
            s = by_name[t]["df"][c]
            cache[(t, c)] = _values(s)
            unique[(t, c)] = s.nunique() / max(1, s.notna().sum())
        return cache[(t, c)]

    rels: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for ta in keys:
        for tb in keys:
            if ta == tb:
                continue
            for a in keys[ta]:
                for b in keys[tb]:
                    name = _name_score(ta, a, tb, b)
                    va, vb = vals(ta, a), vals(tb, b)
                    if name == 0 and (np.median(va.str.len()) < 3 or abs(np.median(va.str.len()) - np.median(vb.str.len())) > 2):
                        continue  # without a name match, only compare key-shaped values of similar length
                    containment = len(va.intersection(vb)) / max(1, len(va))
                    if containment < MIN_CONTAINMENT or unique[(tb, b)] < UNIQUE_RATIO:
                        continue
                    kind = "one_to_one" if unique[(ta, a)] >= UNIQUE_RATIO else "many_to_one"
                    conf = round(0.8 * containment + 0.2 * name, 3)
                    pair = tuple(sorted((ta, tb)))
                    if pair not in rels or conf > rels[pair]["confidence"]:
                        rels[pair] = {"from_table": ta, "from_column": a, "to_table": tb, "to_column": b, "kind": kind,
                                      "containment_pct": round(containment * 100, 1), "name_match": name > 0, "confidence": conf}

    relationships = sorted(rels.values(), key=lambda r: -r["confidence"])
    score = {t["name"]: 0 for t in tables}
    for r in relationships:
        score[r["from_table"]] += 2  # tables that point to parents are facts (good grains)
        if r["kind"] == "many_to_one":
            score[r["to_table"]] += 1
    suggested = max(tables, key=lambda t: (score[t["name"]], len(t["df"])))["name"] if tables else None
    return {"relationships": relationships, "suggested_base": suggested}


def _primary_date(df: pd.DataFrame, kinds: Dict[str, str]) -> Optional[str]:
    dates = [c for c, k in kinds.items() if k == "datetime" and c in df and df[c].notna().mean() > 0.5]
    if not dates:
        return None
    preferred = [c for c in dates if re.search(r"start|admit|date$|_at$|order|visit|encounter", c)]
    return (preferred or dates)[0]


def _snake(v: Any) -> str:
    return re.sub(r"[^0-9a-z]+", "_", str(v).lower()).strip("_")[:30] or "blank"


def _aggregate(child: pd.DataFrame, kinds: Dict[str, str], group: str, prefix: str, skip: set) -> pd.DataFrame:
    g = child.groupby(group, sort=False)
    parts = [g.size().rename(f"{prefix}__n_rows")]
    numeric = [c for c, k in kinds.items() if k == "numeric" and c in child and c not in skip][:MAX_NUMERIC_AGG]
    for c in numeric:
        agg = g[c].agg(["sum", "mean", "max"])
        agg.columns = [f"{prefix}__{c}_{f}" for f in agg.columns]
        parts.append(agg)
    for c, k in kinds.items():
        if c in skip or c not in child:
            continue
        if k == "boolean":
            parts.append(g[c].mean().astype(float).rename(f"{prefix}__{c}_share"))
        elif k == "category" and child[c].nunique() <= MAX_CATEGORY_LEVELS:
            top = child[c].astype("string").value_counts().head(TOP_LEVELS).index
            parts.append(g[c].nunique().rename(f"{prefix}__{c}_distinct"))
            for v in top:
                parts.append((child[c].astype("string") == v).groupby(child[group], sort=False).sum().rename(f"{prefix}__{c}__{_snake(v)}_count"))
    return pd.concat(parts, axis=1)


def consolidate(tables: List[Table], base: str, relationships: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    by_name = {t["name"]: t for t in tables}
    if base not in by_name:
        raise ValueError(f"Unknown base table '{base}'.")
    b = by_name[base]
    out = b["df"].copy().reset_index(drop=True)
    out["__row"] = np.arange(len(out))
    kinds_out = dict(b["kinds"])
    base_date = _primary_date(b["df"], b["kinds"])
    colmap: Dict[str, Dict[str, str]] = {base: {c: c for c in b["df"].columns}}  # table -> original column -> column in `out`
    steps: List[Dict[str, Any]] = []
    warnings: List[str] = []
    done = {base}
    queue = deque([(base, 0)])

    # One-to-one links can be walked from either side
    walk = list(relationships) + [
        {**r, "from_table": r["to_table"], "from_column": r["to_column"], "to_table": r["from_table"], "to_column": r["from_column"]}
        for r in relationships if r["kind"] == "one_to_one"
    ]
    while queue:
        current, depth = queue.popleft()
        for r in walk:
            # Parent lookups: current.x -> parent.y (y unique)
            if r["from_table"] == current and r["to_table"] not in done and depth < 2:
                parent = by_name[r["to_table"]]
                left_col = colmap[current][r["from_column"]]
                prefix = r["to_table"]
                right = parent["df"].copy()
                renamed = {c: f"{prefix}__{c}" for c in right.columns if c != r["to_column"]}
                right = right.rename(columns=renamed)
                right["__rk"] = right.pop(r["to_column"]).astype(str)
                right = right.drop_duplicates(subset=["__rk"])
                key = out[left_col].astype(str).where(out[left_col].notna())
                before = len(out)
                out = out.assign(__k=key).merge(right, how="left", left_on="__k", right_on="__rk").drop(columns=["__k", "__rk"])
                assert len(out) == before, "parent join must not change the grain"
                matched = out[list(renamed.values())].notna().any(axis=1).mean() * 100 if renamed else 0
                colmap[r["to_table"]] = {orig: new for orig, new in renamed.items()} | {r["to_column"]: left_col}
                kinds_out.update({renamed[c]: k for c, k in parent["kinds"].items() if c in renamed})
                steps.append({"table": r["to_table"], "relation": "lookup (many-to-one)" if r["kind"] == "many_to_one" else "lookup (one-to-one)",
                              "on": f"{current}.{r['from_column']} = {r['to_table']}.{r['to_column']}", "matched_pct": round(float(matched), 1),
                              "columns_added": len(renamed), "point_in_time": None, "note": ""})
                done.add(r["to_table"])
                queue.append((r["to_table"], depth + 1))
            # Child aggregations: child.y -> current.x (x unique)
            elif r["to_table"] == current and r["from_table"] not in done and r["kind"] == "many_to_one":
                child_t = by_name[r["from_table"]]
                child = child_t["df"]
                key_in_out = colmap[current].get(r["to_column"])
                if key_in_out is None:
                    continue
                prefix = r["from_table"]
                child_date = _primary_date(child, child_t["kinds"])
                link = pd.DataFrame({"__row": out["__row"], "__k": out[key_in_out].astype(str)})
                if base_date:
                    link["__bd"] = out[base_date]
                c = child.copy()
                c["__k"] = c[r["from_column"]].astype(str)
                counts = c["__k"].value_counts()
                est = int((link["__k"].map(counts).fillna(0)).sum())
                pit = bool(base_date and child_date) and est <= MAX_PIT_ROWS
                if base_date and child_date and not pit:
                    warnings.append(f"{prefix}: too many rows for a point-in-time join ({est:,}); all rows were aggregated. Check these features for leakage.")
                if pit:
                    merged = link.merge(c, on="__k", how="inner")
                    merged = merged[merged[child_date] <= merged["__bd"]]
                    note = f"only {prefix}.{child_date} on or before {base}.{base_date}"
                else:
                    merged = link[["__row", "__k"]].merge(c, on="__k", how="inner") if est <= MAX_PIT_ROWS else None
                    note = "" if base_date and child_date else "no shared dates: all rows counted; make sure they are known at prediction time"
                skip = {r["from_column"], "__k"} | {k for k, v in child_t["kinds"].items() if v in ("identifier", "text", "datetime")}
                if merged is not None:
                    agg = _aggregate(merged, child_t["kinds"], "__row", prefix, skip)
                    out = out.merge(agg, how="left", left_on="__row", right_index=True)
                else:
                    agg = _aggregate(c, child_t["kinds"], "__k", prefix, skip)
                    out = out.assign(__k=out[key_in_out].astype(str)).merge(agg, how="left", left_on="__k", right_index=True).drop(columns="__k")
                new_cols = list(agg.columns)
                count_like = [x for x in new_cols if x.endswith(("_count", "__n_rows", "_distinct", "_sum"))]
                out[count_like] = out[count_like].fillna(0)
                kinds_out.update({x: "numeric" for x in new_cols})
                matched = (out[f"{prefix}__n_rows"] > 0).mean() * 100
                steps.append({"table": prefix, "relation": "aggregated (one-to-many)", "on": f"{prefix}.{r['from_column']} = {current}.{r['to_column']}",
                              "matched_pct": round(float(matched), 1), "columns_added": len(new_cols), "point_in_time": pit, "note": note})
                done.add(r["from_table"])

    unused = [t["name"] for t in tables if t["name"] not in done]
    if unused:
        warnings.append(f"Not linked to {base}: {', '.join(unused)} (no usable relationship).")
    out = out.drop(columns="__row")
    lineage = {"base": base, "base_date": base_date, "rows": int(len(out)), "columns": int(out.shape[1]), "steps": steps, "warnings": warnings}
    return out, lineage
