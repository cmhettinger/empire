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
    OHLCVPersistenceError,
    ProviderListing,
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


def _bar(
    trading_date: date,
    *,
    close: str,
    volume: str | None = None,
) -> DailyBar:
    close_value = Decimal(close)
    return DailyBar(
        trading_date=trading_date,
        open=close_value - Decimal("0.5"),
        high=close_value + Decimal("1"),
        low=close_value - Decimal("1"),
        close=close_value,
        volume=None if volume is None else Decimal(volume),
    )


def test_daily_bar_writer_round_trip_against_postgres(
    database_connection: object,
) -> None:
    connection = database_connection
    first_date = date(2026, 1, 2)
    middle_date = date(2026, 1, 5)
    last_date = date(2026, 1, 6)
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        listing = ProviderListing(
            provider_code="EODDATA",
            market="M35_NASDAQ",
            ticker="AAPL",
        )
        listing_id = upsert_provider_listings(
            cursor=cursor,
            listings=(listing,),
        ).provider_listing_id_for(listing)

        first = upsert_daily_bars(
            cursor=cursor,
            bars=(
                DailyBarWriteInput(listing_id, _bar(last_date, close="12")),
                DailyBarWriteInput(
                    listing_id,
                    _bar(first_date, close="10", volume="100.000000004"),
                ),
            ),
        )
        rerun = upsert_daily_bars(
            cursor=cursor,
            bars=(
                DailyBarWriteInput(
                    listing_id,
                    _bar(first_date, close="10", volume="100.000000004"),
                ),
                DailyBarWriteInput(listing_id, _bar(last_date, close="12")),
            ),
        )
        filled_gap = upsert_daily_bars(
            cursor=cursor,
            bars=(DailyBarWriteInput(listing_id, _bar(middle_date, close="11")),),
        )
        corrected = upsert_daily_bars(
            cursor=cursor,
            bars=(DailyBarWriteInput(listing_id, _bar(middle_date, close="10.5")),),
        )

        assert first.to_dict() == {
            "inserted": 2,
            "updated": 0,
            "unchanged": 0,
            "derived_updated": 0,
        }
        assert rerun.to_dict() == {
            "inserted": 0,
            "updated": 0,
            "unchanged": 2,
            "derived_updated": 0,
        }
        assert filled_gap.to_dict() == {
            "inserted": 1,
            "updated": 0,
            "unchanged": 0,
            "derived_updated": 1,
        }
        assert corrected.to_dict() == {
            "inserted": 0,
            "updated": 1,
            "unchanged": 0,
            "derived_updated": 1,
        }

        cursor.execute(
            """
            SELECT
                trading_date,
                close,
                volume,
                change,
                changepct,
                typ,
                hl_range,
                oc_range
            FROM stonks.ohlcv_daily
            WHERE provider_listing_id = %s
            ORDER BY trading_date
            """,
            (listing_id,),
        )
        assert cursor.fetchall() == [
            (
                first_date,
                Decimal("10.0000000000"),
                Decimal("100.00000000"),
                None,
                None,
                Decimal("10.00000000"),
                Decimal("2.00000000"),
                Decimal("0.50000000"),
            ),
            (
                middle_date,
                Decimal("10.5000000000"),
                None,
                Decimal("0.50000000"),
                Decimal("0.05000000"),
                Decimal("10.50000000"),
                Decimal("2.00000000"),
                Decimal("0.50000000"),
            ),
            (
                last_date,
                Decimal("12.0000000000"),
                None,
                Decimal("1.50000000"),
                Decimal("0.14285714"),
                Decimal("12.00000000"),
                Decimal("2.00000000"),
                Decimal("0.50000000"),
            ),
        ]
        cursor.execute(
            """
            SELECT first_seen, last_seen
            FROM stonks.provider_listing
            WHERE provider_listing_id = %s
            """,
            (listing_id,),
        )
        assert cursor.fetchone() == (first_date, last_date)


def test_daily_bar_writer_rejects_duplicate_and_missing_listing(
    database_connection: object,
) -> None:
    connection = database_connection
    bar = _bar(date(2026, 1, 2), close="10")
    missing_listing_id = uuid4()
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        with pytest.raises(OHLCVPersistenceError, match="Duplicate daily-bar"):
            upsert_daily_bars(
                cursor=cursor,
                bars=(
                    DailyBarWriteInput(missing_listing_id, bar),
                    DailyBarWriteInput(missing_listing_id, bar),
                ),
            )
        with pytest.raises(OHLCVPersistenceError, match="does not exist"):
            upsert_daily_bars(
                cursor=cursor,
                bars=(DailyBarWriteInput(missing_listing_id, bar),),
            )
