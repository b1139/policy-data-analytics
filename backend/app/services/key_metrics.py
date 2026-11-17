"""Dynamic KPI tile generation: deterministic metrics from the data, worded by the LLM.

Every number shown in a tile is computed from the (query-filtered, chronologically
sorted) dataset. The LLM only chooses the most relevant candidates for the query and
rewrites their labels/captions; it can never introduce a new value.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_COUNT_HINTS = ("count", "headcount", "employment", "workers", "total", "population", "number")


def _fmt_num(v: float) -> str:
    a = abs(v)
    if a >= 1_000_000_000:
        return f"{v / 1_000_000_000:.2f}B"
    if a >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if a >= 10_000:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:,.1f}"
    return f"{v:,.2f}"


def _fmt_pct(v: float, signed: bool = True) -> str:
    return f"{'+' if signed and v > 0 else ''}{v:.1f}%"


def _label(val: Any) -> str:
    try:
        f = float(val)
        if f.is_integer():
            return str(int(f))
    except (TypeError, ValueError):
        pass
    return str(val)


def _tone(v: float | None) -> str:
    if v is None or abs(v) < 1e-9:
        return "neutral"
    return "positive" if v > 0 else "negative"


def _prepare_series(
    df: pd.DataFrame, query: str, meta: dict[str, Any]
) -> tuple[pd.DataFrame, str, str | None, str | None]:
    """Return (filtered df, value_col, time_col, sector_col) consistent with the stats run."""
    from app.agents.tools.analysis_tools import filter_dataframe_by_query

    filtered, qmeta = filter_dataframe_by_query(
        df,
        query=query,
        preferred_val=meta.get("value_col"),
        preferred_time=meta.get("time_col"),
        preferred_sector=meta.get("sector_col"),
    )
    v_col = meta.get("value_col") or qmeta.get("val_col")
    t_col = meta.get("time_col") or qmeta.get("time_col")
    s_col = meta.get("sector_col") or qmeta.get("category_col")
    return filtered, v_col, t_col, s_col


def compute_candidates(
    datasets: list[dict[str, Any]], stats: dict[str, Any], query: str
) -> list[dict[str, Any]]:
    """Compute candidate KPI tiles purely from data."""
    from app.agents.tools.analysis_tools import _parse_dataframe

    meta = stats.get("metadata") if isinstance(stats.get("metadata"), dict) else {}
    df = None
    for ds in datasets:
        raw = ds.get("df_json") or ds.get("dataframe_json") or ds.get("data")
        cand = _parse_dataframe(raw)
        if cand.empty:
            continue
        if meta.get("value_col") and meta["value_col"] not in cand.columns:
            continue
        df = cand
        break
    if df is None:
        return []

    work, v_col, t_col, s_col = _prepare_series(df, query, meta)
    if work.empty or not v_col or v_col not in work.columns:
        return []

    work = work.copy()
    work[v_col] = pd.to_numeric(work[v_col], errors="coerce")
    work = work.dropna(subset=[v_col])
    if work.empty:
        return []

    metric = v_col.replace("_", " ").title()
    is_pct_metric = any(k in v_col.lower() for k in ("pct", "percent", "rate", "growth"))
    unit = "%" if is_pct_metric else ""

    def fmt_val(x: float) -> str:
        return f"{_fmt_num(x)}{unit}"

    cands: list[dict[str, Any]] = []

    # ---- Time series (aggregated per period, chronological) ----
    series: pd.Series | None = None
    if t_col and t_col in work.columns:
        agg = (
            "sum"
            if (not is_pct_metric and any(k in v_col.lower() for k in _COUNT_HINTS))
            else "mean"
        )
        grouped = work.groupby(t_col)[v_col].agg(agg)
        tnum = pd.to_numeric(pd.Series(grouped.index, index=grouped.index), errors="coerce")
        if tnum.notna().all():
            grouped = grouped.iloc[tnum.argsort().to_numpy()]
        else:
            tdt = pd.to_datetime(pd.Series(grouped.index, index=grouped.index), errors="coerce")
            grouped = (
                grouped.iloc[tdt.argsort().to_numpy()]
                if tdt.notna().all()
                else grouped.sort_index()
            )
        series = grouped

    if series is not None and len(series) >= 1:
        first_p, last_p = _label(series.index[0]), _label(series.index[-1])
        first_v, last_v = float(series.iloc[0]), float(series.iloc[-1])
        cands.append(
            {
                "id": "latest",
                "label": f"Latest {metric}",
                "value": fmt_val(last_v),
                "caption": f"As of {last_p}",
                "tone": "neutral",
                "icon": "activity",
            }
        )
        if len(series) >= 2:
            if is_pct_metric:
                diff = last_v - first_v
                cands.append(
                    {
                        "id": "change",
                        "label": f"Change {first_p}–{last_p}",
                        "value": f"{'+' if diff > 0 else ''}{diff:.2f} pts",
                        "caption": f"{fmt_val(first_v)} → {fmt_val(last_v)}",
                        "tone": _tone(diff),
                        "icon": "trend",
                    }
                )
            elif first_v != 0:
                pct = (last_v - first_v) / abs(first_v) * 100.0
                cands.append(
                    {
                        "id": "change",
                        "label": f"Change {first_p}–{last_p}",
                        "value": _fmt_pct(pct),
                        "caption": f"{fmt_val(first_v)} → {fmt_val(last_v)}",
                        "tone": _tone(pct),
                        "icon": "trend",
                    }
                )
                # CAGR for yearly numeric series
                try:
                    years = float(last_p) - float(first_p)
                    if years > 0 and first_v > 0 and last_v > 0:
                        cagr = ((last_v / first_v) ** (1 / years) - 1) * 100
                        cands.append(
                            {
                                "id": "cagr",
                                "label": "Compound Annual Growth",
                                "value": _fmt_pct(cagr),
                                "caption": f"Per year, {first_p}–{last_p}",
                                "tone": _tone(cagr),
                                "icon": "percent",
                            }
                        )
                except ValueError:
                    pass
            peak_idx, low_idx = series.idxmax(), series.idxmin()
            cands.append(
                {
                    "id": "peak",
                    "label": "Peak Period",
                    "value": _label(peak_idx),
                    "caption": f"Highest: {fmt_val(float(series.max()))}",
                    "tone": "neutral",
                    "icon": "calendar",
                }
            )
            cands.append(
                {
                    "id": "low",
                    "label": "Lowest Period",
                    "value": _label(low_idx),
                    "caption": f"Lowest: {fmt_val(float(series.min()))}",
                    "tone": "neutral",
                    "icon": "calendar",
                }
            )
            cands.append(
                {
                    "id": "average",
                    "label": f"Average {metric}",
                    "value": fmt_val(float(series.mean())),
                    "caption": f"Across {len(series)} periods",
                    "tone": "neutral",
                    "icon": "activity",
                }
            )
            vol = float(series.std(ddof=1)) if len(series) > 2 else 0.0
            mean = float(series.mean())
            if mean:
                cands.append(
                    {
                        "id": "volatility",
                        "label": "Volatility",
                        "value": f"{abs(vol / mean) * 100:.1f}%",
                        "caption": "Std. dev. relative to mean",
                        "tone": "neutral",
                        "icon": "activity",
                    }
                )
    else:
        cands.append(
            {
                "id": "average",
                "label": f"Average {metric}",
                "value": fmt_val(float(work[v_col].mean())),
                "caption": f"Across {len(work)} observations",
                "tone": "neutral",
                "icon": "activity",
            }
        )

    # ---- Category leaders ----
    if s_col and s_col in work.columns and work[s_col].nunique() > 1:
        sub = work
        if t_col and t_col in work.columns and series is not None and len(series):
            last_raw = work[t_col][work[t_col].map(_label) == _label(series.index[-1])]
            if not last_raw.empty:
                sub = work[work[t_col].isin(last_raw.unique())]
        by_cat = (
            sub.groupby(s_col)[v_col].sum()
            if not is_pct_metric
            else sub.groupby(s_col)[v_col].mean()
        )
        by_cat = by_cat[by_cat.notna()]
        if len(by_cat) > 1:
            top = by_cat.idxmax()
            total = float(by_cat.sum())
            share = (
                (float(by_cat.max()) / total * 100.0) if (total > 0 and not is_pct_metric) else None
            )
            cands.append(
                {
                    "id": "top_category",
                    "label": f"Top {s_col.replace('_', ' ').title()}",
                    "value": str(top)[:28],
                    "caption": (
                        f"{share:.1f}% of total"
                        if share is not None
                        else f"{fmt_val(float(by_cat.max()))}"
                    ),
                    "tone": "neutral",
                    "icon": "database",
                }
            )
            cands.append(
                {
                    "id": "categories",
                    "label": f"{s_col.replace('_', ' ').title()} Covered",
                    "value": str(int(by_cat.shape[0])),
                    "caption": "Distinct groups analysed",
                    "tone": "neutral",
                    "icon": "database",
                }
            )

    cands.append(
        {
            "id": "coverage",
            "label": "Observations",
            "value": f"{len(work):,}",
            "caption": (
                f"{_label(series.index[0])}–{_label(series.index[-1])}"
                if series is not None and len(series) > 1
                else "Official records analysed"
            ),
            "tone": "neutral",
            "icon": "database",
        }
    )
    return cands


async def _llm_select(
    cands: list[dict[str, Any]], query: str, insights: str, count: int
) -> list[dict[str, Any]] | None:
    """Ask the LLM to choose and re-word the most relevant candidates. Values stay untouched."""
    try:
        from app.llm.router import get_llm_router

        router = get_llm_router()
        facts = [
            {"id": c["id"], "label": c["label"], "value": c["value"], "caption": c["caption"]}
            for c in cands
        ]
        prompt = (
            f"User query: {query}\n"
            f"Computed facts (JSON): {json.dumps(facts)}\n"
            f"Insight summary: {insights[:600]}\n\n"
            f"Pick the {count} facts most relevant to the query. For each, return a short "
            f"label (<=28 chars) and a one-line caption (<=60 chars) that explains what the "
            f"number means for the query. Do NOT change or invent values.\n"
            f'Return ONLY JSON: [{{"id":"...","label":"...","caption":"..."}}]'
        )
        resp = await router.complete(
            messages=[
                {
                    "role": "system",
                    "content": "You write concise dashboard tile text. Output strict JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        text = (resp.content or "").strip() if resp else ""
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            return None
        picked = json.loads(m.group(0))
        by_id = {c["id"]: c for c in cands}
        out: list[dict[str, Any]] = []
        for p in picked:
            c = by_id.get(str(p.get("id")))
            if not c or any(o["id"] == c["id"] for o in out):
                continue
            out.append(
                {
                    **c,
                    "label": str(p.get("label") or c["label"])[:40],
                    "caption": str(p.get("caption") or c["caption"])[:90],
                    "source": "llm",
                }
            )
        return out or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM key-metric selection failed, using deterministic tiles: %s", exc)
        return None


async def build_key_metrics(
    datasets: list[dict[str, Any]],
    stats: dict[str, Any],
    query: str,
    insights: str = "",
    count: int = 4,
) -> list[dict[str, Any]]:
    """Return `count` dynamic KPI tiles (label, value, caption, tone, icon)."""
    if not isinstance(stats, dict) or not stats:
        return []
    try:
        cands = compute_candidates(datasets, stats, query)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Key metric computation failed: %s", exc)
        return []
    if not cands:
        return []

    chosen = await _llm_select(cands, query, insights, count) or []
    # Top up deterministically (preferred order) so we always return `count` tiles
    priority = [
        "latest",
        "change",
        "peak",
        "top_category",
        "cagr",
        "average",
        "low",
        "volatility",
        "coverage",
        "categories",
    ]
    rank = {k: i for i, k in enumerate(priority)}
    for c in sorted(cands, key=lambda c: rank.get(c["id"], 99)):
        if len(chosen) >= count:
            break
        if not any(o["id"] == c["id"] for o in chosen):
            chosen.append({**c, "source": "data"})
    return chosen[:count]
