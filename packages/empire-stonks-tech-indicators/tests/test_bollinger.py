from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    BollingerStateArrays,
    CalculationArrays,
    MaskedFloatArray,
    MovingAverageArrays,
    SourceBar,
    TechIndicatorsCalculationError,
    calculate_bollinger_state,
    calculate_moving_averages,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import bollinger as bollinger_module
from empire_stonks_tech_indicators.models import PYTHON_FEATURE_FIELDS


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
OTHER_LISTING_ID = UUID("00000000-0000-4000-8000-000000000002")
PERIOD = 20


def _bars(
    observation_count: int = 260,
    *,
    provider_listing_id: UUID = LISTING_ID,
) -> tuple[SourceBar, ...]:
    first_date = date(2024, 1, 2)
    result = []
    for index in range(observation_count):
        close = Decimal(index - 100) * Decimal("0.6")
        close += Decimal((index % 9) - 4) / Decimal("5")
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
) -> tuple[MovingAverageArrays, BollingerStateArrays]:
    moving_averages = calculate_moving_averages(arrays)
    return (
        moving_averages,
        calculate_bollinger_state(arrays, moving_averages),
    )


def _population_stddev_reference(close: np.ndarray) -> np.ndarray:
    result = np.full(len(close), np.nan, dtype=np.float64)
    for index in range(PERIOD - 1, len(close)):
        window = [
            float(value) for value in close[index - PERIOD + 1 : index + 1]
        ]
        mean = sum(window) / PERIOD
        variance = sum((value - mean) ** 2 for value in window) / PERIOD
        result[index] = variance**0.5
    return result


