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
    MovingAverageTrendArrays,
    SourceBar,
    TechIndicatorsCalculationError,
    calculate_moving_average_trends,
    calculate_moving_averages,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import moving_average_trends as trend_module
from empire_stonks_tech_indicators.models import PYTHON_FEATURE_FIELDS


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
OTHER_LISTING_ID = UUID("00000000-0000-4000-8000-000000000002")


def _bars(
    observation_count: int = 260,
    *,
    provider_listing_id: UUID = LISTING_ID,
) -> tuple[SourceBar, ...]:
    first_date = date(2024, 1, 2)
    result = []
    for index in range(observation_count):
        close = Decimal(index - 90) * Decimal("0.8")
        close += Decimal((index % 13) - 6) / Decimal("10")
        result.append(
            SourceBar(
                provider_listing_id=provider_listing_id,
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


def _calculate(
    arrays: CalculationArrays,
) -> tuple[MovingAverageArrays, MovingAverageTrendArrays]:
    moving_averages = calculate_moving_averages(arrays)
    return (
        moving_averages,
        calculate_moving_average_trends(arrays, moving_averages),
    )


def _distance_reference(
    numerator: MaskedFloatArray,
    denominator: MaskedFloatArray,
    *,
    lag: int = 0,
) -> np.ndarray:
    result = np.full(len(numerator.values), np.nan, dtype=np.float64)
    for index in range(lag, len(result)):
        denominator_index = index - lag
        if (
            numerator.null_mask[index]
            or denominator.null_mask[denominator_index]
            or denominator.values[denominator_index] == 0.0
        ):
            continue
        result[index] = (
            numerator.values[index] / denominator.values[denominator_index]
            - 1.0
        )
    return result


def _assert_reference(actual: MaskedFloatArray, expected: np.ndarray) -> None:
    expected_mask = np.isnan(expected)
    np.testing.assert_array_equal(actual.null_mask, expected_mask)
    np.testing.assert_allclose(
        actual.values[~expected_mask],
        expected[~expected_mask],
        atol=1e-12,
        rtol=1e-10,
    )


def test_trend_api_fields_and_persistence_ownership_are_explicit() -> None:
    assert trend_module.__all__ == [
        "MOVING_AVERAGE_CHANGE_FIELDS",
        "MOVING_AVERAGE_DISTANCE_REFERENCE_FIELDS",
        "MOVING_AVERAGE_TREND_FIELDS",
        "MovingAverageTrendArrays",
        "calculate_moving_average_trends",
    ]
    assert trend_module.MOVING_AVERAGE_CHANGE_FIELDS == (
        "sma_50_change_20d_pct",
        "sma_200_change_20d_pct",
    )
    assert trend_module.MOVING_AVERAGE_DISTANCE_REFERENCE_FIELDS == (
        "pct_sma_20",
        "pct_sma_50",
        "pct_sma_200",
        "pct_ema_20",
        "pct_ema_50",
        "pct_sma_20_vs_50",
        "pct_sma_20_vs_200",
        "pct_sma_50_vs_200",
    )
    assert set(trend_module.MOVING_AVERAGE_CHANGE_FIELDS) <= set(
        PYTHON_FEATURE_FIELDS
    )
    assert not set(
        trend_module.MOVING_AVERAGE_DISTANCE_REFERENCE_FIELDS
    ) & set(PYTHON_FEATURE_FIELDS)
    assert public_api.MovingAverageTrendArrays is MovingAverageTrendArrays
    assert (
        public_api.calculate_moving_average_trends
        is calculate_moving_average_trends
    )


def test_changes_and_generated_references_match_independent_formulas() -> None:
    arrays = _arrays()
    moving_averages, result = _calculate(arrays)
    false_mask = np.zeros(arrays.observation_count, dtype=np.bool_)
    false_mask.setflags(write=False)
    close = MaskedFloatArray(values=arrays.close, null_mask=false_mask)

    expected = {
        "sma_50_change_20d_pct": _distance_reference(
            moving_averages.sma_50,
            moving_averages.sma_50,
            lag=20,
        ),
        "sma_200_change_20d_pct": _distance_reference(
            moving_averages.sma_200,
            moving_averages.sma_200,
            lag=20,
        ),
        "pct_sma_20": _distance_reference(close, moving_averages.sma_20),
        "pct_sma_50": _distance_reference(close, moving_averages.sma_50),
        "pct_sma_200": _distance_reference(close, moving_averages.sma_200),
        "pct_ema_20": _distance_reference(close, moving_averages.ema_20),
        "pct_ema_50": _distance_reference(close, moving_averages.ema_50),
        "pct_sma_20_vs_50": _distance_reference(
            moving_averages.sma_20,
            moving_averages.sma_50,
        ),
        "pct_sma_20_vs_200": _distance_reference(
            moving_averages.sma_20,
            moving_averages.sma_200,
        ),
        "pct_sma_50_vs_200": _distance_reference(
            moving_averages.sma_50,
            moving_averages.sma_200,
        ),
    }
    for field_name, reference in expected.items():
        _assert_reference(getattr(result, field_name), reference)


@pytest.mark.parametrize(
    ("field_name", "first_valid_index"),
    [
        ("sma_50_change_20d_pct", 69),
        ("sma_200_change_20d_pct", 219),
        ("pct_sma_20", 19),
        ("pct_sma_50", 49),
        ("pct_sma_200", 199),
        ("pct_ema_20", 19),
        ("pct_ema_50", 49),
        ("pct_sma_20_vs_50", 49),
        ("pct_sma_20_vs_200", 199),
        ("pct_sma_50_vs_200", 199),
    ],
)
def test_each_field_has_the_frozen_first_valid_observation(
    field_name: str,
    first_valid_index: int,
) -> None:
    _, result = _calculate(_arrays())
    series = getattr(result, field_name)

    assert series.value_at(first_valid_index - 1) is None
    assert series.value_at(first_valid_index) is not None


def test_short_history_and_exact_zero_denominators_remain_null() -> None:
    short_arrays = _arrays(_bars(10))
    _, short_result = _calculate(short_arrays)
    assert short_result.observation_count == 10
    for field_name in trend_module.MOVING_AVERAGE_TREND_FIELDS:
        assert getattr(short_result, field_name).null_mask.all()

    zero_bars = tuple(
        replace(bar, open=Decimal(0), high=Decimal(0), low=Decimal(0), close=Decimal(0))
        for bar in _bars()
    )
    _, zero_result = _calculate(_arrays(zero_bars))
    for field_name in trend_module.MOVING_AVERAGE_TREND_FIELDS:
        assert getattr(zero_result, field_name).null_mask.all()


def test_append_prefix_is_unchanged_by_future_observations() -> None:
    bars = _bars()
    split = 225
    _, prefix = _calculate(_arrays(bars[:split]))
    _, full = _calculate(_arrays(bars))

    for field_name in trend_module.MOVING_AVERAGE_TREND_FIELDS:
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


def test_rejects_misaligned_or_tampered_moving_averages() -> None:
    arrays = _arrays()
    moving_averages = calculate_moving_averages(arrays)
    other_arrays = _arrays(_bars(provider_listing_id=OTHER_LISTING_ID))
    with pytest.raises(TechIndicatorsCalculationError, match="do not match"):
        calculate_moving_average_trends(other_arrays, moving_averages)

    changed_values = moving_averages.sma_50.values.copy()
    changed_values[100] += 1.0
    changed_values.setflags(write=False)
    tampered_sma = MaskedFloatArray(
        values=changed_values,
        null_mask=moving_averages.sma_50.null_mask,
    )
    tampered = replace(moving_averages, sma_50=tampered_sma)
    with pytest.raises(TechIndicatorsCalculationError, match="sma_50"):
        calculate_moving_average_trends(arrays, tampered)


def test_nonfinite_change_fails_calculation() -> None:
    bars = []
    for index in range(70):
        close = Decimal("1e-308") if index < 69 else Decimal("1e308")
        bars.append(
            SourceBar(
                provider_listing_id=LISTING_ID,
                trading_date=date(2025, 1, 1) + timedelta(days=index),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=Decimal(1),
            )
        )
    arrays = _arrays(tuple(bars))
    moving_averages = calculate_moving_averages(arrays)

    with pytest.raises(
        TechIndicatorsCalculationError,
        match="sma_50_change_20d_pct.*observation 69",
    ):
        calculate_moving_average_trends(arrays, moving_averages)


def test_result_and_calculator_reject_invalid_inputs() -> None:
    arrays = _arrays()
    moving_averages, result = _calculate(arrays)
    shorter_arrays = _arrays(_bars(30))
    _, shorter_result = _calculate(shorter_arrays)

    with pytest.raises(ValueError, match="source observation count"):
        replace(result, pct_sma_20=shorter_result.pct_sma_20)
    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_moving_average_trends(
            object(),  # type: ignore[arg-type]
            moving_averages,
        )
    with pytest.raises(TypeError, match="MovingAverageArrays"):
        calculate_moving_average_trends(
            arrays,
            object(),  # type: ignore[arg-type]
        )
