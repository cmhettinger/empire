from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from typing import Iterator
from uuid import uuid4

import pytest

from empire_core import EmpireDatabase
from empire_stonks_ohlcv import OHLCVConfigError, plan_yahoo_daily_completeness


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


def _insert_bar(cursor: object, listing_id: object, trading_date: date) -> None:
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.ohlcv_daily (
            provider_listing_id,
            trading_date,
            open,
            high,
            low,
            close,
            volume,
            change,
            changepct,
            typ,
            hl_range,
            oc_range
        )
        VALUES (%s, %s, 10, 12, 9, 11, 100, NULL, NULL,
                10.66666667, 3, 1)
        """,
        (listing_id, trading_date),
    )


def test_database_plan_is_noop_after_completion_and_missing_is_retryable(
    database_connection: object,
) -> None:
    connection = database_connection
    ticker = f"Y810{uuid4().hex[:8].upper()}"
    yahoo_ticker = f"^{ticker}"
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        cursor.execute(
            """
            INSERT INTO stonks.provider_listing (
                provider_code,
                market,
                ticker,
                name,
                instrument_type_code,
                status,
                metadata,
                session_policy_code
            )
            VALUES ('YAHOO', 'XIDX', %s, %s, 'EQUITY_INDEX', 'ACTIVE',
                    %s::jsonb, 'YH_XNYS_CLOSE_90M')
            RETURNING provider_listing_id
            """,
            (
                ticker,
                f"{ticker} Completeness Test",
                json.dumps({"YahooTicker": yahoo_ticker}),
            ),
        )
        listing_id = cursor.fetchone()[0]
        _insert_bar(cursor, listing_id, date(2026, 7, 1))

        arguments = {
            "cursor": cursor,
            "start_date": date(2026, 7, 1),
            "end_date": date(2026, 7, 2),
            "now": datetime(2026, 7, 3, tzinfo=UTC),
            "max_request_days": 10,
            "tickers": (ticker,),
        }
        missing = plan_yahoo_daily_completeness(**arguments)
        retry = plan_yahoo_daily_completeness(**arguments)

        assert missing.pulls == retry.pulls
        assert missing.pulls[0].planned_dates == (date(2026, 7, 2),)
        assert missing.enumerated_listing_count >= 1

        _insert_bar(cursor, listing_id, date(2026, 7, 2))
        completed = plan_yahoo_daily_completeness(**arguments)

        assert completed.requests == ()
        assert completed.listings[0].missing_sessions == ()

        cursor.execute(
            """
            DELETE FROM stonks.ohlcv_daily
            WHERE provider_listing_id = %s
              AND trading_date = %s
            """,
            (listing_id, date(2026, 7, 2)),
        )
        missing_again = plan_yahoo_daily_completeness(**arguments)

        assert missing_again.pulls == missing.pulls


@pytest.mark.parametrize(
    "ticker",
    ("BCOM", "CSI300", "MOVE", "PSEI", "SET", "TASI", "W5000"),
)
def test_database_plan_excludes_reviewed_stale_inactive_seed(
    database_connection: object,
    ticker: str,
) -> None:
    connection = database_connection
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        with pytest.raises(OHLCVConfigError, match="not an active seed"):
            plan_yahoo_daily_completeness(
                cursor=cursor,
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 30),
                now=datetime(2026, 8, 1, tzinfo=UTC),
                max_request_days=10,
                tickers=(ticker,),
            )