def _generated_references(
    close: np.ndarray,
    sma_20: MaskedFloatArray,
    stddev: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    percent_b = np.full(len(close), np.nan, dtype=np.float64)
    bandwidth = np.full(len(close), np.nan, dtype=np.float64)
    for index in range(len(close)):
        if sma_20.null_mask[index] or np.isnan(stddev[index]):
            continue
        upper = sma_20.values[index] + 2.0 * stddev[index]
        lower = sma_20.values[index] - 2.0 * stddev[index]
        width = upper - lower
        if width != 0.0:
            percent_b[index] = (close[index] - lower) / width
        if abs(sma_20.values[index]) != 0.0:
            bandwidth[index] = width / abs(sma_20.values[index])
    return percent_b, bandwidth


def _assert_reference(actual: MaskedFloatArray, expected: np.ndarray) -> None:
    expected_mask = np.isnan(expected)
    np.testing.assert_array_equal(actual.null_mask, expected_mask)
    np.testing.assert_allclose(
        actual.values[~expected_mask],
        expected[~expected_mask],
        atol=1e-12,
        rtol=1e-10,
    )


def test_bollinger_api_profile_and_ownership_are_explicit() -> None:
    assert bollinger_module.__all__ == [
        "BOLLINGER_DEVIATIONS",
        "BOLLINGER_FIELDS",
        "BOLLINGER_PERIOD",
        "BollingerStateArrays",
        "calculate_bollinger_state",
    ]
    assert bollinger_module.BOLLINGER_PERIOD == 20
    assert bollinger_module.BOLLINGER_DEVIATIONS == 2.0
    assert bollinger_module.BOLLINGER_FIELDS == (
        "price_stddev_20",
        "bollinger_percent_b_20_2",
        "bollinger_bandwidth_20_2",
    )
    assert "price_stddev_20" in PYTHON_FEATURE_FIELDS
    assert "bollinger_percent_b_20_2" not in PYTHON_FEATURE_FIELDS
    assert "bollinger_bandwidth_20_2" not in PYTHON_FEATURE_FIELDS
    assert public_api.BollingerStateArrays is BollingerStateArrays
    assert public_api.calculate_bollinger_state is calculate_bollinger_state


def test_stddev_percent_b_and_bandwidth_match_independent_formulas() -> None:
    arrays = _arrays()
    moving_averages, result = _calculate(arrays)
    stddev = _population_stddev_reference(arrays.close)
    percent_b, bandwidth = _generated_references(
        arrays.close,
        moving_averages.sma_20,
        stddev,
    )

    _assert_reference(result.price_stddev_20, stddev)
    _assert_reference(result.bollinger_percent_b_20_2, percent_b)
    _assert_reference(result.bollinger_bandwidth_20_2, bandwidth)


def test_warmup_uses_one_complete_twenty_observation_window() -> None:
    for observation_count in (1, 19):
        _, result = _calculate(_arrays(_bars(observation_count)))
        for field_name in bollinger_module.BOLLINGER_FIELDS:
            assert getattr(result, field_name).null_mask.all()

    _, result = _calculate(_arrays(_bars(20)))
    for field_name in bollinger_module.BOLLINGER_FIELDS:
        assert getattr(result, field_name).value_at(18) is None
        assert getattr(result, field_name).value_at(19) is not None


@pytest.mark.parametrize(
    ("close", "percent_b_is_null", "bandwidth_is_null"),
    [
        (Decimal("50"), True, False),
        (Decimal("-50"), True, False),
        (Decimal("0"), True, True),
    ],
)
def test_flat_band_zero_and_middle_zero_rules(
    close: Decimal,
    percent_b_is_null: bool,
    bandwidth_is_null: bool,
) -> None:
    bars = tuple(
        replace(bar, open=close, high=close, low=close, close=close)
        for bar in _bars(30)
    )
    _, result = _calculate(_arrays(bars))

    assert result.price_stddev_20.value_at(19) == 0.0
    assert bool(
        result.bollinger_percent_b_20_2.null_mask[19]
    ) is percent_b_is_null
    assert bool(
        result.bollinger_bandwidth_20_2.null_mask[19]
    ) is bandwidth_is_null
    if not bandwidth_is_null:
        assert result.bollinger_bandwidth_20_2.value_at(19) == 0.0


def test_upper_and_lower_bands_are_not_retained() -> None:
    _, result = _calculate(_arrays())

    assert not hasattr(result, "upper_20_2")
    assert not hasattr(result, "lower_20_2")
    assert not any("upper" in field or "lower" in field for field in result.__dict__)


def test_append_prefix_is_unchanged_by_future_observations() -> None:
    bars = _bars()
    split = 175
    _, prefix = _calculate(_arrays(bars[:split]))
    _, full = _calculate(_arrays(bars))

    for field_name in bollinger_module.BOLLINGER_FIELDS:
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


def test_rejects_misaligned_or_tampered_sma_20() -> None:
    arrays = _arrays()
    moving_averages = calculate_moving_averages(arrays)
    other_arrays = _arrays(_bars(provider_listing_id=OTHER_LISTING_ID))
    with pytest.raises(TechIndicatorsCalculationError, match="do not match"):
        calculate_bollinger_state(other_arrays, moving_averages)

    changed_values = moving_averages.sma_20.values.copy()
    changed_values[100] += 1.0
    changed_values.setflags(write=False)
    tampered_sma = MaskedFloatArray(
        values=changed_values,
        null_mask=moving_averages.sma_20.null_mask,
    )
    tampered = replace(moving_averages, sma_20=tampered_sma)
    with pytest.raises(TechIndicatorsCalculationError, match="sma_20"):
        calculate_bollinger_state(arrays, tampered)


def test_result_and_calculator_reject_invalid_inputs() -> None:
    arrays = _arrays()
    moving_averages, result = _calculate(arrays)
    _, shorter = _calculate(_arrays(_bars(30)))

    with pytest.raises(ValueError, match="source observation count"):
        replace(result, price_stddev_20=shorter.price_stddev_20)
    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_bollinger_state(
            object(),  # type: ignore[arg-type]
            moving_averages,
        )
    with pytest.raises(TypeError, match="MovingAverageArrays"):
        calculate_bollinger_state(
            arrays,
            object(),  # type: ignore[arg-type]
        )
