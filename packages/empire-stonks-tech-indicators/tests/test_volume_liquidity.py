from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    MaskedFloatArray,
    SourceBar,
    TechIndicatorsCalculationError,
    VolumeLiquidityArrays,
    calculate_bar_structure,
    calculate_volume_liquidity,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import (
    volume_liquidity as volume_liquidity_module,
)


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
FIELD_CASES = (
    ("volume_avg_20", 20, False),
    ("volume_avg_60", 60, False),
    ("dollar_volume_avg_20", 20, True),
)


def _bar(
    index: int,
    *,
    close: str,
    volume: str | None,
    gap_days: int = 0,
) -> SourceBar:
    close_value = Decimal(close)
    return SourceBar(
        provider_listing_id=LISTING_ID,
        trading_date=date(2020, 1, 1) + timedelta(days=index + gap_days),
        open=close_value,
        high=close_value + Decimal("1"),
        low=close_value - Decimal("1"),
        close=close_value,
        volume=None if volume is None else Decimal(volume),
    )


def _bars(observation_count: int) -> tuple[SourceBar, ...]:
    return tuple(
        _bar(
            index,
            close=str(-(index + 1) if index % 2 else index + 1),
            volume=(
                None
                if index == 5
                else "0"
                if index == 10
                else "11.5"
                if index == 11
                else str(index + 1)
            ),
            gap_days=4 if index > 30 else 0,
        )
        for index in range(observation_count)
    )


def _calculate(bars: tuple[SourceBar, ...]) -> VolumeLiquidityArrays:
    calculation_arrays = normalize_source_bars(bars)
    bar_structure_arrays = calculate_bar_structure(calculation_arrays)
    return calculate_volume_liquidity(
        calculation_arrays,
        bar_structure_arrays,
    )


def test_volume_liquidity_api_is_explicitly_exported() -> None:
    assert volume_liquidity_module.__all__ == [
        "VOLUME_LIQUIDITY_FIELDS",
        "VolumeLiquidityArrays",
        "calculate_volume_liquidity",
    ]
    assert public_api.VolumeLiquidityArrays is VolumeLiquidityArrays
    assert public_api.calculate_volume_liquidity is calculate_volume_liquidity


@pytest.mark.parametrize(
    ("field_name", "period", "use_dollar_volume"),
    FIELD_CASES,
)
def test_complete_windows_match_independent_averages(
    field_name: str,
    period: int,
    use_dollar_volume: bool,
) -> None:
    bars = _bars(75)
    result = _calculate(bars)
    series = getattr(result, field_name)

    for index in range(len(bars)):
        if index < period - 1:
            assert series.value_at(index) is None
            continue
        window = bars[index - period + 1 : index + 1]
        if any(bar.volume is None for bar in window):
            assert series.value_at(index) is None
            continue
        assert all(bar.volume is not None for bar in window)
        if use_dollar_volume:
            source = [
                float(abs(bar.close) * bar.volume)
                for bar in window
                if bar.volume is not None
            ]
        else:
            source = [
                float(bar.volume)
                for bar in window
                if bar.volume is not None
            ]
        assert series.value_at(index) == pytest.approx(sum(source) / period)


def test_null_window_recovers_and_zero_volume_remains_valid() -> None:
    result = _calculate(_bars(66))

    assert result.volume_avg_20.value_at(24) is None
    assert result.volume_avg_20.value_at(25) is not None
    assert result.dollar_volume_avg_20.value_at(24) is None
    assert result.dollar_volume_avg_20.value_at(25) is not None
    assert result.volume_avg_60.value_at(64) is None
    assert result.volume_avg_60.value_at(65) is not None

    zero_bars = tuple(
        _bar(index, close="-2", volume="0" if index == 10 else "20")
        for index in range(20)
    )
    zero_result = _calculate(zero_bars)
    assert zero_result.volume_avg_20.value_at(19) == 19.0
    assert zero_result.dollar_volume_avg_20.value_at(19) == 38.0


def test_short_history_remains_null_and_outputs_are_contiguous() -> None:
    result = _calculate(_bars(19))

    assert result.observation_count == 19
    for field_name in volume_liquidity_module.VOLUME_LIQUIDITY_FIELDS:
        series = getattr(result, field_name)
        assert series.null_mask.all()
        assert np.isnan(series.values).all()
        assert series.values.dtype == np.dtype("float64")
        assert series.values.flags.c_contiguous
        assert not series.values.flags.writeable
        assert series.null_mask.dtype == np.dtype("bool")
        assert series.null_mask.flags.c_contiguous
        assert not series.null_mask.flags.writeable


def test_prefix_results_are_independent_of_future_volume() -> None:
    prefix_bars = _bars(70)
    future = _bar(74, close="1000000", volume="1000000", gap_days=4)
    full = _calculate((*prefix_bars, future))
    prefix = _calculate(prefix_bars)

    for field_name in volume_liquidity_module.VOLUME_LIQUIDITY_FIELDS:
        full_series = getattr(full, field_name)
        prefix_series = getattr(prefix, field_name)
        np.testing.assert_array_equal(
            prefix_series.values,
            full_series.values[:70],
        )
        np.testing.assert_array_equal(
            prefix_series.null_mask,
            full_series.null_mask[:70],
        )


def test_rejects_misaligned_or_tampered_bar_structure() -> None:
    calculation_arrays = normalize_source_bars(_bars(20))
    bar_structure_arrays = calculate_bar_structure(calculation_arrays)
    other_arrays = normalize_source_bars(
        tuple(
            _bar(index, close=str(index + 2), volume=str(index + 1))
            for index in range(20)
        )
    )
    with pytest.raises(TechIndicatorsCalculationError, match="do not match"):
        calculate_volume_liquidity(other_arrays, bar_structure_arrays)

    changed_values = bar_structure_arrays.dollar_volume.values.copy()
    changed_values[0] += 1.0
    changed_values.setflags(write=False)
    changed_dollar_volume = MaskedFloatArray(
        values=changed_values,
        null_mask=bar_structure_arrays.dollar_volume.null_mask,
    )
    tampered = replace(
        bar_structure_arrays,
        dollar_volume=changed_dollar_volume,
    )
    with pytest.raises(TechIndicatorsCalculationError, match="Dollar-volume"):
        calculate_volume_liquidity(calculation_arrays, tampered)


@pytest.mark.parametrize(
    ("close", "volume", "field_name"),
    [
        ("1", "1e308", "volume_avg_20"),
        ("1e308", "1", "dollar_volume_avg_20"),
    ],
)
def test_nonfinite_window_average_fails_calculation(
    close: str,
    volume: str,
    field_name: str,
) -> None:
    bars = tuple(
        _bar(index, close=close, volume=volume) for index in range(20)
    )

    with pytest.raises(TechIndicatorsCalculationError, match=field_name):
        _calculate(bars)


def test_calculate_volume_liquidity_rejects_wrong_input_types() -> None:
    calculation_arrays = normalize_source_bars(_bars(20))
    bar_structure_arrays = calculate_bar_structure(calculation_arrays)

    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_volume_liquidity(
            object(),  # type: ignore[arg-type]
            bar_structure_arrays,
        )
    with pytest.raises(TypeError, match="BarStructureArrays"):
        calculate_volume_liquidity(
            calculation_arrays,
            object(),  # type: ignore[arg-type]
        )
