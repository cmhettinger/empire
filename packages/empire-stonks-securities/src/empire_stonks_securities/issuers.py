"""Upsert issuers from SEC provider observations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable
from uuid import UUID

from empire_core.db.postgres import row_to_dict

from empire_stonks_securities.observations import SEC_SOURCE_PROVIDER_CODES


logger = logging.getLogger(__name__)

CIK_IDENTIFIER_TYPE = "CIK"
SEC_DIRECT_CONFIDENCE = "HIGH"
ISSUER_EVIDENCE_ROLE = "CREATED_FROM"
ELIGIBLE_SEC_OBSERVATION_PROVIDERS = tuple(SEC_SOURCE_PROVIDER_CODES.values())


class SecIssuerUpsertError(ValueError):
    """Raised when an issuer upsert input is invalid."""


@dataclass(frozen=True)
class SecIssuerObservation:
    """Provider observation input for issuer upserts."""

    provider_observation_id: UUID
    provider_code: str
    provider_date: date | None
    observed_at: datetime | None
    summary_json: dict[str, Any]


@dataclass(frozen=True)
class SecIssuerUpsertResult:
    """Counts from one SEC issuer upsert run."""

    observations_scanned: int = 0
    observations_skipped: int = 0
    issuers_created: int = 0
    issuers_updated: int = 0
    issuer_identifiers_inserted: int = 0
    issuer_identifiers_skipped: int = 0
    name_history_inserted: int = 0
    name_history_skipped: int = 0
    evidence_inserted: int = 0
    evidence_skipped: int = 0
    warning_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "observations_scanned": self.observations_scanned,
            "observations_skipped": self.observations_skipped,
            "issuers_created": self.issuers_created,
            "issuers_updated": self.issuers_updated,
            "issuer_identifiers_inserted": self.issuer_identifiers_inserted,
            "issuer_identifiers_skipped": self.issuer_identifiers_skipped,
            "name_history_inserted": self.name_history_inserted,
            "name_history_skipped": self.name_history_skipped,
            "evidence_inserted": self.evidence_inserted,
            "evidence_skipped": self.evidence_skipped,
            "warning_count": self.warning_count,
        }


@dataclass(frozen=True)
class _IssuerUpsertOutcome:
    issuer_id: UUID
    created: bool
    updated: bool


def upsert_sec_issuers_from_provider_observations(
    *,
    connection: Any,
    source_run_id: str | UUID | None = None,
    limit: int | None = None,
) -> SecIssuerUpsertResult:
    """Select eligible SEC ticker observations and upsert issuer identity rows."""

    observations = select_sec_issuer_observations(
        connection=connection,
        source_run_id=source_run_id,
        limit=limit,
    )
    result = upsert_sec_issuers(connection=connection, observations=observations)
    logger.info(
        "Completed SEC issuer upsert: observations_scanned=%s observations_skipped=%s "
        "issuers_created=%s issuers_updated=%s issuer_identifiers_inserted=%s "
        "issuer_identifiers_skipped=%s name_history_inserted=%s name_history_skipped=%s "
        "evidence_inserted=%s evidence_skipped=%s warning_count=%s",
        result.observations_scanned,
        result.observations_skipped,
        result.issuers_created,
        result.issuers_updated,
        result.issuer_identifiers_inserted,
        result.issuer_identifiers_skipped,
        result.name_history_inserted,
        result.name_history_skipped,
        result.evidence_inserted,
        result.evidence_skipped,
        result.warning_count,
    )
    return result


def select_sec_issuer_observations(
    *,
    connection: Any,
    source_run_id: str | UUID | None = None,
    limit: int | None = None,
) -> list[SecIssuerObservation]:
    """Fetch SEC ticker observations that still require issuer reconciliation."""

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
                AND pe.issuer_id IS NOT NULL
                AND pe.security_id IS NULL
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
        rows = cursor.fetchall()
        return [_observation_from_row(cursor, row) for row in rows]


def upsert_sec_issuers(
    *,
    connection: Any,
    observations: Iterable[SecIssuerObservation],
) -> SecIssuerUpsertResult:
    """Upsert issuers, CIK identifiers, name history, and issuer evidence."""

    counts = _MutableIssuerCounts()
    with connection.cursor() as cursor:
        for observation in observations:
            counts.observations_scanned += 1
            parsed = _parse_observation(observation)
            if parsed is None:
                counts.observations_skipped += 1
                counts.warning_count += 1
                continue

            issuer = _upsert_issuer(
                cursor=cursor,
                cik_padded=parsed["cik_padded"],
                company_name=parsed["company_name"],
                seen_date=parsed["seen_date"],
            )
            counts.issuers_created += int(issuer.created)
            counts.issuers_updated += int(issuer.updated)

            if _insert_issuer_identifier(
                cursor=cursor,
                issuer_id=issuer.issuer_id,
                cik_padded=parsed["cik_padded"],
                provider_code=observation.provider_code,
                valid_from=parsed["seen_date"],
            ):
                counts.issuer_identifiers_inserted += 1
            else:
                counts.issuer_identifiers_skipped += 1

            if parsed["company_name"]:
                if _insert_issuer_name_history(
                    cursor=cursor,
                    issuer_id=issuer.issuer_id,
                    company_name=parsed["company_name"],
                    provider_code=observation.provider_code,
                    valid_from=parsed["seen_date"],
                ):
                    counts.name_history_inserted += 1
                else:
                    counts.name_history_skipped += 1
            else:
                counts.name_history_skipped += 1

            if _insert_provider_evidence(
                cursor=cursor,
                provider_observation_id=observation.provider_observation_id,
                issuer_id=issuer.issuer_id,
                cik_padded=parsed["cik_padded"],
            ):
                counts.evidence_inserted += 1
            else:
                counts.evidence_skipped += 1

    connection.commit()
    return counts.to_result()


def _upsert_issuer(
    *,
    cursor: Any,
    cik_padded: str,
    company_name: str | None,
    seen_date: date | None,
) -> _IssuerUpsertOutcome:
    issuer = _find_issuer_by_cik(cursor, cik_padded)
    if issuer is None:
        current_name = company_name or f"SEC CIK {cik_padded}"
        cursor.execute(
            """
            INSERT INTO stonks.issuer (
                cik,
                current_name,
                first_seen,
                last_seen
            )
            VALUES (%s, %s, %s, %s)
            RETURNING issuer_id
            """,
            (cik_padded, current_name, seen_date, seen_date),
        )
        return _IssuerUpsertOutcome(
            issuer_id=cursor.fetchone()[0],
            created=True,
            updated=False,
        )

    issuer_id = issuer["issuer_id"]
    current_name = _clean_name(issuer.get("current_name"))
    should_update_cik = issuer.get("cik") is None
    should_update_name = bool(company_name) and current_name != company_name
    should_update_last_seen = (
        seen_date is not None
        and (issuer.get("last_seen") is None or issuer["last_seen"] < seen_date)
    )
    if should_update_cik or should_update_name or should_update_last_seen:
        cursor.execute(
            """
            UPDATE stonks.issuer
            SET
                cik = COALESCE(cik, %s),
                current_name = CASE WHEN %s::text IS NULL THEN current_name ELSE %s END,
                last_seen = CASE
                    WHEN %s::date IS NULL THEN last_seen
                    ELSE GREATEST(COALESCE(last_seen, %s), %s)
                END,
                updated_at = now()
            WHERE issuer_id = %s
            """,
            (
                cik_padded if should_update_cik else None,
                company_name if should_update_name else None,
                company_name if should_update_name else None,
                seen_date if should_update_last_seen else None,
                seen_date,
                seen_date,
                issuer_id,
            ),
        )
    return _IssuerUpsertOutcome(
        issuer_id=issuer_id,
        created=False,
        updated=bool(should_update_cik or should_update_name or should_update_last_seen),
    )


def _find_issuer_by_cik(cursor: Any, cik_padded: str) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT issuer_id, cik, current_name, first_seen, last_seen
        FROM stonks.issuer
        WHERE cik = %s
        """,
        (cik_padded,),
    )
    row = cursor.fetchone()
    if row is not None:
        return row_to_dict(cursor, row)

    cursor.execute(
        """
        SELECT i.issuer_id, i.cik, i.current_name, i.first_seen, i.last_seen
        FROM stonks.issuer i
        JOIN stonks.issuer_identifier ii
          ON ii.issuer_id = i.issuer_id
        WHERE ii.id_type = 'CIK'
          AND ii.id_value = %s
        ORDER BY i.created_at
        LIMIT 1
        """,
        (cik_padded,),
    )
    row = cursor.fetchone()
    return row_to_dict(cursor, row) if row is not None else None


