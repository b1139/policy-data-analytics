"""Unit tests for Pydantic schemas (analysis and agent)."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.agent_log import AgentLog
from app.models.analysis import Analysis
from app.schemas.agent import AgentLogResponse, AgentStepSchema, AgentStepType
from app.schemas.analysis import (
    AnalysisCreate,
    AnalysisListItem,
    AnalysisResponse,
    AnalysisStatus,
)


def test_analysis_create_schema():
    """Test valid and invalid AnalysisCreate payloads."""
    payload = AnalysisCreate(
        query="What is the CPF contribution rate history?",
        metadata={"preferred_source": "data.gov.sg"},
    )
    assert payload.query == "What is the CPF contribution rate history?"
    assert payload.metadata == {"preferred_source": "data.gov.sg"}

    # Validation failure: query too short (< 3 chars)
    with pytest.raises(ValidationError):
        AnalysisCreate(query="hi")


def test_analysis_response_from_orm():
    """Test converting an ORM Analysis object to AnalysisResponse."""
    now = datetime.now(UTC)
    analysis = Analysis(
        id=uuid.uuid4(),
        query="What is Singapore's GDP growth rate?",
        status=AnalysisStatus.DONE.value,
        result={"growth": 3.4},
        metadata_={"sources": ["SingStat"], "duration_ms": 1500},
        error_msg=None,
        created_at=now,
        updated_at=now,
    )

    response = AnalysisResponse.model_validate(analysis)
    assert response.id == analysis.id
    assert response.query == analysis.query
    assert response.status == AnalysisStatus.DONE
    assert response.result == {"growth": 3.4}
    assert response.metadata == {"sources": ["SingStat"], "duration_ms": 1500}
    assert response.created_at == now


def test_analysis_list_item():
    """Test AnalysisListItem conversion."""
    now = datetime.now(UTC)
    analysis = Analysis(
        id=uuid.uuid4(),
        query="Public housing resale prices",
        status=AnalysisStatus.PENDING.value,
        created_at=now,
        updated_at=now,
    )

    item = AnalysisListItem.model_validate(analysis)
    assert item.id == analysis.id
    assert item.query == "Public housing resale prices"
    assert item.status == AnalysisStatus.PENDING


def test_agent_step_schema():
    """Test AgentStepSchema creation and validation."""
    step = AgentStepSchema(
        agent_name="analytics",
        step_type=AgentStepType.THINK.value,
        content={"calculation": "linear regression"},
        sequence_no=1,
    )
    assert step.agent_name == "analytics"
    assert step.step_type == "THINK"
    assert step.sequence_no == 1

    # sequence_no < 1 should fail
    with pytest.raises(ValidationError):
        AgentStepSchema(
            agent_name="analytics",
            step_type="THINK",
            content={},
            sequence_no=0,
        )


def test_agent_log_response_from_orm():
    """Test converting an ORM AgentLog to AgentLogResponse."""
    now = datetime.now(UTC)
    analysis_id = uuid.uuid4()
    log_id = uuid.uuid4()

    log = AgentLog(
        id=log_id,
        analysis_id=analysis_id,
        agent_name="extraction",
        step_type="OBSERVE",
        content={"rows_received": 50},
        sequence_no=3,
        created_at=now,
    )

    response = AgentLogResponse.model_validate(log)
    assert response.id == log_id
    assert response.analysis_id == analysis_id
    assert response.agent_name == "extraction"
    assert response.step_type == "OBSERVE"
    assert response.sequence_no == 3
    assert response.content == {"rows_received": 50}
