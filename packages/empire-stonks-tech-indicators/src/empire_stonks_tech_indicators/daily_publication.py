"""Candidate-publication persistence used by the package-owned daily runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable
from uuid import UUID, uuid4

from empire_stonks_tech_indicators.config import DEFAULT_CALCULATION_VERSION
from empire_stonks_tech_indicators.exceptions import TechIndicatorsWorkflowError
from empire_stonks_tech_indicators.persistence import TechIndicatorsPayloadSlot
from empire_stonks_tech_indicators.reports import BENCHMARK_CONTRACT_VERSION


@dataclass(frozen=True, order=True)
class DailyCandidateListing:
    """One complete candidate-membership image for a daily publication."""

    provider_listing_id: UUID
    target_slot: TechIndicatorsPayloadSlot
    source_coverage_start_date: date
    source_coverage_end_date: date
    source_row_count: int
    benchmark_provider_listing_id: UUID | None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_listing_id, UUID):
            raise TypeError("provider_listing_id must be a UUID.")
        if not isinstance(self.target_slot, TechIndicatorsPayloadSlot):
            raise TypeError("target_slot must be a TechIndicatorsPayloadSlot.")
        for name in ("source_coverage_start_date", "source_coverage_end_date"):
            if type(getattr(self, name)) is not date:
                raise TypeError(f"{name} must be a date.")
        if self.source_coverage_end_date < self.source_coverage_start_date:
            raise ValueError("source coverage dates are reversed.")
        if type(self.source_row_count) is not int or self.source_row_count <= 0:
            raise ValueError("source_row_count must be a positive integer.")
        if self.benchmark_provider_listing_id is not None and not isinstance(
            self.benchmark_provider_listing_id, UUID
        ):
            raise TypeError("benchmark_provider_listing_id must be a UUID or None.")


def select_daily_target_slots(
    *,
    cursor: Any,
    provider_listing_ids: Iterable[UUID],
) -> dict[UUID, TechIndicatorsPayloadSlot]:
    """Use each listing's active slot, or deterministic slot A initially."""

    identifiers = _listing_ids(provider_listing_ids)
    if not identifiers:
        return {}
    cursor.execute(
        """
        SELECT provider_listing_id, target_slot
        FROM stonks.tech_indicators_publication_listing
        WHERE is_active
          AND provider_listing_id = ANY(%s::uuid[])
        ORDER BY provider_listing_id
        """,
        (list(identifiers),),
    )
    active: dict[UUID, TechIndicatorsPayloadSlot] = {}
    for listing_id, raw_slot in cursor.fetchall():
        if listing_id not in identifiers or listing_id in active:
            raise TechIndicatorsWorkflowError(
                "Active technical-indicator membership is inconsistent."
            )
        try:
            active[listing_id] = TechIndicatorsPayloadSlot(raw_slot)
        except ValueError as exc:
            raise TechIndicatorsWorkflowError(
                "Active technical-indicator membership has an invalid slot."
            ) from exc
    return {
        listing_id: active.get(listing_id, TechIndicatorsPayloadSlot.A)
        for listing_id in identifiers
    }


