"""Read-only SEC inputs for provisional-security reconciliation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping
from uuid import UUID

from empire_core.db.postgres import row_to_dict

from empire_stonks_securities.issuers import ELIGIBLE_SEC_OBSERVATION_PROVIDERS
from empire_stonks_securities.reconciliation_audit import IDENTITY_STATUS_PROVISIONAL


@dataclass(frozen=True)
class ReconciliationIdentifier:
    """One canonical issuer or security identifier available to the collector."""

    identifier_id: UUID
    id_type: str
    id_value: str
    valid_from: date | None
    valid_to: date | None
    source_code: str | None
    confidence_code: str


@dataclass(frozen=True)
class ReconciliationListing:
    """One listing attached to a provisional security."""

    listing_id: UUID
    exchange_id: UUID
    exchange_code: str
    ticker_norm: str | None
    status: str
    valid_from: date | None
    valid_to: date | None
    first_seen: date | None
    last_seen: date | None


@dataclass(frozen=True)
class SecReconciliationSupportingObservation:
    """SEC observation and provider-evidence lineage supporting a security."""

    provider_evidence_id: UUID
    provider_observation_id: UUID
    provider_code: str
    provider_date: date | None
    observed_at: datetime | None
    summary_json: Mapping[str, Any]
    source_snapshot_id: UUID | None
    source_code: str | None
    content_sha256: str | None
    snapshot_created_at: datetime | None


@dataclass(frozen=True)
class ProvisionalSecurityEvidenceInput:
    """All read-only SEC evidence inputs for one provisional security.

    This bundle intentionally contains no derived-evidence key or decision.
    E3.5 owns writing immutable summaries after this query layer has selected
    the stable source trail.
    """

    security_id: UUID
    issuer_id: UUID | None
    issuer_cik: str | None
    security_title: str
    instrument_type_code: str
    first_seen: date | None
    last_seen: date | None
    issuer_identifiers: tuple[ReconciliationIdentifier, ...]
    security_identifiers: tuple[ReconciliationIdentifier, ...]
    listings: tuple[ReconciliationListing, ...]
    supporting_observations: tuple[SecReconciliationSupportingObservation, ...]


def select_provisional_security_evidence_inputs(
    *,
    connection: Any,
    limit: int | None = None,
) -> list[ProvisionalSecurityEvidenceInput]:
    """Select deterministic SEC lineage and canonical context for provisional securities.

    The query deliberately does not inspect derived reconciliation evidence.
    Selecting the same source facts on every invocation is what lets the next
    writer stage derive the same immutable evidence keys on a rerun.
    """

    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")

    sql = """
        WITH provisional_security AS (
            SELECT
                s.security_id,
                s.issuer_id,
                s.security_title,
                s.instrument_type_code,
                s.first_seen,
                s.last_seen
            FROM stonks.security s
            WHERE s.identity_status = %s
            ORDER BY s.last_seen DESC NULLS LAST, s.security_id
        )
        SELECT
            s.security_id,
            s.issuer_id,
            i.cik AS issuer_cik,
            s.security_title,
            s.instrument_type_code,
            s.first_seen,
            s.last_seen,
            issuer_identifiers.identifiers AS issuer_identifiers,
            security_identifiers.identifiers AS security_identifiers,
            listings.listings AS listings,
            support.observations AS supporting_observations
        FROM provisional_security s
        LEFT JOIN stonks.issuer i ON i.issuer_id = s.issuer_id
        LEFT JOIN LATERAL (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'identifier_id', ii.issuer_identifier_id,
                        'id_type', ii.id_type,
                        'id_value', ii.id_value,
                        'valid_from', ii.valid_from,
                        'valid_to', ii.valid_to,
                        'source_code', ii.source_code,
                        'confidence_code', ii.confidence_code
                    )
                    ORDER BY ii.id_type, ii.id_value, ii.valid_from NULLS FIRST,
                        ii.issuer_identifier_id
                ),
                '[]'::jsonb
            ) AS identifiers
            FROM stonks.issuer_identifier ii
            WHERE ii.issuer_id = s.issuer_id
        ) issuer_identifiers ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'identifier_id', si.security_identifier_id,
                        'id_type', si.id_type,
                        'id_value', si.id_value,
                        'valid_from', si.valid_from,
                        'valid_to', si.valid_to,
                        'source_code', si.source_code,
                        'confidence_code', si.confidence_code
                    )
                    ORDER BY si.id_type, si.id_value, si.valid_from NULLS FIRST,
                        si.security_identifier_id
                ),
                '[]'::jsonb
            ) AS identifiers
            FROM stonks.security_identifier si
            WHERE si.security_id = s.security_id
        ) security_identifiers ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'listing_id', l.listing_id,
                        'exchange_id', l.exchange_id,
                        'exchange_code', e.exchange_code,
                        'ticker_norm', l.ticker_norm,
                        'status', l.status,
                        'valid_from', l.valid_from,
                        'valid_to', l.valid_to,
                        'first_seen', l.first_seen,
                        'last_seen', l.last_seen
                    )
                    ORDER BY l.last_seen DESC NULLS LAST, l.listing_id
                ),
                '[]'::jsonb
            ) AS listings
            FROM stonks.listing l
            JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
            WHERE l.security_id = s.security_id
        ) listings ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'provider_evidence_id', pe.provider_evidence_id,
                        'provider_observation_id', po.provider_observation_id,
                        'provider_code', po.provider_code,
                        'provider_date', po.provider_date,
                        'observed_at', po.observed_at,
                        'summary_json', po.summary_json,
                        'source_snapshot_id', pss.source_snapshot_id,
                        'source_code', pss.source_code,
                        'content_sha256', pss.content_sha256,
                        'snapshot_created_at', pss.created_at
                    )
                    ORDER BY po.observed_at NULLS LAST, po.created_at,
                        pe.provider_evidence_id
                ),
                '[]'::jsonb
            ) AS observations
            FROM stonks.provider_evidence pe
            JOIN stonks.provider_observation po
                ON po.provider_observation_id = pe.provider_observation_id
            LEFT JOIN stonks.provider_source_snapshot pss
                ON pss.source_snapshot_id = po.source_snapshot_id
            WHERE pe.security_id = s.security_id
              AND po.provider_code = ANY(%s)
        ) support ON TRUE
        ORDER BY s.last_seen DESC NULLS LAST, s.security_id
    """
    params: list[Any] = [IDENTITY_STATUS_PROVISIONAL, list(ELIGIBLE_SEC_OBSERVATION_PROVIDERS)]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return [_input_from_row(row_to_dict(cursor, row)) for row in cursor.fetchall()]


def _input_from_row(row: Mapping[str, Any]) -> ProvisionalSecurityEvidenceInput:
    return ProvisionalSecurityEvidenceInput(
        security_id=row["security_id"],
        issuer_id=row["issuer_id"],
        issuer_cik=row["issuer_cik"],
        security_title=row["security_title"],
        instrument_type_code=row["instrument_type_code"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        issuer_identifiers=tuple(
            _identifier_from_row(value) for value in row["issuer_identifiers"]
        ),
        security_identifiers=tuple(
            _identifier_from_row(value) for value in row["security_identifiers"]
        ),
        listings=tuple(_listing_from_row(value) for value in row["listings"]),
        supporting_observations=tuple(
            _supporting_observation_from_row(value)
            for value in row["supporting_observations"]
        ),
    )


def _identifier_from_row(row: Mapping[str, Any]) -> ReconciliationIdentifier:
    return ReconciliationIdentifier(
        identifier_id=row["identifier_id"],
        id_type=row["id_type"],
        id_value=row["id_value"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        source_code=row["source_code"],
        confidence_code=row["confidence_code"],
    )


def _listing_from_row(row: Mapping[str, Any]) -> ReconciliationListing:
    return ReconciliationListing(
        listing_id=row["listing_id"],
        exchange_id=row["exchange_id"],
        exchange_code=row["exchange_code"],
        ticker_norm=row["ticker_norm"],
        status=row["status"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
    )


def _supporting_observation_from_row(
    row: Mapping[str, Any],
) -> SecReconciliationSupportingObservation:
    return SecReconciliationSupportingObservation(
        provider_evidence_id=row["provider_evidence_id"],
        provider_observation_id=row["provider_observation_id"],
        provider_code=row["provider_code"],
        provider_date=row["provider_date"],
        observed_at=row["observed_at"],
        summary_json=row["summary_json"],
        source_snapshot_id=row["source_snapshot_id"],
        source_code=row["source_code"],
        content_sha256=row["content_sha256"],
        snapshot_created_at=row["snapshot_created_at"],
    )
