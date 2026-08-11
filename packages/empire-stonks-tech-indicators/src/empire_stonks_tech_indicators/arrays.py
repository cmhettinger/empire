"""Strict source-bar normalization for technical-indicator calculations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from math import isfinite
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsCalculationError,
)
from empire_stonks_tech_indicators.models import SourceBar


FloatArray = NDArray[np.float64]
NullMask = NDArray[np.bool_]


def _calculation_error(message: str) -> TechIndicatorsCalculationError:
    return TechIndicatorsCalculationError(message)


def _to_float64(field_name: str, bars: tuple[SourceBar, ...]) -> FloatArray:
    values: list[float] = []
    for index, bar in enumerate(bars):
        source_value = getattr(bar, field_name)
        if source_value is None:
            values.append(np.nan)
            continue
        try:
            value = float(source_value)
        except (OverflowError, ValueError) as error:
            raise _calculation_error(
                f"{field_name} at observation {index} cannot be converted to float64."
            ) from error
        if not isfinite(value):
            raise _calculation_error(
                f"{field_name} at observation {index} is non-finite after "
                "float64 conversion."
            )
        values.append(value)

    result = np.ascontiguousarray(values, dtype=np.float64)
    result.setflags(write=False)
    return result


def _volume_null_mask(bars: tuple[SourceBar, ...]) -> NullMask:
    result = np.ascontiguousarray(
        [bar.volume is None for bar in bars],
        dtype=np.bool_,
    )
    result.setflags(write=False)
    return result


@dataclass(frozen=True, eq=False)
class CalculationArrays:
    """One strictly chronological provider listing as calculation arrays.

    The source-bar tuple retains exact ``Decimal`` values for later source-copy
    validation. Numerical arrays are read-only, C-contiguous ``float64``
    values in the same observation order. ``volume_null_mask`` is authoritative
    for missing volume; matching volume positions contain ``NaN``, never a
    synthesized zero.
    """

    source_bars: tuple[SourceBar, ...]
    open: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray
    volume: FloatArray
    volume_null_mask: NullMask

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple):
            raise TypeError("source_bars must be a tuple.")
        if not self.source_bars:
            raise ValueError("source_bars must contain at least one observation.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")

        provider_listing_id = self.source_bars[0].provider_listing_id
        previous_date: date | None = None
        for bar in self.source_bars:
            if bar.provider_listing_id != provider_listing_id:
                raise ValueError("source_bars must contain one provider listing.")
            if previous_date is not None and bar.trading_date <= previous_date:
                raise ValueError("source_bars must be strictly chronological.")
            previous_date = bar.trading_date

        observation_count = len(self.source_bars)
        for field_name in ("open", "high", "low", "close", "volume"):
            values = getattr(self, field_name)
            if not isinstance(values, np.ndarray):
                raise TypeError(f"{field_name} must be a NumPy array.")
            if values.dtype != np.dtype(np.float64):
                raise TypeError(f"{field_name} must use float64 values.")
            if values.shape != (observation_count,):
                raise ValueError(
                    f"{field_name} must have one value per source observation."
                )
            if not values.flags.c_contiguous:
                raise ValueError(f"{field_name} must be C-contiguous.")
            if values.flags.writeable:
                raise ValueError(f"{field_name} must be read-only.")

        mask = self.volume_null_mask
        if not isinstance(mask, np.ndarray):
            raise TypeError("volume_null_mask must be a NumPy array.")
        if mask.dtype != np.dtype(np.bool_):
            raise TypeError("volume_null_mask must use boolean values.")
        if mask.shape != (observation_count,):
            raise ValueError(
                "volume_null_mask must have one value per source observation."
            )
        if not mask.flags.c_contiguous:
            raise ValueError("volume_null_mask must be C-contiguous.")
        if mask.flags.writeable:
            raise ValueError("volume_null_mask must be read-only.")

        expected_mask = np.fromiter(
            (bar.volume is None for bar in self.source_bars),
            dtype=np.bool_,
            count=observation_count,
        )
        if not np.array_equal(mask, expected_mask):
            raise ValueError("volume_null_mask does not match source volume nulls.")
        if not np.isnan(self.volume[mask]).all():
            raise ValueError("null source volume positions must contain NaN.")
        if not np.isfinite(self.volume[~mask]).all():
            raise ValueError("populated source volume positions must be finite.")
        for field_name in ("open", "high", "low", "close"):
            if not np.isfinite(getattr(self, field_name)).all():
                raise ValueError(f"{field_name} must contain only finite values.")
        for field_name in ("open", "high", "low", "close", "volume"):
            expected = _to_float64(field_name, self.source_bars)
            if not np.array_equal(
                getattr(self, field_name),
                expected,
                equal_nan=True,
            ):
                raise ValueError(
                    f"{field_name} does not match the attached source bars."
                )

    @property
    def provider_listing_id(self) -> UUID:
        return self.source_bars[0].provider_listing_id

    @property
    def trading_dates(self) -> tuple[date, ...]:
        return tuple(bar.trading_date for bar in self.source_bars)

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def normalize_source_bars(source_bars: Iterable[SourceBar]) -> CalculationArrays:
    """Convert one already ordered source series without sorting or filling it."""

    try:
        bars = tuple(source_bars)
    except TypeError as error:
        raise TypeError(
            "source_bars must be an iterable of SourceBar records."
        ) from error

    if not bars:
        raise _calculation_error("Cannot normalize an empty source-bar series.")
    if any(not isinstance(bar, SourceBar) for bar in bars):
        raise TypeError("source_bars must contain only SourceBar records.")

    provider_listing_id = bars[0].provider_listing_id
    previous_date: date | None = None
    for index, bar in enumerate(bars):
        if bar.provider_listing_id != provider_listing_id:
            raise _calculation_error(
                "Calculation input must contain exactly one provider listing."
            )
        if previous_date is not None and bar.trading_date <= previous_date:
            raise _calculation_error(
                "Calculation input must be strictly ordered by trading_date; "
                f"observation {index} is duplicate or out of order."
            )
        previous_date = bar.trading_date

    return CalculationArrays(
        source_bars=bars,
        open=_to_float64("open", bars),
        high=_to_float64("high", bars),
        low=_to_float64("low", bars),
        close=_to_float64("close", bars),
        volume=_to_float64("volume", bars),
        volume_null_mask=_volume_null_mask(bars),
    )


__all__ = ["CalculationArrays", "normalize_source_bars"]
