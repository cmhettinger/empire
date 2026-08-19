from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, localcontext
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    BenchmarkHistory,
    ResolvedBenchmark,
    SourceBar,
    SpxBetaArrays,
    TechIndicatorsCalculationError,
    calculate_aligned_returns,
    calculate_spx_beta,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import spx_beta as beta_module


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


def _aligned(
    subject_closes: list[Decimal],
    benchmark_rows: list[tuple[int, Decimal]],
):
    subject = normalize_source_bars(
        _bar(SUBJECT_ID, index, close)
        for index, close in enumerate(subject_closes)
    )
    return calculate_aligned_returns(subject, _benchmark(benchmark_rows))


def _closes_from_returns(returns: list[Decimal]) -> list[Decimal]:
    with localcontext() as context:
        context.prec = 80
        closes = [Decimal("100")]
        for value in returns:
            closes.append(closes[-1] * (Decimal("1") + value))
        return closes


def _linear_beta_inputs(
    *,
    observation_count: int,
    multiplier: Decimal,
    scale: Decimal = Decimal("1"),
) -> tuple[list[Decimal], list[tuple[int, Decimal]]]:
    pattern = [Decimal("-0.004"), Decimal("-0.001"), Decimal("0.002"), Decimal("0.005")]
    spx_returns = [
        pattern[index % len(pattern)] * scale
        for index in range(observation_count - 1)
    ]
    subject_returns = [multiplier * value for value in spx_returns]
    subject_closes = _closes_from_returns(subject_returns)
    spx_closes = _closes_from_returns(spx_returns)
    return subject_closes, list(enumerate(spx_closes))


def test_spx_beta_api_is_explicitly_exported() -> None:
    assert beta_module.__all__ == [
        "SPX_BETA_FIELDS",
        "SPX_BETA_PERIODS",
        "SpxBetaArrays",
        "calculate_spx_beta",
    ]
    assert beta_module.SPX_BETA_PERIODS == (60, 252)
    assert beta_module.SPX_BETA_FIELDS == (
        ("spx_beta_60d", 60),
        ("spx_beta_252d", 252),
    )
    assert public_api.SpxBetaArrays is SpxBetaArrays
    assert public_api.calculate_spx_beta is calculate_spx_beta


@pytest.mark.parametrize(("field_name", "period"), beta_module.SPX_BETA_FIELDS)
def test_beta_warms_up_at_complete_window_and_matches_linear_returns(
    field_name: str,
    period: int,
) -> None:
    subject, benchmark = _linear_beta_inputs(
        observation_count=260,
        multiplier=Decimal("2"),
    )
    beta = calculate_spx_beta(_aligned(subject, benchmark))
    series = getattr(beta, field_name)

    assert series.null_mask[:period].all()
    assert series.value_at(period - 1) is None
    assert series.value_at(period) == pytest.approx(2.0, abs=1e-10)


@pytest.mark.parametrize("multiplier", [Decimal("-2"), Decimal("1000")])
def test_beta_is_not_arbitrarily_bounded(multiplier: Decimal) -> None:
    subject, benchmark = _linear_beta_inputs(
        observation_count=65,
        multiplier=multiplier,
        scale=Decimal("0.001"),
    )
    beta = calculate_spx_beta(_aligned(subject, benchmark))

    assert beta.spx_beta_60d.value_at(60) == pytest.approx(
        float(multiplier),
        rel=1e-10,
        abs=1e-10,
    )


def test_exact_zero_spx_variance_is_null() -> None:
    subject = [Decimal(index + 1) for index in range(65)]
    benchmark = [(index, Decimal("100")) for index in range(65)]
    beta = calculate_spx_beta(_aligned(subject, benchmark))

    assert beta.spx_beta_60d.value_at(60) is None
    assert beta.spx_beta_60d.null_mask[60:].all()


def test_subject_only_date_is_null_and_does_not_consume_beta_window() -> None:
    subject = [Decimal(index * index + 100) for index in range(70)]
    benchmark = [
        (index, Decimal(index * index + index + 200))
        for index in range(70)
        if index != 10
    ]
    beta = calculate_spx_beta(_aligned(subject, benchmark))

    assert beta.spx_beta_60d.value_at(10) is None
    assert beta.spx_beta_60d.value_at(60) is None
    assert beta.spx_beta_60d.value_at(61) is not None


def test_invalid_pair_nulls_beta_until_it_ages_out() -> None:
    subject = [Decimal(index + 1) for index in range(70)]
    subject[5] = Decimal("0")
    benchmark = [(index, Decimal(index * index + 100)) for index in range(70)]
    beta = calculate_spx_beta(_aligned(subject, benchmark))

    assert beta.spx_beta_60d.value_at(60) is None
    assert beta.spx_beta_60d.value_at(65) is None
    assert beta.spx_beta_60d.value_at(66) is not None


def test_nonfinite_sample_statistic_fails_calculation() -> None:
    closes = [
        Decimal("1e-308") if index % 2 == 0 else Decimal("1")
        for index in range(61)
    ]

    with pytest.raises(
        TechIndicatorsCalculationError,
        match="(subject mean|sample covariance).*aligned observation 60",
    ):
        calculate_spx_beta(
            _aligned(closes, list(enumerate(closes))),
        )


def test_outputs_are_read_only_subject_order_arrays() -> None:
    subject, benchmark = _linear_beta_inputs(
        observation_count=65,
        multiplier=Decimal("2"),
    )
    beta = calculate_spx_beta(_aligned(subject, benchmark))

    assert beta.observation_count == 65
    for field_name, _ in beta_module.SPX_BETA_FIELDS:
        series = getattr(beta, field_name)
        assert series.values.shape == (65,)
        assert series.values.dtype == np.dtype(np.float64)
        assert series.values.flags.c_contiguous
        assert not series.values.flags.writeable
        assert series.null_mask.dtype == np.dtype(np.bool_)
        assert not series.null_mask.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        beta.spx_beta_60d.values[0] = 0.0


def test_future_rows_do_not_change_beta_prefix() -> None:
    subject, benchmark = _linear_beta_inputs(
        observation_count=260,
        multiplier=Decimal("2"),
    )
    full = calculate_spx_beta(_aligned(subject, benchmark))
    prefix = calculate_spx_beta(_aligned(subject[:100], benchmark[:100]))

    for field_name, _ in beta_module.SPX_BETA_FIELDS:
        full_series = getattr(full, field_name)
        prefix_series = getattr(prefix, field_name)
        np.testing.assert_array_equal(prefix_series.values, full_series.values[:100])
        np.testing.assert_array_equal(
            prefix_series.null_mask,
            full_series.null_mask[:100],
        )


def test_calculate_spx_beta_rejects_wrong_input_type() -> None:
    with pytest.raises(TypeError, match="AlignedReturnArrays"):
        calculate_spx_beta(object())  # type: ignore[arg-type]
