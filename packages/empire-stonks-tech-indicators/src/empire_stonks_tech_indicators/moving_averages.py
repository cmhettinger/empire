"""SMA and EMA calculations for TECH_INDICATORS_V1."""

from __future__ import annotations

from dataclasses import dataclass

from empire_stonks_tech_indicators.arrays import (
    CalculationArrays,
    MaskedFloatArray,
)
from empire_stonks_tech_indicators.models import SourceBar
from empire_stonks_tech_indicators.talib_adapter import TALibAdapter


SMA_PERIODS = (20, 50, 200)
EMA_PERIODS = (12, 20, 26, 50)
MOVING_AVERAGE_FIELDS = (
    *(f"sma_{period}" for period in SMA_PERIODS),
    *(f"ema_{period}" for period in EMA_PERIODS),
)


@dataclass(frozen=True, eq=False)
class MovingAverageArrays:
    """The seven V1 moving-average fields in source observation order."""

    source_bars: tuple[SourceBar, ...]
    sma_20: MaskedFloatArray
    sma_50: MaskedFloatArray
    sma_200: MaskedFloatArray
    ema_12: MaskedFloatArray
    ema_20: MaskedFloatArray
    ema_26: MaskedFloatArray
    ema_50: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple):
            raise TypeError("source_bars must be a tuple.")
        if not self.source_bars:
            raise ValueError("source_bars must not be empty.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        for field_name in MOVING_AVERAGE_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != len(self.source_bars):
                raise ValueError(
                    "moving-average arrays must match the source observation "
                    "count."
                )

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_moving_averages(
    calculation_arrays: CalculationArrays,
) -> MovingAverageArrays:
    """Calculate every frozen V1 SMA and EMA from the complete source prefix."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")

    adapter = TALibAdapter(calculation_arrays)
    return MovingAverageArrays(
        source_bars=calculation_arrays.source_bars,
        sma_20=adapter.sma(timeperiod=20),
        sma_50=adapter.sma(timeperiod=50),
        sma_200=adapter.sma(timeperiod=200),
        ema_12=adapter.ema(timeperiod=12),
        ema_20=adapter.ema(timeperiod=20),
        ema_26=adapter.ema(timeperiod=26),
        ema_50=adapter.ema(timeperiod=50),
    )


__all__ = [
    "EMA_PERIODS",
    "MOVING_AVERAGE_FIELDS",
    "SMA_PERIODS",
    "MovingAverageArrays",
    "calculate_moving_averages",
]
