"""Mock LLM provider implementation for local development and offline testing."""

import asyncio
import json
import re
import logging
import time
from typing import Any

from app.llm.base import AbstractLLMProvider, LLMResponse, validate_messages

logger = logging.getLogger(__name__)


# Deterministic canned response datasets for domain queries
MOCK_KNOWLEDGE_BASE: dict[str, dict[str, Any]] = {
    "foreign_workforce": {
        "text": (
            "Singapore's foreign workforce policy maintains a calibrated approach across Employment Pass (EP), "
            "S Pass, and Work Permit categories. The COMPASS evaluation framework ensures high complementarity "
            "and diversity, while tiered foreign worker levies balance resident workforce protection with industry "
            "manpower demands."
        ),
        "json": {
            "topic": "foreign_workforce",
            "ep_holders": 197000,
            "s_pass_holders": 178000,
            "work_permit_holders": 860000,
            "policy_framework": "COMPASS points-based evaluation and tiered sectoral levies",
            "key_finding": "Calibrated foreign workforce controls maintain resident wage growth while meeting specialist labor needs.",
            "status": "success",
        },
    },
    "employment": {
        "text": (
            "Based on official statistics from SingStat and the Ministry of Manpower, Singapore's resident employment "
            "rate registered steady performance, standing at 67.2% with overall unemployment holding low at 1.9%. "
            "Employment gains remain concentrated in high-value sectors including financial services, information & "
            "communications, and professional services, supported by proactive tripartite career transition programs. "
            "From a macroeconomic and policy perspective, continuous workforce upskilling and the expansion of the "
            "Progressive Wage Model have underpinned resident income resilience across all percentiles. Sectoral headcounts "
            "demonstrate sustained labor demand in critical technical specialties, while calibrated foreign manpower policies "
            "ensure local career advancement alongside access to global talent. Policymakers should continue monitoring labor "
            "market tightness and sectoral productivity to sustain inclusive real wage growth across future economic cycles."
        ),
        "json": {
            "topic": "employment",
            "resident_employment_rate": 67.2,
            "overall_unemployment_rate": 1.9,
            "resident_unemployment_rate": 2.7,
            "key_finding": "Labor market conditions remain resilient with tight resident employment across high-value services.",
            "status": "success",
        },
    },
    "policy_recommendations": {
        "text": (
            "Key policy recommendations: 1. Enhance SkillsFuture Enterprise Credits for mid-career AI capability adoption. "
            "2. Institutionalize Tripartite Guidelines on Flexible Work Arrangement Requests. "
            "3. Progressively expand Progressive Wage Model (PWM) standards to emerging green and technical roles."
        ),
        "json": {
            "topic": "policy_recommendations",
            "recommendations": [
                "Expand SkillsFuture mid-career subsidies for AI and digital capabilities.",
                "Implement Tripartite Guidelines on Flexible Work Arrangement Requests.",
                "Extend Progressive Wage Model (PWM) coverage to technical sustainability occupations.",
            ],
            "impact_assessment": "High anticipated productivity enhancement and inclusive resident wage progression.",
            "status": "success",
        },
    },
    "gdp": {
        "text": (
            "Singapore's Gross Domestic Product (GDP) grew by 3.6% year-on-year, led by strong expansion in the "
            "manufacturing cluster (notably electronics and precision engineering) and sustained wholesale trade volume."
        ),
        "json": {
            "topic": "gdp",
            "gdp_growth_rate": 3.6,
            "nominal_gdp_bil_sgd": 673.3,
            "leading_sectors": [
                "Manufacturing (Electronics)",
                "Wholesale Trade",
                "Finance & Insurance",
            ],
            "status": "success",
        },
    },
    "inflation": {
        "text": (
            "Headline Consumer Price Index (CPI) inflation eased to 2.4% year-on-year, while MAS Core Inflation "
            "moderated to 2.7%. The prevailing appreciating S$NEER monetary policy band continues to buffer against "
            "imported inflation and anchor medium-term price stability."
        ),
        "json": {
            "topic": "inflation",
            "headline_cpi": 2.4,
            "core_inflation": 2.7,
            "mas_policy_stance": "Appreciating S$NEER band maintained to anchor medium-term price stability.",
            "status": "success",
        },
    },
    "population_demographics": {
        "text": (
            "Singapore's total population reached 6.04 million in 2024, representing a 2.0% increase primarily "
            "from non-resident workforce normalization. However, the resident Total Fertility Rate (TFR) registered "
            "an unprecedented historical low of 0.97 births per female, down from 1.14 in 2018. Marriages stabilized "
            "at ~28,300 annual unions, while citizen life expectancy at birth remains world-leading at 83.0 years. "
            "Policy measures include enhanced baby bonuses, extended parental leave, and housing prioritization for "
            "young families to mitigate long-term demographic contraction."
        ),
        "json": {
            "topic": "population_demographics",
            "total_population_mil": 6.04,
            "total_fertility_rate": 0.97,
            "life_expectancy_years": 83.0,
            "annual_marriages": 28310,
            "status": "success",
        },
    },
    "gdp_6yr": {
        "text": (
            "Across the 2018–2024 period, Singapore's real GDP experienced significant cyclical fluctuations, reflecting "
            "external vulnerability and subsequent resilient recovery. Following pre-COVID growth of 3.5% (2018) and "
            "1.3% (2019), the economy contracted by -3.9% in 2020 during the pandemic circuit-breaker. Singapore "
            "rebounded vigorously with +8.9% in 2021, moderated to +3.8% in 2022 and +1.1% in 2023 amid global tightening, "
            "before accelerating to +3.6% in 2024. Over the 6-year period, compound annual real growth averaged +2.6%, "
            "anchored by advanced manufacturing and financial services."
        ),
        "json": {
            "topic": "gdp_6yr",
            "growth_2018": 3.5,
            "growth_2019": 1.3,
            "growth_2020": -3.9,
            "growth_2021": 8.9,
            "growth_2022": 3.8,
            "growth_2023": 1.1,
            "growth_2024": 3.6,
            "cagr_pct": 2.6,
            "status": "success",
        },
    },
    "industry_gdp": {
        "text": (
            "Singapore's GDP composition is anchored by high-value manufacturing and modern services. In 2024, "
            "Manufacturing contributed 21.6% of nominal GDP, driven by biomedical engineering and the semiconductor upswing. "
            "Wholesale & Retail Trade represented 18.4%, while Finance & Insurance accounted for 14.2%. Information & "
            "Communications (ICT) was the fastest expanding cluster (+7.6% annualized), now comprising 5.8% of GDP as "
            "enterprise cloud and AI investments accelerated."
        ),
        "json": {
            "topic": "industry_gdp",
            "manufacturing_share_pct": 21.6,
            "wholesale_trade_share_pct": 18.4,
            "finance_share_pct": 14.2,
            "transportation_share_pct": 7.1,
            "ict_share_pct": 5.8,
            "status": "success",
        },
    },
    "trade_investments": {
        "text": (
            "Singapore maintains an open external trade architecture with total merchandise trade surpassing S$1.28 trillion "
            "in 2024 (+6.6% YoY). Non-Oil Domestic Exports (NODX) expanded by +4.2% YoY, rebounding from a cyclical contraction "
            "of -13.1% in 2023, bolstered by electronics shipments to China and the United States. Foreign Direct Investment "
            "(FDI) inflows remained robust with S$12.7 billion in fixed asset commitments secured by the Economic Development Board (EDB)."
        ),
        "json": {
            "topic": "trade_investments",
            "total_trade_bil_sgd": 1285.3,
            "nodx_growth_pct": 4.2,
            "fdi_commitments_bil_sgd": 12.7,
            "status": "success",
        },
    },
    "household_income": {
        "text": (
            "Singapore's median monthly household income from work among resident employed households reached S$10,869 "
            "in 2023 (up from S$9,520 in 2021 and S$10,099 in 2022). Accounting for inflation, real median household income "
            "rose by 2.8% in 2023. The Gini coefficient before government transfers was 0.433, which declined to an all-time low "
            "of 0.371 after incorporating permanent redistribution and progressive taxes."
        ),
        "json": {
            "topic": "household_income",
            "median_income_2021": 9520,
            "median_income_2022": 10099,
            "median_income_2023": 10869,
            "real_growth_pct": 2.8,
            "gini_before_transfers": 0.433,
            "gini_after_transfers": 0.371,
            "status": "success",
        },
    },
    "aging_demographics": {
        "text": (
            "Singapore's demographic aging accelerated sharply between 2018 and 2024. The proportion of resident citizens "
            "and PRs aged 65 and above increased from 14.4% in 2018 to 19.9% in 2024 (~831,000 seniors). Concurrently, "
            "the youth cohort (aged 0–14) contracted from 15.3% to 13.5%. The old-age dependency ratio rose from 20.1 to 29.8 "
            "elderly per 100 working-age adults (aged 20–64), underscoring critical requirements for healthcare expansion "
            "and progressive CPF retirement adequacy."
        ),
        "json": {
            "topic": "aging_demographics",
            "elderly_proportion_2018": 14.4,
            "elderly_proportion_2024": 19.9,
            "youth_proportion_2024": 13.5,
            "dependency_ratio_2018": 20.1,
            "dependency_ratio_2024": 29.8,
            "status": "success",
        },
    },
    "default": {
        "text": (
            "Policy data analytics evaluation completed. Synthesized findings indicate stable macroeconomic indicators "
            "and positive structural transformation aligned with national strategic priorities."
        ),
        "json": {
            "topic": "general_policy_analytics",
            "summary": "Deterministic mock analysis completed successfully with standard domain parameters.",
            "status": "success",
        },
    },
}


