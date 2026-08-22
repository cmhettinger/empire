from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterator
from uuid import UUID, uuid4

import pytest

from empire_stonks_tech_indicators import (
    InPlaceSlotChanges,
    PublicationRecoveryAction,
    SourceBar,
    TechIndicatorsPayloadSlot,
    TechIndicatorsWorkflowError,
    fail_unpublished_publication,
    finalize_publication,
    inspect_publication_recovery,
    select_inactive_payload_slots,
    upsert_feature_rows,
)
from empire_stonks_tech_indicators.models import FeatureRow
from empire_stonks_tech_indicators.publication import (
    TECH_INDICATORS_WRITER_LOCK_KEY,
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


def _listing_and_source(
    cursor: object, *, market: str = "NASDAQ"
) -> tuple[UUID, date]:
    marker = uuid4().hex[:12].upper()
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.provider_listing (
            provider_code, market, ticker, status, metadata
        )
        VALUES ('EODDATA', %s, %s, 'ACTIVE', '{"type": "Equity"}')
        RETURNING provider_listing_id
        """,
        (market, f"W710{marker}"),
    )
    listing_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    trading_date = date(2097, 8, 22)
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.ohlcv_daily (
            provider_listing_id, trading_date, open, high, low, close, volume,
            change, changepct, typ, hl_range, oc_range
        )
        VALUES (%s, %s, 10, 12, 9, 11, 100, NULL, NULL, 10.66666667, 3, 1)
        """,
        (listing_id, trading_date),
    )
    return listing_id, trading_date


