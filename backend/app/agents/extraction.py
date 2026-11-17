"""Data Extraction Agent node using LangGraph ReAct pattern.

Discovers, retrieves, and validates policy datasets planned by the Coordinator agent,
emitting ACT and OBSERVE telemetry steps to WebSocket and database persistence.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from contextvars import ContextVar
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableBinding
try:
    from langgraph.graph.state import CompiledStateGraph as CompiledGraph
except ImportError:
    try:
        from langgraph.graph.state import CompiledGraph  # type: ignore[attr-defined]
    except ImportError:
        from langgraph.graph.graph import CompiledGraph  # type: ignore[assignment]
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentName, AgentState, StepType
from app.agents.tools.data_tools import (
    fetch_dataset,
    list_available_datasets,
    validate_dataframe,
)
from app.crud.agent_log import create_agent_log
from app.llm.exceptions import format_user_friendly_error
from app.services.pubsub import format_agent_step_message, publish_step

logger = logging.getLogger(__name__)

# Context variable to optionally provide an active AsyncSession to extraction node
extraction_db_context: ContextVar[AsyncSession | None] = ContextVar(
    "extraction_db_context", default=None
)

# Guardrail: Maximum ReAct loop iterations per execution to prevent infinite cycles
MAX_REACT_ITERATIONS: int = 15


class ExtractionChatModel(BaseChatModel):
    """Fallback ChatModel for LangGraph create_react_agent when running offline or mocked."""

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, kwargs
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="Data extraction and quality validation completed successfully."
                    )
                )
            ]
        )

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> RunnableBinding:
        return RunnableBinding(bound=self, kwargs={"tools": tools, **kwargs})

    @property
    def _llm_type(self) -> str:
        return "extraction_react_model"


def create_extraction_agent(
    model: Any = None,
    tools: list[Any] | None = None,
    checkpointer: Any = None,
) -> CompiledGraph:
    """Create a LangGraph ReAct agent pre-configured with data extraction tools.

    Args:
        model: Optional LangChain BaseChatModel. Defaults to ExtractionChatModel.
        tools: Optional list of LangChain tools. Defaults to data extraction tools.
        checkpointer: Optional LangGraph checkpoint saver.

    Returns:
        CompiledGraph: Compiled LangGraph ReAct agent graph.
    """
    selected_tools = (
        tools
        if tools is not None
        else [
            list_available_datasets,
            fetch_dataset,
            validate_dataframe,
        ]
    )
    chat_model = model if model is not None else ExtractionChatModel()
    return create_react_agent(
        model=chat_model,
        tools=selected_tools,
        checkpointer=checkpointer,
    )


async def _emit_step(
    state: AgentState,
    step_type: StepType,
    content: dict[str, Any],
    active_db: AsyncSession | None,
    analysis_id: str,
    analysis_uuid: uuid.UUID,
) -> dict[str, Any]:
    """Emit an agent step, persist to state agent_logs, broadcast via PubSub, and save to DB."""
    seq_no = len(state.get("agent_logs", [])) + 1
    log_entry = {
        "agent_name": AgentName.EXTRACTION,
        "step_type": step_type,
        "content": content,
        "sequence_no": seq_no,
    }
    state.setdefault("agent_logs", []).append(log_entry)

    try:
        msg = format_agent_step_message(
            analysis_id=analysis_id,
            agent_name=AgentName.EXTRACTION,
            step_type=step_type,
            content=content,
            sequence_no=seq_no,
        )
        await publish_step(analysis_id, msg)
    except Exception as exc:
        logger.warning("Failed to publish extraction %s step to pubsub: %s", step_type, exc)

    if active_db is not None:
        try:
            await create_agent_log(
                db=active_db,
                analysis_id=analysis_uuid,
                agent_name=AgentName.EXTRACTION,
                step_type=step_type,
                content=content,
                seq_no=seq_no,
            )
        except Exception as exc:
            logger.warning("Failed to persist extraction %s step to DB: %s", step_type, exc)

    return log_entry


def _shrink_dataframe(
    df_json: str,
    shrink_instructions: dict[str, Any] | None,
) -> tuple[str, int, str]:
    """Shrink the dataset according to coordinator instructions so the extracted slice is focused.

    Returns:
        (shrunk_df_json, row_count, slice_summary)
    """
    if not df_json or not df_json.strip() or not shrink_instructions:
        return df_json, 0, ""

    try:
        import io
        import pandas as pd

        df = pd.read_json(io.StringIO(df_json), orient="split")
        orig_len = len(df)
        if df.empty:
            return df_json, 0, ""

        filter_vals = [
            str(v).strip()
            for v in shrink_instructions.get("filter_values", [])
            if str(v).strip()
        ]
        filtered = False

        if filter_vals:
            filter_col = shrink_instructions.get("filter_column", "year")
            for candidate in (filter_col, "year", "period", "period_start"):
                if candidate in df.columns:
                    mask = df[candidate].astype(str).str.strip().apply(
                        lambda val: any(fv in val for fv in filter_vals)
                    )
                    if mask.any():
                        df = df[mask].copy()
                        filtered = True
                    break

        new_json = df.to_json(orient="split", date_format="iso")
        summary = (
            f"Shrunk from {orig_len} to {len(df)} rows covering {filter_vals}"
            if filtered
            else f"Retained {len(df)} rows"
        )
        return new_json, len(df), summary
    except Exception as exc:
        logger.debug("Failed shrinking dataframe: %s", exc)
        return df_json, 0, ""


def _build_extraction_targets(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Formulate actionable dataset extraction targets from the research plan."""
    from app.core.config import settings

    allow_mock = bool(
        getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False)
        or getattr(settings, "USE_MOCK_DATA_SOURCES", False)
    )
    default_source = "mock_internal" if allow_mock else "singstat"
    time_filter = plan.get("time_filter")
    shrink_instructions = plan.get("shrink_instructions") or {}

    targets: list[dict[str, Any]] = []

    planned = plan.get("planned_datasets") or []
    if isinstance(planned, list) and len(planned) > 0:
        for item in planned:
            if isinstance(item, dict):
                src = item.get("source", default_source)
                d_id = item.get("dataset_id") or item.get("id")

                # Sanitize placeholder IDs like 'dataset1'
                if str(d_id).lower() in ("dataset1", "dataset2", "id"):
                    topics = plan.get("topics", ["employment"])
                    if "ict" in topics or "technology" in topics:
                        d_id = "M810361" if src == "singstat" else "ict_workforce_trends"
                    elif "wages" in topics:
                        d_id = "M810361" if src == "singstat" else "median_gross_wages"
                    elif "unemployment" in topics:
                        d_id = "M810361" if src == "singstat" else "unemployment_rate_quarterly"
                    else:
                        d_id = "M810361" if src == "singstat" else "employment_by_sector"
                elif not d_id or str(d_id).lower() in ("null", "none"):
                    if src == "singstat":
                        d_id = "M810361"
                    elif src == "datagov":
                        # Keep None to trigger ReAct dynamic dataset discovery on Data.gov.sg
                        d_id = None
                    else:
                        d_id = "employment_by_sector"

                if not allow_mock and str(src).lower() in ("mock", "mock_internal", "mock_db"):
                    continue
                targets.append(
                    {
                        "source": src,
                        "dataset_id": d_id,
                        "title": item.get("title", "Dataset"),
                        "keywords": item.get("keywords")
                        or " ".join(plan.get("topics", ["employment"])),
                        "time_filter": item.get("time_filter") or time_filter,
                        "shrink_instructions": shrink_instructions,
                    }
                )

    # If planned_datasets is empty, parse sub_tasks
    sub_tasks = plan.get("sub_tasks") or []
    if not targets and isinstance(sub_tasks, list) and len(sub_tasks) > 0:
        for task in sub_tasks:
            s_task = str(task)
            task_lower = s_task.lower()
            if "singstat" in task_lower:
                src = "singstat"
            elif "data.gov" in task_lower or "datagov" in task_lower:
                src = "datagov"
            elif "mock" in task_lower:
                if not allow_mock:
                    continue
                src = "mock_internal"
            else:
                sources_list = plan.get("sources", [])
                src = sources_list[0] if sources_list else default_source

            # Match keyword
            kw = "employment"
            for candidate in [
                "employment",
                "workforce",
                "wages",
                "wage",
                "salary",
                "gdp",
                "trade",
                "inflation",
                "business",
            ]:
                if candidate in task_lower:
                    kw = candidate
                    break

            mapped_id = "M810361" if src == "singstat" else "employment_by_sector"
            targets.append(
                {
                    "source": src,
                    "dataset_id": mapped_id,
                    "title": s_task,
                    "keywords": kw,
                    "sub_task": s_task,
                    "time_filter": time_filter,
                    "shrink_instructions": shrink_instructions,
                }
            )

    # Fallback to sources and topics
    if not targets:
        sources = plan.get("sources") or [default_source]
        topics = plan.get("topics") or ["employment"]
        for src in sources:
            if not allow_mock and str(src).lower() in ("mock", "mock_internal", "mock_db"):
                continue
            for tp in topics:
                mapped_id = "M810361" if src == "singstat" else "employment_by_sector"
                targets.append(
                    {
                        "source": src,
                        "dataset_id": mapped_id,
                        "title": f"{src} {tp} dataset",
                        "keywords": tp,
                        "time_filter": time_filter,
                        "shrink_instructions": shrink_instructions,
                    }
                )

    return targets


