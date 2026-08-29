#!/usr/bin/env python3
"""Benchmark representative V1 full-prefix calculation workloads."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import resource
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from uuid import UUID

import numpy
import talib
from empire_stonks_tech_indicators import (
    BenchmarkHistory,
    EligibleListing,
    ResolvedBenchmark,
    SourceBar,
    assemble_feature_rows,
    normalize_source_bars,
)


DEFAULT_OBSERVATIONS = 20_000
MAXIMUM_OBSERVATIONS = 20_000
MINIMUM_OBSERVATIONS = 600
MAXIMUM_CASE_SECONDS = 120.0
MAXIMUM_TOTAL_SECONDS = 300.0
MAXIMUM_PEAK_RSS_MIB = 512.0
SUBJECT_ID = UUID("91250000-0000-4000-8000-000000000001")
BENCHMARK_ID = UUID("91250000-0000-4000-8000-000000000002")


def _peak_rss_mib() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return peak / (1024.0 * 1024.0)
    return peak / 1024.0


def _bars(
    listing_id: UUID,
    *,
    observations: int,
    base: Decimal,
    nullable_volume: bool,
) -> tuple[SourceBar, ...]:
    trading_date = date(1970, 1, 2)
    rows: list[SourceBar] = []
    for index in range(observations):
        if index:
            trading_date += timedelta(days=3 if index % 97 == 0 else 1)
        close = (
            base
            + Decimal(index) * Decimal("0.013")
            + Decimal(index % 29 - 14) * Decimal("0.007")
        )
        volume = (
            None
            if nullable_volume and index % 113 == 0
            else Decimal(100_000 + (index % 211) * 37)
        )
        rows.append(
            SourceBar(
                provider_listing_id=listing_id,
                trading_date=trading_date,
                open=close - Decimal("0.31"),
                high=close + Decimal("1.17"),
                low=close - Decimal("1.09"),
                close=close,
                volume=volume,
            )
        )
    return tuple(rows)


def _listing(bars: tuple[SourceBar, ...]) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=SUBJECT_ID,
        provider_code="EODDATA",
        market="NASDAQ",
        ticker="V126PERF",
        instrument_type_code="UNKNOWN",
        status="ACTIVE",
        first_trading_date=bars[0].trading_date,
        last_trading_date=bars[-1].trading_date,
        source_observation_count=len(bars),
    )


def _benchmark(bars: tuple[SourceBar, ...]) -> BenchmarkHistory:
    return BenchmarkHistory(
        benchmark=ResolvedBenchmark(provider_listing_id=BENCHMARK_ID),
        bars=bars,
    )


def _calculate(
    bars: tuple[SourceBar, ...],
    benchmark_bars: tuple[SourceBar, ...],
    *,
    calculated_at: datetime,
) -> tuple[tuple[object, ...], float]:
    started = perf_counter()
    rows = assemble_feature_rows(
        normalize_source_bars(bars),
        subject=_listing(bars),
        benchmark_history=_benchmark(benchmark_bars),
        calculated_at=calculated_at,
    )
    elapsed = perf_counter() - started
    if elapsed > MAXIMUM_CASE_SECONDS:
        raise AssertionError("a 20,000-observation calculation exceeded 2 minutes")
    return rows, elapsed


def _changed_rows(
    left: tuple[object, ...],
    right: tuple[object, ...],
    *,
    start: int,
) -> int:
    return sum(
        left[index] != right[index]
        for index in range(start, len(left))
    )


def run(observations: int = DEFAULT_OBSERVATIONS) -> dict[str, object]:
    if not MINIMUM_OBSERVATIONS <= observations <= MAXIMUM_OBSERVATIONS:
        raise ValueError(
            f"observations must be between {MINIMUM_OBSERVATIONS} "
            f"and {MAXIMUM_OBSERVATIONS}"
        )
    started = perf_counter()
    calculated_at = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    subject_bars = _bars(
        SUBJECT_ID,
        observations=observations,
        base=Decimal("100"),
        nullable_volume=False,
    )
    benchmark_bars = _bars(
        BENCHMARK_ID,
        observations=observations,
        base=Decimal("4200"),
        nullable_volume=True,
    )

    reference, rebuild_seconds = _calculate(
        subject_bars,
        benchmark_bars,
        calculated_at=calculated_at,
    )
    append_rows, append_seconds = _calculate(
        subject_bars,
        benchmark_bars,
        calculated_at=calculated_at,
    )
    if append_rows[-1] != reference[-1]:
        raise AssertionError("full-prefix append result differs from rebuild")
    del append_rows

    correction_index = observations - 500
    corrected_subject = list(subject_bars)
    original_subject = corrected_subject[correction_index]
    corrected_subject[correction_index] = replace(
        original_subject,
        open=original_subject.open + Decimal("5"),
        high=original_subject.high + Decimal("5"),
        low=original_subject.low + Decimal("5"),
        close=original_subject.close + Decimal("5"),
    )
    source_rows, source_seconds = _calculate(
        tuple(corrected_subject),
        benchmark_bars,
        calculated_at=calculated_at,
    )
    source_changed = _changed_rows(
        reference,
        source_rows,
        start=correction_index,
    )
    if source_changed < 1:
        raise AssertionError("source correction did not affect its write suffix")
    del corrected_subject, source_rows

    corrected_benchmark = list(benchmark_bars)
    original_benchmark = corrected_benchmark[correction_index]
    corrected_benchmark[correction_index] = replace(
        original_benchmark,
        open=original_benchmark.open + Decimal("25"),
        high=original_benchmark.high + Decimal("25"),
        low=original_benchmark.low + Decimal("25"),
        close=original_benchmark.close + Decimal("25"),
    )
    spx_rows, spx_seconds = _calculate(
        subject_bars,
        tuple(corrected_benchmark),
        calculated_at=calculated_at,
    )
    spx_changed = _changed_rows(
        reference,
        spx_rows,
        start=correction_index,
    )
    if spx_changed < 1:
        raise AssertionError("SPX correction did not affect its write suffix")
    del corrected_benchmark, spx_rows

    total_seconds = perf_counter() - started
    peak_rss = _peak_rss_mib()
    if total_seconds > MAXIMUM_TOTAL_SECONDS:
        raise AssertionError("calculation benchmark exceeded 5 minutes")
    if peak_rss > MAXIMUM_PEAK_RSS_MIB:
        raise AssertionError("calculation benchmark exceeded 512 MiB peak RSS")

    return {
        "cases": {
            "append": {
                "calculated_rows": observations,
                "seconds": append_seconds,
                "suffix_write_rows": 1,
            },
            "rebuild": {
                "calculated_rows": observations,
                "seconds": rebuild_seconds,
                "write_rows": observations,
            },
            "source_correction": {
                "calculated_rows": observations,
                "changed_suffix_rows": source_changed,
                "seconds": source_seconds,
                "suffix_write_rows": observations - correction_index,
            },
            "spx_correction": {
                "calculated_rows": observations,
                "changed_suffix_rows": spx_changed,
                "seconds": spx_seconds,
                "suffix_write_rows": observations - correction_index,
            },
        },
        "gates": {
            "case_seconds_at_most_120": True,
            "peak_rss_mib_at_most_512": True,
            "total_seconds_at_most_300": True,
        },
        "profile": {
            "calendar_gaps": True,
            "correction_index": correction_index,
            "nullable_benchmark_volume": True,
            "observations": observations,
            "peak_rss_mib": peak_rss,
            "total_seconds": total_seconds,
        },
        "runtime": {
            "numpy_version": numpy.__version__,
            "package_version": importlib.metadata.version(
                "empire-stonks-tech-indicators"
            ),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "talib_version": talib.__version__,
        },
        "status": "ok",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark rebuild, append, source-correction, and SPX-correction "
            "calculation at the P0.8 single-listing envelope."
        )
    )
    parser.add_argument(
        "--observations",
        default=DEFAULT_OBSERVATIONS,
        type=int,
    )
    result = run(parser.parse_args().observations)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
