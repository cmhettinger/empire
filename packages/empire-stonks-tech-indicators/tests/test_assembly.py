from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from math import isclose
from uuid import UUID

import pytest

from empire_stonks_tech_indicators import (
    BenchmarkHistory,
    EligibleListing,
    ResolvedBenchmark,
    SourceBar,
    TechIndicatorsValidationError,
    assemble_feature_rows,
    normalize_source_bars,
)
from empire_stonks_tech_indicators.models import PYTHON_FEATURE_FIELDS


SUBJECT_ID = UUID("41111111-1111-4111-8111-111111111111")
BENCHMARK_ID = UUID("42222222-2222-4222-8222-222222222222")
RUN_ID = UUID("43333333-3333-4333-8333-333333333333")
CALCULATED_AT = datetime(2026, 8, 22, 16, 30, tzinfo=UTC)

GENERATED_OR_DATABASE_FIELDS = {
    "created_at",
    "updated_at",
    "dollar_volume",
    "intraday_return_1d_pct",
    "daily_range_pct",
    "close_location_1d",
    "pct_sma_20",
    "pct_sma_50",
    "pct_sma_200",
    "pct_ema_20",
    "pct_ema_50",
    "pct_sma_20_vs_50",
    "pct_sma_20_vs_200",
    "pct_sma_50_vs_200",
    "pct_hh_20",
    "pct_hh_50",
    "pct_hh_252",
    "pct_ll_20",
    "pct_ll_50",
    "atr_pct_14",
    "bollinger_percent_b_20_2",
    "bollinger_bandwidth_20_2",
    "volume_ratio_20",
    "macd_12_26_pct",
    "macd_histogram_12_26_9_pct",
}
WRITE_PAYLOAD_FIELDS = (
    "provider_listing_id",
    "trading_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "relative_strength_benchmark_provider_listing_id",
    "history_observation_count",
    "calculation_version",
    "run_id",
    "calculated_at",
    *PYTHON_FEATURE_FIELDS,
)


def _bars(
    listing_id: UUID,
    count: int,
    *,
    base: Decimal,
    step: Decimal,
) -> tuple[SourceBar, ...]:
    start = date(2025, 1, 1)
    result = []
    for index in range(count):
        close = base + step * index + Decimal(index % 11) / Decimal("100")
        result.append(
            SourceBar(
                provider_listing_id=listing_id,
                trading_date=start + timedelta(days=index),
                open=close - Decimal("0.25"),
                high=close + Decimal("1.5"),
                low=close - Decimal("1.25"),
                close=close,
                volume=Decimal(10_000 + index * 3),
            )
        )
    return tuple(result)


def _subject(
    bars: tuple[SourceBar, ...],
    *,
    provider_code: str = "EODDATA",
    market: str = "NYSE",
) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=bars[0].provider_listing_id,
        provider_code=provider_code,
        market=market,
        ticker="ASSEMBLY",
        instrument_type_code="UNKNOWN",
        status="ACTIVE",
        first_trading_date=bars[0].trading_date,
        last_trading_date=bars[-1].trading_date,
        source_observation_count=len(bars),
    )


def _benchmark(count: int) -> BenchmarkHistory:
    return BenchmarkHistory(
        benchmark=ResolvedBenchmark(provider_listing_id=BENCHMARK_ID),
        bars=_bars(
            BENCHMARK_ID,
            count,
            base=Decimal("4200"),
            step=Decimal("0.41"),
        ),
    )


@pytest.fixture(scope="module")
def assembled_state():
    bars = _bars(
        SUBJECT_ID,
        260,
        base=Decimal("100"),
        step=Decimal("0.17"),
    )
    subject = _subject(bars)
    benchmark = _benchmark(len(bars))
    arrays = normalize_source_bars(bars)
    rows = assemble_feature_rows(
        arrays,
        subject=subject,
        calculated_at=CALCULATED_AT,
        benchmark_history=benchmark,
        run_id=RUN_ID,
    )
    return bars, subject, benchmark, arrays, rows


def test_assembles_exact_65_column_rows_in_source_order(assembled_state) -> None:
    bars, _subject_row, _benchmark_row, _arrays, rows = assembled_state

    assert len(rows) == len(bars)
    assert tuple(row.source for row in rows) == bars
    assert tuple(row.history_observation_count for row in rows) == tuple(
        range(1, len(rows) + 1)
    )
    for row in rows:
        payload = row.to_dict()
        assert len(payload) == 65
        assert tuple(payload) == WRITE_PAYLOAD_FIELDS
        assert set(PYTHON_FEATURE_FIELDS) <= set(payload)
        assert not GENERATED_OR_DATABASE_FIELDS & set(payload)
        assert row.calculation_version == "TECH_INDICATORS_V1"
        assert row.calculated_at == CALCULATED_AT
        assert row.run_id == RUN_ID
        assert row.relative_strength_benchmark_provider_listing_id == BENCHMARK_ID


