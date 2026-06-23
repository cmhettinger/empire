"""Upsert provisional securities from SEC ticker observations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable
from uuid import UUID

from empire_core.db.postgres import row_to_dict

from empire_stonks_securities.issuers import ELIGIBLE_SEC_OBSERVATION_PROVIDERS
from empire_stonks_securities.symbols import normalize_sec_ticker


logger = logging.getLogger(__name__)

# Phase 2A SEC ticker files do not prove durable security identity or instrument
# type. These constants mark rows as provisional bootstrap records that later
# reconciliation/backfill can promote when stronger identifiers or type evidence
# arrive.
PROVISIONAL_INSTRUMENT_TYPE = "UNKNOWN"
TICKER_IDENTIFIER_TYPE = "TICKER"
SECURITY_IDENTIFIER_CONFIDENCE = "MEDIUM"
SECURITY_EVIDENCE_ROLE = "CREATED_FROM"


class SecSecurityUpsertError(ValueError):
    """Raised when a security upsert input is invalid."""


@dataclass(frozen=True)
class SecSecurityObservation:
    """Provider observation input for provisional security upserts."""

    provider_observation_id: UUID
    provider_code: str
    provider_date: date | None
    observed_at: datetime | None
    summary_json: dict[str, Any]


@dataclass(frozen=True)
class SecSecurityUpsertResult:
    """Counts from one SEC provisional security upsert run."""

    observations_scanned: int = 0
    observations_skipped: int = 0
    issuers_resolved: int = 0
    issuers_missing: int = 0
    securities_created: int = 0
    securities_updated: int = 0
    security_identifiers_inserted: int = 0
    security_identifiers_skipped: int = 0
    evidence_inserted: int = 0
    evidence_skipped: int = 0
    warning_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "observations_scanned": self.observations_scanned,
            "observations_skipped": self.observations_skipped,
            "issuers_resolved": self.issuers_resolved,
            "issuers_missing": self.issuers_missing,
            "securities_created": self.securities_created,
            "securities_updated": self.securities_updated,
            "security_identifiers_inserted": self.security_identifiers_inserted,
            "security_identifiers_skipped": self.security_identifiers_skipped,
            "evidence_inserted": self.evidence_inserted,
            "evidence_skipped": self.evidence_skipped,
            "warning_count": self.warning_count,
        }


@dataclass(frozen=True)
class _SecurityUpsertOutcome:
    security_id: UUID
    created: bool
    updated: bool


def upsert_sec_securities_from_provider_observations(
    *,
    connection: Any,
    source_run_id: str | UUID | None = None,
    limit: int | None = None,
) -> SecSecurityUpsertResult:
    """Select eligible SEC ticker observations and upsert provisional securities."""

    observations = select_sec_security_observations(
        connection=connection,
        source_run_id=source_run_id,
        limit=limit,
    )
    result = upsert_sec_securities(connection=connection, observations=observations)
    logger.info(
        "Completed SEC security upsert: observations_scanned=%s observations_skipped=%s "
        "issuers_resolved=%s issuers_missing=%s securities_created=%s securities_updated=%s "
        "security_identifiers_inserted=%s security_identifiers_skipped=%s "
        "evidence_inserted=%s evidence_skipped=%s warning_count=%s",
        result.observations_scanned,
        result.observations_skipped,
        result.issuers_resolved,
        result.issuers_missing,
        result.securities_created,
        result.securities_updated,
        result.security_identifiers_inserted,
        result.security_identifiers_skipped,
        result.evidence_inserted,
        result.evidence_skipped,
        result.warning_count,
    )
    return result


def select_sec_security_observations(
    *,
    connection: Any,
    source_run_id: str | UUID | None = None,
    limit: int | None = None,
) -> list[SecSecurityObservation]:
    """Fetch SEC ticker observations that still require security reconciliation."""

    params: list[Any] = [list(ELIGIBLE_SEC_OBSERVATION_PROVIDERS)]
    sql = """
        SELECT
            po.provider_observation_id,
            po.provider_code,
            po.provider_date,
            po.observed_at,
            po.summary_json
        FROM stonks.provider_observation po
        WHERE po.provider_code = ANY(%s)
          AND (
              %s::uuid IS NULL
              OR EXISTS (
                  SELECT 1
                  FROM core.stored_object so
                  LEFT JOIN stonks.provider_source_snapshot_object psso
                    ON psso.object_id = so.object_id
                  WHERE so.run_id = %s::uuid
                    AND so.object_kind = 'sec_source_file'
                    AND (
                        psso.source_snapshot_id = po.source_snapshot_id
                        OR (
                            po.source_snapshot_id IS NULL
                            AND (
                                so.object_id = po.object_id
                                OR so.checksum_sha256 = po.summary_json #>> '{source_file,sha256}'
                                OR so.object_key = po.summary_json #>> '{source_file,object_key}'
                            )
                        )
                    )
              )
          )
          AND NOT EXISTS (
              SELECT 1
              FROM stonks.provider_evidence pe
              WHERE pe.provider_observation_id = po.provider_observation_id
                AND pe.security_id IS NOT NULL
                AND pe.listing_id IS NULL
                AND pe.event_id IS NULL
                AND pe.created_at >= po.created_at
          )
        ORDER BY po.observed_at NULLS LAST, po.created_at, po.provider_observation_id
    """
    params.extend([source_run_id, source_run_id])
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return [_observation_from_row(cursor, row) for row in cursor.fetchall()]


def upsert_sec_securities(
    *,
    connection: Any,
    observations: Iterable[SecSecurityObservation],
) -> SecSecurityUpsertResult:
    """Upsert issuer-linked provisional securities, ticker identifiers, and evidence."""

    counts = _MutableSecurityCounts()
    with connection.cursor() as cursor:
        for observation in observations:
            counts.observations_scanned += 1
            parsed = _parse_observation(observation)
            if parsed is None:
                counts.observations_skipped += 1
                counts.warning_count += 1
                continue

            issuer_id = _resolve_issuer_id(
                cursor=cursor,
                provider_observation_id=observation.provider_observation_id,
                cik_padded=parsed["cik_padded"],
            )
            if issuer_id is None:
                counts.observations_skipped += 1
                counts.issuers_missing += 1
                counts.warning_count += 1
                logger.warning(
                    "Skipping SEC security observation without issuer: "
                    "provider_observation_id=%s cik_padded=%s ticker_norm=%s",
                    observation.provider_observation_id,
                    parsed["cik_padded"],
                    parsed["ticker_norm"],
                )
                continue
            counts.issuers_resolved += 1

            security = _upsert_provisional_security_from_sec_ticker(
                cursor=cursor,
                issuer_id=issuer_id,
                ticker_norm=parsed["ticker_norm"],
                company_name=parsed["company_name"],
                seen_date=parsed["seen_date"],
            )
            counts.securities_created += int(security.created)
            counts.securities_updated += int(security.updated)

            if _insert_security_identifier(
                cursor=cursor,
                security_id=security.security_id,
                ticker_norm=parsed["ticker_norm"],
                provider_code=observation.provider_code,
                valid_from=parsed["seen_date"],
            ):
                counts.security_identifiers_inserted += 1
            else:
                counts.security_identifiers_skipped += 1

            if _insert_provider_evidence(
                cursor=cursor,
                provider_observation_id=observation.provider_observation_id,
                issuer_id=issuer_id,
                security_id=security.security_id,
                ticker_norm=parsed["ticker_norm"],
            ):
                counts.evidence_inserted += 1
            else:
                counts.evidence_skipped += 1

    connection.commit()
    return counts.to_result()


def _resolve_issuer_id(
    *,
    cursor: Any,
    provider_observation_id: UUID,
    cik_padded: str,
) -> UUID | None:
    cursor.execute(
        """
        SELECT issuer_id
        FROM stonks.provider_evidence
        WHERE provider_observation_id = %s
          AND issuer_id IS NOT NULL
          AND security_id IS NULL
          AND listing_id IS NULL
          AND event_id IS NULL
        ORDER BY created_at
        LIMIT 1
        """,
        (provider_observation_id,),
    )
    row = cursor.fetchone()
    if row is not None:
        return row[0]

    cursor.execute(
        """
        SELECT issuer_id
        FROM stonks.issuer
        WHERE cik = %s
        """,
        (cik_padded,),
    )
    row = cursor.fetchone()
    return row[0] if row is not None else None


def _upsert_provisional_security_from_sec_ticker(
    *,
    cursor: Any,
    issuer_id: UUID,
    ticker_norm: str,
    company_name: str | None,
    seen_date: date | None,
) -> _SecurityUpsertOutcome:
    """Resolve/create a provisional current-state security from weak SEC ticker evidence.

    This resolver intentionally preserves the Phase 2A behavior of one
    provisional security per issuer/current observed ticker. Ticker is recorded
    as medium-confidence evidence, not permanent identity. Future backfill or
    security-type enrichment should add stronger identifiers and reconcile or
    promote these provisional records outside this bootstrap resolver.
    """

    security = _find_security_by_issuer_ticker(
        cursor=cursor,
        issuer_id=issuer_id,
        ticker_norm=ticker_norm,
    )
    if security is None:
        title = company_name or f"SEC ticker {ticker_norm}"
        cursor.execute(
            """
            INSERT INTO stonks.security (
                issuer_id,
                instrument_type_code,
                security_title,
                first_seen,
                last_seen
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING security_id
            """,
            (issuer_id, PROVISIONAL_INSTRUMENT_TYPE, title, seen_date, seen_date),
        )
        return _SecurityUpsertOutcome(
            security_id=cursor.fetchone()[0],
            created=True,
            updated=False,
        )

    security_id = security["security_id"]
    current_title = _clean_text(security.get("security_title"))
    should_update_title = bool(company_name) and current_title != company_name
    should_update_last_seen = (
        seen_date is not None
        and (security.get("last_seen") is None or security["last_seen"] < seen_date)
    )
    if should_update_title or should_update_last_seen:
        cursor.execute(
            """
            UPDATE stonks.security
            SET
                security_title = CASE WHEN %s::text IS NULL THEN security_title ELSE %s END,
                last_seen = CASE
                    WHEN %s::date IS NULL THEN last_seen
                    ELSE GREATEST(COALESCE(last_seen, %s), %s)
                END,
                updated_at = now()
            WHERE security_id = %s
            """,
            (
                company_name if should_update_title else None,
                company_name if should_update_title else None,
                seen_date if should_update_last_seen else None,
                seen_date,
                seen_date,
                security_id,
            ),
        )
    return _SecurityUpsertOutcome(
        security_id=security_id,
        created=False,
        updated=bool(should_update_title or should_update_last_seen),
    )


def _find_security_by_issuer_ticker(
    *,
    cursor: Any,
    issuer_id: UUID,
    ticker_norm: str,
) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT s.security_id, s.issuer_id, s.instrument_type_code, s.security_title, s.last_seen
        FROM stonks.security s
        JOIN stonks.security_identifier si
          ON si.security_id = s.security_id
        WHERE s.issuer_id = %s
          AND si.id_type = 'TICKER'
          AND si.id_value = %s
        ORDER BY s.created_at
        LIMIT 1
        """,
        (issuer_id, ticker_norm),
    )
    row = cursor.fetchone()
    return row_to_dict(cursor, row) if row is not None else None