def _benchmark_facts(cursor: object) -> tuple[UUID, date, date, int]:
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT listing.provider_listing_id, min(daily.trading_date),
               max(daily.trading_date), count(daily.trading_date)::integer
        FROM stonks.provider_listing AS listing
        JOIN stonks.ohlcv_daily AS daily
          ON daily.provider_listing_id = listing.provider_listing_id
        WHERE listing.provider_code = 'YAHOO'
          AND listing.market = 'XIDX'
          AND listing.ticker = 'SPX'
          AND listing.status = 'ACTIVE'
          AND listing.instrument_type_code = 'EQUITY_INDEX'
          AND listing.metadata ->> 'YahooTicker' = '^GSPC'
        GROUP BY listing.provider_listing_id
        """
    )
    row = cursor.fetchone()  # type: ignore[union-attr]
    assert row is not None
    return row


def _feature_row(
    listing_id: UUID,
    trading_date: date,
    value: float,
    *,
    benchmark_id: UUID | None = None,
) -> FeatureRow:
    return FeatureRow(
        source=SourceBar(
            provider_listing_id=listing_id,
            trading_date=trading_date,
            open=Decimal("10"),
            high=Decimal("12"),
            low=Decimal("9"),
            close=Decimal("11"),
            volume=Decimal("100"),
        ),
        history_observation_count=1,
        calculation_version="TECH_INDICATORS_V1",
        calculated_at=datetime.now(timezone.utc),
        relative_strength_benchmark_provider_listing_id=benchmark_id,
        return_1d_pct=value,
    )


def _core_evidence(cursor: object, marker: str, status: str) -> tuple[UUID, UUID, UUID]:
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO core.core_run (
            domain, job_name, subject_key, run_type, status, runner, completed_at
        )
        VALUES (
            'stonks', 'stonks_tech_indicators_backfill', %s, 'manual', %s,
            'pytest', CASE WHEN %s = 'started' THEN NULL ELSE now() END
        )
        RETURNING run_id
        """,
        (marker, status, status),
    )
    run_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT storage_root_id
        FROM core.storage_root
        WHERE root_name = 'global' AND is_active
        """
    )
    storage_root_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    object_ids: list[UUID] = []
    for filename, content_type, object_kind, checksum in (
        (
            "report.json",
            "application/json",
            "stonks_tech_indicators_report",
            "a" * 64,
        ),
        (
            "report.pdf",
            "application/pdf",
            "stonks_tech_indicators_pdf_report",
            "b" * 64,
        ),
    ):
        cursor.execute(  # type: ignore[union-attr]
            """
            INSERT INTO core.stored_object (
                run_id, storage_root_id, object_key, filename, object_scope,
                domain, content_type, object_kind, size_bytes,
                checksum_sha256, metadata
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
        object_ids.append(cursor.fetchone()[0])  # type: ignore[union-attr]
    return run_id, object_ids[0], object_ids[1]


def _publication(
    cursor: object,
    *,
    listing_id: UUID,
    trading_date: date,
    slot: str,
    scope_hash: str,
    run_status: str = "succeeded",
    publication_kind: str = "BACKFILL",
    publication_method: str = "STAGED",
    inserted_rows: int = 1,
    updated_rows: int = 0,
    equivalent_rows: int = 0,
    benchmark_facts: tuple[UUID, date, date, int] | None = None,
) -> UUID:
    run_id, json_id, pdf_id = _core_evidence(cursor, scope_hash[:12], run_status)
    benchmark_id = None if benchmark_facts is None else benchmark_facts[0]
    benchmark_start = None if benchmark_facts is None else benchmark_facts[1]
    benchmark_end = None if benchmark_facts is None else benchmark_facts[2]
    benchmark_count = None if benchmark_facts is None else benchmark_facts[3]
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.tech_indicators_publication (
            publication_kind, status, calculation_version
        )
        VALUES (%s, 'BUILDING', 'TECH_INDICATORS_V1')
        RETURNING publication_id
        """,
        (publication_kind,),
    )
    publication_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.tech_indicators_publication
        SET publication_method = %s, scope_schema_version = 1,
            scope_hash = %s, run_id = %s, benchmark_required = %s,
            benchmark_provider_listing_id = %s,
            benchmark_contract_version = %s,
            benchmark_coverage_start_date = %s,
            benchmark_coverage_end_date = %s,
            benchmark_source_row_count = %s,
            expected_listing_count = 1, expected_source_row_count = 1,
            expected_payload_row_count = 1, inserted_row_count = %s,
            updated_row_count = %s, deleted_row_count = 0,
            equivalent_row_count = %s, warning_count = 0, failure_count = 0,
            completed_batch_count = CASE WHEN %s = 'STAGED' THEN 1 ELSE 0 END,
            staged_payload_row_count = CASE WHEN %s = 'STAGED' THEN 1 ELSE 0 END,
            resume_provider_listing_id = CASE WHEN %s = 'STAGED' THEN %s END,
            resume_trading_date = CASE WHEN %s = 'STAGED' THEN %s END,
            resume_cursor_updated_at = CASE WHEN %s = 'STAGED' THEN now() END,
            json_report_object_id = %s,
            pdf_report_object_id = %s, source_validated_at = now(),
            prepared_at = now(), status = 'PREPARED', updated_at = now()
        WHERE publication_id = %s
        """,
        (
            publication_method,
            scope_hash,
            run_id,
            benchmark_facts is not None,
            benchmark_id,
            "TECH_INDICATORS_SPX_V1" if benchmark_facts is not None else None,
            benchmark_start,
            benchmark_end,
            benchmark_count,
            inserted_rows,
            updated_rows,
            equivalent_rows,
            publication_method,
            publication_method,
            publication_method,
            listing_id,
            publication_method,
            trading_date,
            publication_method,
            json_id,
            pdf_id,
            publication_id,
        ),
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.tech_indicators_publication_listing (
            publication_id, provider_listing_id, action, target_slot,
            calculation_version, source_coverage_start_date,
            source_coverage_end_date, source_row_count, payload_row_count,
            benchmark_provider_listing_id, candidate_completed_at
        )
        VALUES (
            %s, %s, 'PRESENT', %s, 'TECH_INDICATORS_V1', %s, %s, 1, 1,
            %s, now()
        )
        """,
        (
            publication_id,
            listing_id,
            slot,
            trading_date,
            trading_date,
            benchmark_id,
        ),
    )
    return publication_id


def _view_value(cursor: object, listing_id: UUID) -> float | None:
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT return_1d_pct
        FROM stonks.ohlcv_daily_tech_indicators
        WHERE provider_listing_id = %s
        """,
        (listing_id,),
    )
    row = cursor.fetchone()  # type: ignore[union-attr]
    return None if row is None else row[0]


