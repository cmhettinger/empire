from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from empire_stonks_tech_indicators import (
    BenchmarkHistory,
    EligibleListing,
    FeatureRow,
    ResolvedBenchmark,
    SourceBar,
    TechIndicatorsValidationError,
    calculate_bar_structure,
    calculate_bollinger_state,
    calculate_directional_movement,
    calculate_macd,
    calculate_moving_average_trends,
    calculate_moving_averages,
    calculate_range_relationships,
    calculate_return_statistics,
    calculate_returns,
    calculate_rsi_atr,
    calculate_spx_features,
    calculate_streaks,
    calculate_volume_liquidity,
    normalize_source_bars,
    validate_feature_rows,
)
from empire_stonks_tech_indicators.models import PYTHON_FEATURE_FIELDS


SUBJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
BENCHMARK_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_ID = UUID("33333333-3333-4333-8333-333333333333")
CALCULATED_AT = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def _bars(
    listing_id: UUID,
    count: int,
    *,
    base: Decimal,
    increment: Decimal,
) -> tuple[SourceBar, ...]:
    start = date(2025, 1, 1)
    result = []
    for index in range(count):
        close = base + increment * index + Decimal(index % 7) / Decimal("100")
        result.append(
            SourceBar(
                provider_listing_id=listing_id,
                trading_date=start + timedelta(days=index),
                open=close - Decimal("0.2"),
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                volume=Decimal(1000 + index),
            )
        )
    return tuple(result)


def _listing(
    bars: tuple[SourceBar, ...],
    *,
    provider_code: str = "EODDATA",
    market: str = "NYSE",
) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=bars[0].provider_listing_id,
        provider_code=provider_code,
        market=market,
        ticker="TEST",
        instrument_type_code="UNKNOWN",
        status="ACTIVE",
        first_trading_date=bars[0].trading_date,
        last_trading_date=bars[-1].trading_date,
        source_observation_count=len(bars),
    )


def _benchmark_history(count: int) -> BenchmarkHistory:
    return BenchmarkHistory(
        benchmark=ResolvedBenchmark(provider_listing_id=BENCHMARK_ID),
        bars=_bars(
            BENCHMARK_ID,
            count,
            base=Decimal("4000"),
            increment=Decimal("0.37"),
        ),
    )


def _calculated_rows(
    bars: tuple[SourceBar, ...],
    *,
    subject: EligibleListing,
    benchmark_history: BenchmarkHistory | None,
) -> tuple[tuple[FeatureRow, ...], object]:
    arrays = normalize_source_bars(bars)
    returns = calculate_returns(arrays)
    bar_structure = calculate_bar_structure(arrays)
    moving_averages = calculate_moving_averages(arrays)
    moving_average_trends = calculate_moving_average_trends(
        arrays,
        moving_averages,
    )
    ranges = calculate_range_relationships(arrays)
    rsi_atr = calculate_rsi_atr(arrays)
    return_statistics = calculate_return_statistics(arrays, returns)
    bollinger = calculate_bollinger_state(arrays, moving_averages)
    directional = calculate_directional_movement(arrays)
    macd = calculate_macd(arrays, moving_averages)
    volume = calculate_volume_liquidity(arrays, bar_structure)
    streaks = calculate_streaks(arrays)
    spx = calculate_spx_features(
        arrays,
        subject=subject,
        benchmark_history=benchmark_history,
    )
    families = (
        returns,
        bar_structure,
        moving_averages,
        moving_average_trends,
        ranges,
        rsi_atr,
        return_statistics,
        bollinger,
        directional,
        macd,
        volume,
        spx,
    )

    rows = []
    for index, bar in enumerate(bars):
        values = {
            field_name: getattr(family, field_name).value_at(index)
            for field_name in PYTHON_FEATURE_FIELDS
            if field_name not in {"consecutive_up_days", "consecutive_down_days"}
            for family in families
            if hasattr(family, field_name)
        }
        rows.append(
            FeatureRow(
                source=bar,
                history_observation_count=index + 1,
                calculation_version="TECH_INDICATORS_V1",
                calculated_at=CALCULATED_AT,
                relative_strength_benchmark_provider_listing_id=(
                    spx.benchmark_provider_listing_id
                ),
                consecutive_up_days=int(streaks.consecutive_up_days[index]),
                consecutive_down_days=int(streaks.consecutive_down_days[index]),
                **values,
            )
        )
    return tuple(rows), arrays


@pytest.fixture(scope="module")
def supported_state():
    bars = _bars(
        SUBJECT_ID,
        260,
        base=Decimal("100"),
        increment=Decimal("0.13"),
    )
    subject = _listing(bars)
    benchmark = _benchmark_history(len(bars))
    rows, arrays = _calculated_rows(
        bars,
        subject=subject,
        benchmark_history=benchmark,
    )
    return rows, arrays, subject, benchmark


