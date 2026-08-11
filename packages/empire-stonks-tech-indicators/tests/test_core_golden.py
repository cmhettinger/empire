from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import mean, stdev
from typing import Any
from uuid import UUID

import pytest

from empire_stonks_tech_indicators import (
    SourceBar,
    calculate_bar_structure,
    calculate_range_relationships,
    calculate_return_statistics,
    calculate_returns,
    calculate_streaks,
    calculate_volume_liquidity,
    normalize_source_bars,
)
from empire_stonks_tech_indicators.bar_structure import BAR_STRUCTURE_FIELDS
from empire_stonks_tech_indicators.range_relationships import (
    RANGE_RELATIONSHIP_FIELDS,
)
from empire_stonks_tech_indicators.return_statistics import (
    RETURN_STATISTIC_FIELDS,
)
from empire_stonks_tech_indicators.returns import RETURN_FIELDS
from empire_stonks_tech_indicators.streaks import STREAK_FIELDS
from empire_stonks_tech_indicators.volume_liquidity import (
    VOLUME_LIQUIDITY_FIELDS,
)


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
ABSOLUTE_TOLERANCE = 1e-12
RELATIVE_TOLERANCE = 1e-10
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "core_features_v1.json"
FLOAT_FIELDS = (
    *(field_name for field_name, _ in RETURN_FIELDS),
    *BAR_STRUCTURE_FIELDS,
    *RANGE_RELATIONSHIP_FIELDS,
    *VOLUME_LIQUIDITY_FIELDS,
    *RETURN_STATISTIC_FIELDS,
)
ALL_FIELDS = (*FLOAT_FIELDS, *STREAK_FIELDS)


def _decimal(value: float | int) -> Decimal:
    return Decimal(str(value))


def _source_bar(
    *,
    trading_date: date,
    open_value: float,
    high: float,
    low: float,
    close: float,
    volume: float | None,
) -> SourceBar:
    return SourceBar(
        provider_listing_id=LISTING_ID,
        trading_date=trading_date,
        open=_decimal(open_value),
        high=_decimal(high),
        low=_decimal(low),
        close=_decimal(close),
        volume=None if volume is None else _decimal(volume),
    )


def _next_business_day(value: date) -> date:
    result = value + timedelta(days=1)
    while result.weekday() >= 5:
        result += timedelta(days=1)
    return result


def _golden_bars(case: dict[str, Any]) -> tuple[SourceBar, ...]:
    generator = case["generator"]
    current_date = date.fromisoformat(generator["start_date"])
    bars: list[SourceBar] = []
    for index in range(generator["observations"]):
        if index:
            if generator.get("business_days", False):
                current_date = _next_business_day(current_date)
            else:
                current_date += timedelta(days=1)
        if index == generator.get("gap_before_index"):
            current_date += timedelta(days=generator["gap_days"])

        close = generator.get("close_start", 100.0) + index * generator.get(
            "close_step",
            1.0,
        )
        if index >= generator.get("split_index", generator["observations"]):
            close *= generator["split_factor"]
        volume = generator["volume_start"] + index * generator["volume_step"]
        bars.append(
            _source_bar(
                trading_date=current_date,
                open_value=close + generator["open_offset"],
                high=close + generator["high_offset"],
                low=close + generator["low_offset"],
                close=close,
                volume=volume,
            )
        )
    return tuple(bars)


