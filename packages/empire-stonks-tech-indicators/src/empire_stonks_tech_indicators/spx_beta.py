"""Rolling sample-covariance SPX beta calculations for V1."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from empire_stonks_tech_indicators.arrays import MaskedFloatArray
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsCalculationError,
)
from empire_stonks_tech_indicators.models import SourceBar
from empire_stonks_tech_indicators.spx_alignment import AlignedReturnArrays


SPX_BETA_PERIODS = (60, 252)
SPX_BETA_FIELDS = tuple(
    (f"spx_beta_{period}d", period) for period in SPX_BETA_PERIODS
)


def _aligned_beta(
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
            sample_spx_variance = float(
                np.sum(spx_deviation * spx_deviation, dtype=np.float64)
                / (period - 1)
            )

        for statistic_name, statistic in (
            ("subject mean", subject_mean),
            ("SPX mean", spx_mean),
            ("sample covariance", sample_covariance),
            ("sample SPX variance", sample_spx_variance),
        ):
            if not np.isfinite(statistic):
                raise TechIndicatorsCalculationError(
                    f"{field_name} {statistic_name} produced a non-finite "
                    f"value at aligned observation {aligned_index}."
                )
        if sample_spx_variance == 0.0:
            continue
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            calculated = sample_covariance / sample_spx_variance
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
class SpxBetaArrays:
    """The two persisted V1 rolling SPX beta fields in subject-row order."""

    source_bars: tuple[SourceBar, ...]
    spx_beta_60d: MaskedFloatArray
    spx_beta_252d: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple) or not self.source_bars:
            raise ValueError("source_bars must be a non-empty tuple.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        for field_name, _ in SPX_BETA_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != len(self.source_bars):
                raise ValueError(
                    "SPX beta arrays must match the subject observation count."
                )

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_spx_beta(
    aligned_returns: AlignedReturnArrays,
) -> SpxBetaArrays:
    """Calculate complete-window sample-covariance SPX beta."""

    if not isinstance(aligned_returns, AlignedReturnArrays):
        raise TypeError("aligned_returns must be AlignedReturnArrays.")

    aligned_series = {
        field_name: _aligned_beta(
            aligned_returns,
            field_name=field_name,
            period=period,
        )
        for field_name, period in SPX_BETA_FIELDS
    }
    return SpxBetaArrays(
        source_bars=aligned_returns.source_bars,
        **{
            field_name: _to_subject_order(
                aligned_series[field_name],
                aligned_returns=aligned_returns,
            )
            for field_name, _ in SPX_BETA_FIELDS
        },
    )


__all__ = [
    "SPX_BETA_FIELDS",
    "SPX_BETA_PERIODS",
    "SpxBetaArrays",
    "calculate_spx_beta",
]
