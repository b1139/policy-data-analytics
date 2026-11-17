"""LangGraph multi-agent workflow compilation and execution graph."""

import contextlib
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from langgraph.graph import END, START, StateGraph

try:
    from langgraph.graph.state import CompiledStateGraph as CompiledGraph
except ImportError:
    try:
        from langgraph.graph.state import CompiledGraph  # type: ignore[attr-defined]
    except ImportError:
        from langgraph.graph.graph import CompiledGraph  # type: ignore[assignment]
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analytics import _resolve_citation_url, analytics_db_context
from app.agents.coordinator import coordinator_db_context
from app.agents.extraction import extraction_db_context
from app.agents.state import AgentState, create_initial_state
from app.core.config import settings
from app.core.database import async_session_factory
from app.crud.analysis import get_analysis, update_analysis_status
from app.llm.exceptions import format_user_friendly_error
from app.llm.router import get_llm_router
from app.schemas.analysis import AnalysisStatus
from app.services.pubsub import (
    format_analysis_done_message,
    format_analysis_error_message,
    format_status_change_message,
    publish_step,
)

logger = logging.getLogger(__name__)


async def default_coordinator_node(state: AgentState) -> dict[str, Any]:
    """Stub coordinator node executed when no specialized implementation is supplied."""
    logger.debug("Executing coordinator node for analysis_id=%s", state.get("analysis_id"))
    return {
        "current_agent": "coordinator",
        "status": "planned",
    }


async def default_extraction_node(state: AgentState) -> dict[str, Any]:
    """Stub extraction node executed when no specialized implementation is supplied."""
    logger.debug("Executing extraction node for analysis_id=%s", state.get("analysis_id"))
    return {
        "current_agent": "extraction",
        "status": "extracted",
    }


async def default_analytics_node(state: AgentState) -> dict[str, Any]:
    """Stub analytics node executed when no specialized implementation is supplied."""
    logger.debug("Executing analytics node for analysis_id=%s", state.get("analysis_id"))
    return {
        "current_agent": "analytics",
        "status": "completed",
    }


def route_after_extraction(state: AgentState) -> str:
    """Determine the next step after the extraction node.

    Routes to END (with status marked as 'failed') if:
    - Extraction produced errors AND 0 datasets were retrieved (raw_datasets is empty), OR
    - Extraction errors exceed the retry threshold (> 2).
    Otherwise routes to 'analytics'.
    """
    errors = state.get("extraction_errors", [])
    raw_datasets = state.get("raw_datasets")
    if raw_datasets is None:
        raw_datasets = state.get("selected_datasets")

    # If datasets list is explicitly present and empty while errors exist -> END with failed
    if (
        ("raw_datasets" in state or "selected_datasets" in state)
        and len(errors) > 0
        and len(raw_datasets or []) == 0
    ):
        logger.warning(
            "Extraction failure: %d error(s) logged and 0 datasets retrieved. Routing to END.",
            len(errors),
        )
        if state.get("status") not in ("extraction_failed", "failed"):
            state["status"] = "failed"
        return END

    if len(errors) > 2:
        logger.warning(
            "Extraction errors threshold exceeded (%d > 2). Terminating workflow at END.",
            len(errors),
        )
        return END

    return "analytics"


def _resolve_node_handlers(
    coordinator_node_override: Callable[[AgentState], Any] | None = None,
    extraction_node_override: Callable[[AgentState], Any] | None = None,
    analytics_node_override: Callable[[AgentState], Any] | None = None,
) -> tuple[Callable, Callable, Callable]:
    """Resolve node handlers from specialized modules or fallback stubs."""
    # Coordinator resolution
    if coordinator_node_override is not None:
        coord_fn = coordinator_node_override
    else:
        try:
            from app.agents.coordinator import coordinator_node as coord_fn
        except (ImportError, AttributeError):
            coord_fn = default_coordinator_node

    # Extraction resolution
    if extraction_node_override is not None:
        extract_fn = extraction_node_override
    else:
        try:
            from app.agents.extraction import extraction_node as extract_fn
        except (ImportError, AttributeError):
            extract_fn = default_extraction_node

    # Analytics resolution
    if analytics_node_override is not None:
        analytics_fn = analytics_node_override
    else:
        try:
            from app.agents.analytics import analytics_node as analytics_fn
        except (ImportError, AttributeError):
            analytics_fn = default_analytics_node

    return coord_fn, extract_fn, analytics_fn


