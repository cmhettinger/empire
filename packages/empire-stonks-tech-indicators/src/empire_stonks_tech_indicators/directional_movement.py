"""Directional movement calculations for TECH_INDICATORS_V1."""

from __future__ import annotations

from dataclasses import dataclass

from empire_stonks_tech_indicators.arrays import (
    CalculationArrays,
    MaskedFloatArray,
)
from empire_stonks_tech_indicators.models import SourceBar
from empire_stonks_tech_indicators.talib_adapter import TALibAdapter


DIRECTIONAL_MOVEMENT_PERIOD = 14
DIRECTIONAL_MOVEMENT_FIELDS = ("plus_di_14", "minus_di_14", "adx_14")


@dataclass(frozen=True, eq=False)
class DirectionalMovementArrays:
    """The V1 +DI 14, -DI 14, and ADX 14 fields in observation order."""

    source_bars: tuple[SourceBar, ...]
    plus_di_14: MaskedFloatArray
    minus_di_14: MaskedFloatArray
    adx_14: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple):
            raise TypeError("source_bars must be a tuple.")
        if not self.source_bars:
            raise ValueError("source_bars must not be empty.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        for field_name in DIRECTIONAL_MOVEMENT_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != len(self.source_bars):
                raise ValueError(
                    "Directional-movement arrays must match the source "
                    "observation count."
                )

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_directional_movement(
    calculation_arrays: CalculationArrays,
) -> DirectionalMovementArrays:
    """Calculate pinned Wilder +DI, -DI, and ADX from the complete prefix."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")

    adapter = TALibAdapter(calculation_arrays)
    return DirectionalMovementArrays(
        source_bars=calculation_arrays.source_bars,
        plus_di_14=adapter.plus_di(timeperiod=DIRECTIONAL_MOVEMENT_PERIOD),
        minus_di_14=adapter.minus_di(timeperiod=DIRECTIONAL_MOVEMENT_PERIOD),
        adx_14=adapter.adx(timeperiod=DIRECTIONAL_MOVEMENT_PERIOD),
    )


__all__ = [
    "DIRECTIONAL_MOVEMENT_FIELDS",
    "DIRECTIONAL_MOVEMENT_PERIOD",
    "DirectionalMovementArrays",
    "calculate_directional_movement",
]
