from __future__ import annotations

import os
from typing import Iterator

import pytest

from empire_core.db.connection import EmpireDatabase

from empire_stonks_ohlcv import ProviderListing, upsert_provider_listings


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


def test_provider_listing_writer_round_trip_against_postgres(
    database_connection: object,
) -> None:
    connection = database_connection
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        cursor.execute(
            """
            SELECT type_code
            FROM stonks.instrument_type
            WHERE type_code <> 'UNKNOWN'
              AND is_active
            ORDER BY type_code
            LIMIT 1
            """
        )
        known_instrument_type = cursor.fetchone()[0]

        first_inputs = (
            ProviderListing(
                provider_code="STOOQ",
                market="M34_US",
                ticker="AAPL",
            ),
            ProviderListing(
                provider_code="EODDATA",
                market="M34_NASDAQ",
                ticker="AAPL",
                name="Apple",
            ),
            ProviderListing(
                provider_code="EODDATA",
                market="M34_NASDAQ",
                ticker="aapl",
            ),
        )
        first = upsert_provider_listings(cursor=cursor, listings=first_inputs)
        rerun = upsert_provider_listings(cursor=cursor, listings=first_inputs)
        corrected = upsert_provider_listings(
            cursor=cursor,
            listings=(
                ProviderListing(
                    provider_code="EODDATA",
                    market="M34_NASDAQ",
                    ticker="AAPL",
                    name="Apple Inc.",
                    instrument_type_code=known_instrument_type,
                ),
            ),
        )

        assert first.counts.to_dict() == {
            "inserted": 3,
            "updated": 0,
            "unchanged": 0,
            "derived_updated": 0,
        }
        assert rerun.counts.to_dict() == {
            "inserted": 0,
            "updated": 0,
            "unchanged": 3,
            "derived_updated": 0,
        }
        assert corrected.counts.to_dict() == {
            "inserted": 0,
            "updated": 1,
            "unchanged": 0,
            "derived_updated": 0,
        }

        cursor.execute(
            """
            SELECT name, instrument_type_code, first_seen, last_seen
            FROM stonks.provider_listing
            WHERE provider_code = 'EODDATA'
              AND market = 'M34_NASDAQ'
              AND ticker = 'AAPL'
            """
        )
        stored = cursor.fetchone()
        assert stored == ("Apple Inc.", known_instrument_type, None, None)

        cursor.execute(
            """
            SELECT count(*)
            FROM stonks.provider_listing
            WHERE (provider_code, market, ticker) IN (
                ('STOOQ', 'M34_US', 'AAPL'),
                ('EODDATA', 'M34_NASDAQ', 'AAPL'),
                ('EODDATA', 'M34_NASDAQ', 'aapl')
            )
            """
        )
        assert cursor.fetchone()[0] == 3
