from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    CalculationArrays,
    MaskedFloatArray,
    MovingAverageArrays,
    SourceBar,
    calculate_moving_averages,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import moving_averages as moving_module


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
ABSOLUTE_TOLERANCE = 1e-12
RELATIVE_TOLERANCE = 1e-10


def _bars(observation_count: int = 260) -> tuple[SourceBar, ...]:
    first_date = date(2024, 1, 2)
    result = []
    for index in range(observation_count):
        close = Decimal(index - 80) * Decimal("0.75")
        close += Decimal((index % 11) - 5) / Decimal("10")
        result.append(
            SourceBar(
                provider_listing_id=LISTING_ID,
                trading_date=first_date + timedelta(days=index * 2),
                open=close,
                high=close + Decimal("2"),
                low=close - Decimal("2"),
                close=close,
                volume=Decimal("1000") + index,
            )
        )
    return tuple(result)


def _arrays(bars: tuple[SourceBar, ...] | None = None) -> CalculationArrays:
    return normalize_source_bars(_bars() if bars is None else bars)


def _sma_reference(close: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(close), np.nan, dtype=np.float64)
    for index in range(period - 1, len(close)):
        window = close[index - period + 1 : index + 1]
        result[index] = sum(float(value) for value in window) / period
    return result


def _ema_reference(close: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(close), np.nan, dtype=np.float64)
    if len(close) < period:
        return result
    seed_index = period - 1
    result[seed_index] = (
        sum(float(value) for value in close[:period]) / period
    )
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(close)):
        result[index] = (
            (float(close[index]) - result[index - 1]) * alpha
            + result[index - 1]
        )
    return result


def _assert_equivalent(actual: MaskedFloatArray, expected: np.ndarray) -> None:
    expected_mask = np.isnan(expected)
    np.testing.assert_array_equal(actual.null_mask, expected_mask)
    np.testing.assert_allclose(
        actual.values[~expected_mask],
        expected[~expected_mask],
        atol=ABSOLUTE_TOLERANCE,
        rtol=RELATIVE_TOLERANCE,
    )


def test_moving_average_api_and_fixed_profile_are_explicit() -> None:
    assert moving_module.__all__ == [
        "EMA_PERIODS",
        "MOVING_AVERAGE_FIELDS",
        "SMA_PERIODS",
        "MovingAverageArrays",
        "calculate_moving_averages",
    ]
    assert moving_module.SMA_PERIODS == (20, 50, 200)
    assert moving_module.EMA_PERIODS == (12, 20, 26, 50)
    assert moving_module.MOVING_AVERAGE_FIELDS == (
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_12",
        "ema_20",
        "ema_26",
        "ema_50",
    )
    assert public_api.MovingAverageArrays is MovingAverageArrays
    assert public_api.calculate_moving_averages is calculate_moving_averages


def test_sma_matches_independent_complete_window_reference() -> None:
    arrays = _arrays()
    result = calculate_moving_averages(arrays)

    for period in moving_module.SMA_PERIODS:
        actual = getattr(result, f"sma_{period}")
        _assert_equivalent(actual, _sma_reference(arrays.close, period))
        assert actual.value_at(period - 2) is None
        assert actual.value_at(period - 1) is not None


def test_ema_matches_independent_sma_seed_and_recursion_reference() -> None:
    arrays = _arrays()
    result = calculate_moving_averages(arrays)

    for period in moving_module.EMA_PERIODS:
        actual = getattr(result, f"ema_{period}")
        expected = _ema_reference(arrays.close, period)
        _assert_equivalent(actual, expected)
        assert actual.value_at(period - 2) is None
        assert actual.value_at(period - 1) == pytest.approx(
            expected[period - 1],
            abs=ABSOLUTE_TOLERANCE,
            rel=RELATIVE_TOLERANCE,
        )


def test_short_history_preserves_exact_warmup_masks() -> None:
    result = calculate_moving_averages(_arrays(_bars(10)))

    assert result.observation_count == 10
    for field_name in moving_module.MOVING_AVERAGE_FIELDS:
        series = getattr(result, field_name)
        assert series.null_mask.all()
        assert np.isnan(series.values).all()


@pytest.mark.parametrize("split", [1, 11, 12, 19, 20, 49, 50, 199, 200, 233])
def test_full_prefix_append_calculation_is_incrementally_equivalent(
    split: int,
) -> None:
    bars = _bars()
    prefix = calculate_moving_averages(_arrays(bars[:split]))
    full = calculate_moving_averages(_arrays(bars))

    for field_name in moving_module.MOVING_AVERAGE_FIELDS:
        prefix_series = getattr(prefix, field_name)
        full_series = getattr(full, field_name)
        np.testing.assert_array_equal(
            prefix_series.values,
            full_series.values[:split],
        )
        np.testing.assert_array_equal(
            prefix_series.null_mask,
            full_series.null_mask[:split],
        )


def test_full_recalculation_with_suffix_write_matches_corrected_rebuild() -> None:
    bars = _bars()
    correction_index = 75
    corrected_bar = replace(
        bars[correction_index],
        open=bars[correction_index].open + Decimal("5"),
        high=bars[correction_index].high + Decimal("5"),
        low=bars[correction_index].low + Decimal("5"),
        close=bars[correction_index].close + Decimal("5"),
    )
    corrected_bars = (
        *bars[:correction_index],
        corrected_bar,
        *bars[correction_index + 1 :],
    )
    previous = calculate_moving_averages(_arrays(bars))
    recalculated = calculate_moving_averages(_arrays(corrected_bars))

    for field_name in moving_module.MOVING_AVERAGE_FIELDS:
        previous_series = getattr(previous, field_name)
        recalculated_series = getattr(recalculated, field_name)
        combined_values = np.concatenate(
            (
                previous_series.values[:correction_index],
                recalculated_series.values[correction_index:],
            )
        )
        combined_mask = np.concatenate(
            (
                previous_series.null_mask[:correction_index],
                recalculated_series.null_mask[correction_index:],
            )
        )
        np.testing.assert_array_equal(combined_values, recalculated_series.values)
        np.testing.assert_array_equal(combined_mask, recalculated_series.null_mask)


def test_result_rejects_positional_length_drift() -> None:
    result = calculate_moving_averages(_arrays())
    shorter = calculate_moving_averages(_arrays(_bars(30)))

    with pytest.raises(ValueError, match="source observation count"):
        replace(result, ema_12=shorter.ema_12)


def test_calculator_accepts_only_normalized_arrays() -> None:
    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_moving_averages(object())  # type: ignore[arg-type]
