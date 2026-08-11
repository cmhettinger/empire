"""Pure V1 bar-structure and copied-source calculations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from empire_stonks_tech_indicators.arrays import (
    CalculationArrays,
    MaskedFloatArray,
)
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsCalculationError,
)
from empire_stonks_tech_indicators.models import SourceBar


BAR_STRUCTURE_FIELDS = (
    "gap_1d_pct",
    "intraday_return_1d_pct",
    "daily_range_pct",
    "close_location_1d",
    "dollar_volume",
)


def _masked_series(
    values: np.ndarray,
    null_mask: np.ndarray,
) -> MaskedFloatArray:
    result_values = np.ascontiguousarray(values, dtype=np.float64)
    result_mask = np.ascontiguousarray(null_mask, dtype=np.bool_)
    result_values.setflags(write=False)
    result_mask.setflags(write=False)
    return MaskedFloatArray(values=result_values, null_mask=result_mask)


def _divide_series(
    *,
    field_name: str,
    numerator: np.ndarray,
    denominator: np.ndarray,
    eligible: np.ndarray,
    subtract_one: bool = False,
) -> MaskedFloatArray:
    values = np.full(len(numerator), np.nan, dtype=np.float64)
    null_mask = np.ones(len(numerator), dtype=np.bool_)
    valid = eligible & (denominator != 0.0)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        calculated = numerator[valid] / denominator[valid]
        if subtract_one:
            calculated = calculated - 1.0
    nonfinite = ~np.isfinite(calculated)
    if nonfinite.any():
        observation = int(np.flatnonzero(valid)[nonfinite][0])
        raise TechIndicatorsCalculationError(
            f"{field_name} produced a non-finite value at observation "
            f"{observation}."
        )
    values[valid] = calculated
    null_mask[valid] = False
    return _masked_series(values, null_mask)


def _dollar_volume(calculation_arrays: CalculationArrays) -> MaskedFloatArray:
    null_mask = calculation_arrays.volume_null_mask.copy()
    values = np.full(
        calculation_arrays.observation_count,
        np.nan,
        dtype=np.float64,
    )
    populated = ~null_mask
    with np.errstate(invalid="ignore", over="ignore"):
        calculated = (
            np.abs(calculation_arrays.close[populated])
            * calculation_arrays.volume[populated]
        )
    nonfinite = ~np.isfinite(calculated)
    if nonfinite.any():
        observation = int(np.flatnonzero(populated)[nonfinite][0])
        raise TechIndicatorsCalculationError(
            "dollar_volume produced a non-finite value at observation "
            f"{observation}."
        )
    values[populated] = calculated
    return _masked_series(values, null_mask)


@dataclass(frozen=True, eq=False)
class BarStructureArrays:
    """Bar features plus exact source records retained for row assembly.

    Only ``gap_1d_pct`` is a Python-written payload field. The other calculated
    series are reference values for validating the matching PostgreSQL stored
    generated columns; this record does not change their persistence ownership.
    """

    copied_source_bars: tuple[SourceBar, ...]
    gap_1d_pct: MaskedFloatArray
    intraday_return_1d_pct: MaskedFloatArray
    daily_range_pct: MaskedFloatArray
    close_location_1d: MaskedFloatArray
    dollar_volume: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.copied_source_bars, tuple):
            raise TypeError("copied_source_bars must be a tuple.")
        if not self.copied_source_bars:
            raise ValueError("copied_source_bars must not be empty.")
        if any(
            not isinstance(bar, SourceBar) for bar in self.copied_source_bars
        ):
            raise TypeError(
                "copied_source_bars must contain only SourceBar records."
            )
        observation_count = len(self.copied_source_bars)
        for field_name in BAR_STRUCTURE_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != observation_count:
                raise ValueError(
                    f"{field_name} must match the copied source observation count."
                )

    @property
    def observation_count(self) -> int:
        return len(self.copied_source_bars)


def calculate_bar_structure(
    calculation_arrays: CalculationArrays,
) -> BarStructureArrays:
    """Calculate V1 same-bar structure without filling or future access."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")

    observation_count = calculation_arrays.observation_count
    all_observations = np.ones(observation_count, dtype=np.bool_)
    gap_eligible = all_observations.copy()
    gap_eligible[0] = False
    prior_close = np.zeros(observation_count, dtype=np.float64)
    prior_close[1:] = calculation_arrays.close[:-1]

    with np.errstate(invalid="ignore", over="ignore"):
        range_numerator = calculation_arrays.high - calculation_arrays.low
        location_numerator = calculation_arrays.close - calculation_arrays.low

    return BarStructureArrays(
        copied_source_bars=calculation_arrays.source_bars,
        gap_1d_pct=_divide_series(
            field_name="gap_1d_pct",
            numerator=calculation_arrays.open,
            denominator=prior_close,
            eligible=gap_eligible,
            subtract_one=True,
        ),
        intraday_return_1d_pct=_divide_series(
            field_name="intraday_return_1d_pct",
            numerator=calculation_arrays.close,
            denominator=calculation_arrays.open,
            eligible=all_observations,
            subtract_one=True,
        ),
        daily_range_pct=_divide_series(
            field_name="daily_range_pct",
            numerator=range_numerator,
            denominator=np.abs(calculation_arrays.close),
            eligible=all_observations,
        ),
        close_location_1d=_divide_series(
            field_name="close_location_1d",
            numerator=location_numerator,
            denominator=range_numerator,
            eligible=all_observations,
        ),
        dollar_volume=_dollar_volume(calculation_arrays),
    )


__all__ = [
    "BAR_STRUCTURE_FIELDS",
    "BarStructureArrays",
    "calculate_bar_structure",
]
