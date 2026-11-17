"""Unit tests for SQLAlchemy models and database schema."""

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.agent_log import AgentLog
from app.models.analysis import Analysis
from app.models.dataset import AnalysisDataset, Dataset
from app.schemas.analysis import AnalysisStatus


@pytest.fixture
def test_db_session():
    """Create an in-memory SQLite database engine and session for model testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_analysis_crud(test_db_session: Session):
    """Test creating, reading, and updating an Analysis model."""
    analysis = Analysis(
        id=uuid.uuid4(),
        query="What is the historical CPI inflation trend in Singapore?",
        status=AnalysisStatus.PENDING.value,
        metadata_={"data_sources": ["singstat"], "duration_ms": 0},
    )
    test_db_session.add(analysis)
    test_db_session.commit()

    stmt = select(Analysis).where(Analysis.id == analysis.id)
    fetched = test_db_session.execute(stmt).scalar_one_or_none()

    assert fetched is not None
    assert fetched.query == "What is the historical CPI inflation trend in Singapore?"
    assert fetched.status == "PENDING"
    assert fetched.metadata_ == {"data_sources": ["singstat"], "duration_ms": 0}

    # Test update
    fetched.status = AnalysisStatus.DONE.value
    fetched.result = {"summary": "Inflation averaged 2.1%"}
    test_db_session.commit()

    stmt = select(Analysis).where(Analysis.id == analysis.id)
    updated = test_db_session.execute(stmt).scalar_one()
    assert updated.status == "DONE"
    assert updated.result == {"summary": "Inflation averaged 2.1%"}


def test_agent_log_relationship(test_db_session: Session):
    """Test AgentLog creation, relationship to Analysis, and ordering."""
    analysis_id = uuid.uuid4()
    analysis = Analysis(
        id=analysis_id,
        query="Test query",
        status=AnalysisStatus.RUNNING.value,
    )
    test_db_session.add(analysis)

    log1 = AgentLog(
        id=uuid.uuid4(),
        analysis_id=analysis_id,
        agent_name="coordinator",
        step_type="THINK",
        content={"thought": "Formulating research plan"},
        sequence_no=1,
    )
    log2 = AgentLog(
        id=uuid.uuid4(),
        analysis_id=analysis_id,
        agent_name="extraction",
        step_type="ACT",
        content={"tool": "singstat_mcp", "params": {"query": "CPI"}},
        sequence_no=2,
    )
    test_db_session.add_all([log1, log2])
    test_db_session.commit()

    # Query agent logs ordered by sequence_no
    stmt_logs = (
        select(AgentLog).where(AgentLog.analysis_id == analysis_id).order_by(AgentLog.sequence_no)
    )
    logs = test_db_session.execute(stmt_logs).scalars().all()

    assert len(logs) == 2
    assert logs[0].sequence_no == 1
    assert logs[0].agent_name == "coordinator"
    assert logs[1].sequence_no == 2
    assert logs[1].agent_name == "extraction"
    assert logs[0].analysis.id == analysis_id


def test_cascade_delete(test_db_session: Session):
    """Test that deleting an analysis cascades and deletes related agent_logs."""
    analysis_id = uuid.uuid4()
    analysis = Analysis(
        id=analysis_id,
        query="Test query for cascade",
        status=AnalysisStatus.PENDING.value,
    )
    test_db_session.add(analysis)

    log = AgentLog(
        id=uuid.uuid4(),
        analysis_id=analysis_id,
        agent_name="coordinator",
        step_type="THINK",
        content={"thought": "Cascade delete test"},
        sequence_no=1,
    )
    test_db_session.add(log)
    test_db_session.commit()

    # Delete analysis
    test_db_session.delete(analysis)
    test_db_session.commit()

    stmt_logs = select(AgentLog).where(AgentLog.analysis_id == analysis_id)
    res_logs = test_db_session.execute(stmt_logs).scalars().all()
    assert len(res_logs) == 0


def test_dataset_and_association(test_db_session: Session):
    """Test Dataset model and AnalysisDataset many-to-many relationship."""
    analysis_id = uuid.uuid4()
    dataset_id = uuid.uuid4()

    analysis = Analysis(
        id=analysis_id,
        query="Query needing dataset",
        status=AnalysisStatus.RUNNING.value,
    )
    dataset = Dataset(
        id=dataset_id,
        source="singstat",
        source_id="M212161",
        title="Consumer Price Index, Monthly",
        data_hash="abc123hash",
        row_count=120,
        columns=[{"name": "month", "dtype": "string"}, {"name": "cpi", "dtype": "float"}],
    )
    test_db_session.add_all([analysis, dataset])
    test_db_session.commit()

    assoc = AnalysisDataset(analysis_id=analysis_id, dataset_id=dataset_id)
    test_db_session.add(assoc)
    test_db_session.commit()

    stmt = select(AnalysisDataset).where(AnalysisDataset.analysis_id == analysis_id)
    records = test_db_session.execute(stmt).scalars().all()
    assert len(records) == 1
    assert records[0].dataset_id == dataset_id


def test_repr_strings():
    """Test __repr__ methods on models."""
    analysis_id = uuid.uuid4()
    analysis = Analysis(id=analysis_id, query="Short query", status="PENDING")
    assert f"<Analysis(id={analysis_id}" in repr(analysis)

    log_id = uuid.uuid4()
    log = AgentLog(id=log_id, agent_name="coord", step_type="THINK", sequence_no=1)
    assert f"<AgentLog(id={log_id}" in repr(log)

    ds_id = uuid.uuid4()
    ds = Dataset(id=ds_id, source="singstat", title="CPI")
    assert f"<Dataset(id={ds_id}" in repr(ds)
