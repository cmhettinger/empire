"""Reusable technical-indicator utilities for Empire stonks."""

from typing import TYPE_CHECKING

from empire_stonks_tech_indicators.config import (
    BenchmarkConfig,
    TechIndicatorsConfig,
)
from empire_stonks_tech_indicators.exceptions import (
    EmpireStonksTechIndicatorsError,
    TechIndicatorsCalculationError,
    TechIndicatorsConfigError,
    TechIndicatorsPersistenceError,
    TechIndicatorsValidationError,
    TechIndicatorsWorkflowError,
)
from empire_stonks_tech_indicators.models import (
    FeatureCounts,
    FeatureRow,
    ReasonCount,
    ResolvedBenchmark,
    SourceBar,
    TechIndicatorsIssue,
    TechIndicatorsRunResult,
    TechIndicatorsScope,
    TechIndicatorsSummary,
)
from empire_stonks_tech_indicators.queries import (
    BenchmarkHistory,
    EligibleListing,
    iter_source_bar_pages,
    load_spx_benchmark_history,
    resolve_spx_benchmark,
    select_eligible_listings,
)
from empire_stonks_tech_indicators.readiness import (
    EODDATA_DAILY_JOB_NAME,
    SourceReadinessDecision,
    YAHOO_DAILY_JOB_NAME,
    decide_source_readiness,
)
from empire_stonks_tech_indicators.state import (
    ListingStateComparison,
    iter_state_comparison_pages,
)

if TYPE_CHECKING:
    from empire_stonks_tech_indicators.arrays import (
        CalculationArrays,
        normalize_source_bars,
    )


def __getattr__(name: str) -> object:
    if name in {"CalculationArrays", "normalize_source_bars"}:
        from empire_stonks_tech_indicators.arrays import (
            CalculationArrays,
            normalize_source_bars,
        )

        exports = {
            "CalculationArrays": CalculationArrays,
            "normalize_source_bars": normalize_source_bars,
        }
        globals().update(exports)
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "EmpireStonksTechIndicatorsError",
    "TechIndicatorsCalculationError",
    "TechIndicatorsConfigError",
    "TechIndicatorsPersistenceError",
    "TechIndicatorsValidationError",
    "TechIndicatorsWorkflowError",
    "BenchmarkConfig",
    "TechIndicatorsConfig",
    "CalculationArrays",
    "BenchmarkHistory",
    "EligibleListing",
    "EODDATA_DAILY_JOB_NAME",
    "ListingStateComparison",
    "SourceReadinessDecision",
    "YAHOO_DAILY_JOB_NAME",
    "decide_source_readiness",
    "iter_source_bar_pages",
    "iter_state_comparison_pages",
    "load_spx_benchmark_history",
    "normalize_source_bars",
    "resolve_spx_benchmark",
    "select_eligible_listings",
    "FeatureCounts",
    "FeatureRow",
    "ReasonCount",
    "ResolvedBenchmark",
    "SourceBar",
    "TechIndicatorsIssue",
    "TechIndicatorsRunResult",
    "TechIndicatorsScope",
    "TechIndicatorsSummary",
]