def test_validates_complete_supported_feature_image(supported_state) -> None:
    rows, arrays, subject, benchmark = supported_state

    assert (
        validate_feature_rows(
            rows,
            calculation_arrays=arrays,
            subject=subject,
            benchmark_history=benchmark,
        )
        is None
    )


def test_validates_unsupported_subject_with_null_spx_family() -> None:
    bars = _bars(
        SUBJECT_ID,
        40,
        base=Decimal("100"),
        increment=Decimal("0.13"),
    )
    subject = _listing(bars, provider_code="YAHOO", market="XIDX")
    rows, arrays = _calculated_rows(
        bars,
        subject=subject,
        benchmark_history=None,
    )

    validate_feature_rows(rows, calculation_arrays=arrays, subject=subject)


@pytest.mark.parametrize(
    ("replacement", "match"),
    [
        ({"history_observation_count": 2}, "history observation count"),
        ({"return_1d_pct": 0.5}, "return_1d_pct"),
        ({"rsi_14": 101.0}, "between 0 and 100"),
        ({"spx_correlation_60d": -1.1}, "between -1 and 1"),
        ({"atr_14": -0.1}, "non-negative"),
        ({"consecutive_up_days": 1}, "consecutive_up_days"),
        (
            {"relative_strength_benchmark_provider_listing_id": OTHER_ID},
            "benchmark lineage",
        ),
    ],
)
def test_rejects_invalid_row_state(supported_state, replacement, match) -> None:
    rows, arrays, subject, benchmark = supported_state
    changed = (replace(rows[0], **replacement), *rows[1:])

    with pytest.raises(TechIndicatorsValidationError, match=match):
        validate_feature_rows(
            changed,
            calculation_arrays=arrays,
            subject=subject,
            benchmark_history=benchmark,
        )


def test_rejects_copied_source_drift(supported_state) -> None:
    rows, arrays, subject, benchmark = supported_state
    drifted_source = replace(rows[5].source, volume=Decimal("999999"))
    changed = (*rows[:5], replace(rows[5], source=drifted_source), *rows[6:])

    with pytest.raises(TechIndicatorsValidationError, match="copied OHLCV"):
        validate_feature_rows(
            changed,
            calculation_arrays=arrays,
            subject=subject,
            benchmark_history=benchmark,
        )


def test_rejects_wrong_warmup_null_mask(supported_state) -> None:
    rows, arrays, subject, benchmark = supported_state
    changed = (replace(rows[0], return_1d_pct=0.0), *rows[1:])

    with pytest.raises(TechIndicatorsValidationError, match="return_1d_pct"):
        validate_feature_rows(
            changed,
            calculation_arrays=arrays,
            subject=subject,
            benchmark_history=benchmark,
        )


def test_generated_reference_detects_tolerance_amplification() -> None:
    close = Decimal("0.000000000001")
    bars = tuple(
        SourceBar(
            provider_listing_id=SUBJECT_ID,
            trading_date=date(2025, 1, 1) + timedelta(days=index),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=Decimal("1"),
        )
        for index in range(20)
    )
    subject = _listing(bars, provider_code="YAHOO", market="XIDX")
    rows, arrays = _calculated_rows(
        bars,
        subject=subject,
        benchmark_history=None,
    )
    changed = (*rows[:-1], replace(rows[-1], sma_20=rows[-1].sma_20 + 5e-13))

    with pytest.raises(TechIndicatorsValidationError, match="pct_sma_20"):
        validate_feature_rows(changed, calculation_arrays=arrays, subject=subject)


def test_rejects_incomplete_image_and_subject_coverage_drift(supported_state) -> None:
    rows, arrays, subject, benchmark = supported_state
    with pytest.raises(TechIndicatorsValidationError, match="row count"):
        validate_feature_rows(
            rows[:-1],
            calculation_arrays=arrays,
            subject=subject,
            benchmark_history=benchmark,
        )

    with pytest.raises(TechIndicatorsValidationError, match="observation count"):
        validate_feature_rows(
            rows,
            calculation_arrays=arrays,
            subject=replace(subject, source_observation_count=len(rows) - 1),
            benchmark_history=benchmark,
        )


def test_supported_subject_requires_benchmark_history(supported_state) -> None:
    rows, arrays, subject, _benchmark = supported_state
    with pytest.raises(TechIndicatorsValidationError, match="benchmark history"):
        validate_feature_rows(rows, calculation_arrays=arrays, subject=subject)
