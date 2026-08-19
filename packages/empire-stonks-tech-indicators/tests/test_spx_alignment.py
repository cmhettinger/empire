from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    AlignedReturnArrays,
    BenchmarkHistory,
    ResolvedBenchmark,
    SourceBar,
    TechIndicatorsCalculationError,
    calculate_aligned_returns,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import spx_alignment as alignment_module


SUBJECT_ID = UUID("00000000-0000-4000-8000-000000000001")
SPX_ID = UUID("00000000-0000-4000-8000-000000000002")


def _bar(listing_id: UUID, trading_date: date, close: str) -> SourceBar:
    value = Decimal(close)
    return SourceBar(
        provider_listing_id=listing_id,
        trading_date=trading_date,
        open=value,
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value,
        volume=Decimal("100"),
    )


def _benchmark_history(rows: list[tuple[date, str]]) -> BenchmarkHistory:
    benchmark = ResolvedBenchmark(
        provider_listing_id=SPX_ID,
        provider_code="YAHOO",
        market="XIDX",
        ticker="SPX",
        instrument_type_code="EQUITY_INDEX",
        status="ACTIVE",
        yahoo_ticker="^GSPC",
    )
    return BenchmarkHistory(
        benchmark=benchmark,
        bars=tuple(_bar(SPX_ID, trading_date, close) for trading_date, close in rows),
    )


def _calculate(
    subject_rows: list[tuple[date, str]],
    benchmark_rows: list[tuple[date, str]],
) -> AlignedReturnArrays:
    subject = normalize_source_bars(
        _bar(SUBJECT_ID, trading_date, close)
        for trading_date, close in subject_rows
    )
    return calculate_aligned_returns(
        subject,
        _benchmark_history(benchmark_rows),
    )


def test_aligned_return_api_is_explicitly_exported() -> None:
    assert alignment_module.__all__ == [
        "AlignedReturnArrays",
        "calculate_aligned_returns",
    ]
    assert public_api.AlignedReturnArrays is AlignedReturnArrays
    assert public_api.calculate_aligned_returns is calculate_aligned_returns


def test_exact_date_intersection_preserves_gaps_and_common_return_horizons() -> None:
    jan_2 = date(2020, 1, 2)
    jan_3 = date(2020, 1, 3)
    jan_6 = date(2020, 1, 6)
    jan_7 = date(2020, 1, 7)
    jan_8 = date(2020, 1, 8)
    aligned = _calculate(
        [
            (jan_2, "10"),
            (jan_3, "20"),
            (jan_6, "30"),
            (jan_7, "60"),
            (jan_8, "90"),
        ],
        [(jan_2, "100"), (jan_6, "120"), (jan_8, "150")],
    )

    assert aligned.aligned_trading_dates == (jan_2, jan_6, jan_8)
    assert aligned.aligned_subject_observation_indices == (0, 2, 4)
    np.testing.assert_array_equal(aligned.subject_aligned_close, [10, 30, 90])
    np.testing.assert_array_equal(aligned.spx_aligned_close, [100, 120, 150])
    assert aligned.subject_aligned_return_1d_pct.value_at(0) is None
    assert aligned.subject_aligned_return_1d_pct.value_at(1) == 2.0
    assert aligned.subject_aligned_return_1d_pct.value_at(2) == 2.0
    assert aligned.spx_aligned_return_1d_pct.value_at(1) == pytest.approx(0.2)
    assert aligned.spx_aligned_return_1d_pct.value_at(2) == pytest.approx(0.25)
    assert aligned.aligned_close_observation_count.tolist() == [1, 1, 2, 2, 3]
    assert aligned.trailing_valid_aligned_return_count.tolist() == [0, 0, 1, 0, 2]


def test_exact_intersection_ignores_benchmark_only_dates_without_filling() -> None:
    aligned = _calculate(
        [(date(2020, 1, 2), "10"), (date(2020, 1, 6), "20")],
        [
            (date(2019, 12, 31), "90"),
            (date(2020, 1, 2), "100"),
            (date(2020, 1, 3), "110"),
        ],
    )

    assert aligned.aligned_trading_dates == (date(2020, 1, 2),)
    assert aligned.aligned_close_observation_count.tolist() == [1, 1]
    assert aligned.trailing_valid_aligned_return_count.tolist() == [0, 0]
    assert aligned.subject_aligned_return_1d_pct.null_mask.tolist() == [True]


