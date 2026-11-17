"""Data source connectors, registry, and SingStat MCP client.

Exports the AbstractDataSource base class, concrete connectors, DataSourceRegistry,
and the global data_source_registry singleton. Auto-registers available concrete data sources.
"""

import logging

from app.data_sources.base import (
    DEFAULT_HEALTH_CHECK_TIMEOUT,
    AbstractDataSource,
)
from app.data_sources.datagov import DataGovDataSource
from app.data_sources.mock_internal import MockInternalDataSource
from app.data_sources.registry import (
    DataSourceRegistry,
    data_source_registry,
)
from app.data_sources.singstat import SingStatDataSource

logger = logging.getLogger(__name__)


def auto_register_sources() -> None:
    """Discover and register available concrete data sources."""
    # SingStat MCP Data Source (S17 / S16)
    try:
        from app.data_sources.singstat_mcp import SingStatMCPDataSource

        data_source_registry.register(SingStatMCPDataSource(), overwrite=True)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Could not auto-register SingStatMCPDataSource: %s", exc)

    # SingStat REST Data Source (S17)
    try:
        data_source_registry.register(SingStatDataSource(), overwrite=True)
    except Exception as exc:
        logger.warning("Could not auto-register SingStatDataSource: %s", exc)

    # Data.gov.sg Data Source (S17)
    try:
        data_source_registry.register(DataGovDataSource(), overwrite=True)
    except Exception as exc:
        logger.warning("Could not auto-register DataGovDataSource: %s", exc)

    # Mock Internal Data Source (S18)
    try:
        data_source_registry.register(MockInternalDataSource(), overwrite=True)
    except Exception as exc:
        logger.warning("Could not auto-register MockInternalDataSource: %s", exc)


# Auto-register available sources on module import
auto_register_sources()

__all__ = [
    "DEFAULT_HEALTH_CHECK_TIMEOUT",
    "AbstractDataSource",
    "DataGovDataSource",
    "DataSourceRegistry",
    "MockInternalDataSource",
    "SingStatDataSource",
    "auto_register_sources",
    "data_source_registry",
]
