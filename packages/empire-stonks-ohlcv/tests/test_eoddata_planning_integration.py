from __future__ import annotations

import os
from datetime import UTC, date, datetime
from typing import Iterator
from uuid import uuid4

import pytest

from empire_core import EmpireDatabase
from empire_stonks_ohlcv import (
    EODDataExchangeWorkReason,
    plan_eoddata_exchange_work,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
SESSION_DATE = date(2035, 7, 2)


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


def _insert_listing(cursor: object, exchange: str) -> object:
    policy_code = (
        "ED_XNAS_1900_60M"
        if exchange == "NASDAQ"
        else "ED_XNYS_1900_60M"
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.provider_listing (
            provider_code,
            market,
            ticker,
            name,
            status,
            session_policy_code
        )
        VALUES ('EODDATA', %s, %s, %s, 'ACTIVE', %s)
        RETURNING provider_listing_id
        """,
        (
            exchange,
            f"C93.{uuid4().hex.upper()}",
            f"C9.3 {exchange} planner test",
            policy_code,
        ),
    )
    return cursor.fetchone()[0]  # type: ignore[union-attr]


def _insert_bar(cursor: object, listing_id: object) -> None:
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
            typ,
            hl_range,
            oc_range
        )
        VALUES (%s, %s, 10, 12, 9, 11, 100, 10.66666667, 3, 1)
        """,
        (listing_id, SESSION_DATE),
    )


def test_database_plan_reconciles_complete_and_retries_missing_exchange(
    database_connection: object,
) -> None:
    connection = database_connection
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        listing_ids = {
            exchange: _insert_listing(cursor, exchange)
            for exchange in ("NYSE", "NASDAQ", "AMEX")
        }
        _insert_bar(cursor, listing_ids["NYSE"])
        _insert_bar(cursor, listing_ids["NASDAQ"])

        arguments = {
            "cursor": cursor,
            "start_date": SESSION_DATE,
            "end_date": SESSION_DATE,
            "now": datetime(2035, 7, 3, 2, tzinfo=UTC),
            "reconciliation_sessions": 1,
        }
        first = plan_eoddata_exchange_work(**arguments)
        repeated = plan_eoddata_exchange_work(**arguments)

        assert first == repeated
        assert tuple(item.exchange for item in first.work) == (
            "NYSE",
            "NASDAQ",
            "AMEX",
        )
        assert tuple(item.reason for item in first.work) == (
            EODDataExchangeWorkReason.RECENT_RECONCILIATION,
            EODDataExchangeWorkReason.RECENT_RECONCILIATION,
            EODDataExchangeWorkReason.ELIGIBLE_MISSING_SESSION,
        )
        assert first.exchanges[0].latest_eligible_is_complete
        assert first.exchanges[1].latest_eligible_is_complete
        assert not first.exchanges[2].latest_eligible_is_complete
