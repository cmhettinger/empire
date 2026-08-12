"""MACD calculations for TECH_INDICATORS_V1."""

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
from empire_stonks_tech_indicators.moving_averages import MovingAverageArrays
from empire_stonks_tech_indicators.talib_adapter import TALibAdapter


MACD_FAST_PERIOD = 12
MACD_SLOW_PERIOD = 26
MACD_SIGNAL_PERIOD = 9
MACD_FIELDS = (
    "macd_12_26",
    "macd_signal_12_26_9",
    "macd_histogram_12_26_9",
    "macd_12_26_pct",
    "macd_histogram_12_26_9_pct",
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


def _validate_ema_26_alignment(
    calculation_arrays: CalculationArrays,
    moving_averages: MovingAverageArrays,
    expected_ema_26: MaskedFloatArray,
) -> None:
    if moving_averages.source_bars != calculation_arrays.source_bars:
        raise TechIndicatorsCalculationError(
            "Moving-average inputs do not match the normalized source series."
        )
    if not np.array_equal(
        moving_averages.ema_26.null_mask,
        expected_ema_26.null_mask,
    ) or not np.array_equal(
        moving_averages.ema_26.values,
        expected_ema_26.values,
        equal_nan=True,
    ):
        raise TechIndicatorsCalculationError(
            "ema_26 does not match the normalized source series."
        )


def _normalized_reference(
    numerator: MaskedFloatArray,
    denominator: np.ndarray,
    denominator_null_mask: np.ndarray,
    *,
    output_name: str,
) -> MaskedFloatArray:
    values = np.full(len(numerator.values), np.nan, dtype=np.float64)
    null_mask = np.ones(len(numerator.values), dtype=np.bool_)
    populated = ~numerator.null_mask & ~denominator_null_mask
    eligible = populated & (np.abs(denominator) != 0.0)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        normalized = numerator.values[eligible] / np.abs(denominator[eligible])
    if not np.isfinite(normalized).all():
        failing_offset = int(np.flatnonzero(~np.isfinite(normalized))[0])
        failing_index = int(np.flatnonzero(eligible)[failing_offset])
        raise TechIndicatorsCalculationError(
            f"{output_name} produced a non-finite value at observation "
            f"{failing_index}."
        )
    values[eligible] = normalized
    null_mask[eligible] = False
    return _masked_series(values, null_mask)


@dataclass(frozen=True, eq=False)
class MacdArrays:
    """Raw MACD outputs plus PostgreSQL-generated reference values.

    Only the line, signal, and histogram are Python-written. The two
    normalized arrays are reference values used to validate generated columns.
    """

    source_bars: tuple[SourceBar, ...]
    macd_12_26: MaskedFloatArray
    macd_signal_12_26_9: MaskedFloatArray
    macd_histogram_12_26_9: MaskedFloatArray
    macd_12_26_pct: MaskedFloatArray
    macd_histogram_12_26_9_pct: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple):
            raise TypeError("source_bars must be a tuple.")
        if not self.source_bars:
            raise ValueError("source_bars must not be empty.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        for field_name in MACD_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != len(self.source_bars):
                raise ValueError(
                    "MACD arrays must match the source observation count."
                )

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_macd(
    calculation_arrays: CalculationArrays,
    moving_averages: MovingAverageArrays,
) -> MacdArrays:
    """Calculate the fixed 12/26/9 MACD profile from the complete prefix."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")
    if not isinstance(moving_averages, MovingAverageArrays):
        raise TypeError("moving_averages must be MovingAverageArrays.")

    adapter = TALibAdapter(calculation_arrays)
    expected_ema_26 = adapter.ema(timeperiod=MACD_SLOW_PERIOD)
    _validate_ema_26_alignment(
        calculation_arrays,
        moving_averages,
        expected_ema_26,
    )
    line, signal, histogram = adapter.macd(
        fastperiod=MACD_FAST_PERIOD,
        slowperiod=MACD_SLOW_PERIOD,
        signalperiod=MACD_SIGNAL_PERIOD,
    )
    return MacdArrays(
        source_bars=calculation_arrays.source_bars,
        macd_12_26=line,
        macd_signal_12_26_9=signal,
        macd_histogram_12_26_9=histogram,
        macd_12_26_pct=_normalized_reference(
            line,
            moving_averages.ema_26.values,
            moving_averages.ema_26.null_mask,
            output_name="macd_12_26_pct",
        ),
        macd_histogram_12_26_9_pct=_normalized_reference(
            histogram,
            calculation_arrays.close,
            np.zeros(calculation_arrays.observation_count, dtype=np.bool_),
            output_name="macd_histogram_12_26_9_pct",
        ),
    )


__all__ = [
    "MACD_FAST_PERIOD",
    "MACD_FIELDS",
    "MACD_SIGNAL_PERIOD",
    "MACD_SLOW_PERIOD",
    "MacdArrays",
    "calculate_macd",
]