def _insert_security_identifier(
    *,
    cursor: Any,
    security_id: UUID,
    ticker_norm: str,
    provider_code: str,
    valid_from: date | None,
) -> bool:
    cursor.execute(
        """
        INSERT INTO stonks.security_identifier (
            security_id,
            id_type,
            id_value,
            valid_from,
            provider_code,
            confidence_code
        )
        VALUES (%s, 'TICKER', %s, %s, %s, %s)
        ON CONFLICT ON CONSTRAINT uq_security_identifier
        DO NOTHING
        RETURNING security_identifier_id
        """,
        (
            security_id,
            ticker_norm,
            valid_from,
            provider_code,
            SECURITY_IDENTIFIER_CONFIDENCE,
        ),
    )
    return cursor.fetchone() is not None


def _insert_provider_evidence(
    *,
    cursor: Any,
    provider_observation_id: UUID,
    issuer_id: UUID,
    security_id: UUID,
    ticker_norm: str,
) -> bool:
    cursor.execute(
        """
        SELECT provider_evidence_id
        FROM stonks.provider_evidence
        WHERE provider_observation_id = %s
          AND security_id = %s
          AND listing_id IS NULL
          AND event_id IS NULL
        LIMIT 1
        """,
        (provider_observation_id, security_id),
    )
    if cursor.fetchone() is not None:
        return False

    cursor.execute(
        """
        INSERT INTO stonks.provider_evidence (
            provider_observation_id,
            issuer_id,
            security_id,
            evidence_role,
            notes
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING provider_evidence_id
        """,
        (
            provider_observation_id,
            issuer_id,
            security_id,
            SECURITY_EVIDENCE_ROLE,
            f"SEC ticker {ticker_norm} observed for issuer; provisional security identity.",
        ),
    )
    return cursor.fetchone() is not None


