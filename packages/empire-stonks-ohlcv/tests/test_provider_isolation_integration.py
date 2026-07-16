from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Iterator

import pytest

from empire_core.db.connection import EmpireDatabase
from empire_stonks_ohlcv import (
    DailyBar,
    DailyBarWriteInput,
    ProviderListing,
    select_daily_bar_date_range,
    select_latest_trading_date,
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


def test_identical_native_series_remain_isolated_by_provider(
    database_connection: object,
) -> None:
    connection = database_connection
    trading_date = date(2026, 1, 7)
    listings = tuple(
        ProviderListing(
            provider_code=provider_code,
            market="M37_SHARED",
            ticker="SAME",
        )
        for provider_code in ("EODDATA", "STOOQ", "YAHOO")
    )
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        resolved = upsert_provider_listings(cursor=cursor, listings=listings)
        listing_ids = {
            listing.provider_code: resolved.provider_listing_id_for(listing)
            for listing in listings
        }
        assert len(set(listing_ids.values())) == 3

        first = upsert_daily_bars(
            cursor=cursor,
            bars=(
                DailyBarWriteInput(
                    listing_ids["EODDATA"],
                    _bar(trading_date, "10"),
                ),
                DailyBarWriteInput(
                    listing_ids["STOOQ"], _bar(trading_date, "20")),
                DailyBarWriteInput(
                    listing_ids["YAHOO"], _bar(trading_date, "30")),
            ),
        )
        corrected = upsert_daily_bars(
            cursor=cursor,
            bars=(
                DailyBarWriteInput(
                    listing_ids["EODDATA"],
                    _bar(trading_date, "11"),
                ),
            ),
        )

        assert first.to_dict() == {
            "inserted": 3,
            "updated": 0,
            "unchanged": 0,
            "derived_updated": 0,
        }
        assert corrected.to_dict() == {
            "inserted": 0,
            "updated": 1,
            "unchanged": 0,
            "derived_updated": 0,
        }

        cursor.execute(
            """
            SELECT listing.provider_code, daily.provider_listing_id, daily.close
            FROM stonks.ohlcv_daily AS daily
            JOIN stonks.provider_listing AS listing
              ON listing.provider_listing_id = daily.provider_listing_id
            WHERE listing.market = 'M37_SHARED'
              AND listing.ticker = 'SAME'
            ORDER BY listing.provider_code
            """
        )
        assert cursor.fetchall() == [
            ("EODDATA", listing_ids["EODDATA"], Decimal("11.0000000000")),
            ("STOOQ", listing_ids["STOOQ"], Decimal("20.0000000000")),
            ("YAHOO", listing_ids["YAHOO"], Decimal("30.0000000000")),
        ]

        for provider_code, provider_listing_id in listing_ids.items():
            assert select_latest_trading_date(
                cursor=cursor,
                provider_listing_id=provider_listing_id,
            ) == trading_date
            assert select_daily_bar_date_range(
                cursor=cursor,
                provider_listing_id=provider_listing_id,
            ).bar_count == 1
            coverage = select_provider_listing_coverage(
                cursor=cursor,
                provider_code=provider_code,
            )
            matching = [
                item
                for item in coverage
                if item.market == "M37_SHARED" and item.ticker == "SAME"
            ]
            assert [item.provider_listing_id for item in matching] == [
                provider_listing_id
            ]
