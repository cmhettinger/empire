"""Atomic publication finalization and deterministic recovery inspection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Any, Iterable
from uuid import UUID

from empire_stonks_tech_indicators.config import HARD_MAX_TRANSACTION_ROWS
from empire_stonks_tech_indicators.exceptions import TechIndicatorsWorkflowError
from empire_stonks_tech_indicators.models import FeatureRow
from empire_stonks_tech_indicators.persistence import (
    FeatureRowKey,
    TechIndicatorsPayloadSlot,
    upsert_feature_rows,
)


TECH_INDICATORS_WRITER_LOCK_KEY = 7681980501239933110
TECH_INDICATORS_WRITER_LOCK_SEED = "empire:stonks:tech-indicators:writer:v1"
_LOCK_CLASS_ID = 1788600464
_LOCK_OBJECT_ID = 2749507766
_MAX_IN_PLACE_SECONDS = 60.0


class PublicationRecoveryAction(StrEnum):
    """Safe next action for one durable publication record."""

    RESUME_BUILDING = "RESUME_BUILDING"
    WAIT_FOR_CORE = "WAIT_FOR_CORE"
    FINALIZE_PREPARED = "FINALIZE_PREPARED"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"


@dataclass(frozen=True, order=True)
class PublicationSlotSelection:
    """Deterministic current/inactive slot choice for one listing."""

    provider_listing_id: UUID
    active_slot: TechIndicatorsPayloadSlot | None
    target_slot: TechIndicatorsPayloadSlot


@dataclass(frozen=True)
class InPlaceSlotChanges:
    """Bounded mutations retained for one physical slot until finalization."""

    slot: TechIndicatorsPayloadSlot
    rows: tuple[FeatureRow, ...] = ()
    deleted_keys: tuple[FeatureRowKey, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.slot, TechIndicatorsPayloadSlot):
            raise TypeError("slot must be a TechIndicatorsPayloadSlot.")
        if any(not isinstance(row, FeatureRow) for row in self.rows):
            raise TypeError("rows must contain only FeatureRow records.")
        if any(not isinstance(key, FeatureRowKey) for key in self.deleted_keys):
            raise TypeError("deleted_keys must contain only FeatureRowKey records.")
        identities = [
            (row.source.provider_listing_id, row.source.trading_date)
            for row in self.rows
        ] + [
            (key.provider_listing_id, key.trading_date)
            for key in self.deleted_keys
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("In-place changes contain duplicate natural keys.")

    @property
    def row_count(self) -> int:
        return len(self.rows) + len(self.deleted_keys)


@dataclass(frozen=True)
class PublicationFinalizationResult:
    """Compact result whose durability is owned by the caller's commit."""

    publication_id: UUID
    published: bool
    already_published: bool
    publication_method: str
    activated_listing_count: int
    inserted_row_count: int
    updated_row_count: int
    deleted_row_count: int
    equivalent_row_count: int


@dataclass(frozen=True)
class PublicationRecoveryDecision:
    """Fail-closed recovery classification from durable state."""

    publication_id: UUID
    publication_status: str
    core_status: str | None
    action: PublicationRecoveryAction


@dataclass(frozen=True)
class _Publication:
    publication_id: UUID
    status: str
    publication_kind: str
    publication_method: str | None
    calculation_version: str
    scope_hash: str | None
    run_id: UUID | None
    benchmark_required: bool | None
    benchmark_provider_listing_id: UUID | None
    benchmark_coverage_start_date: object
    benchmark_coverage_end_date: object
    benchmark_source_row_count: int | None
    expected_listing_count: int | None
    expected_source_row_count: int | None
    expected_payload_row_count: int | None
    inserted_row_count: int | None
    updated_row_count: int | None
    deleted_row_count: int | None
    equivalent_row_count: int | None
    failure_count: int | None
    completed_batch_count: int | None
    staged_payload_row_count: int | None
    json_report_object_id: UUID | None
    pdf_report_object_id: UUID | None


