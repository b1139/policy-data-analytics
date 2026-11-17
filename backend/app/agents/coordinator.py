"""Coordinator agent node for interpreting policy queries and generating research plans."""

import json
import logging
import re
import uuid
from contextvars import ContextVar
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentName, AgentState, ResearchPlan, StepType
from app.core.config import settings
from app.crud.agent_log import create_agent_log
from app.llm.exceptions import AllProvidersFailedError
from app.llm.router import get_llm_router
from app.services.pubsub import format_agent_step_message, publish_step

logger = logging.getLogger(__name__)

# Context variable to optionally provide an active AsyncSession to graph nodes
coordinator_db_context: ContextVar[AsyncSession | None] = ContextVar(
    "coordinator_db_context", default=None
)

# Known Singapore policy and economic sectors
SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Technology": [
        "tech",
        "technology",
        "ict",
        "software",
        "ai",
        "digital",
        "infocomm",
        "computing",
        "it",
    ],
    "Finance": ["finance", "financial", "banking", "fintech", "insurance", "wealth", "investment"],
    "Manufacturing": [
        "manufacturing",
        "factory",
        "electronics",
        "precision",
        "semiconductor",
        "biomedical manufacturing",
    ],
    "Healthcare": ["health", "healthcare", "hospital", "medical", "biomedical", "nursing", "care"],
    "Construction": [
        "construction",
        "real estate",
        "building",
        "infrastructure",
        "housing",
        "property",
    ],
    "Services": [
        "service",
        "retail",
        "hospitality",
        "tourism",
        "f&b",
        "food and beverage",
        "transport",
        "logistics",
    ],
}

# Known policy research topics
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "employment": [
        "employment",
        "employ",
        "headcount",
        "jobs",
        "labor",
        "labour",
        "workforce",
        "hiring",
        "unemployment",
        "retrenchment",
    ],
    "wages": ["wage", "salary", "salaries", "compensation", "income", "earnings", "remuneration"],
    "gdp": ["gdp", "economic growth", "gross domestic product", "value added", "output"],
    "productivity": ["productivity", "efficiency", "output per worker"],
    "trade": ["trade", "export", "import", "commerce"],
    "inflation": ["inflation", "cpi", "consumer price", "cost of living"],
}


# Curated Singapore official statistical dataset catalog (SingStat Table Builder & Mock Internal)
SINGAPORE_DATASET_CATALOG: dict[str, dict[str, Any]] = {
    "employment": {
        "topics": ["employment", "jobs", "workforce", "labor", "labour", "headcount", "growth"],
        "singstat_id": "M810361",
        "singstat_title": "Key Indicators On Household Employment Income Among Resident Employed Households, Annual",
        "mock_id": "employment_by_sector",
        "mock_title": "Singapore Total Employment by Sector (2019-2024)",
        "default_chart": "grouped_bar",
        "metrics": ["employment_count", "yoy_change_pct", "growth_rate"],
    },
    "ict_workforce": {
        "topics": ["ict", "tech", "technology", "software", "digital", "infocomm", "it"],
        "singstat_id": "M810361",
        "singstat_title": "Information & Communications Sector Workforce and Employment Indicators",
        "mock_id": "ict_workforce_trends",
        "mock_title": "ICT Workforce Employment and Talent Trends (2019-2024)",
        "default_chart": "grouped_bar",
        "metrics": ["headcount_thousands", "share_of_total_workforce_pct", "growth_rate"],
    },
    "wages": {
        "topics": ["wage", "wages", "salary", "salaries", "income", "compensation", "earnings"],
        "singstat_id": "M810361",
        "singstat_title": "Median Monthly Household Employment Income and Real Wage Growth",
        "mock_id": "median_gross_wages",
        "mock_title": "Median Gross Monthly Wages by Occupation Group (2019-2025)",
        "default_chart": "bar",
        "metrics": ["median_monthly_income", "real_wage_growth"],
    },
    "unemployment": {
        "topics": ["unemployment", "retrenchment", "jobless", "layoff", "redundancy"],
        "singstat_id": "M810361",
        "singstat_title": "Quarterly Unemployment and Retrenchment Trends",
        "mock_id": "unemployment_rate_quarterly",
        "mock_title": "Quarterly Seasonally Adjusted Unemployment Rates (2019-2024)",
        "default_chart": "line",
        "metrics": ["overall_unemployment_rate", "youth_unemployment_rate"],
    },
    "population": {
        "topics": ["population", "demographics", "resident", "citizen", "headcount"],
        "singstat_id": "M810001",
        "singstat_title": "Indicators On Population, Annual",
        "mock_id": "employment_by_sector",
        "mock_title": "Singapore Population and Workforce Benchmark",
        "default_chart": "line",
        "metrics": ["total_population", "resident_population"],
    },
    "business": {
        "topics": [
            "business",
            "company",
            "enterprise",
            "registration",
            "formation",
            "cessation",
            "acra",
        ],
        "singstat_id": "M810361",
        "singstat_title": "Business Performance and Formation Indicators",
        "mock_id": "business_registrations",
        "mock_title": "Business Formations and Cessations by Industry (2019-2024)",
        "default_chart": "bar",
        "metrics": ["new_registrations", "cessations", "net_formation"],
    },
}