def test_staged_finalizer_flips_one_complete_membership_unit(
    database_connection: object,
) -> None:
    cursor = database_connection.cursor()  # type: ignore[union-attr]
    listing_id, trading_date = _listing_and_source(cursor)
    benchmark = _benchmark_facts(cursor)
    selection = select_inactive_payload_slots(
        cursor=cursor,
        provider_listing_ids=(listing_id,),
    )
    assert selection[0].active_slot is None
    assert selection[0].target_slot is TechIndicatorsPayloadSlot.A
    upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=(
            _feature_row(
                listing_id,
                trading_date,
                0.2,
                benchmark_id=benchmark[0],
            ),
        ),
    )
    publication_id = _publication(
        cursor,
        listing_id=listing_id,
        trading_date=trading_date,
        slot="A",
        scope_hash="a" * 64,
        benchmark_facts=benchmark,
    )
    assert _view_value(cursor, listing_id) is None
    cursor.execute(  # type: ignore[union-attr]
        "SELECT pg_try_advisory_xact_lock(%s::bigint)",
        (TECH_INDICATORS_WRITER_LOCK_KEY,),
    )
    assert cursor.fetchone() == (True,)  # type: ignore[union-attr]

    result = finalize_publication(
        cursor=cursor,
        publication_id=publication_id,
        scope_hash="a" * 64,
        calculation_version="TECH_INDICATORS_V1",
        provider_listing_ids=(listing_id,),
    )

    assert result.published
    assert not result.already_published
    assert _view_value(cursor, listing_id) == pytest.approx(0.2)
    repeated = finalize_publication(
        cursor=cursor,
        publication_id=publication_id,
        scope_hash="a" * 64,
        calculation_version="TECH_INDICATORS_V1",
        provider_listing_ids=(listing_id,),
    )
    assert repeated.already_published


def test_in_place_finalizer_mutates_payload_and_membership_atomically(
    database_connection: object,
) -> None:
    cursor = database_connection.cursor()  # type: ignore[union-attr]
    listing_id, trading_date = _listing_and_source(cursor)
    benchmark = _benchmark_facts(cursor)
    upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=(
            _feature_row(
                listing_id,
                trading_date,
                0.1,
                benchmark_id=benchmark[0],
            ),
        ),
    )
    old_id = _publication(
        cursor,
        listing_id=listing_id,
        trading_date=trading_date,
        slot="A",
        scope_hash="e" * 64,
        benchmark_facts=benchmark,
    )
    cursor.execute(  # type: ignore[union-attr]
        "SELECT pg_try_advisory_xact_lock(%s::bigint)",
        (TECH_INDICATORS_WRITER_LOCK_KEY,),
    )
    finalize_publication(
        cursor=cursor,
        publication_id=old_id,
        scope_hash="e" * 64,
        calculation_version="TECH_INDICATORS_V1",
        provider_listing_ids=(listing_id,),
    )

    candidate_id = _publication(
        cursor,
        listing_id=listing_id,
        trading_date=trading_date,
        slot="A",
        scope_hash="f" * 64,
        publication_kind="DAILY",
        publication_method="IN_PLACE",
        inserted_rows=0,
        updated_rows=1,
        benchmark_facts=benchmark,
    )
    assert _view_value(cursor, listing_id) == pytest.approx(0.1)
    result = finalize_publication(
        cursor=cursor,
        publication_id=candidate_id,
        scope_hash="f" * 64,
        calculation_version="TECH_INDICATORS_V1",
        provider_listing_ids=(listing_id,),
        in_place_changes=(
            InPlaceSlotChanges(
                slot=TechIndicatorsPayloadSlot.A,
                rows=(
                    _feature_row(
                        listing_id,
                        trading_date,
                        0.4,
                        benchmark_id=benchmark[0],
                    ),
                ),
            ),
        ),
    )
    assert result.updated_row_count == 1
    assert _view_value(cursor, listing_id) == pytest.approx(0.4)


