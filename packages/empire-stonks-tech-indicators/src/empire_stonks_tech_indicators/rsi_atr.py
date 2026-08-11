"""Wilder RSI and ATR calculations for TECH_INDICATORS_V1."""

from __future__ import annotations

from dataclasses import dataclass

from empire_stonks_tech_indicators.arrays import (
    CalculationArrays,
    MaskedFloatArray,
)
from empire_stonks_tech_indicators.models import SourceBar
from empire_stonks_tech_indicators.talib_adapter import TALibAdapter


RSI_ATR_PERIOD = 14
RSI_ATR_FIELDS = ("rsi_14", "atr_14")


@dataclass(frozen=True, eq=False)
class RsiAtrArrays:
    """The V1 RSI 14 and ATR 14 fields in source observation order."""

    source_bars: tuple[SourceBar, ...]
    rsi_14: MaskedFloatArray
    atr_14: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple):
            raise TypeError("source_bars must be a tuple.")
        if not self.source_bars:
            raise ValueError("source_bars must not be empty.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        for field_name in RSI_ATR_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != len(self.source_bars):
                raise ValueError(
                    "RSI and ATR arrays must match the source observation count."
                )

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_rsi_atr(calculation_arrays: CalculationArrays) -> RsiAtrArrays:
    """Calculate pinned Wilder RSI 14 and ATR 14 from the complete prefix."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")

    adapter = TALibAdapter(calculation_arrays)
    return RsiAtrArrays(
        source_bars=calculation_arrays.source_bars,
        rsi_14=adapter.rsi(timeperiod=RSI_ATR_PERIOD),
        atr_14=adapter.atr(timeperiod=RSI_ATR_PERIOD),
    )


__all__ = [
    "RSI_ATR_FIELDS",
    "RSI_ATR_PERIOD",
    "RsiAtrArrays",
    "calculate_rsi_atr",
]
