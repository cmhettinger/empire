"""TA-Lib boundary for TECH_INDICATORS_V1 calculations."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import version
from typing import Any, Callable

import numpy as np
import talib as _talib

from empire_stonks_tech_indicators.arrays import (
    CalculationArrays,
    MaskedFloatArray,
)
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsCalculationError,
)


EXPECTED_NUMPY_VERSION = "2.4.6"
EXPECTED_TALIB_VERSION = "0.7.1"
_UNSTABLE_FUNCTIONS = (
    "EMA",
    "RSI",
    "ATR",
    "PLUS_DI",
    "MINUS_DI",
    "ADX",
)


@dataclass(frozen=True)
class TALibRuntimeInfo:
    """Serializable identity of the pinned native calculation runtime."""

    library_name: str
    python_wrapper_version: str
    c_library_version: str
    numpy_version: str
    compatibility: str
    unstable_period: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "library_name": self.library_name,
            "python_wrapper_version": self.python_wrapper_version,
            "c_library_version": self.c_library_version,
            "numpy_version": self.numpy_version,
            "compatibility": self.compatibility,
            "unstable_period": self.unstable_period,
        }


def _runtime_info() -> TALibRuntimeInfo:
    numpy_version = version("numpy")
    talib_version = version("TA-Lib")
    c_version = _talib.__ta_version__.decode("ascii").split()[0]
    if numpy_version != EXPECTED_NUMPY_VERSION:
        raise TechIndicatorsCalculationError(
            "NumPy runtime does not match TECH_INDICATORS_V1."
        )
    if (
        talib_version != EXPECTED_TALIB_VERSION
        or c_version != EXPECTED_TALIB_VERSION
    ):
        raise TechIndicatorsCalculationError(
            "TA-Lib runtime does not match TECH_INDICATORS_V1."
        )
    _assert_global_settings()
    return TALibRuntimeInfo(
        library_name="TA-Lib",
        python_wrapper_version=talib_version,
        c_library_version=c_version,
        numpy_version=numpy_version,
        compatibility="DEFAULT",
        unstable_period=0,
    )


def _assert_global_settings() -> None:
    if _talib.get_compatibility() != 0:
        raise TechIndicatorsCalculationError(
            "TA-Lib compatibility must be DEFAULT for TECH_INDICATORS_V1."
        )
    for function_name in _UNSTABLE_FUNCTIONS:
        if _talib.get_unstable_period(function_name) != 0:
            raise TechIndicatorsCalculationError(
                "TA-Lib unstable periods must be zero for TECH_INDICATORS_V1."
            )


def _validate_timeperiod(timeperiod: int) -> None:
    if type(timeperiod) is not int or timeperiod < 2:
        raise ValueError("timeperiod must be an integer of at least 2.")


def _normalize_output(
    output: object,
    *,
    output_name: str,
    observation_count: int,
    first_valid_index: int,
) -> MaskedFloatArray:
    if not isinstance(output, np.ndarray):
        raise TechIndicatorsCalculationError(
            f"TA-Lib {output_name} returned an invalid output array."
        )
    if output.dtype != np.dtype(np.float64) or output.shape != (observation_count,):
        raise TechIndicatorsCalculationError(
            f"TA-Lib {output_name} returned an invalid output array."
        )

    warmup_end = min(first_valid_index, observation_count)
    if np.isfinite(output[:warmup_end]).any():
        raise TechIndicatorsCalculationError(
            f"TA-Lib {output_name} populated its documented warm-up prefix."
        )
    post_warmup = output[warmup_end:]
    if not np.isfinite(post_warmup).all():
        offset = int(np.flatnonzero(~np.isfinite(post_warmup))[0])
        raise TechIndicatorsCalculationError(
            f"TA-Lib {output_name} produced a non-finite value at observation "
            f"{warmup_end + offset}."
        )

    values = np.ascontiguousarray(output, dtype=np.float64).copy()
    values[:warmup_end] = np.nan
    null_mask = np.zeros(observation_count, dtype=np.bool_)
    null_mask[:warmup_end] = True
    values.setflags(write=False)
    null_mask.setflags(write=False)
    return MaskedFloatArray(values=values, null_mask=null_mask)


@dataclass(frozen=True, eq=False)
class TALibAdapter:
    """Run reviewed TA-Lib functions without exposing library-owned types."""

    calculation_arrays: CalculationArrays = field(repr=False)
    runtime: TALibRuntimeInfo = field(init=False)

    def __init__(self, calculation_arrays: CalculationArrays) -> None:
        if not isinstance(calculation_arrays, CalculationArrays):
            raise TypeError("calculation_arrays must be CalculationArrays.")
        object.__setattr__(self, "calculation_arrays", calculation_arrays)
        object.__setattr__(self, "runtime", _runtime_info())

    def _single_output(
        self,
        function: Callable[..., Any],
        *inputs: np.ndarray[Any, Any],
        output_name: str,
        first_valid_index: int,
        **parameters: int | float,
    ) -> MaskedFloatArray:
        _assert_global_settings()
        try:
            output = function(*inputs, **parameters)
        except Exception:
            raise TechIndicatorsCalculationError(
                f"TA-Lib {output_name} calculation failed."
            ) from None
        return _normalize_output(
            output,
            output_name=output_name,
            observation_count=self.calculation_arrays.observation_count,
            first_valid_index=first_valid_index,
        )

    def sma(self, *, timeperiod: int) -> MaskedFloatArray:
        _validate_timeperiod(timeperiod)
        return self._single_output(
            _talib.SMA,
            self.calculation_arrays.close,
            output_name="SMA",
            first_valid_index=timeperiod - 1,
            timeperiod=timeperiod,
        )

    def ema(self, *, timeperiod: int) -> MaskedFloatArray:
        _validate_timeperiod(timeperiod)
        return self._single_output(
            _talib.EMA,
            self.calculation_arrays.close,
            output_name="EMA",
            first_valid_index=timeperiod - 1,
            timeperiod=timeperiod,
        )

    def rsi(self, *, timeperiod: int) -> MaskedFloatArray:
        _validate_timeperiod(timeperiod)
        return self._single_output(
            _talib.RSI,
            self.calculation_arrays.close,
            output_name="RSI",
            first_valid_index=timeperiod,
            timeperiod=timeperiod,
        )

    def atr(self, *, timeperiod: int) -> MaskedFloatArray:
        _validate_timeperiod(timeperiod)
        return self._single_output(
            _talib.ATR,
            self.calculation_arrays.high,
            self.calculation_arrays.low,
            self.calculation_arrays.close,
            output_name="ATR",
            first_valid_index=timeperiod,
            timeperiod=timeperiod,
        )

    def stddev(self, *, timeperiod: int, nbdev: float) -> MaskedFloatArray:
        _validate_timeperiod(timeperiod)
        if (
            not isinstance(nbdev, (int, float))
            or not np.isfinite(nbdev)
            or nbdev <= 0
        ):
            raise ValueError("nbdev must be a finite positive number.")
        return self._single_output(
            _talib.STDDEV,
            self.calculation_arrays.close,
            output_name="STDDEV",
            first_valid_index=timeperiod - 1,
            timeperiod=timeperiod,
            nbdev=float(nbdev),
        )

    def plus_di(self, *, timeperiod: int) -> MaskedFloatArray:
        _validate_timeperiod(timeperiod)
        return self._single_output(
            _talib.PLUS_DI,
            self.calculation_arrays.high,
            self.calculation_arrays.low,
            self.calculation_arrays.close,
            output_name="PLUS_DI",
            first_valid_index=timeperiod,
            timeperiod=timeperiod,
        )

    def minus_di(self, *, timeperiod: int) -> MaskedFloatArray:
        _validate_timeperiod(timeperiod)
        return self._single_output(
            _talib.MINUS_DI,
            self.calculation_arrays.high,
            self.calculation_arrays.low,
            self.calculation_arrays.close,
            output_name="MINUS_DI",
            first_valid_index=timeperiod,
            timeperiod=timeperiod,
        )

    def adx(self, *, timeperiod: int) -> MaskedFloatArray:
        _validate_timeperiod(timeperiod)
        return self._single_output(
            _talib.ADX,
            self.calculation_arrays.high,
            self.calculation_arrays.low,
            self.calculation_arrays.close,
            output_name="ADX",
            first_valid_index=(2 * timeperiod) - 1,
            timeperiod=timeperiod,
        )

    def macd(
        self,
        *,
        fastperiod: int,
        slowperiod: int,
        signalperiod: int,
    ) -> tuple[MaskedFloatArray, MaskedFloatArray, MaskedFloatArray]:
        for period in (fastperiod, slowperiod, signalperiod):
            _validate_timeperiod(period)
        if fastperiod >= slowperiod:
            raise ValueError("fastperiod must be less than slowperiod.")
        _assert_global_settings()
        try:
            outputs = _talib.MACD(
                self.calculation_arrays.close,
                fastperiod=fastperiod,
                slowperiod=slowperiod,
                signalperiod=signalperiod,
            )
        except Exception:
            raise TechIndicatorsCalculationError(
                "TA-Lib MACD calculation failed."
            ) from None
        if not isinstance(outputs, tuple) or len(outputs) != 3:
            raise TechIndicatorsCalculationError(
                "TA-Lib MACD returned an invalid output collection."
            )
        first_valid_index = slowperiod + signalperiod - 2
        return tuple(
            _normalize_output(
                output,
                output_name=output_name,
                observation_count=self.calculation_arrays.observation_count,
                first_valid_index=first_valid_index,
            )
            for output, output_name in zip(
                outputs,
                ("MACD", "MACD signal", "MACD histogram"),
                strict=True,
            )
        )


__all__ = ["TALibAdapter", "TALibRuntimeInfo"]
