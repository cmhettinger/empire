from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, localcontext
from math import sqrt
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    BenchmarkHistory,
    ResolvedBenchmark,
    SourceBar,
    SpxCorrelationArrays,
    TechIndicatorsCalculationError,
    calculate_aligned_returns,
    calculate_spx_correlation,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import spx_correlation as correlation_module


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


def _return_inputs(
    *,
    observation_count: int,
    subject_transform,
) -> tuple[list[Decimal], list[tuple[int, Decimal]], list[float], list[float]]:
    pattern = [
        Decimal("-0.004"),
        Decimal("-0.001"),
        Decimal("0.002"),
        Decimal("0.005"),
        Decimal("0.001"),
    ]
    spx_returns = [
        pattern[index % len(pattern)] for index in range(observation_count - 1)
    ]
    subject_returns = [
        subject_transform(value, index)
        for index, value in enumerate(spx_returns)
    ]
    subject_closes = _closes_from_returns(subject_returns)
    spx_closes = _closes_from_returns(spx_returns)
    return (
        subject_closes,
        list(enumerate(spx_closes)),
        [float(value) for value in subject_returns],
        [float(value) for value in spx_returns],
    )


def _pearson(subject: list[float], spx: list[float]) -> float:
    subject_mean = sum(subject) / len(subject)
    spx_mean = sum(spx) / len(spx)
    covariance = sum(
        (x - subject_mean) * (y - spx_mean)
        for x, y in zip(subject, spx, strict=True)
    ) / (len(subject) - 1)
    subject_variance = sum((x - subject_mean) ** 2 for x in subject) / (
        len(subject) - 1
    )
    spx_variance = sum((y - spx_mean) ** 2 for y in spx) / (len(spx) - 1)
    return covariance / (sqrt(subject_variance) * sqrt(spx_variance))


def test_spx_correlation_api_is_explicitly_exported() -> None:
    assert correlation_module.__all__ == [
        "SPX_CORRELATION_BOUND_TOLERANCE",
        "SPX_CORRELATION_FIELDS",
        "SPX_CORRELATION_PERIODS",
        "SpxCorrelationArrays",
        "calculate_spx_correlation",
    ]
    assert correlation_module.SPX_CORRELATION_PERIODS == (60, 252)
    assert correlation_module.SPX_CORRELATION_FIELDS == (
        ("spx_correlation_60d", 60),
        ("spx_correlation_252d", 252),
    )
    assert correlation_module.SPX_CORRELATION_BOUND_TOLERANCE == 1e-12
    assert public_api.SpxCorrelationArrays is SpxCorrelationArrays
    assert public_api.calculate_spx_correlation is calculate_spx_correlation


@pytest.mark.parametrize(
    ("field_name", "period"),
    correlation_module.SPX_CORRELATION_FIELDS,
)
def test_correlation_warms_up_and_matches_perfect_positive_returns(
    field_name: str,
    period: int,
) -> None:
    subject, benchmark, _, _ = _return_inputs(
        observation_count=260,
        subject_transform=lambda value, _: Decimal("2") * value,
    )
    correlation = calculate_spx_correlation(_aligned(subject, benchmark))
    series = getattr(correlation, field_name)

    assert series.null_mask[:period].all()
    assert series.value_at(period - 1) is None
    assert series.value_at(period) == pytest.approx(1.0, abs=1e-12)


def test_perfect_negative_returns_produce_negative_one() -> None:
    subject, benchmark, _, _ = _return_inputs(
        observation_count=65,
        subject_transform=lambda value, _: Decimal("-2") * value,
    )
    correlation = calculate_spx_correlation(_aligned(subject, benchmark))

    assert correlation.spx_correlation_60d.value_at(60) == pytest.approx(-1.0)


def test_nonperfect_correlation_matches_independent_sample_formula() -> None:
    subject, benchmark, subject_returns, spx_returns = _return_inputs(
        observation_count=65,
        subject_transform=lambda value, index: (
            Decimal("0.75") * value
            + Decimal(index % 3 - 1) * Decimal("0.0007")
        ),
    )
    correlation = calculate_spx_correlation(_aligned(subject, benchmark))

    expected = _pearson(subject_returns[:60], spx_returns[:60])
    assert correlation.spx_correlation_60d.value_at(60) == pytest.approx(
        expected,
        abs=1e-12,
    )


