from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4

import pytest

from empire_core import ObjectStore, RunService
from empire_core.db.connection import EmpireDatabase
from empire_core.object_store.models import StoredObject
from empire_core.object_store.repository import PostgresObjectRepository
from empire_stonks_ohlcv import (
    AcquiredObject,
    DailyBar,
    DailyBarWriteInput,
    ProviderListing,
    RAW_SOURCE_OBJECT_KIND,
    REPORT_OBJECT_KIND,
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
SOURCE_CODE = "eoddata_v106_cleanup"
SESSION_POLICY_CODE = "ED_XNYS_1900_60M"
TRADING_DATE = date(2026, 7, 15)
REPORT_BYTES = b'{"status":"PASS","task":"V10.6"}\n'


class _FixtureObjectRepository(PostgresObjectRepository):
    """Limit expiration cleanup to the object created by this test."""

    cleanup_object_id: UUID | None = None

    def find_expired_objects(
        self,
        *,
        limit: int,
        after_expires_at: datetime | None = None,
        after_object_id: UUID | None = None,
    ) -> list[StoredObject]:
        del after_expires_at, after_object_id
        if self.cleanup_object_id is None or limit <= 0:
            return []
        stored = self.get_object(self.cleanup_object_id)
        if (
            stored is None
            or stored.deleted_at is not None
            or stored.expires_at is None
            or stored.expires_at > datetime.now(UTC)
        ):
            return []
        return [stored]


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


def test_expired_raw_object_cleanup_preserves_durable_ohlcv_and_report(
    database_connection: object,
) -> None:
    connection = database_connection
    marker = uuid4().hex[:10]
    runner = f"pytest:v106:{marker}"
    raw_bytes = f"date,open,high,low,close\n{TRADING_DATE},10,12,9,11\n".encode()
    repository = _FixtureObjectRepository(connection)
    object_store = ObjectStore(repository, tombstone_days=0)
    run_service = RunService.from_connection(connection)
    run_id: UUID | None = None
    raw_object_id: UUID | None = None
    report_object_id: UUID | None = None
    source_snapshot_id: UUID | None = None
    provider_listing_id: UUID | None = None
    raw_path: Path | None = None

    try:
        run_context = run_service.start_run(
            domain="stonks",
            job_name="stonks_ohlcv_v106_cleanup",
            subject_key="EODDATA:NYSE",
            effective_date=TRADING_DATE,
            run_type="manual",
            runner=runner,
        )
        run_id = run_context.run_id
        object_key = f"stonks/ohlcv/tests/v106/{marker}"
        raw_object = object_store.put_bytes(
            run_context=run_context,
            storage_root="global",
            object_key=f"{object_key}/raw",
            filename="raw.csv",
            data=raw_bytes,
            object_scope="run",
            domain="stonks",
            logical_name=SOURCE_CODE,
            content_type="text/csv",
            object_kind=RAW_SOURCE_OBJECT_KIND,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
            metadata={"provider_code": "EODDATA"},
        )
        raw_object_id = raw_object.object_id
        raw_path = object_store.get_path(raw_object_id)
        report_object = object_store.put_bytes(
            run_context=run_context,
            storage_root="global",
            object_key=f"{object_key}/report",
            filename="report.json",
            data=REPORT_BYTES,
            object_scope="run",
            domain="stonks",
            logical_name="stonks_ohlcv_v106_cleanup_report",
            content_type="application/json",
            object_kind=REPORT_OBJECT_KIND,
            metadata={"provider_code": "EODDATA"},
        )
        report_object_id = report_object.object_id
        repository.cleanup_object_id = raw_object_id

        acquired = AcquiredObject(
            source_code=SOURCE_CODE,
            object_id=raw_object_id,
            object_key=raw_object.object_key,
            filename=raw_object.filename,
            size_bytes=raw_object.size_bytes,
            checksum_sha256=raw_object.checksum_sha256,
        )
        listing = ProviderListing(
            provider_code="EODDATA",
            market="NYSE",
            ticker=f"V106{marker.upper()}",
        )
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            registration = upsert_provider_source_snapshot(
                cursor=cursor,
                provider_code="EODDATA",
                acquired_object=acquired,
                parser_version="test.v10.6",
            )
            source_snapshot_id = registration.source_snapshot_id
            provider_listing_id = upsert_provider_listings(
                cursor=cursor,
                listings=(listing,),
            ).provider_listing_id_for(listing)
            cursor.execute(
                """
                UPDATE stonks.provider_listing
                SET session_policy_code = %s,
                    updated_at = now()
                WHERE provider_listing_id = %s
                """,
                (SESSION_POLICY_CODE, provider_listing_id),
            )
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
        connection.commit()  # type: ignore[union-attr]

        assert raw_path.is_file()
        assert object_store.get_bytes(report_object_id) == REPORT_BYTES
        _assert_membership_count(
            connection,
            source_snapshot_id=source_snapshot_id,
            object_id=raw_object_id,
            expected=1,
        )

        cleanup = object_store.cleanup_expired_objects(batch_size=1)
        assert cleanup.cleaned_count == 1
        assert cleanup.cleaned_bytes == len(raw_bytes)
        assert not raw_path.exists()
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT deleted_at IS NOT NULL, purge_after IS NOT NULL
                FROM core.stored_object
                WHERE object_id = %s
                """,
                (raw_object_id,),
            )
            assert cursor.fetchone() == (True, True)

        assert (
            object_store.purge_deleted_objects_by_run_id(
                run_id,
                ignore_purge_after=True,
            )
            == 1
        )
        _assert_membership_count(
            connection,
            source_snapshot_id=source_snapshot_id,
            object_id=raw_object_id,
            expected=0,
        )
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                "SELECT count(*) FROM core.stored_object WHERE object_id = %s",
                (raw_object_id,),
            )
            assert cursor.fetchone()[0] == 0
        _assert_durable_rows(
            connection,
            source_snapshot_id=source_snapshot_id,
            provider_listing_id=provider_listing_id,
            run_id=run_id,
            report_object_id=report_object_id,
            checksum=raw_object.checksum_sha256,
            ticker=listing.ticker,
        )
        assert object_store.get_bytes(report_object_id) == REPORT_BYTES
    finally:
        _cleanup_fixture(
            connection=connection,
            object_store=object_store,
            run_id=run_id,
            source_snapshot_id=source_snapshot_id,
            provider_listing_id=provider_listing_id,
        )


def _assert_membership_count(
    connection: Any,
    *,
    source_snapshot_id: UUID,
    object_id: UUID,
    expected: int,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM stonks.provider_source_snapshot_object
            WHERE source_snapshot_id = %s
              AND object_id = %s
            """,
            (source_snapshot_id, object_id),
        )
        assert cursor.fetchone()[0] == expected