def _insert_issuer_identifier(
    *,
    cursor: Any,
    issuer_id: UUID,
    cik_padded: str,
    provider_code: str,
    valid_from: date | None,
) -> bool:
    cursor.execute(
        """
        INSERT INTO stonks.issuer_identifier (
            issuer_id,
            id_type,
            id_value,
            valid_from,
            provider_code,
            confidence_code
        )
        VALUES (%s, 'CIK', %s, %s, %s, 'HIGH')
        ON CONFLICT ON CONSTRAINT uq_issuer_identifier
        DO NOTHING
        RETURNING issuer_identifier_id
        """,
        (issuer_id, cik_padded, valid_from, provider_code),
    )
    return cursor.fetchone() is not None


def _insert_issuer_name_history(
    *,
    cursor: Any,
    issuer_id: UUID,
    company_name: str,
    provider_code: str,
    valid_from: date | None,
) -> bool:
    cursor.execute(
        """
        SELECT issuer_name_id
        FROM stonks.issuer_name_history
        WHERE issuer_id = %s
          AND name = %s
          AND valid_from IS NOT DISTINCT FROM %s
        LIMIT 1
        """,
        (issuer_id, company_name, valid_from),
    )
    if cursor.fetchone() is not None:
        return False

    cursor.execute(
        """
        INSERT INTO stonks.issuer_name_history (
            issuer_id,
            name,
            valid_from,
            provider_code,
            confidence_code
        )
        VALUES (%s, %s, %s, %s, 'HIGH')
        RETURNING issuer_name_id
        """,
        (issuer_id, company_name, valid_from, provider_code),
    )
    return cursor.fetchone() is not None


