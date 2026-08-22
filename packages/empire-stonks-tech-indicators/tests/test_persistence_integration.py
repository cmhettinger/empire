from __future__ import annotations

import os
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterator
from uuid import UUID, uuid4

import pytest

from empire_stonks_tech_indicators import (
    FeatureRow,
    FeatureRowKey,
    SlotWriteCounts,
    SourceBar,
    TechIndicatorsScope,
    TechIndicatorsPayloadSlot,
    copy_feature_rows_between_slots,
    iter_state_comparison_pages,
    plan_affected_ranges,
    select_eligible_listings,
    upsert_feature_rows,
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


def _insert_source_bar(cursor: object) -> tuple[UUID, date]:
    ticker = f"W73{uuid4().hex[:12].upper()}"
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.provider_listing (
            provider_code,
            market,
            ticker,
            status
        )
        VALUES ('EODDATA', 'US', %s, 'ACTIVE')
        RETURNING provider_listing_id
        """,
        (ticker,),
    )
    provider_listing_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    trading_date = date(2026, 8, 21)
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
        VALUES (%s, %s, 10, 12, 9, 11, 100, NULL, NULL, 10.66666667, 3, 1)
        """,
        (provider_listing_id, trading_date),
    )
    return provider_listing_id, trading_date


def _row(
    *,
    provider_listing_id: UUID,
    trading_date: date,
    calculated_at: datetime,
    return_1d_pct: float | None,
) -> FeatureRow:
    return FeatureRow(
        source=SourceBar(
            provider_listing_id=provider_listing_id,
            trading_date=trading_date,
            open=Decimal("10"),
            high=Decimal("12"),
            low=Decimal("9"),
            close=Decimal("11"),
            volume=Decimal("100"),
        ),
        history_observation_count=1,
        calculation_version="TECH_INDICATORS_V1",
        calculated_at=calculated_at,
        return_1d_pct=return_1d_pct,
    )


def test_slot_upsert_and_exact_copy_against_postgresql(
    database_connection: object,
) -> None:
    cursor = database_connection.cursor()  # type: ignore[union-attr]
    provider_listing_id, trading_date = _insert_source_bar(cursor)
    first_calculated_at = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    first = _row(
        provider_listing_id=provider_listing_id,
        trading_date=trading_date,
        calculated_at=first_calculated_at,
        return_1d_pct=0.25,
    )

    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=(first,),
    ) == SlotWriteCounts(inserted_rows=1)
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT calculated_at, created_at, updated_at, intraday_return_1d_pct
        FROM stonks.ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id = %s AND trading_date = %s
        """,
        (provider_listing_id, trading_date),
    )
    stored_calculated_at, created_at, inserted_updated_at, intraday_return = (
        cursor.fetchone()  # type: ignore[union-attr]
    )
    assert stored_calculated_at == first_calculated_at
    assert intraday_return == pytest.approx(0.1)

    equivalent = _row(
        provider_listing_id=provider_listing_id,
        trading_date=trading_date,
        calculated_at=first_calculated_at + timedelta(hours=1),
        return_1d_pct=0.25 + 5e-13,
    )
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=(equivalent,),
    ) == SlotWriteCounts(unchanged_rows=1)
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT calculated_at, created_at, updated_at, return_1d_pct
        FROM stonks.ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id = %s AND trading_date = %s
        """,
        (provider_listing_id, trading_date),
    )
    assert cursor.fetchone() == (  # type: ignore[union-attr]
        stored_calculated_at,
        created_at,
        inserted_updated_at,
        0.25,
    )

    changed_calculated_at = first_calculated_at + timedelta(hours=2)
    changed = _row(
        provider_listing_id=provider_listing_id,
        trading_date=trading_date,
        calculated_at=changed_calculated_at,
        return_1d_pct=0.5,
    )
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=(changed,),
    ) == SlotWriteCounts(updated_rows=1)
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT calculated_at, created_at, updated_at, return_1d_pct
        FROM stonks.ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id = %s AND trading_date = %s
        """,
        (provider_listing_id, trading_date),
    )
    assert cursor.fetchone() == (  # type: ignore[union-attr]
        changed_calculated_at,
        created_at,
        changed_calculated_at,
        0.5,
    )

    key = FeatureRowKey(provider_listing_id, trading_date)
    assert copy_feature_rows_between_slots(
        cursor=cursor,
        source_slot=TechIndicatorsPayloadSlot.A,
        target_slot=TechIndicatorsPayloadSlot.B,
        keys=(key,),
    ) == SlotWriteCounts(unchanged_rows=1)
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT calculated_at, created_at, updated_at, return_1d_pct
        FROM stonks.ohlcv_daily_tech_indicators_b
        WHERE provider_listing_id = %s AND trading_date = %s
        """,
        (provider_listing_id, trading_date),
    )
    assert cursor.fetchone() == (  # type: ignore[union-attr]
        changed_calculated_at,
        created_at,
        changed_calculated_at,
        0.5,
    )
    assert copy_feature_rows_between_slots(
        cursor=cursor,
        source_slot=TechIndicatorsPayloadSlot.A,
        target_slot=TechIndicatorsPayloadSlot.B,
        keys=(key,),
    ) == SlotWriteCounts(unchanged_rows=1)


