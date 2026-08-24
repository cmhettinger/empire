"""Durable staged-publication state for resumable technical-indicator backfills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

from empire_stonks_tech_indicators.backfill_scope import (
    ResolvedTechIndicatorsBackfillScope,
    TechIndicatorsBackfillCursor,
)
from empire_stonks_tech_indicators.exceptions import TechIndicatorsWorkflowError
from empire_stonks_tech_indicators.persistence import (
    SlotWriteCounts,
    TechIndicatorsPayloadSlot,
)
from empire_stonks_tech_indicators.queries import BenchmarkHistory, EligibleListing
from empire_stonks_tech_indicators.reports import BENCHMARK_CONTRACT_VERSION


@dataclass(frozen=True)
class BackfillPublicationProgress:
    publication_id: UUID
    completed_batch_count: int
    staged_payload_row_count: int
    cursor: TechIndicatorsBackfillCursor | None
    inserted_row_count: int
    updated_row_count: int
    equivalent_row_count: int
    deleted_row_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.publication_id, UUID):
            raise TypeError("publication_id must be a UUID.")
        for name in (
            "completed_batch_count",
            "staged_payload_row_count",
            "inserted_row_count",
            "updated_row_count",
            "equivalent_row_count",
            "deleted_row_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")
        if (self.completed_batch_count == 0) != (self.cursor is None):
            raise ValueError("completed batches and progress cursor do not match.")
        if self.cursor is not None and (
            not isinstance(self.cursor, TechIndicatorsBackfillCursor)
            or self.cursor.batch_number != self.completed_batch_count
        ):
            raise ValueError("progress cursor does not match completed batches.")


def create_or_resume_backfill_candidate(
    *,
    cursor: Any,
    resolved: ResolvedTechIndicatorsBackfillScope,
    run_id: UUID,
    benchmark: BenchmarkHistory | None,
) -> BackfillPublicationProgress:
    """Create a BUILDING candidate or attach a new Core run to its exact cursor."""

    requested = resolved.request.resume_cursor
    cursor.execute(
        """
        SELECT publication_id, effective_date, requested_start_date,
               requested_end_date, calculation_version, completed_batch_count,
               staged_payload_row_count, resume_provider_listing_id,
               resume_trading_date, inserted_row_count, updated_row_count,
               equivalent_row_count, deleted_row_count, benchmark_required,
               benchmark_provider_listing_id, benchmark_coverage_start_date,
               benchmark_coverage_end_date, benchmark_source_row_count
        FROM stonks.tech_indicators_publication
        WHERE publication_kind IN ('BACKFILL', 'VERSION_REBUILD')
          AND publication_method = 'STAGED'
          AND scope_schema_version = 1
          AND scope_hash = %s
          AND status = 'BUILDING'
        ORDER BY created_at
        FOR UPDATE
        """,
        (resolved.scope_hash,),
    )
    rows = cursor.fetchall()
    if requested is None:
        if rows:
            raise TechIndicatorsWorkflowError(
                "An unpublished candidate already exists; resume from its exact cursor."
            )
        return _create_candidate(
            cursor=cursor,
            resolved=resolved,
            run_id=run_id,
            benchmark=benchmark,
        )
    if len(rows) != 1:
        raise TechIndicatorsWorkflowError(
            "Resume requires exactly one matching unpublished candidate."
        )
    row = rows[0]
    observed = TechIndicatorsBackfillCursor(row[7], row[8], row[5])
    if (
        row[1] != resolved.request.effective_date
        or row[2] != resolved.request.start_date
        or row[3] != resolved.request.end_date
        or row[4] != resolved.request.calculation_version
        or observed != requested
        or (row[13], row[14], row[15], row[16], row[17])
        != _benchmark_facts(benchmark)
    ):
        raise TechIndicatorsWorkflowError(
            "Resume cursor or immutable backfill identity does not match "
            "durable progress."
        )
    cursor.execute(
        """
        UPDATE stonks.tech_indicators_publication
        SET run_id = %s, updated_at = now()
        WHERE publication_id = %s AND status = 'BUILDING'
        """,
        (run_id, row[0]),
    )
    if cursor.rowcount != 1:
        raise TechIndicatorsWorkflowError("Backfill candidate changed during resume.")
    return BackfillPublicationProgress(
        publication_id=row[0],
        completed_batch_count=row[5],
        staged_payload_row_count=row[6],
        cursor=observed,
        inserted_row_count=row[9],
        updated_row_count=row[10],
        equivalent_row_count=row[11],
        deleted_row_count=row[12],
    )


def record_backfill_batch(
    *,
    cursor: Any,
    progress: BackfillPublicationProgress,
    provider_listing_id: UUID,
    trading_date: date,
    row_count: int,
    writes: SlotWriteCounts,
) -> BackfillPublicationProgress:
    """Advance the durable exclusive cursor in the same transaction as one batch."""

    if row_count != writes.total_rows or row_count <= 0:
        raise ValueError("row_count must equal the positive batch write count.")
    batch_number = progress.completed_batch_count + 1
    cursor.execute(
        """
        UPDATE stonks.tech_indicators_publication
        SET completed_batch_count = %s,
            staged_payload_row_count = staged_payload_row_count + %s,
            resume_provider_listing_id = %s, resume_trading_date = %s,
            resume_cursor_updated_at = now(),
            inserted_row_count = inserted_row_count + %s,
            updated_row_count = updated_row_count + %s,
            equivalent_row_count = equivalent_row_count + %s,
            updated_at = now()
        WHERE publication_id = %s AND status = 'BUILDING'
          AND completed_batch_count = %s
        """,
        (
            batch_number,
            row_count,
            provider_listing_id,
            trading_date,
            writes.inserted_rows,
            writes.updated_rows,
            writes.unchanged_rows,
            progress.publication_id,
            progress.completed_batch_count,
        ),
    )
    if cursor.rowcount != 1:
        raise TechIndicatorsWorkflowError("Backfill progress changed concurrently.")
    return BackfillPublicationProgress(
        publication_id=progress.publication_id,
        completed_batch_count=batch_number,
        staged_payload_row_count=progress.staged_payload_row_count + row_count,
        cursor=TechIndicatorsBackfillCursor(
            provider_listing_id, trading_date, batch_number
        ),
        inserted_row_count=progress.inserted_row_count + writes.inserted_rows,
        updated_row_count=progress.updated_row_count + writes.updated_rows,
        equivalent_row_count=(
            progress.equivalent_row_count + writes.unchanged_rows
        ),
        deleted_row_count=progress.deleted_row_count,
    )


def delete_stale_backfill_rows(
    *,
    cursor: Any,
    progress: BackfillPublicationProgress,
    provider_listing_id: UUID,
    target_slot: TechIndicatorsPayloadSlot,
    maximum_rows: int,
) -> BackfillPublicationProgress:
    """Delete bounded inactive-slot keys that no longer exist in current OHLCV."""

    table = target_slot.table_name
    cursor.execute(
        f"""
        SELECT count(*)
        FROM {table} AS payload
        WHERE payload.provider_listing_id = %s
          AND NOT EXISTS (
              SELECT 1 FROM stonks.ohlcv_daily AS source
              WHERE source.provider_listing_id = payload.provider_listing_id
                AND source.trading_date = payload.trading_date
          )
        """,
        (provider_listing_id,),
    )
    count = cursor.fetchone()[0]
    if count > maximum_rows:
        raise TechIndicatorsWorkflowError(
            "Inactive-slot cleanup exceeds the bounded transaction ceiling."
        )
    if count:
        cursor.execute(
            f"""
            DELETE FROM {table} AS payload
            WHERE payload.provider_listing_id = %s
              AND NOT EXISTS (
                  SELECT 1 FROM stonks.ohlcv_daily AS source
                  WHERE source.provider_listing_id = payload.provider_listing_id
                    AND source.trading_date = payload.trading_date
              )
            """,
            (provider_listing_id,),
        )
        if cursor.rowcount != count:
            raise TechIndicatorsWorkflowError("Inactive-slot cleanup drifted.")
        cursor.execute(
            """
            UPDATE stonks.tech_indicators_publication
            SET deleted_row_count = deleted_row_count + %s, updated_at = now()
            WHERE publication_id = %s AND status = 'BUILDING'
            """,
            (count, progress.publication_id),
        )
    return BackfillPublicationProgress(
        publication_id=progress.publication_id,
        completed_batch_count=progress.completed_batch_count,
        staged_payload_row_count=progress.staged_payload_row_count,
        cursor=progress.cursor,
        inserted_row_count=progress.inserted_row_count,
        updated_row_count=progress.updated_row_count,
        equivalent_row_count=progress.equivalent_row_count,
        deleted_row_count=progress.deleted_row_count + count,
    )


def complete_backfill_listing(
    *,
    cursor: Any,
    publication_id: UUID,
    listing: EligibleListing,
    target_slot: TechIndicatorsPayloadSlot,
    calculation_version: str,
    benchmark_provider_listing_id: UUID | None,
) -> None:
    """Record immutable membership only after the complete listing image exists."""

    cursor.execute(
        """
        INSERT INTO stonks.tech_indicators_publication_listing (
            publication_id, provider_listing_id, action, target_slot,
            calculation_version, source_coverage_start_date,
            source_coverage_end_date, source_row_count, payload_row_count,
            benchmark_provider_listing_id, candidate_completed_at
        ) VALUES (%s, %s, 'PRESENT', %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (publication_id, provider_listing_id) DO NOTHING
        """,
        (
            publication_id,
            listing.provider_listing_id,
            target_slot.value,
            calculation_version,
            listing.first_trading_date,
            listing.last_trading_date,
            listing.source_observation_count,
            listing.source_observation_count,
            benchmark_provider_listing_id,
        ),
    )
    inserted = cursor.rowcount
    if inserted not in {0, 1}:
        raise TechIndicatorsWorkflowError("Backfill membership write was inconsistent.")
    if inserted == 0:
        cursor.execute(
            """
            SELECT target_slot, calculation_version,
                   source_coverage_start_date, source_coverage_end_date,
                   source_row_count, payload_row_count,
                   benchmark_provider_listing_id
            FROM stonks.tech_indicators_publication_listing
            WHERE publication_id = %s AND provider_listing_id = %s
            """,
            (publication_id, listing.provider_listing_id),
        )
        observed = cursor.fetchone()
        expected = (
            target_slot.value,
            calculation_version,
            listing.first_trading_date,
            listing.last_trading_date,
            listing.source_observation_count,
            listing.source_observation_count,
            benchmark_provider_listing_id,
        )
        if observed != expected:
            raise TechIndicatorsWorkflowError(
                "Existing backfill membership does not match the complete image."
            )


def prepare_backfill_candidate(
    *,
    cursor: Any,
    progress: BackfillPublicationProgress,
    expected_listing_count: int,
    expected_source_row_count: int,
    json_report_object_id: UUID,
    pdf_report_object_id: UUID,
) -> None:
    """Freeze a complete report-backed staged candidate as PREPARED."""

    if progress.staged_payload_row_count != expected_source_row_count:
        raise TechIndicatorsWorkflowError(
            "Staged payload count does not equal the complete source image."
        )
    cursor.execute(
        """
        UPDATE stonks.tech_indicators_publication
        SET expected_listing_count = %s, expected_source_row_count = %s,
            expected_payload_row_count = %s,
            warning_count = 0, failure_count = 0,
            json_report_object_id = %s, pdf_report_object_id = %s,
            source_validated_at = now(), prepared_at = now(),
            status = 'PREPARED', updated_at = now()
        WHERE publication_id = %s AND status = 'BUILDING'
          AND completed_batch_count = %s
          AND staged_payload_row_count = %s
          AND (SELECT count(*) FROM stonks.tech_indicators_publication_listing
               WHERE publication_id = %s) = %s
        """,
        (
            expected_listing_count,
            expected_source_row_count,
            expected_source_row_count,
            json_report_object_id,
            pdf_report_object_id,
            progress.publication_id,
            progress.completed_batch_count,
            progress.staged_payload_row_count,
            progress.publication_id,
            expected_listing_count,
        ),
    )
    if cursor.rowcount != 1:
        raise TechIndicatorsWorkflowError(
            "Complete backfill candidate could not prepare."
        )


def _create_candidate(
    *,
    cursor: Any,
    resolved: ResolvedTechIndicatorsBackfillScope,
    run_id: UUID,
    benchmark: BenchmarkHistory | None,
) -> BackfillPublicationProgress:
    publication_id = uuid4()
    required = benchmark is not None
    cursor.execute(
        """
        INSERT INTO stonks.tech_indicators_publication (
            publication_id, publication_kind, status, calculation_version,
            publication_method, scope_schema_version, scope_hash, effective_date,
            requested_start_date, requested_end_date, run_id,
            benchmark_required, benchmark_provider_listing_id,
            benchmark_contract_version, benchmark_coverage_start_date,
            benchmark_coverage_end_date, benchmark_source_row_count,
            inserted_row_count, updated_row_count, deleted_row_count,
            equivalent_row_count, completed_batch_count, staged_payload_row_count
        ) VALUES (
            %s, %s, 'BUILDING', %s, 'STAGED', 1, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, 0, 0, 0, 0, 0, 0
        )
        """,
        (
            publication_id,
            "VERSION_REBUILD" if resolved.request.rebuild else "BACKFILL",
            resolved.request.calculation_version,
            resolved.scope_hash,
            resolved.request.effective_date,
            resolved.request.start_date,
            resolved.request.end_date,
            run_id,
            required,
            None if benchmark is None else benchmark.benchmark.provider_listing_id,
            BENCHMARK_CONTRACT_VERSION if required else None,
            None if benchmark is None else benchmark.first_trading_date,
            None if benchmark is None else benchmark.last_trading_date,
            None if benchmark is None else len(benchmark.bars),
        ),
    )
    return BackfillPublicationProgress(publication_id, 0, 0, None, 0, 0, 0, 0)


def _benchmark_facts(
    benchmark: BenchmarkHistory | None,
) -> tuple[bool, UUID | None, date | None, date | None, int | None]:
    if benchmark is None:
        return False, None, None, None, None
    return (
        True,
        benchmark.benchmark.provider_listing_id,
        benchmark.first_trading_date,
        benchmark.last_trading_date,
        len(benchmark.bars),
    )


__all__ = [
    "BackfillPublicationProgress",
    "complete_backfill_listing",
    "create_or_resume_backfill_candidate",
    "delete_stale_backfill_rows",
    "prepare_backfill_candidate",
    "record_backfill_batch",
]