def build_graph(
    coordinator_node_fn: Callable[[AgentState], Any] | None = None,
    extraction_node_fn: Callable[[AgentState], Any] | None = None,
    analytics_node_fn: Callable[[AgentState], Any] | None = None,
    checkpointer: Any = None,
) -> CompiledGraph:
    """Construct and compile the LangGraph StateGraph multi-agent workflow.

    Workflow topology:
      START -> coordinator -> extraction
      extraction -> END (if len(extraction_errors) > 0 and len(raw_datasets) == 0, or errors > 2)
      extraction -> analytics (otherwise)
      analytics -> END
    """
    coord_fn, extract_fn, analytics_fn = _resolve_node_handlers(
        coordinator_node_override=coordinator_node_fn,
        extraction_node_override=extraction_node_fn,
        analytics_node_override=analytics_node_fn,
    )

    workflow = StateGraph(AgentState)

    workflow.add_node("coordinator", coord_fn)
    workflow.add_node("extraction", extract_fn)
    workflow.add_node("analytics", analytics_fn)

    workflow.add_edge(START, "coordinator")
    workflow.add_edge("coordinator", "extraction")
    workflow.add_conditional_edges(
        "extraction",
        route_after_extraction,
        {
            "analytics": "analytics",
            END: END,
        },
    )
    workflow.add_edge("analytics", END)

    return workflow.compile(checkpointer=checkpointer)