def _insert_listing(
    cursor: object,
    *,
    provider_code: str,
    market: str,
    ticker: str,
    metadata_json: str,
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
        VALUES (%s, %s, %s, 'ACTIVE', %s::jsonb)
        RETURNING provider_listing_id
        """,
        (provider_code, market, ticker, metadata_json),
    )
    return cursor.fetchone()[0]  # type: ignore[union-attr,no-any-return]


def _insert_exact_source_bar(cursor: object, source: SourceBar) -> None:
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
            %s, %s, %s, %s, %s, %s, %s, NULL, NULL,
            round((%s + %s + %s) / 3, 8),
            round(%s - %s, 8),
            round(%s - %s, 8)
        )
        """,
        (
            source.provider_listing_id,
            source.trading_date,
            source.open,
            source.high,
            source.low,
            source.close,
            source.volume,
            source.high,
            source.low,
            source.close,
            source.high,
            source.low,
            source.close,
            source.open,
        ),
    )


def _feature_rows(
    sources: tuple[SourceBar, SourceBar],
    *,
    calculated_at: datetime,
    benchmark_id: UUID | None,
    relative_offset: float = 0.0,
) -> tuple[FeatureRow, FeatureRow]:
    first, second = sources
    second_return = float(second.close / first.close - 1)
    relative_values = (1.0 + relative_offset, 1.1 + relative_offset)
    return (
        FeatureRow(
            source=first,
            history_observation_count=1,
            calculation_version="TECH_INDICATORS_V1",
            calculated_at=calculated_at,
            relative_strength_benchmark_provider_listing_id=benchmark_id,
            rel_spx=None if benchmark_id is None else relative_values[0],
        ),
        FeatureRow(
            source=second,
            history_observation_count=2,
            calculation_version="TECH_INDICATORS_V1",
            calculated_at=calculated_at,
            relative_strength_benchmark_provider_listing_id=benchmark_id,
            return_1d_pct=second_return,
            rel_spx=None if benchmark_id is None else relative_values[1],
        ),
    )


