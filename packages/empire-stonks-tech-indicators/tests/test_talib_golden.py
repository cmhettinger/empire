from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from empire_stonks_tech_indicators import (
    SourceBar,
    TALibAdapter,
    calculate_bollinger_state,
    calculate_directional_movement,
    calculate_macd,
    calculate_moving_average_trends,
    calculate_moving_averages,
    calculate_rsi_atr,
    normalize_source_bars,
)


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
ABSOLUTE_TOLERANCE = 1e-12
RELATIVE_TOLERANCE = 1e-10
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "talib_features_v1.json"
RAW_TALIB_FIELDS = (
    "sma_20",
    "sma_50",
    "sma_200",
    "ema_12",
    "ema_20",
    "ema_26",
    "ema_50",
    "rsi_14",
    "atr_14",
    "price_stddev_20",
    "plus_di_14",
    "minus_di_14",
    "adx_14",
    "macd_12_26",
    "macd_signal_12_26_9",
    "macd_histogram_12_26_9",
)
REFERENCE_FIELDS = (
    *RAW_TALIB_FIELDS[:7],
    "sma_50_change_20d_pct",
    "sma_200_change_20d_pct",
    "pct_sma_20",
    "pct_sma_50",
    "pct_sma_200",
    "pct_ema_20",
    "pct_ema_50",
    "pct_sma_20_vs_50",
    "pct_sma_20_vs_200",
    "pct_sma_50_vs_200",
    *RAW_TALIB_FIELDS[7:10],
    "bollinger_percent_b_20_2",
    "bollinger_bandwidth_20_2",
    *RAW_TALIB_FIELDS[10:],
    "macd_12_26_pct",
    "macd_histogram_12_26_9_pct",
)


def _decimal(value: float | int) -> Decimal:
    return Decimal(str(value))


def _source_bar(
    *,
    trading_date: date,
    open_value: float,
    high: float,
    low: float,
    close: float,
) -> SourceBar:
    return SourceBar(
        provider_listing_id=LISTING_ID,
        trading_date=trading_date,
        open=_decimal(open_value),
        high=_decimal(high),
        low=_decimal(low),
        close=_decimal(close),
        volume=Decimal("1000"),
    )


def _next_business_day(value: date) -> date:
    result = value + timedelta(days=1)
    while result.weekday() >= 5:
        result += timedelta(days=1)
    return result


def _fixture_bars(case: dict[str, Any]) -> tuple[SourceBar, ...]:
    generator = case["generator"]
    current_date = date.fromisoformat(generator["start_date"])
    bars = []
    for index in range(generator["observations"]):
        if index:
            current_date = (
                _next_business_day(current_date)
                if generator.get("business_days", False)
                else current_date + timedelta(days=1)
            )
        if index == generator.get("gap_before_index"):
            current_date += timedelta(days=generator["gap_days"])
        close = generator.get("close_start", 100.0)
        close += index * generator.get("close_step", 1.0)
        if index >= generator.get("split_index", generator["observations"]):
            close *= generator["split_factor"]
        bars.append(
            _source_bar(
                trading_date=current_date,
                open_value=close + generator["open_offset"],
                high=close + generator["high_offset"],
                low=close + generator["low_offset"],
                close=close,
            )
        )
    return tuple(bars)


def _random_bars(
    *,
    seed: int,
    count: int,
    initial_close: float,
) -> tuple[SourceBar, ...]:
    generator = random.Random(seed)
    current_date = date(2018, 1, 2)
    close = initial_close
    bars = []
    for index in range(count):
        if index:
            current_date += timedelta(days=generator.randint(1, 4))
            close += generator.uniform(-4.0, 4.0)
        if index in (83, 211):
            close *= 0.45
        close = round(close, 6)
        open_value = round(close + generator.uniform(-1.5, 1.5), 6)
        spread = round(generator.uniform(0.05, 3.0), 6)
        high = round(max(open_value, close) + spread, 6)
        low = round(min(open_value, close) - spread, 6)
        bars.append(
            _source_bar(
                trading_date=current_date,
                open_value=open_value,
                high=high,
                low=low,
                close=close,
            )
        )
    return tuple(bars)


