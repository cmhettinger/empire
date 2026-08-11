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
        MaskedFloatArray,
        normalize_source_bars,
    )
    from empire_stonks_tech_indicators.returns import (
        ReturnArrays,
        calculate_returns,
    )
    from empire_stonks_tech_indicators.bar_structure import (
        BarStructureArrays,
        calculate_bar_structure,
    )


def __getattr__(name: str) -> object:
    if name in {
        "CalculationArrays",
        "MaskedFloatArray",
        "normalize_source_bars",
    }:
        from empire_stonks_tech_indicators.arrays import (
            CalculationArrays,
            MaskedFloatArray,
            normalize_source_bars,
        )

        exports = {
            "CalculationArrays": CalculationArrays,
            "MaskedFloatArray": MaskedFloatArray,
            "normalize_source_bars": normalize_source_bars,
        }
        globals().update(exports)
        return exports[name]
    if name in {"ReturnArrays", "calculate_returns"}:
        from empire_stonks_tech_indicators.returns import (
            ReturnArrays,
            calculate_returns,
        )

        exports = {
            "ReturnArrays": ReturnArrays,
            "calculate_returns": calculate_returns,
        }
        globals().update(exports)
        return exports[name]
    if name in {"BarStructureArrays", "calculate_bar_structure"}:
        from empire_stonks_tech_indicators.bar_structure import (
            BarStructureArrays,
            calculate_bar_structure,
        )

        exports = {
            "BarStructureArrays": BarStructureArrays,
            "calculate_bar_structure": calculate_bar_structure,
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
    "BarStructureArrays",
    "CalculationArrays",
    "MaskedFloatArray",
    "ReturnArrays",
    "BenchmarkHistory",
    "EligibleListing",
    "EODDATA_DAILY_JOB_NAME",
    "ListingStateComparison",
    "SourceReadinessDecision",
    "YAHOO_DAILY_JOB_NAME",
    "calculate_bar_structure",
    "calculate_returns",
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
