"""Comprehensive unit tests for async CRUD operations (Analysis, AgentLog, Dataset)."""

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import Base
from app.crud.agent_log import (
    create_agent_log,
    get_agent_log,
    list_agent_logs,
)
from app.crud.analysis import (
    count_analyses,
    create_analysis,
    delete_analysis,
    get_analysis,
    list_analyses,
    update_analysis_status,
)
from app.crud.dataset import (
    get_dataset,
    get_datasets_for_analysis,
    get_or_create_dataset,
    link_dataset_to_analysis,
)
from app.schemas.analysis import AnalysisStatus


@pytest_asyncio.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite async database session for CRUD tests."""
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


@pytest.mark.asyncio
async def test_create_and_get_analysis(async_db: AsyncSession):
    """Test creating an analysis and retrieving it by UUID."""
    query_text = "What is the historical CPI inflation rate in Singapore?"
    metadata = {"sources": ["singstat"], "requested_by": "test-suite"}

    analysis = await create_analysis(
        db=async_db,
        query=query_text,
        metadata=metadata,
    )

    assert analysis.id is not None
    assert analysis.query == query_text
    assert analysis.status == AnalysisStatus.PENDING.value
    assert analysis.metadata_ == metadata

    # Fetch by ID
    fetched = await get_analysis(db=async_db, id=analysis.id)
    assert fetched is not None
    assert fetched.id == analysis.id
    assert fetched.query == query_text
    assert fetched.status == "PENDING"
    assert fetched.metadata_ == metadata

    # Fetch non-existent ID
    non_existent = await get_analysis(db=async_db, id=uuid.uuid4())
    assert non_existent is None


@pytest.mark.asyncio
async def test_update_analysis_status(async_db: AsyncSession):
    """Test updating analysis status, result payload, and error messages."""
    analysis = await create_analysis(
        db=async_db,
        query="Analyze GDP growth trend 2018-2023",
    )

    # 1. Update to RUNNING
    updated = await update_analysis_status(
        db=async_db,
        id=analysis.id,
        status=AnalysisStatus.RUNNING,
    )
    assert updated is not None
    assert updated.status == AnalysisStatus.RUNNING.value

    # 2. Update to DONE with result payload
    result_data = {
        "summary": "GDP grew at an annualized rate of 2.8%",
        "charts": [{"type": "line", "data": [1, 2, 3]}],
    }
    updated_done = await update_analysis_status(
        db=async_db,
        id=analysis.id,
        status="DONE",
        result=result_data,
        metadata={"completed_steps": 5},
    )
    assert updated_done is not None
    assert updated_done.status == "DONE"
    assert updated_done.result == result_data
    assert updated_done.metadata_ == {"completed_steps": 5}

    # 3. Update to FAILED with error message
    updated_failed = await update_analysis_status(
        db=async_db,
        id=analysis.id,
        status=AnalysisStatus.FAILED,
        error_msg="MCP data extraction timed out",
    )
    assert updated_failed is not None
    assert updated_failed.status == "FAILED"
    assert updated_failed.error_msg == "MCP data extraction timed out"

    # 4. Updating non-existent analysis returns None
    missing_update = await update_analysis_status(
        db=async_db,
        id=uuid.uuid4(),
        status="RUNNING",
    )
    assert missing_update is None


@pytest.mark.asyncio
async def test_list_and_count_analyses(async_db: AsyncSession):
    """Test pagination and ordering of list_analyses and total counting."""
    # Initially count is 0
    assert await count_analyses(async_db) == 0

    # Create 5 analyses
    created_ids = []
    for i in range(5):
        a = await create_analysis(
            db=async_db,
            query=f"Query number {i}",
        )
        created_ids.append(a.id)

    assert await count_analyses(async_db) == 5

    # Test list pagination
    first_page = await list_analyses(db=async_db, skip=0, limit=3)
    assert len(first_page) == 3

    second_page = await list_analyses(db=async_db, skip=3, limit=3)
    assert len(second_page) == 2

    # Verify no overlap between pages
    first_page_ids = {a.id for a in first_page}
    second_page_ids = {a.id for a in second_page}
    assert first_page_ids.isdisjoint(second_page_ids)


@pytest.mark.asyncio
async def test_delete_analysis_soft_and_hard(async_db: AsyncSession):
    """Test soft delete (sets status='DELETED') and hard delete behavior."""
    analysis = await create_analysis(db=async_db, query="Analysis to delete")

    # Soft delete
    deleted = await delete_analysis(db=async_db, id=analysis.id, soft=True)
    assert deleted is True

    # Re-deleting already soft-deleted returns False
    deleted_again = await delete_analysis(db=async_db, id=analysis.id, soft=True)
    assert deleted_again is False

    # get_analysis excludes soft-deleted by default
    assert await get_analysis(db=async_db, id=analysis.id) is None
    # get_analysis with include_deleted=True finds it
    fetched_deleted = await get_analysis(db=async_db, id=analysis.id, include_deleted=True)
    assert fetched_deleted is not None
    assert fetched_deleted.status == AnalysisStatus.DELETED.value

    # list_analyses excludes soft-deleted by default
    active_list = await list_analyses(db=async_db)
    assert len(active_list) == 0
    assert await count_analyses(db=async_db) == 0

    # include_deleted=True includes it
    all_list = await list_analyses(db=async_db, include_deleted=True)
    assert len(all_list) == 1
    assert await count_analyses(db=async_db, include_deleted=True) == 1

    # Hard delete
    hard_analysis = await create_analysis(db=async_db, query="Hard delete target")
    hard_deleted = await delete_analysis(db=async_db, id=hard_analysis.id, soft=False)
    assert hard_deleted is True
    # Permanently gone from DB
    assert await get_analysis(db=async_db, id=hard_analysis.id, include_deleted=True) is None

    # Deleting nonexistent ID returns False
    assert await delete_analysis(db=async_db, id=uuid.uuid4()) is False


@pytest.mark.asyncio
async def test_agent_log_crud_and_sequence_ordering(async_db: AsyncSession):
    """Test creating agent logs, retrieving by ID, and ordering by sequence_no."""
    analysis = await create_analysis(db=async_db, query="Multi-agent execution pipeline")

    # Insert logs in reverse order to verify order_by sequence_no
    log3 = await create_agent_log(
        db=async_db,
        analysis_id=analysis.id,
        agent_name="analytics",
        step_type="OBSERVE",
        content={"summary": "Calculation complete"},
        seq_no=3,
    )
    log1 = await create_agent_log(
        db=async_db,
        analysis_id=analysis.id,
        agent_name="coordinator",
        step_type="THINK",
        content={"thought": "Decomposing query"},
        seq_no=1,
    )
    log2 = await create_agent_log(
        db=async_db,
        analysis_id=analysis.id,
        agent_name="extraction",
        step_type="ACT",
        content={"tool": "singstat_search", "query": "CPI"},
        seq_no=2,
    )

    # Test get_agent_log
    fetched_log1 = await get_agent_log(db=async_db, id=log1.id)
    assert fetched_log1 is not None
    assert fetched_log1.agent_name == "coordinator"
    assert fetched_log1.step_type == "THINK"
    assert fetched_log1.sequence_no == 1

    # Test list_agent_logs is sorted asc by sequence_no: 1, 2, 3
    logs = await list_agent_logs(db=async_db, analysis_id=analysis.id)
    assert len(logs) == 3
    assert [log.sequence_no for log in logs] == [1, 2, 3]
    assert [log.agent_name for log in logs] == ["coordinator", "extraction", "analytics"]
    assert logs[0].id == log1.id
    assert logs[1].id == log2.id
    assert logs[2].id == log3.id

    # Test include_logs on get_analysis
    analysis_with_logs = await get_analysis(
        db=async_db,
        id=analysis.id,
        include_logs=True,
    )
    assert analysis_with_logs is not None
    assert len(analysis_with_logs.agent_logs) == 3
    assert [log.sequence_no for log in analysis_with_logs.agent_logs] == [1, 2, 3]


@pytest.mark.asyncio
async def test_dataset_crud_and_analysis_linking(async_db: AsyncSession):
    """Test get_or_create_dataset deduplication, fetching, and analysis linking."""
    # 1. First get_or_create creates new dataset
    dataset1, created1 = await get_or_create_dataset(
        db=async_db,
        source="singstat",
        source_id="M212161",
        data_hash="hash_cpi_2024",
        title="Consumer Price Index, Monthly",
        row_count=120,
        columns=[{"name": "month", "dtype": "string"}, {"name": "cpi", "dtype": "float"}],
    )
    assert created1 is True
    assert dataset1.id is not None
    assert dataset1.source == "singstat"
    assert dataset1.source_id == "M212161"

    # 2. Second call with same source and source_id returns existing record
    dataset2, created2 = await get_or_create_dataset(
        db=async_db,
        source="singstat",
        source_id="M212161",
        data_hash="hash_cpi_2024",
    )
    assert created2 is False
    assert dataset2.id == dataset1.id

    # 3. Third call matching by data_hash when source_id is None
    dataset3, created3 = await get_or_create_dataset(
        db=async_db,
        source="singstat",
        source_id=None,
        data_hash="hash_cpi_2024",
    )
    assert created3 is False
    assert dataset3.id == dataset1.id

    # 4. Fetch dataset by ID
    fetched_ds = await get_dataset(db=async_db, id=dataset1.id)
    assert fetched_ds is not None
    assert fetched_ds.title == "Consumer Price Index, Monthly"

    # 5. Link dataset to analysis
    analysis = await create_analysis(db=async_db, query="Singapore CPI correlation")
    link = await link_dataset_to_analysis(
        db=async_db,
        analysis_id=analysis.id,
        dataset_id=dataset1.id,
    )
    assert link.analysis_id == analysis.id
    assert link.dataset_id == dataset1.id

    # 6. Linking again is idempotent (does not fail with duplicate key)
    link_duplicate = await link_dataset_to_analysis(
        db=async_db,
        analysis_id=analysis.id,
        dataset_id=dataset1.id,
    )
    assert link_duplicate.analysis_id == analysis.id

    # 7. Retrieve datasets linked to analysis
    datasets_for_analysis = await get_datasets_for_analysis(
        db=async_db,
        analysis_id=analysis.id,
    )
    assert len(datasets_for_analysis) == 1
    assert datasets_for_analysis[0].id == dataset1.id


def test_alembic_upgrade_head_sql():
    """Verify that Alembic migration environment successfully renders upgrade SQL."""
    from pathlib import Path
    ini_path = "alembic.ini" if Path("alembic.ini").exists() else "backend/alembic.ini"
    alembic_cfg = Config(ini_path)
    # Verify migration config exists and runs upgrade head in offline mode
    command.upgrade(alembic_cfg, "head", sql=True)
