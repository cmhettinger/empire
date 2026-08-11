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
    from empire_stonks_tech_indicators.return_statistics import (
        ReturnStatisticArrays,
        calculate_return_statistics,
    )
    from empire_stonks_tech_indicators.rsi_atr import (
        RsiAtrArrays,
        calculate_rsi_atr,
    )
    from empire_stonks_tech_indicators.bar_structure import (
        BarStructureArrays,
        calculate_bar_structure,
    )
    from empire_stonks_tech_indicators.range_relationships import (
        RangeRelationshipArrays,
        calculate_range_relationships,
    )
    from empire_stonks_tech_indicators.volume_liquidity import (
        VolumeLiquidityArrays,
        calculate_volume_liquidity,
    )
    from empire_stonks_tech_indicators.streaks import (
        StreakArrays,
        calculate_streaks,
    )
    from empire_stonks_tech_indicators.moving_averages import (
        MovingAverageArrays,
        calculate_moving_averages,
    )
    from empire_stonks_tech_indicators.moving_average_trends import (
        MovingAverageTrendArrays,
        calculate_moving_average_trends,
    )
    from empire_stonks_tech_indicators.talib_adapter import (
        TALibAdapter,
        TALibRuntimeInfo,
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
    if name in {"ReturnStatisticArrays", "calculate_return_statistics"}:
        from empire_stonks_tech_indicators.return_statistics import (
            ReturnStatisticArrays,
            calculate_return_statistics,
        )

        exports = {
            "ReturnStatisticArrays": ReturnStatisticArrays,
            "calculate_return_statistics": calculate_return_statistics,
        }
        globals().update(exports)
        return exports[name]
    if name in {"RsiAtrArrays", "calculate_rsi_atr"}:
        from empire_stonks_tech_indicators.rsi_atr import (
            RsiAtrArrays,
            calculate_rsi_atr,
        )

        exports = {
            "RsiAtrArrays": RsiAtrArrays,
            "calculate_rsi_atr": calculate_rsi_atr,
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
    if name in {"RangeRelationshipArrays", "calculate_range_relationships"}:
        from empire_stonks_tech_indicators.range_relationships import (
            RangeRelationshipArrays,
            calculate_range_relationships,
        )

        exports = {
            "RangeRelationshipArrays": RangeRelationshipArrays,
            "calculate_range_relationships": calculate_range_relationships,
        }
        globals().update(exports)
        return exports[name]
    if name in {"VolumeLiquidityArrays", "calculate_volume_liquidity"}:
        from empire_stonks_tech_indicators.volume_liquidity import (
            VolumeLiquidityArrays,
            calculate_volume_liquidity,
        )

        exports = {
            "VolumeLiquidityArrays": VolumeLiquidityArrays,
            "calculate_volume_liquidity": calculate_volume_liquidity,
        }
        globals().update(exports)
        return exports[name]
    if name in {"StreakArrays", "calculate_streaks"}:
        from empire_stonks_tech_indicators.streaks import (
            StreakArrays,
            calculate_streaks,
        )

        exports = {
            "StreakArrays": StreakArrays,
            "calculate_streaks": calculate_streaks,
        }
        globals().update(exports)
        return exports[name]
    if name in {"MovingAverageArrays", "calculate_moving_averages"}:
        from empire_stonks_tech_indicators.moving_averages import (
            MovingAverageArrays,
            calculate_moving_averages,
        )

        exports = {
            "MovingAverageArrays": MovingAverageArrays,
            "calculate_moving_averages": calculate_moving_averages,
        }
        globals().update(exports)
        return exports[name]
    if name in {"MovingAverageTrendArrays", "calculate_moving_average_trends"}:
        from empire_stonks_tech_indicators.moving_average_trends import (
            MovingAverageTrendArrays,
            calculate_moving_average_trends,
        )

        exports = {
            "MovingAverageTrendArrays": MovingAverageTrendArrays,
            "calculate_moving_average_trends": calculate_moving_average_trends,
        }
        globals().update(exports)
        return exports[name]
    if name in {"TALibAdapter", "TALibRuntimeInfo"}:
        from empire_stonks_tech_indicators.talib_adapter import (
            TALibAdapter,
            TALibRuntimeInfo,
        )

        exports = {
            "TALibAdapter": TALibAdapter,
            "TALibRuntimeInfo": TALibRuntimeInfo,
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
    "RangeRelationshipArrays",
    "ReturnArrays",
    "ReturnStatisticArrays",
    "RsiAtrArrays",
    "BenchmarkHistory",
    "EligibleListing",
    "EODDATA_DAILY_JOB_NAME",
    "ListingStateComparison",
    "MovingAverageArrays",
    "MovingAverageTrendArrays",
    "SourceReadinessDecision",
    "StreakArrays",
    "TALibAdapter",
    "TALibRuntimeInfo",
    "VolumeLiquidityArrays",
    "YAHOO_DAILY_JOB_NAME",
    "calculate_bar_structure",
    "calculate_moving_averages",
    "calculate_moving_average_trends",
    "calculate_range_relationships",
    "calculate_return_statistics",
    "calculate_returns",
    "calculate_rsi_atr",
    "calculate_streaks",
    "calculate_volume_liquidity",
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