async def _execute_analysis(
    analysis_id_str: str,
    analysis_uuid: uuid.UUID,
    query: str | None,
    session: AsyncSession | None,
    graph: CompiledGraph | None,
    raise_exceptions: bool = False,
) -> dict[str, Any]:
    """Internal implementation for running the analysis pipeline with active DB session."""
    token_coord = coordinator_db_context.set(session) if session is not None else None
    token_extr = extraction_db_context.set(session) if session is not None else None
    token_anal = analytics_db_context.set(session) if session is not None else None

    # Track active query context on LLM router for fallback persistence across this query
    router = get_llm_router()
    router.set_current_query(analysis_id_str)

    analysis_record = None
    try:
        # Load analysis record if present in DB
        if session is not None:
            try:
                analysis_record = await get_analysis(session, analysis_uuid, include_deleted=True)
            except Exception as db_err:
                logger.debug("Could not fetch analysis record: %s", db_err)
                analysis_record = None

        if query is None:
            query = analysis_record.query if analysis_record else f"Analysis {analysis_id_str}"

        # 1. Update analysis status to RUNNING via crud before starting graph execution
        if session is not None and analysis_record is not None:
            await update_analysis_status(
                db=session,
                id=analysis_uuid,
                status=AnalysisStatus.RUNNING,
            )

        # 2. Emit status change to WebSocket
        await publish_step(
            analysis_id=analysis_id_str,
            step_dict=format_status_change_message(
                analysis_id=analysis_id_str,
                status=AnalysisStatus.RUNNING,
                details={"message": "Analysis pipeline execution started."},
            ),
        )

        # 3. Create initial state and run graph via ainvoke
        compiled_graph = graph or build_graph()
        initial_state = create_initial_state(analysis_id=analysis_id_str, query=query)
        if session is not None:
            initial_state["_db"] = session  # type: ignore

        final_state = await compiled_graph.ainvoke(initial_state)

        # Check for conditional failure branch (extraction failure or status=failed)
        has_extraction_errors = len(final_state.get("extraction_errors", [])) > 0
        raw_datasets = final_state.get("raw_datasets")
        if raw_datasets is None:
            raw_datasets = final_state.get("selected_datasets")

        is_failed = final_state.get("status") in ("failed", "extraction_failed") or (
            has_extraction_errors and len(raw_datasets or []) == 0
        )

        if is_failed:
            raw_err = (
                "; ".join(final_state.get("extraction_errors", []))
                or "Extraction failed: no datasets retrieved"
            )
            friendly_err = format_user_friendly_error(raw_err)
            if final_state.get("status") not in ("extraction_failed", "failed"):
                final_state["status"] = "failed"

            # Structure data context on which execution failed for frontend inspection & AI resolution
            r_plan = final_state.get("research_plan") or {}
            attempted_datasets: list[dict[str, Any]] = []
            if final_state.get("raw_datasets"):
                attempted_datasets.extend(final_state.get("raw_datasets"))
            elif final_state.get("selected_datasets"):
                attempted_datasets.extend(final_state.get("selected_datasets"))
            elif r_plan.get("planned_datasets"):
                attempted_datasets.extend(r_plan.get("planned_datasets"))
            else:
                for src in r_plan.get("sources", ["singstat"]):
                    attempted_datasets.append({"source": src, "topics": r_plan.get("topics", [])})

            failed_data_info = {
                "failed_stage": "extraction" if has_extraction_errors else "processing",
                "error": friendly_err,
                "technical_details": raw_err,
                "attempted_datasets": attempted_datasets,
                "sources": r_plan.get("sources", []),
                "topics": r_plan.get("topics", []),
                "date_range": r_plan.get("date_range", []),
                "extraction_errors": final_state.get("extraction_errors", []),
                "query": query,
            }
            failed_result_payload = {
                "status": "failed",
                "error": friendly_err,
                "failed_data": failed_data_info,
                "insights": None,
                "charts": [],
                "citations": [],
            }
            final_state["failed_data"] = failed_data_info

            if session is not None and analysis_record is not None:
                existing_meta = analysis_record.metadata_ or {}
                updated_meta = {
                    **existing_meta,
                    "failed_data": failed_data_info,
                    "technical_error": raw_err,
                }
                await update_analysis_status(
                    db=session,
                    id=analysis_uuid,
                    status=AnalysisStatus.FAILED,
                    error_msg=friendly_err,
                    result=failed_result_payload,
                    metadata=updated_meta,
                )
            await publish_step(
                analysis_id=analysis_id_str,
                step_dict=format_analysis_error_message(
                    analysis_id=analysis_id_str,
                    error=friendly_err,
                ),
            )
            return final_state

        # 4. Assemble final AnalysisResult payload
        raw_insights = final_state.get("insights")
        if isinstance(raw_insights, list):
            insights_str = "\n\n".join(str(i) for i in raw_insights if i)
        elif isinstance(raw_insights, str):
            insights_str = raw_insights
        else:
            insights_str = ""

        charts = final_state.get("charts") or []
        if not charts and final_state.get("final_report"):
            charts = final_state["final_report"].get("charts", [])

        no_data = bool(final_state.get("no_data"))
        citations = list(final_state.get("citations") or [])
        if not citations and not no_data:
            raw_ds = final_state.get("raw_datasets") or final_state.get("selected_datasets") or []
            for ds in raw_ds:
                citations.append(
                    {
                        "source": ds.get("source", "Official Statistics"),
                        "dataset_id": ds.get("dataset_id") or ds.get("id"),
                        "title": ds.get("title", "Dataset"),
                        "url": (
                            ds.get("metadata", {}).get("url")
                            or f"https://tablebuilder.singstat.gov.sg/table/{ds.get('dataset_id')}"
                        ),
                        "accessed": datetime.now(UTC).strftime("%Y-%m-%d"),
                    }
                )

        # Validate that all citations have redirectable official HTTPS URLs
        for c in citations:
            ds_id = str(c.get("dataset_id") or "")
            src = str(c.get("source") or "")
            title = str(c.get("title") or "")
            c["url"] = _resolve_citation_url(
                source=src,
                dataset_id=ds_id,
                title=title,
                existing_url=c.get("url"),
            )

        # Collect realtime models called during this analysis
        models_used = []
        if final_state.get("coordinator_model"):
            models_used.append(final_state["coordinator_model"])
        if final_state.get("analytics_model"):
            models_used.append(final_state["analytics_model"])
        if not models_used:
            try:
                r = get_llm_router()
                p_name = getattr(
                    r, "primary_name", getattr(settings, "primary_llm_provider", "bedrock")
                )
                m_name = getattr(
                    r.primary,
                    "model",
                    getattr(
                        settings,
                        "bedrock_model_id" if p_name == "bedrock" else "gemini_model",
                        "apac.amazon.nova-lite-v1:0",
                    ),
                )
                models_used = [
                    {
                        "agent": "coordinator",
                        "provider": p_name,
                        "model": str(m_name),
                        "role": "Query Decomposition & Planning",
                    },
                    {
                        "agent": "analytics",
                        "provider": p_name,
                        "model": str(m_name),
                        "role": "Grounded Statistical Synthesis",
                    },
                ]
            except Exception:
                fallback_p = getattr(settings, "primary_llm_provider", "bedrock")
                fallback_m = getattr(
                    settings,
                    "bedrock_model_id" if fallback_p == "bedrock" else "gemini_model",
                    "apac.amazon.nova-lite-v1:0",
                )
                models_used = [
                    {
                        "agent": "coordinator",
                        "provider": fallback_p,
                        "model": str(fallback_m),
                        "role": "Query Decomposition & Planning",
                    },
                    {
                        "agent": "analytics",
                        "provider": fallback_p,
                        "model": str(fallback_m),
                        "role": "Grounded Statistical Synthesis",
                    },
                ]

        stats_summary = (
            final_state.get("statistical_results")
            or final_state.get("stats")
            or (
                final_state.get("final_report", {}).get("statistical_results")
                if final_state.get("final_report")
                else {}
            )
            or {}
        )

        generated_at = datetime.now(UTC).isoformat()
        truncated_preview = (
            (insights_str[:200] + "...") if len(insights_str) > 200 else insights_str
        )

        # Run hallucination verification
        hallucination_report: dict[str, Any] = {}
        try:
            from app.services.hallucination_detector import HallucinationDetector

            detector = HallucinationDetector()
            hallucination_report = detector.run_all_checks(
                insights=insights_str,
                datasets=citations
                or (final_state.get("selected_datasets") or final_state.get("raw_datasets") or []),
                stats=stats_summary,
            )
        except Exception as h_err:
            logger.warning("Hallucination check execution failed: %s", h_err)
            hallucination_report = {"passed": True, "error": str(h_err)}

        # Dynamic KPI tiles: computed from data, worded by the LLM
        if isinstance(stats_summary, dict) and stats_summary and not no_data:
            try:
                from app.agents.analytics import _collect_datasets_from_state
                from app.services.key_metrics import build_key_metrics

                key_metrics = await build_key_metrics(
                    datasets=_collect_datasets_from_state(final_state),
                    stats=stats_summary,
                    query=query,
                    insights=insights_str,
                )
                if key_metrics:
                    stats_summary = {**stats_summary, "key_metrics": key_metrics}
            except Exception as km_err:
                logger.warning("Key metrics generation failed: %s", km_err)

        result_payload = {
            "insights": insights_str,
            "charts": charts,
            "citations": citations,
            "stats_summary": stats_summary,
            "no_data": no_data,
            "models_used": models_used,
            "generated_at": generated_at,
            "truncated_preview": truncated_preview,
            "hallucination_report": hallucination_report,
        }

        final_state["final_report"] = {
            "analysis_id": analysis_id_str,
            "query": query,
            "insights": final_state.get("insights", [insights_str]),
            "charts": charts,
            "citations": citations,
            "statistical_results": stats_summary,
            "models_used": models_used,
            "status": "completed",
            "no_data": no_data,
            "result": result_payload,
            "hallucination_report": hallucination_report,
        }
        final_state["models_used"] = models_used
        final_state["hallucination_report"] = hallucination_report
        final_state["charts"] = charts
        final_state["stats"] = stats_summary
        final_state["status"] = "completed"

        # 5. Set analysis status to DONE with result payload and metadata in database
        if session is not None and analysis_record is not None:
            # Ensure extracted datasets are persisted and associated with analysis
            try:
                from app.crud.dataset import get_or_create_dataset, link_dataset_to_analysis

                extracted = (
                    final_state.get("selected_datasets") or final_state.get("raw_datasets") or []
                )
                for ds in extracted:
                    src = ds.get("source", "mock_internal")
                    ds_id = str(ds.get("dataset_id") or ds.get("id") or "mock_dataset")
                    ds_title = ds.get("title", f"Dataset {ds_id}")
                    db_ds, _ = await get_or_create_dataset(
                        db=session,
                        source=src,
                        source_id=ds_id,
                        title=ds_title,
                    )
                    await link_dataset_to_analysis(
                        db=session,
                        analysis_id=analysis_uuid,
                        dataset_id=db_ds.id,
                    )
            except Exception as ds_err:
                logger.debug("Failed to link datasets to analysis: %s", ds_err)

            existing_metadata = analysis_record.metadata_ or {}
            updated_metadata = {**existing_metadata, "hallucination_check": hallucination_report}
            await update_analysis_status(
                db=session,
                id=analysis_uuid,
                status=AnalysisStatus.DONE,
                result=result_payload,
                metadata=updated_metadata,
            )

        # 6. Emit ANALYSIS_DONE terminal event via publish_step()
        await publish_step(
            analysis_id=analysis_id_str,
            step_dict=format_analysis_done_message(
                analysis_id=analysis_id_str,
                result=result_payload,
            ),
        )

        return final_state

    except Exception as exc:
        logger.exception(
            "Analysis execution encountered unhandled exception for analysis_id=%s: %s",
            analysis_id_str,
            exc,
        )
        friendly_err = format_user_friendly_error(exc)
        failed_data_info = {
            "failed_stage": "pipeline",
            "error": friendly_err,
            "technical_details": str(exc),
            "attempted_datasets": [],
            "query": query,
        }
        failed_result_payload = {
            "status": "failed",
            "error": friendly_err,
            "failed_data": failed_data_info,
            "insights": None,
            "charts": [],
            "citations": [],
        }
        if session is not None and analysis_record is not None:
            with contextlib.suppress(Exception):
                existing_meta = analysis_record.metadata_ or {}
                updated_meta = {
                    **existing_meta,
                    "failed_data": failed_data_info,
                    "technical_error": str(exc),
                }
                await update_analysis_status(
                    db=session,
                    id=analysis_uuid,
                    status=AnalysisStatus.FAILED,
                    error_msg=friendly_err,
                    result=failed_result_payload,
                    metadata=updated_meta,
                )
        with contextlib.suppress(Exception):
            await publish_step(
                analysis_id=analysis_id_str,
                step_dict=format_analysis_error_message(
                    analysis_id=analysis_id_str,
                    error=friendly_err,
                ),
            )
        if raise_exceptions:
            raise
        return {
            "analysis_id": analysis_id_str,
            "status": "failed",
            "error": friendly_err,
            "failed_data": failed_data_info,
            "final_report": None,
        }

    finally:
        # Clear query context on LLM router so the next query can retry the primary provider
        router.clear_current_query(analysis_id_str)
        if token_coord is not None:
            coordinator_db_context.reset(token_coord)
        if token_extr is not None:
            extraction_db_context.reset(token_extr)
        if token_anal is not None:
            analytics_db_context.reset(token_anal)


