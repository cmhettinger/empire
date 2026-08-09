#!/usr/bin/env python3
"""Prototype TA-Lib full replay versus bounded recursive suffix replay."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import resource
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter

import numpy as np
import talib


ABSOLUTE_TOLERANCE = 1e-12
RELATIVE_TOLERANCE = 1e-10
EXPECTED_NUMPY_VERSION = "2.4.6"
EXPECTED_TALIB_VERSION = "0.7.1"
DEFAULT_OBSERVATIONS = 20_000
DEFAULT_APPEND_START = 18_000
DEFAULT_REPLAY_PREFIX = 252
FAMILY_FIELDS = {
    "ema": ("ema_12", "ema_20", "ema_26", "ema_50"),
    "rsi": ("rsi_14",),
    "atr": ("atr_14",),
    "adx": ("plus_di_14", "minus_di_14", "adx_14"),
    "macd": (
        "macd_12_26",
        "macd_signal_12_26_9",
        "macd_histogram_12_26_9",
    ),
}


@dataclass(frozen=True)
class PriceSeries:
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    def slice(self, start: int, stop: int | None = None) -> PriceSeries:
        return PriceSeries(
            high=np.ascontiguousarray(self.high[start:stop]),
            low=np.ascontiguousarray(self.low[start:stop]),
            close=np.ascontiguousarray(self.close[start:stop]),
        )


def _assert_runtime() -> None:
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


def _typical_series(observations: int) -> PriceSeries:
    rng = np.random.default_rng(20260809)
    log_returns = rng.normal(0.00015, 0.011, size=observations)
    close = 100.0 * np.exp(np.cumsum(log_returns, dtype=np.float64))
    spread = rng.uniform(0.001, 0.025, size=observations)
    high = close * (1.0 + spread)
    low = close * (1.0 - spread)
    return PriceSeries(
        high=np.ascontiguousarray(high),
        low=np.ascontiguousarray(low),
        close=np.ascontiguousarray(close),
    )


def _high_offset_series(observations: int) -> PriceSeries:
    index = np.arange(observations, dtype=np.float64)
    close = (
        1.0e20
        + np.sin(index / 17.0) * 6.0e12
        + np.cos(index / 53.0) * 2.0e12
        + index * 3.0e7
    )
    spread = 8.0e11 + (np.sin(index / 29.0) + 1.0) * 2.0e11
    return PriceSeries(
        high=np.ascontiguousarray(close + spread),
        low=np.ascontiguousarray(close - spread),
        close=np.ascontiguousarray(close),
    )


def _correct(series: PriceSeries, index: int) -> PriceSeries:
    high = series.high.copy()
    low = series.low.copy()
    close = series.close.copy()
    relative_change = 0.07 if abs(close[index]) < 1.0e15 else 1.0e-6
    corrected_close = close[index] * (1.0 + relative_change)
    correction_size = abs(corrected_close - close[index])
    close[index] = corrected_close
    high[index] = max(high[index], corrected_close + correction_size * 0.1)
    low[index] = min(low[index], corrected_close - correction_size * 0.1)
    return PriceSeries(
        high=np.ascontiguousarray(high),
        low=np.ascontiguousarray(low),
        close=np.ascontiguousarray(close),
    )


def _calculate(series: PriceSeries) -> dict[str, np.ndarray]:
    for values in (series.high, series.low, series.close):
        if values.dtype != np.dtype("float64") or not values.flags.c_contiguous:
            raise AssertionError("TA-Lib inputs must be contiguous float64 arrays")

    macd, signal, histogram = talib.MACD(
        series.close,
        fastperiod=12,
        slowperiod=26,
        signalperiod=9,
    )
    return {
        "ema_12": talib.EMA(series.close, timeperiod=12),
        "ema_20": talib.EMA(series.close, timeperiod=20),
        "ema_26": talib.EMA(series.close, timeperiod=26),
        "ema_50": talib.EMA(series.close, timeperiod=50),
        "rsi_14": talib.RSI(series.close, timeperiod=14),
        "atr_14": talib.ATR(
            series.high,
            series.low,
            series.close,
            timeperiod=14,
        ),
        "plus_di_14": talib.PLUS_DI(
            series.high,
            series.low,
            series.close,
            timeperiod=14,
        ),
        "minus_di_14": talib.MINUS_DI(
            series.high,
            series.low,
            series.close,
            timeperiod=14,
        ),
        "adx_14": talib.ADX(
            series.high,
            series.low,
            series.close,
            timeperiod=14,
        ),
        "macd_12_26": macd,
        "macd_signal_12_26_9": signal,
        "macd_histogram_12_26_9": histogram,
    }


def _combine(
    prior: Mapping[str, np.ndarray],
    recalculated: Mapping[str, np.ndarray],
    start: int,
) -> dict[str, np.ndarray]:
    return {
        field: np.concatenate((prior[field][:start], values[start:]))
        for field, values in recalculated.items()
    }


def _field_comparison(
    expected: np.ndarray,
    actual: np.ndarray,
    global_start: int,
) -> dict[str, int | float | None]:
    if expected.shape != actual.shape:
        raise AssertionError(
            f"shape mismatch: expected {expected.shape}, got {actual.shape}"
        )
    expected_null = np.isnan(expected)
    actual_null = np.isnan(actual)
    null_mismatch = expected_null != actual_null
    finite_pair = np.isfinite(expected) & np.isfinite(actual)
    finite_difference = np.zeros(expected.shape, dtype=np.float64)
    finite_difference[finite_pair] = np.abs(
        expected[finite_pair] - actual[finite_pair]
    )
    scale = np.maximum(np.abs(expected), np.abs(actual))
    threshold = np.maximum(
        ABSOLUTE_TOLERANCE,
        RELATIVE_TOLERANCE * scale,
    )
    value_mismatch = finite_pair & (finite_difference > threshold)
    nonfinite_mismatch = ~(expected_null | actual_null | finite_pair)
    mismatch = null_mismatch | value_mismatch | nonfinite_mismatch
    mismatch_positions = np.flatnonzero(mismatch)

    comparable = finite_pair & (scale > 0.0)
    relative_difference = np.zeros(expected.shape, dtype=np.float64)
    relative_difference[comparable] = (
        finite_difference[comparable] / scale[comparable]
    )
    return {
        "first_mismatch_index": (
            None
            if mismatch_positions.size == 0
            else int(global_start + mismatch_positions[0])
        ),
        "max_absolute_difference": (
            0.0 if not finite_pair.any() else float(finite_difference.max())
        ),
        "max_relative_difference": (
            0.0
            if not comparable.any()
            else float(relative_difference.max())
        ),
        "mismatch_count": int(mismatch.sum()),
        "null_mask_mismatch_count": int(null_mismatch.sum()),
    }


def _family_comparison(
    expected: Mapping[str, np.ndarray],
    actual: Mapping[str, np.ndarray],
    global_start: int,
) -> dict[str, dict[str, int | float | None]]:
    result: dict[str, dict[str, int | float | None]] = {}
    for family, fields in FAMILY_FIELDS.items():
        comparisons = [
            _field_comparison(expected[field], actual[field], global_start)
            for field in fields
        ]
        first_indexes = [
            value
            for comparison in comparisons
            if (value := comparison["first_mismatch_index"]) is not None
        ]
        result[family] = {
            "first_mismatch_index": (
                None if not first_indexes else int(min(first_indexes))
            ),
            "max_absolute_difference": float(
                max(item["max_absolute_difference"] for item in comparisons)
            ),
            "max_relative_difference": float(
                max(item["max_relative_difference"] for item in comparisons)
            ),
            "mismatch_count": int(
                sum(item["mismatch_count"] for item in comparisons)
            ),
            "null_mask_mismatch_count": int(
                sum(item["null_mask_mismatch_count"] for item in comparisons)
            ),
        }
    return result


def _all_equivalent(
    comparison: Mapping[str, Mapping[str, int | float | None]],
) -> bool:
    return all(item["mismatch_count"] == 0 for item in comparison.values())


def _mismatched_families(
    comparison: Mapping[str, Mapping[str, int | float | None]],
) -> set[str]:
    return {
        family
        for family, item in comparison.items()
        if item["mismatch_count"] != 0
    }


def _append_experiment(
    series: PriceSeries,
    append_start: int,
    replay_prefix: int,
) -> dict[str, object]:
    prior = _calculate(series.slice(0, append_start))
    reference = _calculate(series)
    full_candidate = _combine(prior, reference, append_start)
    full_comparison = _family_comparison(reference, full_candidate, 0)

    replay_start = append_start - replay_prefix
    bounded = _calculate(series.slice(replay_start))
    expected_suffix = {
        field: values[append_start:]
        for field, values in reference.items()
    }
    bounded_suffix = {
        field: values[replay_prefix:]
        for field, values in bounded.items()
    }
    bounded_comparison = _family_comparison(
        expected_suffix,
        bounded_suffix,
        append_start,
    )
    return {
        "append_start": append_start,
        "appended_observations": len(series.close) - append_start,
        "bounded_replay": {
            "all_equivalent": _all_equivalent(bounded_comparison),
            "comparison": bounded_comparison,
            "input_start": replay_start,
            "prefix_observations": replay_prefix,
        },
        "full_prefix_replay": {
            "all_equivalent": _all_equivalent(full_comparison),
            "comparison": full_comparison,
            "input_start": 0,
        },
    }


def _correction_experiment(
    series: PriceSeries,
    correction_index: int,
    replay_prefix: int,
) -> dict[str, object]:
    prior = _calculate(series)
    corrected = _correct(series, correction_index)
    reference = _calculate(corrected)
    full_candidate = _combine(prior, reference, correction_index)
    full_comparison = _family_comparison(reference, full_candidate, 0)

    replay_start = correction_index - replay_prefix
    bounded = _calculate(corrected.slice(replay_start))
    expected_suffix = {
        field: values[correction_index:]
        for field, values in reference.items()
    }
    bounded_suffix = {
        field: values[replay_prefix:]
        for field, values in bounded.items()
    }
    bounded_comparison = _family_comparison(
        expected_suffix,
        bounded_suffix,
        correction_index,
    )
    return {
        "bounded_replay": {
            "all_equivalent": _all_equivalent(bounded_comparison),
            "comparison": bounded_comparison,
            "input_start": replay_start,
            "prefix_observations": replay_prefix,
        },
        "correction_index": correction_index,
        "full_prefix_replay": {
            "all_equivalent": _all_equivalent(full_comparison),
            "comparison": full_comparison,
            "input_start": 0,
        },
        "suffix_observations": len(series.close) - correction_index,
    }


def _peak_rss_mib() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return peak / (1024.0 * 1024.0)
    return peak / 1024.0


def _validate_scope(
    observations: int,
    append_start: int,
    replay_prefix: int,
) -> tuple[int, ...]:
    if observations < 2_000:
        raise ValueError("observations must be at least 2000")
    if replay_prefix < 50:
        raise ValueError("replay prefix must be at least 50 observations")
    if append_start <= replay_prefix or append_start >= observations:
        raise ValueError("append start must leave prefix and appended rows")
    corrections = (observations // 4, observations - 500)
    if any(index <= replay_prefix for index in corrections):
        raise ValueError("correction indexes must leave the replay prefix")
    return corrections


def run_prototype(
    observations: int,
    append_start: int,
    replay_prefix: int,
) -> dict[str, object]:
    _assert_runtime()
    corrections = _validate_scope(observations, append_start, replay_prefix)
    started = perf_counter()
    datasets = {
        "high_offset": _high_offset_series(observations),
        "typical": _typical_series(observations),
    }
    results: dict[str, object] = {}
    bounded_mismatches: set[str] = set()

    for name, series in datasets.items():
        append = _append_experiment(series, append_start, replay_prefix)
        full_output = _calculate(series)
        reconstructed_macd = full_output["ema_12"] - full_output["ema_26"]
        macd_reconstruction = _field_comparison(
            full_output["macd_12_26"],
            reconstructed_macd,
            0,
        )
        if macd_reconstruction["mismatch_count"] == 0:
            raise AssertionError(
                f"independent EMA values unexpectedly reproduced MACD for {name}"
            )
        correction_results = [
            _correction_experiment(series, index, replay_prefix)
            for index in corrections
        ]
        results[name] = {
            "append": append,
            "corrections": correction_results,
            "macd_from_independent_ema": macd_reconstruction,
        }

        full_sections = [append["full_prefix_replay"]]
        full_sections.extend(
            item["full_prefix_replay"] for item in correction_results
        )
        if not all(section["all_equivalent"] for section in full_sections):
            raise AssertionError(f"full-prefix replay failed for {name}")

        bounded_sections = [append["bounded_replay"]]
        bounded_sections.extend(
            item["bounded_replay"] for item in correction_results
        )
        for section in bounded_sections:
            bounded_mismatches.update(
                _mismatched_families(section["comparison"])
            )

    expected_families = set(FAMILY_FIELDS)
    if bounded_mismatches != expected_families:
        missing = sorted(expected_families - bounded_mismatches)
        raise AssertionError(
            f"bounded replay did not expose mismatches for: {missing}"
        )

    elapsed = perf_counter() - started
    if elapsed > 120.0:
        raise AssertionError(f"prototype exceeded 120 seconds: {elapsed}")
    peak_rss = _peak_rss_mib()
    if peak_rss > 512.0:
        raise AssertionError(f"prototype exceeded 512 MiB RSS: {peak_rss}")

    return {
        "decision": {
            "append": "full_prefix_replay",
            "bounded_replay": "rejected_without_complete_recurrence_state",
            "correction": "full_prefix_replay_then_write_affected_suffix",
            "recurrence_state_table": "rejected_for_v1",
        },
        "evidence": {
            "bounded_mismatch_families": sorted(bounded_mismatches),
            "full_prefix_all_equivalent": True,
            "results": results,
        },
        "profile": {
            "append_start": append_start,
            "correction_indexes": list(corrections),
            "datasets": sorted(datasets),
            "elapsed_seconds": round(elapsed, 6),
            "observations_per_dataset": observations,
            "peak_rss_mib": round(peak_rss, 3),
            "replay_prefix_observations": replay_prefix,
        },
        "runtime": {
            "numpy_version": importlib.metadata.version("numpy"),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "talib_c_version": talib.__ta_version__.decode("ascii"),
            "talib_version": importlib.metadata.version("TA-Lib"),
        },
        "schema_version": 1,
        "status": "ok",
        "tolerance": {
            "absolute": ABSOLUTE_TOLERANCE,
            "relative": RELATIVE_TOLERANCE,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare full-prefix and bounded TA-Lib recursive replay.",
    )
    parser.add_argument(
        "--observations",
        type=int,
        default=DEFAULT_OBSERVATIONS,
    )
    parser.add_argument(
        "--append-start",
        type=int,
        default=DEFAULT_APPEND_START,
    )
    parser.add_argument(
        "--replay-prefix",
        type=int,
        default=DEFAULT_REPLAY_PREFIX,
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_prototype(
            observations=args.observations,
            append_start=args.append_start,
            replay_prefix=args.replay_prefix,
        )
    except (AssertionError, ValueError) as exc:
        print(f"recursive-equivalence failed: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, allow_nan=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