def _publish_active_slots(
    cursor: object,
    *,
    marker: str,
    benchmark_id: UUID,
    first_date: date,
    second_date: date,
    memberships: tuple[tuple[UUID, str, UUID | None], ...],
) -> None:
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO core.core_run (
            domain,
            job_name,
            subject_key,
            run_type,
            status,
            runner
        )
        VALUES (
            'stonks',
            'stonks_tech_indicators_backfill',
            %s,
            'manual',
            'succeeded',
            'pytest'
        )
        RETURNING run_id
        """,
        (f"w78:{marker}",),
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
    for filename, logical_name, content_type, object_kind, checksum in (
        (
            "report.json",
            "tech_indicators_backfill_report",
            "application/json",
            "stonks_tech_indicators_report",
            "c" * 64,
        ),
        (
            "report.pdf",
            "tech_indicators_backfill_pdf_report",
            "application/pdf",
            "stonks_tech_indicators_pdf_report",
            "d" * 64,
        ),
    ):
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
            VALUES (
                %s, %s, %s, %s, 'run', 'stonks', %s, %s, %s,
                1, %s, '{}'::jsonb
            )
            RETURNING object_id
            """,
            (
                run_id,
                storage_root_id,
                f"stonks/tech-indicators/tests/{marker}",
                filename,
                logical_name,
                content_type,
                object_kind,
                checksum,
            ),
        )
        object_ids.append(cursor.fetchone()[0])  # type: ignore[union-attr]
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.tech_indicators_publication (
            publication_kind,
            status,
            calculation_version
        )
        VALUES ('BACKFILL', 'BUILDING', 'TECH_INDICATORS_V1')
        RETURNING publication_id
        """
    )
    publication_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.tech_indicators_publication
        SET
            publication_method = 'STAGED',
            scope_schema_version = 1,
            scope_hash = repeat('c', 64),
            run_id = %s,
            benchmark_required = true,
            benchmark_provider_listing_id = %s,
            benchmark_contract_version = 'TECH_INDICATORS_SPX_V1',
            benchmark_coverage_start_date = %s,
            benchmark_coverage_end_date = %s,
            benchmark_source_row_count = 2,
            expected_listing_count = %s,
            expected_source_row_count = %s,
            expected_payload_row_count = %s,
            inserted_row_count = %s,
            updated_row_count = 0,
            deleted_row_count = 0,
            equivalent_row_count = 0,
            warning_count = 0,
            failure_count = 0,
            completed_batch_count = 0,
            staged_payload_row_count = 0,
            json_report_object_id = %s,
            pdf_report_object_id = %s,
            source_validated_at = now(),
            prepared_at = now(),
            status = 'PREPARED',
            updated_at = now()
        WHERE publication_id = %s
        """,
        (
            run_id,
            benchmark_id,
            first_date,
            second_date,
            len(memberships),
            len(memberships) * 2,
            len(memberships) * 2,
            len(memberships) * 2,
            object_ids[0],
            object_ids[1],
            publication_id,
        ),
    )
    for listing_id, target_slot, membership_benchmark_id in memberships:
        cursor.execute(  # type: ignore[union-attr]
            """
            INSERT INTO stonks.tech_indicators_publication_listing (
                publication_id,
                provider_listing_id,
                action,
                target_slot,
                calculation_version,
                source_coverage_start_date,
                source_coverage_end_date,
                source_row_count,
                payload_row_count,
                benchmark_provider_listing_id,
                candidate_completed_at
            )
            VALUES (
                %s, %s, 'PRESENT', %s, 'TECH_INDICATORS_V1',
                %s, %s, 2, 2, %s, now()
            )
            """,
            (
                publication_id,
                listing_id,
                target_slot,
                first_date,
                second_date,
                membership_benchmark_id,
            ),
        )
    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.tech_indicators_publication
        SET status = 'PUBLISHED', published_at = now(), updated_at = now()
        WHERE publication_id = %s
        """,
        (publication_id,),
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.tech_indicators_publication_listing
        SET is_active = true, activated_at = now(), updated_at = now()
        WHERE publication_id = %s
        """,
        (publication_id,),
    )


