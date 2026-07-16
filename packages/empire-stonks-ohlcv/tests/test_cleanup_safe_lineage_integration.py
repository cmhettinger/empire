from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Iterator
from uuid import uuid4

import pytest

from empire_core.db.connection import EmpireDatabase
from empire_stonks_ohlcv import (
    AcquiredObject,
    DailyBar,
    DailyBarWriteInput,
    ProviderListing,
    RAW_SOURCE_OBJECT_KIND,
    upsert_daily_bars,
    upsert_provider_listings,
    upsert_provider_source_snapshot,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
SOURCE_CODE = "eoddata_c44_cleanup"
CHECKSUM = "cd" * 32
TRADING_DATE = date(2026, 7, 15)


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


def test_raw_object_purge_preserves_snapshot_and_ohlcv_rows(
    database_connection: object,
) -> None:
    connection = database_connection
    marker = str(uuid4())
    object_key = (
        f"stonks/ohlcv/eoddata/runs/2026/07/16/{marker}/{SOURCE_CODE}"
    )
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        cursor.execute(
            """
            INSERT INTO core.core_run (
                domain,
                job_name,
                subject_key,
                effective_date,
                run_type,
                status,
                runner
            )
            VALUES (
                'stonks',
                'stonks_ohlcv_eoddata_daily',
                'all_series',
                DATE '2026-07-16',
                'cli',
                'started',
                'pytest'
            )
            RETURNING run_id
            """
        )
        run_id = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT storage_root_id
            FROM core.storage_root
            WHERE root_name = 'global'
              AND is_active
            """
        )
        storage_root_id = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO core.stored_object (
                run_id,
                storage_root_id,
                object_key,
                filename,
                object_scope,
                domain,
                logical_name,
                content_type,
                object_kind,
                size_bytes,
                checksum_sha256,
                metadata
            )
            VALUES (%s, %s, %s, 'raw.csv', 'run', 'stonks', %s, 'text/csv',
                    %s, 42, %s, '{}'::jsonb)
            RETURNING object_id
            """,
            (
                run_id,
                storage_root_id,
                object_key,
                SOURCE_CODE,
                RAW_SOURCE_OBJECT_KIND,
                CHECKSUM,
            ),
        )
        object_id = cursor.fetchone()[0]
        acquired = AcquiredObject(
            source_code=SOURCE_CODE,
            object_id=object_id,
            object_key=object_key,
            filename="raw.csv",
            size_bytes=42,
            checksum_sha256=CHECKSUM,
        )
        registration = upsert_provider_source_snapshot(
            cursor=cursor,
            provider_code="EODDATA",
            acquired_object=acquired,
            parser_version="test.v1",
        )

        listing = ProviderListing(
            provider_code="EODDATA",
            market=f"C44_{marker}",
            ticker="LINEAGE",
        )
        provider_listing_id = upsert_provider_listings(
            cursor=cursor,
            listings=(listing,),
        ).provider_listing_id_for(listing)
        write_result = upsert_daily_bars(
            cursor=cursor,
            bars=(
                DailyBarWriteInput(
                    provider_listing_id=provider_listing_id,
                    bar=DailyBar(
                        trading_date=TRADING_DATE,
                        open=Decimal("10"),
                        high=Decimal("12"),
                        low=Decimal("9"),
                        close=Decimal("11"),
                        volume=Decimal("100"),
                    ),
                ),
            ),
        )
        assert write_result.inserted == 1
        cursor.execute(
            """
            SELECT count(*)
            FROM stonks.provider_source_snapshot_object
            WHERE source_snapshot_id = %s
              AND object_id = %s
            """,
            (registration.source_snapshot_id, object_id),
        )
        assert cursor.fetchone()[0] == 1

        cursor.execute(
            """
            DELETE FROM core.stored_object
            WHERE object_id = %s
            """,
            (object_id,),
        )
        assert cursor.rowcount == 1

        cursor.execute(
            """
            SELECT count(*)
            FROM stonks.provider_source_snapshot_object
            WHERE object_id = %s
            """,
            (object_id,),
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            """
            SELECT
                provider_code,
                source_code,
                content_sha256,
                first_seen_object_id,
                first_seen_run_id,
                parser_version
            FROM stonks.provider_source_snapshot
            WHERE source_snapshot_id = %s
            """,
            (registration.source_snapshot_id,),
        )
        assert cursor.fetchone() == (
            "EODDATA",
            SOURCE_CODE,
            CHECKSUM,
            None,
            run_id,
            "test.v1",
        )
        cursor.execute(
            """
            SELECT
                pl.provider_code,
                pl.market,
                pl.ticker,
                od.trading_date,
                od.open,
                od.high,
                od.low,
                od.close,
                od.volume
            FROM stonks.provider_listing pl
            JOIN stonks.ohlcv_daily od
              ON od.provider_listing_id = pl.provider_listing_id
            WHERE pl.provider_listing_id = %s
            """,
            (provider_listing_id,),
        )
        assert cursor.fetchone() == (
            "EODDATA",
            f"C44_{marker}",
            "LINEAGE",
            TRADING_DATE,
            Decimal("10.0000000000"),
            Decimal("12.0000000000"),
            Decimal("9.0000000000"),
            Decimal("11.0000000000"),
            Decimal("100.00000000"),
        )
