"""Read-only SEC inputs for provisional-security reconciliation evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping
from uuid import UUID

from empire_core.db.postgres import json_dumps, row_to_dict

from empire_stonks_securities.issuers import ELIGIBLE_SEC_OBSERVATION_PROVIDERS
from empire_stonks_securities.reconciliation_audit import IDENTITY_STATUS_PROVISIONAL


RECONCILIATION_EVIDENCE_COLLECTOR_VERSION = "sec-v1"
EVIDENCE_TYPE_SEC_ISSUER_SECURITY_MATCH = "SEC_ISSUER_SECURITY_MATCH"
EVIDENCE_TYPE_SEC_TICKER_EXCHANGE_STABILITY = "SEC_TICKER_EXCHANGE_STABILITY"
EVIDENCE_TYPE_SEC_SOURCE_SNAPSHOT_CONTINUITY = "SEC_SOURCE_SNAPSHOT_CONTINUITY"
EVIDENCE_ROLE_SUPPORTS = "SUPPORTS"


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


@dataclass(frozen=True)
class DerivedSecurityReconciliationEvidence:
    """One immutable, derived SEC evidence summary ready for persistence."""

    security_id: UUID
    issuer_id: UUID | None
    listing_id: UUID | None
    evidence_type: str
    evidence_role: str
    evidence_key: str
    summary_json: Mapping[str, Any]
    provider_evidence_ids: tuple[UUID, ...]
    source_snapshot_ids: tuple[UUID, ...]
    collector_version: str = RECONCILIATION_EVIDENCE_COLLECTOR_VERSION


@dataclass(frozen=True)
class DerivedEvidenceWriteResult:
    """Identity and insertion status for one immutable evidence write."""

    reconciliation_evidence_id: UUID
    inserted: bool


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


def derive_security_reconciliation_evidence(
    evidence_input: ProvisionalSecurityEvidenceInput,
    *,
    collector_version: str = RECONCILIATION_EVIDENCE_COLLECTOR_VERSION,
) -> tuple[DerivedSecurityReconciliationEvidence, ...]:
    """Derive deterministic SEC evidence summaries without writing to the database.

    This first collector intentionally emits only evidence whose source facts
    are available in the SEC ticker inputs.  Series/class evidence remains a
    placeholder until that SEC source exists.
    """

    if not collector_version.strip():
        raise ValueError("collector_version is required")

    observations = tuple(
        sorted(
            evidence_input.supporting_observations,
            key=lambda item: (
                item.observed_at.isoformat() if item.observed_at is not None else "",
                str(item.provider_evidence_id),
            ),
        )
    )
    derived: list[DerivedSecurityReconciliationEvidence] = []

    issuer_cik = _normalize_cik(evidence_input.issuer_cik)
    issuer_matches = tuple(
        item
        for item in observations
        if issuer_cik is not None and _observation_cik(item) == issuer_cik
    )
    if evidence_input.issuer_id is not None and issuer_matches:
        derived.append(
            _derived_evidence(
                evidence_input=evidence_input,
                evidence_type=EVIDENCE_TYPE_SEC_ISSUER_SECURITY_MATCH,
                listing_id=None,
                observations=issuer_matches,
                normalized_values={
                    "issuer_cik": issuer_cik,
                    "tickers": sorted(
                        {ticker for item in issuer_matches if (ticker := _observation_ticker(item))}
                    ),
                },
                collector_version=collector_version,
            )
        )

    for listing in evidence_input.listings:
        ticker = _normalize_ticker(listing.ticker_norm)
        exchange = _normalize_exchange(listing.exchange_code)
        if ticker is None or exchange is None:
            continue
        matching = tuple(
            item
            for item in observations
            if _observation_ticker(item) == ticker and _observation_exchange(item) == exchange
        )
        if matching:
            snapshot_ids = _source_snapshot_ids(matching)
            derived.append(
                _derived_evidence(
                    evidence_input=evidence_input,
                    evidence_type=EVIDENCE_TYPE_SEC_TICKER_EXCHANGE_STABILITY,
                    listing_id=listing.listing_id,
                    observations=matching,
                    normalized_values={
                        "ticker": ticker,
                        "exchange": exchange,
                        "distinct_snapshot_count": len(snapshot_ids),
                        "insufficient_repeat": len(snapshot_ids) < 2,
                    },
                    collector_version=collector_version,
                )
            )

            # Continuity is source-specific: two providers or SEC source files
            # must not be presented as one continuous source mapping.
            by_source: dict[tuple[str, str | None], list[SecReconciliationSupportingObservation]] = {}
            for item in matching:
                if item.source_snapshot_id is not None:
                    by_source.setdefault((item.provider_code, item.source_code), []).append(item)
            for (provider_code, source_code), source_observations in sorted(by_source.items()):
                derived.append(
                    _derived_evidence(
                        evidence_input=evidence_input,
                        evidence_type=EVIDENCE_TYPE_SEC_SOURCE_SNAPSHOT_CONTINUITY,
                        listing_id=listing.listing_id,
                        observations=tuple(source_observations),
                        normalized_values={
                            "issuer_cik": issuer_cik,
                            "ticker": ticker,
                            "exchange": exchange,
                            "provider_code": provider_code,
                            "source_code": source_code,
                            "distinct_snapshot_count": len(_source_snapshot_ids(source_observations)),
                        },
                        collector_version=collector_version,
                    )
                )

    return tuple(sorted(derived, key=lambda item: (item.evidence_type, str(item.listing_id), item.evidence_key)))


def write_derived_security_reconciliation_evidence(
    *,
    connection: Any,
    evidence: DerivedSecurityReconciliationEvidence,
) -> DerivedEvidenceWriteResult:
    """Persist immutable evidence and its lineage idempotently in one transaction."""

    if not evidence.provider_evidence_ids:
        raise ValueError("derived evidence requires provider_evidence_ids")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO stonks.security_reconciliation_evidence (
                security_id, issuer_id, listing_id, evidence_type, evidence_role,
                evidence_key, summary_json, collector_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT ON CONSTRAINT uq_sec_recon_evidence_identity DO NOTHING
            RETURNING reconciliation_evidence_id
            """,
            (
                evidence.security_id, evidence.issuer_id, evidence.listing_id,
                evidence.evidence_type, evidence.evidence_role, evidence.evidence_key,
                json_dumps(dict(evidence.summary_json)), evidence.collector_version,
            ),
        )
        row = cursor.fetchone()
        inserted = row is not None
        if row is None:
            cursor.execute(
                """
                SELECT reconciliation_evidence_id
                FROM stonks.security_reconciliation_evidence
                WHERE security_id = %s AND evidence_type = %s AND evidence_key = %s
                """,
                (evidence.security_id, evidence.evidence_type, evidence.evidence_key),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("derived evidence conflict did not return an existing row")
        reconciliation_evidence_id = row[0]
        for provider_evidence_id in evidence.provider_evidence_ids:
            cursor.execute(
                """
                INSERT INTO stonks.security_reconciliation_evidence_provider_evidence (
                    reconciliation_evidence_id, provider_evidence_id
                ) VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                (reconciliation_evidence_id, provider_evidence_id),
            )
        for source_snapshot_id in evidence.source_snapshot_ids:
            cursor.execute(
                """
                INSERT INTO stonks.security_reconciliation_evidence_source_snapshot (
                    reconciliation_evidence_id, source_snapshot_id
                ) VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                (reconciliation_evidence_id, source_snapshot_id),
            )
    connection.commit()
    return DerivedEvidenceWriteResult(reconciliation_evidence_id, inserted)


def _derived_evidence(
    *, evidence_input: ProvisionalSecurityEvidenceInput, evidence_type: str,
    listing_id: UUID | None, observations: tuple[SecReconciliationSupportingObservation, ...],
    normalized_values: Mapping[str, Any], collector_version: str,
) -> DerivedSecurityReconciliationEvidence:
    provider_evidence_ids = tuple(sorted({item.provider_evidence_id for item in observations}, key=str))
    source_snapshot_ids = _source_snapshot_ids(observations)
    observed_times = [item.observed_at for item in observations if item.observed_at is not None]
    summary = {
        "evidence_type": evidence_type,
        "normalized_values": dict(normalized_values),
        "provider_evidence_count": len(provider_evidence_ids),
        "source_snapshot_ids": [str(item) for item in source_snapshot_ids],
        "first_observed_at": min(observed_times).isoformat() if observed_times else None,
        "last_observed_at": max(observed_times).isoformat() if observed_times else None,
    }
    key_input = {
        "collector_version": collector_version,
        "security_id": str(evidence_input.security_id),
        "issuer_id": str(evidence_input.issuer_id) if evidence_input.issuer_id else None,
        "listing_id": str(listing_id) if listing_id else None,
        "evidence_type": evidence_type,
        "normalized_values": normalized_values,
        "provider_evidence_ids": [str(item) for item in provider_evidence_ids],
        "source_snapshot_ids": [str(item) for item in source_snapshot_ids],
    }
    return DerivedSecurityReconciliationEvidence(
        security_id=evidence_input.security_id, issuer_id=evidence_input.issuer_id,
        listing_id=listing_id, evidence_type=evidence_type, evidence_role=EVIDENCE_ROLE_SUPPORTS,
        evidence_key=_evidence_key(key_input), summary_json=summary,
        provider_evidence_ids=provider_evidence_ids, source_snapshot_ids=source_snapshot_ids,
        collector_version=collector_version,
    )


def _source_snapshot_ids(observations: Any) -> tuple[UUID, ...]:
    return tuple(sorted({item.source_snapshot_id for item in observations if item.source_snapshot_id}, key=str))


def _observation_cik(item: SecReconciliationSupportingObservation) -> str | None:
    return _normalize_cik(item.summary_json.get("cik_padded") or item.summary_json.get("cik"))


def _observation_ticker(item: SecReconciliationSupportingObservation) -> str | None:
    return _normalize_ticker(item.summary_json.get("ticker_norm") or item.summary_json.get("ticker"))


def _observation_exchange(item: SecReconciliationSupportingObservation) -> str | None:
    return _normalize_exchange(item.summary_json.get("exchange_code") or item.summary_json.get("exchange"))


def _normalize_cik(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text.zfill(10) if text.isdigit() else None


def _normalize_ticker(value: Any) -> str | None:
    text = str(value).strip().upper() if value is not None else ""
    return text or None


def _normalize_exchange(value: Any) -> str | None:
    text = str(value).strip().upper() if value is not None else ""
    return text or None


def _evidence_key(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> str:
    if isinstance(value, (UUID, date, datetime)):
        return value.isoformat()
    raise TypeError(f"unsupported evidence key value: {type(value)!r}")


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
