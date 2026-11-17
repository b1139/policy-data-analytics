"""CRUD operations for Database Models in Policy Data Analytics Platform."""

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

__all__ = [
    # Analysis CRUD
    "create_analysis",
    "get_analysis",
    "list_analyses",
    "count_analyses",
    "update_analysis_status",
    "delete_analysis",
    # AgentLog CRUD
    "create_agent_log",
    "get_agent_log",
    "list_agent_logs",
    # Dataset CRUD
    "get_dataset",
    "get_or_create_dataset",
    "link_dataset_to_analysis",
    "get_datasets_for_analysis",
]
