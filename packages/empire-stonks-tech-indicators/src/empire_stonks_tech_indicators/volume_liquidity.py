"""Pure complete-window volume and liquidity calculations for V1."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from empire_stonks_tech_indicators.arrays import (
    CalculationArrays,
    MaskedFloatArray,
)
from empire_stonks_tech_indicators.bar_structure import BarStructureArrays
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsCalculationError,
)


VOLUME_LIQUIDITY_FIELDS = (
    "volume_avg_20",
    "volume_avg_60",
    "dollar_volume_avg_20",
)


def _complete_window_average(
    source: MaskedFloatArray,
    *,
    field_name: str,
    period: int,
) -> MaskedFloatArray:
    observation_count = len(source.values)
    values = np.full(observation_count, np.nan, dtype=np.float64)
    null_mask = np.ones(observation_count, dtype=np.bool_)

    if observation_count >= period:
        value_windows = np.lib.stride_tricks.sliding_window_view(
            source.values,
            period,
        )
        mask_windows = np.lib.stride_tricks.sliding_window_view(
            source.null_mask,
            period,
        )
        complete = ~np.any(mask_windows, axis=1)
        with np.errstate(invalid="ignore", over="ignore"):
            calculated = np.sum(value_windows[complete], axis=1) / period
        nonfinite = ~np.isfinite(calculated)
        if nonfinite.any():
            window_offset = int(np.flatnonzero(complete)[nonfinite][0])
            observation = period - 1 + window_offset
            raise TechIndicatorsCalculationError(
                f"{field_name} produced a non-finite value at observation "
                f"{observation}."
            )
        eligible_indices = period - 1 + np.flatnonzero(complete)
        values[eligible_indices] = calculated
        null_mask[eligible_indices] = False

    values = np.ascontiguousarray(values)
    null_mask = np.ascontiguousarray(null_mask)
    values.setflags(write=False)
    null_mask.setflags(write=False)
    return MaskedFloatArray(values=values, null_mask=null_mask)


def _volume_series(calculation_arrays: CalculationArrays) -> MaskedFloatArray:
    return MaskedFloatArray(
        values=calculation_arrays.volume,
        null_mask=calculation_arrays.volume_null_mask,
    )


def _validate_bar_structure_alignment(
    calculation_arrays: CalculationArrays,
    bar_structure_arrays: BarStructureArrays,
) -> None:
    if bar_structure_arrays.copied_source_bars != calculation_arrays.source_bars:
        raise TechIndicatorsCalculationError(
            "Bar-structure inputs do not match the normalized source series."
        )
    dollar_volume = bar_structure_arrays.dollar_volume
    if not np.array_equal(
        dollar_volume.null_mask,
        calculation_arrays.volume_null_mask,
    ):
        raise TechIndicatorsCalculationError(
            "Dollar-volume nulls do not match normalized source volume."
        )
    populated = ~calculation_arrays.volume_null_mask
    with np.errstate(invalid="ignore", over="ignore"):
        expected = (
            np.abs(calculation_arrays.close[populated])
            * calculation_arrays.volume[populated]
        )
    if not np.array_equal(dollar_volume.values[populated], expected):
        raise TechIndicatorsCalculationError(
            "Dollar-volume values do not match normalized source values."
        )


@dataclass(frozen=True, eq=False)
class VolumeLiquidityArrays:
    """V1 volume and nominal liquidity averages in observation order."""

    volume_avg_20: MaskedFloatArray
    volume_avg_60: MaskedFloatArray
    dollar_volume_avg_20: MaskedFloatArray

    def __post_init__(self) -> None:
        lengths: set[int] = set()
        for field_name in VOLUME_LIQUIDITY_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            lengths.add(len(series.values))
        if len(lengths) != 1:
            raise ValueError(
                "volume and liquidity arrays must have one observation count."
            )

    @property
    def observation_count(self) -> int:
        return len(self.volume_avg_20.values)


def calculate_volume_liquidity(
    calculation_arrays: CalculationArrays,
    bar_structure_arrays: BarStructureArrays,
) -> VolumeLiquidityArrays:
    """Calculate complete volume windows with strict source alignment."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")
    if not isinstance(bar_structure_arrays, BarStructureArrays):
        raise TypeError("bar_structure_arrays must be BarStructureArrays.")
    _validate_bar_structure_alignment(calculation_arrays, bar_structure_arrays)

    volume = _volume_series(calculation_arrays)
    return VolumeLiquidityArrays(
        volume_avg_20=_complete_window_average(
            volume,
            field_name="volume_avg_20",
            period=20,
        ),
        volume_avg_60=_complete_window_average(
            volume,
            field_name="volume_avg_60",
            period=60,
        ),
        dollar_volume_avg_20=_complete_window_average(
            bar_structure_arrays.dollar_volume,
            field_name="dollar_volume_avg_20",
            period=20,
        ),
    )


__all__ = [
    "VOLUME_LIQUIDITY_FIELDS",
    "VolumeLiquidityArrays",
    "calculate_volume_liquidity",
]
