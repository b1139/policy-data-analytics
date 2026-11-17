"""REST API endpoints for policy data analysis management."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_analysis
from app.core.config import settings
from app.core.database import get_db
from app.crud.analysis import (
    count_analyses,
    create_analysis,
    delete_analysis,
    get_analysis,
    list_analyses,
    update_analysis_status,
)
from app.llm.exceptions import format_user_friendly_error
from app.schemas.analysis import (
    AnalysisListResponse,
    AnalysisResponse,
    AnalysisStartRequest,
    AnalysisStartResponse,
    AnalysisStatus,
)
from app.services.analysis_service import AnalysisService

logger = logging.getLogger(__name__)

__all__ = [
    "get_analysis_by_id",
    "router",
    "run_analysis",
    "run_analysis_pipeline",
    "start_analysis",
]

router = APIRouter(prefix="/analysis", tags=["Analysis"])


async def run_analysis_pipeline(analysis_id: uuid.UUID) -> None:
    """Execute asynchronous multi-agent policy data analysis pipeline.

    Enqueued as a background task upon analysis initiation. Runs the service
    pipeline and broadcasts real-time steps over Redis pubsub.

    Args:
        analysis_id: UUID of the persisted analysis record to process.
    """
    logger.info("Executing background analysis pipeline for analysis_id=%s", analysis_id)
    await AnalysisService.run_pipeline(analysis_id)


@router.post(
    "/start",
    response_model=AnalysisStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a natural-language query and start an analysis pipeline",
    responses={
        201: {
            "description": "Analysis pipeline queued successfully.",
            "model": AnalysisStartResponse,
        },
        422: {"description": "Validation error (e.g. query length outside 10-2000 chars)."},
    },
)
async def start_analysis(
    payload: AnalysisStartRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalysisStartResponse:
    """Initiate a multi-agent policy analysis task.

    Validates natural language query parameters, creates a persistent analysis job in
    the database in PENDING status, enqueues the async agent execution background task,
    and returns connection metadata including the WebSocket streaming URL.

    Example:
    ```bash
    curl -X POST "http://localhost:8000/api/v1/analysis/start" \\
         -H "Content-Type: application/json" \\
         -d '{"query": "What is the 5-year trend in Singapore consumer price index?"}'
    ```
    """
    logger.debug("Received analysis request: query_length=%d", len(payload.query))

    try:
        analysis = await create_analysis(
            db=db,
            query=payload.query,
            metadata=payload.metadata,
            status=AnalysisStatus.PENDING,
        )
    except Exception as exc:
        logger.error("Failed to create analysis record: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate analysis job in database.",
        ) from exc

    # Enqueue background agent execution task
    background_tasks.add_task(run_analysis_pipeline, analysis.id)

    ws_base = settings.NEXT_PUBLIC_WS_URL.rstrip("/")
    ws_url = f"{ws_base}/ws/analysis/{analysis.id}"

    logger.debug("Enqueued analysis job: analysis_id=%s, ws_url=%s", analysis.id, ws_url)
    return AnalysisStartResponse(
        analysis_id=analysis.id,
        status=str(analysis.status),
        ws_url=ws_url,
    )


@router.post(
    "/{id}/rerun",
    response_model=AnalysisStartResponse,
    status_code=status.HTTP_200_OK,
    summary="Re-run a previously failed or executed analysis pipeline",
    responses={
        200: {
            "description": "Analysis pipeline successfully re-queued for execution.",
            "model": AnalysisStartResponse,
        },
        404: {"description": "Analysis record not found or soft-deleted."},
    },
)
async def rerun_analysis(
    id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalysisStartResponse:
    """Re-run a policy analysis task from scratch.

    Resets the analysis status to PENDING, clears past error messages,
    re-enqueues the async agent execution background task, and returns the
    streaming WebSocket URL.
    """
    logger.info("Re-running analysis for id=%s", id)

    analysis = await get_analysis(db=db, id=id, include_deleted=False)
    if analysis is None:
        logger.debug("Cannot re-run: analysis %s not found or deleted", id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {id} not found",
        )

    # Reset analysis status to PENDING and clear error
    try:
        await update_analysis_status(
            db=db,
            id=id,
            status=AnalysisStatus.PENDING,
            error_msg=None,
        )
    except Exception as exc:
        logger.error("Failed to reset analysis record status for %s: %s", id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update analysis status in database.",
        ) from exc

    # Enqueue background agent execution task
    background_tasks.add_task(run_analysis_pipeline, analysis.id)

    ws_base = settings.NEXT_PUBLIC_WS_URL.rstrip("/")
    ws_url = f"{ws_base}/ws/analysis/{analysis.id}"

    return AnalysisStartResponse(
        analysis_id=analysis.id,
        status=str(AnalysisStatus.PENDING),
        ws_url=ws_url,
    )


@router.post(
    "/{id}/resolve-data",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Use AI to diagnose data loading failure, discover alternative official tables, and resolve",
    responses={
        200: {
            "description": "Analysis data loading resolved successfully with generated report.",
            "model": AnalysisResponse,
        },
        404: {"description": "Analysis record not found or soft-deleted."},
        500: {"description": "AI resolution encountered an error."},
    },
)
async def resolve_analysis_data(
    id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalysisResponse:
    """Diagnose and resolve failed data loading using AI assistance.

    Examines the failed query and attempted data context, uses the LLM to identify
    the correct official Singapore government data tables or catalog keywords,
    re-executes data extraction, and completes the analytics pipeline.
    """
    logger.info("Request to resolve data with AI for analysis_id=%s", id)

    analysis = await get_analysis(db=db, id=id, include_deleted=False, include_logs=True)
    if analysis is None:
        logger.debug("Cannot resolve: analysis %s not found or deleted", id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {id} not found",
        )

    try:
        await AnalysisService.resolve_failed_data(id)
        # Fetch updated record with logs
        updated = await get_analysis(db=db, id=id, include_deleted=False, include_logs=True)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis {id} not found after resolution",
            )
        if updated.agent_logs:
            updated.agent_logs.sort(key=lambda item: item.sequence_no)
        return AnalysisResponse.model_validate(updated)
    except Exception as exc:
        logger.exception("AI data resolution failed for %s: %s", id, exc)
        friendly = format_user_friendly_error(exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI data resolution could not complete: {friendly}",
        ) from exc


@router.get(
    "/{id}",
    response_model=AnalysisResponse,
    summary="Fetch detailed analysis record including chronological agent logs",
    responses={
        200: {
            "description": "Full analysis details with agent step logs.",
            "model": AnalysisResponse,
        },
        404: {"description": "Analysis record not found or soft-deleted."},
    },
)
async def get_analysis_by_id(
    id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalysisResponse:
    """Retrieve full analysis report and historical execution trace.

    Fetches the complete analysis result including synthesized narrative insights,
    generated Plotly chart specifications, source citations, and all agent execution logs
    sorted chronologically by sequence number.

    Example:
    ```bash
    curl -X GET "http://localhost:8000/api/v1/analysis/550e8400-e29b-41d4-a716-446655440000"
    ```
    """
    logger.debug("Fetching analysis details for id=%s", id)

    analysis = await get_analysis(db=db, id=id, include_deleted=False, include_logs=True)
    if analysis is None:
        logger.debug("Analysis %s not found or marked deleted", id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {id} not found",
        )

    # Ensure logs are ordered by sequence_no
    if analysis.agent_logs:
        analysis.agent_logs.sort(key=lambda item: item.sequence_no)

    return AnalysisResponse.model_validate(analysis)


@router.get(
    "",
    response_model=AnalysisListResponse,
    include_in_schema=False,
)
@router.get(
    "/",
    response_model=AnalysisListResponse,
    summary="Retrieve paginated list of policy analyses",
    responses={
        200: {
            "description": "Paginated collection of analysis records.",
            "model": AnalysisListResponse,
        },
    },
)
async def list_analyses_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Max number of records to return")] = 20,
) -> AnalysisListResponse:
    """Retrieve a paginated collection of past analyses.

    Excludes soft-deleted analysis runs. Returns summary metadata suitable for dashboard
    listing and history tables.

    Example:
    ```bash
    curl -X GET "http://localhost:8000/api/v1/analysis/?skip=0&limit=20"
    ```
    """
    logger.debug("Listing analyses: skip=%d, limit=%d", skip, limit)

    analyses = await list_analyses(db=db, skip=skip, limit=limit, include_deleted=False)
    total = await count_analyses(db=db, include_deleted=False)

    return AnalysisListResponse(
        items=analyses,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{id}/export",
    summary="Export full analysis results and logs as a downloadable JSON file",
    responses={
        200: {
            "description": "Downloadable JSON file payload.",
            "content": {"application/json": {}},
        },
        404: {"description": "Analysis record not found or soft-deleted."},
    },
)
async def export_analysis(
    id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Download the complete analysis payload as a formatted JSON document.

    Sets Content-Disposition header with filename 'analysis_{id}.json' to prompt
    browser file download.

    Example:
    ```bash
    curl -X GET "http://localhost:8000/api/v1/analysis/550e8400-e29b-41d4-a716-446655440000/export" -OJ
    ```
    """
    logger.debug("Exporting analysis id=%s", id)

    analysis = await get_analysis(db=db, id=id, include_deleted=False, include_logs=True)
    if analysis is None:
        logger.debug("Cannot export: analysis %s not found or deleted", id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {id} not found",
        )

    if analysis.agent_logs:
        analysis.agent_logs.sort(key=lambda item: item.sequence_no)

    payload = AnalysisResponse.model_validate(analysis).model_dump(mode="json")
    headers = {"Content-Disposition": f'attachment; filename="analysis_{id}.json"'}

    return JSONResponse(
        content=payload,
        status_code=status.HTTP_200_OK,
        headers=headers,
        media_type="application/json",
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete an analysis record",
    responses={
        204: {"description": "Analysis successfully soft-deleted."},
        404: {"description": "Analysis record not found or already deleted."},
    },
)
async def delete_analysis_endpoint(
    id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Soft delete an analysis by setting its status to DELETED.

    Soft-deleted analyses will no longer appear in query listings or single fetches.

    Example:
    ```bash
    curl -X DELETE "http://localhost:8000/api/v1/analysis/550e8400-e29b-41d4-a716-446655440000"
    ```
    """
    logger.debug("Deleting analysis id=%s", id)

    deleted = await delete_analysis(db=db, id=id, soft=True)
    if not deleted:
        logger.debug("Delete failed: analysis %s not found or already deleted", id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {id} not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
