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
    RsiAtrArrays,
    SourceBar,
    calculate_rsi_atr,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import rsi_atr as rsi_atr_module


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
PERIOD = 14


def _bars(observation_count: int = 300) -> tuple[SourceBar, ...]:
    first_date = date(2024, 1, 2)
    close = Decimal("100")
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


def _rsi_reference(close: np.ndarray) -> np.ndarray:
    result = np.full(len(close), np.nan, dtype=np.float64)
    if len(close) <= PERIOD:
        return result

    changes = np.diff(close)
    gain = sum(max(float(change), 0.0) for change in changes[:PERIOD]) / PERIOD
    loss = sum(max(-float(change), 0.0) for change in changes[:PERIOD]) / PERIOD

    def rsi_value(average_gain: float, average_loss: float) -> float:
        total = average_gain + average_loss
        return 0.0 if total == 0.0 else 100.0 * average_gain / total

    result[PERIOD] = rsi_value(gain, loss)
    for index in range(PERIOD + 1, len(close)):
        change = float(changes[index - 1])
        gain = (gain * (PERIOD - 1) + max(change, 0.0)) / PERIOD
        loss = (loss * (PERIOD - 1) + max(-change, 0.0)) / PERIOD
        result[index] = rsi_value(gain, loss)
    return result


def _atr_reference(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> np.ndarray:
    result = np.full(len(close), np.nan, dtype=np.float64)
    if len(close) <= PERIOD:
        return result

    true_range = np.full(len(close), np.nan, dtype=np.float64)
    for index in range(1, len(close)):
        true_range[index] = max(
            float(high[index] - low[index]),
            abs(float(high[index] - close[index - 1])),
            abs(float(low[index] - close[index - 1])),
        )
    atr = sum(float(value) for value in true_range[1 : PERIOD + 1]) / PERIOD
    result[PERIOD] = atr
    for index in range(PERIOD + 1, len(close)):
        atr = (atr * (PERIOD - 1) + true_range[index]) / PERIOD
        result[index] = atr
    return result


def _assert_reference(actual, expected: np.ndarray) -> None:
    expected_mask = np.isnan(expected)
    np.testing.assert_array_equal(actual.null_mask, expected_mask)
    np.testing.assert_allclose(
        actual.values[~expected_mask],
        expected[~expected_mask],
        atol=1e-12,
        rtol=1e-10,
    )


def test_rsi_atr_api_and_period_are_explicit() -> None:
    assert rsi_atr_module.__all__ == [
        "RSI_ATR_FIELDS",
        "RSI_ATR_PERIOD",
        "RsiAtrArrays",
        "calculate_rsi_atr",
    ]
    assert rsi_atr_module.RSI_ATR_PERIOD == 14
    assert rsi_atr_module.RSI_ATR_FIELDS == ("rsi_14", "atr_14")
    assert public_api.RsiAtrArrays is RsiAtrArrays
    assert public_api.calculate_rsi_atr is calculate_rsi_atr


def test_rsi_and_atr_match_independent_wilder_references() -> None:
    arrays = _arrays()
    result = calculate_rsi_atr(arrays)

    _assert_reference(result.rsi_14, _rsi_reference(arrays.close))
    _assert_reference(
        result.atr_14,
        _atr_reference(arrays.high, arrays.low, arrays.close),
    )
    assert result.rsi_14.value_at(13) is None
    assert result.atr_14.value_at(13) is None
    assert result.rsi_14.value_at(14) is not None
    assert result.atr_14.value_at(14) is not None


def test_short_history_is_null_through_the_wilder_seed() -> None:
    for observation_count in (1, 13, 14):
        result = calculate_rsi_atr(_arrays(_bars(observation_count)))

        assert result.observation_count == observation_count
        assert result.rsi_14.null_mask.all()
        assert result.atr_14.null_mask.all()


@pytest.mark.parametrize(
    ("step", "expected_rsi"),
    [
        (Decimal("1"), 100.0),
        (Decimal("-1"), 0.0),
        (Decimal("0"), 0.0),
    ],
)
def test_rsi_zero_guards_follow_pinned_talib_behavior(
    step: Decimal,
    expected_rsi: float,
) -> None:
    base = _bars(40)
    bars = tuple(
        replace(
            bar,
            open=Decimal("50") + step * index,
            high=Decimal("50") + step * index,
            low=Decimal("50") + step * index,
            close=Decimal("50") + step * index,
        )
        for index, bar in enumerate(base)
    )
    result = calculate_rsi_atr(_arrays(bars))

    np.testing.assert_array_equal(result.rsi_14.values[14:], expected_rsi)
    np.testing.assert_array_equal(result.atr_14.values[14:], abs(float(step)))


def test_provider_discontinuity_uses_true_range_and_calendar_gaps_add_no_rows() -> None:
    bars = list(_bars(40))
    index = 20
    discontinuous_close = bars[index - 1].close + Decimal("25")
    bars[index] = replace(
        bars[index],
        open=discontinuous_close,
        high=discontinuous_close + Decimal("1"),
        low=discontinuous_close - Decimal("1"),
        close=discontinuous_close,
    )
    arrays = _arrays(tuple(bars))
    result = calculate_rsi_atr(arrays)

    _assert_reference(
        result.atr_14,
        _atr_reference(arrays.high, arrays.low, arrays.close),
    )
    assert result.observation_count == 40
    assert arrays.trading_dates[1] - arrays.trading_dates[0] == timedelta(days=2)


def test_full_prefix_correction_replay_composes_with_suffix_write() -> None:
    bars = _bars()
    correction_index = 80
    corrected_close = bars[correction_index].close + Decimal("20")
    corrected_bar = replace(
        bars[correction_index],
        open=corrected_close,
        high=corrected_close + Decimal("3"),
        low=corrected_close - Decimal("4"),
        close=corrected_close,
    )
    corrected_bars = (
        *bars[:correction_index],
        corrected_bar,
        *bars[correction_index + 1 :],
    )
    previous = calculate_rsi_atr(_arrays(bars))
    recalculated = calculate_rsi_atr(_arrays(corrected_bars))

    for field_name in rsi_atr_module.RSI_ATR_FIELDS:
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
    prefix = calculate_rsi_atr(_arrays(bars[:split]))
    full = calculate_rsi_atr(_arrays(bars))

    for field_name in rsi_atr_module.RSI_ATR_FIELDS:
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


def test_result_and_calculator_reject_invalid_inputs() -> None:
    result = calculate_rsi_atr(_arrays())
    shorter = calculate_rsi_atr(_arrays(_bars(30)))

    with pytest.raises(ValueError, match="source observation count"):
        replace(result, atr_14=shorter.atr_14)
    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_rsi_atr(object())  # type: ignore[arg-type]
