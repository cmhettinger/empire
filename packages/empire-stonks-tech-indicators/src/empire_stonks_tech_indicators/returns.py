"""Pure observation-return calculations for TECH_INDICATORS_V1."""

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


RETURN_PERIODS = (1, 2, 3, 5, 10, 20, 63, 126, 252)
RETURN_FIELDS = tuple((f"return_{period}d_pct", period) for period in RETURN_PERIODS)


def _return_series(
    calculation_arrays: CalculationArrays,
    *,
    field_name: str,
    period: int,
) -> MaskedFloatArray:
    observation_count = calculation_arrays.observation_count
    values = np.full(observation_count, np.nan, dtype=np.float64)
    null_mask = np.ones(observation_count, dtype=np.bool_)

    if observation_count > period:
        prior_close = calculation_arrays.close[:-period]
        current_close = calculation_arrays.close[period:]
        valid_denominator = prior_close != 0.0
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            calculated = (
                current_close[valid_denominator]
                / prior_close[valid_denominator]
                - 1.0
            )
        nonfinite = ~np.isfinite(calculated)
        if nonfinite.any():
            first_offset = int(np.flatnonzero(valid_denominator)[nonfinite][0])
            raise TechIndicatorsCalculationError(
                f"{field_name} produced a non-finite value at observation "
                f"{period + first_offset}."
            )

        eligible_indices = np.arange(period, observation_count)[valid_denominator]
        values[eligible_indices] = calculated
        null_mask[eligible_indices] = False

    values = np.ascontiguousarray(values)
    null_mask = np.ascontiguousarray(null_mask)
    values.setflags(write=False)
    null_mask.setflags(write=False)
    return MaskedFloatArray(values=values, null_mask=null_mask)


@dataclass(frozen=True, eq=False)
class ReturnArrays:
    """The nine V1 observation-return fields in source observation order."""

    source_bars: tuple[SourceBar, ...]
    return_1d_pct: MaskedFloatArray
    return_2d_pct: MaskedFloatArray
    return_3d_pct: MaskedFloatArray
    return_5d_pct: MaskedFloatArray
    return_10d_pct: MaskedFloatArray
    return_20d_pct: MaskedFloatArray
    return_63d_pct: MaskedFloatArray
    return_126d_pct: MaskedFloatArray
    return_252d_pct: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple):
            raise TypeError("source_bars must be a tuple.")
        if not self.source_bars:
            raise ValueError("source_bars must not be empty.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        lengths: set[int] = set()
        for field_name, _ in RETURN_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            lengths.add(len(series.values))
        if len(lengths) != 1:
            raise ValueError("return arrays must have one common observation count.")
        if lengths != {len(self.source_bars)}:
            raise ValueError(
                "return arrays must match the source observation count."
            )

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_returns(calculation_arrays: CalculationArrays) -> ReturnArrays:
    """Calculate every frozen V1 return without calendar fill or look-ahead."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")

    return ReturnArrays(
        source_bars=calculation_arrays.source_bars,
        **{
            field_name: _return_series(
                calculation_arrays,
                field_name=field_name,
                period=period,
            )
            for field_name, period in RETURN_FIELDS
        }
    )


__all__ = [
    "RETURN_FIELDS",
    "RETURN_PERIODS",
    "ReturnArrays",
    "calculate_returns",
]