class MockLLMProvider(AbstractLLMProvider):
    """Deterministic Mock LLM Provider for offline development and testing.

    Features:
        - Keyword-based routing to deterministic domain answers
        - Configurable mock latency for async timeout/concurrency testing
        - Strict JSON mode compliance with structured data payloads
        - Token estimation and zero external network calls
    """

    def __init__(
        self,
        model: str = "mock-model",
        mock_latency_ms: float = 0.0,
        custom_responses: dict[str, str | dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the MockLLMProvider.

        Args:
            model: Name/id of the mock model.
            mock_latency_ms: Milliseconds of delay to simulate on each complete() call.
            custom_responses: Optional dictionary mapping keywords to custom response strings or dicts.
        """
        self.model = model
        self.provider_name = "mock"
        self.provider = "mock"
        self.mock_latency_ms = max(0.0, float(mock_latency_ms))
        self.custom_responses = custom_responses or {}

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a deterministic completion based on keywords in messages.

        Args:
            messages: List of message dicts: [{"role": "system"|"user"|"assistant", "content": str}]
            temperature: Sampling temperature (ignored by mock)
            max_tokens: Maximum tokens in generated completion
            json_mode: If True, return valid JSON string payload
            **kwargs: Ignored mock parameters

        Returns:
            LLMResponse: Structured response model.
        """
        validate_messages(messages)
        # Unused mock parameters explicitly acknowledged
        _ = (temperature, max_tokens, kwargs)
        start_time = time.perf_counter()

        # Simulate latency if configured
        if self.mock_latency_ms > 0:
            await asyncio.sleep(self.mock_latency_ms / 1000.0)

        # Concatenate message texts for keyword discovery
        full_query_text = " ".join(str(m.get("content", "")) for m in messages).lower()

        # Determine matched topic
        topic_data = self._route_keyword(full_query_text)

        # Generate response content
        if json_mode:
            content = json.dumps(topic_data["json"], indent=2)
        elif "**key findings**" in full_query_text:
            content = self._to_bullet_insight(topic_data["text"])
        else:
            content = topic_data["text"]

        # Calculate token counts
        input_word_count = sum(len(str(m.get("content", "")).split()) for m in messages)
        input_tokens = max(10, input_word_count * 2)
        output_tokens = max(1, len(content.split()) * 2)
        total_tokens = input_tokens + output_tokens

        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        reported_latency = max(self.mock_latency_ms, elapsed_ms)

        logger.debug(
            "MockLLMProvider completion: model=%s latency_ms=%.2f tokens=%d json_mode=%s",
            self.model,
            reported_latency,
            total_tokens,
            json_mode,
        )

        return LLMResponse(
            content=content,
            model=self.model,
            provider="mock",
            usage=usage,
            latency_ms=round(reported_latency, 2),
        )

    @staticmethod
    def _to_bullet_insight(text: str) -> str:
        """Reshape a canned paragraph into the bullet-point insight format."""
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if len(sentences) < 3:
            return text
        findings, implications = sentences[1:-2] or sentences[1:2], sentences[-2:]
        return "\n".join(
            [f"**Answer:** {sentences[0]}", "", "**Key Findings**"]
            + [f"- {s}" for s in findings[:4]]
            + ["", "**Policy Implications**"]
            + [f"- {s}" for s in implications]
        )

    async def health_check(self) -> bool:
        """Check provider operational status.

        Returns:
            bool: Always True for MockLLMProvider.
        """
        return True

    def _route_keyword(self, text: str) -> dict[str, Any]:
        """Find the matching canned response based on message text."""
        # 1. Custom responses check
        for key, val in self.custom_responses.items():
            if key.lower() in text:
                if isinstance(val, dict):
                    return {"text": json.dumps(val), "json": val}
                return {"text": str(val), "json": {"response": str(val), "keyword": key}}

        # 2. Priority keyword checks
        if any(
            kw in text for kw in ("policy recommendation", "recommendation", "policy intervention")
        ):
            return MOCK_KNOWLEDGE_BASE["policy_recommendations"]
        if any(
            kw in text
            for kw in (
                "foreign workforce",
                "work permit",
                "s pass",
                "employment pass",
                "compass framework",
            )
        ):
            return MOCK_KNOWLEDGE_BASE["foreign_workforce"]
        if any(
            kw in text
            for kw in ("employment", "unemployment", "job vacancy", "labor market", "workforce")
        ):
            return MOCK_KNOWLEDGE_BASE["employment"]
        if any(
            kw in text
            for kw in (
                "population",
                "fertility",
                "marriage",
                "life expectancy",
                "tfr",
                "demographic",
            )
        ):
            return MOCK_KNOWLEDGE_BASE["population_demographics"]
        if any(
            kw in text
            for kw in (
                "aged people vs youth",
                "elderly",
                "dependency ratio",
                "aging",
                "youth growth",
                "seniors",
            )
        ):
            return MOCK_KNOWLEDGE_BASE["aging_demographics"]
        if any(
            kw in text
            for kw in (
                "household income",
                "income of last 3 years",
                "gini",
                "median monthly household income",
            )
        ):
            return MOCK_KNOWLEDGE_BASE["household_income"]
        if any(
            kw in text
            for kw in (
                "trade and investments",
                "nodx",
                "non-oil domestic exports",
                "foreign direct investment",
                "fdi",
                "external trade",
            )
        ):
            return MOCK_KNOWLEDGE_BASE["trade_investments"]
        if any(
            kw in text
            for kw in (
                "various industries",
                "gdp growth by",
                "industry sectors",
                "manufacturing",
                "sectoral",
            )
        ):
            return MOCK_KNOWLEDGE_BASE["industry_gdp"]
        if any(
            kw in text
            for kw in ("last 6 years", "6 years gdp", "gdp trajectory")
        ):
            return MOCK_KNOWLEDGE_BASE["gdp_6yr"]
        if any(kw in text for kw in ("gdp", "economic growth", "gross domestic product")):
            return MOCK_KNOWLEDGE_BASE["gdp"]
        if any(kw in text for kw in ("inflation", "cpi", "consumer price index", "price index")):
            return MOCK_KNOWLEDGE_BASE["inflation"]

        # 3. Fallback default
        return MOCK_KNOWLEDGE_BASE["default"]
