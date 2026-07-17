from __future__ import annotations

import json
import os
from typing import Iterator
from uuid import uuid4

import pytest

from empire_core.db.connection import EmpireDatabase
from empire_stonks_ohlcv import (
    select_provider_market_health,
    select_provider_series_health,
    select_provider_weekday_gaps,
)
from empire_stonks_ohlcv import health


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
MARKETS = ("NYSE", "NASDAQ", "AMEX")
LISTINGS_PER_MARKET = 1_500
ACTIVE_PER_MARKET = 1_350
INACTIVE_PER_MARKET = 150
ACTIVE_BARS_PER_MARKET = 41_800
INACTIVE_BARS_PER_MARKET = 4_600
ACTIVE_GAPS = 150


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


def _market_rows(cursor: object) -> dict[str, object]:
    return {
        row.market: row
        for row in select_provider_market_health(
            cursor=cursor,
            provider_code="EODDATA",
        )
    }


def _count(value: object, attribute: str) -> int:
    return 0 if value is None else getattr(value, attribute)


def _plan_text(cursor: object, query: str, params: tuple[object, ...]) -> str:
    cursor.execute("SET LOCAL enable_seqscan = off")
    cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query, params)
    plan = cursor.fetchone()[0]
    cursor.execute("SET LOCAL enable_seqscan = on")
    return json.dumps(plan)


def test_eoddata_health_queries_and_existing_indexes_at_representative_volume(
    database_connection: object,
) -> None:
    connection = database_connection
    ticker_prefix = f"E67{uuid4().hex[:10].upper()}"

    with connection.cursor() as cursor:  # type: ignore[union-attr]
        baseline_markets = _market_rows(cursor)
        baseline_series_count = len(
            select_provider_series_health(
                cursor=cursor,
                provider_code="EODDATA",
            )
        )
        baseline_gap_count = select_provider_weekday_gaps(
            cursor=cursor,
            provider_code="EODDATA",
        ).total_count
        baseline_market_gaps = {
            market: select_provider_weekday_gaps(
                cursor=cursor,
                provider_code="EODDATA",
                market=market,
            ).total_count
            for market in MARKETS
        }

        cursor.execute(
            """
            INSERT INTO stonks.provider_listing (
                provider_code,
                market,
                ticker,
                first_seen,
                last_seen,
                status
            )
            SELECT
                'EODDATA',
                market,
                %s || lpad(series_number::text, 4, '0'),
                DATE '2026-01-02',
                DATE '2026-02-13',
                CASE
                    WHEN series_number %% 10 = 0 THEN 'INACTIVE'
                    ELSE 'ACTIVE'
                END
            FROM unnest(%s::text[]) AS market
            CROSS JOIN generate_series(1, %s) AS series_number
            """,
            (ticker_prefix, list(MARKETS), LISTINGS_PER_MARKET),
        )
        cursor.execute(
            """
            INSERT INTO stonks.ohlcv_daily (
                provider_listing_id,
                trading_date,
                open,
                high,
                low,
                close,
                volume,
                typ,
                hl_range,
                oc_range
            )
            SELECT
                listing.provider_listing_id,
                trading_day::date,
                10,
                12,
                9,
                11,
                100,
                10.66666667,
                3,
                1
            FROM stonks.provider_listing AS listing
            CROSS JOIN generate_series(
                DATE '2026-01-02',
                DATE '2026-02-13',
                interval '1 day'
            ) AS trading_day
            WHERE listing.provider_code = 'EODDATA'
              AND listing.ticker LIKE %s
              AND extract(isodow FROM trading_day) <= 5
              AND NOT (
                  trading_day::date = DATE '2026-01-14'
                  AND right(listing.ticker, 4)::integer %% 15 = 0
              )
            """,
            (ticker_prefix + "%",),
        )

        markets = _market_rows(cursor)
        series = select_provider_series_health(
            cursor=cursor,
            provider_code="EODDATA",
        )
        gaps = select_provider_weekday_gaps(
            cursor=cursor,
            provider_code="EODDATA",
        )
        market_gaps = {
            market: select_provider_weekday_gaps(
                cursor=cursor,
                provider_code="EODDATA",
                market=market,
            )
            for market in MARKETS
        }

        assert len(series) == baseline_series_count + 4_500
        inserted_series = [
            row for row in series if row.ticker.startswith(ticker_prefix)
        ]
        assert len(inserted_series) == 4_500
        assert sum(row.is_active for row in inserted_series) == 4_050
        assert sum(not row.is_active for row in inserted_series) == 450
        assert gaps.total_count == baseline_gap_count + ACTIVE_GAPS
        assert gaps.to_dict()["calendar_authoritative"] is False
        assert gaps.sample_count <= 100
        assert all(
            market_gaps[market].total_count
            == baseline_market_gaps[market] + 50
            for market in MARKETS
        )

        for market in MARKETS:
            current = markets[market]
            baseline = baseline_markets.get(market)
            assert (
                current.active_listing_count
                - _count(baseline, "active_listing_count")
                == ACTIVE_PER_MARKET
            )
            assert (
                current.inactive_listing_count
                - _count(baseline, "inactive_listing_count")
                == INACTIVE_PER_MARKET
            )
            assert (
                current.active_bar_count
                - _count(baseline, "active_bar_count")
                == ACTIVE_BARS_PER_MARKET
            )
            assert (
                current.inactive_bar_count
                - _count(baseline, "inactive_bar_count")
                == INACTIVE_BARS_PER_MARKET
            )

        series_plan = _plan_text(
            cursor,
            health._SERIES_HEALTH_SQL,
            ("EODDATA",),
        )
        gap_plan = _plan_text(
            cursor,
            health._WEEKDAY_GAPS_SQL,
            ("EODDATA", None, None, 100),
        )
        assert any(
            index_name in series_plan
            for index_name in (
                "provider_listing_pkey",
                "uq_provider_listing_identity",
            )
        )
        assert "pk_ohlcv_daily" in series_plan
        assert any(
            index_name in gap_plan
            for index_name in (
                "provider_listing_pkey",
                "uq_provider_listing_identity",
            )
        )
        assert "pk_ohlcv_daily" in gap_plan