def detect_chart_type_from_query(query: str, date_range: tuple[str, str] | list[str]) -> str:
    """Determine optimal chart type based on query semantics and temporal dimensionality."""
    q_lower = query.lower()

    # 1. Comparison between periods or years (e.g., 2023 vs 2024) -> grouped_bar
    is_comparison = bool(
        re.search(r"\b(vs|versus|compare|comparison|compared\s+to|between)\b", q_lower)
    )
    years = [str(y) for y in date_range]
    has_two_distinct_years = len(years) == 2 and years[0] != years[1]

    if (is_comparison or has_two_distinct_years) and any(
        w in q_lower
        for w in ("between", "vs", "versus", "compared", "growth", "difference", "compare")
    ):
        return "grouped_bar"

    # 2. Composition / shares
    if any(
        k in q_lower
        for k in ("share", "shares", "proportion", "breakdown", "composition", "percentage", "pie")
    ):
        return "pie"

    # 3. Categorical distribution or ranking across sectors
    if any(
        k in q_lower
        for k in ("rank", "top ", "by industry", "by sector", "distribution", "ranking")
    ):
        return "horizontal_bar"

    # 4. Multi-period time series trend
    if any(
        k in q_lower
        for k in ("trend", "historical", "over time", "trajectory", "evolution", "quarterly")
    ):
        return "line"

    if has_two_distinct_years:
        return "grouped_bar"

    return "bar"


def build_shrink_instructions(
    _query: str,
    date_range: tuple[str, str] | list[str],
    target_sectors: list[str],
    topics: list[str],
) -> dict[str, Any]:
    """Formulate actionable instructions on how to shrink/slice retrieved datasets."""
    y_start, y_end = str(date_range[0]), str(date_range[1])
    years_list = [y_start] if y_start == y_end else [y_start, y_end]

    try:
        y1, y2 = int(y_start), int(y_end)
        if 0 < y2 - y1 <= 10:
            years_list = [str(y) for y in range(y1, y2 + 1)]
    except (ValueError, TypeError):
        pass

    metric_cols = ["employment_count", "yoy_change_pct", "value", "headcount", "growth_rate"]
    if "wages" in topics:
        metric_cols = ["median_monthly_income", "real_wage_growth", "value"]
    elif "unemployment" in topics:
        metric_cols = ["overall_unemployment_rate", "youth_unemployment_rate", "value"]

    time_filter_str = ",".join(years_list)
    return {
        "filter_column": "year",
        "filter_values": years_list,
        "time_filter": time_filter_str,
        "metric_columns": metric_cols,
        "target_sectors": target_sectors,
        "slice_clue": (
            f"Filter data where year/period is in {years_list}. "
            f"Focus on metrics {metric_cols[:2]} across sectors {target_sectors[:3]}."
        ),
    }


