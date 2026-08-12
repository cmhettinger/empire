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
    MacdArrays,
    MaskedFloatArray,
    MovingAverageArrays,
    SourceBar,
    TechIndicatorsCalculationError,
    calculate_macd,
    calculate_moving_averages,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import macd as macd_module
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
        close = Decimal(index - 90) * Decimal("0.7")
        close += Decimal((index % 13) - 6) / Decimal("8")
        result.append(
            SourceBar(
                provider_listing_id=provider_listing_id,
                trading_date=first_date + timedelta(days=index * 2),
                open=close - Decimal("0.3"),
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
) -> tuple[MovingAverageArrays, MacdArrays]:
    moving_averages = calculate_moving_averages(arrays)
    return moving_averages, calculate_macd(arrays, moving_averages)


def _assert_talib_output(
    actual: MaskedFloatArray,
    expected: np.ndarray,
) -> None:
    expected_mask = ~np.isfinite(expected)
    np.testing.assert_array_equal(actual.null_mask, expected_mask)
    np.testing.assert_array_equal(
        actual.values[~expected_mask],
        expected[~expected_mask],
    )


def test_macd_api_profile_and_ownership_are_explicit() -> None:
    assert macd_module.__all__ == [
        "MACD_FAST_PERIOD",
        "MACD_FIELDS",
        "MACD_SIGNAL_PERIOD",
        "MACD_SLOW_PERIOD",
        "MacdArrays",
        "calculate_macd",
    ]
    assert (
        macd_module.MACD_FAST_PERIOD,
        macd_module.MACD_SLOW_PERIOD,
        macd_module.MACD_SIGNAL_PERIOD,
    ) == (12, 26, 9)
    assert macd_module.MACD_FIELDS == (
        "macd_12_26",
        "macd_signal_12_26_9",
        "macd_histogram_12_26_9",
        "macd_12_26_pct",
        "macd_histogram_12_26_9_pct",
    )
    assert set(macd_module.MACD_FIELDS[:3]) <= set(PYTHON_FEATURE_FIELDS)
    assert not set(macd_module.MACD_FIELDS[3:]) & set(PYTHON_FEATURE_FIELDS)
    assert public_api.MacdArrays is MacdArrays
    assert public_api.calculate_macd is calculate_macd


def test_raw_outputs_match_one_fixed_talib_macd_call() -> None:
    arrays = _arrays()
    _, result = _calculate(arrays)
    expected = talib.MACD(
        arrays.close,
        fastperiod=12,
        slowperiod=26,
        signalperiod=9,
    )

    for field_name, expected_values in zip(
        macd_module.MACD_FIELDS[:3],
        expected,
        strict=True,
    ):
        _assert_talib_output(getattr(result, field_name), expected_values)


def test_normalized_references_use_fixed_absolute_scales() -> None:
    arrays = _arrays()
    moving_averages, result = _calculate(arrays)
    populated = ~result.macd_12_26.null_mask

    np.testing.assert_array_equal(
        result.macd_12_26_pct.null_mask,
        result.macd_12_26.null_mask,
    )
    np.testing.assert_array_equal(
        result.macd_histogram_12_26_9_pct.null_mask,
        result.macd_histogram_12_26_9.null_mask,
    )
    np.testing.assert_allclose(
        result.macd_12_26_pct.values[populated],
        result.macd_12_26.values[populated]
        / np.abs(moving_averages.ema_26.values[populated]),
        atol=0.0,
        rtol=0.0,
    )
    np.testing.assert_allclose(
        result.macd_histogram_12_26_9_pct.values[populated],
        result.macd_histogram_12_26_9.values[populated]
        / np.abs(arrays.close[populated]),
        atol=0.0,
        rtol=0.0,
    )


def test_shared_warmup_begins_at_observation_33() -> None:
    for observation_count in (1, 25, 33):
        _, result = _calculate(_arrays(_bars(observation_count)))
        for field_name in macd_module.MACD_FIELDS:
            assert getattr(result, field_name).null_mask.all()

    _, result = _calculate(_arrays(_bars(34)))
    for field_name in macd_module.MACD_FIELDS:
        series = getattr(result, field_name)
        assert series.value_at(32) is None
        assert series.value_at(33) is not None


@pytest.mark.parametrize("close", [Decimal("50"), Decimal("-50")])
def test_flat_nonzero_close_produces_populated_normalized_zeros(
    close: Decimal,
) -> None:
    bars = tuple(
        replace(bar, open=close, high=close, low=close, close=close)
        for bar in _bars(50)
    )
    _, result = _calculate(_arrays(bars))

    for field_name in macd_module.MACD_FIELDS:
        assert getattr(result, field_name).value_at(33) == 0.0


def test_exact_zero_scales_leave_normalized_values_null() -> None:
    zero = Decimal("0")
    bars = tuple(
        replace(bar, open=zero, high=zero, low=zero, close=zero)
        for bar in _bars(50)
    )
    _, result = _calculate(_arrays(bars))

    for field_name in macd_module.MACD_FIELDS[:3]:
        assert getattr(result, field_name).value_at(33) == 0.0
    assert result.macd_12_26_pct.value_at(33) is None
    assert result.macd_histogram_12_26_9_pct.value_at(33) is None


def test_macd_line_is_not_reconstructed_from_stored_emas() -> None:
    arrays = _arrays()
    moving_averages, result = _calculate(arrays)
    reconstructed = moving_averages.ema_12.values - moving_averages.ema_26.values

    assert result.macd_12_26.null_mask[25:33].all()
    assert not moving_averages.ema_12.null_mask[25:33].any()
    assert not moving_averages.ema_26.null_mask[25:33].any()
    populated = ~result.macd_12_26.null_mask
    assert np.any(result.macd_12_26.values[populated] != reconstructed[populated])


def test_append_prefix_is_unchanged_by_future_observations() -> None:
    bars = _bars()
    split = 175
    _, prefix = _calculate(_arrays(bars[:split]))
    _, full = _calculate(_arrays(bars))

    for field_name in macd_module.MACD_FIELDS:
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


def test_correction_recalculation_supports_affected_suffix_writes() -> None:
    bars = _bars()
    correction_index = 80
    corrected_close = bars[correction_index].close + Decimal("7")
    corrected_bar = replace(
        bars[correction_index],
        open=corrected_close,
        high=corrected_close + Decimal("2"),
        low=corrected_close - Decimal("2"),
        close=corrected_close,
    )
    corrected_bars = (
        *bars[:correction_index],
        corrected_bar,
        *bars[correction_index + 1 :],
    )
    _, previous = _calculate(_arrays(bars))
    _, recalculated = _calculate(_arrays(corrected_bars))

    for field_name in macd_module.MACD_FIELDS:
        old = getattr(previous, field_name)
        new = getattr(recalculated, field_name)
        combined_values = np.concatenate(
            (old.values[:correction_index], new.values[correction_index:])
        )
        combined_mask = np.concatenate(
            (old.null_mask[:correction_index], new.null_mask[correction_index:])
        )
        np.testing.assert_array_equal(combined_values, new.values)
        np.testing.assert_array_equal(combined_mask, new.null_mask)
        populated = ~old.null_mask[correction_index:]
        populated &= ~new.null_mask[correction_index:]
        assert np.any(
            old.values[correction_index:][populated]
            != new.values[correction_index:][populated]
        )


def test_rejects_misaligned_or_tampered_ema_26() -> None:
    arrays = _arrays()
    moving_averages = calculate_moving_averages(arrays)
    other_arrays = _arrays(_bars(provider_listing_id=OTHER_LISTING_ID))
    with pytest.raises(TechIndicatorsCalculationError, match="do not match"):
        calculate_macd(other_arrays, moving_averages)

    changed_values = moving_averages.ema_26.values.copy()
    changed_values[100] += 1.0
    changed_values.setflags(write=False)
    tampered_ema = MaskedFloatArray(
        values=changed_values,
        null_mask=moving_averages.ema_26.null_mask,
    )
    tampered = replace(moving_averages, ema_26=tampered_ema)
    with pytest.raises(TechIndicatorsCalculationError, match="ema_26"):
        calculate_macd(arrays, tampered)


def test_result_and_calculator_reject_invalid_inputs() -> None:
    arrays = _arrays()
    moving_averages, result = _calculate(arrays)
    _, shorter = _calculate(_arrays(_bars(40)))

    with pytest.raises(ValueError, match="source observation count"):
        replace(result, macd_12_26=shorter.macd_12_26)
    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_macd(object(), moving_averages)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="MovingAverageArrays"):
        calculate_macd(arrays, object())  # type: ignore[arg-type]
