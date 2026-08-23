from __future__ import annotations

import os
from datetime import date
from typing import Iterator
from uuid import UUID, uuid4

import pytest

from empire_stonks_tech_indicators.daily_publication import (
    DailyCandidateListing,
    create_daily_candidate,
    prepare_daily_candidate,
    select_daily_target_slots,
)
from empire_stonks_tech_indicators.persistence import TechIndicatorsPayloadSlot


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


def test_building_daily_candidate_matches_flyway_shape(
    database_connection: object,
) -> None:
    connection = database_connection
    cursor = connection.cursor()  # type: ignore[union-attr]
    marker = uuid4().hex[:12].upper()
    trading_date = date(2097, 9, 3)
    publication_id: UUID | None = None
    run_id: UUID | None = None
    listing_id: UUID | None = None
    object_ids: list[UUID] = []
    try:
        cursor.execute(
            """
            INSERT INTO stonks.provider_listing (
                provider_code, market, ticker, status, metadata
            )
            VALUES ('EODDATA', 'NASDAQ', %s, 'ACTIVE', '{"type": "Equity"}')
            RETURNING provider_listing_id
            """,
            (f"J93{marker}",),
        )
        listing_id = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO stonks.ohlcv_daily (
                provider_listing_id, trading_date, open, high, low, close,
                volume, change, changepct, typ, hl_range, oc_range
            )
            VALUES (%s, %s, 10, 12, 9, 11, 100, NULL, NULL,
                    10.66666667, 3, 1)
            """,
            (listing_id, trading_date),
        )
        cursor.execute(
            """
            INSERT INTO core.core_run (
                domain, job_name, subject_key, run_type, status, runner
            )
            VALUES (
                'stonks', 'stonks_tech_indicators_daily', 'all_series',
                'manual', 'started', 'pytest'
            )
            RETURNING run_id
            """
        )
        run_id = cursor.fetchone()[0]
        slots = select_daily_target_slots(
            cursor=cursor,
            provider_listing_ids=(listing_id,),
        )
        publication_id = create_daily_candidate(
            cursor=cursor,
            publication_kind="DAILY",
            effective_date=trading_date,
            run_id=run_id,
            scope_hash="a" * 64,
            memberships=(
                DailyCandidateListing(
                    provider_listing_id=listing_id,
                    target_slot=slots[listing_id],
                    source_coverage_start_date=trading_date,
                    source_coverage_end_date=trading_date,
                    source_row_count=1,
                    benchmark_provider_listing_id=None,
                ),
            ),
            benchmark_provider_listing_id=None,
            benchmark_coverage_start_date=None,
            benchmark_coverage_end_date=None,
            benchmark_source_row_count=None,
        )
        connection.commit()

        cursor.execute(
            """
            SELECT publication_kind, status, publication_method,
                   scope_schema_version, scope_hash, effective_date, run_id
            FROM stonks.tech_indicators_publication
            WHERE publication_id = %s
            """,
            (publication_id,),
        )
        assert cursor.fetchone() == (
            "DAILY",
            "BUILDING",
            "IN_PLACE",
            1,
            "a" * 64,
            trading_date,
            run_id,
        )
        cursor.execute(
            """
            SELECT action, target_slot, source_row_count, payload_row_count,
                   is_active
            FROM stonks.tech_indicators_publication_listing
            WHERE publication_id = %s
            """,
            (publication_id,),
        )
        assert cursor.fetchone() == ("PRESENT", "A", 1, 1, False)
        cursor.execute(
            "SELECT storage_root_id FROM core.storage_root "
            "WHERE root_name = 'global' AND is_active"
        )
        storage_root_id = cursor.fetchone()[0]
        for filename, content_type, object_kind, checksum in (
            (
                "report.json",
                "application/json",
                "stonks_tech_indicators_report",
                "c" * 64,
            ),
            (
                "report.pdf",
                "application/pdf",
                "stonks_tech_indicators_pdf_report",
                "d" * 64,
            ),
        ):
            cursor.execute(
                """
                INSERT INTO core.stored_object (
                    run_id, storage_root_id, object_key, filename,
                    object_scope, domain, content_type, object_kind,
                    size_bytes, checksum_sha256, metadata
                )
                VALUES (
                    %s, %s, %s, %s, 'run', 'stonks', %s, %s, 1, %s, '{}'
                )
                RETURNING object_id
                """,
                (
                    run_id,
                    storage_root_id,
                    f"stonks/tech-indicators/tests/{marker}",
                    filename,
                    content_type,
                    object_kind,
                    checksum,
                ),
            )
            object_ids.append(cursor.fetchone()[0])
        prepare_daily_candidate(
            cursor=cursor,
            publication_id=publication_id,
            expected_listing_count=1,
            expected_source_row_count=1,
            expected_payload_row_count=1,
            inserted_row_count=1,
            updated_row_count=0,
            deleted_row_count=0,
            equivalent_row_count=0,
            warning_count=0,
            failure_count=0,
            json_report_object_id=object_ids[0],
            pdf_report_object_id=object_ids[1],
        )
        connection.commit()
        cursor.execute(
            "SELECT status, expected_listing_count, inserted_row_count, "
            "completed_batch_count, staged_payload_row_count "
            "FROM stonks.tech_indicators_publication WHERE publication_id = %s",
            (publication_id,),
        )
        assert cursor.fetchone() == ("PREPARED", 1, 1, 0, 0)
    finally:
        connection.rollback()
        if publication_id is not None:
            cursor.execute(
                "DELETE FROM stonks.tech_indicators_publication_listing "
                "WHERE publication_id = %s",
                (publication_id,),
            )
            cursor.execute(
                "DELETE FROM stonks.tech_indicators_publication "
                "WHERE publication_id = %s",
                (publication_id,),
            )
        if listing_id is not None:
            cursor.execute(
                "DELETE FROM stonks.provider_listing "
                "WHERE provider_listing_id = %s",
                (listing_id,),
            )
        if object_ids:
            cursor.execute(
                "DELETE FROM core.stored_object WHERE object_id = ANY(%s::uuid[])",
                (object_ids,),
            )
        if run_id is not None:
            cursor.execute(
                "DELETE FROM core.core_run WHERE run_id = %s",
                (run_id,),
            )
        connection.commit()
