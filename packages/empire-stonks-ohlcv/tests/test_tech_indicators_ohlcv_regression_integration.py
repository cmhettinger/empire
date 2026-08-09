from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Any, Iterator, Literal
from uuid import UUID, uuid4

import pytest

from empire_core.db.connection import EmpireDatabase
from empire_stonks_ohlcv import (
    DailyBar,
    DailyBarWriteInput,
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
PayloadSlot = Literal["a", "b"]
PAYLOAD_TABLES = {
    "a": "ohlcv_daily_tech_indicators_a",
    "b": "ohlcv_daily_tech_indicators_b",
}


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
        volume=Decimal("100"),
    )


def _insert_payload(
    cursor: Any,
    *,
    slot: PayloadSlot,
    provider_listing_id: UUID,
    trading_date: date,
) -> None:
    table_name = PAYLOAD_TABLES[slot]
    cursor.execute(
        f"""
        INSERT INTO stonks.{table_name} (
            provider_listing_id,
            trading_date,
            history_observation_count,
            calculation_version,
            calculated_at,
            open,
            high,
            low,
            close,
            volume,
            consecutive_up_days,
            consecutive_down_days
        )
        SELECT
            provider_listing_id,
            trading_date,
            1,
            'TECH_INDICATORS_V1',
            TIMESTAMPTZ '2026-02-01 00:00:00+00',
            open,
            high,
            low,
            close,
            volume,
            0,
            0
        FROM stonks.ohlcv_daily
        WHERE provider_listing_id = %s
          AND trading_date = %s
        """,
        (provider_listing_id, trading_date),
    )
    assert cursor.rowcount == 1


def _payload_rows(cursor: Any, provider_listing_id: UUID) -> list[tuple[Any, ...]]:
    cursor.execute(
        """
        SELECT 'a', trading_date, close
        FROM stonks.ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id = %s
        UNION ALL
        SELECT 'b', trading_date, close
        FROM stonks.ohlcv_daily_tech_indicators_b
        WHERE provider_listing_id = %s
        ORDER BY 1, 2
        """,
        (provider_listing_id, provider_listing_id),
    )
    return cursor.fetchall()


def test_existing_writers_preserve_provider_identity_and_isolation(
    database_connection: object,
) -> None:
    connection = database_connection
    marker = uuid4().hex[:10].upper()
    market = f"S27_{marker}"
    first_date = date(2026, 1, 2)
    middle_date = date(2026, 1, 5)
    last_date = date(2026, 1, 6)
    listings = (
        ProviderListing("EODDATA", market, "SAME"),
        ProviderListing("EODDATA", market, "same"),
        ProviderListing("STOOQ", market, "SAME"),
        ProviderListing(
            "YAHOO",
            market,
            "SAME",
            metadata={"YahooTicker": f"S27{marker}"},
        ),
    )

    with connection.cursor() as cursor:  # type: ignore[union-attr]
        resolved = upsert_provider_listings(cursor=cursor, listings=listings)
        listing_ids = {
            (listing.provider_code, listing.ticker): resolved.provider_listing_id_for(
                listing
            )
            for listing in listings
        }
        assert resolved.counts.inserted == 4
        assert len(set(listing_ids.values())) == 4
        cursor.execute(
            """
            SELECT provider_code, ticker, provider_listing_id
            FROM stonks.provider_listing
            WHERE market = %s
            ORDER BY provider_code, ticker
            """,
            (market,),
        )
        assert set(cursor.fetchall()) == {
            ("EODDATA", "SAME", listing_ids[("EODDATA", "SAME")]),
            ("EODDATA", "same", listing_ids[("EODDATA", "same")]),
            ("STOOQ", "SAME", listing_ids[("STOOQ", "SAME")]),
            ("YAHOO", "SAME", listing_ids[("YAHOO", "SAME")]),
        }

        bars = tuple(
            DailyBarWriteInput(
                listing_ids[(provider_code, "SAME")],
                _bar(trading_date, close),
            )
            for provider_code, first_close, last_close in (
                ("EODDATA", "10", "12"),
                ("STOOQ", "20", "22"),
                ("YAHOO", "30", "32"),
            )
            for trading_date, close in (
                (first_date, first_close),
                (last_date, last_close),
            )
        )
        assert upsert_daily_bars(cursor=cursor, bars=bars).to_dict() == {
            "inserted": 6,
            "updated": 0,
            "unchanged": 0,
            "derived_updated": 0,
        }

        for provider_code in ("EODDATA", "STOOQ", "YAHOO"):
            provider_listing_id = listing_ids[(provider_code, "SAME")]
            _insert_payload(
                cursor,
                slot="a",
                provider_listing_id=provider_listing_id,
                trading_date=first_date,
            )
            _insert_payload(
                cursor,
                slot="b",
                provider_listing_id=provider_listing_id,
                trading_date=last_date,
            )

        eoddata_listing_id = listing_ids[("EODDATA", "SAME")]
        correction = upsert_daily_bars(
            cursor=cursor,
            bars=(
                DailyBarWriteInput(
                    eoddata_listing_id,
                    _bar(first_date, "11"),
                ),
            ),
        )
        assert correction.to_dict() == {
            "inserted": 0,
            "updated": 1,
            "unchanged": 0,
            "derived_updated": 1,
        }

        gap_insert = upsert_daily_bars(
            cursor=cursor,
            bars=(
                DailyBarWriteInput(
                    eoddata_listing_id,
                    _bar(middle_date, "11.5"),
                ),
            ),
        )
        assert gap_insert.to_dict() == {
            "inserted": 1,
            "updated": 0,
            "unchanged": 0,
            "derived_updated": 1,
        }
        unchanged = upsert_daily_bars(
            cursor=cursor,
            bars=(
                DailyBarWriteInput(
                    eoddata_listing_id,
                    _bar(middle_date, "11.5"),
                ),
            ),
        )
        assert unchanged.to_dict() == {
            "inserted": 0,
            "updated": 0,
            "unchanged": 1,
            "derived_updated": 0,
        }

        listing_update = ProviderListing(
            "EODDATA",
            market,
            "SAME",
            name="S2.7 updated name",
        )
        listing_update_result = upsert_provider_listings(
            cursor=cursor,
            listings=(listing_update,),
        )
        assert listing_update_result.counts.updated == 1
        assert (
            listing_update_result.provider_listing_id_for(listing_update)
            == eoddata_listing_id
        )

        cursor.execute(
            """
            SELECT
                listing.provider_code,
                daily.trading_date,
                daily.close,
                daily.change
            FROM stonks.provider_listing AS listing
            JOIN stonks.ohlcv_daily AS daily USING (provider_listing_id)
            WHERE listing.market = %s
              AND listing.ticker = 'SAME'
            ORDER BY listing.provider_code, daily.trading_date
            """,
            (market,),
        )
        assert cursor.fetchall() == [
            ("EODDATA", first_date, Decimal("11.0000000000"), None),
            (
                "EODDATA",
                middle_date,
                Decimal("11.5000000000"),
                Decimal("0.50000000"),
            ),
            (
                "EODDATA",
                last_date,
                Decimal("12.0000000000"),
                Decimal("0.50000000"),
            ),
            ("STOOQ", first_date, Decimal("20.0000000000"), None),
            (
                "STOOQ",
                last_date,
                Decimal("22.0000000000"),
                Decimal("2.00000000"),
            ),
            ("YAHOO", first_date, Decimal("30.0000000000"), None),
            (
                "YAHOO",
                last_date,
                Decimal("32.0000000000"),
                Decimal("2.00000000"),
            ),
        ]

        assert _payload_rows(cursor, eoddata_listing_id) == [
            ("a", first_date, Decimal("10.0000000000")),
            ("b", last_date, Decimal("12.0000000000")),
        ]
        for provider_code, expected_first, expected_last in (
            ("STOOQ", "20.0000000000", "22.0000000000"),
            ("YAHOO", "30.0000000000", "32.0000000000"),
        ):
            assert _payload_rows(
                cursor,
                listing_ids[(provider_code, "SAME")],
            ) == [
                ("a", first_date, Decimal(expected_first)),
                ("b", last_date, Decimal(expected_last)),
            ]


