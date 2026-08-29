from __future__ import annotations

import os
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from math import isfinite
from typing import Iterator
from uuid import UUID, uuid4

import pytest

from empire_stonks_tech_indicators import (
    BenchmarkHistory,
    EligibleListing,
    ResolvedBenchmark,
    SourceBar,
    TechIndicatorsPayloadSlot,
    assemble_feature_rows,
    normalize_source_bars,
    upsert_feature_rows,
)
from empire_stonks_tech_indicators.models import (
    PYTHON_FEATURE_FIELDS,
    FeatureRow,
)


EmpireDatabase = pytest.importorskip(
    "empire_core.db.connection",
    reason="Empire Core database runtime is not installed.",
).EmpireDatabase

DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
GENERATED_FEATURE_FIELDS = (
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
)
AUDITED_COLUMNS = (
    "provider_listing_id",
    "trading_date",
    "relative_strength_benchmark_provider_listing_id",
    "history_observation_count",
    "calculation_version",
    "open",
    "high",
    "low",
    "close",
    "volume",
    *PYTHON_FEATURE_FIELDS,
    *GENERATED_FEATURE_FIELDS,
)
ABSOLUTE_TOLERANCE = 1e-12
RELATIVE_TOLERANCE = 1e-10


@pytest.fixture
def database_connection() -> Iterator[object]:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")
    connection = EmpireDatabase.connect_from_env()
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _bars(
    listing_id: UUID,
    *,
    count: int,
    base: Decimal,
    step: Decimal,
    gap_every: int,
    nullable_volume: bool = False,
) -> tuple[SourceBar, ...]:
    current_date = date(2024, 1, 2)
    result: list[SourceBar] = []
    for index in range(count):
        if index:
            current_date += timedelta(
                days=3 if index % gap_every == 0 else 1
            )
        close = (
            base
            + step * index
            + Decimal(index % 13 - 6) / Decimal("100")
        )
        volume = (
            None
            if nullable_volume and index % 7 == 0
            else Decimal(10_000 + index * 17)
        )
        result.append(
            SourceBar(
                provider_listing_id=listing_id,
                trading_date=current_date,
                open=close - Decimal("0.25"),
                high=close + Decimal("1.50"),
                low=close - Decimal("1.25"),
                close=close,
                volume=volume,
            )
        )
    return tuple(result)


def _insert_listing(
    cursor: object,
    *,
    provider_code: str,
    market: str,
    ticker: str,
    instrument_type_code: str,
) -> UUID:
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.provider_listing (
            provider_code, market, ticker, instrument_type_code, status,
            metadata
        )
        VALUES (%s, %s, %s, %s, 'ACTIVE', %s::jsonb)
        RETURNING provider_listing_id
        """,
        (
            provider_code,
            market,
            ticker,
            instrument_type_code,
            json.dumps(
                {"YahooTicker": f"^{ticker}"}
                if provider_code == "YAHOO"
                else {"type": "Equity"}
            ),
        ),
    )
    return cursor.fetchone()[0]  # type: ignore[union-attr,no-any-return]


def _insert_source_bars(cursor: object, bars: tuple[SourceBar, ...]) -> None:
    cursor.executemany(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.ohlcv_daily (
            provider_listing_id, trading_date, open, high, low, close,
            volume, change, changepct, typ, hl_range, oc_range
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, NULL, NULL,
            round((%s + %s + %s) / 3, 8),
            round(%s - %s, 8),
            round(%s - %s, 8)
        )
        """,
        (
            (
                bar.provider_listing_id,
                bar.trading_date,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.high,
                bar.low,
                bar.close,
                bar.high,
                bar.low,
                bar.close,
                bar.open,
            )
            for bar in bars
        ),
    )


def _listing(
    bars: tuple[SourceBar, ...],
    *,
    provider_code: str,
    market: str,
    ticker: str,
    instrument_type_code: str,
) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=bars[0].provider_listing_id,
        provider_code=provider_code,
        market=market,
        ticker=ticker,
        instrument_type_code=instrument_type_code,
        status="ACTIVE",
        first_trading_date=bars[0].trading_date,
        last_trading_date=bars[-1].trading_date,
        source_observation_count=len(bars),
    )


def _assemble(
    bars: tuple[SourceBar, ...],
    *,
    listing: EligibleListing,
    benchmark: BenchmarkHistory | None,
    run_id: UUID,
    calculated_at: datetime,
) -> tuple[FeatureRow, ...]:
    return assemble_feature_rows(
        normalize_source_bars(bars),
        subject=listing,
        benchmark_history=benchmark,
        run_id=run_id,
        calculated_at=calculated_at,
    )