def test_incomplete_supported_subject_benchmark_cannot_publish(
    database_connection: object,
) -> None:
    cursor = database_connection.cursor()  # type: ignore[union-attr]
    listing_id, trading_date = _listing_and_source(cursor, market="NASDAQ")
    upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.B,
        rows=(_feature_row(listing_id, trading_date, 0.2),),
    )
    publication_id = _publication(
        cursor,
        listing_id=listing_id,
        trading_date=trading_date,
        slot="B",
        scope_hash="0" * 64,
    )
    with pytest.raises(TechIndicatorsWorkflowError, match="writer lock"):
        finalize_publication(
            cursor=cursor,
            publication_id=publication_id,
            scope_hash="0" * 64,
            calculation_version="TECH_INDICATORS_V1",
            provider_listing_ids=(listing_id,),
        )
    cursor.execute(  # type: ignore[union-attr]
        "SELECT pg_try_advisory_xact_lock(%s::bigint)",
        (TECH_INDICATORS_WRITER_LOCK_KEY,),
    )
    with pytest.raises(TechIndicatorsWorkflowError, match="benchmark requirement"):
        finalize_publication(
            cursor=cursor,
            publication_id=publication_id,
            scope_hash="0" * 64,
            calculation_version="TECH_INDICATORS_V1",
            provider_listing_ids=(listing_id,),
        )
    assert _view_value(cursor, listing_id) is None


