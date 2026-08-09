#!/usr/bin/env python3
"""Prove the pinned tech-indicators native runtime without package code."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
from pathlib import Path

import numpy as np
import talib


EXPECTED_NUMPY_VERSION = "2.4.6"
EXPECTED_TALIB_VERSION = "0.7.1"


def _assert_null_prefix(values: np.ndarray, first_valid_index: int) -> None:
    if values.dtype != np.dtype("float64"):
        raise AssertionError(f"unexpected output dtype: {values.dtype}")
    if not np.isnan(values[:first_valid_index]).all():
        raise AssertionError(
            f"expected NaN through index {first_valid_index - 1}"
        )
    if not np.isfinite(values[first_valid_index:]).all():
        raise AssertionError(
            f"expected finite output from index {first_valid_index}"
        )


def main() -> int:
    numpy_version = importlib.metadata.version("numpy")
    talib_version = importlib.metadata.version("TA-Lib")
    if numpy_version != EXPECTED_NUMPY_VERSION:
        raise AssertionError(
            f"expected NumPy {EXPECTED_NUMPY_VERSION}, got {numpy_version}"
        )
    if talib_version != EXPECTED_TALIB_VERSION:
        raise AssertionError(
            f"expected TA-Lib {EXPECTED_TALIB_VERSION}, got {talib_version}"
        )
    if talib.get_compatibility() != 0:
        raise AssertionError("TA-Lib compatibility must be DEFAULT (0)")

    for function_name in ("EMA", "RSI", "ATR", "ADX"):
        if talib.get_unstable_period(function_name) != 0:
            raise AssertionError(
                f"TA-Lib unstable period must be zero for {function_name}"
            )

    close = np.linspace(100.0, 179.0, 80, dtype=np.float64)
    high = np.ascontiguousarray(close + 1.25)
    low = np.ascontiguousarray(close - 1.25)
    close = np.ascontiguousarray(close)
    if not close.flags.c_contiguous:
        raise AssertionError("calculation input must be C-contiguous")

    _assert_null_prefix(talib.SMA(close, timeperiod=20), 19)
    _assert_null_prefix(talib.EMA(close, timeperiod=20), 19)
    _assert_null_prefix(talib.RSI(close, timeperiod=14), 14)
    _assert_null_prefix(talib.ATR(high, low, close, timeperiod=14), 14)
    _assert_null_prefix(talib.PLUS_DI(high, low, close, timeperiod=14), 14)
    _assert_null_prefix(talib.MINUS_DI(high, low, close, timeperiod=14), 14)
    _assert_null_prefix(talib.ADX(high, low, close, timeperiod=14), 27)
    macd, signal, histogram = talib.MACD(
        close,
        fastperiod=12,
        slowperiod=26,
        signalperiod=9,
    )
    for output in (macd, signal, histogram):
        _assert_null_prefix(output, 33)

    extension_path = Path(talib._ta_lib.__file__).resolve()
    result = {
        "numpy_version": numpy_version,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "status": "ok",
        "talib_c_version": talib.__ta_version__.decode("ascii"),
        "talib_extension": str(extension_path),
        "talib_version": talib_version,
    }
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
