from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    RangeRelationshipArrays,
    SourceBar,
    calculate_range_relationships,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import (
    range_relationships as range_relationships_module,
)


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
FIELD_CASES = (
    ("hh_20", "high", 20, max),
    ("hh_50", "high", 50, max),
    ("hh_252", "high", 252, max),
    ("ll_20", "low", 20, min),
    ("ll_50", "low", 50, min),
)


def _bar(index: int, high: Decimal, low: Decimal, *, gap_days: int = 0) -> SourceBar:
    return SourceBar(
        provider_listing_id=LISTING_ID,
        trading_date=date(2020, 1, 1) + timedelta(days=index + gap_days),
        open=low,
        high=high,
        low=low,
        close=high,
        volume=Decimal("100"),
    )


def _bars(
    observation_count: int,
    *,
    gap_after: int | None = None,
) -> tuple[SourceBar, ...]:
    return tuple(
        _bar(
            index,
            high=Decimal((index * 17) % 37 - 10),
            low=Decimal((index * 17) % 37 - 15),
            gap_days=4 if gap_after is not None and index > gap_after else 0,
        )
        for index in range(observation_count)
    )


def _calculate(bars: tuple[SourceBar, ...]) -> RangeRelationshipArrays:
    return calculate_range_relationships(normalize_source_bars(bars))


def test_range_relationship_api_is_explicitly_exported() -> None:
    assert range_relationships_module.__all__ == [
        "HIGH_PERIODS",
        "LOW_PERIODS",
        "RANGE_RELATIONSHIP_FIELDS",
        "RangeRelationshipArrays",
        "calculate_range_relationships",
    ]
    assert public_api.RangeRelationshipArrays is RangeRelationshipArrays
    assert public_api.calculate_range_relationships is calculate_range_relationships


@pytest.mark.parametrize(
    ("field_name", "source_name", "period", "operation"),
    FIELD_CASES,
)
def test_complete_windows_match_independent_trailing_extremes(
    field_name: str,
    source_name: str,
    period: int,
    operation: Callable[[list[float]], float],
) -> None:
    bars = _bars(253, gap_after=100)
    result = _calculate(bars)
    series = getattr(result, field_name)
    source = [float(getattr(bar, source_name)) for bar in bars]

    assert series.null_mask[: period - 1].all()
    assert np.isnan(series.values[: period - 1]).all()
    assert series.value_at(period - 2) is None
    for index in range(period - 1, len(bars)):
        expected = operation(source[index - period + 1 : index + 1])
        assert series.value_at(index) == expected


def test_current_observation_participates_in_high_and_low_windows() -> None:
    bars = tuple(
        _bar(
            index,
            high=Decimal("5") if index == 19 else Decimal("1"),
            low=Decimal("-4") if index == 19 else Decimal("0"),
        )
        for index in range(20)
    )

    result = _calculate(bars)

    assert result.hh_20.value_at(18) is None
    assert result.hh_20.value_at(19) == 5.0
    assert result.ll_20.value_at(18) is None
    assert result.ll_20.value_at(19) == -4.0


def test_short_history_remains_null_for_every_range() -> None:
    result = _calculate(_bars(19))

    assert result.observation_count == 19
    for field_name in range_relationships_module.RANGE_RELATIONSHIP_FIELDS:
        series = getattr(result, field_name)
        assert series.null_mask.all()
        assert np.isnan(series.values).all()


def test_prefix_results_are_independent_of_future_extremes() -> None:
    prefix_bars = _bars(60)
    future = _bar(
        60,
        high=Decimal("1000000"),
        low=Decimal("-1000000"),
    )
    full = _calculate((*prefix_bars, future))
    prefix = _calculate(prefix_bars)

    for field_name in range_relationships_module.RANGE_RELATIONSHIP_FIELDS:
        full_series = getattr(full, field_name)
        prefix_series = getattr(prefix, field_name)
        np.testing.assert_array_equal(
            prefix_series.values,
            full_series.values[:60],
        )
        np.testing.assert_array_equal(
            prefix_series.null_mask,
            full_series.null_mask[:60],
        )


def test_outputs_are_read_only_contiguous_with_explicit_masks() -> None:
    result = _calculate(_bars(252))

    for field_name in range_relationships_module.RANGE_RELATIONSHIP_FIELDS:
        series = getattr(result, field_name)
        assert series.values.dtype == np.dtype("float64")
        assert series.values.flags.c_contiguous
        assert not series.values.flags.writeable
        assert series.null_mask.dtype == np.dtype("bool")
        assert series.null_mask.flags.c_contiguous
        assert not series.null_mask.flags.writeable


def test_calculate_range_relationships_rejects_wrong_input_type() -> None:
    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_range_relationships(object())  # type: ignore[arg-type]