@pytest.mark.parametrize("constant_side", ["subject", "spx"])
def test_exact_zero_variance_is_null(constant_side: str) -> None:
    varying = [Decimal(index * index + 100) for index in range(65)]
    constant = [Decimal("100") for _ in range(65)]
    subject = constant if constant_side == "subject" else varying
    spx = constant if constant_side == "spx" else varying
    correlation = calculate_spx_correlation(
        _aligned(subject, list(enumerate(spx)))
    )

    assert correlation.spx_correlation_60d.value_at(60) is None
    assert correlation.spx_correlation_60d.null_mask[60:].all()


def test_subject_only_date_is_null_and_does_not_consume_window() -> None:
    subject = [Decimal(index * index + 100) for index in range(70)]
    benchmark = [
        (index, Decimal(index * index + index + 200))
        for index in range(70)
        if index != 10
    ]
    correlation = calculate_spx_correlation(_aligned(subject, benchmark))

    assert correlation.spx_correlation_60d.value_at(10) is None
    assert correlation.spx_correlation_60d.value_at(60) is None
    assert correlation.spx_correlation_60d.value_at(61) is not None


def test_invalid_pair_nulls_correlation_until_it_ages_out() -> None:
    subject = [Decimal(index + 1) for index in range(70)]
    subject[5] = Decimal("0")
    benchmark = [(index, Decimal(index * index + 100)) for index in range(70)]
    correlation = calculate_spx_correlation(_aligned(subject, benchmark))

    assert correlation.spx_correlation_60d.value_at(60) is None
    assert correlation.spx_correlation_60d.value_at(65) is None
    assert correlation.spx_correlation_60d.value_at(66) is not None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.25, 0.25),
        (1.0 + 5e-13, 1.0),
        (-1.0 - 5e-13, -1.0),
    ],
)
def test_boundary_canonicalization_is_narrow(value: float, expected: float) -> None:
    assert correlation_module._canonicalize_correlation(
        value,
        field_name="spx_correlation_60d",
        aligned_index=60,
    ) == pytest.approx(expected)


@pytest.mark.parametrize("value", [1.0 + 2e-12, -1.0 - 2e-12])
def test_materially_out_of_bounds_correlation_fails(value: float) -> None:
    with pytest.raises(
        TechIndicatorsCalculationError,
        match="out-of-bounds correlation.*aligned observation 60",
    ):
        correlation_module._canonicalize_correlation(
            value,
            field_name="spx_correlation_60d",
            aligned_index=60,
        )


def test_nonfinite_sample_statistic_fails_calculation() -> None:
    closes = [
        Decimal("1e-308") if index % 2 == 0 else Decimal("1")
        for index in range(61)
    ]

    with pytest.raises(
        TechIndicatorsCalculationError,
        match="(subject mean|sample covariance).*aligned observation 60",
    ):
        calculate_spx_correlation(_aligned(closes, list(enumerate(closes))))


def test_outputs_are_read_only_subject_order_arrays() -> None:
    subject, benchmark, _, _ = _return_inputs(
        observation_count=65,
        subject_transform=lambda value, _: Decimal("2") * value,
    )
    correlation = calculate_spx_correlation(_aligned(subject, benchmark))

    assert correlation.observation_count == 65
    for field_name, _ in correlation_module.SPX_CORRELATION_FIELDS:
        series = getattr(correlation, field_name)
        assert series.values.shape == (65,)
        assert series.values.dtype == np.dtype(np.float64)
        assert series.values.flags.c_contiguous
        assert not series.values.flags.writeable
        assert series.null_mask.dtype == np.dtype(np.bool_)
        assert not series.null_mask.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        correlation.spx_correlation_60d.values[0] = 0.0


def test_future_rows_do_not_change_correlation_prefix() -> None:
    subject, benchmark, _, _ = _return_inputs(
        observation_count=260,
        subject_transform=lambda value, index: (
            Decimal("0.75") * value
            + Decimal(index % 3 - 1) * Decimal("0.0007")
        ),
    )
    full = calculate_spx_correlation(_aligned(subject, benchmark))
    prefix = calculate_spx_correlation(_aligned(subject[:100], benchmark[:100]))

    for field_name, _ in correlation_module.SPX_CORRELATION_FIELDS:
        full_series = getattr(full, field_name)
        prefix_series = getattr(prefix, field_name)
        np.testing.assert_array_equal(prefix_series.values, full_series.values[:100])
        np.testing.assert_array_equal(
            prefix_series.null_mask,
            full_series.null_mask[:100],
        )


def test_calculate_spx_correlation_rejects_wrong_input_type() -> None:
    with pytest.raises(TypeError, match="AlignedReturnArrays"):
        calculate_spx_correlation(object())  # type: ignore[arg-type]