def _assert_durable_rows(
    connection: Any,
    *,
    source_snapshot_id: UUID,
    provider_listing_id: UUID,
    run_id: UUID,
    report_object_id: UUID,
    checksum: str,
    ticker: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM core.stored_object WHERE object_id = %s",
            (report_object_id,),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            """
            SELECT object_kind, expires_at, deleted_at
            FROM core.stored_object
            WHERE object_id = %s
              AND run_id = %s
            """,
            (report_object_id, run_id),
        )
        assert cursor.fetchone() == (REPORT_OBJECT_KIND, None, None)
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
            (source_snapshot_id,),
        )
        assert cursor.fetchone() == (
            "EODDATA",
            SOURCE_CODE,
            checksum,
            None,
            run_id,
            "test.v10.6",
        )
        cursor.execute(
            """
            SELECT
                listing.provider_code,
                listing.market,
                listing.ticker,
                policy.session_policy_code,
                policy.calendar_name,
                bar.trading_date,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume
            FROM stonks.provider_listing AS listing
            JOIN stonks.ohlcv_session_policy AS policy
              USING (session_policy_code)
            JOIN stonks.ohlcv_daily AS bar
              USING (provider_listing_id)
            WHERE listing.provider_listing_id = %s
            """,
            (provider_listing_id,),
        )
        assert cursor.fetchone() == (
            "EODDATA",
            "NYSE",
            ticker,
            SESSION_POLICY_CODE,
            "XNYS",
            TRADING_DATE,
            Decimal("10.0000000000"),
            Decimal("12.0000000000"),
            Decimal("9.0000000000"),
            Decimal("11.0000000000"),
            Decimal("100.00000000"),
        )


def _cleanup_fixture(
    *,
    connection: Any,
    object_store: ObjectStore,
    run_id: UUID | None,
    source_snapshot_id: UUID | None,
    provider_listing_id: UUID | None,
) -> None:
    connection.rollback()
    if run_id is not None:
        object_store.delete_objects_by_run_id(run_id)
        object_store.purge_deleted_objects_by_run_id(
            run_id,
            ignore_purge_after=True,
        )
    with connection.cursor() as cursor:
        if source_snapshot_id is not None:
            cursor.execute(
                """
                DELETE FROM stonks.provider_source_snapshot
                WHERE source_snapshot_id = %s
                """,
                (source_snapshot_id,),
            )
        if provider_listing_id is not None:
            cursor.execute(
                """
                DELETE FROM stonks.provider_listing
                WHERE provider_listing_id = %s
                """,
                (provider_listing_id,),
            )
        if run_id is not None:
            cursor.execute(
                "DELETE FROM core.core_run WHERE run_id = %s",
                (run_id,),
            )
    connection.commit()
