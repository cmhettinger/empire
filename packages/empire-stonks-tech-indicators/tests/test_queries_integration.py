from __future__ import annotations

import os
from datetime import date
from typing import Iterator
from uuid import UUID, uuid4

import pytest

from empire_stonks_tech_indicators import (
    TechIndicatorsScope,
    select_eligible_listings,
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


def _insert_listing(
    cursor: object,
    *,
    provider_code: str,
    market: str,
    ticker: str,
    status: str = "ACTIVE",
    metadata_json: str | None = None,
) -> UUID:
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.provider_listing (
            provider_code,
            market,
            ticker,
            status,
            metadata
        )
        VALUES (%s, %s, %s, %s, %s::jsonb)
        RETURNING provider_listing_id
        """,
        (provider_code, market, ticker, status, metadata_json),
    )
    return cursor.fetchone()[0]  # type: ignore[union-attr,no-any-return]


def _insert_bar(cursor: object, provider_listing_id: UUID, trading_date: date) -> None:
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
        VALUES (
            %s, %s, 10, 12, 9, 11, 100, NULL, NULL,
            round((12::numeric + 9 + 11) / 3, 8), 3, 1
        )
        """,
        (provider_listing_id, trading_date),
    )


def test_eligible_listing_query_enforces_policy_status_dates_and_history(
    database_connection: object,
) -> None:
    marker = uuid4().hex[:12].upper()
    first_date = date(2026, 1, 2)
    second_date = date(2026, 1, 5)

    with database_connection.cursor() as cursor:  # type: ignore[union-attr]
        active_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="NASDAQ",
            ticker=f"I31A{marker}",
            metadata_json='{"type": " equity "}',
        )
        short_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="NYSE",
            ticker=f"I31S{marker}",
            metadata_json='{"type": "Equity"}',
        )
        amex_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="AMEX",
            ticker=f"I31E{marker}",
            metadata_json='{"type": "EQUITY"}',
        )
        inactive_id = _insert_listing(
            cursor,
            provider_code="STOOQ",
            market="nasdaq",
            ticker=f"I31I{marker}.US",
            status="INACTIVE",
        )
        stooq_nyse_id = _insert_listing(
            cursor,
            provider_code="STOOQ",
            market="nyse",
            ticker=f"I31N{marker}.US",
        )
        stooq_nysemkt_id = _insert_listing(
            cursor,
            provider_code="STOOQ",
            market="nysemkt",
            ticker=f"I31K{marker}.US",
        )
        unsupported_type_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="AMEX",
            ticker=f"I31T{marker}",
            metadata_json='{"type": "ETF"}',
        )
        non_string_type_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="AMEX",
            ticker=f"I31J{marker}",
            metadata_json='{"type": 1}',
        )
        missing_type_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="NYSE",
            ticker=f"I31X{marker}",
            metadata_json='{}',
        )
        unsupported_market_id = _insert_listing(
            cursor,
            provider_code="STOOQ",
            market="NASDAQ",
            ticker=f"I31M{marker}.US",
        )
        unsupported_yahoo_id = _insert_listing(
            cursor,
            provider_code="YAHOO",
            market="XIDX",
            ticker=f"I31Y{marker}",
            metadata_json=f'{{"YahooTicker": "^{marker}"}}',
        )
        _insert_bar(cursor, active_id, first_date)
        _insert_bar(cursor, active_id, second_date)
        _insert_bar(cursor, short_id, second_date)
        _insert_bar(cursor, inactive_id, second_date)

        explicit_ids = (
            active_id,
            short_id,
            amex_id,
            inactive_id,
            stooq_nyse_id,
            stooq_nysemkt_id,
            unsupported_type_id,
            non_string_type_id,
            missing_type_id,
            unsupported_market_id,
            unsupported_yahoo_id,
        )
        active = select_eligible_listings(
            cursor=cursor,
            scope=TechIndicatorsScope(provider_listing_ids=explicit_ids),
        )
        by_id = {item.provider_listing_id: item for item in active}
        assert set(by_id) == {
            active_id,
            short_id,
            amex_id,
            stooq_nyse_id,
            stooq_nysemkt_id,
        }
        assert by_id[active_id].source_observation_count == 2
        assert by_id[short_id].source_observation_count == 1
        assert by_id[amex_id].source_observation_count == 0
        assert by_id[stooq_nyse_id].source_observation_count == 0
        assert by_id[stooq_nysemkt_id].source_observation_count == 0
        assert by_id[active_id].has_minimum_history(2) is True
        assert by_id[short_id].has_minimum_history(2) is False

        scoped = select_eligible_listings(
            cursor=cursor,
            scope=TechIndicatorsScope(
                provider_listing_ids=(active_id, short_id),
                start_date=second_date,
                end_date=second_date,
            ),
        )
        assert [item.source_observation_count for item in scoped] == [1, 1]
        assert all(item.first_trading_date == second_date for item in scoped)
        assert all(item.last_trading_date == second_date for item in scoped)

        inactive = select_eligible_listings(
            cursor=cursor,
            scope=TechIndicatorsScope(
                provider_listing_ids=(inactive_id,),
                include_inactive=True,
            ),
        )
        assert len(inactive) == 1
        assert inactive[0].status == "INACTIVE"
        assert inactive[0].source_observation_count == 1

        cursor.execute(
            """
            SELECT provider_listing_id
            FROM stonks.provider_listing
            WHERE provider_code = 'YAHOO'
              AND market = 'XIDX'
              AND ticker = 'SPX'
              AND status = 'ACTIVE'
            """
        )
        spx_id = cursor.fetchone()[0]
        spx = select_eligible_listings(
            cursor=cursor,
            scope=TechIndicatorsScope(
                provider_listing_ids=(spx_id,),
                start_date=date(2099, 1, 1),
                end_date=date(2099, 1, 1),
            ),
        )
        assert len(spx) == 1
        assert spx[0].provider_code == "YAHOO"
        assert spx[0].market == "XIDX"
        assert spx[0].ticker == "SPX"
        assert spx[0].instrument_type_code == "EQUITY_INDEX"
        assert spx[0].source_observation_count == 0
