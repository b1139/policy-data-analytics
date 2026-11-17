"""Hallucination detection and verification service for policy data insights (Story S31).

Provides multi-dimensional verification of LLM-generated narrative insights:
1. Citation Grounding: Validates that all cited sources exist in retrieved dataset metadata.
2. Numeric Consistency: Verifies that cited metrics/percentages align within 15% tolerance
   of computed deterministic statistical values.
3. Source Attribution: Checks that all quantitative claims include explicit attribution
   phrases ("according to", "based on", etc.) or year references.
"""

from __future__ import annotations

import contextlib
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class HallucinationCheckResult(BaseModel):
    """Structured report produced by hallucination check routines."""

    passed: bool
    ungrounded_citations: list[str] = Field(default_factory=list)
    suspicious_numbers: list[str] = Field(default_factory=list)
    unattributed_claims: list[str] = Field(default_factory=list)
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, item: str) -> Any:
        """Support dictionary-style access for backwards compatibility."""
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item) from None

    def get(self, item: str, default: Any = None) -> Any:
        """Support dictionary-style get access."""
        return getattr(self, item, default)

    def to_dict(self) -> dict[str, Any]:
        """Convert result model to serializable Python dictionary."""
        return self.model_dump()


class HallucinationDetector:
    """Evaluates generated policy narratives against underlying datasets and statistics."""

    # Official and common agencies/sources recognized in Singapore policy context
    KNOWN_AGENCIES: dict[str, set[str]] = {
        "singstat": {
            "singstat",
            "singapore department of statistics",
            "department of statistics",
            "dos",
            "tablebuilder",
        },
        "datagov": {
            "datagov",
            "data.gov.sg",
            "data gov sg",
            "singapore government data",
        },
        "mom": {
            "mom",
            "ministry of manpower",
            "manpower ministry",
        },
        "mof": {
            "mof",
            "ministry of finance",
        },
        "mas": {
            "mas",
            "monetary authority of singapore",
        },
        "mti": {
            "mti",
            "ministry of trade and industry",
        },
        "hdb": {
            "hdb",
            "housing & development board",
            "housing and development board",
        },
        "ura": {
            "ura",
            "urban redevelopment authority",
        },
        "lta": {
            "lta",
            "land transport authority",
        },
        "nea": {
            "nea",
            "national environment agency",
        },
        "cpf": {
            "cpf",
            "central provident fund",
            "cpf board",
        },
        "mock": {
            "mock",
            "internal",
            "mock database",
            "internal database",
            "synthetic",
        },
    }

    # External institutions that should be flagged if not in datasets metadata
    EXTERNAL_INSTITUTIONS: set[str] = {
        "world bank",
        "imf",
        "international monetary fund",
        "oecd",
        "eurostat",
        "federal reserve",
        "fed",
        "bureau of labor statistics",
        "bls",
        "united nations",
        "un",
        "pew research",
        "pew research center",
        "statista",
        "wikipedia",
        "asian development bank",
        "adb",
        "bank of england",
        "european central bank",
        "ecb",
    }

    ATTRIBUTION_PHRASES: tuple[str, ...] = (
        "according to",
        "based on",
        "data from",
        "source:",
        "sources:",
        "reported by",
        "published by",
        "as per",
        "cited by",
        "statistics from",
        "findings from",
        "records from",
        "documented by",
        "released by",
    )

    def check_citation_grounding(
        self,
        insights: str,
        datasets: list[dict[str, Any]] | list[Any],
    ) -> HallucinationCheckResult:
        """Verify that every data source or institution cited in the insight exists in dataset metadata.

        Args:
            insights: LLM-generated narrative insight text.
            datasets: List of dataset metadata objects or dictionaries retrieved for the query.

        Returns:
            HallucinationCheckResult with passed=True if all citations are grounded,
            or list of ungrounded citations if hallucinated sources are detected.
        """
        if not insights or not insights.strip():
            return HallucinationCheckResult(
                passed=True,
                ungrounded_citations=[],
                message="Insight text is empty; no ungrounded citations found.",
            )

        # 1. Build catalog of valid normalized source identifiers from retrieved datasets
        valid_identifiers: set[str] = set()
        for ds in datasets or []:
            if isinstance(ds, dict):
                src = str(ds.get("source") or "").lower().strip()
                title = str(ds.get("title") or "").lower().strip()
                agency = str(ds.get("agency") or ds.get("publisher") or "").lower().strip()
                ds_id = str(ds.get("dataset_id") or ds.get("id") or "").lower().strip()
            else:
                src = str(getattr(ds, "source", "") or "").lower().strip()
                title = str(getattr(ds, "title", "") or "").lower().strip()
                agency = (
                    str(getattr(ds, "agency", getattr(ds, "publisher", "")) or "").lower().strip()
                )
                ds_id = str(getattr(ds, "dataset_id", getattr(ds, "id", "")) or "").lower().strip()

            for token in (src, title, agency, ds_id):
                if token:
                    valid_identifiers.add(token)

            # Expand recognized aliases
            for aliases in self.KNOWN_AGENCIES.values():
                if any(alias in src or alias in agency or alias in title for alias in aliases):
                    valid_identifiers.update(aliases)

        # 2. Extract candidate citations from insight text
        mentioned_sources: list[str] = []
        text_lower = insights.lower()

        # Check for mentions of external non-grounded bodies
        for ext in self.EXTERNAL_INSTITUTIONS:
            if re.search(rf"\b{re.escape(ext)}\b", text_lower) and not any(
                ext in valid_id for valid_id in valid_identifiers
            ):
                mentioned_sources.append(ext.title())

        # Check for known agency mentions that are NOT in dataset metadata
        for group_name, aliases in self.KNOWN_AGENCIES.items():
            if group_name == "mock":
                continue
            for alias in aliases:
                # Match full word
                if len(alias) >= 3 and re.search(rf"\b{re.escape(alias)}\b", text_lower):
                    # Check if this agency is represented in retrieved datasets
                    grounded = any(
                        alias in valid_id or valid_id in alias for valid_id in valid_identifiers
                    )
                    if not grounded:
                        pretty_name = alias.title() if len(alias) > 4 else alias.upper()
                        if pretty_name not in mentioned_sources:
                            mentioned_sources.append(pretty_name)

        # Regex patterns for explicit citation clauses: e.g. "According to World Bank,"
        citation_regexes = [
            r"(?i)\baccording\s+to\s+(?:the\s+)?([A-Z][A-Za-z0-9\.\s&-]{2,45}?)(?:,|\.|\n|;|\s+in\s+\d{4}|\s+shows|\s+indicates|\s+reports)",
            r"(?i)\bbased\s+on\s+(?:official\s+)?(?:records\s+from|data\s+from|statistics\s+from|reports\s+from)?\s*(?:the\s+)?([A-Z][A-Za-z0-9\.\s&-]{2,45}?)(?:,|\.|\n|;|\s+in\s+\d{4})",
            r"(?i)\bsource:\s*([A-Za-z0-9\.\s&-]{2,45})(?:[;\n.]|$)",
            r"(?i)\bpublished\s+by\s+(?:the\s+)?([A-Z][A-Za-z0-9\.\s&-]{2,45}?)(?:,|\.|\n|;)",
        ]
        for pattern in citation_regexes:
            for match in re.finditer(pattern, insights):
                raw_cand = match.group(1).strip()
                cand_lower = raw_cand.lower()
                # Exclude common non-source phrases
                if cand_lower in {
                    "official statistics",
                    "the data",
                    "our analysis",
                    "recent findings",
                    "the table",
                }:
                    continue
                # Verify whether candidate is supported by valid_identifiers
                cand_grounded = any(
                    cand_lower in valid_id or valid_id in cand_lower
                    for valid_id in valid_identifiers
                )
                if not cand_grounded and raw_cand not in mentioned_sources:
                    mentioned_sources.append(raw_cand)

        # Deduplicate while preserving order
        seen = set()
        ungrounded: list[str] = []
        for s in mentioned_sources:
            norm = s.lower().strip()
            if norm not in seen:
                seen.add(norm)
                ungrounded.append(s)

        passed = len(ungrounded) == 0
        message = (
            "All cited sources grounded in dataset metadata."
            if passed
            else f"Detected {len(ungrounded)} ungrounded citation(s): {', '.join(ungrounded)}"
        )
        return HallucinationCheckResult(
            passed=passed,
            ungrounded_citations=ungrounded,
            message=message,
        )

    def check_numeric_consistency(
        self,
        insights: str,
        stats: dict[str, Any] | Any,
        tolerance: float = 0.15,
    ) -> HallucinationCheckResult:
        r"""Verify that numerical claims and percentages in the insight match computed statistics.

        Acceptance Criteria:
        - Extracts all numbers/percentages from insights text (regex r'\b\d+\.?\d*\s*%'
          and r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b')
        - For each number: checks if within 15% tolerance of any value in stats_result
        - Reports: {passed: bool, suspicious_numbers: list[str]}

        Args:
            insights: Narrative insight text.
            stats: Computed statistics dictionary or StatsResult instance.
            tolerance: Relative tolerance threshold (default 0.15 = 15%).

        Returns:
            HallucinationCheckResult detailing consistency status and suspicious numbers.
        """
        if not insights or not insights.strip():
            return HallucinationCheckResult(
                passed=True,
                suspicious_numbers=[],
                message="Insight text is empty; no numeric inconsistencies found.",
            )

        # 1. Extract candidate numbers from insights
        pct_matches = list(re.finditer(r"\b\d+\.?\d*\s*%", insights))
        pct_spans = [m.span() for m in pct_matches]
        pct_strings = [m.group(0).strip() for m in pct_matches]

        num_matches = list(re.finditer(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b", insights))
        num_strings: list[str] = []
        for m in num_matches:
            # Skip if part of an already extracted percentage
            if any(start <= m.start() and m.end() <= end for start, end in pct_spans):
                continue
            # Skip section formatting like "1." at beginning of line
            token = m.group(0).strip()
            num_strings.append(token)

        # 2. Extract all numeric values from stats dictionary / model
        stat_values = self._extract_numbers_from_stats(stats)
        calendar_years = self._extract_calendar_years(stats)

        suspicious_numbers: list[str] = []

        # 3. Verify percentages
        for pct_str in pct_strings:
            try:
                val = float(pct_str.rstrip("%").strip())
            except ValueError:
                continue

            matched = False
            for s in stat_values:
                # Compare as raw percentage (e.g. 20% vs 20.0)
                diff = abs(val - s) / abs(s) if s != 0 else abs(val - s)
                if diff <= tolerance:
                    matched = True
                    break
                # Compare decimal fraction if stat is in [0, 1] range (e.g. 20% vs 0.20)
                if abs(s) <= 1.0 and s != 0:
                    diff_frac = abs(val / 100.0 - s) / abs(s)
                    if diff_frac <= tolerance:
                        matched = True
                        break

            if not matched:
                suspicious_numbers.append(pct_str)

        # 4. Verify regular numbers
        for num_str in num_strings:
            clean = num_str.replace(",", "")
            try:
                val = float(clean)
            except ValueError:
                continue

            # Allow recognized 4-digit calendar years
            if 1900 <= val <= 2099 and (val in calendar_years or int(val) in calendar_years):
                continue

            # Skip small integers 1-5 when used as ordinal bullet points (e.g. "1.", "2.")
            if val in {1, 2, 3, 4, 5} and re.search(
                rf"(?:^|\n)\s*\(?{re.escape(num_str)}[\.\)]", insights
            ):
                continue

            matched = False
            for s in stat_values:
                diff = abs(val - s) / abs(s) if s != 0 else abs(val - s)
                if diff <= tolerance:
                    matched = True
                    break

            if not matched:
                suspicious_numbers.append(num_str)

        passed = len(suspicious_numbers) == 0
        message = (
            "All quantitative values consistent with computed statistics."
            if passed
            else f"Detected {len(suspicious_numbers)} suspicious number(s): {', '.join(suspicious_numbers)}"
        )
        return HallucinationCheckResult(
            passed=passed,
            suspicious_numbers=suspicious_numbers,
            message=message,
        )

    def check_source_attribution(self, insights: str) -> HallucinationCheckResult:
        """Verify that every sentence making a quantitative claim includes attribution or year reference.

        Acceptance Criteria:
        - Verifies all quantitative claims include "according to" / "based on" / year reference
        - Heuristic: sentences with numbers should have attribution
        - Reports: {passed: bool, unattributed_claims: list[str]}

        Args:
            insights: Narrative insight text.

        Returns:
            HallucinationCheckResult detailing attribution compliance.
        """
        if not insights or not insights.strip():
            return HallucinationCheckResult(
                passed=True,
                unattributed_claims=[],
                message="Insight text is empty; no unattributed claims found.",
            )

        # Split into sentences on sentence terminators (. ! ?) or paragraph breaks
        raw_sentences = re.split(r"(?<=[.!?])\s+|\n+", insights.strip())
        unattributed_claims: list[str] = []
        year_pattern = r"\b(19|20)\d{2}\b"

        for sent in raw_sentences:
            s = sent.strip()
            if not s:
                continue

            # Strip leading list numbers (e.g. "1. ", "2) ")
            cleaned = re.sub(r"^\s*\(?\d+[\.\)]\s*", "", s)

            has_percentage = bool(re.search(r"\b\d+\.?\d*\s*%", cleaned))
            has_number = bool(re.search(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b", cleaned))

            if not (has_percentage or has_number):
                continue

            # Check attribution phrases
            lower_s = s.lower()
            has_attribution = any(phrase in lower_s for phrase in self.ATTRIBUTION_PHRASES)
            has_year = bool(re.search(year_pattern, s))

            if not (has_attribution or has_year):
                unattributed_claims.append(s)

        passed = len(unattributed_claims) == 0
        message = (
            "All quantitative claims have source attribution or temporal grounding."
            if passed
            else f"Detected {len(unattributed_claims)} unattributed quantitative claim(s)."
        )
        return HallucinationCheckResult(
            passed=passed,
            unattributed_claims=unattributed_claims,
            message=message,
        )

    def run_all_checks(
        self,
        insights: str,
        datasets: list[dict[str, Any]] | list[Any],
        stats: dict[str, Any] | Any,
    ) -> dict[str, Any]:
        """Execute full hallucination audit suite and produce structured summary dictionary.

        Args:
            insights: LLM-generated narrative insight.
            datasets: List of dataset metadata objects or dictionaries.
            stats: Computed statistics dictionary or StatsResult instance.

        Returns:
            Composite verification report suitable for saving in Analysis.metadata.
        """
        citation_res = self.check_citation_grounding(insights, datasets)
        numeric_res = self.check_numeric_consistency(insights, stats)
        attribution_res = self.check_source_attribution(insights)

        all_passed = citation_res.passed and numeric_res.passed and attribution_res.passed

        return {
            "passed": all_passed,
            "citation_grounding": citation_res.to_dict(),
            "numeric_consistency": numeric_res.to_dict(),
            "source_attribution": attribution_res.to_dict(),
            "ungrounded_citations": citation_res.ungrounded_citations,
            "suspicious_numbers": numeric_res.suspicious_numbers,
            "unattributed_claims": attribution_res.unattributed_claims,
        }

    # Internal helper methods

    @classmethod
    def _extract_numbers_from_stats(cls, obj: Any) -> set[float]:
        """Recursively extract all numeric values and numeric keys from a statistics object."""
        nums: set[float] = set()
        if isinstance(obj, (int, float)) and not isinstance(obj, bool):
            nums.add(float(obj))
        elif isinstance(obj, str):
            clean = obj.replace(",", "").rstrip("%").strip()
            with contextlib.suppress(ValueError):
                nums.add(float(clean))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                clean_k = str(k).replace(",", "").rstrip("%").strip()
                with contextlib.suppress(ValueError):
                    nums.add(float(clean_k))
                nums.update(cls._extract_numbers_from_stats(v))
        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                nums.update(cls._extract_numbers_from_stats(item))
        elif hasattr(obj, "model_dump"):
            nums.update(cls._extract_numbers_from_stats(obj.model_dump()))
        elif hasattr(obj, "__dict__"):
            nums.update(cls._extract_numbers_from_stats(obj.__dict__))
        return nums

    @classmethod
    def _extract_calendar_years(cls, stats: Any) -> set[int]:
        """Extract all 4-digit calendar years associated with stats periods or keys."""
        years: set[int] = set()
        nums = cls._extract_numbers_from_stats(stats)
        for n in nums:
            if 1900 <= n <= 2099 and n.is_integer():
                years.add(int(n))

        # Check metadata strings for year ranges like "2019-2024"
        def scan_strings(data: Any) -> None:
            if isinstance(data, str):
                for match in re.finditer(r"\b(19|20)\d{2}\b", data):
                    years.add(int(match.group(0)))
            elif isinstance(data, dict):
                for val in data.values():
                    scan_strings(val)
            elif isinstance(data, (list, tuple)):
                for item in data:
                    scan_strings(item)
            elif hasattr(data, "model_dump"):
                scan_strings(data.model_dump())

        scan_strings(stats)
        return years