def test_source_cleanup_cascades_only_owned_technical_rows(
    database_connection: object,
) -> None:
    connection = database_connection
    marker = uuid4().hex[:10].upper()
    first_date = date(2026, 1, 2)
    last_date = date(2026, 1, 5)
    target = ProviderListing("STOOQ", f"S27_CLEAN_{marker}", "TARGET")
    survivor = ProviderListing("EODDATA", f"S27_CLEAN_{marker}", "SURVIVOR")

    with connection.cursor() as cursor:  # type: ignore[union-attr]
        resolved = upsert_provider_listings(
            cursor=cursor,
            listings=(target, survivor),
        )
        target_id = resolved.provider_listing_id_for(target)
        survivor_id = resolved.provider_listing_id_for(survivor)
        bars = tuple(
            DailyBarWriteInput(listing_id, _bar(trading_date, close))
            for listing_id, first_close, last_close in (
                (target_id, "40", "42"),
                (survivor_id, "50", "52"),
            )
            for trading_date, close in (
                (first_date, first_close),
                (last_date, last_close),
            )
        )
        assert upsert_daily_bars(cursor=cursor, bars=bars).inserted == 4

        for listing_id in (target_id, survivor_id):
            for slot in ("a", "b"):
                for trading_date in (first_date, last_date):
                    _insert_payload(
                        cursor,
                        slot=slot,
                        provider_listing_id=listing_id,
                        trading_date=trading_date,
                    )

        cursor.execute(
            """
            DELETE FROM stonks.ohlcv_daily
            WHERE provider_listing_id = %s
              AND trading_date = %s
            """,
            (target_id, first_date),
        )
        assert cursor.rowcount == 1
        assert _payload_rows(cursor, target_id) == [
            ("a", last_date, Decimal("42.0000000000")),
            ("b", last_date, Decimal("42.0000000000")),
        ]
        assert len(_payload_rows(cursor, survivor_id)) == 4

        cursor.execute(
            """
            DELETE FROM stonks.provider_listing
            WHERE provider_listing_id = %s
            """,
            (target_id,),
        )
        assert cursor.rowcount == 1
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM stonks.ohlcv_daily
                 WHERE provider_listing_id = %s),
                (SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators_a
                 WHERE provider_listing_id = %s),
                (SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators_b
                 WHERE provider_listing_id = %s),
                (SELECT count(*) FROM stonks.ohlcv_daily
                 WHERE provider_listing_id = %s)
            """,
            (target_id, target_id, target_id, survivor_id),
        )
        assert cursor.fetchone() == (0, 0, 0, 2)
        assert len(_payload_rows(cursor, survivor_id)) == 4
