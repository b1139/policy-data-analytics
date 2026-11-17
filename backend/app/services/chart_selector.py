"""LLM-driven chart type selection for query-aligned visualizations."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.llm.router import get_llm_router

logger = logging.getLogger(__name__)

CHART_TYPES: tuple[str, ...] = ("line", "bar", "horizontal_bar", "grouped_bar", "pie")

SYSTEM_PROMPT = (
    "Pick the best chart for the query. line=trend over time; bar=few categories; "
    "horizontal_bar=many/long-named categories; grouped_bar=2 periods x categories; "
    'pie=shares of a total. Reply JSON only: {"chart_type":"<type>"}'
)


def feasible_chart_types(profile: dict[str, Any]) -> list[str]:
    """Return chart types that the data shape can actually support."""
    has_time = bool(profile.get("time_col")) and profile.get("n_periods", 0) >= 2
    has_cat = bool(profile.get("category_col")) and profile.get("n_categories", 0) >= 2
    types: list[str] = []
    if has_time:
        types.append("line")
    if has_cat or profile.get("time_col"):
        types.extend(["bar", "horizontal_bar"])
    else:
        types.append("bar")
    if has_cat and profile.get("n_periods", 0) >= 2:
        types.append("grouped_bar")
    if has_cat and 2 <= profile.get("n_categories", 0) <= 10 and profile.get("additive", False):
        types.append("pie")
    return types


def heuristic_chart_type(query: str, profile: dict[str, Any]) -> str:
    """Deterministic fallback used when the LLM is unavailable or answers invalidly."""
    feasible = feasible_chart_types(profile)
    q = (query or "").lower()
    if profile.get("is_comparison") and "grouped_bar" in feasible:
        return "grouped_bar"
    if any(k in q for k in ("share", "composition", "proportion", "breakdown")) and "pie" in feasible:
        return "pie"
    if any(k in q for k in ("distribution", "by sector", "by industry", "rank", "top ")):
        if "horizontal_bar" in feasible and profile.get("n_categories", 0) > 6:
            return "horizontal_bar"
        if "bar" in feasible:
            return "bar"
    if "line" in feasible:
        return "line"
    return "bar"


def _parse_choice(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


async def select_chart_type(query: str, profile: dict[str, Any]) -> dict[str, str]:
    """Ask the LLM which chart type best answers the query; validate against the data shape.

    Returns {"chart_type", "reason", "selected_by"} where selected_by is 'llm' or 'heuristic'.
    """
    feasible = feasible_chart_types(profile)
    fallback = heuristic_chart_type(query, profile)

    user_prompt = (
        f"Q: {query.strip()}\n"
        f"Data: {json.dumps(profile, default=str, separators=(',', ':'))}\n"
        f"Allowed: {','.join(feasible)}"
    )
    try:
        router = get_llm_router()
        response = await router.complete(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=20,
        )
        choice = _parse_choice(response.content if response else "")
        chart_type = str((choice or {}).get("chart_type", "")).strip().lower()
        if chart_type in CHART_TYPES and chart_type in feasible:
            return {
                "chart_type": chart_type,
                "reason": "Selected by LLM from query intent and data shape.",
                "selected_by": "llm",
            }
        logger.info("LLM chart choice %r unusable (feasible=%s); using heuristic.", chart_type, feasible)
    except Exception as exc:
        logger.warning("LLM chart type selection failed (%s); using heuristic.", exc)

    return {
        "chart_type": fallback,
        "reason": "Selected by rule-based fallback from query intent and data shape.",
        "selected_by": "heuristic",
    }
