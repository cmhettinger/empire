from __future__ import annotations

import hashlib
import os
from datetime import date
from decimal import Decimal
from typing import Iterator
from uuid import UUID, uuid4

import pytest

from empire_core import RunContext
from empire_core.db.connection import EmpireDatabase
from empire_stonks_ohlcv import (
    AcquiredObject,
    DailyBar,
    OHLCVWorkflowError,
    ParsedListingBatch,
    ProviderListing,
    RAW_SOURCE_OBJECT_KIND,
    execute_import_boundary,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
SOURCE_CODE = "eoddata_c46_boundary"
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


def test_raw_objects_survive_failures_and_database_writes_rerun_atomically(
    database_connection: object,
) -> None:
    connection = database_connection
    marker = str(uuid4())
    market = f"C46_{marker}"
    checksums = {
        stage: hashlib.sha256(f"{marker}:{stage}".encode()).hexdigest()
        for stage in ("success", "acquisition", "parsing", "persistence")
    }
    object_ids: list[UUID] = []

    try:
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
                    %s,
                    DATE '2026-07-16',
                    'cli',
                    'started',
                    'pytest'
                )
                RETURNING run_id, started_at
                """,
                (f"c46:{marker}",),
            )
            run_id, started_at = cursor.fetchone()
            cursor.execute(
                """
                SELECT storage_root_id
                FROM core.storage_root
                WHERE root_name = 'global'
                  AND is_active
                """
            )
            storage_root_id = cursor.fetchone()[0]
        connection.commit()  # type: ignore[union-attr]

        run_context = RunContext(
            run_id=run_id,
            domain="stonks",
            job_name="stonks_ohlcv_eoddata_daily",
            subject_key=f"c46:{marker}",
            effective_date=date(2026, 7, 16),
            run_type="cli",
            status="started",
            runner="pytest",
            params={},
            started_at=started_at,
        )

        def store_raw(stage: str) -> AcquiredObject:
            object_key = f"stonks/ohlcv/eoddata/c46/{marker}/{stage}"
            with connection.cursor() as cursor:  # type: ignore[union-attr]
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
                    VALUES (%s, %s, %s, 'raw.csv', 'run', 'stonks', %s,
                            'text/csv', %s, 42, %s, '{}'::jsonb)
                    RETURNING object_id
                    """,
                    (
                        run_id,
                        storage_root_id,
                        object_key,
                        SOURCE_CODE,
                        RAW_SOURCE_OBJECT_KIND,
                        checksums[stage],
                    ),
                )
                object_id = cursor.fetchone()[0]
            connection.commit()  # type: ignore[union-attr]
            object_ids.append(object_id)
            return AcquiredObject(
                source_code=SOURCE_CODE,
                object_id=object_id,
                object_key=object_key,
                filename="raw.csv",
                size_bytes=42,
                checksum_sha256=checksums[stage],
            )

        valid_batch = ParsedListingBatch(
            listing=ProviderListing(
                provider_code="EODDATA",
                market=market,
                ticker="LINEAGE",
            ),
            bars=(
                DailyBar(
                    trading_date=TRADING_DATE,
                    open=Decimal("10"),
                    high=Decimal("12"),
                    low=Decimal("9"),
                    close=Decimal("11"),
                    volume=Decimal("100"),
                ),
            ),
        )

        success_object = store_raw("success")
        first = execute_import_boundary(
            connection=connection,
            run_context=run_context,
            provider_code="EODDATA",
            acquire=lambda _context: (success_object,),
            parse=lambda _objects: (valid_batch,),
            parser_versions={SOURCE_CODE: "test.v1"},
        )
        rerun = execute_import_boundary(
            connection=connection,
            run_context=run_context,
            provider_code="EODDATA",
            acquire=lambda _context: (success_object,),
            parse=lambda _objects: (valid_batch,),
            parser_versions={SOURCE_CODE: "test.v1"},
        )
        assert first.listing_counts.inserted == 1
        assert first.bar_counts.inserted == 1
        assert rerun.listing_counts.unchanged == 1
        assert rerun.bar_counts.unchanged == 1

        acquisition_object = store_raw("acquisition")

        def fail_after_acquisition(
            _context: RunContext,
        ) -> tuple[AcquiredObject, ...]:
            assert acquisition_object.object_id in object_ids
            raise RuntimeError("provider acquisition detail")

        with pytest.raises(OHLCVWorkflowError) as acquisition_error:
            execute_import_boundary(
                connection=connection,
                run_context=run_context,
                provider_code="EODDATA",
                acquire=fail_after_acquisition,
                parse=lambda _objects: (),
            )
        assert acquisition_error.value.stage == "acquisition"

        parsing_object = store_raw("parsing")
        with pytest.raises(OHLCVWorkflowError) as parsing_error:
            execute_import_boundary(
                connection=connection,
                run_context=run_context,
                provider_code="EODDATA",
                acquire=lambda _context: (parsing_object,),
                parse=lambda _objects: (_ for _ in ()).throw(
                    RuntimeError("provider parser detail")
                ),
            )
        assert parsing_error.value.stage == "parsing"

        persistence_object = store_raw("persistence")
        invalid_batch = ParsedListingBatch(
            listing=ProviderListing(
                provider_code="EODDATA",
                market=market,
                ticker="ROLLBACK",
                instrument_type_code="C46_NOT_REAL",
            ),
            bars=(),
        )
        with pytest.raises(OHLCVWorkflowError) as persistence_error:
            execute_import_boundary(
                connection=connection,
                run_context=run_context,
                provider_code="EODDATA",
                acquire=lambda _context: (persistence_object,),
                parse=lambda _objects: (invalid_batch,),
            )
        assert persistence_error.value.stage == "persistence"

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT count(*)
                FROM core.stored_object
                WHERE object_id = ANY(%s)
                """,
                (object_ids,),
            )
            assert cursor.fetchone()[0] == 4
            cursor.execute(
                """
                SELECT content_sha256
                FROM stonks.provider_source_snapshot
                WHERE provider_code = 'EODDATA'
                  AND source_code = %s
                  AND content_sha256 = ANY(%s)
                """,
                (SOURCE_CODE, list(checksums.values())),
            )
            assert cursor.fetchall() == [(checksums["success"],)]
            cursor.execute(
                """
                SELECT pl.ticker, count(od.trading_date)
                FROM stonks.provider_listing pl
                LEFT JOIN stonks.ohlcv_daily od
                  ON od.provider_listing_id = pl.provider_listing_id
                WHERE pl.provider_code = 'EODDATA'
                  AND pl.market = %s
                GROUP BY pl.ticker
                """,
                (market,),
            )
            assert cursor.fetchall() == [("LINEAGE", 1)]
    finally:
        connection.rollback()  # type: ignore[union-attr]
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                DELETE FROM stonks.provider_listing
                WHERE provider_code = 'EODDATA'
                  AND market = %s
                """,
                (market,),
            )
            cursor.execute(
                """
                DELETE FROM stonks.provider_source_snapshot_object
                WHERE object_id = ANY(%s)
                """,
                (object_ids,),
            )
            cursor.execute(
                """
                DELETE FROM stonks.provider_source_snapshot
                WHERE provider_code = 'EODDATA'
                  AND source_code = %s
                  AND content_sha256 = ANY(%s)
                """,
                (SOURCE_CODE, list(checksums.values())),
            )
            cursor.execute(
                """
                DELETE FROM core.stored_object
                WHERE object_id = ANY(%s)
                """,
                (object_ids,),
            )
            cursor.execute(
                """
                DELETE FROM core.core_run
                WHERE subject_key = %s
                """,
                (f"c46:{marker}",),
            )
        connection.commit()  # type: ignore[union-attr]