def _published_rows(
    cursor: object,
    listing_ids: tuple[UUID, ...],
) -> dict[tuple[UUID, date], tuple[object, ...]]:
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT
            provider_listing_id,
            trading_date,
            return_1d_pct,
            relative_strength_benchmark_provider_listing_id,
            rel_spx,
            dollar_volume,
            intraday_return_1d_pct,
            daily_range_pct,
            close_location_1d
        FROM stonks.ohlcv_daily_tech_indicators
        WHERE provider_listing_id = ANY(%s::uuid[])
        ORDER BY provider_listing_id, trading_date
        """,
        (list(listing_ids),),
    )
    return {
        (row[0], row[1]): row[2:]
        for row in cursor.fetchall()  # type: ignore[union-attr]
    }


def test_phase_7_postgresql_vertical_converges_without_cross_series_leakage(
    database_connection: object,
) -> None:
    marker = uuid4().hex[:12].upper()
    first_date = date(2098, 1, 6)
    second_date = date(2098, 1, 7)
    calculated_at = datetime(2026, 8, 22, 14, tzinfo=timezone.utc)
    cursor = database_connection.cursor()  # type: ignore[union-attr]
    eoddata_id = _insert_listing(
        cursor,
        provider_code="EODDATA",
        market="NASDAQ",
        ticker=f"W78{marker}",
        metadata_json='{"type": "Equity"}',
    )
    stooq_id = _insert_listing(
        cursor,
        provider_code="STOOQ",
        market="nasdaq",
        ticker=f"W78{marker}.US",
        metadata_json="{}",
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT provider_listing_id
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker = 'SPX'
          AND status = 'ACTIVE'
        """
    )
    benchmark_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    sources_by_listing = {
        eoddata_id: (
            SourceBar(
                eoddata_id,
                first_date,
                Decimal("10"),
                Decimal("12"),
                Decimal("8"),
                Decimal("11"),
                Decimal("100"),
            ),
            SourceBar(
                eoddata_id,
                second_date,
                Decimal("11"),
                Decimal("14"),
                Decimal("10"),
                Decimal("13"),
                Decimal("120"),
            ),
        ),
        stooq_id: (
            SourceBar(
                stooq_id,
                first_date,
                Decimal("20"),
                Decimal("22"),
                Decimal("18"),
                Decimal("21"),
                Decimal("50"),
            ),
            SourceBar(
                stooq_id,
                second_date,
                Decimal("21"),
                Decimal("24"),
                Decimal("20"),
                Decimal("23"),
                Decimal("60"),
            ),
        ),
        benchmark_id: (
            SourceBar(
                benchmark_id,
                first_date,
                Decimal("100"),
                Decimal("104"),
                Decimal("98"),
                Decimal("102"),
                None,
            ),
            SourceBar(
                benchmark_id,
                second_date,
                Decimal("102"),
                Decimal("106"),
                Decimal("100"),
                Decimal("104"),
                None,
            ),
        ),
    }
    for sources in sources_by_listing.values():
        for source in sources:
            _insert_exact_source_bar(cursor, source)

    eoddata_rows = _feature_rows(
        sources_by_listing[eoddata_id],
        calculated_at=calculated_at,
        benchmark_id=benchmark_id,
    )
    stooq_rows = _feature_rows(
        sources_by_listing[stooq_id],
        calculated_at=calculated_at,
        benchmark_id=benchmark_id,
    )
    benchmark_rows = _feature_rows(
        sources_by_listing[benchmark_id],
        calculated_at=calculated_at,
        benchmark_id=None,
    )
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=eoddata_rows + benchmark_rows,
    ) == SlotWriteCounts(inserted_rows=4)
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.B,
        rows=stooq_rows,
    ) == SlotWriteCounts(inserted_rows=2)
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.B,
        rows=tuple(replace(row, rel_spx=9.0) for row in eoddata_rows),
    ) == SlotWriteCounts(inserted_rows=2)
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=tuple(replace(row, rel_spx=8.0) for row in stooq_rows),
    ) == SlotWriteCounts(inserted_rows=2)
    _publish_active_slots(
        cursor,
        marker=marker,
        benchmark_id=benchmark_id,
        first_date=first_date,
        second_date=second_date,
        memberships=(
            (eoddata_id, "A", benchmark_id),
            (stooq_id, "B", benchmark_id),
            (benchmark_id, "A", None),
        ),
    )

    listing_ids = (eoddata_id, stooq_id, benchmark_id)
    published = _published_rows(cursor, listing_ids)
    assert len(published) == 6
    assert published[eoddata_id, second_date][0] == pytest.approx(2 / 11)
    assert published[stooq_id, second_date][0] == pytest.approx(2 / 21)
    assert published[eoddata_id, second_date][2] == pytest.approx(1.1)
    assert published[stooq_id, second_date][2] == pytest.approx(1.1)
    assert published[eoddata_id, first_date][3:] == pytest.approx(
        (1100.0, 0.1, 4 / 11, 0.75)
    )
    assert published[benchmark_id, first_date][1:3] == (None, None)
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=eoddata_rows,
    ) == SlotWriteCounts(unchanged_rows=2)

    cursor.execute("SAVEPOINT w78_active_write")  # type: ignore[union-attr]
    transient_rows = tuple(
        replace(
            row,
            calculated_at=calculated_at + timedelta(hours=1),
            rel_spx=0.777,
        )
        for row in eoddata_rows
    )
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=transient_rows,
    ) == SlotWriteCounts(updated_rows=2)
    assert _published_rows(cursor, listing_ids)[eoddata_id, second_date][
        2
    ] == pytest.approx(0.777)
    cursor.execute(  # type: ignore[union-attr]
        "ROLLBACK TO SAVEPOINT w78_active_write"
    )
    assert _published_rows(cursor, listing_ids)[eoddata_id, second_date][
        2
    ] == pytest.approx(1.1)

    corrected_eoddata_sources = (
        replace(sources_by_listing[eoddata_id][0], close=Decimal("10.5")),
        sources_by_listing[eoddata_id][1],
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.ohlcv_daily
        SET
            close = %s,
            typ = round((high + low + %s) / 3, 8),
            oc_range = round(%s - open, 8),
            updated_at = now()
        WHERE provider_listing_id = %s AND trading_date = %s
        """,
        (
            corrected_eoddata_sources[0].close,
            corrected_eoddata_sources[0].close,
            corrected_eoddata_sources[0].close,
            eoddata_id,
            first_date,
        ),
    )
    scope = TechIndicatorsScope(
        provider_listing_ids=(eoddata_id, stooq_id),
        start_date=first_date,
        end_date=second_date,
    )
    listings = select_eligible_listings(cursor=cursor, scope=scope)
    comparisons = tuple(
        item
        for page in iter_state_comparison_pages(
            cursor=cursor,
            scope=scope,
            calculation_version="TECH_INDICATORS_V1",
        )
        for item in page
    )
    comparison_by_id = {item.provider_listing_id: item for item in comparisons}
    assert comparison_by_id[eoddata_id].earliest_source_copy_drift_date == (
        first_date
    )
    assert comparison_by_id[stooq_id].is_equivalent is True
    source_plan = plan_affected_ranges(
        listings=listings,
        comparisons=comparisons,
        requested_end_date=second_date,
    )
    assert [
        (item.provider_listing_id, item.write_start_date)
        for item in source_plan.ranges
    ] == [(eoddata_id, first_date)]
    corrected_eoddata_rows = _feature_rows(
        corrected_eoddata_sources,
        calculated_at=calculated_at + timedelta(hours=2),
        benchmark_id=benchmark_id,
    )
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=corrected_eoddata_rows,
    ) == SlotWriteCounts(updated_rows=2)
    published = _published_rows(cursor, listing_ids)
    assert published[eoddata_id, second_date][0] == pytest.approx(13 / 10.5 - 1)
    assert published[stooq_id, second_date][0] == pytest.approx(2 / 21)
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=corrected_eoddata_rows,
    ) == SlotWriteCounts(unchanged_rows=2)

    comparisons = tuple(
        item
        for page in iter_state_comparison_pages(
            cursor=cursor,
            scope=scope,
            calculation_version="TECH_INDICATORS_V1",
        )
        for item in page
    )
    corrected_benchmark_sources = (
        replace(sources_by_listing[benchmark_id][0], close=Decimal("101")),
        sources_by_listing[benchmark_id][1],
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.ohlcv_daily
        SET
            close = %s,
            typ = round((high + low + %s) / 3, 8),
            oc_range = round(%s - open, 8),
            updated_at = now()
        WHERE provider_listing_id = %s AND trading_date = %s
        """,
        (
            corrected_benchmark_sources[0].close,
            corrected_benchmark_sources[0].close,
            corrected_benchmark_sources[0].close,
            benchmark_id,
            first_date,
        ),
    )
    corrected_benchmark_rows = _feature_rows(
        corrected_benchmark_sources,
        calculated_at=calculated_at + timedelta(hours=3),
        benchmark_id=None,
    )
    assert all(item.is_equivalent for item in comparisons)
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=corrected_benchmark_rows,
    ) == SlotWriteCounts(updated_rows=2)
    benchmark_plan = plan_affected_ranges(
        listings=listings,
        comparisons=comparisons,
        requested_end_date=second_date,
        benchmark_drift_start_date=first_date,
    )
    assert {
        (item.provider_listing_id, item.write_start_date)
        for item in benchmark_plan.ranges
    } == {(eoddata_id, first_date), (stooq_id, first_date)}
    benchmark_corrected_eoddata_rows = tuple(
        replace(row, rel_spx=(row.rel_spx or 0.0) + 0.01)
        for row in corrected_eoddata_rows
    )
    benchmark_corrected_stooq_rows = tuple(
        replace(row, rel_spx=(row.rel_spx or 0.0) + 0.01)
        for row in stooq_rows
    )
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=benchmark_corrected_eoddata_rows,
    ) == SlotWriteCounts(updated_rows=2)
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.B,
        rows=benchmark_corrected_stooq_rows,
    ) == SlotWriteCounts(updated_rows=2)
    published = _published_rows(cursor, listing_ids)
    assert published[eoddata_id, second_date][0] == pytest.approx(13 / 10.5 - 1)
    assert published[eoddata_id, second_date][1] == benchmark_id
    assert published[eoddata_id, second_date][2] == pytest.approx(1.11)
    assert published[stooq_id, second_date][0] == pytest.approx(2 / 21)
    assert published[stooq_id, second_date][1] == benchmark_id
    assert published[stooq_id, second_date][2] == pytest.approx(1.11)
    assert published[benchmark_id, second_date][1:3] == (None, None)
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=benchmark_corrected_eoddata_rows,
    ) == SlotWriteCounts(unchanged_rows=2)
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.B,
        rows=benchmark_corrected_stooq_rows,
    ) == SlotWriteCounts(unchanged_rows=2)
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=corrected_benchmark_rows,
    ) == SlotWriteCounts(unchanged_rows=2)