def _parse_observation(observation: SecSecurityObservation) -> dict[str, Any] | None:
    summary = observation.summary_json or {}
    cik_padded = _cik_padded(summary.get("cik_padded") or summary.get("cik"))
    ticker_norm = _clean_text(summary.get("ticker_norm") or summary.get("ticker"))
    if ticker_norm is not None:
        ticker_norm = normalize_sec_ticker(ticker_norm).normalized_symbol
    if cik_padded is None or ticker_norm is None:
        logger.warning(
            "Skipping SEC security observation without valid CIK/ticker: "
            "provider_observation_id=%s",
            observation.provider_observation_id,
        )
        return None
    return {
        "cik_padded": cik_padded,
        "ticker_norm": ticker_norm,
        "company_name": _clean_text(summary.get("company_name")),
        "seen_date": observation.provider_date or _date_from_datetime(observation.observed_at),
    }


def _observation_from_row(cursor: Any, row: Any) -> SecSecurityObservation:
    data = row_to_dict(cursor, row)
    summary_json = data["summary_json"] or {}
    if not isinstance(summary_json, dict):
        raise SecSecurityUpsertError("provider_observation.summary_json must be a JSON object")
    return SecSecurityObservation(
        provider_observation_id=data["provider_observation_id"],
        provider_code=data["provider_code"],
        provider_date=data["provider_date"],
        observed_at=data["observed_at"],
        summary_json=summary_json,
    )


def _cik_padded(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return f"{parsed:010d}"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date_from_datetime(value: datetime | None) -> date | None:
    return value.date() if value is not None else None


@dataclass
class _MutableSecurityCounts:
    observations_scanned: int = 0
    observations_skipped: int = 0
    issuers_resolved: int = 0
    issuers_missing: int = 0
    securities_created: int = 0
    securities_updated: int = 0
    security_identifiers_inserted: int = 0
    security_identifiers_skipped: int = 0
    evidence_inserted: int = 0
    evidence_skipped: int = 0
    warning_count: int = 0

    def to_result(self) -> SecSecurityUpsertResult:
        return SecSecurityUpsertResult(
            observations_scanned=self.observations_scanned,
            observations_skipped=self.observations_skipped,
            issuers_resolved=self.issuers_resolved,
            issuers_missing=self.issuers_missing,
            securities_created=self.securities_created,
            securities_updated=self.securities_updated,
            security_identifiers_inserted=self.security_identifiers_inserted,
            security_identifiers_skipped=self.security_identifiers_skipped,
            evidence_inserted=self.evidence_inserted,
            evidence_skipped=self.evidence_skipped,
            warning_count=self.warning_count,
        )
