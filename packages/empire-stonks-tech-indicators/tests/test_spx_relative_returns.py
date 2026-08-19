from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    BenchmarkHistory,
    ResolvedBenchmark,
    SourceBar,
    SpxRelativeReturnArrays,
    TechIndicatorsCalculationError,
    calculate_aligned_returns,
    calculate_spx_relative_returns,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import spx_relative_returns as relative_module


SUBJECT_ID = UUID("00000000-0000-4000-8000-000000000001")
SPX_ID = UUID("00000000-0000-4000-8000-000000000002")
START_DATE = date(2020, 1, 1)


def _bar(listing_id: UUID, index: int, close: Decimal) -> SourceBar:
    return SourceBar(
        provider_listing_id=listing_id,
        trading_date=START_DATE + timedelta(days=index),
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("100"),
    )


def _benchmark(rows: list[tuple[int, Decimal]]) -> BenchmarkHistory:
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
        bars=tuple(_bar(SPX_ID, index, close) for index, close in rows),
    )


def _calculate(
    subject_closes: list[Decimal],
    benchmark_rows: list[tuple[int, Decimal]],
) -> SpxRelativeReturnArrays:
    subject = normalize_source_bars(
        _bar(SUBJECT_ID, index, close)
        for index, close in enumerate(subject_closes)
    )
    aligned = calculate_aligned_returns(subject, _benchmark(benchmark_rows))
    return calculate_spx_relative_returns(aligned)


def test_spx_relative_return_api_is_explicitly_exported() -> None:
    assert relative_module.__all__ == [
        "SPX_RELATIVE_RETURN_FIELDS",
        "SPX_RELATIVE_RETURN_PERIODS",
        "SpxRelativeReturnArrays",
        "calculate_spx_relative_returns",
    ]
    assert relative_module.SPX_RELATIVE_RETURN_PERIODS == (20, 63, 126, 252)
    assert public_api.SpxRelativeReturnArrays is SpxRelativeReturnArrays
    assert (
        public_api.calculate_spx_relative_returns
        is calculate_spx_relative_returns
    )


@pytest.mark.parametrize(
    ("field_name", "period"),
    relative_module.SPX_RELATIVE_RETURN_FIELDS,
)
def test_each_relative_return_warms_up_then_compounds_exact_aligned_pairs(
    field_name: str,
    period: int,
) -> None:
    subject = [Decimal(index + 1) for index in range(260)]
    benchmark = [(index, Decimal("100")) for index in range(260)]
    relative = _calculate(subject, benchmark)
    series = getattr(relative, field_name)

    assert series.null_mask[:period].all()
    assert series.value_at(period - 1) is None
    assert series.value_at(period) == pytest.approx(float(period))


def test_subject_only_date_is_null_and_does_not_consume_return_window() -> None:
    subject = [Decimal(index + 1) for index in range(30)]
    benchmark = [
        (index, Decimal("100"))
        for index in range(30)
        if index != 10
    ]
    relative = _calculate(subject, benchmark)

    assert relative.relative_return_spx_20d_pct.value_at(10) is None
    assert relative.relative_return_spx_20d_pct.value_at(20) is None
    assert relative.relative_return_spx_20d_pct.value_at(21) == pytest.approx(21.0)


def test_invalid_pair_nulls_complete_windows_until_it_ages_out() -> None:
    subject = [Decimal(index + 1) for index in range(35)]
    subject[5] = Decimal("0")
    benchmark = [(index, Decimal("100")) for index in range(35)]
    relative = _calculate(subject, benchmark)
    series = relative.relative_return_spx_20d_pct

    assert series.value_at(20) is None
    assert series.value_at(25) is None
    assert series.value_at(26) is not None


def test_exact_zero_spx_gross_denominator_is_null() -> None:
    subject = [Decimal(index + 1) for index in range(22)]
    benchmark_closes = [Decimal("100")] * 20 + [Decimal("0"), Decimal("100")]
    relative = _calculate(
        subject,
        list(enumerate(benchmark_closes)),
    )

    assert relative.relative_return_spx_20d_pct.value_at(20) is None
    assert relative.relative_return_spx_20d_pct.value_at(21) is None


def test_negative_gross_values_remain_valid_when_spx_gross_is_nonzero() -> None:
    subject = [Decimal(index + 1) for index in range(21)]
    benchmark_closes = [Decimal("100")] * 20 + [Decimal("-100")]
    relative = _calculate(
        subject,
        list(enumerate(benchmark_closes)),
    )

    expected = float((Decimal(21) / Decimal(1)) / Decimal("-1") - 1)
    assert relative.relative_return_spx_20d_pct.value_at(20) == expected


def test_nonfinite_chronological_product_fails_calculation() -> None:
    subject = [Decimal("1e-320"), Decimal("1e-160"), Decimal("1")]
    subject.extend([Decimal("1")] * 18)

    with pytest.raises(
        TechIndicatorsCalculationError,
        match="subject gross.*aligned observation 20",
    ):
        _calculate(
            subject,
            [(index, Decimal("100")) for index in range(21)],
        )


def test_outputs_are_read_only_subject_order_arrays() -> None:
    relative = _calculate(
        [Decimal(index + 1) for index in range(25)],
        [
            (index, Decimal("100"))
            for index in range(25)
            if index != 10
        ],
    )

    for field_name, _ in relative_module.SPX_RELATIVE_RETURN_FIELDS:
        series = getattr(relative, field_name)
        assert series.values.shape == (25,)
        assert series.values.dtype == np.dtype(np.float64)
        assert series.values.flags.c_contiguous
        assert not series.values.flags.writeable
        assert series.null_mask.dtype == np.dtype(np.bool_)
        assert not series.null_mask.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        relative.relative_return_spx_20d_pct.values[0] = 0.0


def test_future_rows_do_not_change_relative_return_prefix() -> None:
    subject = [Decimal(index + 1) for index in range(150)]
    benchmark = [(index, Decimal("100")) for index in range(150)]
    full = _calculate(subject, benchmark)
    prefix = _calculate(subject[:80], benchmark[:80])

    for field_name, _ in relative_module.SPX_RELATIVE_RETURN_FIELDS:
        full_series = getattr(full, field_name)
        prefix_series = getattr(prefix, field_name)
        np.testing.assert_array_equal(prefix_series.values, full_series.values[:80])
        np.testing.assert_array_equal(
            prefix_series.null_mask,
            full_series.null_mask[:80],
        )


def test_calculate_spx_relative_returns_rejects_wrong_input_type() -> None:
    with pytest.raises(TypeError, match="AlignedReturnArrays"):
        calculate_spx_relative_returns(object())  # type: ignore[arg-type]
