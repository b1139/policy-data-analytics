"""Data source registry for discovering and managing data source connectors.

Provides a thread-safe singleton registry pattern matching LLD.md §6.
"""

import logging
from collections.abc import Iterator

from app.data_sources.base import AbstractDataSource

logger = logging.getLogger(__name__)


class DataSourceRegistry:
    """Singleton registry for all data source connectors.

    Enables discovery and retrieval of data sources by `source_id` without
    requiring callers (like the extraction agent) to know concrete classes.
    """

    _instance: "DataSourceRegistry | None" = None
    _sources: dict[str, AbstractDataSource]

    def __new__(cls) -> "DataSourceRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sources = {}
        return cls._instance

    def register(self, source: AbstractDataSource, overwrite: bool = True) -> None:
        """Register a data source connector.

        Args:
            source: An instance of a concrete AbstractDataSource subclass.
            overwrite: If True, replace existing source with the same source_id.
                       If False, raise ValueError on duplicate source_id.

        Raises:
            TypeError: If source is not an instance of AbstractDataSource.
            ValueError: If source_id is empty or already registered with overwrite=False.
        """
        if not isinstance(source, AbstractDataSource):
            raise TypeError(f"Expected instance of AbstractDataSource, got {type(source).__name__}")

        source_id = getattr(source, "source_id", None)
        if not source_id or not isinstance(source_id, str):
            raise ValueError(
                f"Data source {type(source).__name__} must have a non-empty string 'source_id'."
            )

        if source_id in self._sources:
            if not overwrite:
                raise ValueError(
                    f"Data source '{source_id}' is already registered and overwrite is False."
                )
            logger.info("Overwriting registered data source '%s' with new instance.", source_id)

        self._sources[source_id] = source
        logger.debug(
            "Registered data source '%s' (%s)",
            source_id,
            getattr(source, "display_name", source_id),
        )

    def get(self, source_id: str) -> AbstractDataSource:
        """Retrieve a registered data source connector by its source_id.

        Args:
            source_id: Unique string identifier of the data source.

        Returns:
            AbstractDataSource: Registered data source instance.

        Raises:
            KeyError: If source_id is not registered.
        """
        if source_id not in self._sources:
            available = sorted(self._sources.keys())
            raise KeyError(
                f"Data source '{source_id}' not found in registry. "
                f"Available registered sources: {available}"
            )
        return self._sources[source_id]

    def list_all(self) -> list[str]:
        """Return a sorted list of all registered source IDs."""
        return sorted(self._sources.keys())

    def get_all(self) -> dict[str, AbstractDataSource]:
        """Return a copy of the dictionary mapping source_id to source instance."""
        return dict(self._sources)

    def unregister(self, source_id: str) -> bool:
        """Remove a source from the registry.

        Args:
            source_id: Unique identifier to remove.

        Returns:
            bool: True if source was found and removed, False otherwise.
        """
        if source_id in self._sources:
            del self._sources[source_id]
            logger.debug("Unregistered data source '%s'", source_id)
            return True
        return False

    def clear(self) -> None:
        """Clear all registered data sources (useful for test teardown)."""
        self._sources.clear()

    def __contains__(self, source_id: str) -> bool:
        return source_id in self._sources

    def __len__(self) -> int:
        return len(self._sources)

    def __iter__(self) -> Iterator[str]:
        return iter(self._sources)


# Global singleton instance
data_source_registry = DataSourceRegistry()