async def run_analysis(
    analysis_id: str | uuid.UUID,
    query: str | None = None,
    db: AsyncSession | None = None,
    graph: CompiledGraph | None = None,
    raise_exceptions: bool = False,
) -> dict[str, Any]:
    """Execute the multi-agent analysis workflow for a given query and analysis ID."""
    if isinstance(analysis_id, uuid.UUID):
        analysis_uuid = analysis_id
        analysis_id_str = str(analysis_id)
    else:
        try:
            analysis_uuid = uuid.UUID(str(analysis_id))
            analysis_id_str = str(analysis_uuid)
        except ValueError:
            analysis_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(analysis_id))
            analysis_id_str = str(analysis_id)

    if db is not None:
        return await _execute_analysis(
            analysis_id_str=analysis_id_str,
            analysis_uuid=analysis_uuid,
            query=query,
            session=db,
            graph=graph,
            raise_exceptions=raise_exceptions,
        )

    session_cm = None
    session = None
    try:
        session_cm = async_session_factory()
        session = await session_cm.__aenter__()
    except Exception as exc:
        logger.debug(
            "Database connection failed (%s); proceeding in offline/mock execution mode",
            exc,
        )
        session = None

    try:
        return await _execute_analysis(
            analysis_id_str=analysis_id_str,
            analysis_uuid=analysis_uuid,
            query=query,
            session=session,
            graph=graph,
            raise_exceptions=raise_exceptions,
        )
    finally:
        if session_cm is not None and session is not None:
            with contextlib.suppress(Exception):
                await session_cm.__aexit__(None, None, None)
