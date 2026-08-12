from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest
import talib

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    CalculationArrays,
    DirectionalMovementArrays,
    SourceBar,
    TechIndicatorsCalculationError,
    calculate_directional_movement,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import directional_movement as dm_module


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
PERIOD = 14


def _bars(observation_count: int = 300) -> tuple[SourceBar, ...]:
    first_date = date(2024, 1, 2)
    close = Decimal("-40")
    result = []
    for index in range(observation_count):
        if index:
            close += Decimal(((index * 17) % 15) - 7) / Decimal("4")
        high_offset = Decimal((index % 5) + 1) / Decimal("2")
        low_offset = Decimal((index % 7) + 1) / Decimal("3")
        result.append(
            SourceBar(
                provider_listing_id=LISTING_ID,
                trading_date=first_date + timedelta(days=index * 2),
                open=close,
                high=close + high_offset,
                low=close - low_offset,
                close=close,
                volume=Decimal("1000") + index,
            )
        )
    return tuple(result)


def _arrays(bars: tuple[SourceBar, ...] | None = None) -> CalculationArrays:
    return normalize_source_bars(_bars() if bars is None else bars)


def _directional_reference(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    observation_count = len(close)
    plus_dm = np.zeros(observation_count, dtype=np.float64)
    minus_dm = np.zeros(observation_count, dtype=np.float64)
    true_range = np.zeros(observation_count, dtype=np.float64)
    for index in range(1, observation_count):
        plus_delta = float(high[index] - high[index - 1])
        minus_delta = float(low[index - 1] - low[index])
        if minus_delta > 0.0 and plus_delta < minus_delta:
            minus_dm[index] = minus_delta
        elif plus_delta > 0.0 and plus_delta > minus_delta:
            plus_dm[index] = plus_delta
        true_range[index] = max(
            float(high[index] - low[index]),
            abs(float(high[index] - close[index - 1])),
            abs(float(low[index] - close[index - 1])),
        )

    plus_di = np.full(observation_count, np.nan, dtype=np.float64)
    minus_di = np.full(observation_count, np.nan, dtype=np.float64)
    adx = np.full(observation_count, np.nan, dtype=np.float64)
    if observation_count <= PERIOD:
        return plus_di, minus_di, adx

    smoothed_plus_dm = sum(float(value) for value in plus_dm[1:PERIOD])
    smoothed_minus_dm = sum(float(value) for value in minus_dm[1:PERIOD])
    smoothed_true_range = sum(
        float(value) for value in true_range[1:PERIOD]
    )
    dx_values: list[float] = []
    previous_adx: float | None = None
    for index in range(PERIOD, observation_count):
        smoothed_plus_dm -= smoothed_plus_dm / PERIOD
        smoothed_plus_dm += plus_dm[index]
        smoothed_minus_dm -= smoothed_minus_dm / PERIOD
        smoothed_minus_dm += minus_dm[index]
        smoothed_true_range -= smoothed_true_range / PERIOD
        smoothed_true_range += true_range[index]

        if smoothed_true_range == 0.0:
            current_plus_di = 0.0
            current_minus_di = 0.0
        else:
            current_plus_di = 100.0 * (
                smoothed_plus_dm / smoothed_true_range
            )
            current_minus_di = 100.0 * (
                smoothed_minus_dm / smoothed_true_range
            )
        plus_di[index] = current_plus_di
        minus_di[index] = current_minus_di

        di_sum = current_plus_di + current_minus_di
        dx = (
            0.0
            if di_sum == 0.0
            else 100.0 * abs(current_minus_di - current_plus_di) / di_sum
        )
        if index <= (2 * PERIOD) - 1:
            dx_values.append(dx)
        if index == (2 * PERIOD) - 1:
            previous_adx = sum(dx_values) / PERIOD
            adx[index] = previous_adx
        elif index > (2 * PERIOD) - 1:
            assert previous_adx is not None
            if smoothed_true_range != 0.0 and di_sum != 0.0:
                previous_adx = (
                    previous_adx * (PERIOD - 1) + dx
                ) / PERIOD
            adx[index] = previous_adx
    return plus_di, minus_di, adx


def _assert_reference(actual, expected: np.ndarray) -> None:
    expected_mask = np.isnan(expected)
    np.testing.assert_array_equal(actual.null_mask, expected_mask)
    np.testing.assert_allclose(
        actual.values[~expected_mask],
        expected[~expected_mask],
        atol=1e-12,
        rtol=1e-10,
    )


def test_directional_movement_api_and_period_are_explicit() -> None:
    assert dm_module.__all__ == [
        "DIRECTIONAL_MOVEMENT_FIELDS",
        "DIRECTIONAL_MOVEMENT_PERIOD",
        "DirectionalMovementArrays",
        "calculate_directional_movement",
    ]
    assert dm_module.DIRECTIONAL_MOVEMENT_PERIOD == 14
    assert dm_module.DIRECTIONAL_MOVEMENT_FIELDS == (
        "plus_di_14",
        "minus_di_14",
        "adx_14",
    )
    assert public_api.DirectionalMovementArrays is DirectionalMovementArrays
    assert (
        public_api.calculate_directional_movement
        is calculate_directional_movement
    )


def test_dmi_and_adx_match_independent_wilder_reference() -> None:
    arrays = _arrays()
    result = calculate_directional_movement(arrays)
    expected_plus, expected_minus, expected_adx = _directional_reference(
        arrays.high,
        arrays.low,
        arrays.close,
    )

    _assert_reference(result.plus_di_14, expected_plus)
    _assert_reference(result.minus_di_14, expected_minus)
    _assert_reference(result.adx_14, expected_adx)
    assert np.all((result.plus_di_14.values[14:] >= 0.0))
    assert np.all((result.plus_di_14.values[14:] <= 100.0))
    assert np.all((result.minus_di_14.values[14:] >= 0.0))
    assert np.all((result.minus_di_14.values[14:] <= 100.0))
    assert np.all((result.adx_14.values[27:] >= 0.0))
    assert np.all((result.adx_14.values[27:] <= 100.0))


def test_frozen_warmup_boundaries() -> None:
    result = calculate_directional_movement(_arrays())

    assert result.plus_di_14.value_at(13) is None
    assert result.minus_di_14.value_at(13) is None
    assert result.plus_di_14.value_at(14) is not None
    assert result.minus_di_14.value_at(14) is not None
    assert result.adx_14.value_at(26) is None
    assert result.adx_14.value_at(27) is not None

    short = calculate_directional_movement(_arrays(_bars(14)))
    for field_name in dm_module.DIRECTIONAL_MOVEMENT_FIELDS:
        assert getattr(short, field_name).null_mask.all()


@pytest.mark.parametrize(
    ("step", "expected_plus", "expected_minus", "expected_adx"),
    [
        (Decimal("1"), 100.0, 0.0, 100.0),
        (Decimal("-1"), 0.0, 100.0, 100.0),
        (Decimal("0"), 0.0, 0.0, 0.0),
    ],
)
def test_direction_and_zero_guards(
    step: Decimal,
    expected_plus: float,
    expected_minus: float,
    expected_adx: float,
) -> None:
    bars = tuple(
        replace(
            bar,
            open=Decimal("50") + step * index,
            high=Decimal("50") + step * index,
            low=Decimal("50") + step * index,
            close=Decimal("50") + step * index,
        )
        for index, bar in enumerate(_bars(50))
    )
    result = calculate_directional_movement(_arrays(bars))

    np.testing.assert_array_equal(result.plus_di_14.values[14:], expected_plus)
    np.testing.assert_array_equal(result.minus_di_14.values[14:], expected_minus)
    np.testing.assert_array_equal(result.adx_14.values[27:], expected_adx)


def test_equal_outside_range_moves_select_neither_direction() -> None:
    bars = []
    for index in range(40):
        high = Decimal("100") + index
        low = Decimal("100") - index
        bars.append(
            SourceBar(
                provider_listing_id=LISTING_ID,
                trading_date=date(2025, 1, 1) + timedelta(days=index),
                open=Decimal("100"),
                high=high,
                low=low,
                close=Decimal("100"),
                volume=Decimal("1000"),
            )
        )
    result = calculate_directional_movement(_arrays(tuple(bars)))

    np.testing.assert_array_equal(result.plus_di_14.values[14:], 0.0)
    np.testing.assert_array_equal(result.minus_di_14.values[14:], 0.0)
    np.testing.assert_array_equal(result.adx_14.values[27:], 0.0)


def test_full_prefix_correction_replay_composes_with_suffix_write() -> None:
    bars = _bars()
    correction_index = 80
    corrected_close = bars[correction_index].close + Decimal("20")
    corrected_bar = replace(
        bars[correction_index],
        open=corrected_close,
        high=corrected_close + Decimal("4"),
        low=corrected_close - Decimal("3"),
        close=corrected_close,
    )
    corrected_bars = (
        *bars[:correction_index],
        corrected_bar,
        *bars[correction_index + 1 :],
    )
    previous = calculate_directional_movement(_arrays(bars))
    recalculated = calculate_directional_movement(_arrays(corrected_bars))

    for field_name in dm_module.DIRECTIONAL_MOVEMENT_FIELDS:
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
        assert not np.array_equal(
            previous_series.values[correction_index:],
            recalculated_series.values[correction_index:],
        )


def test_append_prefix_is_unchanged_by_future_observations() -> None:
    bars = _bars()
    split = 225
    prefix = calculate_directional_movement(_arrays(bars[:split]))
    full = calculate_directional_movement(_arrays(bars))

    for field_name in dm_module.DIRECTIONAL_MOVEMENT_FIELDS:
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


def test_nonzero_unstable_period_fails_closed() -> None:
    try:
        talib.set_unstable_period("ADX", 1)
        with pytest.raises(TechIndicatorsCalculationError, match="unstable"):
            calculate_directional_movement(_arrays())
    finally:
        talib.set_unstable_period("ADX", 0)


def test_result_and_calculator_reject_invalid_inputs() -> None:
    result = calculate_directional_movement(_arrays())
    shorter = calculate_directional_movement(_arrays(_bars(40)))

    with pytest.raises(ValueError, match="source observation count"):
        replace(result, adx_14=shorter.adx_14)
    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_directional_movement(object())  # type: ignore[arg-type]