def _insert_provider_evidence(
    *,
    cursor: Any,
    provider_observation_id: UUID,
    issuer_id: UUID,
    cik_padded: str,
) -> bool:
    cursor.execute(
        """
        SELECT provider_evidence_id
        FROM stonks.provider_evidence
        WHERE provider_observation_id = %s
          AND issuer_id = %s
          AND security_id IS NULL
          AND listing_id IS NULL
          AND event_id IS NULL
        LIMIT 1
        """,
        (provider_observation_id, issuer_id),
    )
    if cursor.fetchone() is not None:
        return False

    cursor.execute(
        """
        INSERT INTO stonks.provider_evidence (
            provider_observation_id,
            issuer_id,
            evidence_role,
            notes
        )
        VALUES (%s, %s, %s, %s)
        RETURNING provider_evidence_id
        """,
        (
            provider_observation_id,
            issuer_id,
            ISSUER_EVIDENCE_ROLE,
            f"SEC CIK {cik_padded} matched issuer identity with HIGH confidence.",
        ),
    )
    return cursor.fetchone() is not None


def _parse_observation(observation: SecIssuerObservation) -> dict[str, Any] | None:
    summary = observation.summary_json or {}
    cik_padded = _cik_padded(summary.get("cik_padded") or summary.get("cik"))
    if cik_padded is None:
        logger.warning(
            "Skipping SEC issuer observation without valid CIK: provider_observation_id=%s",
            observation.provider_observation_id,
        )
        return None

    return {
        "cik_padded": cik_padded,
        "company_name": _clean_name(summary.get("company_name")),
        "seen_date": observation.provider_date or _date_from_datetime(observation.observed_at),
    }


def _observation_from_row(cursor: Any, row: Any) -> SecIssuerObservation:
    data = row_to_dict(cursor, row)
    summary_json = data["summary_json"] or {}
    if not isinstance(summary_json, dict):
        raise SecIssuerUpsertError("provider_observation.summary_json must be a JSON object")
    return SecIssuerObservation(
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


def _clean_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date_from_datetime(value: datetime | None) -> date | None:
    return value.date() if value is not None else None


@dataclass
class _MutableIssuerCounts:
    observations_scanned: int = 0
    observations_skipped: int = 0
    issuers_created: int = 0
    issuers_updated: int = 0
    issuer_identifiers_inserted: int = 0
    issuer_identifiers_skipped: int = 0
    name_history_inserted: int = 0
    name_history_skipped: int = 0
    evidence_inserted: int = 0
    evidence_skipped: int = 0
    warning_count: int = 0

    def to_result(self) -> SecIssuerUpsertResult:
        return SecIssuerUpsertResult(
            observations_scanned=self.observations_scanned,
            observations_skipped=self.observations_skipped,
            issuers_created=self.issuers_created,
            issuers_updated=self.issuers_updated,
            issuer_identifiers_inserted=self.issuer_identifiers_inserted,
            issuer_identifiers_skipped=self.issuer_identifiers_skipped,
            name_history_inserted=self.name_history_inserted,
            name_history_skipped=self.name_history_skipped,
            evidence_inserted=self.evidence_inserted,
            evidence_skipped=self.evidence_skipped,
            warning_count=self.warning_count,
        )
