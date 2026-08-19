from __future__ import annotations

import json
import math
from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from empire_stonks_tech_indicators import (
    BenchmarkHistory,
    EligibleListing,
    ResolvedBenchmark,
    SourceBar,
    SpxFeatureArrays,
    calculate_spx_features,
    normalize_source_bars,
)
from empire_stonks_tech_indicators.spx_features import SPX_FEATURE_FIELDS


SUBJECT_ID = UUID("00000000-0000-4000-8000-000000000001")
SPX_ID = UUID("00000000-0000-4000-8000-000000000002")
ABSOLUTE_TOLERANCE = 1e-12
RELATIVE_TOLERANCE = 1e-10
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "spx_features_v1.json"


def _closes(initial: str, pattern: list[str], count: int) -> list[Decimal]:
    with localcontext() as context:
        context.prec = 80
        returns = [Decimal(value) for value in pattern]
        closes = [Decimal(initial)]
        for index in range(count - 1):
            closes.append(
                closes[-1] * (Decimal("1") + returns[index % len(returns)])
            )
        return closes


def _dates(generator: dict[str, Any]) -> list[date]:
    current = date.fromisoformat(generator["start_date"])
    dates = [current]
    for index in range(1, generator["observations"]):
        current += timedelta(days=1)
        if index == generator["calendar_gap_before_index"]:
            current += timedelta(days=generator["calendar_gap_days"])
        dates.append(current)
    return dates


def _bar(listing_id: UUID, trading_date: date, close: Decimal) -> SourceBar:
    return SourceBar(
        provider_listing_id=listing_id,
        trading_date=trading_date,
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("1000"),
    )


def _case_inputs(
    case: dict[str, Any],
) -> tuple[EligibleListing, tuple[SourceBar, ...], BenchmarkHistory]:
    generator = case["generator"]
    count = generator["observations"]
    dates = _dates(generator)
    subject_closes = _closes(
        generator["subject_initial_close"],
        generator["subject_return_pattern"],
        count,
    )
    benchmark_closes = _closes(
        generator["benchmark_initial_close"],
        generator["benchmark_return_pattern"],
        count,
    )
    subject_bars = tuple(
        _bar(SUBJECT_ID, dates[index], subject_closes[index])
        for index in range(count)
    )
    missing = set(generator["benchmark_missing_indices"])
    benchmark_history = BenchmarkHistory(
        benchmark=ResolvedBenchmark(provider_listing_id=SPX_ID),
        bars=tuple(
            _bar(SPX_ID, dates[index], benchmark_closes[index])
            for index in range(count)
            if index not in missing
        ),
    )
    listing = EligibleListing(
        provider_listing_id=SUBJECT_ID,
        provider_code="EODDATA",
        market="NYSE",
        ticker="GOLDEN",
        instrument_type_code="UNKNOWN",
        status="ACTIVE",
        first_trading_date=dates[0],
        last_trading_date=dates[-1],
        source_observation_count=count,
    )
    return listing, subject_bars, benchmark_history


