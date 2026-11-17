"""Mock internal database data source connector for testing and offline development.

Provides pre-loaded, realistic Singapore employment and economic statistics
modeled after official Ministry of Manpower (MOM), SingStat, and ACRA benchmarks
covering 2019–2024 (including COVID dip and recovery trajectories).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from app.data_sources.base import AbstractDataSource

logger = logging.getLogger(__name__)


# ==============================================================================
# Pre-loaded Dataset Records (Inline Python Data)
# ==============================================================================

# 1. Employment by Sector (Annual 2019–2024, 11 sectors, headcount in thousands)
_EMPLOYMENT_BY_SECTOR_DATA: list[dict[str, Any]] = [
    # 2019
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "sector": "Manufacturing",
        "employment_count": 471.2,
        "yoy_change_pct": -0.8,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "sector": "Construction",
        "employment_count": 475.1,
        "yoy_change_pct": 2.1,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "sector": "Wholesale & Retail Trade",
        "employment_count": 492.3,
        "yoy_change_pct": 0.4,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "sector": "Transportation & Storage",
        "employment_count": 254.8,
        "yoy_change_pct": 1.5,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "sector": "Accommodation & Food Services",
        "employment_count": 260.4,
        "yoy_change_pct": 1.2,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "sector": "Information & Communications",
        "employment_count": 118.5,
        "yoy_change_pct": 5.4,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "sector": "Financial & Insurance Services",
        "employment_count": 215.7,
        "yoy_change_pct": 2.9,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "sector": "Real Estate Services",
        "employment_count": 77.4,
        "yoy_change_pct": 1.0,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "sector": "Professional Services",
        "employment_count": 285.6,
        "yoy_change_pct": 3.2,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "sector": "Administrative & Support Services",
        "employment_count": 226.3,
        "yoy_change_pct": 1.8,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "sector": "Community, Social & Personal Services",
        "employment_count": 512.4,
        "yoy_change_pct": 2.6,
    },
    # 2020 (COVID dip, contraction in tourism/construction, tech/healthcare resilience)
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "sector": "Manufacturing",
        "employment_count": 449.8,
        "yoy_change_pct": -4.54,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "sector": "Construction",
        "employment_count": 412.3,
        "yoy_change_pct": -13.22,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "sector": "Wholesale & Retail Trade",
        "employment_count": 470.5,
        "yoy_change_pct": -4.43,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "sector": "Transportation & Storage",
        "employment_count": 236.2,
        "yoy_change_pct": -7.30,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "sector": "Accommodation & Food Services",
        "employment_count": 228.1,
        "yoy_change_pct": -12.40,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "sector": "Information & Communications",
        "employment_count": 124.7,
        "yoy_change_pct": 5.23,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "sector": "Financial & Insurance Services",
        "employment_count": 218.4,
        "yoy_change_pct": 1.25,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "sector": "Real Estate Services",
        "employment_count": 75.1,
        "yoy_change_pct": -2.97,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "sector": "Professional Services",
        "employment_count": 282.3,
        "yoy_change_pct": -1.16,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "sector": "Administrative & Support Services",
        "employment_count": 210.8,
        "yoy_change_pct": -6.85,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "sector": "Community, Social & Personal Services",
        "employment_count": 516.2,
        "yoy_change_pct": 0.74,
    },
    # 2021 (Stabilization and digital expansion)
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "sector": "Manufacturing",
        "employment_count": 446.5,
        "yoy_change_pct": -0.73,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "sector": "Construction",
        "employment_count": 408.0,
        "yoy_change_pct": -1.04,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "sector": "Wholesale & Retail Trade",
        "employment_count": 465.1,
        "yoy_change_pct": -1.15,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "sector": "Transportation & Storage",
        "employment_count": 238.9,
        "yoy_change_pct": 1.14,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "sector": "Accommodation & Food Services",
        "employment_count": 226.5,
        "yoy_change_pct": -0.70,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "sector": "Information & Communications",
        "employment_count": 134.2,
        "yoy_change_pct": 7.62,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "sector": "Financial & Insurance Services",
        "employment_count": 224.9,
        "yoy_change_pct": 2.98,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "sector": "Real Estate Services",
        "employment_count": 76.8,
        "yoy_change_pct": 2.26,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "sector": "Professional Services",
        "employment_count": 290.4,
        "yoy_change_pct": 2.87,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "sector": "Administrative & Support Services",
        "employment_count": 212.1,
        "yoy_change_pct": 0.62,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "sector": "Community, Social & Personal Services",
        "employment_count": 524.8,
        "yoy_change_pct": 1.67,
    },
    # 2022 (Strong post-COVID reopening recovery)
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "sector": "Manufacturing",
        "employment_count": 462.1,
        "yoy_change_pct": 3.49,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "sector": "Construction",
        "employment_count": 445.6,
        "yoy_change_pct": 9.22,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "sector": "Wholesale & Retail Trade",
        "employment_count": 478.4,
        "yoy_change_pct": 2.86,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "sector": "Transportation & Storage",
        "employment_count": 247.5,
        "yoy_change_pct": 3.60,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "sector": "Accommodation & Food Services",
        "employment_count": 241.8,
        "yoy_change_pct": 6.75,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "sector": "Information & Communications",
        "employment_count": 144.6,
        "yoy_change_pct": 7.75,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "sector": "Financial & Insurance Services",
        "employment_count": 232.8,
        "yoy_change_pct": 3.51,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "sector": "Real Estate Services",
        "employment_count": 79.2,
        "yoy_change_pct": 3.12,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "sector": "Professional Services",
        "employment_count": 304.2,
        "yoy_change_pct": 4.75,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "sector": "Administrative & Support Services",
        "employment_count": 221.7,
        "yoy_change_pct": 4.53,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "sector": "Community, Social & Personal Services",
        "employment_count": 538.1,
        "yoy_change_pct": 2.53,
    },
    # 2023 (Moderate growth, high tech consolidation)
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "sector": "Manufacturing",
        "employment_count": 458.7,
        "yoy_change_pct": -0.74,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "sector": "Construction",
        "employment_count": 472.0,
        "yoy_change_pct": 5.92,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "sector": "Wholesale & Retail Trade",
        "employment_count": 483.2,
        "yoy_change_pct": 1.00,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "sector": "Transportation & Storage",
        "employment_count": 252.1,
        "yoy_change_pct": 1.86,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "sector": "Accommodation & Food Services",
        "employment_count": 248.9,
        "yoy_change_pct": 2.94,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "sector": "Information & Communications",
        "employment_count": 148.5,
        "yoy_change_pct": 2.70,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "sector": "Financial & Insurance Services",
        "employment_count": 238.1,
        "yoy_change_pct": 2.28,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "sector": "Real Estate Services",
        "employment_count": 80.5,
        "yoy_change_pct": 1.64,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "sector": "Professional Services",
        "employment_count": 312.0,
        "yoy_change_pct": 2.56,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "sector": "Administrative & Support Services",
        "employment_count": 225.4,
        "yoy_change_pct": 1.67,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "sector": "Community, Social & Personal Services",
        "employment_count": 549.3,
        "yoy_change_pct": 2.08,
    },
    # 2024 (Sustained baseline expansion)
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "sector": "Manufacturing",
        "employment_count": 461.3,
        "yoy_change_pct": 0.57,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "sector": "Construction",
        "employment_count": 480.5,
        "yoy_change_pct": 1.80,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "sector": "Wholesale & Retail Trade",
        "employment_count": 487.6,
        "yoy_change_pct": 0.91,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "sector": "Transportation & Storage",
        "employment_count": 256.4,
        "yoy_change_pct": 1.71,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "sector": "Accommodation & Food Services",
        "employment_count": 252.3,
        "yoy_change_pct": 1.37,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "sector": "Information & Communications",
        "employment_count": 153.2,
        "yoy_change_pct": 3.16,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "sector": "Financial & Insurance Services",
        "employment_count": 243.6,
        "yoy_change_pct": 2.31,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "sector": "Real Estate Services",
        "employment_count": 81.9,
        "yoy_change_pct": 1.74,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "sector": "Professional Services",
        "employment_count": 319.5,
        "yoy_change_pct": 2.40,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "sector": "Administrative & Support Services",
        "employment_count": 228.9,
        "yoy_change_pct": 1.55,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "sector": "Community, Social & Personal Services",
        "employment_count": 559.8,
        "yoy_change_pct": 1.91,
    },
    # 2025 (Advance Estimates & Economic Projections)
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "sector": "Manufacturing",
        "employment_count": 465.8,
        "yoy_change_pct": 0.98,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "sector": "Construction",
        "employment_count": 488.2,
        "yoy_change_pct": 1.60,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "sector": "Wholesale & Retail Trade",
        "employment_count": 492.0,
        "yoy_change_pct": 0.90,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "sector": "Transportation & Storage",
        "employment_count": 261.2,
        "yoy_change_pct": 1.87,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "sector": "Accommodation & Food Services",
        "employment_count": 256.1,
        "yoy_change_pct": 1.51,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "sector": "Information & Communications",
        "employment_count": 161.5,
        "yoy_change_pct": 5.42,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "sector": "Financial & Insurance Services",
        "employment_count": 251.4,
        "yoy_change_pct": 3.20,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "sector": "Real Estate Services",
        "employment_count": 83.4,
        "yoy_change_pct": 1.83,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "sector": "Professional Services",
        "employment_count": 328.7,
        "yoy_change_pct": 2.88,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "sector": "Administrative & Support Services",
        "employment_count": 232.5,
        "yoy_change_pct": 1.57,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "sector": "Community, Social & Personal Services",
        "employment_count": 571.2,
        "yoy_change_pct": 2.04,
    },
    # 2026
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "sector": "Manufacturing",
        "employment_count": 468.5,
        "yoy_change_pct": 0.58,
    },
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "sector": "Construction",
        "employment_count": 494.0,
        "yoy_change_pct": 1.19,
    },
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "sector": "Wholesale & Retail Trade",
        "employment_count": 495.2,
        "yoy_change_pct": 0.65,
    },
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "sector": "Transportation & Storage",
        "employment_count": 265.8,
        "yoy_change_pct": 1.76,
    },
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "sector": "Accommodation & Food Services",
        "employment_count": 259.4,
        "yoy_change_pct": 1.29,
    },
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "sector": "Information & Communications",
        "employment_count": 170.8,
        "yoy_change_pct": 5.76,
    },
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "sector": "Financial & Insurance Services",
        "employment_count": 259.5,
        "yoy_change_pct": 3.22,
    },
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "sector": "Real Estate Services",
        "employment_count": 84.8,
        "yoy_change_pct": 1.68,
    },
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "sector": "Professional Services",
        "employment_count": 338.2,
        "yoy_change_pct": 2.89,
    },
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "sector": "Administrative & Support Services",
        "employment_count": 235.6,
        "yoy_change_pct": 1.33,
    },
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "sector": "Community, Social & Personal Services",
        "employment_count": 582.4,
        "yoy_change_pct": 1.96,
    },
]

# 2. ICT Workforce Trends (Annual 2019–2024)
_ICT_WORKFORCE_TRENDS_DATA: list[dict[str, Any]] = [
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "ict_headcount": 185.2,
        "total_workforce": 3680.5,
        "pct_of_workforce": 5.03,
        "yoy_growth": 4.80,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "ict_headcount": 194.8,
        "total_workforce": 3524.4,
        "pct_of_workforce": 5.53,
        "yoy_growth": 5.18,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "ict_headcount": 209.6,
        "total_workforce": 3598.2,
        "pct_of_workforce": 5.83,
        "yoy_growth": 7.60,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "ict_headcount": 224.5,
        "total_workforce": 3716.4,
        "pct_of_workforce": 6.04,
        "yoy_growth": 7.11,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "ict_headcount": 232.8,
        "total_workforce": 3788.7,
        "pct_of_workforce": 6.14,
        "yoy_growth": 3.70,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "ict_headcount": 241.6,
        "total_workforce": 3848.3,
        "pct_of_workforce": 6.28,
        "yoy_growth": 3.78,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "ict_headcount": 254.2,
        "total_workforce": 3915.0,
        "pct_of_workforce": 6.49,
        "yoy_growth": 5.21,
    },
    {
        "year": 2026,
        "period_start": "2026-01-01",
        "ict_headcount": 267.5,
        "total_workforce": 3980.2,
        "pct_of_workforce": 6.72,
        "yoy_growth": 5.23,
    },
]

# 3. Unemployment Rate Quarterly (2019–2024, 24 quarters)
_UNEMPLOYMENT_RATE_QUARTERLY_DATA: list[dict[str, Any]] = [
    {
        "quarter": "2019-Q1",
        "year": 2019,
        "period_start": "2019-01-01",
        "period_end": "2019-03-31",
        "overall_rate": 2.2,
        "resident_rate": 3.0,
        "citizen_rate": 3.2,
        "youth_rate": 6.4,
    },
    {
        "quarter": "2019-Q2",
        "year": 2019,
        "period_start": "2019-04-01",
        "period_end": "2019-06-30",
        "overall_rate": 2.3,
        "resident_rate": 3.1,
        "citizen_rate": 3.3,
        "youth_rate": 6.5,
    },
    {
        "quarter": "2019-Q3",
        "year": 2019,
        "period_start": "2019-07-01",
        "period_end": "2019-09-30",
        "overall_rate": 2.3,
        "resident_rate": 3.2,
        "citizen_rate": 3.3,
        "youth_rate": 6.7,
    },
    {
        "quarter": "2019-Q4",
        "year": 2019,
        "period_start": "2019-10-01",
        "period_end": "2019-12-31",
        "overall_rate": 2.3,
        "resident_rate": 3.2,
        "citizen_rate": 3.3,
        "youth_rate": 6.6,
    },
    {
        "quarter": "2020-Q1",
        "year": 2020,
        "period_start": "2020-01-01",
        "period_end": "2020-03-31",
        "overall_rate": 2.5,
        "resident_rate": 3.3,
        "citizen_rate": 3.5,
        "youth_rate": 7.2,
    },
    {
        "quarter": "2020-Q2",
        "year": 2020,
        "period_start": "2020-04-01",
        "period_end": "2020-06-30",
        "overall_rate": 2.8,
        "resident_rate": 3.8,
        "citizen_rate": 4.0,
        "youth_rate": 8.9,
    },
    {
        "quarter": "2020-Q3",
        "year": 2020,
        "period_start": "2020-07-01",
        "period_end": "2020-09-30",
        "overall_rate": 3.5,
        "resident_rate": 4.8,
        "citizen_rate": 4.9,
        "youth_rate": 10.6,
    },
    {
        "quarter": "2020-Q4",
        "year": 2020,
        "period_start": "2020-10-01",
        "period_end": "2020-12-31",
        "overall_rate": 3.3,
        "resident_rate": 4.4,
        "citizen_rate": 4.5,
        "youth_rate": 9.4,
    },
    {
        "quarter": "2021-Q1",
        "year": 2021,
        "period_start": "2021-01-01",
        "period_end": "2021-03-31",
        "overall_rate": 3.1,
        "resident_rate": 4.0,
        "citizen_rate": 4.1,
        "youth_rate": 8.5,
    },
    {
        "quarter": "2021-Q2",
        "year": 2021,
        "period_start": "2021-04-01",
        "period_end": "2021-06-30",
        "overall_rate": 2.7,
        "resident_rate": 3.5,
        "citizen_rate": 3.7,
        "youth_rate": 7.8,
    },
    {
        "quarter": "2021-Q3",
        "year": 2021,
        "period_start": "2021-07-01",
        "period_end": "2021-09-30",
        "overall_rate": 2.6,
        "resident_rate": 3.4,
        "citizen_rate": 3.5,
        "youth_rate": 7.5,
    },
    {
        "quarter": "2021-Q4",
        "year": 2021,
        "period_start": "2021-10-01",
        "period_end": "2021-12-31",
        "overall_rate": 2.3,
        "resident_rate": 3.1,
        "citizen_rate": 3.2,
        "youth_rate": 6.9,
    },
    {
        "quarter": "2022-Q1",
        "year": 2022,
        "period_start": "2022-01-01",
        "period_end": "2022-03-31",
        "overall_rate": 2.2,
        "resident_rate": 3.0,
        "citizen_rate": 3.1,
        "youth_rate": 6.4,
    },
    {
        "quarter": "2022-Q2",
        "year": 2022,
        "period_start": "2022-04-01",
        "period_end": "2022-06-30",
        "overall_rate": 2.1,
        "resident_rate": 2.9,
        "citizen_rate": 3.0,
        "youth_rate": 6.2,
    },
    {
        "quarter": "2022-Q3",
        "year": 2022,
        "period_start": "2022-07-01",
        "period_end": "2022-09-30",
        "overall_rate": 2.0,
        "resident_rate": 2.8,
        "citizen_rate": 2.9,
        "youth_rate": 6.1,
    },
    {
        "quarter": "2022-Q4",
        "year": 2022,
        "period_start": "2022-10-01",
        "period_end": "2022-12-31",
        "overall_rate": 2.0,
        "resident_rate": 2.8,
        "citizen_rate": 2.9,
        "youth_rate": 5.9,
    },
    {
        "quarter": "2023-Q1",
        "year": 2023,
        "period_start": "2023-01-01",
        "period_end": "2023-03-31",
        "overall_rate": 1.9,
        "resident_rate": 2.6,
        "citizen_rate": 2.7,
        "youth_rate": 5.7,
    },
    {
        "quarter": "2023-Q2",
        "year": 2023,
        "period_start": "2023-04-01",
        "period_end": "2023-06-30",
        "overall_rate": 1.9,
        "resident_rate": 2.7,
        "citizen_rate": 2.8,
        "youth_rate": 5.8,
    },
    {
        "quarter": "2023-Q3",
        "year": 2023,
        "period_start": "2023-07-01",
        "period_end": "2023-09-30",
        "overall_rate": 2.0,
        "resident_rate": 2.8,
        "citizen_rate": 2.9,
        "youth_rate": 6.0,
    },
    {
        "quarter": "2023-Q4",
        "year": 2023,
        "period_start": "2023-10-01",
        "period_end": "2023-12-31",
        "overall_rate": 2.0,
        "resident_rate": 2.8,
        "citizen_rate": 2.9,
        "youth_rate": 5.9,
    },
    {
        "quarter": "2024-Q1",
        "year": 2024,
        "period_start": "2024-01-01",
        "period_end": "2024-03-31",
        "overall_rate": 2.1,
        "resident_rate": 2.9,
        "citizen_rate": 3.0,
        "youth_rate": 6.1,
    },
    {
        "quarter": "2024-Q2",
        "year": 2024,
        "period_start": "2024-04-01",
        "period_end": "2024-06-30",
        "overall_rate": 2.0,
        "resident_rate": 2.8,
        "citizen_rate": 2.9,
        "youth_rate": 5.9,
    },
    {
        "quarter": "2024-Q3",
        "year": 2024,
        "period_start": "2024-07-01",
        "period_end": "2024-09-30",
        "overall_rate": 1.9,
        "resident_rate": 2.7,
        "citizen_rate": 2.8,
        "youth_rate": 5.8,
    },
    {
        "quarter": "2024-Q4",
        "year": 2024,
        "period_start": "2024-10-01",
        "period_end": "2024-12-31",
        "overall_rate": 1.9,
        "resident_rate": 2.7,
        "citizen_rate": 2.8,
        "youth_rate": 5.7,
    },
]

# 4. Median Gross Wages by Occupation Group (Annual 2019–2024, SGD)
_MEDIAN_GROSS_WAGES_DATA: list[dict[str, Any]] = [
    # 2019
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "occupation_group": "PMETs",
        "median_monthly_wage_sgd": 6000,
        "yoy_growth": 3.80,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "occupation_group": "Clerical",
        "median_monthly_wage_sgd": 2800,
        "yoy_growth": 3.20,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "occupation_group": "Service/Sales",
        "median_monthly_wage_sgd": 2350,
        "yoy_growth": 3.50,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "occupation_group": "Production/Craft",
        "median_monthly_wage_sgd": 2600,
        "yoy_growth": 2.80,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "occupation_group": "Cleaners/Laborers",
        "median_monthly_wage_sgd": 1450,
        "yoy_growth": 4.50,
    },
    # 2020
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "occupation_group": "PMETs",
        "median_monthly_wage_sgd": 6000,
        "yoy_growth": 0.00,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "occupation_group": "Clerical",
        "median_monthly_wage_sgd": 2800,
        "yoy_growth": 0.00,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "occupation_group": "Service/Sales",
        "median_monthly_wage_sgd": 2300,
        "yoy_growth": -2.13,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "occupation_group": "Production/Craft",
        "median_monthly_wage_sgd": 2550,
        "yoy_growth": -1.92,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "occupation_group": "Cleaners/Laborers",
        "median_monthly_wage_sgd": 1480,
        "yoy_growth": 2.07,
    },
    # 2021
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "occupation_group": "PMETs",
        "median_monthly_wage_sgd": 6300,
        "yoy_growth": 5.00,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "occupation_group": "Clerical",
        "median_monthly_wage_sgd": 2920,
        "yoy_growth": 4.29,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "occupation_group": "Service/Sales",
        "median_monthly_wage_sgd": 2420,
        "yoy_growth": 5.22,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "occupation_group": "Production/Craft",
        "median_monthly_wage_sgd": 2680,
        "yoy_growth": 5.10,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "occupation_group": "Cleaners/Laborers",
        "median_monthly_wage_sgd": 1570,
        "yoy_growth": 6.08,
    },
    # 2022
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "occupation_group": "PMETs",
        "median_monthly_wage_sgd": 6700,
        "yoy_growth": 6.35,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "occupation_group": "Clerical",
        "median_monthly_wage_sgd": 3080,
        "yoy_growth": 5.48,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "occupation_group": "Service/Sales",
        "median_monthly_wage_sgd": 2580,
        "yoy_growth": 6.61,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "occupation_group": "Production/Craft",
        "median_monthly_wage_sgd": 2830,
        "yoy_growth": 5.60,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "occupation_group": "Cleaners/Laborers",
        "median_monthly_wage_sgd": 1710,
        "yoy_growth": 8.92,
    },
    # 2023
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "occupation_group": "PMETs",
        "median_monthly_wage_sgd": 7000,
        "yoy_growth": 4.48,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "occupation_group": "Clerical",
        "median_monthly_wage_sgd": 3220,
        "yoy_growth": 4.55,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "occupation_group": "Service/Sales",
        "median_monthly_wage_sgd": 2720,
        "yoy_growth": 5.43,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "occupation_group": "Production/Craft",
        "median_monthly_wage_sgd": 2970,
        "yoy_growth": 4.95,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "occupation_group": "Cleaners/Laborers",
        "median_monthly_wage_sgd": 1850,
        "yoy_growth": 8.19,
    },
    # 2024
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "occupation_group": "PMETs",
        "median_monthly_wage_sgd": 7350,
        "yoy_growth": 5.00,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "occupation_group": "Clerical",
        "median_monthly_wage_sgd": 3380,
        "yoy_growth": 4.97,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "occupation_group": "Service/Sales",
        "median_monthly_wage_sgd": 2850,
        "yoy_growth": 4.78,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "occupation_group": "Production/Craft",
        "median_monthly_wage_sgd": 3100,
        "yoy_growth": 4.38,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "occupation_group": "Cleaners/Laborers",
        "median_monthly_wage_sgd": 1980,
        "yoy_growth": 7.03,
    },
    # 2025 (Projected & Collective Bargaining Adjustments)
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "occupation_group": "PMETs",
        "median_monthly_wage_sgd": 7650,
        "yoy_growth": 4.08,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "occupation_group": "Clerical",
        "median_monthly_wage_sgd": 3520,
        "yoy_growth": 4.14,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "occupation_group": "Service/Sales",
        "median_monthly_wage_sgd": 2980,
        "yoy_growth": 4.56,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "occupation_group": "Production/Craft",
        "median_monthly_wage_sgd": 3240,
        "yoy_growth": 4.52,
    },
    {
        "year": 2025,
        "period_start": "2025-01-01",
        "occupation_group": "Cleaners/Laborers",
        "median_monthly_wage_sgd": 2100,
        "yoy_growth": 6.06,
    },
]

# 5. Business Registrations and Formations by Industry (Annual 2019–2024)
_BUSINESS_REGISTRATIONS_DATA: list[dict[str, Any]] = [
    # 2019
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "industry": "Information & Communications",
        "new_company_registrations": 5820,
        "business_cessations": 3940,
        "net_formation": 1880,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "industry": "Financial & Insurance Services",
        "new_company_registrations": 4210,
        "business_cessations": 2850,
        "net_formation": 1360,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "industry": "Wholesale & Retail Trade",
        "new_company_registrations": 12400,
        "business_cessations": 10200,
        "net_formation": 2200,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "industry": "Professional, Scientific & Technical",
        "new_company_registrations": 8350,
        "business_cessations": 6120,
        "net_formation": 2230,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "industry": "Manufacturing",
        "new_company_registrations": 3400,
        "business_cessations": 2950,
        "net_formation": 450,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "industry": "Accommodation & Food Services",
        "new_company_registrations": 3650,
        "business_cessations": 3200,
        "net_formation": 450,
    },
    {
        "year": 2019,
        "period_start": "2019-01-01",
        "industry": "Construction",
        "new_company_registrations": 3820,
        "business_cessations": 3150,
        "net_formation": 670,
    },
    # 2020
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "industry": "Information & Communications",
        "new_company_registrations": 6450,
        "business_cessations": 3620,
        "net_formation": 2830,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "industry": "Financial & Insurance Services",
        "new_company_registrations": 4340,
        "business_cessations": 2720,
        "net_formation": 1620,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "industry": "Wholesale & Retail Trade",
        "new_company_registrations": 11100,
        "business_cessations": 10800,
        "net_formation": 300,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "industry": "Professional, Scientific & Technical",
        "new_company_registrations": 8120,
        "business_cessations": 5950,
        "net_formation": 2170,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "industry": "Manufacturing",
        "new_company_registrations": 3150,
        "business_cessations": 3100,
        "net_formation": 50,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "industry": "Accommodation & Food Services",
        "new_company_registrations": 2850,
        "business_cessations": 3450,
        "net_formation": -600,
    },
    {
        "year": 2020,
        "period_start": "2020-01-01",
        "industry": "Construction",
        "new_company_registrations": 2980,
        "business_cessations": 3340,
        "net_formation": -360,
    },
    # 2021
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "industry": "Information & Communications",
        "new_company_registrations": 7180,
        "business_cessations": 3850,
        "net_formation": 3330,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "industry": "Financial & Insurance Services",
        "new_company_registrations": 4780,
        "business_cessations": 2940,
        "net_formation": 1840,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "industry": "Wholesale & Retail Trade",
        "new_company_registrations": 11900,
        "business_cessations": 10400,
        "net_formation": 1500,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "industry": "Professional, Scientific & Technical",
        "new_company_registrations": 8860,
        "business_cessations": 6210,
        "net_formation": 2650,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "industry": "Manufacturing",
        "new_company_registrations": 3380,
        "business_cessations": 2980,
        "net_formation": 400,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "industry": "Accommodation & Food Services",
        "new_company_registrations": 3120,
        "business_cessations": 3380,
        "net_formation": -260,
    },
    {
        "year": 2021,
        "period_start": "2021-01-01",
        "industry": "Construction",
        "new_company_registrations": 3250,
        "business_cessations": 3280,
        "net_formation": -30,
    },
    # 2022
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "industry": "Information & Communications",
        "new_company_registrations": 7420,
        "business_cessations": 4210,
        "net_formation": 3210,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "industry": "Financial & Insurance Services",
        "new_company_registrations": 4960,
        "business_cessations": 3120,
        "net_formation": 1840,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "industry": "Wholesale & Retail Trade",
        "new_company_registrations": 12800,
        "business_cessations": 10900,
        "net_formation": 1900,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "industry": "Professional, Scientific & Technical",
        "new_company_registrations": 9450,
        "business_cessations": 6680,
        "net_formation": 2770,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "industry": "Manufacturing",
        "new_company_registrations": 3520,
        "business_cessations": 3050,
        "net_formation": 470,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "industry": "Accommodation & Food Services",
        "new_company_registrations": 3590,
        "business_cessations": 3240,
        "net_formation": 350,
    },
    {
        "year": 2022,
        "period_start": "2022-01-01",
        "industry": "Construction",
        "new_company_registrations": 3740,
        "business_cessations": 3220,
        "net_formation": 520,
    },
    # 2023
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "industry": "Information & Communications",
        "new_company_registrations": 7150,
        "business_cessations": 4490,
        "net_formation": 2660,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "industry": "Financial & Insurance Services",
        "new_company_registrations": 4890,
        "business_cessations": 3250,
        "net_formation": 1640,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "industry": "Wholesale & Retail Trade",
        "new_company_registrations": 12600,
        "business_cessations": 11200,
        "net_formation": 1400,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "industry": "Professional, Scientific & Technical",
        "new_company_registrations": 9620,
        "business_cessations": 6940,
        "net_formation": 2680,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "industry": "Manufacturing",
        "new_company_registrations": 3460,
        "business_cessations": 3120,
        "net_formation": 340,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "industry": "Accommodation & Food Services",
        "new_company_registrations": 3720,
        "business_cessations": 3360,
        "net_formation": 360,
    },
    {
        "year": 2023,
        "period_start": "2023-01-01",
        "industry": "Construction",
        "new_company_registrations": 3920,
        "business_cessations": 3350,
        "net_formation": 570,
    },
    # 2024
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "industry": "Information & Communications",
        "new_company_registrations": 7380,
        "business_cessations": 4520,
        "net_formation": 2860,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "industry": "Financial & Insurance Services",
        "new_company_registrations": 5050,
        "business_cessations": 3310,
        "net_formation": 1740,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "industry": "Wholesale & Retail Trade",
        "new_company_registrations": 12950,
        "business_cessations": 11150,
        "net_formation": 1800,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "industry": "Professional, Scientific & Technical",
        "new_company_registrations": 9900,
        "business_cessations": 7050,
        "net_formation": 2850,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "industry": "Manufacturing",
        "new_company_registrations": 3580,
        "business_cessations": 3140,
        "net_formation": 440,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "industry": "Accommodation & Food Services",
        "new_company_registrations": 3810,
        "business_cessations": 3400,
        "net_formation": 410,
    },
    {
        "year": 2024,
        "period_start": "2024-01-01",
        "industry": "Construction",
        "new_company_registrations": 4050,
        "business_cessations": 3390,
        "net_formation": 660,
    },
]

# 6. Singapore Population Growth, Fertility, Marriage & Life Expectancy (2018–2024)
_POPULATION_GROWTH_DATA: list[dict[str, Any]] = [
    {"year": 2018, "period_start": "2018-01-01", "total_population_k": 5638.7, "resident_population_k": 3994.3, "total_fertility_rate": 1.14, "marriages": 27007, "life_expectancy_years": 83.2},
    {"year": 2019, "period_start": "2019-01-01", "total_population_k": 5703.6, "resident_population_k": 4026.2, "total_fertility_rate": 1.14, "marriages": 25434, "life_expectancy_years": 83.6},
    {"year": 2020, "period_start": "2020-01-01", "total_population_k": 5685.8, "resident_population_k": 4044.3, "total_fertility_rate": 1.10, "marriages": 22651, "life_expectancy_years": 83.7},
    {"year": 2021, "period_start": "2021-01-01", "total_population_k": 5453.6, "resident_population_k": 3986.8, "total_fertility_rate": 1.12, "marriages": 28329, "life_expectancy_years": 83.2},
    {"year": 2022, "period_start": "2022-01-01", "total_population_k": 5637.0, "resident_population_k": 4073.2, "total_fertility_rate": 1.04, "marriages": 29389, "life_expectancy_years": 83.0},
    {"year": 2023, "period_start": "2023-01-01", "total_population_k": 5917.6, "resident_population_k": 4150.1, "total_fertility_rate": 0.97, "marriages": 28310, "life_expectancy_years": 83.0},
    {"year": 2024, "period_start": "2024-01-01", "total_population_k": 6040.0, "resident_population_k": 4180.0, "total_fertility_rate": 0.97, "marriages": 28500, "life_expectancy_years": 83.1},
]

# 7. Singapore 6-Year Real GDP Growth Trajectory (2018–2024)
_GDP_GROWTH_6YR_DATA: list[dict[str, Any]] = [
    {"year": 2018, "period_start": "2018-01-01", "real_gdp_growth_pct": 3.5, "gdp_constant_2015_bil": 483.4, "gdp_current_bil": 508.4, "per_capita_gdp_sgd": 90150},
    {"year": 2019, "period_start": "2019-01-01", "real_gdp_growth_pct": 1.3, "gdp_constant_2015_bil": 489.7, "gdp_current_bil": 512.2, "per_capita_gdp_sgd": 89800},
    {"year": 2020, "period_start": "2020-01-01", "real_gdp_growth_pct": -3.9, "gdp_constant_2015_bil": 470.6, "gdp_current_bil": 476.3, "per_capita_gdp_sgd": 83770},
    {"year": 2021, "period_start": "2021-01-01", "real_gdp_growth_pct": 8.9, "gdp_constant_2015_bil": 512.5, "gdp_current_bil": 569.5, "per_capita_gdp_sgd": 104430},
    {"year": 2022, "period_start": "2022-01-01", "real_gdp_growth_pct": 3.8, "gdp_constant_2015_bil": 532.0, "gdp_current_bil": 643.5, "per_capita_gdp_sgd": 114160},
    {"year": 2023, "period_start": "2023-01-01", "real_gdp_growth_pct": 1.1, "gdp_constant_2015_bil": 537.8, "gdp_current_bil": 655.2, "per_capita_gdp_sgd": 110720},
    {"year": 2024, "period_start": "2024-01-01", "real_gdp_growth_pct": 3.6, "gdp_constant_2015_bil": 557.2, "gdp_current_bil": 673.3, "per_capita_gdp_sgd": 111470},
]

# 8. GDP Growth by Industry in Singapore (2019–2024)
_GDP_BY_INDUSTRY_DATA: list[dict[str, Any]] = [
    {"year": 2019, "period_start": "2019-01-01", "industry": "Manufacturing", "gdp_contribution_bil": 104.2, "yoy_growth_pct": -1.4, "gdp_share_pct": 20.3},
    {"year": 2019, "period_start": "2019-01-01", "industry": "Wholesale & Retail Trade", "gdp_contribution_bil": 89.6, "yoy_growth_pct": -0.6, "gdp_share_pct": 17.5},
    {"year": 2019, "period_start": "2019-01-01", "industry": "Financial & Insurance Services", "gdp_contribution_bil": 70.1, "yoy_growth_pct": 4.1, "gdp_share_pct": 13.7},
    {"year": 2019, "period_start": "2019-01-01", "industry": "Transportation & Storage", "gdp_contribution_bil": 37.4, "yoy_growth_pct": 1.2, "gdp_share_pct": 7.3},
    {"year": 2019, "period_start": "2019-01-01", "industry": "Information & Communications", "gdp_contribution_bil": 24.5, "yoy_growth_pct": 6.8, "gdp_share_pct": 4.8},

    {"year": 2021, "period_start": "2021-01-01", "industry": "Manufacturing", "gdp_contribution_bil": 128.5, "yoy_growth_pct": 13.2, "gdp_share_pct": 22.5},
    {"year": 2021, "period_start": "2021-01-01", "industry": "Wholesale & Retail Trade", "gdp_contribution_bil": 101.3, "yoy_growth_pct": 7.5, "gdp_share_pct": 17.8},
    {"year": 2021, "period_start": "2021-01-01", "industry": "Financial & Insurance Services", "gdp_contribution_bil": 78.4, "yoy_growth_pct": 7.4, "gdp_share_pct": 13.8},
    {"year": 2021, "period_start": "2021-01-01", "industry": "Transportation & Storage", "gdp_contribution_bil": 38.6, "yoy_growth_pct": 5.6, "gdp_share_pct": 6.8},
    {"year": 2021, "period_start": "2021-01-01", "industry": "Information & Communications", "gdp_contribution_bil": 30.2, "yoy_growth_pct": 11.2, "gdp_share_pct": 5.3},

    {"year": 2024, "period_start": "2024-01-01", "industry": "Manufacturing", "gdp_contribution_bil": 145.4, "yoy_growth_pct": 4.1, "gdp_share_pct": 21.6},
    {"year": 2024, "period_start": "2024-01-01", "industry": "Wholesale & Retail Trade", "gdp_contribution_bil": 123.9, "yoy_growth_pct": 3.8, "gdp_share_pct": 18.4},
    {"year": 2024, "period_start": "2024-01-01", "industry": "Financial & Insurance Services", "gdp_contribution_bil": 95.6, "yoy_growth_pct": 4.5, "gdp_share_pct": 14.2},
    {"year": 2024, "period_start": "2024-01-01", "industry": "Transportation & Storage", "gdp_contribution_bil": 47.8, "yoy_growth_pct": 3.2, "gdp_share_pct": 7.1},
    {"year": 2024, "period_start": "2024-01-01", "industry": "Information & Communications", "gdp_contribution_bil": 39.1, "yoy_growth_pct": 7.6, "gdp_share_pct": 5.8},
]

# 9. Singapore Trade, NODX & Inward Investments (2020–2024)
_TRADE_AND_INVESTMENTS_DATA: list[dict[str, Any]] = [
    {"year": 2020, "period_start": "2020-01-01", "merchandise_trade_bil": 969.1, "nodx_growth_pct": 4.3, "fdi_commitments_bil": 17.2, "electronics_exports_growth_pct": 4.9},
    {"year": 2021, "period_start": "2021-01-01", "merchandise_trade_bil": 1159.8, "nodx_growth_pct": 12.1, "fdi_commitments_bil": 11.8, "electronics_exports_growth_pct": 16.3},
    {"year": 2022, "period_start": "2022-01-01", "merchandise_trade_bil": 1365.4, "nodx_growth_pct": 3.0, "fdi_commitments_bil": 22.5, "electronics_exports_growth_pct": 0.5},
    {"year": 2023, "period_start": "2023-01-01", "merchandise_trade_bil": 1205.7, "nodx_growth_pct": -13.1, "fdi_commitments_bil": 12.7, "electronics_exports_growth_pct": -19.7},
    {"year": 2024, "period_start": "2024-01-01", "merchandise_trade_bil": 1285.3, "nodx_growth_pct": 4.2, "fdi_commitments_bil": 13.5, "electronics_exports_growth_pct": 8.1},
]

# 10. Household Income from Work & Gini (2020–2024)
_HOUSEHOLD_INCOME_DATA: list[dict[str, Any]] = [
    {"year": 2020, "period_start": "2020-01-01", "median_monthly_income_sgd": 9189, "real_income_growth_pct": -2.4, "gini_original": 0.452, "gini_after_transfers": 0.375, "percentile_20th_sgd": 2850, "percentile_80th_sgd": 16200},
    {"year": 2021, "period_start": "2021-01-01", "median_monthly_income_sgd": 9520, "real_income_growth_pct": 1.5, "gini_original": 0.444, "gini_after_transfers": 0.386, "percentile_20th_sgd": 2980, "percentile_80th_sgd": 16900},
    {"year": 2022, "period_start": "2022-01-01", "median_monthly_income_sgd": 10099, "real_income_growth_pct": 0.2, "gini_original": 0.437, "gini_after_transfers": 0.378, "percentile_20th_sgd": 3120, "percentile_80th_sgd": 17800},
    {"year": 2023, "period_start": "2023-01-01", "median_monthly_income_sgd": 10869, "real_income_growth_pct": 2.8, "gini_original": 0.433, "gini_after_transfers": 0.371, "percentile_20th_sgd": 3380, "percentile_80th_sgd": 19100},
    {"year": 2024, "period_start": "2024-01-01", "median_monthly_income_sgd": 11350, "real_income_growth_pct": 2.6, "gini_original": 0.430, "gini_after_transfers": 0.368, "percentile_20th_sgd": 3550, "percentile_80th_sgd": 19900},
]

# 11. Demographic Aging vs Youth Growth in Singapore (2018–2024)
_AGING_VS_YOUTH_DATA: list[dict[str, Any]] = [
    {"year": 2018, "period_start": "2018-01-01", "elderly_65plus_k": 547.9, "elderly_proportion_pct": 14.4, "youth_0_to_14_k": 582.1, "youth_proportion_pct": 15.3, "old_age_dependency_ratio": 20.1},
    {"year": 2019, "period_start": "2019-01-01", "elderly_65plus_k": 580.8, "elderly_proportion_pct": 15.2, "youth_0_to_14_k": 574.6, "youth_proportion_pct": 15.0, "old_age_dependency_ratio": 21.3},
    {"year": 2020, "period_start": "2020-01-01", "elderly_65plus_k": 614.4, "elderly_proportion_pct": 16.0, "youth_0_to_14_k": 567.2, "youth_proportion_pct": 14.7, "old_age_dependency_ratio": 22.7},
    {"year": 2021, "period_start": "2021-01-01", "elderly_65plus_k": 651.1, "elderly_proportion_pct": 16.8, "youth_0_to_14_k": 560.4, "youth_proportion_pct": 14.5, "old_age_dependency_ratio": 24.1},
    {"year": 2022, "period_start": "2022-01-01", "elderly_65plus_k": 706.3, "elderly_proportion_pct": 17.7, "youth_0_to_14_k": 554.8, "youth_proportion_pct": 14.1, "old_age_dependency_ratio": 25.8},
    {"year": 2023, "period_start": "2023-01-01", "elderly_65plus_k": 772.4, "elderly_proportion_pct": 18.7, "youth_0_to_14_k": 550.1, "youth_proportion_pct": 13.8, "old_age_dependency_ratio": 27.6},
    {"year": 2024, "period_start": "2024-01-01", "elderly_65plus_k": 831.2, "elderly_proportion_pct": 19.9, "youth_0_to_14_k": 544.5, "youth_proportion_pct": 13.5, "old_age_dependency_ratio": 29.8},
]



# Metadata catalog for all datasets
_DATASET_CATALOG: dict[str, dict[str, Any]] = {
    "employment_by_sector": {
        "id": "employment_by_sector",
        "title": "Employment by Sector (Annual 2019–2026)",
        "description": (
            "Annual total employment headcount (in thousands) and year-over-year change "
            "across 11 key industry sectors in Singapore (MOM/SingStat benchmark)."
        ),
        "url": "https://www.singstat.gov.sg/find-data/search-by-theme/economy/labour-and-employment",
        "format": "tabular",
        "industry": "Multi-Sector",
        "data": _EMPLOYMENT_BY_SECTOR_DATA,
        "aliases": ["employment_by_sector_2019_2024", "employment_by_sector_2019_2025", "employment_by_sector_2019_2026", "mock_policy_benchmark", "m810361"],
    },
    "ict_workforce_trends": {
        "id": "ict_workforce_trends",
        "title": "ICT Workforce Growth and Tech Talent Trends (2019–2026)",
        "description": (
            "Annual Singapore Information and Communications Technology (ICT) workforce headcounts, "
            "total workforce, tech workforce penetration percentage, and annual growth rates."
        ),
        "url": "https://data.gov.sg/datasets?query=ict+workforce",
        "format": "tabular",
        "industry": "Information & Communications",
        "data": _ICT_WORKFORCE_TRENDS_DATA,
        "aliases": ["ict_workforce_trends_2019_2024", "ict_workforce_trends_2019_2025", "ict_workforce_trends_2019_2026", "d_e3b8a1c9", "tech_employment"],
    },
    "unemployment_rate_quarterly": {
        "id": "unemployment_rate_quarterly",
        "title": "Quarterly Unemployment Rates in Singapore (2019–2024)",
        "description": (
            "Quarterly seasonally adjusted and headline unemployment rates for overall labor force, "
            "resident workforce, citizen workforce, and youth demographic (under 30) from Q1 2019 to Q4 2024."
        ),
        "url": "https://data.gov.sg/datasets?query=unemployment+rate",
        "format": "tabular",
        "industry": "Economy-wide",
        "data": _UNEMPLOYMENT_RATE_QUARTERLY_DATA,
        "aliases": ["unemployment_rate", "unemployment_quarterly"],
    },
    "median_gross_wages": {
        "id": "median_gross_wages",
        "title": "Median Gross Monthly Wages by Occupation Group (2019–2025)",
        "description": (
            "Annual median gross monthly wages in SGD (including employer CPF contributions) "
            "for major occupation groups: PMETs, Clerical, Service/Sales, Production/Craft, Cleaners/Laborers."
        ),
        "url": "https://data.gov.sg/datasets?query=wages",
        "format": "tabular",
        "industry": "Labor Economics",
        "data": _MEDIAN_GROSS_WAGES_DATA,
        "aliases": ["median_gross_wages_by_occupation", "wages_by_occupation"],
    },
    "business_registrations": {
        "id": "business_registrations",
        "title": "Business Formations and Cessations by Industry (2019–2024)",
        "description": (
            "Annual new company registrations, business entity cessations, and net enterprise "
            "formation in Singapore across key sectors from 2019 to 2024 (ACRA benchmark)."
        ),
        "url": "https://data.gov.sg/datasets?query=business+entities",
        "format": "tabular",
        "industry": "Enterprise & Business",
        "data": _BUSINESS_REGISTRATIONS_DATA,
        "aliases": ["business_registrations_by_industry", "acra_business_registrations"],
    },
    "singapore_population_growth": {
        "id": "singapore_population_growth",
        "title": "Singapore Population Growth, Fertility (TFR), Marriages & Life Expectancy (2018–2024)",
        "description": (
            "Official demographic indicators including total and resident population, "
            "total fertility rate (TFR), annual registered marriages, and citizen life expectancy."
        ),
        "url": "https://tablebuilder.singstat.gov.sg/table/TS/M810011",
        "format": "tabular",
        "industry": "Demographics & Society",
        "data": _POPULATION_GROWTH_DATA,
        "aliases": [
            "population_growth",
            "singapore_population",
            "population_growth_marriage_fertility_life_expectancy",
            "fertility_rate",
            "m810011",
            "demographics",
            "life_expectancy",
            "marriages",
        ],
    },
    "singapore_gdp_growth_6yr": {
        "id": "singapore_gdp_growth_6yr",
        "title": "Singapore Real GDP Growth Trajectory and Macroeconomic Performance (2018–2024)",
        "description": (
            "Annual real GDP growth rates, constant 2015 GDP levels, and per capita GDP "
            "covering Singapore's last 6 years economic trajectory (MTI/SingStat benchmark)."
        ),
        "url": "https://tablebuilder.singstat.gov.sg/table/TS/M015661",
        "format": "tabular",
        "industry": "Macroeconomy",
        "data": _GDP_GROWTH_6YR_DATA,
        "aliases": [
            "gdp_growth_6yr",
            "last_6_years_gdp_growth",
            "gdp_growth",
            "singapore_gdp_growth",
            "real_gdp_growth",
            "m015661",
            "economic_growth",
        ],
    },
    "singapore_gdp_by_industry": {
        "id": "singapore_gdp_by_industry",
        "title": "Singapore GDP Growth and Sectoral Contribution by Industry (2019–2024)",
        "description": (
            "Annual GDP value, YoY growth rate, and percentage share across key Singapore industries: "
            "Manufacturing, Wholesale & Retail Trade, Finance & Insurance, Transport, and ICT."
        ),
        "url": "https://tablebuilder.singstat.gov.sg/table/TS/M015671",
        "format": "tabular",
        "industry": "Industrial Economics",
        "data": _GDP_BY_INDUSTRY_DATA,
        "aliases": [
            "gdp_by_industry",
            "gdp_growth_by_industry",
            "gdp_growth_by_various_industries",
            "industry_gdp",
            "m015671",
            "manufacturing_gdp",
            "finance_gdp",
            "ict_gdp",
        ],
    },
    "singapore_trade_investments": {
        "id": "singapore_trade_investments",
        "title": "Singapore External Trade, Non-Oil Domestic Exports (NODX) & Foreign Direct Investment (2020–2024)",
        "description": (
            "Annual merchandise trade totals, Non-Oil Domestic Exports (NODX) percentage growth, "
            "electronics export growth, and inward FDI fixed asset investment commitments."
        ),
        "url": "https://tablebuilder.singstat.gov.sg/table/TS/M084221",
        "format": "tabular",
        "industry": "Trade & External Economy",
        "data": _TRADE_AND_INVESTMENTS_DATA,
        "aliases": [
            "trade_and_investments",
            "singapore_trade",
            "nodx_growth",
            "non_oil_domestic_exports",
            "fdi_commitments",
            "external_trade_investments",
            "m084221",
        ],
    },
    "singapore_household_income": {
        "id": "singapore_household_income",
        "title": "Singapore Household Income from Work, Wage Percentiles & Gini Coefficient (2020–2024)",
        "description": (
            "Median monthly household income from work, real growth rates, wage percentiles (20th and 80th), "
            "and Gini coefficient before and after government taxes and transfers."
        ),
        "url": "https://tablebuilder.singstat.gov.sg/table/TS/M810361",
        "format": "tabular",
        "industry": "Household Economics & Equity",
        "data": _HOUSEHOLD_INCOME_DATA,
        "aliases": [
            "household_income",
            "household_income_last_3_years",
            "median_household_income",
            "household_income_from_work",
            "gini_coefficient",
            "income_inequality",
            "m810361",
        ],
    },
    "singapore_aging_vs_youth": {
        "id": "singapore_aging_vs_youth",
        "title": "Singapore Demographic Aging vs Youth Growth and Dependency Ratios (2018–2024)",
        "description": (
            "Elderly population (aged 65+) headcount and proportion, youth population (aged 0–14) "
            "metrics, and old-age dependency ratio shifts in Singapore."
        ),
        "url": "https://tablebuilder.singstat.gov.sg/table/TS/M810012",
        "format": "tabular",
        "industry": "Demographics & Aging",
        "data": _AGING_VS_YOUTH_DATA,
        "aliases": [
            "aging_vs_youth",
            "aged_people_vs_youth_growth",
            "elderly_vs_youth",
            "old_age_dependency_ratio",
            "demographic_aging",
            "silver_generation",
            "m810012",
        ],
    },
}

# Fast lookup map for primary IDs and aliases
_LOOKUP_MAP: dict[str, str] = {}
for _primary_id, _meta in _DATASET_CATALOG.items():
    _LOOKUP_MAP[_primary_id.lower()] = _primary_id
    for _alias in _meta.get("aliases", []):
        _LOOKUP_MAP[_alias.lower()] = _primary_id


class MockInternalDataSource(AbstractDataSource):
    """Mock internal data source pre-loaded with realistic Singapore statistics.

    Designed for offline testing, local development, and demonstration environments.
    Conforms to the AbstractDataSource interface and guarantees safe fallback execution.
    """

    source_id: str = "mock_internal"
    display_name: str = "Mock Internal Database"

    def __init__(self) -> None:
        """Initialize mock dataset catalog."""
        self._catalog = _DATASET_CATALOG
        self._lookup = _LOOKUP_MAP

    async def search(
        self,
        keywords: str | list[str],
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Search available datasets matching keywords and filters.

        Performs case-insensitive substring matching across dataset ID, title,
        and description. If keywords is empty or wildcard ('*'), returns all
        catalog entries subject to active filters.

        Args:
            keywords: Query string or list of query strings.
            **filters: Optional filters (e.g. industry, format).

        Returns:
            List of matching dataset metadata dictionaries matching standard schema:
            [{'id': str, 'title': str, 'description': str, 'url': str, 'format': str}]
        """
        # Normalize keywords to list of lowercase strings
        search_terms: list[str] = []
        if isinstance(keywords, str):
            kw_clean = keywords.strip()
            if kw_clean and kw_clean != "*":
                # Check both full string and individual whitespace-separated tokens
                search_terms = [kw_clean.lower()] + [t.lower() for t in kw_clean.split()]
        elif isinstance(keywords, (list, tuple, set)):
            for k in keywords:
                if isinstance(k, str) and k.strip():
                    search_terms.append(k.strip().lower())

        results: list[dict[str, Any]] = []

        for meta in self._catalog.values():
            # Check keyword match
            if search_terms:
                haystack = f"{meta['id']} {meta['title']} {meta['description']} {' '.join(meta.get('aliases', []))}".lower()
                matches = any(term in haystack for term in search_terms)
                if not matches:
                    continue

            # Check optional industry filter
            if "industry" in filters and filters["industry"]:
                filter_ind = str(filters["industry"]).strip().lower()
                ds_ind = meta.get("industry", "").lower()
                if filter_ind not in ds_ind and ds_ind not in filter_ind and filter_ind != "*":
                    continue

            # Check optional format filter
            if "format" in filters and filters["format"]:
                filter_fmt = str(filters["format"]).strip().lower()
                if filter_fmt != meta.get("format", "").lower() and filter_fmt != "*":
                    continue

            results.append(
                {
                    "id": meta["id"],
                    "title": meta["title"],
                    "description": meta["description"],
                    "url": f"internal://mock_database/{meta['id']}",
                    "format": meta["format"],
                }
            )

        return results

    async def fetch(self, dataset_id: str) -> pd.DataFrame:
        """Fetch and return a normalized pandas DataFrame for the specified dataset.

        Args:
            dataset_id: Identifier of the dataset to retrieve (supports aliases).

        Returns:
            Normalized pandas DataFrame with lowercase columns, underscores,
            UTC timestamp columns, and metadata attached to `df.attrs`.
            Returns an empty DataFrame if dataset_id is not found.
        """
        if not dataset_id or not isinstance(dataset_id, str):
            logger.warning(
                "MockInternalDataSource.fetch called with empty or invalid dataset_id: %r",
                dataset_id,
            )
            return pd.DataFrame()

        lookup_key = dataset_id.strip().lower()
        primary_id = self._lookup.get(lookup_key)

        if not primary_id or primary_id not in self._catalog:
            logger.warning("Dataset '%s' not found in MockInternalDataSource", dataset_id)
            return pd.DataFrame()

        meta = self._catalog[primary_id]
        records = meta.get("data", [])

        # Create DataFrame from pre-loaded records
        raw_df = pd.DataFrame(records)

        # Normalize DataFrame according to platform standards
        metadata = {
            "source": self.source_id,
            "dataset_id": primary_id,
            "requested_id": dataset_id,
            "title": meta["title"],
            "description": meta["description"],
            "url": meta["url"],
            "industry": meta.get("industry"),
            "fetched_at": datetime.now(UTC).isoformat(),
        }

        normalized_df = self.normalize_dataframe(raw_df, metadata=metadata)
        logger.debug(
            "Successfully fetched dataset '%s' (%d rows) from %s",
            primary_id,
            len(normalized_df),
            self.source_id,
        )
        return normalized_df

    async def health_check(self) -> bool:
        """Check availability of mock data source.

        Always returns True as pre-loaded data is residing in memory.
        """
        return True
