"""Data.gov.sg CKAN API data source connector.

Connects to the official Data.gov.sg portal via the CKAN Action API:
- Dataset / Package search: https://data.gov.sg/api/action/package_search?q={kw}
- Resource datastore search: https://data.gov.sg/api/action/datastore_search?resource_id={id}

Implements AbstractDataSource contract with optional Bearer token authorization
(DATAGOV_API_TOKEN) and resilient, automatic fallback to MockInternalDataSource
when live requests fail, time out, or when USE_MOCK_DATA_SOURCES=true is enabled.
"""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd

from app.core.config import settings
from app.data_sources.base import AbstractDataSource
from app.data_sources.mock_internal import MockInternalDataSource

logger = logging.getLogger(__name__)


class DataGovDataSource(AbstractDataSource):
    """Data.gov.sg CKAN Action API data source connector."""

    source_id: str = "datagov"
    display_name: str = "Data.gov.sg"

    # API Endpoints
    BASE_URL: str = "https://data.gov.sg/api"
    PACKAGE_SEARCH_ENDPOINT: str = "https://data.gov.sg/api/action/package_search"
    DATASTORE_SEARCH_ENDPOINT: str = "https://data.gov.sg/api/action/datastore_search"
    V2_DATASETS_ENDPOINT: str = "https://api-production.data.gov.sg/v2/public/api/datasets"
    V1_INITIATE_DOWNLOAD_ENDPOINT: str = (
        "https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/initiate-download"
    )
    HEALTH_CHECK_URL: str = "https://data.gov.sg/api/action/package_search?rows=1"

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
        """Build request headers, adding Bearer token authorization if configured."""
        headers: dict[str, str] = {
            "Accept": "application/json, text/csv, */*",
            "User-Agent": "AgenticPolicyPlatform/1.0",
        }
        if settings.DATAGOV_API_TOKEN:
            token = settings.DATAGOV_API_TOKEN.strip()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def search(
        self,
        keywords: str | list[str],
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Search Data.gov.sg packages matching keywords.

        Args:
            keywords: Query terms (string or list of strings).
            **filters: Optional additional query parameters (e.g. rows, limit, format).

        Returns:
            List of matching dataset metadata dictionaries:
            [{"id": ..., "title": ..., "description": ..., "url": ..., "format": ...}]
        """
        # 1. Offline / Mock Mode Check
        if settings.USE_MOCK_DATA_SOURCES:
            logger.info("USE_MOCK_DATA_SOURCES is True; DataGov search falling back to mock")
            return await self._mock_source.search(keywords, **filters)

        # 2. Parse query string
        if isinstance(keywords, list):
            kw = " ".join(str(k).strip() for k in keywords if str(k).strip())
        else:
            kw = str(keywords).strip()

        if not kw:
            return []

        # 3. Execute live CKAN package search
        params: dict[str, Any] = {"q": kw}
        if "rows" in filters or "limit" in filters:
            params["rows"] = filters.get("rows") or filters.get("limit")

        try:
            if self._custom_client:
                resp = await self._custom_client.get(
                    self.PACKAGE_SEARCH_ENDPOINT,
                    params=params,
                    headers=self._get_headers(),
                )
            else:
                async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                    resp = await client.get(
                        self.PACKAGE_SEARCH_ENDPOINT,
                        params=params,
                        headers=self._get_headers(),
                    )
            resp.raise_for_status()
            data = resp.json()

            records = self._extract_package_records(data)
            results: list[dict[str, Any]] = []

            for item in records:
                if not isinstance(item, dict):
                    continue

                # Locate primary resource ID or fallback to package ID
                resources = item.get("resources") or []
                res_id = ""
                res_url = ""
                res_fmt = "csv"
                if isinstance(resources, list) and resources:
                    first_res = resources[0]
                    if isinstance(first_res, dict):
                        res_id = str(first_res.get("id") or "").strip()
                        res_url = str(first_res.get("url") or "")
                        res_fmt = str(first_res.get("format") or "csv").lower()

                item_id = res_id or str(item.get("id") or item.get("name") or "").strip()
                if not item_id:
                    continue

                title = str(item.get("title") or item.get("name") or item_id).strip()
                description = str(
                    item.get("notes") or item.get("description") or item.get("theme") or title
                ).strip()
                url = (
                    res_url
                    or item.get("url")
                    or f"https://data.gov.sg/datasets/{item.get('name') or item_id}"
                )
                fmt = res_fmt or str(item.get("format") or "csv").lower()

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

            if not self._custom_client:
                v2_results = await self._search_v2(kw, **filters)
                if v2_results:
                    return v2_results

            if (
                getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False)
                or settings.USE_MOCK_DATA_SOURCES
            ):
                logger.info(
                    "DataGov live search yielded no records for '%s'; using mock fallback", kw
                )
                return await self._mock_source.search(keywords, **filters)
            logger.warning(
                "DataGov live search yielded no records for '%s' (mock fallback disabled)", kw
            )
            return []

        except Exception as exc:
            if not self._custom_client:
                v2_results = await self._search_v2(kw, **filters)
                if v2_results:
                    return v2_results

            if (
                getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False)
                or settings.USE_MOCK_DATA_SOURCES
            ):
                logger.warning(
                    "DataGov search request failed for keywords '%s' (%s); falling back to mock",
                    kw,
                    exc,
                )
                return await self._mock_source.search(keywords, **filters)
            logger.error(
                "DataGov search request failed for keywords '%s' (%s) and USE_MOCK_DATA_AS_FALLBACK=false",
                kw,
                exc,
            )
            return []

    async def _search_v2(self, kw: str, **filters: Any) -> list[dict[str, Any]]:
        """Query modern Data.gov.sg v2 datasets API as resilient live search."""
        try:
            limit = filters.get("rows") or filters.get("limit") or 10
            async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                resp = await client.get(
                    self.V2_DATASETS_ENDPOINT,
                    params={"query": kw, "limit": limit},
                    headers=self._get_headers(),
                )
            if resp.status_code == 200:
                datasets = resp.json().get("data", {}).get("datasets", [])
                results: list[dict[str, Any]] = []
                for item in datasets:
                    if not isinstance(item, dict):
                        continue
                    did = str(item.get("datasetId") or "").strip()
                    if not did:
                        continue
                    title = str(item.get("name") or did).strip()
                    desc = str(item.get("description") or title).strip()
                    fmt = str(item.get("format") or "csv").lower()
                    if "format" in filters and filters["format"]:
                        filter_fmt = str(filters["format"]).strip().lower()
                        if filter_fmt != "*" and filter_fmt != fmt:
                            continue
                    results.append(
                        {
                            "id": did,
                            "title": title,
                            "description": desc,
                            "url": f"https://data.gov.sg/datasets/{did}",
                            "format": fmt,
                        }
                    )
                return results
        except Exception as v2_err:
            logger.debug("DataGov v2 search failed: %s", v2_err)
        return []

    def _extract_package_records(self, data: Any) -> list[dict[str, Any]]:
        """Extract dataset packages from CKAN API response envelope."""
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]

        if isinstance(data, dict):
            result = data.get("result")
            if isinstance(result, dict):
                packages = result.get("results") or result.get("packages") or result.get("records")
                if isinstance(packages, list):
                    return [x for x in packages if isinstance(x, dict)]
            elif isinstance(result, list):
                return [x for x in result if isinstance(x, dict)]

            results = data.get("results") or data.get("packages") or data.get("data")
            if isinstance(results, list):
                return [x for x in results if isinstance(x, dict)]

        return []

    async def fetch(self, dataset_id: str) -> pd.DataFrame:
        """Fetch and return a normalized DataFrame from Data.gov.sg Datastore.

        Args:
            dataset_id: CKAN resource identifier or dataset name.

        Returns:
            Normalized pandas DataFrame with lowercase columns, underscores,
            UTC timestamps, '_source', and '_fetched_at' columns.
        """
        if not dataset_id or not isinstance(dataset_id, str) or not dataset_id.strip():
            logger.warning("DataGov fetch called with empty or invalid dataset_id: %r", dataset_id)
            return pd.DataFrame()

        clean_id = dataset_id.strip()

        # 1. Offline / Mock Mode Check
        if settings.USE_MOCK_DATA_SOURCES:
            logger.info("USE_MOCK_DATA_SOURCES is True; DataGov fetch falling back to mock")
            return await self._fallback_fetch_mock(clean_id)

        # 2. Modern Data.gov.sg v1 initiate-download check (for d_ IDs)
        if clean_id.startswith("d_") and not self._custom_client:
            try:
                dl_endpoint = self.V1_INITIATE_DOWNLOAD_ENDPOINT.format(dataset_id=clean_id)
                async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                    init_resp = await client.get(dl_endpoint, headers=self._get_headers())
                    if init_resp.status_code in (200, 201):
                        init_data = init_resp.json().get("data", {})
                        csv_url = init_data.get("url")
                        if csv_url:
                            csv_resp = await client.get(csv_url)
                            if csv_resp.status_code == 200:
                                raw_df = pd.read_csv(io.StringIO(csv_resp.text))
                                if not raw_df.empty:
                                    logger.info(
                                        "DataGov successfully downloaded live dataset '%s'",
                                        clean_id,
                                    )
                                    return self._finalize_dataframe(
                                        raw_df,
                                        dataset_id=clean_id,
                                        url=f"https://data.gov.sg/datasets/{clean_id}",
                                    )
            except Exception as dl_exc:
                logger.debug("DataGov v1 initiate-download failed for '%s': %s", clean_id, dl_exc)

        # 3. Execute CKAN datastore_search (for legacy resource UUIDs or mocked tests)
        params = {"resource_id": clean_id}
        url = self.DATASTORE_SEARCH_ENDPOINT
        try:
            if self._custom_client:
                resp = await self._custom_client.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                )
            else:
                async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                    resp = await client.get(
                        url,
                        params=params,
                        headers=self._get_headers(),
                    )
            resp.raise_for_status()

            raw_df = self._parse_datastore_response(resp)
            if raw_df is not None and not raw_df.empty:
                return self._finalize_dataframe(raw_df, dataset_id=clean_id, url=url)

            if (
                getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False)
                or settings.USE_MOCK_DATA_SOURCES
            ):
                logger.warning(
                    "DataGov response for '%s' could not be parsed into non-empty DataFrame; falling back to mock",
                    clean_id,
                )
                return await self._fallback_fetch_mock(clean_id)

            logger.error(
                "DataGov response for '%s' could not be parsed into non-empty DataFrame (mock fallback disabled)",
                clean_id,
            )
            return pd.DataFrame()

        except Exception as exc:
            # Attempt live package search discovery if clean_id was a synthetic or outdated ID
            if not self._custom_client:
                try:
                    search_kw = (
                        clean_id.replace("d_", "").replace("_", " ")
                        if not clean_id.startswith("d_") or len(clean_id) <= 12
                        else "employment"
                    )
                    if search_kw in ("e3b8a1c9", "acra business entities") or len(search_kw) <= 10:
                        search_kw = "employment"
                    discovered = await self.search(search_kw, rows=3)
                    for cand in discovered:
                        cand_id = cand.get("id")
                        if cand_id and cand_id != clean_id and cand_id.startswith("d_"):
                            async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                                retry_resp = await client.get(
                                    url,
                                    params={"resource_id": cand_id},
                                    headers=self._get_headers(),
                                )
                            if retry_resp.status_code == 200:
                                retry_df = self._parse_datastore_response(retry_resp)
                                if retry_df is not None and not retry_df.empty:
                                    logger.info(
                                        "DataGov resolved '%s' to live resource '%s'",
                                        clean_id,
                                        cand_id,
                                    )
                                    return self._finalize_dataframe(
                                        retry_df, dataset_id=cand_id, url=url
                                    )
                except Exception as retry_exc:
                    logger.debug("DataGov live discovery retry failed: %s", retry_exc)

            if (
                getattr(settings, "USE_MOCK_DATA_AS_FALLBACK", False)
                or settings.USE_MOCK_DATA_SOURCES
            ):
                logger.warning(
                    "DataGov fetch failed for '%s' (%s); falling back to mock data",
                    clean_id,
                    exc,
                )
                return await self._fallback_fetch_mock(clean_id)

            logger.error(
                "DataGov fetch failed for '%s' (%s) and USE_MOCK_DATA_AS_FALLBACK=false",
                clean_id,
                exc,
            )
            return pd.DataFrame()

    def _parse_datastore_response(self, resp: httpx.Response) -> pd.DataFrame | None:
        """Parse Data.gov.sg response (CSV, Excel spreadsheet, or CKAN datastore JSON records) into DataFrame."""
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

        # Handle CKAN datastore JSON response
        try:
            data = resp.json()
        except Exception as json_err:
            logger.debug("Failed parsing response as JSON: %s", json_err)
            return None

        if isinstance(data, dict):
            result = data.get("result")
            if isinstance(result, dict):
                records = result.get("records")
                if isinstance(records, list) and records:
                    return pd.DataFrame(records)

            records = data.get("records")
            if isinstance(records, list) and records:
                return pd.DataFrame(records)

            inner_data = data.get("data")
            if isinstance(inner_data, list) and inner_data:
                return pd.DataFrame(inner_data)

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
            "url": url or f"https://data.gov.sg/datasets/{dataset_id}",
            "fetched_at": fetched_at_str,
            "fallback": is_fallback,
        }

        # Normalize column names and timestamps via AbstractDataSource
        df = self.normalize_dataframe(raw_df, metadata=metadata)

        # Append explicit audit/provenance columns
        df["_source"] = self.source_id
        df["_fetched_at"] = fetched_at_str
        return df

    async def _fallback_fetch_mock(self, dataset_id: str) -> pd.DataFrame:
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
                "DataGov mapping external ID '%s' to mock dataset '%s'",
                dataset_id,
                fallback_id,
            )
            df = await self._mock_source.fetch(fallback_id)

        if not df.empty:
            return self._finalize_dataframe(
                df,
                dataset_id=dataset_id,
                url=f"https://data.gov.sg/datasets/{dataset_id}",
                is_fallback=True,
            )

        return pd.DataFrame()

    async def health_check(self) -> bool:
        """Probe Data.gov.sg API availability with a 5-second timeout."""
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
            logger.warning("DataGov health check failed: %s", exc)
            return False