def _distance(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0.0 else numerator / denominator - 1.0


def _complete_window(
    source: list[float | None],
    end: int,
    period: int,
) -> list[float] | None:
    if end < period:
        return None
    window = source[end - period + 1 : end + 1]
    if any(value is None for value in window):
        return None
    return [float(value) for value in window]


def _sample_statistics(
    subject: list[float],
    benchmark: list[float],
) -> tuple[float, float, float]:
    count = len(subject)
    subject_mean = sum(subject) / count
    benchmark_mean = sum(benchmark) / count
    covariance = sum(
        (subject_value - subject_mean) * (benchmark_value - benchmark_mean)
        for subject_value, benchmark_value in zip(
            subject,
            benchmark,
            strict=True,
        )
    ) / (count - 1)
    subject_variance = sum(
        (value - subject_mean) ** 2 for value in subject
    ) / (count - 1)
    benchmark_variance = sum(
        (value - benchmark_mean) ** 2 for value in benchmark
    ) / (count - 1)
    return covariance, subject_variance, benchmark_variance


def _independent_reference(
    subject_bars: tuple[SourceBar, ...],
    benchmark_history: BenchmarkHistory,
) -> dict[str, list[float | None]]:
    result = {
        field_name: [None] * len(subject_bars)
        for field_name in SPX_FEATURE_FIELDS
    }
    benchmark_by_date = {
        bar.trading_date: float(bar.close) for bar in benchmark_history.bars
    }
    aligned = [
        (index, float(bar.close), benchmark_by_date[bar.trading_date])
        for index, bar in enumerate(subject_bars)
        if bar.trading_date in benchmark_by_date
    ]
    ratios: list[float | None] = []
    subject_returns: list[float | None] = [None]
    benchmark_returns: list[float | None] = [None]
    for aligned_index, (row_index, subject_close, benchmark_close) in enumerate(
        aligned
    ):
        ratio = (
            None
            if benchmark_close == 0.0
            else subject_close / benchmark_close
        )
        ratios.append(ratio)
        result["rel_spx"][row_index] = ratios[-1]
        if aligned_index == 0:
            continue
        previous = aligned[aligned_index - 1]
        subject_returns.append(_distance(subject_close, previous[1]))
        benchmark_returns.append(_distance(benchmark_close, previous[2]))

    for aligned_index, (row_index, _, _) in enumerate(aligned):
        for period in (20, 50):
            if aligned_index + 1 < period:
                continue
            window = ratios[aligned_index - period + 1 : aligned_index + 1]
            if any(value is None for value in window):
                continue
            populated = [float(value) for value in window]
            ratio_mean = sum(populated) / period
            if ratio_mean != 0.0:
                result[f"pct_rel_spx_{period}"][row_index] = (
                    populated[-1] / ratio_mean - 1.0
                )

        for period in (20, 63, 126, 252):
            subject_window = _complete_window(
                subject_returns,
                aligned_index,
                period,
            )
            benchmark_window = _complete_window(
                benchmark_returns,
                aligned_index,
                period,
            )
            if subject_window is None or benchmark_window is None:
                continue
            subject_gross = 1.0
            benchmark_gross = 1.0
            for value in subject_window:
                subject_gross *= 1.0 + value
            for value in benchmark_window:
                benchmark_gross *= 1.0 + value
            if benchmark_gross != 0.0:
                result[f"relative_return_spx_{period}d_pct"][row_index] = (
                    subject_gross / benchmark_gross - 1.0
                )

        for period in (60, 252):
            subject_window = _complete_window(
                subject_returns,
                aligned_index,
                period,
            )
            benchmark_window = _complete_window(
                benchmark_returns,
                aligned_index,
                period,
            )
            if subject_window is None or benchmark_window is None:
                continue
            covariance, subject_variance, benchmark_variance = (
                _sample_statistics(subject_window, benchmark_window)
            )
            if benchmark_variance != 0.0:
                result[f"spx_beta_{period}d"][row_index] = (
                    covariance / benchmark_variance
                )
            if subject_variance == 0.0 or benchmark_variance == 0.0:
                continue
            correlation = covariance / (
                math.sqrt(subject_variance) * math.sqrt(benchmark_variance)
            )
            if correlation > 1.0 and abs(correlation - 1.0) <= 1e-12:
                correlation = 1.0
            elif correlation < -1.0 and abs(correlation + 1.0) <= 1e-12:
                correlation = -1.0
            result[f"spx_correlation_{period}d"][row_index] = correlation

    return result


def _actual(case: dict[str, Any]) -> SpxFeatureArrays:
    listing, subject_bars, benchmark_history = _case_inputs(case)
    return calculate_spx_features(
        normalize_source_bars(subject_bars),
        subject=listing,
        benchmark_history=benchmark_history,
    )


def _assert_equivalent(
    actual: float | None,
    expected: float | None,
    *,
    label: str,
) -> None:
    if expected is None:
        assert actual is None, label
        return
    assert actual is not None, label
    assert math.isfinite(actual), label
    difference = abs(actual - expected)
    tolerance = max(
        ABSOLUTE_TOLERANCE,
        RELATIVE_TOLERANCE * max(abs(actual), abs(expected)),
    )
    assert difference <= tolerance, (
        f"{label}: actual={actual!r}, expected={expected!r}, "
        f"difference={difference!r}, tolerance={tolerance!r}"
    )


def test_committed_spx_golden_snapshots_match_independent_oracle() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert fixture["schema_version"] == "TECH_INDICATORS_SPX_GOLDEN_V1"
    assert fixture["provenance"]["absolute_tolerance"] == ABSOLUTE_TOLERANCE
    assert fixture["provenance"]["relative_tolerance"] == RELATIVE_TOLERANCE
    for case_name, case in fixture["cases"].items():
        _, subject_bars, benchmark_history = _case_inputs(case)
        oracle = _independent_reference(subject_bars, benchmark_history)
        actual = _actual(case)
        assert set(case["expected"]) == {
            str(index) for index in case["snapshot_indices"]
        }
        for index_text, expected_fields in case["expected"].items():
            index = int(index_text)
            assert tuple(expected_fields) == SPX_FEATURE_FIELDS
            for field_name, expected in expected_fields.items():
                _assert_equivalent(
                    oracle[field_name][index],
                    expected,
                    label=f"{case_name}.oracle[{index}].{field_name}",
                )
                _assert_equivalent(
                    getattr(actual, field_name).value_at(index),
                    expected,
                    label=f"{case_name}.actual[{index}].{field_name}",
                )


@pytest.mark.parametrize("case_name", ["exact_date_gaps", "low_nonzero_variance"])
def test_every_spx_value_and_null_matches_independent_scalar_formulas(
    case_name: str,
) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    case = fixture["cases"][case_name]
    _, subject_bars, benchmark_history = _case_inputs(case)
    oracle = _independent_reference(subject_bars, benchmark_history)
    actual = _actual(case)

    for field_name in SPX_FEATURE_FIELDS:
        for index, expected in enumerate(oracle[field_name]):
            _assert_equivalent(
                getattr(actual, field_name).value_at(index),
                expected,
                label=f"{case_name}[{index}].{field_name}",
            )


def test_golden_cases_prove_exact_gaps_and_low_nonzero_variance() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    gap_case = fixture["cases"]["exact_date_gaps"]
    gap_actual = _actual(gap_case)
    for index in gap_case["generator"]["benchmark_missing_indices"]:
        assert all(
            getattr(gap_actual, field_name).value_at(index) is None
            for field_name in SPX_FEATURE_FIELDS
        )
    dates = _dates(gap_case["generator"])
    gap_index = gap_case["generator"]["calendar_gap_before_index"]
    assert (dates[gap_index] - dates[gap_index - 1]).days > 1

    low_case = fixture["cases"]["low_nonzero_variance"]
    _, subject_bars, benchmark_history = _case_inputs(low_case)
    aligned_returns = [
        float(benchmark_history.bars[index].close)
        / float(benchmark_history.bars[index - 1].close)
        - 1.0
        for index in range(1, len(benchmark_history.bars))
    ]
    mean_return = sum(aligned_returns) / len(aligned_returns)
    variance = sum(
        (value - mean_return) ** 2 for value in aligned_returns
    ) / (len(aligned_returns) - 1)
    assert 0.0 < variance < 1e-14
    assert len(subject_bars) == low_case["generator"]["observations"]
    low_actual = _actual(low_case)
    assert low_actual.spx_beta_252d.value_at(252) is not None
    assert low_actual.spx_correlation_252d.value_at(252) is not None