def test_cancelled_or_incomplete_candidate_never_replaces_published_rows(
    database_connection: object,
) -> None:
    cursor = database_connection.cursor()  # type: ignore[union-attr]
    listing_id, trading_date = _listing_and_source(cursor)
    benchmark = _benchmark_facts(cursor)
    upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=(
            _feature_row(
                listing_id,
                trading_date,
                0.1,
                benchmark_id=benchmark[0],
            ),
        ),
    )
    old_id = _publication(
        cursor,
        listing_id=listing_id,
        trading_date=trading_date,
        slot="A",
        scope_hash="b" * 64,
        benchmark_facts=benchmark,
    )
    cursor.execute(  # type: ignore[union-attr]
        "SELECT pg_try_advisory_xact_lock(%s::bigint)",
        (TECH_INDICATORS_WRITER_LOCK_KEY,),
    )
    finalize_publication(
        cursor=cursor,
        publication_id=old_id,
        scope_hash="b" * 64,
        calculation_version="TECH_INDICATORS_V1",
        provider_listing_ids=(listing_id,),
    )
    assert _view_value(cursor, listing_id) == pytest.approx(0.1)

    upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.B,
        rows=(
            _feature_row(
                listing_id,
                trading_date,
                0.9,
                benchmark_id=benchmark[0],
            ),
        ),
    )
    cancelled_id = _publication(
        cursor,
        listing_id=listing_id,
        trading_date=trading_date,
        slot="B",
        scope_hash="c" * 64,
        run_status="cancelled",
        benchmark_facts=benchmark,
    )
    decision = inspect_publication_recovery(
        cursor=cursor,
        publication_id=cancelled_id,
        scope_hash="c" * 64,
        calculation_version="TECH_INDICATORS_V1",
    )
    assert decision.action is PublicationRecoveryAction.TERMINAL_FAILURE
    with pytest.raises(TechIndicatorsWorkflowError, match="Core run"):
        finalize_publication(
            cursor=cursor,
            publication_id=cancelled_id,
            scope_hash="c" * 64,
            calculation_version="TECH_INDICATORS_V1",
            provider_listing_ids=(listing_id,),
        )
    assert _view_value(cursor, listing_id) == pytest.approx(0.1)
    fail_unpublished_publication(
        cursor=cursor,
        publication_id=cancelled_id,
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT status, failed_at IS NOT NULL
        FROM stonks.tech_indicators_publication
        WHERE publication_id = %s
        """,
        (cancelled_id,),
    )
    assert cursor.fetchone() == ("FAILED", True)  # type: ignore[union-attr]

    mixed_version_id = _publication(
        cursor,
        listing_id=listing_id,
        trading_date=trading_date,
        slot="B",
        scope_hash="d" * 64,
        benchmark_facts=benchmark,
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.ohlcv_daily_tech_indicators_b
        SET calculation_version = 'TECH_INDICATORS_V2'
        WHERE provider_listing_id = %s
        """,
        (listing_id,),
    )
    with pytest.raises(TechIndicatorsWorkflowError, match="complete current source"):
        finalize_publication(
            cursor=cursor,
            publication_id=mixed_version_id,
            scope_hash="d" * 64,
            calculation_version="TECH_INDICATORS_V1",
            provider_listing_ids=(listing_id,),
        )
    assert _view_value(cursor, listing_id) == pytest.approx(0.1)

    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.ohlcv_daily_tech_indicators_b
        SET calculation_version = 'TECH_INDICATORS_V1'
        WHERE provider_listing_id = %s
        """,
        (listing_id,),
    )
    partial_date_id = _publication(
        cursor,
        listing_id=listing_id,
        trading_date=trading_date,
        slot="B",
        scope_hash="1" * 64,
        benchmark_facts=benchmark,
    )
    next_date = date(2097, 8, 23)
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.ohlcv_daily (
            provider_listing_id, trading_date, open, high, low, close, volume,
            change, changepct, typ, hl_range, oc_range
        )
        VALUES (%s, %s, 11, 13, 10, 12, 110, NULL, NULL, 11.66666667, 3, 1)
        """,
        (listing_id, next_date),
    )
    with pytest.raises(TechIndicatorsWorkflowError, match="complete current source"):
        finalize_publication(
            cursor=cursor,
            publication_id=partial_date_id,
            scope_hash="1" * 64,
            calculation_version="TECH_INDICATORS_V1",
            provider_listing_ids=(listing_id,),
        )
    assert _view_value(cursor, listing_id) == pytest.approx(0.1)