def test_preserves_warmups_and_populates_the_complete_v1_tail(
    assembled_state,
) -> None:
    _bars_value, _subject_row, _benchmark_row, _arrays, rows = assembled_state

    assert rows[0].return_1d_pct is None
    assert rows[0].sma_20 is None
    assert rows[0].consecutive_up_days == 0
    assert rows[19].sma_20 is not None
    assert rows[19].return_20d_pct is None
    assert rows[20].return_20d_pct is not None
    assert rows[252].return_252d_pct is not None
    assert all(
        getattr(rows[-1], field_name) is not None
        for field_name in PYTHON_FEATURE_FIELDS
    )


def test_source_position_and_return_values_cannot_drift(assembled_state) -> None:
    bars, _subject_row, _benchmark_row, _arrays, rows = assembled_state

    for index in (1, 37, 128, 259):
        expected = float(bars[index].close / bars[index - 1].close - 1)
        assert isclose(
            rows[index].return_1d_pct,
            expected,
            rel_tol=1e-10,
            abs_tol=1e-12,
        )
        assert rows[index].source.trading_date == bars[index].trading_date


def test_assembles_unsupported_subject_with_intentional_spx_nulls() -> None:
    bars = _bars(
        SUBJECT_ID,
        40,
        base=Decimal("100"),
        step=Decimal("0.17"),
    )
    rows = assemble_feature_rows(
        normalize_source_bars(bars),
        subject=_subject(bars, provider_code="YAHOO", market="XIDX"),
        calculated_at=CALCULATED_AT,
    )

    spx_fields = PYTHON_FEATURE_FIELDS[-11:]
    assert all(
        row.relative_strength_benchmark_provider_listing_id is None
        for row in rows
    )
    assert all(
        getattr(row, field_name) is None
        for row in rows
        for field_name in spx_fields
    )


def test_supported_subject_requires_benchmark_history() -> None:
    bars = _bars(
        SUBJECT_ID,
        20,
        base=Decimal("100"),
        step=Decimal("0.17"),
    )
    with pytest.raises(TechIndicatorsValidationError, match="benchmark history"):
        assemble_feature_rows(
            normalize_source_bars(bars),
            subject=_subject(bars),
            calculated_at=CALCULATED_AT,
        )


@pytest.mark.parametrize(
    ("overrides", "error_type", "match"),
    [
        (
            {"calculation_version": "TECH_INDICATORS_V2"},
            ValueError,
            "TECH_INDICATORS_V1",
        ),
        ({"calculated_at": datetime(2026, 8, 22)}, ValueError, "timezone-aware"),
        ({"run_id": "not-a-uuid"}, TypeError, "UUID or None"),
    ],
)
def test_rejects_invalid_row_metadata(overrides, error_type, match) -> None:
    bars = _bars(
        SUBJECT_ID,
        5,
        base=Decimal("100"),
        step=Decimal("0.17"),
    )
    arguments = {
        "subject": _subject(bars, provider_code="YAHOO", market="XIDX"),
        "calculated_at": CALCULATED_AT,
        **overrides,
    }
    with pytest.raises(error_type, match=match):
        assemble_feature_rows(normalize_source_bars(bars), **arguments)


def test_rejects_subject_identity_or_coverage_drift() -> None:
    bars = _bars(
        SUBJECT_ID,
        5,
        base=Decimal("100"),
        step=Decimal("0.17"),
    )
    arrays = normalize_source_bars(bars)
    subject = _subject(bars, provider_code="YAHOO", market="XIDX")

    with pytest.raises(TechIndicatorsValidationError, match="calculation listing"):
        assemble_feature_rows(
            arrays,
            subject=EligibleListing(
                provider_listing_id=BENCHMARK_ID,
                provider_code=subject.provider_code,
                market=subject.market,
                ticker=subject.ticker,
                instrument_type_code=subject.instrument_type_code,
                status=subject.status,
                first_trading_date=subject.first_trading_date,
                last_trading_date=subject.last_trading_date,
                source_observation_count=subject.source_observation_count,
            ),
            calculated_at=CALCULATED_AT,
        )

    with pytest.raises(TechIndicatorsValidationError, match="observation count"):
        assemble_feature_rows(
            arrays,
            subject=EligibleListing(
                provider_listing_id=subject.provider_listing_id,
                provider_code=subject.provider_code,
                market=subject.market,
                ticker=subject.ticker,
                instrument_type_code=subject.instrument_type_code,
                status=subject.status,
                first_trading_date=subject.first_trading_date,
                last_trading_date=subject.last_trading_date,
                source_observation_count=subject.source_observation_count - 1,
            ),
            calculated_at=CALCULATED_AT,
        )
