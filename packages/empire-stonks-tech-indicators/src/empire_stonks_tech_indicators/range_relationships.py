"""Pure complete-window high and low calculations for V1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from empire_stonks_tech_indicators.arrays import (
    CalculationArrays,
    MaskedFloatArray,
)
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsCalculationError,
)


HIGH_PERIODS = (20, 50, 252)
LOW_PERIODS = (20, 50)
RANGE_RELATIONSHIP_FIELDS = (
    "hh_20",
    "hh_50",
    "hh_252",
    "ll_20",
    "ll_50",
)


def _rolling_extreme(
    source: np.ndarray,
    *,
    field_name: str,
    period: int,
    operation: Literal["maximum", "minimum"],
) -> MaskedFloatArray:
    observation_count = len(source)
    values = np.full(observation_count, np.nan, dtype=np.float64)
    null_mask = np.ones(observation_count, dtype=np.bool_)

    if observation_count >= period:
        windows = np.lib.stride_tricks.sliding_window_view(source, period)
        if operation == "maximum":
            calculated = np.max(windows, axis=1)
        else:
            calculated = np.min(windows, axis=1)
        nonfinite = ~np.isfinite(calculated)
        if nonfinite.any():
            observation = period - 1 + int(np.flatnonzero(nonfinite)[0])
            raise TechIndicatorsCalculationError(
                f"{field_name} produced a non-finite value at observation "
                f"{observation}."
            )
        values[period - 1 :] = calculated
        null_mask[period - 1 :] = False

    values = np.ascontiguousarray(values)
    null_mask = np.ascontiguousarray(null_mask)
    values.setflags(write=False)
    null_mask.setflags(write=False)
    return MaskedFloatArray(values=values, null_mask=null_mask)


@dataclass(frozen=True, eq=False)
class RangeRelationshipArrays:
    """V1 rolling high and low levels in source observation order."""

    hh_20: MaskedFloatArray
    hh_50: MaskedFloatArray
    hh_252: MaskedFloatArray
    ll_20: MaskedFloatArray
    ll_50: MaskedFloatArray

    def __post_init__(self) -> None:
        lengths: set[int] = set()
        for field_name in RANGE_RELATIONSHIP_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            lengths.add(len(series.values))
        if len(lengths) != 1:
            raise ValueError(
                "range relationship arrays must have one observation count."
            )

    @property
    def observation_count(self) -> int:
        return len(self.hh_20.values)


def calculate_range_relationships(
    calculation_arrays: CalculationArrays,
) -> RangeRelationshipArrays:
    """Calculate complete trailing highs and lows with no future access."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")

    return RangeRelationshipArrays(
        hh_20=_rolling_extreme(
            calculation_arrays.high,
            field_name="hh_20",
            period=20,
            operation="maximum",
        ),
        hh_50=_rolling_extreme(
            calculation_arrays.high,
            field_name="hh_50",
            period=50,
            operation="maximum",
        ),
        hh_252=_rolling_extreme(
            calculation_arrays.high,
            field_name="hh_252",
            period=252,
            operation="maximum",
        ),
        ll_20=_rolling_extreme(
            calculation_arrays.low,
            field_name="ll_20",
            period=20,
            operation="minimum",
        ),
        ll_50=_rolling_extreme(
            calculation_arrays.low,
            field_name="ll_50",
            period=50,
            operation="minimum",
        ),
    )


__all__ = [
    "HIGH_PERIODS",
    "LOW_PERIODS",
    "RANGE_RELATIONSHIP_FIELDS",
    "RangeRelationshipArrays",
    "calculate_range_relationships",
]
