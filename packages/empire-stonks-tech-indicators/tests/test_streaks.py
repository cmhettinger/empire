from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    SourceBar,
    StreakArrays,
    calculate_streaks,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import streaks as streaks_module


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")


def _bar(index: int, close: str, *, gap_days: int = 0) -> SourceBar:
    close_value = Decimal(close)
    return SourceBar(
        provider_listing_id=LISTING_ID,
        trading_date=date(2020, 1, 1) + timedelta(days=index + gap_days),
        open=close_value,
        high=close_value + Decimal("1"),
        low=close_value - Decimal("1"),
        close=close_value,
        volume=Decimal("100"),
    )


def _bars(closes: list[str]) -> tuple[SourceBar, ...]:
    return tuple(
        _bar(index, close, gap_days=4 if index > 4 else 0)
        for index, close in enumerate(closes)
    )


def _calculate(bars: tuple[SourceBar, ...]) -> StreakArrays:
    return calculate_streaks(normalize_source_bars(bars))


def test_streak_api_is_explicitly_exported() -> None:
    assert streaks_module.__all__ == [
        "STREAK_FIELDS",
        "StreakArrays",
        "calculate_streaks",
    ]
    assert public_api.StreakArrays is StreakArrays
    assert public_api.calculate_streaks is calculate_streaks


def test_up_down_and_unchanged_streak_contract() -> None:
    result = _calculate(
        _bars(["10", "11", "12", "12", "11", "10", "10", "9", "10", "11"])
    )

    assert result.consecutive_up_days.tolist() == [0, 1, 2, 0, 0, 0, 0, 0, 1, 2]
    assert result.consecutive_down_days.tolist() == [0, 0, 0, 0, 1, 2, 0, 1, 0, 0]


def test_negative_closes_and_calendar_gaps_use_observation_order() -> None:
    bars = (
        _bar(0, "-3"),
        _bar(4, "-2"),
        _bar(9, "-1"),
        _bar(10, "-4"),
    )

    result = _calculate(bars)

    assert result.consecutive_up_days.tolist() == [0, 1, 2, 0]
    assert result.consecutive_down_days.tolist() == [0, 0, 0, 1]


def test_repeated_full_prefix_append_matches_one_rebuild() -> None:
    bars = _bars(["1", "2", "3", "2", "1", "1", "2", "3", "4", "0"])
    rebuild = _calculate(bars)

    for end in range(1, len(bars) + 1):
        append_run = _calculate(bars[:end])
        np.testing.assert_array_equal(
            append_run.consecutive_up_days,
            rebuild.consecutive_up_days[:end],
        )
        np.testing.assert_array_equal(
            append_run.consecutive_down_days,
            rebuild.consecutive_down_days[:end],
        )


def test_independent_append_state_matches_full_rebuild_at_every_split() -> None:
    closes = [1.0, 2.0, 3.0, 3.0, -1.0, -2.0, -3.0, 0.0, 1.0]
    bars = _bars([str(close) for close in closes])
    rebuild = _calculate(bars)

    for split in range(1, len(bars)):
        prefix = _calculate(bars[:split])
        up = prefix.consecutive_up_days.tolist()
        down = prefix.consecutive_down_days.tolist()
        for index in range(split, len(closes)):
            if closes[index] > closes[index - 1]:
                up.append(up[-1] + 1)
                down.append(0)
            elif closes[index] < closes[index - 1]:
                up.append(0)
                down.append(down[-1] + 1)
            else:
                up.append(0)
                down.append(0)
        assert up == rebuild.consecutive_up_days.tolist()
        assert down == rebuild.consecutive_down_days.tolist()


def test_long_streak_counts_current_observation_then_resets() -> None:
    bars = _bars([str(index) for index in range(300)] + ["299"])
    result = _calculate(bars)

    assert result.consecutive_up_days[299] == 299
    assert result.consecutive_down_days[299] == 0
    assert result.consecutive_up_days[300] == 0
    assert result.consecutive_down_days[300] == 0


def test_outputs_are_read_only_contiguous_int64_without_nulls() -> None:
    result = _calculate(_bars(["1", "2", "1"]))

    assert result.observation_count == 3
    for field_name in streaks_module.STREAK_FIELDS:
        values = getattr(result, field_name)
        assert values.dtype == np.dtype("int64")
        assert values.flags.c_contiguous
        assert not values.flags.writeable
        assert np.all(values >= 0)
        with pytest.raises(ValueError, match="read-only"):
            values[0] = 1


def test_calculate_streaks_rejects_wrong_input_type() -> None:
    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_streaks(object())  # type: ignore[arg-type]
