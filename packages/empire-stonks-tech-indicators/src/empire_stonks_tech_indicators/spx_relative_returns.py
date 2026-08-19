"""Compounded exact-date SPX-relative return calculations for V1."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from empire_stonks_tech_indicators.arrays import MaskedFloatArray
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsCalculationError,
)
from empire_stonks_tech_indicators.models import SourceBar
from empire_stonks_tech_indicators.spx_alignment import AlignedReturnArrays


SPX_RELATIVE_RETURN_PERIODS = (20, 63, 126, 252)
SPX_RELATIVE_RETURN_FIELDS = tuple(
    (f"relative_return_spx_{period}d_pct", period)
    for period in SPX_RELATIVE_RETURN_PERIODS
)


def _chronological_gross_return(
    returns: np.ndarray,
    *,
    field_name: str,
    side: str,
    aligned_index: int,
) -> float:
    gross = np.float64(1.0)
    for value in returns:
        with np.errstate(invalid="ignore", over="ignore", under="ignore"):
            gross = gross * (np.float64(1.0) + value)
        if not np.isfinite(gross):
            raise TechIndicatorsCalculationError(
                f"{field_name} {side} gross produced a non-finite value at "
                f"aligned observation {aligned_index}."
            )
    return float(gross)


def _aligned_relative_return(
    aligned_returns: AlignedReturnArrays,
    *,
    field_name: str,
    period: int,
) -> MaskedFloatArray:
    aligned_count = aligned_returns.aligned_observation_count
    values = np.full(aligned_count, np.nan, dtype=np.float64)
    null_mask = np.ones(aligned_count, dtype=np.bool_)
    pair_null_mask = aligned_returns.subject_aligned_return_1d_pct.null_mask

    for aligned_index in range(period, aligned_count):
        start = aligned_index - period + 1
        window = slice(start, aligned_index + 1)
        if pair_null_mask[window].any():
            continue
        subject_gross = _chronological_gross_return(
            aligned_returns.subject_aligned_return_1d_pct.values[window],
            field_name=field_name,
            side="subject",
            aligned_index=aligned_index,
        )
        spx_gross = _chronological_gross_return(
            aligned_returns.spx_aligned_return_1d_pct.values[window],
            field_name=field_name,
            side="SPX",
            aligned_index=aligned_index,
        )
        if spx_gross == 0.0:
            continue
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            calculated = subject_gross / spx_gross - 1.0
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
class SpxRelativeReturnArrays:
    """The four persisted V1 SPX-relative returns in subject-row order."""

    source_bars: tuple[SourceBar, ...]
    relative_return_spx_20d_pct: MaskedFloatArray
    relative_return_spx_63d_pct: MaskedFloatArray
    relative_return_spx_126d_pct: MaskedFloatArray
    relative_return_spx_252d_pct: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple) or not self.source_bars:
            raise ValueError("source_bars must be a non-empty tuple.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        for field_name, _ in SPX_RELATIVE_RETURN_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != len(self.source_bars):
                raise ValueError(
                    "SPX-relative return arrays must match the subject "
                    "observation count."
                )

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_spx_relative_returns(
    aligned_returns: AlignedReturnArrays,
) -> SpxRelativeReturnArrays:
    """Calculate complete compounded relative returns over aligned pairs."""

    if not isinstance(aligned_returns, AlignedReturnArrays):
        raise TypeError("aligned_returns must be AlignedReturnArrays.")

    aligned_series = {
        field_name: _aligned_relative_return(
            aligned_returns,
            field_name=field_name,
            period=period,
        )
        for field_name, period in SPX_RELATIVE_RETURN_FIELDS
    }
    return SpxRelativeReturnArrays(
        source_bars=aligned_returns.source_bars,
        **{
            field_name: _to_subject_order(
                aligned_series[field_name],
                aligned_returns=aligned_returns,
            )
            for field_name, _ in SPX_RELATIVE_RETURN_FIELDS
        },
    )


__all__ = [
    "SPX_RELATIVE_RETURN_FIELDS",
    "SPX_RELATIVE_RETURN_PERIODS",
    "SpxRelativeReturnArrays",
    "calculate_spx_relative_returns",
]
