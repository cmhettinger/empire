from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Iterator
from uuid import uuid4

import pytest

from empire_core.db.connection import EmpireDatabase
from empire_stonks_ohlcv import (
    DailyBar,
    DailyBarWriteInput,
    ProviderListing,
    select_daily_bar_date_range,
    select_latest_trading_date,
    select_provider_latest_trading_date,
    select_provider_listing_coverage,
    upsert_daily_bars,
    upsert_provider_listings,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)


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


def _bar(trading_date: date, close: str) -> DailyBar:
    close_value = Decimal(close)
    return DailyBar(
        trading_date=trading_date,
        open=close_value - Decimal("0.5"),
        high=close_value + Decimal("1"),
        low=close_value - Decimal("1"),
        close=close_value,
    )


def test_query_helpers_return_ordered_coverage_and_empty_states(
    database_connection: object,
) -> None:
    connection = database_connection
    provider_code = "TEST_M36"
    empty_provider_code = "TEST_M36_NONE"
    first_date = date(2026, 1, 2)
    last_date = date(2026, 1, 5)
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        cursor.execute(
            """
            INSERT INTO stonks.provider (
                provider_code,
                provider_name,
                provider_type,
                description
            )
            VALUES (%s, 'OHLCV query test', 'TEST', 'Rollback-only test row')
            """,
            (provider_code,),
        )
        empty = ProviderListing(provider_code, "M36_EMPTY", "EMPTY")
        nasdaq = ProviderListing(provider_code, "M36_NASDAQ", "AAPL")
        nyse = ProviderListing(provider_code, "M36_NYSE", "MSFT")
        resolved = upsert_provider_listings(
            cursor=cursor,
            listings=(nyse, empty, nasdaq),
        )
        nasdaq_id = resolved.provider_listing_id_for(nasdaq)
        nyse_id = resolved.provider_listing_id_for(nyse)
        upsert_daily_bars(
            cursor=cursor,
            bars=(
                DailyBarWriteInput(nasdaq_id, _bar(last_date, "12")),
                DailyBarWriteInput(nasdaq_id, _bar(first_date, "10")),
                DailyBarWriteInput(nyse_id, _bar(date(2026, 1, 3), "20")),
            ),
        )

        assert select_latest_trading_date(
            cursor=cursor,
            provider_listing_id=nasdaq_id,
        ) == last_date
        assert select_latest_trading_date(
            cursor=cursor,
            provider_listing_id=uuid4(),
        ) is None
        assert select_daily_bar_date_range(
            cursor=cursor,
            provider_listing_id=nasdaq_id,
        ).to_dict() == {
            "provider_listing_id": str(nasdaq_id),
            "first_trading_date": "2026-01-02",
            "last_trading_date": "2026-01-05",
            "bar_count": 2,
        }
        assert select_daily_bar_date_range(
            cursor=cursor,
            provider_listing_id=uuid4(),
        ) is None
        assert select_provider_latest_trading_date(
            cursor=cursor,
            provider_code=provider_code,
        ) == last_date
        assert select_provider_latest_trading_date(
            cursor=cursor,
            provider_code=empty_provider_code,
        ) is None

        coverage = select_provider_listing_coverage(
            cursor=cursor,
            provider_code=provider_code,
        )
        assert [
            (item.market, item.ticker, item.bar_count) for item in coverage
        ] == [
            ("M36_EMPTY", "EMPTY", 0),
            ("M36_NASDAQ", "AAPL", 2),
            ("M36_NYSE", "MSFT", 1),
        ]
        assert coverage[0].first_seen is None
        assert coverage[0].last_seen is None
        assert coverage[0].first_trading_date is None
        assert coverage[0].last_trading_date is None
        assert coverage[1].first_seen == first_date
        assert coverage[1].last_seen == last_date
        assert coverage[1].first_trading_date == first_date
        assert coverage[1].last_trading_date == last_date
        assert select_provider_listing_coverage(
            cursor=cursor,
            provider_code=empty_provider_code,
        ) == ()
