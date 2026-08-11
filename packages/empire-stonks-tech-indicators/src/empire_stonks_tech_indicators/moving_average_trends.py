"""Moving-average changes and generated-distance references for V1."""

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
from empire_stonks_tech_indicators.moving_averages import (
    MOVING_AVERAGE_FIELDS,
    MovingAverageArrays,
    calculate_moving_averages,
)


MOVING_AVERAGE_CHANGE_FIELDS = (
    "sma_50_change_20d_pct",
    "sma_200_change_20d_pct",
)
MOVING_AVERAGE_DISTANCE_REFERENCE_FIELDS = (
    "pct_sma_20",
    "pct_sma_50",
    "pct_sma_200",
    "pct_ema_20",
    "pct_ema_50",
    "pct_sma_20_vs_50",
    "pct_sma_20_vs_200",
    "pct_sma_50_vs_200",
)
MOVING_AVERAGE_TREND_FIELDS = (
    *MOVING_AVERAGE_CHANGE_FIELDS,
    *MOVING_AVERAGE_DISTANCE_REFERENCE_FIELDS,
)


def _nonnullable_series(values: np.ndarray) -> MaskedFloatArray:
    null_mask = np.zeros(len(values), dtype=np.bool_)
    null_mask.setflags(write=False)
    return MaskedFloatArray(values=values, null_mask=null_mask)


def _distance_series(
    numerator: MaskedFloatArray,
    denominator: MaskedFloatArray,
    *,
    field_name: str,
    lag: int = 0,
) -> MaskedFloatArray:
    observation_count = len(numerator.values)
    values = np.full(observation_count, np.nan, dtype=np.float64)
    null_mask = np.ones(observation_count, dtype=np.bool_)

    if observation_count > lag:
        numerator_slice = slice(lag, observation_count)
        denominator_slice = slice(0, observation_count - lag)
        numerator_values = numerator.values[numerator_slice]
        denominator_values = denominator.values[denominator_slice]
        eligible = ~numerator.null_mask[numerator_slice]
        eligible &= ~denominator.null_mask[denominator_slice]
        eligible &= denominator_values != 0.0

        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            calculated = (
                numerator_values[eligible] / denominator_values[eligible] - 1.0
            )
        nonfinite = ~np.isfinite(calculated)
        if nonfinite.any():
            offset = int(np.flatnonzero(eligible)[nonfinite][0])
            raise TechIndicatorsCalculationError(
                f"{field_name} produced a non-finite value at observation "
                f"{lag + offset}."
            )

        eligible_indices = lag + np.flatnonzero(eligible)
        values[eligible_indices] = calculated
        null_mask[eligible_indices] = False
    values.setflags(write=False)
    null_mask.setflags(write=False)
    return MaskedFloatArray(values=values, null_mask=null_mask)


def _validate_moving_average_alignment(
    calculation_arrays: CalculationArrays,
    moving_averages: MovingAverageArrays,
) -> None:
    if moving_averages.source_bars != calculation_arrays.source_bars:
        raise TechIndicatorsCalculationError(
            "Moving-average inputs do not match the normalized source series."
        )
    expected = calculate_moving_averages(calculation_arrays)
    for field_name in MOVING_AVERAGE_FIELDS:
        actual_series = getattr(moving_averages, field_name)
        expected_series = getattr(expected, field_name)
        if not np.array_equal(
            actual_series.null_mask,
            expected_series.null_mask,
        ) or not np.array_equal(
            actual_series.values,
            expected_series.values,
            equal_nan=True,
        ):
            raise TechIndicatorsCalculationError(
                f"{field_name} does not match the normalized source series."
            )


@dataclass(frozen=True, eq=False)
class MovingAverageTrendArrays:
    """Python changes plus PostgreSQL-generated distance references.

    Only the two ``sma_*_change_20d_pct`` series are Python-written payload
    fields. The other series validate generated columns and do not change their
    PostgreSQL ownership.
    """

    source_bars: tuple[SourceBar, ...]
    sma_50_change_20d_pct: MaskedFloatArray
    sma_200_change_20d_pct: MaskedFloatArray
    pct_sma_20: MaskedFloatArray
    pct_sma_50: MaskedFloatArray
    pct_sma_200: MaskedFloatArray
    pct_ema_20: MaskedFloatArray
    pct_ema_50: MaskedFloatArray
    pct_sma_20_vs_50: MaskedFloatArray
    pct_sma_20_vs_200: MaskedFloatArray
    pct_sma_50_vs_200: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple):
            raise TypeError("source_bars must be a tuple.")
        if not self.source_bars:
            raise ValueError("source_bars must not be empty.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        for field_name in MOVING_AVERAGE_TREND_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != len(self.source_bars):
                raise ValueError(
                    "moving-average trend arrays must match the source "
                    "observation count."
                )

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_moving_average_trends(
    calculation_arrays: CalculationArrays,
    moving_averages: MovingAverageArrays,
) -> MovingAverageTrendArrays:
    """Calculate V1 average changes and generated-distance references."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")
    if not isinstance(moving_averages, MovingAverageArrays):
        raise TypeError("moving_averages must be MovingAverageArrays.")
    _validate_moving_average_alignment(calculation_arrays, moving_averages)

    close = _nonnullable_series(calculation_arrays.close)
    return MovingAverageTrendArrays(
        source_bars=calculation_arrays.source_bars,
        sma_50_change_20d_pct=_distance_series(
            moving_averages.sma_50,
            moving_averages.sma_50,
            field_name="sma_50_change_20d_pct",
            lag=20,
        ),
        sma_200_change_20d_pct=_distance_series(
            moving_averages.sma_200,
            moving_averages.sma_200,
            field_name="sma_200_change_20d_pct",
            lag=20,
        ),
        pct_sma_20=_distance_series(
            close,
            moving_averages.sma_20,
            field_name="pct_sma_20",
        ),
        pct_sma_50=_distance_series(
            close,
            moving_averages.sma_50,
            field_name="pct_sma_50",
        ),
        pct_sma_200=_distance_series(
            close,
            moving_averages.sma_200,
            field_name="pct_sma_200",
        ),
        pct_ema_20=_distance_series(
            close,
            moving_averages.ema_20,
            field_name="pct_ema_20",
        ),
        pct_ema_50=_distance_series(
            close,
            moving_averages.ema_50,
            field_name="pct_ema_50",
        ),
        pct_sma_20_vs_50=_distance_series(
            moving_averages.sma_20,
            moving_averages.sma_50,
            field_name="pct_sma_20_vs_50",
        ),
        pct_sma_20_vs_200=_distance_series(
            moving_averages.sma_20,
            moving_averages.sma_200,
            field_name="pct_sma_20_vs_200",
        ),
        pct_sma_50_vs_200=_distance_series(
            moving_averages.sma_50,
            moving_averages.sma_200,
            field_name="pct_sma_50_vs_200",
        ),
    )


__all__ = [
    "MOVING_AVERAGE_CHANGE_FIELDS",
    "MOVING_AVERAGE_DISTANCE_REFERENCE_FIELDS",
    "MOVING_AVERAGE_TREND_FIELDS",
    "MovingAverageTrendArrays",
    "calculate_moving_average_trends",
]
