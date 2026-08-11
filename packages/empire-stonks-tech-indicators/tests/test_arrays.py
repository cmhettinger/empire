from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    CalculationArrays,
    SourceBar,
    TechIndicatorsCalculationError,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import arrays as arrays_module


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
OTHER_LISTING_ID = UUID("00000000-0000-4000-8000-000000000002")


def _bar(
    trading_date: date,
    *,
    provider_listing_id: UUID = LISTING_ID,
    open: str = "10",
    high: str = "12",
    low: str = "9",
    close: str = "11",
    volume: str | None = "100",
) -> SourceBar:
    return SourceBar(
        provider_listing_id=provider_listing_id,
        trading_date=trading_date,
        open=Decimal(open),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=None if volume is None else Decimal(volume),
    )


def test_array_api_is_explicitly_exported() -> None:
    assert arrays_module.__all__ == ["CalculationArrays", "normalize_source_bars"]
    assert public_api.CalculationArrays is CalculationArrays
    assert public_api.normalize_source_bars is normalize_source_bars


def test_normalizes_in_encounter_order_without_calendar_fill() -> None:
    bars = (
        _bar(
            date(2026, 8, 3),
            open="-10.25",
            high="-8",
            low="-12",
            close="-9.5",
            volume=None,
        ),
        _bar(
            date(2026, 8, 5),
            open="0",
            high="2",
            low="-1",
            close="1",
            volume="0",
        ),
        _bar(
            date(2026, 8, 10),
            open="3",
            high="5",
            low="2",
            close="4",
            volume="2.5",
        ),
    )

    arrays = normalize_source_bars(iter(bars))

    assert arrays.source_bars == bars
    assert arrays.provider_listing_id == LISTING_ID
    assert arrays.trading_dates == (
        date(2026, 8, 3),
        date(2026, 8, 5),
        date(2026, 8, 10),
    )
    assert arrays.observation_count == 3
    np.testing.assert_array_equal(arrays.open, [-10.25, 0.0, 3.0])
    np.testing.assert_array_equal(arrays.high, [-8.0, 2.0, 5.0])
    np.testing.assert_array_equal(arrays.low, [-12.0, -1.0, 2.0])
    np.testing.assert_array_equal(arrays.close, [-9.5, 1.0, 4.0])
    np.testing.assert_array_equal(arrays.volume_null_mask, [True, False, False])
    assert np.isnan(arrays.volume[0])
    np.testing.assert_array_equal(arrays.volume[1:], [0.0, 2.5])


def test_arrays_are_read_only_contiguous_and_use_exact_dtypes() -> None:
    arrays = normalize_source_bars(
        (_bar(date(2026, 8, 1)), _bar(date(2026, 8, 2), volume=None))
    )

    for values in (
        arrays.open,
        arrays.high,
        arrays.low,
        arrays.close,
        arrays.volume,
    ):
        assert values.dtype == np.dtype("float64")
        assert values.flags.c_contiguous
        assert not values.flags.writeable
    assert arrays.volume_null_mask.dtype == np.dtype("bool")
    assert arrays.volume_null_mask.flags.c_contiguous
    assert not arrays.volume_null_mask.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        arrays.close[0] = 999.0


def test_prefix_normalization_is_identical_and_uses_no_future_values() -> None:
    bars = tuple(
        _bar(
            date(2026, 8, day),
            open=str(day),
            high=str(day + 2),
            low=str(day - 1),
            close=str(day + 1),
        )
        for day in range(1, 6)
    )

    full = normalize_source_bars(bars)
    prefix = normalize_source_bars(bars[:3])

    for field_name in ("open", "high", "low", "close", "volume"):
        np.testing.assert_array_equal(
            getattr(prefix, field_name),
            getattr(full, field_name)[:3],
        )
    np.testing.assert_array_equal(
        prefix.volume_null_mask,
        full.volume_null_mask[:3],
    )


def test_record_rejects_arrays_that_drift_from_attached_source() -> None:
    arrays = normalize_source_bars((_bar(date(2026, 8, 1)),))
    changed_close = arrays.close.copy()
    changed_close[0] = 10.5
    changed_close.setflags(write=False)

    with pytest.raises(ValueError, match="attached source bars"):
        replace(arrays, close=changed_close)


@pytest.mark.parametrize(
    ("bars", "message"),
    [
        ((), "empty"),
        (
            (_bar(date(2026, 8, 1)), _bar(date(2026, 8, 1))),
            "duplicate or out of order",
        ),
        (
            (_bar(date(2026, 8, 2)), _bar(date(2026, 8, 1))),
            "duplicate or out of order",
        ),
        (
            (
                _bar(date(2026, 8, 1)),
                _bar(date(2026, 8, 2), provider_listing_id=OTHER_LISTING_ID),
            ),
            "exactly one provider listing",
        ),
    ],
)
def test_rejects_empty_mixed_or_nonchronological_input(
    bars: tuple[SourceBar, ...],
    message: str,
) -> None:
    with pytest.raises(TechIndicatorsCalculationError, match=message):
        normalize_source_bars(bars)


def test_rejects_non_source_bar_members() -> None:
    with pytest.raises(TypeError, match="SourceBar"):
        normalize_source_bars([object()])  # type: ignore[list-item]


@pytest.mark.parametrize("field_name", ["open", "high", "low", "volume"])
def test_rejects_nonfinite_float64_conversion(field_name: str) -> None:
    values = {
        "open": "1",
        "high": "2",
        "low": "0",
        "close": "1",
        "volume": "1",
    }
    if field_name == "open":
        values.update(open="1e1000000", high="1e1000000")
    elif field_name == "high":
        values.update(high="1e1000000")
    elif field_name == "low":
        values.update(low="-1e1000000")
    else:
        values.update(volume="1e1000000")
    bar = _bar(date(2026, 8, 1), **values)

    with pytest.raises(TechIndicatorsCalculationError, match=field_name):
        normalize_source_bars((bar,))