def extract_years_from_query(query: str) -> tuple[str, str]:
    """Extract start and end year strings from query or default to ('2019', '2025')."""
    # Match patterns like 2019-2024, 2019 to 2024, 2024 vs 2025
    range_match = re.search(
        r"\b(19\d\d|20\d\d)\s*(?:-|–|to|vs|versus|compared\s+to|and)\s*(19\d\d|20\d\d)\b",
        query,
        re.IGNORECASE,
    )
    if range_match:
        y1, y2 = range_match.group(1), range_match.group(2)
        return (min(y1, y2), max(y1, y2))

    # Match all individual 4-digit years
    years = re.findall(r"\b(19\d\d|20\d\d)\b", query)
    if len(years) >= 2:
        return (min(years), max(years))
    if len(years) == 1:
        return (years[0], years[0])

    return ("2019", "2025")


def detect_sectors_from_query(query: str) -> list[str]:
    """Detect relevant Singapore economic sectors from user query."""
    query_lower = query.lower()
    matched: list[str] = []
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(kw)}\b", query_lower) for kw in keywords):
            matched.append(sector)

    if not matched:
        return ["General Economy", "Technology", "Finance"]
    return matched


def detect_topics_from_query(query: str) -> list[str]:
    """Detect relevant policy analysis topics from user query."""
    query_lower = query.lower()
    matched: list[str] = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(kw)}\b", query_lower) for kw in keywords):
            matched.append(topic)

    if not matched:
        return ["employment", "economic_indicators"]
    return matched


def generate_rule_based_plan(query: str) -> ResearchPlan:
    """Generate a deterministic ResearchPlan using rule-based query parsing fallback."""
    start_year, end_year = extract_years_from_query(query)
    time_period = f"{start_year}-{end_year}" if start_year != end_year else start_year
    target_sectors = detect_sectors_from_query(query)
    topics = detect_topics_from_query(query)
    date_range = (start_year, end_year)

    # Required metrics derivation
    required_metrics: list[str] = []
    if "employment" in topics:
        required_metrics.extend(["employment_rate", "headcount", "retrenchment_rate"])
    if "wages" in topics:
        required_metrics.extend(["median_monthly_income", "real_wage_growth"])
    if "gdp" in topics or "General Economy" in target_sectors:
        required_metrics.extend(["gdp_growth_rate", "value_added"])
    if not required_metrics:
        required_metrics = ["headcount", "growth_rate", "policy_index"]

    from app.core.config import settings

    allow_mock = bool(
        getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False)
        or getattr(settings, "USE_MOCK_DATA_SOURCES", False)
    )
    sources = ["singstat", "datagov", "mock"] if allow_mock else ["singstat", "datagov"]
    sectors_str = ", ".join(target_sectors)

    # Chart recommendation & shrink instructions
    recommended_chart = detect_chart_type_from_query(query, date_range)
    shrink_instructions = build_shrink_instructions(query, date_range, target_sectors, topics)
    time_filter = shrink_instructions.get("time_filter", f"{start_year},{end_year}")

    # Sub tasks: actionable fetch instructions
    sub_tasks = [
        f"Fetch {', '.join(topics)} data for {sectors_str} ({time_period}) from SingStat",
        f"Fetch {target_sectors[0]} workforce statistics ({time_period}) from Data.gov.sg",
    ]
    if allow_mock:
        sub_tasks.append(
            f"Fetch benchmark policy indicators ({time_period}) from mock internal data source"
        )

    # Select mapped dataset IDs
    catalog_entry = SINGAPORE_DATASET_CATALOG.get("employment")
    for topic in topics:
        if topic in SINGAPORE_DATASET_CATALOG:
            catalog_entry = SINGAPORE_DATASET_CATALOG[topic]
            break

    planned_datasets = [
        {
            "source": "singstat",
            "dataset_id": catalog_entry.get("singstat_id", "M810361")
            if catalog_entry
            else "M810361",
            "title": catalog_entry.get(
                "singstat_title", f"SingStat {target_sectors[0]} Sector Performance ({time_period})"
            )
            if catalog_entry
            else f"SingStat {target_sectors[0]} Sector Performance ({time_period})",
            "time_filter": time_filter,
        },
        {
            "source": "datagov",
            # No hard-coded resource id: extraction discovers a live Data.gov.sg resource by keywords.
            "dataset_id": None,
            "keywords": " ".join(topics) or "employment",
            "title": f"Data.gov.sg {target_sectors[0]} Headcount and Metrics ({time_period})",
            "time_filter": time_filter,
        },
    ]
    if allow_mock:
        planned_datasets.append(
            {
                "source": "mock",
                "dataset_id": catalog_entry.get("mock_id", "employment_by_sector")
                if catalog_entry
                else "employment_by_sector",
                "title": catalog_entry.get(
                    "mock_title", f"Singapore Policy Benchmark Dataset ({time_period})"
                )
                if catalog_entry
                else f"Singapore Policy Benchmark Dataset ({time_period})",
                "time_filter": time_filter,
            }
        )

    return {
        "query_intent": f"Analyze Singapore policy metrics for {sectors_str} across {', '.join(topics)} ({time_period})",
        "target_sectors": target_sectors,
        "time_period": time_period,
        "required_metrics": required_metrics,
        "planned_datasets": planned_datasets,
        "sources": sources,
        "topics": topics,
        "date_range": date_range,
        "time_filter": time_filter,
        "recommended_chart": recommended_chart,
        "shrink_instructions": shrink_instructions,
        "sub_tasks": sub_tasks,
    }


