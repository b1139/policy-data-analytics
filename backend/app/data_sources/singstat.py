"""SingStat Table Builder API data source connector.

Connects to the official Singapore Department of Statistics (SingStat) Table Builder
REST API for statistical table discovery and time series data retrieval:
- Table search: https://tablebuilder.singstat.gov.sg/api/table/search?keyword={kw}
- Table data: https://tablebuilder.singstat.gov.sg/api/table/tabledata/{id}

Implements AbstractDataSource contract with automatic, resilient fallback to
MockInternalDataSource when live requests fail, time out, or when
USE_MOCK_DATA_SOURCES=true is configured.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd

from app.core.config import settings
from app.data_sources.base import AbstractDataSource
from app.data_sources.mock_internal import MockInternalDataSource

logger = logging.getLogger(__name__)


class SingStatDataSource(AbstractDataSource):
    """SingStat Table Builder REST API data source connector."""

    source_id: str = "singstat"
    display_name: str = "SingStat Table Builder"

    # API Endpoints
    BASE_URL: str = "https://tablebuilder.singstat.gov.sg/api/table"
    SEARCH_ENDPOINT: str = "https://tablebuilder.singstat.gov.sg/api/table/resourceid"
    TABLE_DATA_ENDPOINT: str = "https://tablebuilder.singstat.gov.sg/api/table/tabledata"
    HEALTH_CHECK_URL: str = (
        "https://tablebuilder.singstat.gov.sg/api/table/resourceid?keyword=employment&searchOption=all"
    )

    # Timeouts
    REQUEST_TIMEOUT: float = 30.0
    HEALTH_TIMEOUT: float = 5.0

    def __init__(
        self,
        mock_fallback: AbstractDataSource | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize connector with optional mock fallback and custom HTTP client."""
        self._mock_source = mock_fallback or MockInternalDataSource()
        self._custom_client = client

    def _get_headers(self) -> dict[str, str]:
        """Build request headers, including optional API key if configured."""
        headers: dict[str, str] = {
            "Accept": "application/json, text/csv, */*",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        if settings.SINGSTAT_API_KEY:
            api_key = settings.SINGSTAT_API_KEY.strip()
            headers["Authorization"] = f"Bearer {api_key}"
            headers["api-key"] = api_key
        return headers

    async def search(
        self,
        keywords: str | list[str],
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Search SingStat Table Builder tables matching keywords.

        Args:
            keywords: Query terms (string or list of strings).
            **filters: Optional additional filters (e.g. format, frequency).

        Returns:
            List of matching dataset metadata dictionaries:
            [{"id": ..., "title": ..., "description": ..., "url": ..., "format": ...}]
        """
        # 1. Offline / Mock Mode Check
        if settings.USE_MOCK_DATA_SOURCES:
            logger.info("USE_MOCK_DATA_SOURCES is True; SingStat search falling back to mock")
            return await self._mock_source.search(keywords, **filters)

        # 2. Parse query string
        if isinstance(keywords, list):
            kw = " ".join(str(k).strip() for k in keywords if str(k).strip())
        else:
            kw = str(keywords).strip()

        if not kw:
            return []

        # 3a. Preferred: official SingStat MCP (get_relevant_table_names)
        mcp_results = await self._mcp_search(kw)
        if mcp_results:
            return mcp_results

        # 3b. Fallback: live REST search
        params = {"keyword": kw, "searchOption": "all"}
        try:
            if self._custom_client:
                resp = await self._custom_client.get(
                    self.SEARCH_ENDPOINT,
                    params=params,
                    headers=self._get_headers(),
                )
            else:
                async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                    resp = await client.get(
                        self.SEARCH_ENDPOINT,
                        params=params,
                        headers=self._get_headers(),
                    )
            resp.raise_for_status()
            data = resp.json()

            records = self._extract_search_records(data)
            results: list[dict[str, Any]] = []

            for item in records:
                if not isinstance(item, dict):
                    continue
                item_id = str(
                    item.get("id")
                    or item.get("tableId")
                    or item.get("resourceId")
                    or item.get("code")
                    or ""
                ).strip()
                if not item_id:
                    continue

                title = str(
                    item.get("title") or item.get("tableTitle") or item.get("name") or item_id
                ).strip()
                description = str(
                    item.get("description") or item.get("notes") or item.get("theme") or title
                ).strip()
                url = str(
                    item.get("url") or f"https://tablebuilder.singstat.gov.sg/table/{item_id}"
                )
                fmt = str(item.get("format") or "json").lower()

                # Optional format filtering
                if "format" in filters and filters["format"]:
                    filter_fmt = str(filters["format"]).strip().lower()
                    if filter_fmt != "*" and filter_fmt != fmt:
                        continue

                results.append(
                    {
                        "id": item_id,
                        "title": title,
                        "description": description,
                        "url": url,
                        "format": fmt,
                    }
                )

            if results:
                return results

            if getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False) or settings.USE_MOCK_DATA_SOURCES:
                logger.info("SingStat live search yielded no records for '%s'; using mock fallback", kw)
                return await self._mock_source.search(keywords, **filters)
            logger.warning("SingStat live search yielded no records for '%s' (mock fallback disabled)", kw)
            return []

        except Exception as exc:
            if getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False) or settings.USE_MOCK_DATA_SOURCES:
                logger.warning(
                    "SingStat search request failed for keywords '%s' (%s); falling back to mock",
                    kw,
                    exc,
                )
                return await self._mock_source.search(keywords, **filters)
            logger.error(
                "SingStat search request failed for keywords '%s' (%s) and USE_MOCK_DATA_AS_FALLBACK=false",
                kw,
                exc,
            )
            return []

    # ------------------------------------------------------------------
    # SingStat MCP (https://www.singstat.gov.sg/data-tools-services/singstat-mcp)
    # Workflow: get_relevant_table_names -> get_table_metadata -> get_table_data
    # ------------------------------------------------------------------
    MCP_URL: str = "https://chatwithsandra.singstat.gov.sg/mcp"
    MCP_MAX_ROWS: int = 3000  # server-side cap on get_table_data responses

    def _mcp_enabled(self) -> bool:
        # An injected HTTP client means the caller explicitly wants the REST path.
        if self._custom_client is not None:
            return False
        return bool(getattr(settings, "SINGSTAT_MCP_ENABLED", True))

    async def _mcp_call(self, calls: list[tuple[str, dict[str, Any]]], retries: int = 2) -> list[Any]:
        """_mcp_call_once with brief exponential backoff for transient server errors."""
        for attempt in range(retries + 1):
            try:
                return await self._mcp_call_once(calls)
            except BaseException as exc:  # includes ExceptionGroup from anyio
                if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                    raise
                if attempt >= retries:
                    raise
                await asyncio.sleep(1.5 * (2**attempt))
        return []

    async def _mcp_call_once(self, calls: list[tuple[str, dict[str, Any]]]) -> list[Any]:
        """Run tool calls sequentially over one MCP session; return decoded JSON per call."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        out: list[Any] = []
        mcp_url = getattr(settings, "SINGSTAT_MCP_URL", None)
        if not mcp_url or "singstat.gov.sg/data-tools-services" in mcp_url:
            mcp_url = self.MCP_URL  # guard against the docs-page URL being used as endpoint
        async with streamable_http_client(mcp_url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                for name, args in calls:
                    res = await asyncio.wait_for(
                        session.call_tool(name, args), timeout=self.REQUEST_TIMEOUT
                    )
                    text = res.content[0].text if res.content else ""
                    out.append(json.loads(text) if text else {})
        return out

    async def _mcp_search(self, query: str) -> list[dict[str, Any]]:
        """Table discovery via get_relevant_table_names (specific queries work best)."""
        if not self._mcp_enabled():
            return []
        try:
            (payload,) = await self._mcp_call([("get_relevant_table_names", {"query_text": query})])
        except Exception as exc:
            logger.warning("SingStat MCP search failed for '%s': %s", query, exc)
            return []

        results: list[dict[str, Any]] = []
        for group in (payload or {}).get("data", []):
            if not isinstance(group, dict):
                continue
            for group_title, variants in group.items():
                if not isinstance(variants, dict):
                    continue
                for freq, rid in variants.items():
                    freq_label = str(freq).strip(" ,")
                    results.append(
                        {
                            "id": str(rid),
                            "title": f"{group_title} ({freq_label})" if freq_label else group_title,
                            "description": group_title,
                            "url": f"https://tablebuilder.singstat.gov.sg/table/{rid}",
                            "format": "json",
                            "frequency": freq_label,
                        }
                    )
        return results

    @staticmethod
    def _to_mcp_time_filter(time_filter: str | list[str] | None) -> list[str] | None:
        """Convert '2023,2024' / ['2020-01','2023-12'] into the MCP [start, end] yyyy-mm array."""
        if not time_filter:
            return None
        parts = (
            [p.strip() for p in time_filter.split(",")]
            if isinstance(time_filter, str)
            else [str(p).strip() for p in time_filter]
        )
        parts = [p for p in parts if p]
        if not parts:
            return None

        def norm(p: str, end: bool) -> str | None:
            if len(p) == 7 and p[4] == "-":
                return p
            if len(p) == 4 and p.isdigit():
                return f"{p}-12" if end else f"{p}-01"
            return None

        start, end = norm(min(parts), False), norm(max(parts), True)
        return [start, end] if start and end else None

    async def get_metadata(self, dataset_id: str) -> dict[str, Any] | None:
        """Return MCP table metadata (title, periods, total, row list) or None."""
        if not self._mcp_enabled():
            return None
        try:
            (payload,) = await self._mcp_call([("get_table_metadata", {"resource_id": dataset_id})])
            return ((payload or {}).get("data") or {}).get("records") or None
        except Exception as exc:
            logger.warning("SingStat MCP metadata failed for '%s': %s", dataset_id, exc)
            return None

    @staticmethod
    def select_series(rows: list[dict[str, Any]], keywords: str, max_rows: int = 10) -> str | None:
        """Pick seriesNo values (e.g. '1,1.1,1.1.1') whose rowText matches keywords.

        Returns None when the table is small or nothing matches (fetch all rows).
        """
        rows = [r for r in rows if isinstance(r, dict) and r.get("seriesNo")]
        if len(rows) <= max_rows:
            return None
        tokens = [t for t in re.split(r"\W+", (keywords or "").lower()) if len(t) > 2]
        matched = [
            str(r["seriesNo"])
            for r in rows
            if any(t in str(r.get("rowText", "")).lower() for t in tokens)
        ]
        if not matched:
            matched = [str(r["seriesNo"]) for r in rows if "." not in str(r["seriesNo"])]
        return ",".join(matched[:max_rows]) or None

    async def _mcp_fetch(
        self,
        dataset_id: str,
        time_filter: str | list[str] | None = None,
        series_no: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame | None:
        """Fetch via MCP: always metadata first, then data with series/time filters."""
        if not self._mcp_enabled():
            return None
        series_no = series_no or kwargs.get("seriesNoORrowNo")
        mcp_time = self._to_mcp_time_filter(time_filter)
        try:
            meta_payload, = await self._mcp_call([("get_table_metadata", {"resource_id": dataset_id})])
            records = ((meta_payload or {}).get("data") or {}).get("records") or {}
            rows = records.get("row") or []
            total = int(records.get("total") or 0)

            args: dict[str, Any] = {"resource_id": dataset_id}
            if series_no:
                args["seriesNoORrowNo"] = str(series_no)
            if mcp_time:
                args["timeFilter"] = mcp_time
            elif total > self.MCP_MAX_ROWS:
                # Avoid truncated 3,000-row dumps: default to the most recent 5 years.
                end_year = str(records.get("endPeriod") or "")[:4]
                if end_year.isdigit():
                    args["timeFilter"] = [f"{int(end_year) - 4}-01", f"{end_year}-12"]
            logger.info(
                "SingStat MCP get_table_data %s (rows=%d total=%d args=%s)",
                dataset_id, len(rows), total, args,
            )

            (data_payload,) = await self._mcp_call([("get_table_data", args)])
            df = self._parse_json_payload(data_payload)
            if df is not None and not df.empty:
                units = {str(r.get("rowText")): r.get("uoM") for r in rows if isinstance(r, dict)}
                if units:
                    df["unit"] = df["series"].map(units)
                df.attrs["table_title"] = records.get("title")
                df.attrs["last_updated"] = records.get("dataLastUpdated")
            return df
        except Exception as exc:
            logger.warning("SingStat MCP fetch failed for '%s': %s", dataset_id, exc)
            return None

    def _extract_search_records(self, data: Any) -> list[dict[str, Any]]:
        """Extract table records from varied SingStat JSON response envelopes."""
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]

        if isinstance(data, dict):
            # Check Data / data -> records/rows/tables
            inner_data = data.get("Data") if "Data" in data else data.get("data")
            if isinstance(inner_data, list):
                return [x for x in inner_data if isinstance(x, dict)]
            if isinstance(inner_data, dict):
                recs = (
                    inner_data.get("records")
                    or inner_data.get("Records")
                    or inner_data.get("rows")
                    or inner_data.get("row")
                    or inner_data.get("tables")
                )
                if isinstance(recs, list):
                    return [x for x in recs if isinstance(x, dict)]

            # Root records/results
            recs = (
                data.get("records")
                or data.get("Records")
                or data.get("results")
                or data.get("rows")
            )
            if isinstance(recs, list):
                return [x for x in recs if isinstance(x, dict)]

        return []

    async def fetch(self, dataset_id: str, time_filter: str | None = None, **kwargs: Any) -> pd.DataFrame:
        """Fetch and return a normalized DataFrame from SingStat Table Builder.

        Args:
            dataset_id: SingStat table identifier (e.g. 'M810361').
            time_filter: Optional comma-separated time periods or years (e.g. '2023,2024').
            **kwargs: Additional parameters for tabledata retrieval.

        Returns:
            Normalized pandas DataFrame with lowercase columns, underscores,
            UTC timestamps, '_source', and '_fetched_at' columns.
        """
        if not dataset_id or not isinstance(dataset_id, str) or not dataset_id.strip():
            logger.warning("SingStat fetch called with empty or invalid dataset_id: %r", dataset_id)
            return pd.DataFrame()

        clean_id = dataset_id.strip()

        # 1. Offline / Mock Mode Check
        if settings.USE_MOCK_DATA_SOURCES:
            logger.info("USE_MOCK_DATA_SOURCES is True; SingStat fetch falling back to mock")
            return await self._fallback_fetch_mock(clean_id, time_filter=time_filter)

        # 2a. Preferred: official SingStat MCP (metadata -> filtered data)
        mcp_df = await self._mcp_fetch(clean_id, time_filter=time_filter, **kwargs)
        if mcp_df is not None and not mcp_df.empty:
            return self._finalize_dataframe(
                mcp_df,
                dataset_id=clean_id,
                url=f"https://tablebuilder.singstat.gov.sg/table/{clean_id}",
            )

        # 2b. Fallback: live REST table data retrieval
        url = f"{self.TABLE_DATA_ENDPOINT}/{clean_id}"
        query_params: dict[str, str] = {}
        if time_filter:
            query_params["timeFilter"] = str(time_filter).strip()

        try:
            if self._custom_client:
                resp = await self._custom_client.get(
                    url,
                    params=query_params if query_params else None,
                    headers=self._get_headers(),
                )
            else:
                async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                    resp = await client.get(
                        url,
                        params=query_params if query_params else None,
                        headers=self._get_headers(),
                    )
            resp.raise_for_status()

            raw_df = self._parse_table_response(resp)
            if raw_df is not None and not raw_df.empty:
                return self._finalize_dataframe(raw_df, dataset_id=clean_id, url=url)

            if getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False) or settings.USE_MOCK_DATA_SOURCES:
                logger.warning(
                    "SingStat response for '%s' could not be parsed into non-empty DataFrame; falling back to mock",
                    clean_id,
                )
                return await self._fallback_fetch_mock(clean_id, time_filter=time_filter)

            logger.error(
                "SingStat response for '%s' could not be parsed into non-empty DataFrame (mock fallback disabled)",
                clean_id,
            )
            return pd.DataFrame()

        except Exception as exc:
            if getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False) or settings.USE_MOCK_DATA_SOURCES:
                logger.warning(
                    "SingStat fetch failed for '%s' (%s); falling back to mock data",
                    clean_id,
                    exc,
                )
                return await self._fallback_fetch_mock(clean_id, time_filter=time_filter)
            logger.error(
                "SingStat fetch failed for '%s' (%s) and USE_MOCK_DATA_AS_FALLBACK=false",
                clean_id,
                exc,
            )
            return pd.DataFrame()

    def _parse_table_response(self, resp: httpx.Response) -> pd.DataFrame | None:
        """Parse SingStat HTTP response (CSV text, Excel spreadsheet, or JSON structure) into DataFrame."""
        content_type = resp.headers.get("content-type", "").lower()
        text = resp.text.strip()

        # Handle Excel formatted response (.xlsx, .xls, openxml)
        if (
            "excel" in content_type
            or "spreadsheet" in content_type
            or resp.content.startswith(b"PK\x03\x04")
            or resp.content.startswith(b"\xd0\xcf\x11\xe0")
        ):
            try:
                return pd.read_excel(io.BytesIO(resp.content))
            except Exception as excel_err:
                logger.debug("Failed parsing response as Excel: %s", excel_err)

        # Handle CSV formatted response
        if "csv" in content_type or (not text.startswith("{") and not text.startswith("[")):
            try:
                return pd.read_csv(io.StringIO(text))
            except Exception as csv_err:
                logger.debug("Failed parsing response as CSV: %s", csv_err)

        # Handle JSON formatted response
        try:
            data = resp.json()
        except Exception as json_err:
            logger.debug("Failed parsing response as JSON: %s", json_err)
            return None
        return self._parse_json_payload(data)

    def _parse_json_payload(self, data: Any) -> pd.DataFrame | None:
        """Parse a decoded SingStat JSON payload (REST or MCP) into a DataFrame."""
        # Case 1: SingStat hierarchical table structure: {"Data": {"row": [...]}} or {"data": {"row": [...]}}
        if isinstance(data, dict):
            inner_data = data.get("Data") if "Data" in data else data.get("data")
            if isinstance(inner_data, dict):
                rows = inner_data.get("row") or inner_data.get("rows") or inner_data.get("Row")
                if isinstance(rows, list):
                    flattened: list[dict[str, Any]] = []

                    def _extract_columns_recursive(
                        cols_list: list[Any], series_label: str, parent_period: str = ""
                    ) -> None:
                        for c in cols_list:
                            if not isinstance(c, dict):
                                continue
                            c_key = str(c.get("key") or c.get("Key") or parent_period).strip()
                            if "value" in c or "Value" in c:
                                raw_val = c.get("value") if "value" in c else c.get("Value")
                                if raw_val not in (None, "na", "NA", "-", "n.a."):
                                    # Extract 4-digit year if present for easier temporal grouping
                                    year_val = c_key[:4] if len(c_key) >= 4 and c_key[:4].isdigit() else c_key
                                    try:
                                        num_val: Any = float(str(raw_val).replace(",", ""))
                                    except (ValueError, TypeError):
                                        num_val = raw_val
                                    flattened.append(
                                        {
                                            "year": year_val,
                                            "period": c_key,
                                            "sector": series_label,
                                            "series": series_label,
                                            "value": num_val,
                                        }
                                    )
                            nested_cols = c.get("columns") or c.get("Columns")
                            if isinstance(nested_cols, list):
                                _extract_columns_recursive(nested_cols, series_label, c_key)

                    for r in rows:
                        if not isinstance(r, dict):
                            continue
                        series_name = str(
                            r.get("rowText")
                            or r.get("RowText")
                            or r.get("series")
                            or r.get("row")
                            or "Total"
                        ).strip()
                        cols = r.get("columns") or r.get("Columns") or []
                        if isinstance(cols, list):
                            _extract_columns_recursive(cols, series_name)
                        elif isinstance(cols, dict):
                            for k, v in cols.items():
                                k_str = str(k).strip()
                                year_val = k_str[:4] if len(k_str) >= 4 and k_str[:4].isdigit() else k_str
                                try:
                                    num_val = float(str(v).replace(",", ""))
                                except (ValueError, TypeError):
                                    num_val = v
                                flattened.append(
                                    {
                                        "year": year_val,
                                        "period": k_str,
                                        "sector": series_name,
                                        "series": series_name,
                                        "value": num_val,
                                    }
                                )
                    if flattened:
                        return pd.DataFrame(flattened)

            # Case 2: {"Data": [{"col": ...}]} or {"records": [...]}
            if isinstance(inner_data, list):
                return pd.DataFrame(inner_data)

            recs = data.get("records") or data.get("Records") or data.get("rows")
            if isinstance(recs, list):
                return pd.DataFrame(recs)

        elif isinstance(data, list):
            return pd.DataFrame(data)

        return None

    def _finalize_dataframe(
        self,
        raw_df: pd.DataFrame,
        dataset_id: str,
        url: str | None = None,
        is_fallback: bool = False,
    ) -> pd.DataFrame:
        """Normalize DataFrame columns and stamp metadata and audit columns."""
        fetched_at_str = datetime.now(UTC).isoformat()
        metadata: dict[str, Any] = {
            "source": self.source_id,
            "dataset_id": dataset_id,
            "requested_id": dataset_id,
            "url": url or f"https://tablebuilder.singstat.gov.sg/table/{dataset_id}",
            "fetched_at": fetched_at_str,
            "fallback": is_fallback,
        }

        # Normalize column names and timestamps via AbstractDataSource
        df = self.normalize_dataframe(raw_df, metadata=metadata)

        # Append explicit audit/provenance columns
        df["_source"] = self.source_id
        df["_fetched_at"] = fetched_at_str
        return df

    async def _fallback_fetch_mock(
        self, dataset_id: str, time_filter: str | None = None
    ) -> pd.DataFrame:
        """Retrieve fallback data from MockInternalDataSource when live request fails."""
        # 1. Direct fetch via mock catalog or aliases
        df = await self._mock_source.fetch(dataset_id)

        # 2. Heuristic fallback if dataset_id is an external ID not in mock catalog
        if df.empty:
            id_lower = dataset_id.lower()
            if any(k in id_lower for k in ("ict", "tech", "software", "digital")):
                fallback_id = "ict_workforce_trends"
            elif any(k in id_lower for k in ("unemploy", "jobless")):
                fallback_id = "unemployment_rate_quarterly"
            elif any(k in id_lower for k in ("wage", "salary", "income", "earning")):
                fallback_id = "median_gross_wages"
            elif any(k in id_lower for k in ("business", "company", "registration", "acra")):
                fallback_id = "business_registrations"
            else:
                fallback_id = "employment_by_sector"

            logger.info(
                "SingStat mapping external ID '%s' to mock dataset '%s'",
                dataset_id,
                fallback_id,
            )
            df = await self._mock_source.fetch(fallback_id)

        if not df.empty:
            # Apply time filter if requested (e.g. '2023,2024')
            if time_filter:
                filter_years = [y.strip() for y in str(time_filter).split(",") if y.strip()]
                for col in ("year", "period", "period_start"):
                    if col in df.columns:
                        mask = df[col].astype(str).str.strip().apply(
                            lambda val: any(fy in val for fy in filter_years)
                        )
                        if mask.any():
                            df = df[mask].copy()
                        break

            return self._finalize_dataframe(
                df,
                dataset_id=dataset_id,
                url=f"https://tablebuilder.singstat.gov.sg/table/{dataset_id}",
                is_fallback=True,
            )

        return pd.DataFrame()

    async def health_check(self) -> bool:
        """Probe SingStat Table Builder API availability with a 5-second timeout."""
        if settings.USE_MOCK_DATA_SOURCES:
            return True

        try:
            if self._custom_client:
                resp = await self._custom_client.get(
                    self.HEALTH_CHECK_URL,
                    headers=self._get_headers(),
                )
            else:
                async with httpx.AsyncClient(timeout=self.HEALTH_TIMEOUT) as client:
                    resp = await client.get(
                        self.HEALTH_CHECK_URL,
                        headers=self._get_headers(),
                    )
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("SingStat health check failed: %s", exc)
            return False
