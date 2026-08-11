"""Pure V1 return-volatility and return-z-score calculations."""

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
from empire_stonks_tech_indicators.returns import (
    ReturnArrays,
    calculate_returns,
)


RETURN_STATISTIC_FIELDS = (
    "return_volatility_20d_pct",
    "return_volatility_60d_pct",
    "return_1d_zscore_20d",
    "return_3d_zscore_20d",
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


def _validate_return_alignment(
    calculation_arrays: CalculationArrays,
    return_arrays: ReturnArrays,
) -> None:
    if return_arrays.source_bars != calculation_arrays.source_bars:
        raise TechIndicatorsCalculationError(
            "Return inputs do not match the normalized source series."
        )
    expected = calculate_returns(calculation_arrays)
    for field_name in ("return_1d_pct", "return_3d_pct"):
        actual_series = getattr(return_arrays, field_name)
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


def _rolling_sample_stddev(
    source: MaskedFloatArray,
    *,
    field_name: str,
    period: int,
) -> MaskedFloatArray:
    observation_count = len(source.values)
    values = np.full(observation_count, np.nan, dtype=np.float64)
    null_mask = np.ones(observation_count, dtype=np.bool_)
    if observation_count >= period:
        value_windows = np.lib.stride_tricks.sliding_window_view(
            source.values,
            period,
        )
        mask_windows = np.lib.stride_tricks.sliding_window_view(
            source.null_mask,
            period,
        )
        complete = ~np.any(mask_windows, axis=1)
        with np.errstate(invalid="ignore", over="ignore"):
            calculated = np.std(
                value_windows[complete],
                axis=1,
                ddof=1,
            )
        nonfinite = ~np.isfinite(calculated)
        if nonfinite.any():
            window_offset = int(np.flatnonzero(complete)[nonfinite][0])
            observation = period - 1 + window_offset
            raise TechIndicatorsCalculationError(
                f"{field_name} produced a non-finite value at observation "
                f"{observation}."
            )
        eligible_indices = period - 1 + np.flatnonzero(complete)
        values[eligible_indices] = calculated
        null_mask[eligible_indices] = False
    return _masked_series(values, null_mask)


def _prior_reference_zscore(
    source: MaskedFloatArray,
    *,
    field_name: str,
) -> MaskedFloatArray:
    reference_period = 20
    observation_count = len(source.values)
    values = np.full(observation_count, np.nan, dtype=np.float64)
    null_mask = np.ones(observation_count, dtype=np.bool_)
    if observation_count > reference_period:
        reference_values = np.lib.stride_tricks.sliding_window_view(
            source.values[:-1],
            reference_period,
        )
        reference_masks = np.lib.stride_tricks.sliding_window_view(
            source.null_mask[:-1],
            reference_period,
        )
        tested_values = source.values[reference_period:]
        tested_masks = source.null_mask[reference_period:]
        complete = (~tested_masks) & (~np.any(reference_masks, axis=1))
        complete_references = reference_values[complete]
        with np.errstate(invalid="ignore", over="ignore"):
            means = np.mean(complete_references, axis=1)
            sample_stddevs = np.std(
                complete_references,
                axis=1,
                ddof=1,
            )
        nonfinite_reference = (~np.isfinite(means)) | (
            ~np.isfinite(sample_stddevs)
        )
        if nonfinite_reference.any():
            offset = int(np.flatnonzero(complete)[nonfinite_reference][0])
            observation = reference_period + offset
            raise TechIndicatorsCalculationError(
                f"{field_name} reference produced a non-finite value at "
                f"observation {observation}."
            )
        nonzero_stddev = sample_stddevs != 0.0
        complete_indices = np.flatnonzero(complete)
        eligible_offsets = complete_indices[nonzero_stddev]
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            calculated = (
                tested_values[eligible_offsets]
                - means[nonzero_stddev]
            ) / sample_stddevs[nonzero_stddev]
        nonfinite = ~np.isfinite(calculated)
        if nonfinite.any():
            observation = reference_period + int(
                eligible_offsets[nonfinite][0]
            )
            raise TechIndicatorsCalculationError(
                f"{field_name} produced a non-finite value at observation "
                f"{observation}."
            )
        eligible_indices = reference_period + eligible_offsets
        values[eligible_indices] = calculated
        null_mask[eligible_indices] = False
    return _masked_series(values, null_mask)


@dataclass(frozen=True, eq=False)
class ReturnStatisticArrays:
    """The four V1 return-statistic fields in source observation order."""

    return_volatility_20d_pct: MaskedFloatArray
    return_volatility_60d_pct: MaskedFloatArray
    return_1d_zscore_20d: MaskedFloatArray
    return_3d_zscore_20d: MaskedFloatArray

    def __post_init__(self) -> None:
        lengths: set[int] = set()
        for field_name in RETURN_STATISTIC_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            lengths.add(len(series.values))
        if len(lengths) != 1:
            raise ValueError(
                "return statistic arrays must have one observation count."
            )

    @property
    def observation_count(self) -> int:
        return len(self.return_volatility_20d_pct.values)


def calculate_return_statistics(
    calculation_arrays: CalculationArrays,
    return_arrays: ReturnArrays,
) -> ReturnStatisticArrays:
    """Calculate sample volatility and prior-reference return z-scores."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")
    if not isinstance(return_arrays, ReturnArrays):
        raise TypeError("return_arrays must be ReturnArrays.")
    _validate_return_alignment(calculation_arrays, return_arrays)

    return ReturnStatisticArrays(
        return_volatility_20d_pct=_rolling_sample_stddev(
            return_arrays.return_1d_pct,
            field_name="return_volatility_20d_pct",
            period=20,
        ),
        return_volatility_60d_pct=_rolling_sample_stddev(
            return_arrays.return_1d_pct,
            field_name="return_volatility_60d_pct",
            period=60,
        ),
        return_1d_zscore_20d=_prior_reference_zscore(
            return_arrays.return_1d_pct,
            field_name="return_1d_zscore_20d",
        ),
        return_3d_zscore_20d=_prior_reference_zscore(
            return_arrays.return_3d_pct,
            field_name="return_3d_zscore_20d",
        ),
    )


__all__ = [
    "RETURN_STATISTIC_FIELDS",
    "ReturnStatisticArrays",
    "calculate_return_statistics",
]
