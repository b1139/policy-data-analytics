"""Data extraction tools for discovering, retrieving, and validating policy datasets."""

import io
import logging
from typing import Any

import pandas as pd
from langchain_core.tools import StructuredTool, tool

from app.data_sources import auto_register_sources, data_source_registry
from app.services.data_service import DataQualityValidator

logger = logging.getLogger(__name__)

# Ensure concrete data sources are registered
auto_register_sources()

SOURCE_ALIASES: dict[str, str] = {
    "mock": "mock_internal",
    "mock_db": "mock_internal",
    "data_gov": "datagov",
    "data.gov.sg": "datagov",
    "singstat_rest": "singstat",
    "singstat_mcp": "singstat",
}


def _resolve_source_id(source: str) -> str:
    """Normalize and resolve source identifier using aliases and case-insensitivity."""
    from app.core.config import settings

    if settings.USE_MOCK_DATA_SOURCES and "mock_internal" in data_source_registry:
        return "mock_internal"

    cleaned = (source or "").strip()
    if cleaned in data_source_registry:
        return cleaned

    lower = cleaned.lower()
    if lower in data_source_registry:
        return lower

    alias = SOURCE_ALIASES.get(lower)
    if alias and alias in data_source_registry:
        return alias

    for reg_id in data_source_registry.list_all():
        if reg_id.lower() == lower:
            return reg_id

    # Fall back to original input and let registry raise informative KeyError
    return cleaned


def _wrap_dual_callable(tool_obj: StructuredTool) -> StructuredTool:
    """Wrap a StructuredTool to support both direct function calling and LangChain .invoke()/.ainvoke()."""

    class DualCallableTool(StructuredTool):
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            if self.coroutine:
                return self.coroutine(*args, **kwargs)
            if self.func:
                return self.func(*args, **kwargs)
            return super().__call__(*args, **kwargs)

    wrapped = DualCallableTool.from_function(
        func=tool_obj.func,
        coroutine=tool_obj.coroutine,
        name=tool_obj.name,
        description=tool_obj.description,
        args_schema=tool_obj.args_schema,
    )
    return wrapped


@tool
async def list_available_datasets(source: str, keywords: str) -> list[dict[str, Any]]:
    """Search available datasets matching keywords in the specified data source connector.

    For SingStat this calls the MCP get_relevant_table_names tool: use specific terms
    (e.g. 'resident unemployment rate', not 'economy'). Workflow: search -> fetch_dataset
    (metadata is read first, then data with series/time filters) -> validate_dataframe.

    Args:
        source: Source identifier (e.g., 'singstat', 'datagov', 'mock' or 'mock_internal').
        keywords: Search keywords to query against dataset catalog.

    Returns:
        List of matching dataset metadata records: [{"id": ..., "title": ..., "description": ...}].
    """
    resolved = _resolve_source_id(source)
    connector = data_source_registry.get(resolved)
    return await connector.search(keywords=keywords)


@tool
async def fetch_dataset(
    source: str,
    dataset_id: str,
    time_filter: str | None = None,
    series_no: str | None = None,
) -> str:
    """Fetch a dataset from the specified source and return it as a split JSON string.

    Args:
        source: Source identifier (e.g., 'singstat', 'datagov', 'mock' or 'mock_internal').
        dataset_id: Identifier of the dataset to retrieve.
        time_filter: Optional comma-separated years/periods (e.g. '2023,2024'). For SingStat
            it is converted to the MCP [start, end] yyyy-mm range. Always set it to avoid
            the MCP 3,000-row response cap.
        series_no: Optional SingStat series/row numbers (e.g. '1,1.1,1.1.1') to retrieve only
            the needed rows; SingStat connector reads table metadata first to map them.

    Returns:
        JSON string representing the normalized DataFrame using pandas orient='split'.
    """
    resolved = _resolve_source_id(source)
    connector = data_source_registry.get(resolved)
    try:
        import inspect

        sig = inspect.signature(connector.fetch)
        if "time_filter" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        ):
            extra = {"series_no": series_no} if series_no and resolved == "singstat" else {}
            df = await connector.fetch(dataset_id, time_filter=time_filter, **extra)
        else:
            df = await connector.fetch(dataset_id)
    except TypeError:
        df = await connector.fetch(dataset_id)

    if (
        (df is None or df.empty)
        and resolved != "mock_internal"
        and "mock_internal" in data_source_registry
    ):
        mock_connector = data_source_registry.get("mock_internal")
        if mock_connector:
            try:
                df = await mock_connector.fetch(dataset_id)
            except Exception:
                df = pd.DataFrame()

    if df is None:
        df = pd.DataFrame()
    return df.to_json(orient="split", date_format="iso")


@tool
def validate_dataframe(df_json: str) -> dict[str, Any]:
    """Validate data quality of a dataset reconstructed from a split JSON string.

    Args:
        df_json: Compact DataFrame JSON string (orient='split').

    Returns:
        Validation report dictionary with passed status, warnings, errors, and stats.
    """
    validator = DataQualityValidator()
    if not df_json or not df_json.strip():
        df = pd.DataFrame()
    else:
        try:
            df = pd.read_json(io.StringIO(df_json), orient="split")
        except Exception as exc:
            logger.warning("Failed to deserialize DataFrame JSON: %s", exc)
            df = pd.DataFrame()

    result = validator.validate(df)
    return result.model_dump()


# Wrap tools for dual direct/LangChain invocation
list_available_datasets = _wrap_dual_callable(list_available_datasets)
fetch_dataset = _wrap_dual_callable(fetch_dataset)
validate_dataframe = _wrap_dual_callable(validate_dataframe)

__all__ = [
    "fetch_dataset",
    "list_available_datasets",
    "validate_dataframe",
]
