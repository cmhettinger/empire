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
    SpxPriceRatioArrays,
    TechIndicatorsCalculationError,
    calculate_aligned_returns,
    calculate_spx_price_ratios,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import spx_price_ratio as ratio_module


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
) -> SpxPriceRatioArrays:
    subject = normalize_source_bars(
        _bar(SUBJECT_ID, index, close)
        for index, close in enumerate(subject_closes)
    )
    aligned = calculate_aligned_returns(subject, _benchmark(benchmark_rows))
    return calculate_spx_price_ratios(aligned)


def test_spx_price_ratio_api_is_explicitly_exported() -> None:
    assert ratio_module.__all__ == [
        "SPX_PRICE_RATIO_FIELDS",
        "SPX_RATIO_TREND_PERIODS",
        "SpxPriceRatioArrays",
        "calculate_spx_price_ratios",
    ]
    assert ratio_module.SPX_RATIO_TREND_PERIODS == (20, 50)
    assert ratio_module.SPX_PRICE_RATIO_FIELDS == (
        "rel_spx",
        "pct_rel_spx_20",
        "pct_rel_spx_50",
    )
    assert public_api.SpxPriceRatioArrays is SpxPriceRatioArrays
    assert public_api.calculate_spx_price_ratios is calculate_spx_price_ratios


def test_ratio_trends_warm_up_at_exact_aligned_boundaries() -> None:
    subject = [Decimal(index + 1) * 100 for index in range(55)]
    benchmark = [(index, Decimal("100")) for index in range(55)]
    ratios = _calculate(subject, benchmark)

    assert ratios.observation_count == 55
    assert ratios.rel_spx.value_at(0) == 1.0
    assert ratios.rel_spx.value_at(54) == 55.0
    assert ratios.pct_rel_spx_20.null_mask[:19].all()
    assert ratios.pct_rel_spx_20.value_at(19) == pytest.approx(20 / 10.5 - 1)
    assert ratios.pct_rel_spx_50.null_mask[:49].all()
    assert ratios.pct_rel_spx_50.value_at(49) == pytest.approx(50 / 25.5 - 1)


def test_subject_only_date_stays_null_and_does_not_consume_ratio_window() -> None:
    subject = [Decimal(index + 1) * 100 for index in range(25)]
    benchmark = [
        (index, Decimal("100"))
        for index in range(25)
        if index != 10
    ]
    ratios = _calculate(subject, benchmark)

    assert ratios.rel_spx.value_at(10) is None
    assert ratios.pct_rel_spx_20.value_at(19) is None
    expected_ratios = [Decimal(index + 1) for index in range(21) if index != 10]
    expected_mean = sum(expected_ratios) / Decimal(20)
    assert ratios.pct_rel_spx_20.value_at(20) == pytest.approx(
        float(Decimal(21) / expected_mean - 1)
    )


def test_zero_spx_close_nulls_ratio_and_complete_windows_until_recovery() -> None:
    subject = [Decimal(index + 1) for index in range(30)]
    benchmark = [
        (index, Decimal("0") if index == 5 else Decimal("1"))
        for index in range(30)
    ]
    ratios = _calculate(subject, benchmark)

    assert ratios.rel_spx.value_at(5) is None
    assert ratios.rel_spx.value_at(6) == 7.0
    assert ratios.pct_rel_spx_20.value_at(19) is None
    assert ratios.pct_rel_spx_20.value_at(24) is None
    assert ratios.pct_rel_spx_20.value_at(25) is not None


def test_zero_ratio_mean_is_null_without_changing_valid_zero_ratio() -> None:
    alternating = [
        Decimal("1") if index % 2 == 0 else Decimal("-1")
        for index in range(20)
    ]
    ratios = _calculate(
        [value * 100 for value in alternating],
        [(index, Decimal("100")) for index in range(20)],
    )

    assert ratios.rel_spx.value_at(1) == -1.0
    assert ratios.pct_rel_spx_20.value_at(19) is None

    zero_ratio = _calculate(
        [Decimal("0")] * 20,
        [(index, Decimal("100")) for index in range(20)],
    )
    assert zero_ratio.rel_spx.value_at(19) == 0.0
    assert zero_ratio.pct_rel_spx_20.value_at(19) is None


def test_negative_and_tiny_nonzero_spx_denominators_are_valid() -> None:
    ratios = _calculate(
        [Decimal("2"), Decimal("1e-300")],
        [(0, Decimal("-4")), (1, Decimal("1e-300"))],
    )

    assert ratios.rel_spx.value_at(0) == -0.5
    assert ratios.rel_spx.value_at(1) == 1.0


def test_nonfinite_ratio_fails_calculation() -> None:
    with pytest.raises(
        TechIndicatorsCalculationError,
        match="rel_spx.*aligned observation 0",
    ):
        _calculate(
            [Decimal("1")],
            [(0, Decimal("1e-320"))],
        )


def test_outputs_are_read_only_subject_order_arrays() -> None:
    ratios = _calculate(
        [Decimal("10"), Decimal("20"), Decimal("30")],
        [(0, Decimal("100")), (2, Decimal("100"))],
    )

    for field_name in ratio_module.SPX_PRICE_RATIO_FIELDS:
        series = getattr(ratios, field_name)
        assert series.values.shape == (3,)
        assert series.values.dtype == np.dtype(np.float64)
        assert series.values.flags.c_contiguous
        assert not series.values.flags.writeable
        assert series.null_mask.dtype == np.dtype(np.bool_)
        assert not series.null_mask.flags.writeable
    assert ratios.rel_spx.null_mask.tolist() == [False, True, False]
    with pytest.raises(ValueError, match="read-only"):
        ratios.rel_spx.values[0] = 0.0


def test_future_rows_do_not_change_ratio_trend_prefix() -> None:
    subject = [Decimal(index + 1) * 100 for index in range(60)]
    benchmark = [(index, Decimal("100")) for index in range(60)]
    full = _calculate(subject, benchmark)
    prefix = _calculate(subject[:30], benchmark[:30])

    for field_name in ratio_module.SPX_PRICE_RATIO_FIELDS:
        full_series = getattr(full, field_name)
        prefix_series = getattr(prefix, field_name)
        np.testing.assert_array_equal(prefix_series.values, full_series.values[:30])
        np.testing.assert_array_equal(
            prefix_series.null_mask,
            full_series.null_mask[:30],
        )


def test_calculate_spx_price_ratios_rejects_wrong_input_type() -> None:
    with pytest.raises(TypeError, match="AlignedReturnArrays"):
        calculate_spx_price_ratios(object())  # type: ignore[arg-type]
