from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Iterator
from uuid import uuid4

import pytest

import empire_stonks_ohlcv.stooq_history_writer as stooq_writer
from empire_core.db.connection import EmpireDatabase
from empire_stonks_ohlcv import (
    DailyBar,
    OHLCVWorkflowError,
    ParsedListingBatch,
    ProviderListing,
    StooqHistoryChunk,
    StooqHistoryChunkWriter,
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
    value = Decimal(close)
    return DailyBar(
        trading_date=trading_date,
        open=value,
        high=value + 1,
        low=value - 1,
        close=value,
        volume=Decimal("100"),
    )


def _chunk(
    chunk_number: int,
    listing: ProviderListing,
    *bars: DailyBar,
) -> StooqHistoryChunk:
    return StooqHistoryChunk(
        chunk_number=chunk_number,
        batches=(ParsedListingBatch(listing=listing, bars=tuple(bars)),),
    )


def test_chunk_transactions_commit_survive_failure_and_rerun_idempotently(
    database_connection: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = database_connection
    marker = uuid4().hex[:12].upper()
    listing = ProviderListing(
        provider_code="STOOQ",
        market="nasdaq",
        ticker=f"H73{marker}.US",
    )
    failed_listing = ProviderListing(
        provider_code="STOOQ",
        market="nyse",
        ticker=f"H73F{marker}.US",
    )
    first = _chunk(
        1,
        listing,
        _bar(date(2026, 1, 2), "10"),
        _bar(date(2026, 1, 6), "12"),
    )
    gap = _chunk(2, listing, _bar(date(2026, 1, 5), "11"))
    failed = _chunk(3, failed_listing, _bar(date(2026, 1, 7), "20"))

    try:
        writer = StooqHistoryChunkWriter(connection)
        first_result = writer.write(first)
        gap_result = writer.write(gap)

        assert first_result.listing_counts.inserted == 1
        assert first_result.bar_counts.inserted == 2
        assert gap_result.listing_counts.unchanged == 1
        assert gap_result.bar_counts.inserted == 1
        assert gap_result.bar_counts.derived_updated == 1

        original_bar_writer = stooq_writer.upsert_daily_bars

        def fail_bar_write(**_values: object) -> object:
            raise RuntimeError("forced chunk failure")

        monkeypatch.setattr(stooq_writer, "upsert_daily_bars", fail_bar_write)
        with pytest.raises(OHLCVWorkflowError):
            writer.write(failed)

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT count(*)
                FROM stonks.provider_listing
                WHERE provider_code = 'STOOQ'
                  AND ticker = %s
                """,
                (failed_listing.ticker,),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                """
                SELECT count(*)
                FROM stonks.ohlcv_daily AS bar
                JOIN stonks.provider_listing AS listing
                  USING (provider_listing_id)
                WHERE listing.provider_code = 'STOOQ'
                  AND listing.ticker = %s
                """,
                (listing.ticker,),
            )
            assert cursor.fetchone()[0] == 3

        monkeypatch.setattr(
            stooq_writer,
            "upsert_daily_bars",
            original_bar_writer,
        )
        retry_result = writer.write(failed)
        assert retry_result.listing_counts.inserted == 1
        assert retry_result.bar_counts.inserted == 1
        assert writer.summary.chunks_completed == 3
        assert writer.summary.chunks_failed == 1

        rerun = StooqHistoryChunkWriter(connection)
        rerun_first = rerun.write(first)
        rerun_gap = rerun.write(gap)
        rerun_failed = rerun.write(failed)
        assert rerun_first.listing_counts.unchanged == 1
        assert rerun_first.bar_counts.unchanged == 2
        assert rerun_gap.listing_counts.unchanged == 1
        assert rerun_gap.bar_counts.unchanged == 1
        assert rerun_failed.listing_counts.unchanged == 1
        assert rerun_failed.bar_counts.unchanged == 1
    finally:
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                DELETE FROM stonks.ohlcv_daily
                WHERE provider_listing_id IN (
                    SELECT provider_listing_id
                    FROM stonks.provider_listing
                    WHERE provider_code = 'STOOQ'
                      AND ticker = ANY(%s)
                )
                """,
                ([listing.ticker, failed_listing.ticker],),
            )
            cursor.execute(
                """
                DELETE FROM stonks.provider_listing
                WHERE provider_code = 'STOOQ'
                  AND ticker = ANY(%s)
                """,
                ([listing.ticker, failed_listing.ticker],),
            )
        connection.commit()  # type: ignore[union-attr]