def test_concurrent_reader_observes_old_or_new_complete_publication() -> None:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")
    writer = EmpireDatabase.connect_from_env()
    work = EmpireDatabase.connect_from_env()
    reader = EmpireDatabase.connect_from_env()
    cleanup = EmpireDatabase.connect_from_env()
    listing_id: UUID | None = None
    publication_ids: list[UUID] = []
    try:
        work_cursor = work.cursor()
        listing_id, trading_date = _listing_and_source(work_cursor)
        benchmark = _benchmark_facts(work_cursor)
        scope_a = (uuid4().hex * 2)[:64]
        scope_b = (uuid4().hex * 2)[:64]
        upsert_feature_rows(
            cursor=work_cursor,
            slot=TechIndicatorsPayloadSlot.A,
            rows=(
                _feature_row(
                    listing_id,
                    trading_date,
                    0.1,
                    benchmark_id=benchmark[0],
                ),
            ),
        )
        old_id = _publication(
            work_cursor,
            listing_id=listing_id,
            trading_date=trading_date,
            slot="A",
            scope_hash=scope_a,
            benchmark_facts=benchmark,
        )
        work_cursor.execute(
            "SELECT pg_try_advisory_xact_lock(%s::bigint)",
            (TECH_INDICATORS_WRITER_LOCK_KEY,),
        )
        finalize_publication(
            cursor=work_cursor,
            publication_id=old_id,
            scope_hash=scope_a,
            calculation_version="TECH_INDICATORS_V1",
            provider_listing_ids=(listing_id,),
        )
        work.commit()
        publication_ids.append(old_id)

        writer_cursor = writer.cursor()
        writer_cursor.execute(
            "SELECT pg_try_advisory_xact_lock(%s::bigint)",
            (TECH_INDICATORS_WRITER_LOCK_KEY,),
        )
        assert writer_cursor.fetchone() == (True,)
        selection = select_inactive_payload_slots(
            cursor=work_cursor,
            provider_listing_ids=(listing_id,),
        )
        assert selection[0].active_slot is TechIndicatorsPayloadSlot.A
        assert selection[0].target_slot is TechIndicatorsPayloadSlot.B
        upsert_feature_rows(
            cursor=work_cursor,
            slot=TechIndicatorsPayloadSlot.B,
            rows=(
                _feature_row(
                    listing_id,
                    trading_date,
                    0.8,
                    benchmark_id=benchmark[0],
                ),
            ),
        )
        candidate_id = _publication(
            work_cursor,
            listing_id=listing_id,
            trading_date=trading_date,
            slot="B",
            scope_hash=scope_b,
            benchmark_facts=benchmark,
        )
        work.commit()
        publication_ids.append(candidate_id)

        reader_cursor = reader.cursor()
        reader_cursor.execute(
            "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        )
        assert _view_value(reader_cursor, listing_id) == pytest.approx(0.1)
        finalize_publication(
            cursor=writer_cursor,
            publication_id=candidate_id,
            scope_hash=scope_b,
            calculation_version="TECH_INDICATORS_V1",
            provider_listing_ids=(listing_id,),
        )
        assert _view_value(reader_cursor, listing_id) == pytest.approx(0.1)
        writer.commit()
        assert _view_value(reader_cursor, listing_id) == pytest.approx(0.1)
        reader.rollback()
        assert _view_value(reader_cursor, listing_id) == pytest.approx(0.8)
        writer_cursor.execute(
            "SELECT pg_try_advisory_xact_lock(%s::bigint)",
            (TECH_INDICATORS_WRITER_LOCK_KEY,),
        )
        replay = finalize_publication(
            cursor=writer_cursor,
            publication_id=candidate_id,
            scope_hash=scope_b,
            calculation_version="TECH_INDICATORS_V1",
            provider_listing_ids=(listing_id,),
        )
        assert replay.already_published
        writer.rollback()
    finally:
        for connection in (reader, writer, work):
            try:
                connection.rollback()
            finally:
                connection.close()
        try:
            cleanup_cursor = cleanup.cursor()
            if listing_id is not None:
                cleanup_cursor.execute(
                    """
                    DELETE FROM stonks.provider_listing
                    WHERE provider_listing_id = %s
                    """,
                    (listing_id,),
                )
            if publication_ids:
                cleanup_cursor.execute(
                    """
                    SELECT run_id, json_report_object_id, pdf_report_object_id
                    FROM stonks.tech_indicators_publication
                    WHERE publication_id = ANY(%s::uuid[])
                    """,
                    (publication_ids,),
                )
                evidence = cleanup_cursor.fetchall()
                run_ids = [row[0] for row in evidence if row[0] is not None]
                object_ids = [
                    object_id
                    for row in evidence
                    for object_id in row[1:]
                    if object_id is not None
                ]
                cleanup_cursor.execute(
                    """
                    DELETE FROM stonks.tech_indicators_publication
                    WHERE publication_id = ANY(%s::uuid[])
                    """,
                    (publication_ids,),
                )
                cleanup_cursor.execute(
                    "DELETE FROM core.stored_object WHERE object_id = ANY(%s::uuid[])",
                    (object_ids,),
                )
                cleanup_cursor.execute(
                    "DELETE FROM core.core_run WHERE run_id = ANY(%s::uuid[])",
                    (run_ids,),
                )
            cleanup.commit()
        finally:
            cleanup.close()
