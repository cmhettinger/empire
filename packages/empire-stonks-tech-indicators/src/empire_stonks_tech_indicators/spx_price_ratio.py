"""SPX price-ratio and aligned ratio-trend calculations for V1."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from empire_stonks_tech_indicators.arrays import MaskedFloatArray
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsCalculationError,
)
from empire_stonks_tech_indicators.models import SourceBar
from empire_stonks_tech_indicators.spx_alignment import AlignedReturnArrays


SPX_RATIO_TREND_PERIODS = (20, 50)
SPX_PRICE_RATIO_FIELDS = ("rel_spx", "pct_rel_spx_20", "pct_rel_spx_50")


def _aligned_ratio(aligned_returns: AlignedReturnArrays) -> MaskedFloatArray:
    aligned_count = aligned_returns.aligned_observation_count
    values = np.full(aligned_count, np.nan, dtype=np.float64)
    null_mask = np.ones(aligned_count, dtype=np.bool_)
    valid_denominator = aligned_returns.spx_aligned_close != 0.0

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        calculated = (
            aligned_returns.subject_aligned_close[valid_denominator]
            / aligned_returns.spx_aligned_close[valid_denominator]
        )
    nonfinite = ~np.isfinite(calculated)
    if nonfinite.any():
        aligned_index = int(np.flatnonzero(valid_denominator)[nonfinite][0])
        raise TechIndicatorsCalculationError(
            "rel_spx produced a non-finite value at aligned observation "
            f"{aligned_index}."
        )

    valid_indices = np.flatnonzero(valid_denominator)
    values[valid_indices] = calculated
    null_mask[valid_indices] = False
    values.setflags(write=False)
    null_mask.setflags(write=False)
    return MaskedFloatArray(values=values, null_mask=null_mask)


def _aligned_ratio_trend(
    ratio: MaskedFloatArray,
    *,
    period: int,
) -> MaskedFloatArray:
    field_name = f"pct_rel_spx_{period}"
    aligned_count = len(ratio.values)
    values = np.full(aligned_count, np.nan, dtype=np.float64)
    null_mask = np.ones(aligned_count, dtype=np.bool_)

    for aligned_index in range(period - 1, aligned_count):
        start = aligned_index - period + 1
        if ratio.null_mask[start : aligned_index + 1].any():
            continue
        with np.errstate(invalid="ignore", over="ignore"):
            ratio_mean = float(
                np.sum(
                    ratio.values[start : aligned_index + 1],
                    dtype=np.float64,
                )
                / period
            )
        if not np.isfinite(ratio_mean):
            raise TechIndicatorsCalculationError(
                f"{field_name} mean produced a non-finite value at aligned "
                f"observation {aligned_index}."
            )
        if ratio_mean == 0.0:
            continue
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            calculated = ratio.values[aligned_index] / ratio_mean - 1.0
        if not np.isfinite(calculated):
            raise TechIndicatorsCalculationError(
                f"{field_name} produced a non-finite value at aligned "
                f"observation {aligned_index}."
            )
        values[aligned_index] = calculated
        null_mask[aligned_index] = False

    values.setflags(write=False)
    null_mask.setflags(write=False)
    return MaskedFloatArray(values=values, null_mask=null_mask)


def _to_subject_order(
    aligned_series: MaskedFloatArray,
    *,
    aligned_returns: AlignedReturnArrays,
) -> MaskedFloatArray:
    values = np.full(
        aligned_returns.subject_observation_count,
        np.nan,
        dtype=np.float64,
    )
    null_mask = np.ones(
        aligned_returns.subject_observation_count,
        dtype=np.bool_,
    )
    indices = np.asarray(
        aligned_returns.aligned_subject_observation_indices,
        dtype=np.int64,
    )
    if len(indices):
        values[indices] = aligned_series.values
        null_mask[indices] = aligned_series.null_mask
    values.setflags(write=False)
    null_mask.setflags(write=False)
    return MaskedFloatArray(values=values, null_mask=null_mask)


@dataclass(frozen=True, eq=False)
class SpxPriceRatioArrays:
    """The three persisted V1 SPX price-ratio fields in subject-row order."""

    source_bars: tuple[SourceBar, ...]
    rel_spx: MaskedFloatArray
    pct_rel_spx_20: MaskedFloatArray
    pct_rel_spx_50: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple) or not self.source_bars:
            raise ValueError("source_bars must be a non-empty tuple.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        for field_name in SPX_PRICE_RATIO_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != len(self.source_bars):
                raise ValueError(
                    "SPX price-ratio arrays must match the subject observation "
                    "count."
                )

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_spx_price_ratios(
    aligned_returns: AlignedReturnArrays,
) -> SpxPriceRatioArrays:
    """Calculate ratio fields from exact-date aligned close observations."""

    if not isinstance(aligned_returns, AlignedReturnArrays):
        raise TypeError("aligned_returns must be AlignedReturnArrays.")

    aligned_ratio = _aligned_ratio(aligned_returns)
    aligned_trends = {
        period: _aligned_ratio_trend(aligned_ratio, period=period)
        for period in SPX_RATIO_TREND_PERIODS
    }
    return SpxPriceRatioArrays(
        source_bars=aligned_returns.source_bars,
        rel_spx=_to_subject_order(
            aligned_ratio,
            aligned_returns=aligned_returns,
        ),
        pct_rel_spx_20=_to_subject_order(
            aligned_trends[20],
            aligned_returns=aligned_returns,
        ),
        pct_rel_spx_50=_to_subject_order(
            aligned_trends[50],
            aligned_returns=aligned_returns,
        ),
    )


__all__ = [
    "SPX_PRICE_RATIO_FIELDS",
    "SPX_RATIO_TREND_PERIODS",
    "SpxPriceRatioArrays",
    "calculate_spx_price_ratios",
]
