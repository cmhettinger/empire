"""Pure consecutive close-direction streak calculations for V1."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from empire_stonks_tech_indicators.arrays import CalculationArrays


StreakArray = NDArray[np.int64]
STREAK_FIELDS = ("consecutive_up_days", "consecutive_down_days")


@dataclass(frozen=True, eq=False)
class StreakArrays:
    """Non-null V1 up/down streak counts in source observation order."""

    consecutive_up_days: StreakArray
    consecutive_down_days: StreakArray

    def __post_init__(self) -> None:
        lengths: set[int] = set()
        for field_name in STREAK_FIELDS:
            values = getattr(self, field_name)
            if not isinstance(values, np.ndarray):
                raise TypeError(f"{field_name} must be a NumPy array.")
            if values.dtype != np.dtype(np.int64):
                raise TypeError(f"{field_name} must use int64 values.")
            if values.ndim != 1:
                raise ValueError(f"{field_name} must be one-dimensional.")
            if not values.flags.c_contiguous:
                raise ValueError(f"{field_name} must be C-contiguous.")
            if values.flags.writeable:
                raise ValueError(f"{field_name} must be read-only.")
            if np.any(values < 0):
                raise ValueError(f"{field_name} must be non-negative.")
            lengths.add(len(values))
        if len(lengths) != 1:
            raise ValueError("streak arrays must have one observation count.")
        if self.observation_count == 0:
            raise ValueError("streak arrays must not be empty.")
        if self.consecutive_up_days[0] != 0:
            raise ValueError("the first up streak must be zero.")
        if self.consecutive_down_days[0] != 0:
            raise ValueError("the first down streak must be zero.")
        if np.any(
            (self.consecutive_up_days > 0)
            & (self.consecutive_down_days > 0)
        ):
            raise ValueError("up and down streaks cannot both be positive.")

    @property
    def observation_count(self) -> int:
        return len(self.consecutive_up_days)


def calculate_streaks(calculation_arrays: CalculationArrays) -> StreakArrays:
    """Calculate V1 close-direction streaks from the complete source prefix."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")

    observation_count = calculation_arrays.observation_count
    up = np.zeros(observation_count, dtype=np.int64)
    down = np.zeros(observation_count, dtype=np.int64)
    close = calculation_arrays.close
    for index in range(1, observation_count):
        if close[index] > close[index - 1]:
            up[index] = up[index - 1] + 1
        elif close[index] < close[index - 1]:
            down[index] = down[index - 1] + 1

    up = np.ascontiguousarray(up)
    down = np.ascontiguousarray(down)
    up.setflags(write=False)
    down.setflags(write=False)
    return StreakArrays(
        consecutive_up_days=up,
        consecutive_down_days=down,
    )


__all__ = ["STREAK_FIELDS", "StreakArrays", "calculate_streaks"]