async def _singstat_filters(
    source: str, dataset_id: Any, keywords: str, plan: dict[str, Any]
) -> dict[str, str]:
    """SingStat MCP best practice: read table metadata first, then filter series/time.

    Mirrors get_table_data(resource_id, seriesNoORrowNo='1,1.1', timeFilter=[start, end]).
    """
    if str(source).lower() not in ("singstat", "singstat_mcp", "singstat_rest"):
        return {}
    try:
        from app.data_sources import data_source_registry

        connector = data_source_registry.get("singstat")
        meta = await connector.get_metadata(str(dataset_id))
    except Exception as exc:
        logger.debug("SingStat metadata lookup skipped: %s", exc)
        return {}
    filters: dict[str, str] = {}
    if meta:
        series = connector.select_series(meta.get("row") or [], keywords)
        if series:
            filters["series_no"] = series
    time_filter = plan.get("time_filter") or plan.get("years")
    if isinstance(time_filter, (list, tuple)):
        time_filter = ",".join(str(t) for t in time_filter)
    if time_filter:
        filters["time_filter"] = str(time_filter)
    return filters


async def extraction_node(state: AgentState, db: AsyncSession | None = None) -> AgentState:
    """Execute the Data Extraction agent node using the ReAct pattern.

    Args:
        state: Shared LangGraph AgentState containing query and research_plan.
        db: Optional active SQLAlchemy AsyncSession for log persistence.

    Returns:
        AgentState: Updated state with selected_datasets, raw_data, extraction_errors,
                    and agent_logs.
    """
    state["current_agent"] = AgentName.EXTRACTION
    active_db = db or extraction_db_context.get() or state.get("_db")

    analysis_id = str(state.get("analysis_id", ""))
    try:
        analysis_uuid = uuid.UUID(analysis_id)
    except (ValueError, TypeError):
        analysis_uuid = uuid.uuid4()

    state.setdefault("selected_datasets", [])
    state.setdefault("raw_data", {})
    state.setdefault("extraction_errors", [])
    state.setdefault("agent_logs", [])

    research_plan = state.get("research_plan") or {}
    targets = _build_extraction_targets(research_plan)
    from app.core.config import settings

    allow_mock_fallback = bool(
        getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False)
        or getattr(settings, "USE_MOCK_DATA_SOURCES", False)
    )
    default_source = "mock_internal" if allow_mock_fallback else "singstat"

    iteration_count = 0

    try:
        for target in targets:
            if iteration_count >= MAX_REACT_ITERATIONS:
                logger.warning(
                    "Extraction agent reached maximum ReAct iterations (%d). Stopping loop.",
                    MAX_REACT_ITERATIONS,
                )
                break

            source = target.get("source", default_source)
            dataset_id = target.get("dataset_id")
            title = target.get("title", "Dataset")
            keywords = target.get("keywords", "employment")

            # -------------------------------------------------------------
            # Step 1: Discovery if dataset_id is missing or needs lookup
            # -------------------------------------------------------------
            if not dataset_id:
                iteration_count += 1
                act_search = {
                    "tool": "list_available_datasets",
                    "action": "list_available_datasets",
                    "parameters": {"source": source, "keywords": keywords},
                    "thought": (
                        f"Searching available datasets in source '{source}' "
                        f"matching keywords '{keywords}'."
                    ),
                }
                await _emit_step(
                    state,
                    StepType.ACT,
                    act_search,
                    active_db,
                    analysis_id,
                    analysis_uuid,
                )

                try:
                    search_results = await list_available_datasets.ainvoke(
                        {"source": source, "keywords": keywords}
                    )
                except Exception as exc:
                    search_results = []
                    logger.warning(
                        "Search failed in source '%s' for keywords '%s': %s",
                        source,
                        keywords,
                        exc,
                    )

                obs_search = {
                    "tool": "list_available_datasets",
                    "action": "list_available_datasets",
                    "result": search_results,
                    "count": len(search_results),
                    "observation": (
                        f"Discovered {len(search_results)} candidate datasets in source '{source}'."
                    ),
                }
                await _emit_step(
                    state,
                    StepType.OBSERVE,
                    obs_search,
                    active_db,
                    analysis_id,
                    analysis_uuid,
                )

                if search_results and isinstance(search_results, list):
                    dataset_id = search_results[0].get("id")
                    title = search_results[0].get("title", title)
                else:
                    err_msg = f"No matching datasets found for keywords '{keywords}' in source '{source}'."
                    state["extraction_errors"].append(err_msg)
                    continue

            # -------------------------------------------------------------
            # Step 2: Fetch dataset
            # -------------------------------------------------------------
            if iteration_count >= MAX_REACT_ITERATIONS:
                break

            iteration_count += 1
            time_filter = target.get("time_filter")
            fetch_params: dict[str, Any] = {"source": source, "dataset_id": dataset_id}
            if time_filter:
                fetch_params["time_filter"] = time_filter

            act_fetch = {
                "tool": "fetch_dataset",
                "action": "fetch_dataset",
                "parameters": fetch_params,
                "thought": (
                    f"Retrieving dataset '{dataset_id}' from source '{source}'"
                    + (f" with time filter '{time_filter}'" if time_filter else "")
                    + " in one go."
                ),
            }
            await _emit_step(
                state,
                StepType.ACT,
                act_fetch,
                active_db,
                analysis_id,
                analysis_uuid,
            )

            df_json = ""
            fetch_error: str | None = None
            try:
                df_json = await fetch_dataset.ainvoke(fetch_params)
            except Exception as exc:
                fetch_error = str(exc)
                logger.warning("fetch_dataset error for '%s:%s': %s", source, dataset_id, exc)

            # Check if empty data was returned
            is_empty = (
                not df_json
                or df_json.strip() == ""
                or '"data":[]' in df_json
                or '"data": []' in df_json
            )

            # If empty or error and source is external, attempt resilient mock fallback
            if (is_empty or fetch_error) and source != "mock_internal":
                try:
                    mock_id = (
                        "employment_by_sector"
                        if any(k in str(dataset_id).lower() for k in ("m810", "employ", "labor", "workforce"))
                        else dataset_id
                    )
                    fb_params: dict[str, Any] = {
                        "source": "mock_internal",
                        "dataset_id": mock_id,
                    }
                    if time_filter:
                        fb_params["time_filter"] = time_filter
                    fallback_df_json = await fetch_dataset.ainvoke(fb_params)
                    if (
                        fallback_df_json
                        and '"data":[]' not in fallback_df_json
                        and '"data": []' not in fallback_df_json
                    ):
                        df_json = fallback_df_json
                        source = "mock_internal"
                        dataset_id = mock_id
                        title = f"{title} (Mock Fallback)"
                        is_empty = False
                        fetch_error = None
                        logger.info("Fell back to mock_internal for dataset '%s'", mock_id)
                except Exception as fb_exc:
                    logger.debug("Mock fallback attempt failed: %s", fb_exc)

            # If still empty and discovery is possible, attempt search fallback
            if (is_empty or fetch_error) and keywords and iteration_count < MAX_REACT_ITERATIONS:
                try:
                    search_results = await list_available_datasets.ainvoke(
                        {"source": source, "keywords": keywords}
                    )
                    if search_results and search_results[0].get("id") != dataset_id:
                        fallback_id = search_results[0].get("id")
                        fb_search_params: dict[str, Any] = {"source": source, "dataset_id": fallback_id}
                        if time_filter:
                            fb_search_params["time_filter"] = time_filter
                        fallback_df_json = await fetch_dataset.ainvoke(fb_search_params)
                        if (
                            fallback_df_json
                            and '"data":[]' not in fallback_df_json
                            and '"data": []' not in fallback_df_json
                        ):
                            dataset_id = fallback_id
                            title = search_results[0].get("title", title)
                            df_json = fallback_df_json
                            is_empty = False
                            fetch_error = None
                except Exception:
                    pass

            if fetch_error or is_empty:
                raw_err = fetch_error or f"Dataset '{dataset_id}' from '{source}' is empty."
                err_text = format_user_friendly_error(raw_err)
                state["extraction_errors"].append(
                    f"Extraction failed for '{title}' (id={dataset_id}, source={source}): {err_text}"
                )
                obs_fetch = {
                    "tool": "fetch_dataset",
                    "action": "fetch_dataset",
                    "status": "error",
                    "error": err_text,
                    "observation": f"Failed to retrieve data for '{dataset_id}' from '{source}'.",
                }
                await _emit_step(
                    state,
                    StepType.OBSERVE,
                    obs_fetch,
                    active_db,
                    analysis_id,
                    analysis_uuid,
                )
                continue

            # Shrink data according to coordinator instructions so only requested slice is kept
            shrunk_summary = ""
            df_json, shrunk_rows, shrunk_summary = _shrink_dataframe(
                df_json, target.get("shrink_instructions")
            )

            obs_fetch = {
                "tool": "fetch_dataset",
                "action": "fetch_dataset",
                "status": "success",
                "observation": (
                    f"Successfully retrieved dataset '{dataset_id}' from source '{source}'."
                    + (f" {shrunk_summary}." if shrunk_summary else "")
                ),
            }
            await _emit_step(
                state,
                StepType.OBSERVE,
                obs_fetch,
                active_db,
                analysis_id,
                analysis_uuid,
            )

            # -------------------------------------------------------------
            # Step 3: Validate dataframe quality
            # -------------------------------------------------------------
            if iteration_count >= MAX_REACT_ITERATIONS:
                break

            iteration_count += 1
            act_val = {
                "tool": "validate_dataframe",
                "action": "validate_dataframe",
                "parameters": {"df_json": f"<DataFrame JSON ({len(df_json)} chars)>"},
                "thought": f"Executing quality validation checks on dataset '{dataset_id}'.",
            }
            await _emit_step(
                state,
                StepType.ACT,
                act_val,
                active_db,
                analysis_id,
                analysis_uuid,
            )

            try:
                dq_report = validate_dataframe.invoke({"df_json": df_json})
            except Exception as exc:
                dq_report = {
                    "passed": False,
                    "errors": [f"Validation exception: {exc}"],
                    "warnings": [],
                    "stats": {},
                }

            passed = dq_report.get("passed", False)
            obs_val = {
                "tool": "validate_dataframe",
                "action": "validate_dataframe",
                "status": "success" if passed else "warning",
                "passed": passed,
                "result": dq_report,
                "observation": (
                    f"Data quality checks {'passed' if passed else 'flagged issues'} "
                    f"with {len(dq_report.get('warnings', []))} warnings "
                    f"and {len(dq_report.get('errors', []))} errors."
                ),
            }
            await _emit_step(
                state,
                StepType.OBSERVE,
                obs_val,
                active_db,
                analysis_id,
                analysis_uuid,
            )

            # Accumulate quality errors if non-critical or critical
            if not passed and dq_report.get("errors"):
                for err in dq_report.get("errors", []):
                    state["extraction_errors"].append(
                        f"Quality check error for dataset '{dataset_id}': {err}"
                    )

            # -------------------------------------------------------------
            # Step 4: Populate state with dataset record
            # -------------------------------------------------------------
            dataset_record = {
                "source": source,
                "dataset_id": dataset_id,
                "title": title,
                "df_json": df_json,
                "metadata": {
                    "source": source,
                    "dataset_id": dataset_id,
                    "title": title,
                    **dq_report.get("stats", {}),
                },
                "dq_report": dq_report,
            }

            state["selected_datasets"].append(dataset_record)
            state["raw_data"][str(dataset_id)] = {
                "df_json": df_json,
                "metadata": dataset_record["metadata"],
                "dq_report": dq_report,
            }
            state["raw_data"][f"{source}:{dataset_id}"] = state["raw_data"][str(dataset_id)]

            # Populate raw_datasets list if callers inspect it
            if "raw_datasets" not in state:
                state["raw_datasets"] = []
            state["raw_datasets"].append(dataset_record)

            # Persist dataset and associate with analysis if DB session is active
            if active_db is not None and analysis_uuid is not None:
                try:
                    from app.crud.dataset import get_or_create_dataset, link_dataset_to_analysis
                    db_dataset, _ = await get_or_create_dataset(
                        db=active_db,
                        source=source,
                        source_id=str(dataset_id),
                        title=title,
                        row_count=dq_report.get("stats", {}).get("row_count"),
                        columns=dq_report.get("stats", {}).get("columns"),
                    )
                    await link_dataset_to_analysis(
                        db=active_db,
                        analysis_id=analysis_uuid,
                        dataset_id=db_dataset.id,
                    )
                except Exception as db_link_err:
                    logger.debug("Could not link dataset to analysis in DB: %s", db_link_err)

    except Exception as exc:
        logger.exception("Unexpected error occurred inside extraction_node: %s", exc)
        friendly_err = format_user_friendly_error(exc)
        state["extraction_errors"].append(f"Data extraction node error: {friendly_err}")
        err_content = {
            "thought": "Issue encountered during data extraction.",
            "error": friendly_err,
        }
        await _emit_step(
            state,
            StepType.ERROR,
            err_content,
            active_db,
            analysis_id,
            analysis_uuid,
        )

    # -----------------------------------------------------------------
    # Step 5: Finalize state and emit DONE step
    # -----------------------------------------------------------------
    selected_count = len(state.get("selected_datasets", []))
    errors_count = len(state.get("extraction_errors", []))

    if selected_count > 0:
        state["status"] = "extracted"
    elif errors_count > 2:
        state["status"] = "extraction_failed"
    else:
        state["status"] = "extracted"

    done_content = {
        "thought": (
            f"Data extraction phase completed. Retrieved {selected_count} dataset(s) "
            f"with {errors_count} error(s) logged."
        ),
        "selected_datasets_count": selected_count,
        "extraction_errors_count": errors_count,
        "selected_datasets": [
            {
                "source": d.get("source"),
                "dataset_id": d.get("dataset_id"),
                "title": d.get("title"),
            }
            for d in state.get("selected_datasets", [])
        ],
        "extraction_errors": state.get("extraction_errors", []),
    }

    await _emit_step(
        state,
        StepType.DONE,
        done_content,
        active_db,
        analysis_id,
        analysis_uuid,
    )

    return state
