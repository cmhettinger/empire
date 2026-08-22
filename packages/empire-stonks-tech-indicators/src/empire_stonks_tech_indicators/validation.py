"""Strict pre-SQL validation for complete technical-indicator feature rows."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import isfinite

from empire_stonks_tech_indicators.arrays import (
    CalculationArrays,
    MaskedFloatArray,
)
from empire_stonks_tech_indicators.bar_structure import calculate_bar_structure
from empire_stonks_tech_indicators.bollinger import calculate_bollinger_state
from empire_stonks_tech_indicators.directional_movement import (
    calculate_directional_movement,
)
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsValidationError,
)
from empire_stonks_tech_indicators.macd import calculate_macd
from empire_stonks_tech_indicators.models import (
    FeatureRow,
    PYTHON_FEATURE_FIELDS,
    SourceBar,
)
from empire_stonks_tech_indicators.moving_average_trends import (
    calculate_moving_average_trends,
)
from empire_stonks_tech_indicators.moving_averages import calculate_moving_averages
from empire_stonks_tech_indicators.queries import BenchmarkHistory, EligibleListing
from empire_stonks_tech_indicators.range_relationships import (
    calculate_range_relationships,
)
from empire_stonks_tech_indicators.return_statistics import (
    calculate_return_statistics,
)
from empire_stonks_tech_indicators.returns import calculate_returns
from empire_stonks_tech_indicators.rsi_atr import calculate_rsi_atr
from empire_stonks_tech_indicators.spx_features import (
    SpxFeatureArrays,
    calculate_spx_features,
)
from empire_stonks_tech_indicators.streaks import StreakArrays, calculate_streaks
from empire_stonks_tech_indicators.volume_liquidity import (
    calculate_volume_liquidity,
)


ABSOLUTE_TOLERANCE = 1e-12
RELATIVE_TOLERANCE = 1e-10

_BOUNDED_POINT_FIELDS = (
    "rsi_14",
    "plus_di_14",
    "minus_di_14",
    "adx_14",
)
_CORRELATION_FIELDS = ("spx_correlation_60d", "spx_correlation_252d")
_NONNEGATIVE_FIELDS = (
    "atr_14",
    "return_volatility_20d_pct",
    "return_volatility_60d_pct",
    "price_stddev_20",
    "volume_avg_20",
    "volume_avg_60",
    "dollar_volume_avg_20",
)
_GENERATED_FIELDS = (
    "dollar_volume",
    "intraday_return_1d_pct",
    "daily_range_pct",
    "close_location_1d",
    "pct_sma_20",
    "pct_sma_50",
    "pct_sma_200",
    "pct_ema_20",
    "pct_ema_50",
    "pct_sma_20_vs_50",
    "pct_sma_20_vs_200",
    "pct_sma_50_vs_200",
    "pct_hh_20",
    "pct_hh_50",
    "pct_hh_252",
    "pct_ll_20",
    "pct_ll_50",
    "atr_pct_14",
    "bollinger_percent_b_20_2",
    "bollinger_bandwidth_20_2",
    "volume_ratio_20",
    "macd_12_26_pct",
    "macd_histogram_12_26_9_pct",
)


@dataclass(frozen=True)
class _ExpectedFeatureState:
    persisted: dict[str, MaskedFloatArray]
    generated_references: dict[str, MaskedFloatArray]
    streaks: StreakArrays
    spx: SpxFeatureArrays


def _fail(row: FeatureRow, message: str, *, field_name: str | None = None) -> None:
    field = "" if field_name is None else f" field {field_name}"
    raise TechIndicatorsValidationError(
        "Feature row validation failed for provider listing "
        f"{row.source.provider_listing_id} on {row.source.trading_date}{field}: "
        f"{message}"
    )


def _equivalent(actual: float | None, expected: float | None) -> bool:
    if actual is None or expected is None:
        return actual is expected
    if not isfinite(actual) or not isfinite(expected):
        return False
    return abs(actual - expected) <= max(
        ABSOLUTE_TOLERANCE,
        RELATIVE_TOLERANCE * max(abs(actual), abs(expected)),
    )


def _divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0.0:
        return None
    result = numerator / denominator
    if not isfinite(result):
        raise ArithmeticError("generated division produced a non-finite value")
    return result


def _distance(numerator: float | None, denominator: float | None) -> float | None:
    result = _divide(numerator, denominator)
    return None if result is None else result - 1.0


def _multiply(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    result = left * right
    if not isfinite(result):
        raise ArithmeticError("generated multiplication produced a non-finite value")
    return result


def _generated_values(
    source: SourceBar,
    value_for: Callable[[str], float | None],
) -> dict[str, float | None]:
    open_value = float(source.open)
    high = float(source.high)
    low = float(source.low)
    close = float(source.close)
    volume = None if source.volume is None else float(source.volume)

    upper = None
    lower = None
    sma_20 = value_for("sma_20")
    price_stddev_20 = value_for("price_stddev_20")
    ema_26 = value_for("ema_26")
    if sma_20 is not None and price_stddev_20 is not None:
        upper = sma_20 + 2.0 * price_stddev_20
        lower = sma_20 - 2.0 * price_stddev_20
        if not isfinite(upper) or not isfinite(lower):
            raise ArithmeticError("generated Bollinger input produced non-finite bands")

    values = {
        "dollar_volume": _multiply(abs(close), volume),
        "intraday_return_1d_pct": _distance(close, open_value),
        "daily_range_pct": _divide(high - low, abs(close)),
        "close_location_1d": _divide(close - low, high - low),
        "pct_sma_20": _distance(close, sma_20),
        "pct_sma_50": _distance(close, value_for("sma_50")),
        "pct_sma_200": _distance(close, value_for("sma_200")),
        "pct_ema_20": _distance(close, value_for("ema_20")),
        "pct_ema_50": _distance(close, value_for("ema_50")),
        "pct_sma_20_vs_50": _distance(sma_20, value_for("sma_50")),
        "pct_sma_20_vs_200": _distance(sma_20, value_for("sma_200")),
        "pct_sma_50_vs_200": _distance(
            value_for("sma_50"),
            value_for("sma_200"),
        ),
        "pct_hh_20": _distance(close, value_for("hh_20")),
        "pct_hh_50": _distance(close, value_for("hh_50")),
        "pct_hh_252": _distance(close, value_for("hh_252")),
        "pct_ll_20": _distance(close, value_for("ll_20")),
        "pct_ll_50": _distance(close, value_for("ll_50")),
        "atr_pct_14": _divide(value_for("atr_14"), abs(close)),
        "bollinger_percent_b_20_2": _divide(
            None if lower is None else close - lower,
            None if upper is None or lower is None else upper - lower,
        ),
        "bollinger_bandwidth_20_2": _divide(
            None if upper is None or lower is None else upper - lower,
            None if sma_20 is None else abs(sma_20),
        ),
        "volume_ratio_20": _divide(volume, value_for("volume_avg_20")),
        "macd_12_26_pct": _divide(
            value_for("macd_12_26"),
            None if ema_26 is None else abs(ema_26),
        ),
        "macd_histogram_12_26_9_pct": _divide(
            value_for("macd_histogram_12_26_9"),
            abs(close),
        ),
    }
    if tuple(values) != _GENERATED_FIELDS:
        raise AssertionError("generated validation field inventory drifted")
    return values


def _calculate_expected_feature_state(
    calculation_arrays: CalculationArrays,
    *,
    subject: EligibleListing,
    benchmark_history: BenchmarkHistory | None,
) -> _ExpectedFeatureState:
    returns = calculate_returns(calculation_arrays)
    bar_structure = calculate_bar_structure(calculation_arrays)
    moving_averages = calculate_moving_averages(calculation_arrays)
    moving_average_trends = calculate_moving_average_trends(
        calculation_arrays,
        moving_averages,
    )
    ranges = calculate_range_relationships(calculation_arrays)
    rsi_atr = calculate_rsi_atr(calculation_arrays)
    return_statistics = calculate_return_statistics(calculation_arrays, returns)
    bollinger = calculate_bollinger_state(calculation_arrays, moving_averages)
    directional_movement = calculate_directional_movement(calculation_arrays)
    macd = calculate_macd(calculation_arrays, moving_averages)
    volume_liquidity = calculate_volume_liquidity(
        calculation_arrays,
        bar_structure,
    )
    streaks = calculate_streaks(calculation_arrays)
    spx = calculate_spx_features(
        calculation_arrays,
        subject=subject,
        benchmark_history=benchmark_history,
    )

    persisted_families = (
        returns,
        bar_structure,
        moving_averages,
        moving_average_trends,
        ranges,
        rsi_atr,
        return_statistics,
        bollinger,
        directional_movement,
        macd,
        volume_liquidity,
        spx,
    )
    persisted = {
        field_name: getattr(family, field_name)
        for field_name in PYTHON_FEATURE_FIELDS
        if field_name not in {"consecutive_up_days", "consecutive_down_days"}
        for family in persisted_families
        if hasattr(family, field_name)
    }
    expected_float_fields = set(PYTHON_FEATURE_FIELDS) - {
        "consecutive_up_days",
        "consecutive_down_days",
    }
    if set(persisted) != expected_float_fields:
        raise AssertionError("Python feature validation inventory drifted")

    generated_reference_families = (
        bar_structure,
        moving_average_trends,
        bollinger,
        macd,
    )
    generated_references = {
        field_name: getattr(family, field_name)
        for field_name in _GENERATED_FIELDS
        for family in generated_reference_families
        if hasattr(family, field_name)
    }
    return _ExpectedFeatureState(
        persisted=persisted,
        generated_references=generated_references,
        streaks=streaks,
        spx=spx,
    )


def _validate_subject(
    calculation_arrays: CalculationArrays,
    subject: EligibleListing,
) -> None:
    bars = calculation_arrays.source_bars
    if subject.provider_listing_id != calculation_arrays.provider_listing_id:
        raise TechIndicatorsValidationError(
            "Feature validation subject does not match the calculation listing."
        )
    if subject.source_observation_count != len(bars):
        raise TechIndicatorsValidationError(
            "Feature validation subject observation count does not match the "
            "calculation prefix."
        )
    if (
        subject.first_trading_date != bars[0].trading_date
        or subject.last_trading_date != bars[-1].trading_date
    ):
        raise TechIndicatorsValidationError(
            "Feature validation subject coverage does not match the calculation prefix."
        )


def _validate_bounds(row: FeatureRow) -> None:
    for field_name in _BOUNDED_POINT_FIELDS:
        value = getattr(row, field_name)
        if value is not None and not 0.0 <= value <= 100.0:
            _fail(row, "value must be between 0 and 100", field_name=field_name)
    for field_name in _CORRELATION_FIELDS:
        value = getattr(row, field_name)
        if value is not None and not -1.0 <= value <= 1.0:
            _fail(row, "value must be between -1 and 1", field_name=field_name)
    for field_name in _NONNEGATIVE_FIELDS:
        value = getattr(row, field_name)
        if value is not None and value < 0.0:
            _fail(row, "value must be non-negative", field_name=field_name)
    if row.consecutive_up_days > 0 and row.consecutive_down_days > 0:
        _fail(row, "up and down streaks cannot both be positive")


def _validate_feature_rows_against_state(
    rows: Sequence[FeatureRow],
    *,
    calculation_arrays: CalculationArrays,
    subject: EligibleListing,
    expected_state: _ExpectedFeatureState,
) -> None:
    if any(not isinstance(row, FeatureRow) for row in rows):
        raise TypeError("rows must contain only FeatureRow records.")
    if len(rows) != calculation_arrays.observation_count:
        raise TechIndicatorsValidationError(
            "Feature row count does not match the complete calculation prefix."
        )

    _validate_subject(calculation_arrays, subject)

    for index, row in enumerate(rows):
        source = calculation_arrays.source_bars[index]
        if row.source != source:
            _fail(row, "copied OHLCV does not exactly match the source observation")
        if row.history_observation_count != index + 1:
            _fail(
                row,
                "history observation count is not the chronological prefix count",
                field_name="history_observation_count",
            )
        if (
            row.relative_strength_benchmark_provider_listing_id
            != expected_state.spx.benchmark_provider_listing_id
        ):
            _fail(row, "benchmark lineage does not match subject support")
        if (
            row.relative_strength_benchmark_provider_listing_id
            == source.provider_listing_id
        ):
            _fail(row, "the subject cannot be its own relative-strength benchmark")

        _validate_bounds(row)
        expected_persisted = {
            field_name: series.value_at(index)
            for field_name, series in expected_state.persisted.items()
        }
        for field_name, expected in expected_persisted.items():
            if not _equivalent(getattr(row, field_name), expected):
                _fail(
                    row,
                    "value or null mask does not match the V1 calculation",
                    field_name=field_name,
                )

        expected_up = int(expected_state.streaks.consecutive_up_days[index])
        expected_down = int(expected_state.streaks.consecutive_down_days[index])
        if row.consecutive_up_days != expected_up:
            _fail(
                row,
                "value does not match the source prefix",
                field_name="consecutive_up_days",
            )
        if row.consecutive_down_days != expected_down:
            _fail(
                row,
                "value does not match the source prefix",
                field_name="consecutive_down_days",
            )

        try:
            generated = _generated_values(
                row.source,
                lambda field_name: getattr(row, field_name),
            )
            expected_generated = _generated_values(
                source,
                expected_persisted.__getitem__,
            )
        except (ArithmeticError, OverflowError) as error:
            _fail(row, str(error))
        for field_name, value in generated.items():
            if not _equivalent(value, expected_generated[field_name]):
                _fail(
                    row,
                    "generated input does not match the V1 calculation",
                    field_name=field_name,
                )
            reference = expected_state.generated_references.get(field_name)
            if reference is not None and not _equivalent(
                expected_generated[field_name], reference.value_at(index)
            ):
                _fail(
                    row,
                    "generated formula does not match its family reference",
                    field_name=field_name,
                )
            if value is not None and not isfinite(value):
                _fail(
                    row,
                    "generated input produced a non-finite value",
                    field_name=field_name,
                )
        close_location = generated["close_location_1d"]
        if close_location is not None and not 0.0 <= close_location <= 1.0:
            _fail(
                row,
                "generated value must be between 0 and 1",
                field_name="close_location_1d",
            )
        for field_name in (
            "dollar_volume",
            "daily_range_pct",
            "atr_pct_14",
            "bollinger_bandwidth_20_2",
            "volume_ratio_20",
        ):
            value = generated[field_name]
            if value is not None and value < 0.0:
                _fail(
                    row,
                    "generated value must be non-negative",
                    field_name=field_name,
                )


def validate_feature_rows(
    rows: Sequence[FeatureRow],
    *,
    calculation_arrays: CalculationArrays,
    subject: EligibleListing,
    benchmark_history: BenchmarkHistory | None = None,
) -> None:
    """Validate one complete chronological feature image before persistence.

    The row sequence must cover the same full source prefix as
    ``calculation_arrays``. Every package-written field is checked against a
    fresh V1 calculation, and every PostgreSQL-generated expression is
    evaluated from the proposed row inputs before any SQL is allowed.
    """

    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise TypeError("rows must be a sequence of FeatureRow records.")
    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")
    if not isinstance(subject, EligibleListing):
        raise TypeError("subject must be an EligibleListing.")
    if benchmark_history is not None and not isinstance(
        benchmark_history,
        BenchmarkHistory,
    ):
        raise TypeError("benchmark_history must be a BenchmarkHistory or None.")
    expected_state = _calculate_expected_feature_state(
        calculation_arrays,
        subject=subject,
        benchmark_history=benchmark_history,
    )
    _validate_feature_rows_against_state(
        rows,
        calculation_arrays=calculation_arrays,
        subject=subject,
        expected_state=expected_state,
    )


__all__ = [
    "ABSOLUTE_TOLERANCE",
    "RELATIVE_TOLERANCE",
    "validate_feature_rows",
]
