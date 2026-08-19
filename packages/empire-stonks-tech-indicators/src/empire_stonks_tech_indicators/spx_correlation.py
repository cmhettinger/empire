"""Rolling Pearson SPX correlation calculations for V1."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from empire_stonks_tech_indicators.arrays import MaskedFloatArray
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsCalculationError,
)
from empire_stonks_tech_indicators.models import SourceBar
from empire_stonks_tech_indicators.spx_alignment import AlignedReturnArrays


SPX_CORRELATION_PERIODS = (60, 252)
SPX_CORRELATION_FIELDS = tuple(
    (f"spx_correlation_{period}d", period)
    for period in SPX_CORRELATION_PERIODS
)
SPX_CORRELATION_BOUND_TOLERANCE = 1e-12


def _canonicalize_correlation(
    value: float,
    *,
    field_name: str,
    aligned_index: int,
) -> float:
    if -1.0 <= value <= 1.0:
        return value
    if abs(value - 1.0) <= SPX_CORRELATION_BOUND_TOLERANCE:
        return 1.0
    if abs(value + 1.0) <= SPX_CORRELATION_BOUND_TOLERANCE:
        return -1.0
    raise TechIndicatorsCalculationError(
        f"{field_name} produced out-of-bounds correlation {value!r} at "
        f"aligned observation {aligned_index}."
    )


def _aligned_correlation(
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
        subject_returns = (
            aligned_returns.subject_aligned_return_1d_pct.values[window]
        )
        spx_returns = aligned_returns.spx_aligned_return_1d_pct.values[window]
        with np.errstate(invalid="ignore", over="ignore", under="ignore"):
            subject_mean = float(np.sum(subject_returns, dtype=np.float64) / period)
            spx_mean = float(np.sum(spx_returns, dtype=np.float64) / period)
            subject_deviation = subject_returns - subject_mean
            spx_deviation = spx_returns - spx_mean
            sample_covariance = float(
                np.sum(
                    subject_deviation * spx_deviation,
                    dtype=np.float64,
                )
                / (period - 1)
            )
            sample_subject_variance = float(
                np.sum(
                    subject_deviation * subject_deviation,
                    dtype=np.float64,
                )
                / (period - 1)
            )
            sample_spx_variance = float(
                np.sum(spx_deviation * spx_deviation, dtype=np.float64)
                / (period - 1)
            )

        for statistic_name, statistic in (
            ("subject mean", subject_mean),
            ("SPX mean", spx_mean),
            ("sample covariance", sample_covariance),
            ("sample subject variance", sample_subject_variance),
            ("sample SPX variance", sample_spx_variance),
        ):
            if not np.isfinite(statistic):
                raise TechIndicatorsCalculationError(
                    f"{field_name} {statistic_name} produced a non-finite "
                    f"value at aligned observation {aligned_index}."
                )
        if sample_subject_variance == 0.0 or sample_spx_variance == 0.0:
            continue
        with np.errstate(invalid="ignore", over="ignore", under="ignore"):
            denominator = float(
                np.sqrt(sample_subject_variance) * np.sqrt(sample_spx_variance)
            )
        if denominator == 0.0:
            continue
        if not np.isfinite(denominator):
            raise TechIndicatorsCalculationError(
                f"{field_name} denominator produced a non-finite value at "
                f"aligned observation {aligned_index}."
            )
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            calculated = sample_covariance / denominator
        if not np.isfinite(calculated):
            raise TechIndicatorsCalculationError(
                f"{field_name} produced a non-finite value at aligned "
                f"observation {aligned_index}."
            )
        values[aligned_index] = _canonicalize_correlation(
            calculated,
            field_name=field_name,
            aligned_index=aligned_index,
        )
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
class SpxCorrelationArrays:
    """The two persisted V1 rolling SPX correlations in subject-row order."""

    source_bars: tuple[SourceBar, ...]
    spx_correlation_60d: MaskedFloatArray
    spx_correlation_252d: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple) or not self.source_bars:
            raise ValueError("source_bars must be a non-empty tuple.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        for field_name, _ in SPX_CORRELATION_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != len(self.source_bars):
                raise ValueError(
                    "SPX correlation arrays must match the subject observation "
                    "count."
                )

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_spx_correlation(
    aligned_returns: AlignedReturnArrays,
) -> SpxCorrelationArrays:
    """Calculate complete-window sample Pearson SPX correlation."""

    if not isinstance(aligned_returns, AlignedReturnArrays):
        raise TypeError("aligned_returns must be AlignedReturnArrays.")

    aligned_series = {
        field_name: _aligned_correlation(
            aligned_returns,
            field_name=field_name,
            period=period,
        )
        for field_name, period in SPX_CORRELATION_FIELDS
    }
    return SpxCorrelationArrays(
        source_bars=aligned_returns.source_bars,
        **{
            field_name: _to_subject_order(
                aligned_series[field_name],
                aligned_returns=aligned_returns,
            )
            for field_name, _ in SPX_CORRELATION_FIELDS
        },
    )


__all__ = [
    "SPX_CORRELATION_BOUND_TOLERANCE",
    "SPX_CORRELATION_FIELDS",
    "SPX_CORRELATION_PERIODS",
    "SpxCorrelationArrays",
    "calculate_spx_correlation",
]