def select_inactive_payload_slots(
    *,
    cursor: Any,
    provider_listing_ids: Iterable[UUID],
) -> tuple[PublicationSlotSelection, ...]:
    """Choose A for an initial image or the slot opposite current membership."""

    listing_ids = _listing_ids(provider_listing_ids)
    if not listing_ids:
        return ()
    cursor.execute(
        """
        SELECT provider_listing_id
        FROM stonks.provider_listing
        WHERE provider_listing_id = ANY(%s::uuid[])
        ORDER BY provider_listing_id
        """,
        (list(listing_ids),),
    )
    if tuple(row[0] for row in cursor.fetchall()) != listing_ids:
        raise TechIndicatorsWorkflowError(
            "Inactive-slot selection contains a missing provider listing."
        )
    cursor.execute(
        """
        SELECT provider_listing_id, target_slot
        FROM stonks.tech_indicators_publication_listing
        WHERE is_active
          AND provider_listing_id = ANY(%s::uuid[])
        ORDER BY provider_listing_id
        """,
        (list(listing_ids),),
    )
    active: dict[UUID, TechIndicatorsPayloadSlot] = {}
    for row in cursor.fetchall():
        if row[0] not in listing_ids or row[0] in active:
            raise TechIndicatorsWorkflowError(
                "Active publication membership returned identity drift."
            )
        try:
            active[row[0]] = TechIndicatorsPayloadSlot(row[1])
        except ValueError as exc:
            raise TechIndicatorsWorkflowError(
                "Active publication membership returned an invalid slot."
            ) from exc
    return tuple(
        PublicationSlotSelection(
            provider_listing_id=listing_id,
            active_slot=active.get(listing_id),
            target_slot=(
                TechIndicatorsPayloadSlot.B
                if active.get(listing_id) is TechIndicatorsPayloadSlot.A
                else TechIndicatorsPayloadSlot.A
            ),
        )
        for listing_id in listing_ids
    )


def finalize_publication(
    *,
    cursor: Any,
    publication_id: UUID,
    scope_hash: str,
    calculation_version: str,
    provider_listing_ids: Iterable[UUID],
    in_place_changes: Iterable[InPlaceSlotChanges] = (),
) -> PublicationFinalizationResult:
    """Validate and publish one complete P0.9 unit in the caller transaction.

    The cursor must be the dedicated P0.10 lock transaction. This function
    never commits or rolls back. A caller must discard the returned result if
    its later commit fails.
    """

    _validate_identity(publication_id, scope_hash, calculation_version)
    started_at = monotonic()
    listing_ids = _listing_ids(provider_listing_ids)
    changes = _changes(in_place_changes)
    _require_writer_lock(cursor)
    publication = _load_publication(cursor, publication_id)
    _require_requested_identity(
        publication,
        scope_hash=scope_hash,
        calculation_version=calculation_version,
    )
    if publication.status == "PUBLISHED":
        _require_published_memberships(cursor, publication, listing_ids)
        return _result(publication, already_published=True)
    if publication.status != "PREPARED":
        raise TechIndicatorsWorkflowError(
            "Technical-indicator publication is not prepared for finalization."
        )
    _require_prepared_shape(publication, listing_ids)
    _require_core_and_reports(cursor, publication)
    _require_benchmark_current(cursor, publication)
    memberships = _load_candidate_memberships(cursor, publication_id)
    _require_membership_scope(publication, memberships, listing_ids)
    _require_membership_subject_shape(cursor, publication, memberships)
    _require_target_slots_inactive(cursor, publication, memberships)

    observed = (0, 0, 0, 0)
    if publication.publication_method == "IN_PLACE":
        observed = _apply_in_place_changes(cursor, changes, memberships)
        expected = (
            publication.inserted_row_count,
            publication.updated_row_count,
            publication.deleted_row_count,
            publication.equivalent_row_count,
        )
        if observed != expected:
            raise TechIndicatorsWorkflowError(
                "In-place publication write counts do not match prepared facts."
            )
    elif changes:
        raise TechIndicatorsWorkflowError(
            "Only an in-place publication accepts terminal payload changes."
        )

    _require_candidate_images(cursor, publication, memberships)
    if (
        publication.publication_method == "IN_PLACE"
        and monotonic() - started_at > _MAX_IN_PLACE_SECONDS
    ):
        raise TechIndicatorsWorkflowError(
            "In-place finalization exceeded the 60-second transaction gate."
        )
    _publish_memberships(cursor, publication, listing_ids)
    return _result(publication, already_published=False)


