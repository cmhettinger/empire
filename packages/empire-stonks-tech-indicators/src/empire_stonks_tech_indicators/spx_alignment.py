"""Exact-date subject/SPX close alignment and one-observation returns."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from numpy.typing import NDArray

from empire_stonks_tech_indicators.arrays import (
    CalculationArrays,
    MaskedFloatArray,
    normalize_source_bars,
)
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsCalculationError,
)
from empire_stonks_tech_indicators.models import SourceBar
from empire_stonks_tech_indicators.queries import BenchmarkHistory


FloatArray = NDArray[np.float64]
CountArray = NDArray[np.int64]


def _readonly_float64(values: object) -> FloatArray:
    result = np.ascontiguousarray(values, dtype=np.float64)
    result.setflags(write=False)
    return result


def _readonly_int64(values: object) -> CountArray:
    result = np.ascontiguousarray(values, dtype=np.int64)
    result.setflags(write=False)
    return result


def _masked_returns(
    *,
    subject_close: FloatArray,
    spx_close: FloatArray,
) -> tuple[MaskedFloatArray, MaskedFloatArray, CountArray]:
    aligned_count = len(subject_close)
    subject_values = np.full(aligned_count, np.nan, dtype=np.float64)
    spx_values = np.full(aligned_count, np.nan, dtype=np.float64)
    pair_null_mask = np.ones(aligned_count, dtype=np.bool_)
    trailing_counts = np.zeros(aligned_count, dtype=np.int64)

    if aligned_count > 1:
        subject_denominator = subject_close[:-1]
        spx_denominator = spx_close[:-1]
        subject_denominator_valid = subject_denominator != 0.0
        spx_denominator_valid = spx_denominator != 0.0

        subject_calculated = np.full(aligned_count - 1, np.nan, dtype=np.float64)
        spx_calculated = np.full(aligned_count - 1, np.nan, dtype=np.float64)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            subject_calculated[subject_denominator_valid] = (
                subject_close[1:][subject_denominator_valid]
                / subject_denominator[subject_denominator_valid]
                - 1.0
            )
            spx_calculated[spx_denominator_valid] = (
                spx_close[1:][spx_denominator_valid]
                / spx_denominator[spx_denominator_valid]
                - 1.0
            )

        for field_name, calculated, eligible in (
            (
                "subject_aligned_return_1d_pct",
                subject_calculated,
                subject_denominator_valid,
            ),
            (
                "spx_aligned_return_1d_pct",
                spx_calculated,
                spx_denominator_valid,
            ),
        ):
            nonfinite = eligible & ~np.isfinite(calculated)
            if nonfinite.any():
                aligned_index = 1 + int(np.flatnonzero(nonfinite)[0])
                raise TechIndicatorsCalculationError(
                    f"{field_name} produced a non-finite value at aligned "
                    f"observation {aligned_index}."
                )

        valid_pair = subject_denominator_valid & spx_denominator_valid
        valid_indices = 1 + np.flatnonzero(valid_pair)
        subject_values[valid_indices] = subject_calculated[valid_pair]
        spx_values[valid_indices] = spx_calculated[valid_pair]
        pair_null_mask[valid_indices] = False

        for aligned_index in range(1, aligned_count):
            if not pair_null_mask[aligned_index]:
                trailing_counts[aligned_index] = (
                    trailing_counts[aligned_index - 1] + 1
                )

    subject_values.setflags(write=False)
    spx_values.setflags(write=False)
    pair_null_mask.setflags(write=False)
    trailing_counts.setflags(write=False)
    return (
        MaskedFloatArray(values=subject_values, null_mask=pair_null_mask),
        MaskedFloatArray(values=spx_values, null_mask=pair_null_mask),
        trailing_counts,
    )


@dataclass(frozen=True, eq=False)
class AlignedReturnArrays:
    """Exact shared-date closes, returns, and subject-row alignment counts.

    The close and return arrays use compact aligned-observation order. The two
    count arrays use native subject-observation order, retaining subject dates
    that have no exact SPX bar. ``aligned_subject_observation_indices`` maps
    each compact aligned observation back to its subject row.
    """

    source_bars: tuple[SourceBar, ...]
    benchmark_history: BenchmarkHistory
    aligned_trading_dates: tuple[date, ...]
    aligned_subject_observation_indices: tuple[int, ...]
    subject_aligned_close: FloatArray
    spx_aligned_close: FloatArray
    subject_aligned_return_1d_pct: MaskedFloatArray
    spx_aligned_return_1d_pct: MaskedFloatArray
    aligned_close_observation_count: CountArray
    trailing_valid_aligned_return_count: CountArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple) or not self.source_bars:
            raise ValueError("source_bars must be a non-empty tuple.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        if not isinstance(self.benchmark_history, BenchmarkHistory):
            raise TypeError("benchmark_history must be a BenchmarkHistory.")
        if not isinstance(self.aligned_trading_dates, tuple) or any(
            type(value) is not date for value in self.aligned_trading_dates
        ):
            raise TypeError("aligned_trading_dates must contain only dates.")
        if not isinstance(self.aligned_subject_observation_indices, tuple) or any(
            type(value) is not int
            for value in self.aligned_subject_observation_indices
        ):
            raise TypeError(
                "aligned_subject_observation_indices must contain only integers."
            )

        aligned_count = len(self.aligned_trading_dates)
        if len(self.aligned_subject_observation_indices) != aligned_count:
            raise ValueError("aligned dates and subject indices must have one shape.")
        if tuple(sorted(self.aligned_trading_dates)) != self.aligned_trading_dates:
            raise ValueError("aligned_trading_dates must be chronological.")
        if len(set(self.aligned_trading_dates)) != aligned_count:
            raise ValueError("aligned_trading_dates must be unique.")
        if tuple(sorted(self.aligned_subject_observation_indices)) != (
            self.aligned_subject_observation_indices
        ):
            raise ValueError("aligned subject indices must be chronological.")
        if len(set(self.aligned_subject_observation_indices)) != aligned_count:
            raise ValueError("aligned subject indices must be unique.")
        if any(
            index < 0 or index >= len(self.source_bars)
            for index in self.aligned_subject_observation_indices
        ):
            raise ValueError("aligned subject index is out of range.")

        expected_dates = tuple(
            bar.trading_date
            for bar in self.source_bars
            if self.benchmark_history.bar_on(bar.trading_date) is not None
        )
        expected_indices = tuple(
            index
            for index, bar in enumerate(self.source_bars)
            if self.benchmark_history.bar_on(bar.trading_date) is not None
        )
        if self.aligned_trading_dates != expected_dates or (
            self.aligned_subject_observation_indices != expected_indices
        ):
            raise ValueError(
                "aligned observations must be the exact date intersection."
            )

        for field_name in ("subject_aligned_close", "spx_aligned_close"):
            values = getattr(self, field_name)
            if not isinstance(values, np.ndarray):
                raise TypeError(f"{field_name} must be a NumPy array.")
            if values.dtype != np.dtype(np.float64):
                raise TypeError(f"{field_name} must use float64 values.")
            if values.shape != (aligned_count,):
                raise ValueError(f"{field_name} must match aligned observations.")
            if not values.flags.c_contiguous or values.flags.writeable:
                raise ValueError(f"{field_name} must be contiguous and read-only.")
            if not np.isfinite(values).all():
                raise ValueError(f"{field_name} must contain finite values.")

        expected_subject_close = _readonly_float64(
            [self.source_bars[index].close for index in expected_indices]
        )
        expected_spx_close = _readonly_float64(
            [
                self.benchmark_history.bar_on(value).close
                for value in expected_dates
            ]
        )
        if not np.array_equal(self.subject_aligned_close, expected_subject_close):
            raise ValueError("subject aligned closes do not match source bars.")
        if not np.array_equal(self.spx_aligned_close, expected_spx_close):
            raise ValueError("SPX aligned closes do not match benchmark bars.")

        for field_name in (
            "subject_aligned_return_1d_pct",
            "spx_aligned_return_1d_pct",
        ):
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != aligned_count:
                raise ValueError(f"{field_name} must match aligned observations.")
        if not np.array_equal(
            self.subject_aligned_return_1d_pct.null_mask,
            self.spx_aligned_return_1d_pct.null_mask,
        ):
            raise ValueError("subject and SPX aligned returns must share a pair mask.")

        subject_count = len(self.source_bars)
        for field_name in (
            "aligned_close_observation_count",
            "trailing_valid_aligned_return_count",
        ):
            values = getattr(self, field_name)
            if not isinstance(values, np.ndarray):
                raise TypeError(f"{field_name} must be a NumPy array.")
            if values.dtype != np.dtype(np.int64):
                raise TypeError(f"{field_name} must use int64 values.")
            if values.shape != (subject_count,):
                raise ValueError(f"{field_name} must match subject observations.")
            if not values.flags.c_contiguous or values.flags.writeable:
                raise ValueError(f"{field_name} must be contiguous and read-only.")
            if (values < 0).any():
                raise ValueError(f"{field_name} must be non-negative.")

        expected_close_counts = np.zeros(subject_count, dtype=np.int64)
        aligned_seen = 0
        aligned_index_by_subject = dict(
            zip(
                self.aligned_subject_observation_indices,
                range(aligned_count),
                strict=True,
            )
        )
        expected_trailing_counts = np.zeros(subject_count, dtype=np.int64)
        aligned_trailing = 0
        return_mask = self.subject_aligned_return_1d_pct.null_mask
        for subject_index in range(subject_count):
            aligned_index = aligned_index_by_subject.get(subject_index)
            if aligned_index is not None:
                aligned_seen += 1
                if return_mask[aligned_index]:
                    aligned_trailing = 0
                else:
                    aligned_trailing += 1
                expected_trailing_counts[subject_index] = aligned_trailing
            expected_close_counts[subject_index] = aligned_seen
        if not np.array_equal(
            self.aligned_close_observation_count,
            expected_close_counts,
        ):
            raise ValueError("aligned close counts do not match exact-date history.")
        if not np.array_equal(
            self.trailing_valid_aligned_return_count,
            expected_trailing_counts,
        ):
            raise ValueError("trailing aligned return counts do not match pair masks.")

    @property
    def subject_observation_count(self) -> int:
        return len(self.source_bars)

    @property
    def aligned_observation_count(self) -> int:
        return len(self.aligned_trading_dates)


def calculate_aligned_returns(
    calculation_arrays: CalculationArrays,
    benchmark_history: BenchmarkHistory,
) -> AlignedReturnArrays:
    """Align closes by exact date and calculate common-horizon returns."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")
    if not isinstance(benchmark_history, BenchmarkHistory):
        raise TypeError("benchmark_history must be a BenchmarkHistory.")

    benchmark_arrays = (
        None
        if not benchmark_history.bars
        else normalize_source_bars(benchmark_history.bars)
    )
    aligned_dates: list[date] = []
    aligned_subject_indices: list[int] = []
    aligned_benchmark_indices: list[int] = []
    aligned_close_counts = np.zeros(
        calculation_arrays.observation_count,
        dtype=np.int64,
    )

    benchmark_index = 0
    benchmark_dates = tuple(bar.trading_date for bar in benchmark_history.bars)
    for subject_index, subject_date in enumerate(calculation_arrays.trading_dates):
        while (
            benchmark_index < len(benchmark_dates)
            and benchmark_dates[benchmark_index] < subject_date
        ):
            benchmark_index += 1
        if (
            benchmark_index < len(benchmark_dates)
            and benchmark_dates[benchmark_index] == subject_date
        ):
            aligned_dates.append(subject_date)
            aligned_subject_indices.append(subject_index)
            aligned_benchmark_indices.append(benchmark_index)
        aligned_close_counts[subject_index] = len(aligned_dates)

    subject_aligned_close = _readonly_float64(
        calculation_arrays.close[aligned_subject_indices]
    )
    spx_aligned_close = _readonly_float64(
        []
        if benchmark_arrays is None
        else benchmark_arrays.close[aligned_benchmark_indices]
    )
    (
        subject_aligned_returns,
        spx_aligned_returns,
        aligned_trailing_counts,
    ) = _masked_returns(
        subject_close=subject_aligned_close,
        spx_close=spx_aligned_close,
    )

    trailing_counts = np.zeros(
        calculation_arrays.observation_count,
        dtype=np.int64,
    )
    for aligned_index, subject_index in enumerate(aligned_subject_indices):
        trailing_counts[subject_index] = aligned_trailing_counts[aligned_index]

    aligned_close_counts.setflags(write=False)
    trailing_counts.setflags(write=False)
    return AlignedReturnArrays(
        source_bars=calculation_arrays.source_bars,
        benchmark_history=benchmark_history,
        aligned_trading_dates=tuple(aligned_dates),
        aligned_subject_observation_indices=tuple(aligned_subject_indices),
        subject_aligned_close=subject_aligned_close,
        spx_aligned_close=spx_aligned_close,
        subject_aligned_return_1d_pct=subject_aligned_returns,
        spx_aligned_return_1d_pct=spx_aligned_returns,
        aligned_close_observation_count=aligned_close_counts,
        trailing_valid_aligned_return_count=trailing_counts,
    )


__all__ = ["AlignedReturnArrays", "calculate_aligned_returns"]