def create_daily_candidate(
    *,
    cursor: Any,
    publication_kind: str,
    effective_date: date,
    run_id: UUID,
    scope_hash: str,
    memberships: Iterable[DailyCandidateListing],
    benchmark_provider_listing_id: UUID | None,
    benchmark_coverage_start_date: date | None,
    benchmark_coverage_end_date: date | None,
    benchmark_source_row_count: int | None,
    calculation_version: str = DEFAULT_CALCULATION_VERSION,
    publication_id: UUID | None = None,
) -> UUID:
    """Create one BUILDING in-place candidate and its immutable memberships."""

    if publication_kind not in {"DAILY", "CORRECTION"}:
        raise ValueError("daily publication_kind must be DAILY or CORRECTION.")
    candidate = publication_id or uuid4()
    if not isinstance(candidate, UUID) or not isinstance(run_id, UUID):
        raise TypeError("publication_id and run_id must be UUID values.")
    prepared = _memberships(memberships)
    benchmark_required = benchmark_provider_listing_id is not None
    benchmark_values = (
        benchmark_coverage_start_date,
        benchmark_coverage_end_date,
        benchmark_source_row_count,
    )
    if benchmark_required:
        if (
            any(value is None for value in benchmark_values)
            or type(benchmark_source_row_count) is not int
            or benchmark_source_row_count <= 0
        ):
            raise ValueError("required benchmark coverage is incomplete.")
    elif any(value is not None for value in benchmark_values):
        raise ValueError("unrequired benchmark coverage must be empty.")

    cursor.execute(
        """
        INSERT INTO stonks.tech_indicators_publication (
            publication_id, publication_kind, status, calculation_version,
            publication_method, scope_schema_version, scope_hash,
            effective_date, requested_start_date, requested_end_date, run_id,
            benchmark_required, benchmark_provider_listing_id,
            benchmark_contract_version, benchmark_coverage_start_date,
            benchmark_coverage_end_date, benchmark_source_row_count
        )
        VALUES (
            %s, %s, 'BUILDING', %s, 'IN_PLACE', 1, %s, %s, NULL, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        """,
        (
            candidate,
            publication_kind,
            calculation_version,
            scope_hash,
            effective_date,
            effective_date,
            run_id,
            benchmark_required,
            benchmark_provider_listing_id,
            BENCHMARK_CONTRACT_VERSION if benchmark_required else None,
            benchmark_coverage_start_date,
            benchmark_coverage_end_date,
            benchmark_source_row_count,
        ),
    )
    for item in prepared:
        cursor.execute(
            """
            INSERT INTO stonks.tech_indicators_publication_listing (
                publication_id, provider_listing_id, action, target_slot,
                calculation_version, source_coverage_start_date,
                source_coverage_end_date, source_row_count, payload_row_count,
                benchmark_provider_listing_id, candidate_completed_at
            )
            VALUES (%s, %s, 'PRESENT', %s, %s, %s, %s, %s, %s, %s, now())
            """,
            (
                candidate,
                item.provider_listing_id,
                item.target_slot.value,
                calculation_version,
                item.source_coverage_start_date,
                item.source_coverage_end_date,
                item.source_row_count,
                item.source_row_count,
                item.benchmark_provider_listing_id,
            ),
        )
    return candidate


def prepare_daily_candidate(
    *,
    cursor: Any,
    publication_id: UUID,
    expected_listing_count: int,
    expected_source_row_count: int,
    expected_payload_row_count: int,
    inserted_row_count: int,
    updated_row_count: int,
    deleted_row_count: int,
    equivalent_row_count: int,
    warning_count: int,
    failure_count: int,
    json_report_object_id: UUID,
    pdf_report_object_id: UUID,
) -> None:
    """Make complete report-backed candidate facts immutable and PREPARED."""

    counts = (
        expected_listing_count,
        expected_source_row_count,
        expected_payload_row_count,
        inserted_row_count,
        updated_row_count,
        deleted_row_count,
        equivalent_row_count,
        warning_count,
        failure_count,
    )
    if any(type(value) is not int or value < 0 for value in counts):
        raise ValueError("candidate counts must be non-negative integers.")
    cursor.execute(
        """
        UPDATE stonks.tech_indicators_publication
        SET expected_listing_count = %s, expected_source_row_count = %s,
            expected_payload_row_count = %s, inserted_row_count = %s,
            updated_row_count = %s, deleted_row_count = %s,
            equivalent_row_count = %s, warning_count = %s, failure_count = %s,
            completed_batch_count = 0, staged_payload_row_count = 0,
            json_report_object_id = %s, pdf_report_object_id = %s,
            source_validated_at = now(), prepared_at = now(),
            status = 'PREPARED', updated_at = now()
        WHERE publication_id = %s AND status = 'BUILDING'
        """,
        (*counts, json_report_object_id, pdf_report_object_id, publication_id),
    )
    if cursor.rowcount != 1:
        raise TechIndicatorsWorkflowError(
            "Technical-indicator candidate could not be prepared."
        )


def _listing_ids(values: Iterable[UUID]) -> tuple[UUID, ...]:
    identifiers = tuple(sorted(values))
    if any(not isinstance(value, UUID) for value in identifiers):
        raise TypeError("provider_listing_ids must contain UUID values.")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("provider_listing_ids must be unique.")
    return identifiers


def _memberships(
    values: Iterable[DailyCandidateListing],
) -> tuple[DailyCandidateListing, ...]:
    prepared = tuple(sorted(values))
    if any(not isinstance(value, DailyCandidateListing) for value in prepared):
        raise TypeError("memberships must contain DailyCandidateListing values.")
    identifiers = tuple(value.provider_listing_id for value in prepared)
    if not identifiers or len(identifiers) != len(set(identifiers)):
        raise ValueError("memberships must be non-empty with unique listing IDs.")
    return prepared


__all__ = [
    "DailyCandidateListing",
    "create_daily_candidate",
    "prepare_daily_candidate",
    "select_daily_target_slots",
]