def _divide(
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    if numerator is None or denominator is None or denominator == 0.0:
        return None
    result = numerator / denominator
    assert isfinite(result)
    return result


def _distance(
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    result = _divide(numerator, denominator)
    return None if result is None else result - 1.0


def _generated_expectations(row: FeatureRow) -> dict[str, float | None]:
    def value(name: str) -> float | None:
        return getattr(row, name)

    close = float(row.source.close)
    high = float(row.source.high)
    low = float(row.source.low)
    open_value = float(row.source.open)
    volume = None if row.source.volume is None else float(row.source.volume)
    sma_20 = value("sma_20")
    stddev = value("price_stddev_20")
    upper = None if sma_20 is None or stddev is None else sma_20 + 2 * stddev
    lower = None if sma_20 is None or stddev is None else sma_20 - 2 * stddev
    result = {
        "dollar_volume": None if volume is None else abs(close) * volume,
        "intraday_return_1d_pct": _distance(close, open_value),
        "daily_range_pct": _divide(high - low, abs(close)),
        "close_location_1d": _divide(close - low, high - low),
        "pct_sma_20": _distance(close, sma_20),
        "pct_sma_50": _distance(close, value("sma_50")),
        "pct_sma_200": _distance(close, value("sma_200")),
        "pct_ema_20": _distance(close, value("ema_20")),
        "pct_ema_50": _distance(close, value("ema_50")),
        "pct_sma_20_vs_50": _distance(sma_20, value("sma_50")),
        "pct_sma_20_vs_200": _distance(sma_20, value("sma_200")),
        "pct_sma_50_vs_200": _distance(
            value("sma_50"), value("sma_200")
        ),
        "pct_hh_20": _distance(close, value("hh_20")),
        "pct_hh_50": _distance(close, value("hh_50")),
        "pct_hh_252": _distance(close, value("hh_252")),
        "pct_ll_20": _distance(close, value("ll_20")),
        "pct_ll_50": _distance(close, value("ll_50")),
        "atr_pct_14": _divide(value("atr_14"), abs(close)),
        "bollinger_percent_b_20_2": _divide(
            None if lower is None else close - lower,
            None if upper is None or lower is None else upper - lower,
        ),
        "bollinger_bandwidth_20_2": _divide(
            None if upper is None or lower is None else upper - lower,
            None if sma_20 is None else abs(sma_20),
        ),
        "volume_ratio_20": _divide(volume, value("volume_avg_20")),
        "macd_12_26_pct": _divide(
            value("macd_12_26"),
            None if value("ema_26") is None else abs(value("ema_26")),
        ),
        "macd_histogram_12_26_9_pct": _divide(
            value("macd_histogram_12_26_9"), abs(close)
        ),
    }
    assert tuple(result) == GENERATED_FEATURE_FIELDS
    return result


def _expected_values(row: FeatureRow) -> dict[str, object]:
    result: dict[str, object] = {
        "provider_listing_id": row.source.provider_listing_id,
        "trading_date": row.source.trading_date,
        "relative_strength_benchmark_provider_listing_id": (
            row.relative_strength_benchmark_provider_listing_id
        ),
        "history_observation_count": row.history_observation_count,
        "calculation_version": row.calculation_version,
        "open": row.source.open,
        "high": row.source.high,
        "low": row.source.low,
        "close": row.source.close,
        "volume": row.source.volume,
    }
    result.update(
        {field_name: getattr(row, field_name) for field_name in PYTHON_FEATURE_FIELDS}
    )
    result.update(_generated_expectations(row))
    assert tuple(result) == AUDITED_COLUMNS
    return result


def _stored_values(
    cursor: object,
    listing_ids: tuple[UUID, ...],
) -> dict[tuple[UUID, date], dict[str, object]]:
    cursor.execute(  # type: ignore[union-attr]
        f"""
        SELECT {", ".join(AUDITED_COLUMNS)}
        FROM stonks.ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id = ANY(%s::uuid[])
        ORDER BY provider_listing_id, trading_date
        """,
        (list(listing_ids),),
    )
    return {
        (values[0], values[1]): dict(zip(AUDITED_COLUMNS, values, strict=True))
        for values in cursor.fetchall()  # type: ignore[union-attr]
    }


def _assert_stored_matches_fresh(
    stored: dict[tuple[UUID, date], dict[str, object]],
    fresh: tuple[FeatureRow, ...],
) -> None:
    assert len(stored) == len(fresh)
    for row in fresh:
        key = (row.source.provider_listing_id, row.source.trading_date)
        actual = stored[key]
        for field_name, expected in _expected_values(row).items():
            if type(expected) is float:
                assert actual[field_name] == pytest.approx(
                    expected,
                    rel=RELATIVE_TOLERANCE,
                    abs=ABSOLUTE_TOLERANCE,
                ), (key, field_name)
            else:
                assert actual[field_name] == expected, (key, field_name)


def test_stored_features_match_fresh_calculation_across_provider_shapes(
    database_connection: object,
) -> None:
    cursor = database_connection.cursor()  # type: ignore[union-attr]
    marker = uuid4().hex[:12].upper()
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO core.core_run (
            domain, job_name, subject_key, run_type, status, runner
        ) VALUES (
            'stonks', 'stonks_tech_indicators_backfill', %s,
            'manual', 'started', 'pytest.v12.5'
        ) RETURNING run_id
        """,
        (f"v12.5:{marker}",),
    )
    run_id = cursor.fetchone()[0]  # type: ignore[union-attr]

    definitions = (
        (
            "EODDATA", "NASDAQ", f"V125E{marker}", "UNKNOWN", 280,
            "100", "0.17", 17, False,
        ),
        (
            "STOOQ", "nasdaq", f"v125s{marker}.us", "UNKNOWN", 280,
            "70", "0.11", 23, False,
        ),
        ("YAHOO", "XIDX", f"V125Y{marker}", "EQUITY_INDEX", 10, "900", "0.31", 5, True),
        (
            "YAHOO", "XIDX", f"V125B{marker}", "EQUITY_INDEX", 280,
            "4200", "0.41", 19, True,
        ),
    )
    listing_ids: list[UUID] = []
    bars_by_listing: dict[UUID, tuple[SourceBar, ...]] = {}
    listings: dict[UUID, EligibleListing] = {}
    for (
        provider_code,
        market,
        ticker,
        instrument_type_code,
        count,
        base,
        step,
        gap_every,
        nullable_volume,
    ) in definitions:
        listing_id = _insert_listing(
            cursor,
            provider_code=provider_code,
            market=market,
            ticker=ticker,
            instrument_type_code=instrument_type_code,
        )
        bars = _bars(
            listing_id,
            count=count,
            base=Decimal(base),
            step=Decimal(step),
            gap_every=gap_every,
            nullable_volume=nullable_volume,
        )
        _insert_source_bars(cursor, bars)
        listing_ids.append(listing_id)
        bars_by_listing[listing_id] = bars
        listings[listing_id] = _listing(
            bars,
            provider_code=provider_code,
            market=market,
            ticker=ticker,
            instrument_type_code=instrument_type_code,
        )

    eoddata_id, stooq_id, yahoo_id, benchmark_id = listing_ids
    benchmark = BenchmarkHistory(
        benchmark=ResolvedBenchmark(provider_listing_id=benchmark_id),
        bars=bars_by_listing[benchmark_id],
    )
    calculated_at = datetime.now(UTC)
    fresh_by_listing = {
        listing_id: _assemble(
            bars_by_listing[listing_id],
            listing=listings[listing_id],
            benchmark=(
                benchmark if listing_id in (eoddata_id, stooq_id) else None
            ),
            run_id=run_id,
            calculated_at=calculated_at,
        )
        for listing_id in listing_ids
    }
    fresh = tuple(
        row for listing_id in listing_ids for row in fresh_by_listing[listing_id]
    )
    counts = upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=fresh,
    )
    assert counts.inserted_rows == 850
    stored_before = _stored_values(cursor, tuple(listing_ids))
    _assert_stored_matches_fresh(stored_before, fresh)

    aligned_spx = [
        row.rel_spx
        for row in fresh_by_listing[eoddata_id][252:]
    ]
    assert any(value is None for value in aligned_spx)
    assert any(value is not None for value in aligned_spx)
    assert all(
        row.sma_20 is None
        and row.relative_strength_benchmark_provider_listing_id is None
        for row in fresh_by_listing[yahoo_id]
    )

    corrected_bars = list(bars_by_listing[stooq_id])
    correction_index = 137
    original = corrected_bars[correction_index]
    corrected = SourceBar(
        provider_listing_id=original.provider_listing_id,
        trading_date=original.trading_date,
        open=original.open + Decimal("5"),
        high=original.high + Decimal("5"),
        low=original.low + Decimal("5"),
        close=original.close + Decimal("5"),
        volume=original.volume,
    )
    corrected_bars[correction_index] = corrected
    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.ohlcv_daily
        SET open = %s, high = %s, low = %s, close = %s,
            typ = round((%s + %s + %s) / 3, 8),
            hl_range = round(%s - %s, 8),
            oc_range = round(%s - %s, 8), updated_at = now()
        WHERE provider_listing_id = %s AND trading_date = %s
        """,
        (
            corrected.open,
            corrected.high,
            corrected.low,
            corrected.close,
            corrected.high,
            corrected.low,
            corrected.close,
            corrected.high,
            corrected.low,
            corrected.close,
            corrected.open,
            stooq_id,
            corrected.trading_date,
        ),
    )
    corrected_fresh = _assemble(
        tuple(corrected_bars),
        listing=listings[stooq_id],
        benchmark=benchmark,
        run_id=run_id,
        calculated_at=calculated_at + timedelta(hours=1),
    )
    correction_counts = upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=corrected_fresh,
    )
    assert correction_counts.updated_rows > 0
    assert correction_counts.unchanged_rows > 0
    assert correction_counts.total_rows == len(corrected_fresh)

    stored_after = _stored_values(cursor, tuple(listing_ids))
    corrected_all = tuple(
        row
        for listing_id in listing_ids
        for row in (
            corrected_fresh
            if listing_id == stooq_id
            else fresh_by_listing[listing_id]
        )
    )
    _assert_stored_matches_fresh(stored_after, corrected_all)
    for listing_id in (eoddata_id, yahoo_id, benchmark_id):
        assert {
            key: value
            for key, value in stored_before.items()
            if key[0] == listing_id
        } == {
            key: value
            for key, value in stored_after.items()
            if key[0] == listing_id
        }