def _flat_bars(close: float, count: int = 260) -> tuple[SourceBar, ...]:
    return tuple(
        _source_bar(
            trading_date=date(2020, 1, 1) + timedelta(days=index * 2),
            open_value=close,
            high=close,
            low=close,
            close=close,
        )
        for index in range(count)
    )


def _calculate_all(bars: tuple[SourceBar, ...]) -> dict[str, Any]:
    arrays = normalize_source_bars(bars)
    moving = calculate_moving_averages(arrays)
    trends = calculate_moving_average_trends(arrays, moving)
    rsi_atr = calculate_rsi_atr(arrays)
    bollinger = calculate_bollinger_state(arrays, moving)
    directional = calculate_directional_movement(arrays)
    macd = calculate_macd(arrays, moving)
    owners = (moving, trends, rsi_atr, bollinger, directional, macd)
    result = {}
    for field_name in REFERENCE_FIELDS:
        matching = [owner for owner in owners if hasattr(owner, field_name)]
        assert len(matching) == 1
        result[field_name] = getattr(matching[0], field_name)
    return result


def _sma(source: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(source)
    for index in range(period - 1, len(source)):
        result[index] = sum(source[index - period + 1 : index + 1]) / period
    return result


def _ema(source: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(source)
    if len(source) < period:
        return result
    seed_index = period - 1
    current = sum(source[:period]) / period
    result[seed_index] = current
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(source)):
        current = (source[index] - current) * alpha + current
        result[index] = current
    return result


def _distance(
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    if numerator is None or denominator is None or denominator == 0.0:
        return None
    return numerator / denominator - 1.0


def _rsi(close: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = [None] * len(close)
    if len(close) <= period:
        return result
    changes = [close[index] - close[index - 1] for index in range(1, len(close))]
    gain = sum(max(change, 0.0) for change in changes[:period]) / period
    loss = sum(max(-change, 0.0) for change in changes[:period]) / period
    for index in range(period, len(close)):
        if index > period:
            change = changes[index - 1]
            gain = (gain * (period - 1) + max(change, 0.0)) / period
            loss = (loss * (period - 1) + max(-change, 0.0)) / period
        total = gain + loss
        result[index] = 0.0 if total == 0.0 else 100.0 * gain / total
    return result


def _true_ranges(
    high: list[float],
    low: list[float],
    close: list[float],
) -> list[float]:
    result = [0.0] * len(close)
    for index in range(1, len(close)):
        result[index] = max(
            high[index] - low[index],
            abs(high[index] - close[index - 1]),
            abs(low[index] - close[index - 1]),
        )
    return result


def _atr(
    high: list[float],
    low: list[float],
    close: list[float],
    period: int = 14,
) -> list[float | None]:
    result: list[float | None] = [None] * len(close)
    if len(close) <= period:
        return result
    true_range = _true_ranges(high, low, close)
    current = sum(true_range[1 : period + 1]) / period
    result[period] = current
    for index in range(period + 1, len(close)):
        current = (current * (period - 1) + true_range[index]) / period
        result[index] = current
    return result


def _directional_movement(
    high: list[float],
    low: list[float],
    close: list[float],
    period: int = 14,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    count = len(close)
    plus_dm = [0.0] * count
    minus_dm = [0.0] * count
    true_range = _true_ranges(high, low, close)
    for index in range(1, count):
        plus_delta = high[index] - high[index - 1]
        minus_delta = low[index - 1] - low[index]
        if minus_delta > 0.0 and plus_delta < minus_delta:
            minus_dm[index] = minus_delta
        elif plus_delta > 0.0 and plus_delta > minus_delta:
            plus_dm[index] = plus_delta

    plus_di: list[float | None] = [None] * count
    minus_di: list[float | None] = [None] * count
    adx: list[float | None] = [None] * count
    if count <= period:
        return plus_di, minus_di, adx
    smooth_plus = sum(plus_dm[1:period])
    smooth_minus = sum(minus_dm[1:period])
    smooth_range = sum(true_range[1:period])
    dx_values = []
    previous_adx = None
    for index in range(period, count):
        smooth_plus += plus_dm[index] - smooth_plus / period
        smooth_minus += minus_dm[index] - smooth_minus / period
        smooth_range += true_range[index] - smooth_range / period
        current_plus = (
            0.0 if smooth_range == 0.0 else 100.0 * smooth_plus / smooth_range
        )
        current_minus = (
            0.0 if smooth_range == 0.0 else 100.0 * smooth_minus / smooth_range
        )
        plus_di[index] = current_plus
        minus_di[index] = current_minus
        di_sum = current_plus + current_minus
        dx = (
            0.0
            if di_sum == 0.0
            else 100.0 * abs(current_minus - current_plus) / di_sum
        )
        if index <= (2 * period) - 1:
            dx_values.append(dx)
        if index == (2 * period) - 1:
            previous_adx = sum(dx_values) / period
            adx[index] = previous_adx
        elif index > (2 * period) - 1:
            assert previous_adx is not None
            if smooth_range != 0.0 and di_sum != 0.0:
                previous_adx = (previous_adx * (period - 1) + dx) / period
            adx[index] = previous_adx
    return plus_di, minus_di, adx


def _macd(
    close: list[float],
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    count = len(close)
    line: list[float | None] = [None] * count
    signal: list[float | None] = [None] * count
    histogram: list[float | None] = [None] * count
    if count < 34:
        return line, signal, histogram
    slow = sum(close[:26]) / 26
    fast = sum(close[14:26]) / 12
    internal_line = [fast - slow]
    for index in range(26, count):
        slow = (close[index] - slow) * (2.0 / 27.0) + slow
        fast = (close[index] - fast) * (2.0 / 13.0) + fast
        internal_line.append(fast - slow)
    current_signal = sum(internal_line[:9]) / 9
    for index in range(33, count):
        current_line = internal_line[index - 25]
        if index > 33:
            current_signal = (current_line - current_signal) * 0.2 + current_signal
        line[index] = current_line
        signal[index] = current_signal
        histogram[index] = current_line - current_signal
    return line, signal, histogram


def _independent_reference(
    bars: tuple[SourceBar, ...],
) -> dict[str, list[float | None]]:
    high = [float(bar.high) for bar in bars]
    low = [float(bar.low) for bar in bars]
    close = [float(bar.close) for bar in bars]
    count = len(close)
    result = {}
    for period in (20, 50, 200):
        result[f"sma_{period}"] = _sma(close, period)
    for period in (12, 20, 26, 50):
        result[f"ema_{period}"] = _ema(close, period)

    result["sma_50_change_20d_pct"] = [
        _distance(result["sma_50"][index], result["sma_50"][index - 20])
        if index >= 20
        else None
        for index in range(count)
    ]
    result["sma_200_change_20d_pct"] = [
        _distance(result["sma_200"][index], result["sma_200"][index - 20])
        if index >= 20
        else None
        for index in range(count)
    ]
    for period in (20, 50, 200):
        result[f"pct_sma_{period}"] = [
            _distance(close[index], result[f"sma_{period}"][index])
            for index in range(count)
        ]
    for period in (20, 50):
        result[f"pct_ema_{period}"] = [
            _distance(close[index], result[f"ema_{period}"][index])
            for index in range(count)
        ]
    for short, long in ((20, 50), (20, 200), (50, 200)):
        result[f"pct_sma_{short}_vs_{long}"] = [
            _distance(result[f"sma_{short}"][index], result[f"sma_{long}"][index])
            for index in range(count)
        ]

    result["rsi_14"] = _rsi(close)
    result["atr_14"] = _atr(high, low, close)
    stddev: list[float | None] = [None] * count
    for index in range(19, count):
        window = close[index - 19 : index + 1]
        average = sum(window) / 20
        stddev[index] = math.sqrt(sum((value - average) ** 2 for value in window) / 20)
    result["price_stddev_20"] = stddev
    result["bollinger_percent_b_20_2"] = [None] * count
    result["bollinger_bandwidth_20_2"] = [None] * count
    for index in range(count):
        middle = result["sma_20"][index]
        deviation = stddev[index]
        if middle is None or deviation is None:
            continue
        width = 4.0 * deviation
        if width != 0.0:
            lower = middle - 2.0 * deviation
            result["bollinger_percent_b_20_2"][index] = (close[index] - lower) / width
        if abs(middle) != 0.0:
            result["bollinger_bandwidth_20_2"][index] = width / abs(middle)

    plus_di, minus_di, adx = _directional_movement(high, low, close)
    result["plus_di_14"] = plus_di
    result["minus_di_14"] = minus_di
    result["adx_14"] = adx
    line, signal, histogram = _macd(close)
    result["macd_12_26"] = line
    result["macd_signal_12_26_9"] = signal
    result["macd_histogram_12_26_9"] = histogram
    result["macd_12_26_pct"] = [
        None
        if line[index] is None
        or result["ema_26"][index] is None
        or abs(result["ema_26"][index]) == 0.0
        else line[index] / abs(result["ema_26"][index])
        for index in range(count)
    ]
    result["macd_histogram_12_26_9_pct"] = [
        None
        if histogram[index] is None or abs(close[index]) == 0.0
        else histogram[index] / abs(close[index])
        for index in range(count)
    ]
    assert tuple(result) == REFERENCE_FIELDS
    return result


def _assert_equivalent(
    actual: float | None,
    expected: float | None,
    *,
    label: str,
) -> None:
    if expected is None:
        assert actual is None, label
        return
    assert actual is not None, label
    difference = abs(actual - expected)
    tolerance = max(
        ABSOLUTE_TOLERANCE,
        RELATIVE_TOLERANCE * max(abs(actual), abs(expected)),
    )
    assert difference <= tolerance, (
        f"{label}: actual={actual!r}, expected={expected!r}, "
        f"difference={difference!r}, tolerance={tolerance!r}"
    )


def _assert_all_references(bars: tuple[SourceBar, ...]) -> None:
    actual = _calculate_all(bars)
    expected = _independent_reference(bars)
    for field_name in REFERENCE_FIELDS:
        for index, expected_value in enumerate(expected[field_name]):
            _assert_equivalent(
                actual[field_name].value_at(index),
                expected_value,
                label=f"{field_name}[{index}]",
            )


def test_committed_pinned_fixture_and_legacy_overlap() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == "TECH_INDICATORS_TALIB_GOLDEN_V1"
    assert fixture["provenance"]["legacy_overlap"] == [
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_20",
        "ema_50",
        "rsi_14",
        "atr_14",
    ]
    for case_name, case in fixture["cases"].items():
        bars = _fixture_bars(case)
        actual = _calculate_all(bars)
        runtime = TALibAdapter(normalize_source_bars(bars)).runtime.as_dict()
        assert runtime == {
            "library_name": "TA-Lib",
            "python_wrapper_version": fixture["runtime"]["talib_python"],
            "c_library_version": fixture["runtime"]["talib_c"],
            "numpy_version": fixture["runtime"]["numpy"],
            "compatibility": fixture["runtime"]["compatibility"],
            "unstable_period": fixture["runtime"]["unstable_period"],
        }
        for raw_index, expected_fields in case["expected"].items():
            index = int(raw_index)
            for field_name, expected in expected_fields.items():
                assert field_name in RAW_TALIB_FIELDS
                _assert_equivalent(
                    actual[field_name].value_at(index),
                    expected,
                    label=f"{case_name}.{field_name}[{index}]",
                )


@pytest.mark.parametrize(
    ("seed", "initial_close"),
    [(7, 100.0), (19, -70.0), (41, 0.000001)],
)
def test_seeded_provider_native_histories_match_scalar_oracle(
    seed: int,
    initial_close: float,
) -> None:
    _assert_all_references(
        _random_bars(seed=seed, count=340, initial_close=initial_close)
    )


def test_discontinuity_and_calendar_gap_match_scalar_oracle() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    case = fixture["cases"]["provider_native_discontinuity"]
    _assert_all_references(_fixture_bars(case))


@pytest.mark.parametrize("close", [50.0, -50.0, 0.0])
def test_flat_positive_negative_and_zero_histories_match_scalar_oracle(
    close: float,
) -> None:
    _assert_all_references(_flat_bars(close))