def _clean_json_content(content: str) -> str:
    """Strip markdown code fence blocks if present."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_and_validate_plan(raw_json: str, query: str) -> ResearchPlan:
    """Parse JSON string into ResearchPlan, supplementing missing fields with defaults."""
    clean_text = _clean_json_content(raw_json)
    data = json.loads(clean_text)
    if not isinstance(data, dict):
        raise ValueError("LLM completion did not produce a JSON dictionary")

    fallback = generate_rule_based_plan(query)

    # Validate and normalize date_range
    raw_date_range = data.get("date_range")
    if isinstance(raw_date_range, (list, tuple)) and len(raw_date_range) == 2:
        date_range = (str(raw_date_range[0]), str(raw_date_range[1]))
    else:
        date_range = fallback["date_range"]

    from app.core.config import settings

    allow_mock = bool(
        getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False)
        or getattr(settings, "USE_MOCK_DATA_SOURCES", False)
    )
    allowed_source_set = {"singstat", "datagov", "mock"} if allow_mock else {"singstat", "datagov"}
    sources = [str(s).lower() for s in data.get("sources", [])]
    valid_sources = [s for s in sources if s in allowed_source_set]
    if not valid_sources:
        valid_sources = fallback["sources"]

    topics = [str(t) for t in data.get("topics", [])]
    if not topics:
        topics = fallback["topics"]

    sub_tasks = [str(st) for st in data.get("sub_tasks", [])]
    if not sub_tasks:
        sub_tasks = fallback["sub_tasks"]

    target_sectors = [str(s) for s in data.get("target_sectors", [])]
    if not target_sectors:
        target_sectors = fallback["target_sectors"]

    required_metrics = [str(m) for m in data.get("required_metrics", [])]
    if not required_metrics:
        required_metrics = fallback["required_metrics"]

    # Recommended chart validation
    valid_chart_types = {"grouped_bar", "bar", "horizontal_bar", "line", "pie"}
    rec_chart = str(data.get("recommended_chart") or "").strip().lower()
    if rec_chart not in valid_chart_types:
        rec_chart = detect_chart_type_from_query(query, date_range)

    # Time filter validation
    time_filter = str(
        data.get("time_filter") or fallback.get("time_filter") or f"{date_range[0]},{date_range[1]}"
    )

    # Shrink instructions validation
    raw_shrink = data.get("shrink_instructions")
    if isinstance(raw_shrink, dict) and raw_shrink.get("filter_values"):
        shrink_instructions = {
            "filter_column": str(raw_shrink.get("filter_column", "year")),
            "filter_values": [str(v) for v in raw_shrink.get("filter_values", [])],
            "time_filter": str(raw_shrink.get("time_filter") or time_filter),
            "metric_columns": [str(m) for m in raw_shrink.get("metric_columns", required_metrics)],
            "target_sectors": target_sectors,
            "slice_clue": str(
                raw_shrink.get("slice_clue")
                or fallback["shrink_instructions"].get("slice_clue", "")
            ),
        }
    else:
        shrink_instructions = build_shrink_instructions(query, date_range, target_sectors, topics)

    planned_datasets = data.get("planned_datasets")
    if isinstance(planned_datasets, list) and not allow_mock:
        planned_datasets = [
            ds
            for ds in planned_datasets
            if isinstance(ds, dict)
            and str(ds.get("source", "")).lower() not in ("mock", "mock_internal", "mock_db")
        ]
    if not isinstance(planned_datasets, list) or not planned_datasets:
        planned_datasets = fallback["planned_datasets"]
    else:
        # Normalize and sanitize dataset IDs (prevent placeholder hallucinated IDs like dataset1)
        sanitized_datasets: list[dict[str, Any]] = []
        for ds in planned_datasets:
            if not isinstance(ds, dict):
                continue
            src = str(ds.get("source") or "singstat").lower()
            d_id = str(ds.get("dataset_id") or ds.get("id") or "").strip()
            # If dataset_id is a generic placeholder like 'dataset1', remap to real Singapore catalog ID
            if not d_id or d_id.lower() in (
                "dataset1",
                "dataset2",
                "dataset_1",
                "dataset_2",
                "id",
                "id1",
                "none",
                "null",
            ):
                cat = SINGAPORE_DATASET_CATALOG.get("employment")
                for tp in topics:
                    if tp in SINGAPORE_DATASET_CATALOG:
                        cat = SINGAPORE_DATASET_CATALOG[tp]
                        break
                if src == "singstat":
                    d_id = cat.get("singstat_id", "M810361") if cat else "M810361"
                    title = (
                        cat.get("singstat_title", ds.get("title", "SingStat Dataset"))
                        if cat
                        else ds.get("title", "SingStat Dataset")
                    )
                elif src == "datagov":
                    d_id = None  # live discovery by keywords in the extraction agent
                    title = ds.get("title") or f"Data.gov.sg {' '.join(topics)} dataset"
                else:
                    d_id = (
                        cat.get("mock_id", "employment_by_sector")
                        if cat
                        else "employment_by_sector"
                    )
                    title = (
                        cat.get("mock_title", ds.get("title", "Singapore Dataset"))
                        if cat
                        else ds.get("title", "Singapore Dataset")
                    )
            else:
                title = ds.get("title", f"{src} dataset ({d_id})")

            sanitized_datasets.append(
                {
                    "source": src,
                    "dataset_id": d_id,
                    "title": title,
                    "keywords": ds.get("keywords") or " ".join(topics),
                    "time_filter": time_filter,
                }
            )
        planned_datasets = sanitized_datasets or fallback["planned_datasets"]

    # Always pull from BOTH official sources so analytics can combine them
    present = {str(ds.get("source", "")).lower() for ds in planned_datasets}
    for fb_ds in fallback["planned_datasets"]:
        fb_src = str(fb_ds.get("source", "")).lower()
        if fb_src in ("singstat", "datagov") and fb_src not in present:
            planned_datasets.append(fb_ds)
            present.add(fb_src)
    for req in ("singstat", "datagov"):
        if req not in valid_sources:
            valid_sources.append(req)

    query_intent = str(data.get("query_intent") or fallback["query_intent"])
    time_period = str(data.get("time_period") or f"{date_range[0]}-{date_range[1]}")

    return {
        "query_intent": query_intent,
        "target_sectors": target_sectors,
        "time_period": time_period,
        "required_metrics": required_metrics,
        "planned_datasets": planned_datasets,
        "sources": valid_sources,
        "topics": topics,
        "date_range": date_range,
        "time_filter": time_filter,
        "recommended_chart": rec_chart,
        "shrink_instructions": shrink_instructions,
        "sub_tasks": sub_tasks,
    }


async def coordinator_node(
    state: AgentState,
    db: AsyncSession | None = None,
) -> AgentState:
    """Coordinate Singapore policy research planning via LLM interpretation or rule-based fallback.

    Args:
        state: Shared AgentState dictionary.
        db: Optional active AsyncSession for persisting agent steps.

    Returns:
        AgentState: State updated with current_agent, research_plan, agent_logs, and status.
    """
    state["current_agent"] = AgentName.COORDINATOR
    analysis_id = state.get("analysis_id", "unknown-analysis")
    query = state.get("query", "")

    # Resolve DB session
    active_db = db or coordinator_db_context.get() or state.get("_db")
    try:
        analysis_uuid = uuid.UUID(str(analysis_id))
    except (ValueError, TypeError):
        analysis_uuid = uuid.uuid4()

    # Step 1: Emit THINK step
    think_seq = len(state.get("agent_logs", [])) + 1
    think_content = {
        "thought": (
            f"Interpreting policy research query: '{query}'. "
            "Formulating structured Singapore policy research plan."
        )
    }
    think_log = {
        "agent_name": AgentName.COORDINATOR,
        "step_type": StepType.THINK,
        "content": think_content,
        "sequence_no": think_seq,
    }
    state.setdefault("agent_logs", []).append(think_log)

    try:
        think_msg = format_agent_step_message(
            analysis_id=analysis_id,
            agent_name=AgentName.COORDINATOR,
            step_type=StepType.THINK,
            content=think_content,
            sequence_no=think_seq,
        )
        await publish_step(analysis_id, think_msg)
    except Exception as exc:
        logger.warning("Failed to publish coordinator THINK step to pubsub: %s", exc)

    if active_db is not None:
        try:
            await create_agent_log(
                db=active_db,
                analysis_id=analysis_uuid,
                agent_name=AgentName.COORDINATOR,
                step_type=StepType.THINK,
                content=think_content,
                seq_no=think_seq,
            )
        except Exception as exc:
            logger.warning("Failed to persist coordinator THINK step to DB: %s", exc)

    # Step 2: Formulate ResearchPlan via LLM or rule-based fallback
    plan: ResearchPlan | None = None
    router = get_llm_router()
    active_provider = getattr(
        router, "primary_name", getattr(settings, "primary_llm_provider", "bedrock")
    )
    active_model = getattr(
        router.primary,
        "model",
        getattr(
            settings,
            "bedrock_model_id" if active_provider == "bedrock" else "gemini_model",
            "apac.amazon.nova-lite-v1:0",
        ),
    )
    model_info = {
        "agent": "coordinator",
        "provider": active_provider,
        "model": str(active_model),
        "role": "Query Decomposition & Strategic Research Planning",
    }

    system_prompt = (
        "You are the Singapore Policy Research Coordinator. "
        "Formulate a comprehensive research plan as a single compact JSON object (no markdown, no prose). "
        "Specify the exact chart type, real SingStat table IDs (e.g. M810361, M810001) or mock datasets, "
        "and data shrinkage instructions so downstream agents extract and stash the exact required slice in one go."
    )
    user_prompt = (
        f"Query: {query}\n"
        "Keys to return:\n"
        "- query_intent (str): concise intent description\n"
        "- target_sectors (list[str]): Singapore economic sectors\n"
        "- time_period (str): e.g. '2023-2024'\n"
        "- date_range (list[str]): [start_year, end_year]\n"
        "- time_filter (str): comma-separated years/periods to pull in one go (e.g. '2023,2024')\n"
        "- recommended_chart (str): best chart type ('grouped_bar' for 2-period comparisons, 'line' for multi-year trends, 'bar'/'horizontal_bar' for categories, 'pie' for shares)\n"
        "- required_metrics (list[str]): key economic indicators\n"
        "- sources (list[str]): always include both official sources, e.g. ['singstat', 'datagov']\n"
        "- topics (list[str]): e.g. ['employment']\n"
        "- sub_tasks (list[str]): execution tasks\n"
        "- planned_datasets (list[dict]): one entry per source (both 'singstat' AND 'datagov'): "
        "[{source: 'singstat'|'datagov', dataset_id: 'M810361' (SingStat) or null (datagov: auto-discovered), title: str, keywords: str, time_filter: str}]\n"
        "- shrink_instructions (dict): {filter_column: 'year', filter_values: [str], slice_clue: str}"
    )

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = await router.complete(
            messages,
            temperature=0.2,
            max_tokens=650,
            json_mode=True,
        )
        plan = _parse_and_validate_plan(response.content, query)
        if hasattr(response, "model") and response.model:
            model_info["model"] = str(response.model)
        if hasattr(response, "provider") and response.provider:
            model_info["provider"] = str(response.provider)
        if hasattr(response, "latency_ms"):
            model_info["latency_ms"] = response.latency_ms
        logger.info("Successfully formulated research plan via LLM for analysis_id=%s", analysis_id)
    except AllProvidersFailedError:
        logger.error("All LLM providers failed in coordinator node.")
        raise
    except Exception as exc:
        logger.warning(
            "LLM research plan formulation failed (%s). Engaging rule-based fallback parser.",
            exc,
        )
        plan = generate_rule_based_plan(query)

    state["coordinator_model"] = model_info

    # Step 3: Emit DONE step
    done_seq = len(state.get("agent_logs", [])) + 1
    done_content = {
        "thought": (
            f"Formulated structured research plan using {model_info['provider']} ({model_info['model']}). "
            f"Recommended chart: '{plan.get('recommended_chart')}'. "
            f"Data slice: {plan.get('shrink_instructions', {}).get('slice_clue', '')}"
        ),
        "plan": plan,
        "recommended_chart": plan.get("recommended_chart"),
        "time_filter": plan.get("time_filter"),
        "shrink_instructions": plan.get("shrink_instructions"),
        "sources": plan.get("sources", []),
        "sub_tasks": plan.get("sub_tasks", []),
        "model": model_info["model"],
        "provider": model_info["provider"],
    }
    done_log = {
        "agent_name": AgentName.COORDINATOR,
        "step_type": StepType.DONE,
        "content": done_content,
        "sequence_no": done_seq,
    }
    state.setdefault("agent_logs", []).append(done_log)

    try:
        done_msg = format_agent_step_message(
            analysis_id=analysis_id,
            agent_name=AgentName.COORDINATOR,
            step_type=StepType.DONE,
            content=done_content,
            sequence_no=done_seq,
        )
        await publish_step(analysis_id, done_msg)
    except Exception as exc:
        logger.warning("Failed to publish coordinator DONE step to pubsub: %s", exc)

    if active_db is not None:
        try:
            await create_agent_log(
                db=active_db,
                analysis_id=analysis_uuid,
                agent_name=AgentName.COORDINATOR,
                step_type=StepType.DONE,
                content=done_content,
                seq_no=done_seq,
            )
        except Exception as exc:
            logger.warning("Failed to persist coordinator DONE step to DB: %s", exc)

    state["research_plan"] = plan
    state["status"] = "planned"
    return state
