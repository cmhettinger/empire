"""Bollinger state calculations for TECH_INDICATORS_V1."""

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
from empire_stonks_tech_indicators.models import SourceBar
from empire_stonks_tech_indicators.moving_averages import MovingAverageArrays
from empire_stonks_tech_indicators.talib_adapter import TALibAdapter


BOLLINGER_PERIOD = 20
BOLLINGER_DEVIATIONS = 2.0
BOLLINGER_FIELDS = (
    "price_stddev_20",
    "bollinger_percent_b_20_2",
    "bollinger_bandwidth_20_2",
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


def _validate_sma_20_alignment(
    calculation_arrays: CalculationArrays,
    moving_averages: MovingAverageArrays,
    expected_sma_20: MaskedFloatArray,
) -> None:
    if moving_averages.source_bars != calculation_arrays.source_bars:
        raise TechIndicatorsCalculationError(
            "Moving-average inputs do not match the normalized source series."
        )
    if not np.array_equal(
        moving_averages.sma_20.null_mask,
        expected_sma_20.null_mask,
    ) or not np.array_equal(
        moving_averages.sma_20.values,
        expected_sma_20.values,
        equal_nan=True,
    ):
        raise TechIndicatorsCalculationError(
            "sma_20 does not match the normalized source series."
        )


def _generated_references(
    calculation_arrays: CalculationArrays,
    sma_20: MaskedFloatArray,
    price_stddev_20: MaskedFloatArray,
) -> tuple[MaskedFloatArray, MaskedFloatArray]:
    observation_count = calculation_arrays.observation_count
    percent_b_values = np.full(observation_count, np.nan, dtype=np.float64)
    percent_b_mask = np.ones(observation_count, dtype=np.bool_)
    bandwidth_values = np.full(observation_count, np.nan, dtype=np.float64)
    bandwidth_mask = np.ones(observation_count, dtype=np.bool_)

    populated = ~sma_20.null_mask & ~price_stddev_20.null_mask
    populated_indices = np.flatnonzero(populated)
    with np.errstate(invalid="ignore", over="ignore"):
        upper = (
            sma_20.values[populated]
            + BOLLINGER_DEVIATIONS * price_stddev_20.values[populated]
        )
        lower = (
            sma_20.values[populated]
            - BOLLINGER_DEVIATIONS * price_stddev_20.values[populated]
        )
        width = upper - lower
    finite_intermediates = np.isfinite(upper) & np.isfinite(lower)
    finite_intermediates &= np.isfinite(width)
    if not finite_intermediates.all():
        offset = int(np.flatnonzero(~finite_intermediates)[0])
        raise TechIndicatorsCalculationError(
            "Bollinger band reconstruction produced a non-finite value at "
            f"observation {int(populated_indices[offset])}."
        )

    percent_b_eligible = width != 0.0
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        percent_b = (
            calculation_arrays.close[populated][percent_b_eligible]
            - lower[percent_b_eligible]
        ) / width[percent_b_eligible]
    if not np.isfinite(percent_b).all():
        offset = int(np.flatnonzero(percent_b_eligible)[~np.isfinite(percent_b)][0])
        raise TechIndicatorsCalculationError(
            "bollinger_percent_b_20_2 produced a non-finite value at "
            f"observation {int(populated_indices[offset])}."
        )
    percent_b_indices = populated_indices[percent_b_eligible]
    percent_b_values[percent_b_indices] = percent_b
    percent_b_mask[percent_b_indices] = False

    middle = sma_20.values[populated]
    bandwidth_eligible = np.abs(middle) != 0.0
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        bandwidth = (
            width[bandwidth_eligible] / np.abs(middle[bandwidth_eligible])
        )
    if not np.isfinite(bandwidth).all():
        offset = int(
            np.flatnonzero(bandwidth_eligible)[~np.isfinite(bandwidth)][0]
        )
        raise TechIndicatorsCalculationError(
            "bollinger_bandwidth_20_2 produced a non-finite value at "
            f"observation {int(populated_indices[offset])}."
        )
    bandwidth_indices = populated_indices[bandwidth_eligible]
    bandwidth_values[bandwidth_indices] = bandwidth
    bandwidth_mask[bandwidth_indices] = False

    return (
        _masked_series(percent_b_values, percent_b_mask),
        _masked_series(bandwidth_values, bandwidth_mask),
    )


@dataclass(frozen=True, eq=False)
class BollingerStateArrays:
    """Persisted deviation plus generated Bollinger reference values.

    Only ``price_stddev_20`` is Python-written. Percent-b and BandWidth are
    reference values for PostgreSQL generated columns. Upper and lower bands
    are calculation-local intermediates and are not retained by this record.
    """

    source_bars: tuple[SourceBar, ...]
    price_stddev_20: MaskedFloatArray
    bollinger_percent_b_20_2: MaskedFloatArray
    bollinger_bandwidth_20_2: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.source_bars, tuple):
            raise TypeError("source_bars must be a tuple.")
        if not self.source_bars:
            raise ValueError("source_bars must not be empty.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        for field_name in BOLLINGER_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != len(self.source_bars):
                raise ValueError(
                    "Bollinger arrays must match the source observation count."
                )

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_bollinger_state(
    calculation_arrays: CalculationArrays,
    moving_averages: MovingAverageArrays,
) -> BollingerStateArrays:
    """Calculate the fixed 20-observation, two-deviation V1 band state."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")
    if not isinstance(moving_averages, MovingAverageArrays):
        raise TypeError("moving_averages must be MovingAverageArrays.")

    adapter = TALibAdapter(calculation_arrays)
    expected_sma_20 = adapter.sma(timeperiod=BOLLINGER_PERIOD)
    _validate_sma_20_alignment(
        calculation_arrays,
        moving_averages,
        expected_sma_20,
    )
    price_stddev_20 = adapter.stddev(
        timeperiod=BOLLINGER_PERIOD,
        nbdev=1.0,
    )
    percent_b, bandwidth = _generated_references(
        calculation_arrays,
        moving_averages.sma_20,
        price_stddev_20,
    )
    return BollingerStateArrays(
        source_bars=calculation_arrays.source_bars,
        price_stddev_20=price_stddev_20,
        bollinger_percent_b_20_2=percent_b,
        bollinger_bandwidth_20_2=bandwidth,
    )


__all__ = [
    "BOLLINGER_DEVIATIONS",
    "BOLLINGER_FIELDS",
    "BOLLINGER_PERIOD",
    "BollingerStateArrays",
    "calculate_bollinger_state",
]