def test_zero_on_either_prior_close_nulls_pair_and_resets_trailing_count() -> None:
    dates = [date(2020, 1, day) for day in range(1, 5)]
    aligned = _calculate(
        list(zip(dates, ["0", "2", "4", "8"], strict=True)),
        list(zip(dates, ["10", "0", "5", "10"], strict=True)),
    )

    assert aligned.subject_aligned_return_1d_pct.null_mask.tolist() == [
        True,
        True,
        True,
        False,
    ]
    assert aligned.spx_aligned_return_1d_pct.null_mask.tolist() == [
        True,
        True,
        True,
        False,
    ]
    assert aligned.subject_aligned_return_1d_pct.value_at(3) == 1.0
    assert aligned.spx_aligned_return_1d_pct.value_at(3) == 1.0
    assert aligned.trailing_valid_aligned_return_count.tolist() == [0, 0, 0, 1]


def test_negative_and_tiny_nonzero_denominators_remain_eligible() -> None:
    dates = [date(2020, 1, day) for day in range(1, 4)]
    aligned = _calculate(
        list(zip(dates, ["-2", "-1", "-1e-300"], strict=True)),
        list(zip(dates, ["-4", "-2", "-1e-300"], strict=True)),
    )

    assert aligned.subject_aligned_return_1d_pct.value_at(1) == -0.5
    assert aligned.spx_aligned_return_1d_pct.value_at(1) == -0.5
    assert aligned.subject_aligned_return_1d_pct.value_at(2) == pytest.approx(-1.0)
    assert aligned.spx_aligned_return_1d_pct.value_at(2) == pytest.approx(-1.0)
    assert aligned.trailing_valid_aligned_return_count.tolist() == [0, 1, 2]


def test_empty_benchmark_retains_subject_rows_with_zero_counts() -> None:
    aligned = _calculate(
        [(date(2020, 1, 2), "10"), (date(2020, 1, 3), "20")],
        [],
    )

    assert aligned.aligned_observation_count == 0
    assert aligned.subject_observation_count == 2
    assert aligned.aligned_trading_dates == ()
    assert aligned.subject_aligned_close.shape == (0,)
    assert aligned.spx_aligned_close.shape == (0,)
    assert aligned.aligned_close_observation_count.tolist() == [0, 0]
    assert aligned.trailing_valid_aligned_return_count.tolist() == [0, 0]


def test_arrays_are_read_only_contiguous_and_use_contract_dtypes() -> None:
    aligned = _calculate(
        [(date(2020, 1, 2), "10"), (date(2020, 1, 3), "20")],
        [(date(2020, 1, 2), "100"), (date(2020, 1, 3), "110")],
    )

    for values in (aligned.subject_aligned_close, aligned.spx_aligned_close):
        assert values.dtype == np.dtype(np.float64)
        assert values.flags.c_contiguous
        assert not values.flags.writeable
    for values in (
        aligned.aligned_close_observation_count,
        aligned.trailing_valid_aligned_return_count,
    ):
        assert values.dtype == np.dtype(np.int64)
        assert values.flags.c_contiguous
        assert not values.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        aligned.aligned_close_observation_count[0] = 99


def test_future_subject_and_benchmark_rows_do_not_change_prefix_alignment() -> None:
    dates = [date(2020, 1, day) for day in range(1, 6)]
    full = _calculate(
        list(zip(dates, ["10", "20", "30", "40", "50"], strict=True)),
        list(zip(dates, ["100", "110", "120", "130", "140"], strict=True)),
    )
    prefix = _calculate(
        list(zip(dates[:3], ["10", "20", "30"], strict=True)),
        list(zip(dates[:3], ["100", "110", "120"], strict=True)),
    )

    assert prefix.aligned_trading_dates == full.aligned_trading_dates[:3]
    np.testing.assert_array_equal(
        prefix.subject_aligned_return_1d_pct.values,
        full.subject_aligned_return_1d_pct.values[:3],
    )
    np.testing.assert_array_equal(
        prefix.spx_aligned_return_1d_pct.values,
        full.spx_aligned_return_1d_pct.values[:3],
    )


def test_nonfinite_aligned_return_fails_calculation() -> None:
    with pytest.raises(
        TechIndicatorsCalculationError,
        match="subject_aligned_return_1d_pct.*aligned observation 1",
    ):
        _calculate(
            [(date(2020, 1, 2), "1e-320"), (date(2020, 1, 3), "1")],
            [(date(2020, 1, 2), "1"), (date(2020, 1, 3), "2")],
        )


def test_calculate_aligned_returns_rejects_wrong_input_types() -> None:
    history = _benchmark_history([])
    subject = normalize_source_bars((_bar(SUBJECT_ID, date(2020, 1, 2), "1"),))

    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_aligned_returns(object(), history)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="BenchmarkHistory"):
        calculate_aligned_returns(subject, object())  # type: ignore[arg-type]