def _random_bars(seed: int, count: int) -> tuple[SourceBar, ...]:
    generator = random.Random(seed)
    current_date = date(2018, 1, 2)
    close = 100.0
    bars: list[SourceBar] = []
    for index in range(count):
        if index:
            current_date += timedelta(days=generator.randint(1, 4))
            if index % 43 != 0:
                close = round(close * (1.0 + generator.uniform(-0.08, 0.08)), 6)
        open_value = round(close * (1.0 + generator.uniform(-0.025, 0.025)), 6)
        spread = round(generator.uniform(0.01, 2.5), 6)
        high = round(max(open_value, close) + spread, 6)
        low = round(min(open_value, close) - spread, 6)
        if generator.random() < 0.08:
            volume = None
        elif generator.random() < 0.08:
            volume = 0.0
        else:
            volume = round(generator.uniform(100.0, 2_000_000.0), 3)
        bars.append(
            _source_bar(
                trading_date=current_date,
                open_value=open_value,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    return tuple(bars)


def _calculate_all(bars: tuple[SourceBar, ...]) -> dict[str, Any]:
    calculation_arrays = normalize_source_bars(bars)
    returns = calculate_returns(calculation_arrays)
    bar_structure = calculate_bar_structure(calculation_arrays)
    ranges = calculate_range_relationships(calculation_arrays)
    volume = calculate_volume_liquidity(calculation_arrays, bar_structure)
    streaks = calculate_streaks(calculation_arrays)
    return_statistics = calculate_return_statistics(calculation_arrays, returns)

    result: dict[str, Any] = {}
    for owner, field_names in (
        (returns, (field_name for field_name, _ in RETURN_FIELDS)),
        (bar_structure, BAR_STRUCTURE_FIELDS),
        (ranges, RANGE_RELATIONSHIP_FIELDS),
        (volume, VOLUME_LIQUIDITY_FIELDS),
        (return_statistics, RETURN_STATISTIC_FIELDS),
    ):
        for field_name in field_names:
            result[field_name] = getattr(owner, field_name)
    for field_name in STREAK_FIELDS:
        result[field_name] = getattr(streaks, field_name)
    assert tuple(result) == ALL_FIELDS
    return result


def _safe_divide(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0.0 else numerator / denominator


def _rolling(
    source: list[float | None],
    period: int,
    operation: Any,
) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(source)):
        if index + 1 < period:
            result.append(None)
            continue
        window = source[index - period + 1 : index + 1]
        if any(value is None for value in window):
            result.append(None)
            continue
        result.append(operation([float(value) for value in window]))
    return result


def _independent_reference(
    bars: tuple[SourceBar, ...],
) -> dict[str, list[float | int | None]]:
    opens = [float(bar.open) for bar in bars]
    highs = [float(bar.high) for bar in bars]
    lows = [float(bar.low) for bar in bars]
    closes = [float(bar.close) for bar in bars]
    volumes = [None if bar.volume is None else float(bar.volume) for bar in bars]
    count = len(bars)
    result: dict[str, list[float | int | None]] = {}

    for field_name, period in RETURN_FIELDS:
        result[field_name] = [
            None
            if index < period or closes[index - period] == 0.0
            else closes[index] / closes[index - period] - 1.0
            for index in range(count)
        ]

    result["gap_1d_pct"] = [
        None
        if index == 0 or closes[index - 1] == 0.0
        else opens[index] / closes[index - 1] - 1.0
        for index in range(count)
    ]
    result["intraday_return_1d_pct"] = [
        None if opens[index] == 0.0 else closes[index] / opens[index] - 1.0
        for index in range(count)
    ]
    result["daily_range_pct"] = [
        _safe_divide(highs[index] - lows[index], abs(closes[index]))
        for index in range(count)
    ]
    result["close_location_1d"] = [
        _safe_divide(
            closes[index] - lows[index],
            highs[index] - lows[index],
        )
        for index in range(count)
    ]
    dollar_volume = [
        None if volume is None else abs(closes[index]) * volume
        for index, volume in enumerate(volumes)
    ]
    result["dollar_volume"] = dollar_volume

    for period in (20, 50, 252):
        result[f"hh_{period}"] = _rolling(highs, period, max)
    for period in (20, 50):
        result[f"ll_{period}"] = _rolling(lows, period, min)
    result["volume_avg_20"] = _rolling(
        volumes,
        20,
        lambda values: sum(values) / 20,
    )
    result["volume_avg_60"] = _rolling(
        volumes,
        60,
        lambda values: sum(values) / 60,
    )
    result["dollar_volume_avg_20"] = _rolling(
        dollar_volume,
        20,
        lambda values: sum(values) / 20,
    )

    up = [0] * count
    down = [0] * count
    for index in range(1, count):
        if closes[index] > closes[index - 1]:
            up[index] = up[index - 1] + 1
        elif closes[index] < closes[index - 1]:
            down[index] = down[index - 1] + 1
    one_day_returns = result["return_1d_pct"]
    result["return_volatility_20d_pct"] = _rolling(
        one_day_returns,
        20,
        stdev,
    )
    result["return_volatility_60d_pct"] = _rolling(
        one_day_returns,
        60,
        stdev,
    )
    for period in (1, 3):
        source = result[f"return_{period}d_pct"]
        zscores: list[float | None] = []
        for index, tested in enumerate(source):
            if index < 20 or tested is None:
                zscores.append(None)
                continue
            reference = source[index - 20 : index]
            if any(value is None for value in reference):
                zscores.append(None)
                continue
            populated = [float(value) for value in reference]
            sample_stddev = stdev(populated)
            zscores.append(
                None
                if sample_stddev == 0.0
                else (float(tested) - mean(populated)) / sample_stddev
            )
        result[f"return_{period}d_zscore_20d"] = zscores

    result["consecutive_up_days"] = up
    result["consecutive_down_days"] = down

    assert tuple(result) == ALL_FIELDS
    return result


def _value_at(series: Any, index: int) -> float | int | None:
    if hasattr(series, "value_at"):
        return series.value_at(index)
    return int(series[index])


def _assert_equivalent(
    actual: float | int | None,
    expected: float | int | None,
    *,
    label: str,
) -> None:
    if expected is None:
        assert actual is None, label
        return
    assert actual is not None, label
    if isinstance(expected, int):
        assert actual == expected, label
        return
    assert math.isfinite(float(actual)), label
    difference = abs(float(actual) - expected)
    tolerance = max(
        ABSOLUTE_TOLERANCE,
        RELATIVE_TOLERANCE * max(abs(float(actual)), abs(expected)),
    )
    assert difference <= tolerance, (
        f"{label}: actual={actual!r}, expected={expected!r}, "
        f"difference={difference!r}, tolerance={tolerance!r}"
    )


def test_committed_golden_fixture_matches_legacy_and_discontinuity_cases() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert fixture["schema_version"] == "TECH_INDICATORS_CORE_GOLDEN_V1"
    assert fixture["provenance"]["legacy_overlap"] == [
        "hh_20",
        "ll_20",
        "volume_avg_20",
    ]
    for case_name, case in fixture["cases"].items():
        bars = _golden_bars(case)
        actual = _calculate_all(bars)
        for index_text, expected_fields in case["expected"].items():
            index = int(index_text)
            for field_name, expected in expected_fields.items():
                _assert_equivalent(
                    _value_at(actual[field_name], index),
                    expected,
                    label=f"{case_name}[{index}].{field_name}",
                )

    discontinuity = _golden_bars(fixture["cases"]["provider_native_discontinuity"])
    assert (discontinuity[15].trading_date - discontinuity[14].trading_date).days == 31


@pytest.mark.parametrize("count", (1, 3, 15, 19))
def test_short_histories_match_independent_reference(count: int) -> None:
    bars = _random_bars(20260811 + count, count)
    actual = _calculate_all(bars)
    expected = _independent_reference(bars)

    for field_name in ALL_FIELDS:
        for index in range(count):
            _assert_equivalent(
                _value_at(actual[field_name], index),
                expected[field_name][index],
                label=f"short[{count}][{index}].{field_name}",
            )
    for field_name in (
        *RANGE_RELATIONSHIP_FIELDS,
        *VOLUME_LIQUIDITY_FIELDS,
        *RETURN_STATISTIC_FIELDS,
    ):
        assert all(_value_at(actual[field_name], index) is None for index in range(count))


@pytest.mark.parametrize("seed", (7, 20260811, 99173))
def test_randomized_core_outputs_match_independent_scalar_formulas(seed: int) -> None:
    bars = _random_bars(seed, 280)
    actual = _calculate_all(bars)
    expected = _independent_reference(bars)

    assert any(
        (bars[index].trading_date - bars[index - 1].trading_date).days > 1
        for index in range(1, len(bars))
    )
    assert any(bar.volume is None for bar in bars)
    assert any(bar.volume == 0 for bar in bars)
    for field_name in ALL_FIELDS:
        for index in range(len(bars)):
            _assert_equivalent(
                _value_at(actual[field_name], index),
                expected[field_name][index],
                label=f"random[{seed}][{index}].{field_name}",
            )


def test_random_future_mutation_cannot_change_any_prefix_output() -> None:
    original = _random_bars(4441, 280)
    cutoff = 173
    mutated = original[: cutoff + 1] + _random_bars(991, 106)
    replacement_start = original[cutoff].trading_date + timedelta(days=1)
    mutated = mutated[: cutoff + 1] + tuple(
        SourceBar(
            provider_listing_id=bar.provider_listing_id,
            trading_date=replacement_start + timedelta(days=index),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        for index, bar in enumerate(mutated[cutoff + 1 :])
    )
    original_outputs = _calculate_all(original)
    mutated_outputs = _calculate_all(mutated)

    for field_name in ALL_FIELDS:
        for index in range(cutoff + 1):
            _assert_equivalent(
                _value_at(mutated_outputs[field_name], index),
                _value_at(original_outputs[field_name], index),
                label=f"future-mutation[{index}].{field_name}",
            )