def inspect_publication_recovery(
    *,
    cursor: Any,
    publication_id: UUID,
    scope_hash: str | None,
    calculation_version: str,
) -> PublicationRecoveryDecision:
    """Classify a durable publication without changing visibility or state."""

    if not isinstance(publication_id, UUID):
        raise TypeError("publication_id must be a UUID.")
    _validate_scope_hash(scope_hash, allow_none=True)
    if not isinstance(calculation_version, str) or not calculation_version:
        raise ValueError("calculation_version must be non-empty text.")
    _require_writer_lock(cursor)
    publication = _load_publication(cursor, publication_id)
    _require_requested_identity(
        publication,
        scope_hash=scope_hash,
        calculation_version=calculation_version,
    )
    core_status = _core_status(cursor, publication.run_id)
    if publication.status == "PUBLISHED":
        action = PublicationRecoveryAction.ALREADY_PUBLISHED
    elif publication.status in {"FAILED", "ABANDONED", "RETIRED"}:
        action = PublicationRecoveryAction.TERMINAL_FAILURE
    elif (
        publication.status == "BUILDING"
        and publication.completed_batch_count is not None
        and publication.completed_batch_count > 0
    ):
        action = PublicationRecoveryAction.RESUME_BUILDING
    elif core_status in {"failed", "cancelled", "abandoned"}:
        action = PublicationRecoveryAction.TERMINAL_FAILURE
    elif publication.status == "PREPARED" and core_status == "succeeded":
        action = PublicationRecoveryAction.FINALIZE_PREPARED
    else:
        action = PublicationRecoveryAction.WAIT_FOR_CORE
    return PublicationRecoveryDecision(
        publication_id=publication_id,
        publication_status=publication.status,
        core_status=core_status,
        action=action,
    )


def fail_unpublished_publication(
    *,
    cursor: Any,
    publication_id: UUID,
    abandoned: bool = False,
) -> None:
    """Make one BUILDING/PREPARED candidate terminal without exposing it."""

    if not isinstance(publication_id, UUID):
        raise TypeError("publication_id must be a UUID.")
    if type(abandoned) is not bool:
        raise TypeError("abandoned must be a boolean.")
    _require_writer_lock(cursor)
    status = "ABANDONED" if abandoned else "FAILED"
    timestamp = "abandoned_at" if abandoned else "failed_at"
    cursor.execute(
        f"""
        UPDATE stonks.tech_indicators_publication
        SET status = %s, {timestamp} = clock_timestamp(), updated_at = clock_timestamp()
        WHERE publication_id = %s
          AND status IN ('BUILDING', 'PREPARED')
          AND NOT EXISTS (
              SELECT 1
              FROM stonks.tech_indicators_publication_listing AS membership
              WHERE membership.publication_id = %s
                AND membership.is_active
          )
        RETURNING publication_id
        """,
        (status, publication_id, publication_id),
    )
    if cursor.fetchone() is None:
        raise TechIndicatorsWorkflowError(
            "Publication cannot transition to the requested terminal state."
        )


def _validate_identity(
    publication_id: UUID, scope_hash: str, calculation_version: str
) -> None:
    if not isinstance(publication_id, UUID):
        raise TypeError("publication_id must be a UUID.")
    _validate_scope_hash(scope_hash, allow_none=False)
    if not isinstance(calculation_version, str) or not calculation_version:
        raise ValueError("calculation_version must be non-empty text.")


def _validate_scope_hash(
    scope_hash: str | None, *, allow_none: bool
) -> None:
    if allow_none and scope_hash is None:
        return
    if (
        not isinstance(scope_hash, str)
        or len(scope_hash) != 64
        or any(character not in "0123456789abcdef" for character in scope_hash)
    ):
        raise ValueError("scope_hash must be lowercase SHA-256 hex.")


def _listing_ids(values: Iterable[UUID]) -> tuple[UUID, ...]:
    result = tuple(values)
    if any(not isinstance(value, UUID) for value in result):
        raise TypeError("provider_listing_ids must contain only UUIDs.")
    if len(result) != len(set(result)):
        raise ValueError("provider_listing_ids must be unique.")
    return tuple(sorted(result, key=str))


