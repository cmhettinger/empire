from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    BarStructureArrays,
    SourceBar,
    TechIndicatorsCalculationError,
    calculate_bar_structure,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import bar_structure as bar_structure_module
from empire_stonks_tech_indicators.models import PYTHON_FEATURE_FIELDS


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")


def _bar(
    day: int,
    *,
    open: str,
    high: str,
    low: str,
    close: str,
    volume: str | None,
) -> SourceBar:
    return SourceBar(
        provider_listing_id=LISTING_ID,
        trading_date=date(2026, 8, day),
        open=Decimal(open),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=None if volume is None else Decimal(volume),
    )


def _calculate(bars: tuple[SourceBar, ...]) -> BarStructureArrays:
    return calculate_bar_structure(normalize_source_bars(bars))


def test_bar_structure_api_is_explicitly_exported() -> None:
    assert bar_structure_module.__all__ == [
        "BAR_STRUCTURE_FIELDS",
        "BarStructureArrays",
        "calculate_bar_structure",
    ]
    assert public_api.BarStructureArrays is BarStructureArrays
    assert public_api.calculate_bar_structure is calculate_bar_structure


def test_calculates_bar_structure_and_preserves_exact_copied_sources() -> None:
    bars = (
        _bar(
            1,
            open="-3",
            high="-1",
            low="-4",
            close="-2",
            volume=None,
        ),
        _bar(5, open="-1", high="0", low="-2", close="-1", volume="4"),
        _bar(9, open="0", high="2", low="0", close="0", volume="5"),
        _bar(10, open="2", high="2", low="2", close="2", volume="3"),
        _bar(11, open="3", high="4", low="2", close="3", volume="0"),
    )

    result = _calculate(bars)

    assert result.copied_source_bars is bars
    assert result.observation_count == 5
    assert result.gap_1d_pct.value_at(0) is None
    assert result.gap_1d_pct.value_at(1) == -0.5
    assert result.gap_1d_pct.value_at(2) == -1.0
    assert result.gap_1d_pct.value_at(3) is None
    assert result.gap_1d_pct.value_at(4) == 0.5
    assert result.intraday_return_1d_pct.value_at(0) == pytest.approx(-1 / 3)
    assert result.intraday_return_1d_pct.value_at(1) == 0.0
    assert result.intraday_return_1d_pct.value_at(2) is None
    assert result.daily_range_pct.value_at(0) == 1.5
    assert result.daily_range_pct.value_at(1) == 2.0
    assert result.daily_range_pct.value_at(2) is None
    assert result.daily_range_pct.value_at(3) == 0.0
    assert result.close_location_1d.value_at(0) == pytest.approx(2 / 3)
    assert result.close_location_1d.value_at(1) == 0.5
    assert result.close_location_1d.value_at(2) == 0.0
    assert result.close_location_1d.value_at(3) is None
    assert result.dollar_volume.value_at(0) is None
    assert result.dollar_volume.value_at(1) == 4.0
    assert result.dollar_volume.value_at(2) == 0.0
    assert result.dollar_volume.value_at(3) == 6.0
    assert result.dollar_volume.value_at(4) == 0.0
    assert result.copied_source_bars[0].open == Decimal("-3")
    assert result.copied_source_bars[0].volume is None


def test_generated_reference_fields_do_not_change_writer_ownership() -> None:
    assert "gap_1d_pct" in PYTHON_FEATURE_FIELDS
    assert all(
        field_name not in PYTHON_FEATURE_FIELDS
        for field_name in (
            "intraday_return_1d_pct",
            "daily_range_pct",
            "close_location_1d",
            "dollar_volume",
        )
    )


def test_outputs_have_explicit_read_only_contiguous_masks() -> None:
    result = _calculate(
        (_bar(1, open="1", high="2", low="0", close="1", volume=None),)
    )

    for field_name in bar_structure_module.BAR_STRUCTURE_FIELDS:
        series = getattr(result, field_name)
        assert series.values.dtype == np.dtype("float64")
        assert series.values.flags.c_contiguous
        assert not series.values.flags.writeable
        assert series.null_mask.dtype == np.dtype("bool")
        assert series.null_mask.flags.c_contiguous
        assert not series.null_mask.flags.writeable


def test_prefix_results_are_independent_of_future_bars() -> None:
    bars = tuple(
        _bar(
            day,
            open=str(day),
            high=str(day + 2),
            low=str(day - 1),
            close=str(day + 1),
            volume=None if day == 2 else str(day * 10),
        )
        for day in range(1, 8)
    )
    full = _calculate(bars)
    prefix = _calculate(bars[:4])

    assert prefix.copied_source_bars == full.copied_source_bars[:4]
    for field_name in bar_structure_module.BAR_STRUCTURE_FIELDS:
        full_series = getattr(full, field_name)
        prefix_series = getattr(prefix, field_name)
        np.testing.assert_array_equal(
            prefix_series.values,
            full_series.values[:4],
        )
        np.testing.assert_array_equal(
            prefix_series.null_mask,
            full_series.null_mask[:4],
        )


@pytest.mark.parametrize(
    ("bars", "field_name"),
    [
        (
            (
                _bar(
                    1,
                    open="1e-320",
                    high="1",
                    low="0",
                    close="1",
                    volume="1",
                ),
            ),
            "intraday_return_1d_pct",
        ),
        (
            (
                _bar(
                    1,
                    open="1e-320",
                    high="1",
                    low="0",
                    close="1e-320",
                    volume="1",
                ),
            ),
            "daily_range_pct",
        ),
        (
            (
                _bar(
                    1,
                    open="1e308",
                    high="1e308",
                    low="1e308",
                    close="1e308",
                    volume="1e308",
                ),
            ),
            "dollar_volume",
        ),
    ],
)
def test_nonfinite_bar_output_fails_calculation(
    bars: tuple[SourceBar, ...],
    field_name: str,
) -> None:
    with pytest.raises(TechIndicatorsCalculationError, match=field_name):
        _calculate(bars)


def test_calculate_bar_structure_rejects_wrong_input_type() -> None:
    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_bar_structure(object())  # type: ignore[arg-type]
