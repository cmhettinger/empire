from __future__ import annotations

import os
from typing import Iterator
from uuid import UUID, uuid4

import pytest

from empire_core.db.connection import EmpireDatabase
from empire_stonks_ohlcv import (
    AcquiredObject,
    RAW_SOURCE_OBJECT_KIND,
    upsert_provider_source_snapshot,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
CHECKSUM = "ef" * 32
SOURCE_CODE = "eoddata_c43_test"


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


def _insert_core_object(
    *,
    cursor: object,
    run_id: UUID,
    storage_root_id: int,
    marker: str,
) -> AcquiredObject:
    object_key = f"stonks/ohlcv/eoddata/runs/2026/07/16/{marker}/{SOURCE_CODE}"
    cursor.execute(  # type: ignore[union-attr]
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
    object_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    return AcquiredObject(
        source_code=SOURCE_CODE,
        object_id=object_id,
        object_key=object_key,
        filename="raw.csv",
        size_bytes=42,
        checksum_sha256=CHECKSUM,
    )


def test_source_snapshot_registration_round_trip_against_postgres(
    database_connection: object,
) -> None:
    connection = database_connection
    marker = str(uuid4())
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
        first_object = _insert_core_object(
            cursor=cursor,
            run_id=run_id,
            storage_root_id=storage_root_id,
            marker=f"{marker}-first",
        )
        second_object = _insert_core_object(
            cursor=cursor,
            run_id=run_id,
            storage_root_id=storage_root_id,
            marker=f"{marker}-second",
        )

        first = upsert_provider_source_snapshot(
            cursor=cursor,
            provider_code="EODDATA",
            acquired_object=first_object,
            parser_version="test.v1",
        )
        rerun = upsert_provider_source_snapshot(
            cursor=cursor,
            provider_code="EODDATA",
            acquired_object=first_object,
            parser_version="test.v1",
        )
        second = upsert_provider_source_snapshot(
            cursor=cursor,
            provider_code="EODDATA",
            acquired_object=second_object,
            parser_version="test.v1",
        )

        assert first.snapshot_inserted is True
        assert first.object_link_inserted is True
        assert rerun.source_snapshot_id == first.source_snapshot_id
        assert rerun.snapshot_inserted is False
        assert rerun.object_link_inserted is False
        assert second.source_snapshot_id == first.source_snapshot_id
        assert second.snapshot_inserted is False
        assert second.object_link_inserted is True

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
            (first.source_snapshot_id,),
        )
        assert cursor.fetchone() == (
            "EODDATA",
            SOURCE_CODE,
            CHECKSUM,
            first_object.object_id,
            run_id,
            "test.v1",
        )
        cursor.execute(
            """
            SELECT object_id
            FROM stonks.provider_source_snapshot_object
            WHERE source_snapshot_id = %s
            ORDER BY object_id
            """,
            (first.source_snapshot_id,),
        )
        assert {row[0] for row in cursor.fetchall()} == {
            first_object.object_id,
            second_object.object_id,
        }
