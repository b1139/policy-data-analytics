"""Unit and integration tests for analysis REST API endpoints."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import Base, get_db
from app.crud.agent_log import create_agent_log
from app.crud.analysis import create_analysis, delete_analysis, update_analysis_status
from app.main import app
from app.schemas.analysis import AnalysisStatus


@pytest_asyncio.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite async database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def client(async_db: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create an asynchronous HTTP client with database dependency override."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield async_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# =====================================================================
# POST /api/v1/analysis/start
# =====================================================================


@pytest.mark.asyncio
async def test_start_analysis_success(client: httpx.AsyncClient):
    """Test POST /api/v1/analysis/start creates an analysis and enqueues background task."""
    with patch("app.api.v1.analysis.run_analysis_pipeline", new_callable=AsyncMock) as mock_task:
        payload = {
            "query": "What is the 5-year trend in Singapore's consumer price index (CPI)?",
            "metadata": {"preferred_source": "singstat"},
        }
        response = await client.post("/api/v1/analysis/start", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert "analysis_id" in data
        analysis_id = uuid.UUID(data["analysis_id"])
        assert analysis_id is not None
        assert data["status"] == "PENDING"
        assert f"/ws/analysis/{analysis_id}" in data["ws_url"]
        assert data["ws_url"].startswith("ws://")

        # Verify background task was scheduled
        mock_task.assert_called_once_with(analysis_id)


@pytest.mark.asyncio
async def test_start_analysis_validation_too_short(client: httpx.AsyncClient):
    """Test POST /api/v1/analysis/start rejects queries shorter than 10 chars."""
    response = await client.post(
        "/api/v1/analysis/start",
        json={"query": "Short"},
    )
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_start_analysis_validation_whitespace_only(client: httpx.AsyncClient):
    """Test POST /api/v1/analysis/start rejects queries with only whitespace."""
    response = await client.post(
        "/api/v1/analysis/start",
        json={"query": "            "},
    )
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_start_analysis_validation_too_long(client: httpx.AsyncClient):
    """Test POST /api/v1/analysis/start rejects queries longer than 2000 chars."""
    long_query = "A" * 2001
    response = await client.post(
        "/api/v1/analysis/start",
        json={"query": long_query},
    )
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_start_analysis_missing_query(client: httpx.AsyncClient):
    """Test POST /api/v1/analysis/start rejects requests missing query field."""
    response = await client.post(
        "/api/v1/analysis/start",
        json={"metadata": {"test": "val"}},
    )
    assert response.status_code == 422


# =====================================================================
# GET /api/v1/analysis/{id}
# =====================================================================


@pytest.mark.asyncio
async def test_get_analysis_success_with_ordered_logs(
    client: httpx.AsyncClient,
    async_db: AsyncSession,
):
    """Test GET /api/v1/analysis/{id} returns full analysis response with ordered logs."""
    analysis = await create_analysis(
        db=async_db,
        query="Analyze Singapore median household income trends from 2018 to 2023.",
        metadata={"domain": "economics"},
    )
    await update_analysis_status(
        db=async_db,
        id=analysis.id,
        status=AnalysisStatus.DONE,
        result={"summary": "Median income grew steadily", "growth_rate": 3.8},
    )

    # Insert logs in intentionally shuffled sequence order
    await create_agent_log(
        db=async_db,
        analysis_id=analysis.id,
        agent_name="analytics",
        step_type="DONE",
        content={"summary": "Completed analytics calculations"},
        seq_no=3,
    )
    await create_agent_log(
        db=async_db,
        analysis_id=analysis.id,
        agent_name="coordinator",
        step_type="THINK",
        content={"thought": "Formulating research plan"},
        seq_no=1,
    )
    await create_agent_log(
        db=async_db,
        analysis_id=analysis.id,
        agent_name="extraction",
        step_type="ACT",
        content={"tool": "singstat_fetch"},
        seq_no=2,
    )

    response = await client.get(f"/api/v1/analysis/{analysis.id}")
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(analysis.id)
    assert data["query"] == "Analyze Singapore median household income trends from 2018 to 2023."
    assert data["status"] == "DONE"
    assert data["result"]["growth_rate"] == 3.8
    assert data["metadata"]["domain"] == "economics"

    # Verify agent logs are present and correctly ordered by sequence_no
    assert len(data["agent_logs"]) == 3
    assert [log["sequence_no"] for log in data["agent_logs"]] == [1, 2, 3]
    assert data["agent_logs"][0]["agent_name"] == "coordinator"
    assert data["agent_logs"][1]["agent_name"] == "extraction"
    assert data["agent_logs"][2]["agent_name"] == "analytics"


@pytest.mark.asyncio
async def test_get_analysis_not_found(client: httpx.AsyncClient):
    """Test GET /api/v1/analysis/{id} returns 404 when ID does not exist."""
    random_id = uuid.uuid4()
    response = await client.get(f"/api/v1/analysis/{random_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == f"Analysis {random_id} not found"


@pytest.mark.asyncio
async def test_get_analysis_soft_deleted_returns_404(
    client: httpx.AsyncClient,
    async_db: AsyncSession,
):
    """Test GET /api/v1/analysis/{id} returns 404 when analysis is soft deleted."""
    analysis = await create_analysis(
        db=async_db,
        query="Policy study on public transport ridership trends.",
    )
    await delete_analysis(db=async_db, id=analysis.id, soft=True)

    response = await client.get(f"/api/v1/analysis/{analysis.id}")
    assert response.status_code == 404
    assert response.json()["detail"] == f"Analysis {analysis.id} not found"


# =====================================================================
# GET /api/v1/analysis/ (Pagination)
# =====================================================================


@pytest.mark.asyncio
async def test_list_analyses_empty(client: httpx.AsyncClient):
    """Test GET /api/v1/analysis/ returns empty items list when database is empty."""
    response = await client.get("/api/v1/analysis/")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["skip"] == 0
    assert data["limit"] == 20


@pytest.mark.asyncio
async def test_list_analyses_pagination_and_soft_delete_filter(
    client: httpx.AsyncClient,
    async_db: AsyncSession,
):
    """Test GET /api/v1/analysis/ with skip and limit, ensuring soft-deleted are excluded."""
    # Create 5 analyses
    created = []
    for i in range(5):
        a = await create_analysis(
            db=async_db, query=f"Analysis question number {i:02d} for testing"
        )
        created.append(a)

    # Soft-delete the 3rd one
    await delete_analysis(db=async_db, id=created[2].id, soft=True)

    # Active analyses should now be 4
    response = await client.get("/api/v1/analysis/?skip=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    assert len(data["items"]) == 2
    assert data["skip"] == 0
    assert data["limit"] == 2

    # Verify no DELETED record in items
    for item in data["items"]:
        assert item["status"] != "DELETED"

    # Next page
    response_p2 = await client.get("/api/v1/analysis/?skip=2&limit=2")
    assert response_p2.status_code == 200
    data_p2 = response_p2.json()
    assert data_p2["total"] == 4
    assert len(data_p2["items"]) == 2
    assert data_p2["skip"] == 2


@pytest.mark.asyncio
async def test_list_analyses_without_trailing_slash(client: httpx.AsyncClient):
    """Test GET /api/v1/analysis route without trailing slash returns 200."""
    response = await client.get("/api/v1/analysis")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


# =====================================================================
# GET /api/v1/analysis/{id}/export
# =====================================================================


@pytest.mark.asyncio
async def test_export_analysis_success(
    client: httpx.AsyncClient,
    async_db: AsyncSession,
):
    """Test GET /api/v1/analysis/{id}/export returns JSON file download with Content-Disposition."""
    analysis = await create_analysis(
        db=async_db,
        query="Export test: Singapore inflation and wage growth correlation.",
        metadata={"model": "gemini-1.5-flash"},
    )
    await update_analysis_status(
        db=async_db,
        id=analysis.id,
        status=AnalysisStatus.DONE,
        result={"correlation": 0.72, "charts": [{"type": "scatter"}]},
    )

    response = await client.get(f"/api/v1/analysis/{analysis.id}/export")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")
    expected_header = f'attachment; filename="analysis_{analysis.id}.json"'
    assert response.headers["Content-Disposition"] == expected_header

    data = response.json()
    assert data["id"] == str(analysis.id)
    assert data["result"]["correlation"] == 0.72
    assert data["status"] == "DONE"


@pytest.mark.asyncio
async def test_export_analysis_not_found(client: httpx.AsyncClient):
    """Test GET /api/v1/analysis/{id}/export returns 404 for non-existent analysis."""
    random_id = uuid.uuid4()
    response = await client.get(f"/api/v1/analysis/{random_id}/export")
    assert response.status_code == 404
    assert response.json()["detail"] == f"Analysis {random_id} not found"


@pytest.mark.asyncio
async def test_export_analysis_soft_deleted_returns_404(
    client: httpx.AsyncClient,
    async_db: AsyncSession,
):
    """Test GET /api/v1/analysis/{id}/export returns 404 for soft-deleted analysis."""
    analysis = await create_analysis(
        db=async_db,
        query="Export test for deleted analysis record.",
    )
    await delete_analysis(db=async_db, id=analysis.id, soft=True)

    response = await client.get(f"/api/v1/analysis/{analysis.id}/export")
    assert response.status_code == 404
    assert response.json()["detail"] == f"Analysis {analysis.id} not found"


# =====================================================================
# DELETE /api/v1/analysis/{id}
# =====================================================================


@pytest.mark.asyncio
async def test_delete_analysis_success(
    client: httpx.AsyncClient,
    async_db: AsyncSession,
):
    """Test DELETE /api/v1/analysis/{id} performs soft delete and returns 204."""
    analysis = await create_analysis(
        db=async_db,
        query="Policy analysis intended for soft deletion test.",
    )

    # Perform soft delete
    response = await client.delete(f"/api/v1/analysis/{analysis.id}")
    assert response.status_code == 204
    assert response.content == b""

    # Subsequent GET should return 404
    get_res = await client.get(f"/api/v1/analysis/{analysis.id}")
    assert get_res.status_code == 404
    assert get_res.json()["detail"] == f"Analysis {analysis.id} not found"

    # Subsequent DELETE should return 404 (already deleted)
    del_res = await client.delete(f"/api/v1/analysis/{analysis.id}")
    assert del_res.status_code == 404
    assert del_res.json()["detail"] == f"Analysis {analysis.id} not found"


@pytest.mark.asyncio
async def test_delete_analysis_not_found(client: httpx.AsyncClient):
    """Test DELETE /api/v1/analysis/{id} returns 404 for non-existent analysis."""
    random_id = uuid.uuid4()
    response = await client.delete(f"/api/v1/analysis/{random_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == f"Analysis {random_id} not found"


# =====================================================================
# POST /api/v1/analysis/{id}/rerun and resolve-data
# =====================================================================


@pytest.mark.asyncio
async def test_rerun_analysis_success(client: httpx.AsyncClient, async_db: AsyncSession):
    """Test POST /api/v1/analysis/{id}/rerun resets status to PENDING and returns ws_url."""
    analysis = await create_analysis(
        db=async_db,
        query="What is the 5-year trend in Singapore consumer price index (CPI)?",
        status=AnalysisStatus.FAILED,
    )
    with patch("app.api.v1.analysis.run_analysis_pipeline"):
        response = await client.post(f"/api/v1/analysis/{analysis.id}/rerun")
    assert response.status_code == 200
    data = response.json()
    assert data["analysis_id"] == str(analysis.id)
    assert data["status"] == "PENDING"
    assert f"/ws/analysis/{analysis.id}" in data["ws_url"]


@pytest.mark.asyncio
async def test_rerun_analysis_not_found(client: httpx.AsyncClient):
    """Test POST /api/v1/analysis/{id}/rerun returns 404 for non-existent analysis."""
    random_id = uuid.uuid4()
    response = await client.post(f"/api/v1/analysis/{random_id}/rerun")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resolve_analysis_data_success(client: httpx.AsyncClient, async_db: AsyncSession):
    """Test POST /api/v1/analysis/{id}/resolve-data calls AI resolution service."""
    analysis = await create_analysis(
        db=async_db,
        query="What is Singapore labor productivity across sectors?",
        status=AnalysisStatus.FAILED,
    )
    with patch("app.services.analysis_service.AnalysisService.resolve_failed_data") as mock_resolve:
        mock_resolve.return_value = {"status": "completed"}
        response = await client.post(f"/api/v1/analysis/{analysis.id}/resolve-data")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(analysis.id)
    mock_resolve.assert_awaited_once_with(analysis.id)