def _changes(
    values: Iterable[InPlaceSlotChanges],
) -> tuple[InPlaceSlotChanges, ...]:
    result = tuple(values)
    if any(not isinstance(value, InPlaceSlotChanges) for value in result):
        raise TypeError("in_place_changes contains an invalid record.")
    if len({value.slot for value in result}) != len(result):
        raise ValueError("At most one in-place change record is allowed per slot.")
    if sum(value.row_count for value in result) > HARD_MAX_TRANSACTION_ROWS:
        raise TechIndicatorsWorkflowError(
            "In-place publication exceeds the 25,000-row transaction ceiling."
        )
    identities = [
        (row.source.provider_listing_id, row.source.trading_date)
        for value in result
        for row in value.rows
    ] + [
        (key.provider_listing_id, key.trading_date)
        for value in result
        for key in value.deleted_keys
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("In-place publication changes contain duplicate keys.")
    return result


def _require_writer_lock(cursor: Any) -> None:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_locks
            WHERE locktype = 'advisory'
              AND pid = pg_backend_pid()
              AND classid = %s
              AND objid = %s
              AND objsubid = 1
              AND mode = 'ExclusiveLock'
              AND granted
        )
        """,
        (_LOCK_CLASS_ID, _LOCK_OBJECT_ID),
    )
    row = cursor.fetchone()
    if row is None or row[0] is not True:
        raise TechIndicatorsWorkflowError(
            "The tech-indicators writer lock is not held by this transaction."
        )


def _load_publication(cursor: Any, publication_id: UUID) -> _Publication:
    cursor.execute(
        """
        SELECT
            publication_id, status, publication_kind, publication_method,
            calculation_version, scope_hash, run_id, benchmark_required,
            benchmark_provider_listing_id, benchmark_coverage_start_date,
            benchmark_coverage_end_date, benchmark_source_row_count,
            expected_listing_count, expected_source_row_count,
            expected_payload_row_count, inserted_row_count, updated_row_count,
            deleted_row_count, equivalent_row_count, failure_count,
            completed_batch_count, staged_payload_row_count,
            json_report_object_id, pdf_report_object_id
        FROM stonks.tech_indicators_publication
        WHERE publication_id = %s
        FOR UPDATE
        """,
        (publication_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise TechIndicatorsWorkflowError("Publication does not exist.")
    try:
        return _Publication(*row)
    except TypeError as exc:
        raise TechIndicatorsWorkflowError(
            "Publication returned invalid contract data."
        ) from exc


def _require_requested_identity(
    publication: _Publication,
    *,
    scope_hash: str | None,
    calculation_version: str,
) -> None:
    if (
        publication.scope_hash != scope_hash
        or publication.calculation_version != calculation_version
    ):
        raise TechIndicatorsWorkflowError(
            "Publication identity does not match the requested recovery scope."
        )


def _require_prepared_shape(
    publication: _Publication, listing_ids: tuple[UUID, ...]
) -> None:
    if (
        publication.publication_method not in {
            "IN_PLACE",
            "STAGED",
            "MEMBERSHIP_ONLY",
        }
        or publication.expected_listing_count != len(listing_ids)
        or publication.failure_count != 0
        or publication.run_id is None
        or publication.json_report_object_id is None
        or publication.pdf_report_object_id is None
        or (
            publication.publication_method == "IN_PLACE"
            and sum(
                value or 0
                for value in (
                    publication.inserted_row_count,
                    publication.updated_row_count,
                    publication.deleted_row_count,
                    publication.equivalent_row_count,
                )
            )
            > HARD_MAX_TRANSACTION_ROWS
        )
        or (
            publication.publication_method == "STAGED"
            and (
                publication.staged_payload_row_count
                != publication.expected_payload_row_count
                or (
                    (publication.expected_payload_row_count or 0) > 0
                    and (publication.completed_batch_count or 0) == 0
                )
            )
        )
    ):
        raise TechIndicatorsWorkflowError(
            "Prepared publication facts are incomplete or inconsistent."
        )


def _core_status(cursor: Any, run_id: UUID | None) -> str | None:
    if run_id is None:
        return None
    cursor.execute(
        "SELECT status FROM core.core_run WHERE run_id = %s",
        (run_id,),
    )
    row = cursor.fetchone()
    return None if row is None else row[0]


def _require_core_and_reports(cursor: Any, publication: _Publication) -> None:
    cursor.execute(
        """
        SELECT status, completed_at
        FROM core.core_run
        WHERE run_id = %s
        FOR UPDATE
        """,
        (publication.run_id,),
    )
    run = cursor.fetchone()
    if run is None or run[0] != "succeeded" or run[1] is None:
        raise TechIndicatorsWorkflowError(
            "Core run is not durably succeeded; publication remains hidden."
        )
    cursor.execute(
        """
        SELECT object_id, filename, content_type, object_kind, size_bytes,
               checksum_sha256, deleted_at, run_id
        FROM core.stored_object
        WHERE object_id = ANY(%s::uuid[])
        ORDER BY object_id
        FOR UPDATE
        """,
        ([publication.json_report_object_id, publication.pdf_report_object_id],),
    )
    objects = {row[0]: row for row in cursor.fetchall()}
    expected = {
        publication.json_report_object_id: (
            "report.json",
            "application/json",
            "stonks_tech_indicators_report",
        ),
        publication.pdf_report_object_id: (
            "report.pdf",
            "application/pdf",
            "stonks_tech_indicators_pdf_report",
        ),
    }
    for object_id, identity in expected.items():
        row = objects.get(object_id)
        if (
            row is None
            or tuple(row[1:4]) != identity
            or not isinstance(row[4], int)
            or row[4] <= 0
            or not isinstance(row[5], str)
            or len(row[5]) != 64
            or row[6] is not None
            or row[7] != publication.run_id
        ):
            raise TechIndicatorsWorkflowError(
                "Required publication report evidence is missing or incomplete."
            )


def _require_benchmark_current(cursor: Any, publication: _Publication) -> None:
    if publication.benchmark_required is not True:
        return
    cursor.execute(
        """
        SELECT count(*), min(provider_listing_id::text)::uuid
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker = 'SPX'
          AND status = 'ACTIVE'
          AND instrument_type_code = 'EQUITY_INDEX'
          AND jsonb_typeof(metadata) = 'object'
          AND metadata ->> 'YahooTicker' = '^GSPC'
        """
    )
    identity = cursor.fetchone()
    if identity != (1, publication.benchmark_provider_listing_id):
        raise TechIndicatorsWorkflowError(
            "The exact active SPX benchmark identity is unavailable."
        )
    cursor.execute(
        """
        SELECT min(trading_date), max(trading_date), count(*)
        FROM stonks.ohlcv_daily
        WHERE provider_listing_id = %s
        """,
        (publication.benchmark_provider_listing_id,),
    )
    row = cursor.fetchone()
    if row != (
        publication.benchmark_coverage_start_date,
        publication.benchmark_coverage_end_date,
        publication.benchmark_source_row_count,
    ):
        raise TechIndicatorsWorkflowError(
            "Benchmark source changed after candidate preparation."
        )


def _load_candidate_memberships(
    cursor: Any, publication_id: UUID
) -> tuple[tuple[object, ...], ...]:
    cursor.execute(
        """
        SELECT provider_listing_id, action, target_slot, calculation_version,
               source_coverage_start_date, source_coverage_end_date,
               source_row_count, payload_row_count,
               benchmark_provider_listing_id, candidate_completed_at,
               is_active
        FROM stonks.tech_indicators_publication_listing
        WHERE publication_id = %s
        ORDER BY provider_listing_id
        FOR UPDATE
        """,
        (publication_id,),
    )
    return tuple(tuple(row) for row in cursor.fetchall())


def _require_membership_scope(
    publication: _Publication,
    memberships: tuple[tuple[object, ...], ...],
    listing_ids: tuple[UUID, ...],
) -> None:
    if tuple(row[0] for row in memberships) != listing_ids:
        raise TechIndicatorsWorkflowError(
            "Candidate membership does not match the exact requested scope."
        )
    if (
        len(memberships) != publication.expected_listing_count
        or sum(row[6] for row in memberships)
        != publication.expected_source_row_count
        or sum(row[7] for row in memberships)
        != publication.expected_payload_row_count
        or any(row[3] != publication.calculation_version for row in memberships)
        or any(row[10] is True for row in memberships)
    ):
        raise TechIndicatorsWorkflowError(
            "Candidate membership counts or version do not reconcile."
        )


def _require_membership_subject_shape(
    cursor: Any,
    publication: _Publication,
    memberships: tuple[tuple[object, ...], ...],
) -> None:
    cursor.execute(
        """
        SELECT
            provider_listing_id,
            (
                (
                    provider_code = 'EODDATA'
                    AND market IN ('NYSE', 'NASDAQ', 'AMEX')
                    AND jsonb_typeof(metadata) = 'object'
                    AND jsonb_typeof(metadata -> 'type') = 'string'
                    AND upper(btrim(metadata ->> 'type')) = 'EQUITY'
                )
                OR (
                    provider_code = 'STOOQ'
                    AND market IN ('nasdaq', 'nyse', 'nysemkt')
                )
                OR (
                    provider_code = 'YAHOO'
                    AND market = 'XIDX'
                    AND ticker = 'SPX'
                    AND instrument_type_code = 'EQUITY_INDEX'
                    AND jsonb_typeof(metadata) = 'object'
                    AND metadata ->> 'YahooTicker' = '^GSPC'
                )
            ) AS source_eligible,
            (
                (
                    provider_code = 'EODDATA'
                    AND market IN ('NYSE', 'NASDAQ', 'AMEX')
                    AND jsonb_typeof(metadata) = 'object'
                    AND jsonb_typeof(metadata -> 'type') = 'string'
                    AND upper(btrim(metadata ->> 'type')) = 'EQUITY'
                )
                OR (
                    provider_code = 'STOOQ'
                    AND market IN ('nasdaq', 'nyse', 'nysemkt')
                )
            ) AS benchmark_supported
        FROM stonks.provider_listing
        WHERE provider_listing_id = ANY(%s::uuid[])
        ORDER BY provider_listing_id
        """,
        ([row[0] for row in memberships],),
    )
    identities = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
    if set(identities) != {row[0] for row in memberships}:
        raise TechIndicatorsWorkflowError(
            "Candidate membership contains a missing provider listing."
        )
    present = [row for row in memberships if row[1] == "PRESENT"]
    if any(not identities[row[0]][0] for row in present):
        raise TechIndicatorsWorkflowError(
            "A PRESENT membership is outside source-value eligibility."
        )
    requires_benchmark = any(identities[row[0]][1] for row in present)
    if publication.benchmark_required is not requires_benchmark:
        raise TechIndicatorsWorkflowError(
            "Publication benchmark requirement does not match its subjects."
        )
    for row in present:
        expected = (
            publication.benchmark_provider_listing_id
            if identities[row[0]][1]
            else None
        )
        if row[8] != expected:
            raise TechIndicatorsWorkflowError(
                "Candidate membership benchmark shape is incomplete."
            )


def _require_target_slots_inactive(
    cursor: Any,
    publication: _Publication,
    memberships: tuple[tuple[object, ...], ...],
) -> None:
    targets = {row[0]: row[2] for row in memberships if row[1] == "PRESENT"}
    cursor.execute(
        """
        SELECT provider_listing_id, target_slot
        FROM stonks.tech_indicators_publication_listing
        WHERE is_active
          AND provider_listing_id = ANY(%s::uuid[])
        ORDER BY provider_listing_id
        FOR UPDATE
        """,
        (list(targets),),
    )
    active = dict(cursor.fetchall())
    for listing_id, target_slot in targets.items():
        current = active.get(listing_id)
        if publication.publication_method == "STAGED":
            expected = "B" if current == "A" else "A"
            if target_slot != expected:
                raise TechIndicatorsWorkflowError(
                    "A staged candidate does not target the inactive slot."
                )
        if (
            publication.publication_method == "IN_PLACE"
            and target_slot != (current or "A")
        ):
            raise TechIndicatorsWorkflowError(
                "An in-place candidate does not target the active slot."
            )


def _apply_in_place_changes(
    cursor: Any,
    changes: tuple[InPlaceSlotChanges, ...],
    memberships: tuple[tuple[object, ...], ...],
) -> tuple[int, int, int, int]:
    allowed = {(row[0], row[2]) for row in memberships if row[1] == "PRESENT"}
    inserted = updated = deleted = equivalent = 0
    for change in changes:
        if any(
            (row.source.provider_listing_id, change.slot.value) not in allowed
            for row in change.rows
        ) or any(
            (key.provider_listing_id, change.slot.value) not in allowed
            for key in change.deleted_keys
        ):
            raise TechIndicatorsWorkflowError(
                "In-place changes fall outside candidate membership slots."
            )
        counts = upsert_feature_rows(
            cursor=cursor,
            slot=change.slot,
            rows=change.rows,
        )
        inserted += counts.inserted_rows
        updated += counts.updated_rows
        equivalent += counts.unchanged_rows
        if change.deleted_keys:
            table = change.slot.table_name
            cursor.execute(
                f"""
                DELETE FROM {table} AS payload
                USING unnest(%s::uuid[], %s::date[])
                    AS requested(provider_listing_id, trading_date)
                WHERE payload.provider_listing_id = requested.provider_listing_id
                  AND payload.trading_date = requested.trading_date
                RETURNING payload.provider_listing_id
                """,
                (
                    [key.provider_listing_id for key in change.deleted_keys],
                    [key.trading_date for key in change.deleted_keys],
                ),
            )
            deleted += len(cursor.fetchall())
    return inserted, updated, deleted, equivalent


def _require_candidate_images(
    cursor: Any,
    publication: _Publication,
    memberships: tuple[tuple[object, ...], ...],
) -> None:
    for slot in TechIndicatorsPayloadSlot:
        listing_ids = [
            row[0]
            for row in memberships
            if row[1] == "PRESENT" and row[2] == slot.value
        ]
        if not listing_ids:
            continue
        cursor.execute(
            f"""
            WITH source AS (
                SELECT source.provider_listing_id, source.trading_date,
                       source.open, source.high, source.low, source.close,
                       source.volume,
                       row_number() OVER (
                           PARTITION BY source.provider_listing_id
                           ORDER BY source.trading_date
                       ) AS history_observation_count
                FROM stonks.ohlcv_daily AS source
                WHERE source.provider_listing_id = ANY(%s::uuid[])
            ), compared AS (
                SELECT
                    COALESCE(source.provider_listing_id,
                             payload.provider_listing_id) AS listing_id,
                    source.trading_date AS source_date,
                    payload.trading_date AS payload_date,
                    source.open AS source_open, payload.open AS payload_open,
                    source.high AS source_high, payload.high AS payload_high,
                    source.low AS source_low, payload.low AS payload_low,
                    source.close AS source_close, payload.close AS payload_close,
                    source.volume AS source_volume, payload.volume AS payload_volume,
                    source.history_observation_count AS source_history_count,
                    payload.history_observation_count AS payload_history_count,
                    payload.calculation_version,
                    payload.relative_strength_benchmark_provider_listing_id
                FROM source
                FULL JOIN {slot.table_name} AS payload
                  ON payload.provider_listing_id = source.provider_listing_id
                 AND payload.trading_date = source.trading_date
                WHERE COALESCE(source.provider_listing_id,
                               payload.provider_listing_id) = ANY(%s::uuid[])
            )
            SELECT
                listing_id,
                count(*) FILTER (WHERE source_date IS NOT NULL),
                min(source_date), max(source_date),
                count(*) FILTER (WHERE payload_date IS NOT NULL),
                count(*) FILTER (
                    WHERE source_date IS NULL OR payload_date IS NULL
                       OR source_open IS DISTINCT FROM payload_open
                       OR source_high IS DISTINCT FROM payload_high
                       OR source_low IS DISTINCT FROM payload_low
                       OR source_close IS DISTINCT FROM payload_close
                       OR source_volume IS DISTINCT FROM payload_volume
                       OR source_history_count IS DISTINCT FROM payload_history_count
                       OR calculation_version IS DISTINCT FROM %s
                ),
                count(DISTINCT relative_strength_benchmark_provider_listing_id)
                    FILTER (
                        WHERE relative_strength_benchmark_provider_listing_id
                              IS NOT NULL
                    ),
                (array_agg(
                    DISTINCT relative_strength_benchmark_provider_listing_id
                ) FILTER (
                    WHERE relative_strength_benchmark_provider_listing_id
                          IS NOT NULL
                ))[1]
            FROM compared
            GROUP BY listing_id
            ORDER BY listing_id
            """,
            (listing_ids, listing_ids, publication.calculation_version),
        )
        facts = {row[0]: row[1:] for row in cursor.fetchall()}
        membership_by_id = {row[0]: row for row in memberships}
        for listing_id in listing_ids:
            membership = membership_by_id[listing_id]
            row = facts.get(listing_id)
            expected_benchmark = membership[8]
            if (
                row is None
                or row[0] != membership[6]
                or row[1] != membership[4]
                or row[2] != membership[5]
                or row[3] != membership[7]
                or row[4] != 0
                or row[5] != (1 if expected_benchmark is not None else 0)
                or row[6] != expected_benchmark
            ):
                raise TechIndicatorsWorkflowError(
                    "Candidate payload is not a complete current source image."
                )


def _publish_memberships(
    cursor: Any, publication: _Publication, listing_ids: tuple[UUID, ...]
) -> None:
    cursor.execute(
        """
        UPDATE stonks.tech_indicators_publication_listing
        SET is_active = false,
            deactivated_at = clock_timestamp(),
            updated_at = clock_timestamp()
        WHERE is_active
          AND provider_listing_id = ANY(%s::uuid[])
        """,
        (list(listing_ids),),
    )
    cursor.execute(
        """
        UPDATE stonks.tech_indicators_publication
        SET status = 'PUBLISHED',
            published_at = clock_timestamp(),
            updated_at = clock_timestamp()
        WHERE publication_id = %s
          AND status = 'PREPARED'
        RETURNING publication_id
        """,
        (publication.publication_id,),
    )
    if cursor.fetchone() is None:
        raise TechIndicatorsWorkflowError(
            "Prepared publication changed during finalization."
        )
    cursor.execute(
        """
        UPDATE stonks.tech_indicators_publication_listing
        SET is_active = true,
            activated_at = clock_timestamp(),
            updated_at = clock_timestamp()
        WHERE publication_id = %s
          AND NOT is_active
          AND activated_at IS NULL
        RETURNING provider_listing_id
        """,
        (publication.publication_id,),
    )
    if len(cursor.fetchall()) != len(listing_ids):
        raise TechIndicatorsWorkflowError(
            "Publication membership activation was incomplete."
        )


def _require_published_memberships(
    cursor: Any, publication: _Publication, listing_ids: tuple[UUID, ...]
) -> None:
    cursor.execute(
        """
        SELECT provider_listing_id
        FROM stonks.tech_indicators_publication_listing
        WHERE publication_id = %s AND is_active
        ORDER BY provider_listing_id
        """,
        (publication.publication_id,),
    )
    if tuple(row[0] for row in cursor.fetchall()) != listing_ids:
        raise TechIndicatorsWorkflowError(
            "Published recovery result does not own the requested active scope."
        )


def _result(
    publication: _Publication, *, already_published: bool
) -> PublicationFinalizationResult:
    return PublicationFinalizationResult(
        publication_id=publication.publication_id,
        published=True,
        already_published=already_published,
        publication_method=publication.publication_method or "",
        activated_listing_count=publication.expected_listing_count or 0,
        inserted_row_count=publication.inserted_row_count or 0,
        updated_row_count=publication.updated_row_count or 0,
        deleted_row_count=publication.deleted_row_count or 0,
        equivalent_row_count=publication.equivalent_row_count or 0,
    )


__all__ = [
    "InPlaceSlotChanges",
    "PublicationFinalizationResult",
    "PublicationRecoveryAction",
    "PublicationRecoveryDecision",
    "PublicationSlotSelection",
    "TECH_INDICATORS_WRITER_LOCK_KEY",
    "TECH_INDICATORS_WRITER_LOCK_SEED",
    "fail_unpublished_publication",
    "finalize_publication",
    "inspect_publication_recovery",
    "select_inactive_payload_slots",
]
