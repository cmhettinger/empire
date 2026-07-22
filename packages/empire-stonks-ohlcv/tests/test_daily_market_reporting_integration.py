from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterator
from uuid import uuid4

import pytest
from empire_core.db.connection import EmpireDatabase

from empire_stonks_ohlcv import (
    DailyBar,
    DailyBarWriteInput,
    ProviderListing,
    build_eoddata_daily_market_report,
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


def test_daily_market_report_queries_persisted_eoddata_equities(
    database_connection: object,
) -> None:
    connection = database_connection
    report_date = date(2099, 1, 22)
    suffix = uuid4().hex[:10].upper()
    equities = tuple(
        ProviderListing(
            provider_code="EODDATA",
            market=market,
            ticker=f"MKT{suffix}{index}",
            name=f"Market report test {market}",
            metadata={"type": "Equity", "currency": "USD"},
        )
        for index, market in enumerate(("NYSE", "NASDAQ", "AMEX"), start=1)
    )
    fund = ProviderListing(
        provider_code="EODDATA",
        market="AMEX",
        ticker=f"FND{suffix}",
        name="Excluded market report fund",
        metadata={"type": "Fund", "currency": "USD"},
    )

    with connection.cursor() as cursor:  # type: ignore[union-attr]
        resolved = upsert_provider_listings(
            cursor=cursor,
            listings=(*equities, fund),
        )
        nyse_id = resolved.provider_listing_id_for(equities[0])
        nasdaq_id = resolved.provider_listing_id_for(equities[1])
        amex_id = resolved.provider_listing_id_for(equities[2])
        fund_id = resolved.provider_listing_id_for(fund)

        bars: list[DailyBarWriteInput] = []
        for offset in range(21):
            bars.append(
                DailyBarWriteInput(
                    nyse_id,
                    _bar(
                        report_date - timedelta(days=21 - offset),
                        close="10",
                        volume="100",
                    ),
                )
            )
        bars.extend(
            (
                DailyBarWriteInput(
                    nyse_id,
                    _bar(report_date, close="15", volume="6000"),
                ),
                DailyBarWriteInput(
                    nasdaq_id,
                    _bar(report_date - timedelta(days=1), close="10", volume="100"),
                ),
                DailyBarWriteInput(
                    nasdaq_id,
                    _bar(report_date, close="9", volume="200"),
                ),
                DailyBarWriteInput(
                    amex_id,
                    _bar(report_date - timedelta(days=1), close="10", volume="100"),
                ),
                DailyBarWriteInput(
                    amex_id,
                    _bar(report_date, close="10", volume="300"),
                ),
                DailyBarWriteInput(
                    fund_id,
                    _bar(report_date, close="20", volume="400"),
                ),
            )
        )
        upsert_daily_bars(cursor=cursor, bars=bars)

        report = build_eoddata_daily_market_report(
            cursor=cursor,
            trading_date=report_date,
        )

    assert report.universe.source_bar_count == 4
    assert report.universe.equity_bar_count == 3
    assert report.universe.non_equity_bar_count == 1
    assert report.comparable_count == 3
    assert report.advancers == 1
    assert report.decliners == 1
    assert report.unchanged == 1
    assert {row.ticker for row in report.winners} == {equities[0].ticker}
    assert {row.ticker for row in report.losers} == {equities[1].ticker}
    assert report.price_anomalies[0].ticker == equities[0].ticker
    assert report.volume_anomalies[0].ticker == equities[0].ticker
    assert report.volume_anomalies[0].volume_multiple == Decimal("60")
    assert tuple(basket.code for basket in report.baskets) == (
        "MAG7",
        "DOW30",
        "NASDAQ100",
    )
    assert all(basket.available_count == 0 for basket in report.baskets)
    assert tuple(
        (row.market, row.ticker)
        for row in report.high_volume_low_movement
    ) == (("AMEX", equities[2].ticker),)


def _bar(trading_date: date, *, close: str, volume: str) -> DailyBar:
    close_value = Decimal(close)
    return DailyBar(
        trading_date=trading_date,
        open=close_value,
        high=close_value + Decimal("1"),
        low=close_value - Decimal("1"),
        close=close_value,
        volume=Decimal(volume),
    )
