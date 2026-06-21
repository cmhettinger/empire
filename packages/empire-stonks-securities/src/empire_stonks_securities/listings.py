"""Upsert listings from SEC ticker/exchange observations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable
from uuid import UUID

from empire_core.db.postgres import row_to_dict

from empire_stonks_securities.parsing import SEC_COMPANY_TICKERS_EXCHANGE_PROVIDER


logger = logging.getLogger(__name__)

LISTING_EVIDENCE_ROLE = "CREATED_FROM"
LISTING_SYMBOL_CONFIDENCE = "HIGH"
SEC_LISTING_PROVIDER_CODE = SEC_COMPANY_TICKERS_EXCHANGE_PROVIDER


class SecListingUpsertError(ValueError):
    """Raised when a listing upsert input is invalid."""


@dataclass(frozen=True)
class SecListingObservation:
    """Provider observation input for listing upserts."""

    provider_observation_id: UUID
    provider_code: str
    provider_date: date | None
    observed_at: datetime | None
    summary_json: dict[str, Any]


@dataclass(frozen=True)
class SecListingUpsertResult:
    observations_scanned: int = 0
    observations_skipped: int = 0
    issuers_resolved: int = 0
    issuers_missing: int = 0
    securities_resolved: int = 0
    securities_missing: int = 0
    exchanges_resolved: int = 0
    exchanges_unknown: int = 0
    listings_created: int = 0
    listings_updated: int = 0
    symbol_history_inserted: int = 0
    symbol_history_skipped: int = 0
    evidence_inserted: int = 0
    evidence_skipped: int = 0
    warning_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "observations_scanned": self.observations_scanned,
            "observations_skipped": self.observations_skipped,
            "issuers_resolved": self.issuers_resolved,
            "issuers_missing": self.issuers_missing,
            "securities_resolved": self.securities_resolved,
            "securities_missing": self.securities_missing,
            "exchanges_resolved": self.exchanges_resolved,
            "exchanges_unknown": self.exchanges_unknown,
            "listings_created": self.listings_created,
            "listings_updated": self.listings_updated,
            "symbol_history_inserted": self.symbol_history_inserted,
            "symbol_history_skipped": self.symbol_history_skipped,
            "evidence_inserted": self.evidence_inserted,
            "evidence_skipped": self.evidence_skipped,
            "warning_count": self.warning_count,
        }


@dataclass(frozen=True)
class _ListingUpsertOutcome:
    listing_id: UUID
    created: bool
    updated: bool
    conflict: bool = False


def upsert_sec_listings_from_provider_observations(
    *,
    connection: Any,
    source_run_id: str | UUID | None = None,
    limit: int | None = None,
) -> SecListingUpsertResult:
    observations = select_sec_listing_observations(
        connection=connection,
        source_run_id=source_run_id,
        limit=limit,
    )
    result = upsert_sec_listings(connection=connection, observations=observations)
    logger.info(
        "Completed SEC listing upsert: observations_scanned=%s observations_skipped=%s "
        "issuers_resolved=%s issuers_missing=%s securities_resolved=%s securities_missing=%s "
        "exchanges_resolved=%s exchanges_unknown=%s listings_created=%s listings_updated=%s "
        "symbol_history_inserted=%s symbol_history_skipped=%s evidence_inserted=%s "
        "evidence_skipped=%s warning_count=%s",
        result.observations_scanned,
        result.observations_skipped,
        result.issuers_resolved,
        result.issuers_missing,
        result.securities_resolved,
        result.securities_missing,
        result.exchanges_resolved,
        result.exchanges_unknown,
        result.listings_created,
        result.listings_updated,
        result.symbol_history_inserted,
        result.symbol_history_skipped,
        result.evidence_inserted,
        result.evidence_skipped,
        result.warning_count,
    )
    return result


def select_sec_listing_observations(
    *,
    connection: Any,
    source_run_id: str | UUID | None = None,
    limit: int | None = None,
) -> list[SecListingObservation]:
    """Fetch SEC exchange observations that still require listing reconciliation."""

    params: list[Any] = [SEC_LISTING_PROVIDER_CODE]
    sql = """
        SELECT
            po.provider_observation_id,
            po.provider_code,
            po.provider_date,
            po.observed_at,
            po.summary_json
        FROM stonks.provider_observation po
        WHERE po.provider_code = %s
          AND NOT EXISTS (
              SELECT 1
              FROM stonks.provider_evidence pe
              WHERE pe.provider_observation_id = po.provider_observation_id
                AND pe.listing_id IS NOT NULL
                AND pe.created_at >= po.created_at
          )
        ORDER BY po.observed_at NULLS LAST, po.created_at, po.provider_observation_id
    """
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return [_observation_from_row(cursor, row) for row in cursor.fetchall()]


def upsert_sec_listings(
    *,
    connection: Any,
    observations: Iterable[SecListingObservation],
) -> SecListingUpsertResult:
    counts = _MutableListingCounts()
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
                continue
            counts.issuers_resolved += 1

            security_id = _resolve_security_id(
                cursor=cursor,
                provider_observation_id=observation.provider_observation_id,
                issuer_id=issuer_id,
                ticker_norm=parsed["ticker_norm"],
            )
            if security_id is None:
                counts.observations_skipped += 1
                counts.securities_missing += 1
                counts.warning_count += 1
                continue
            counts.securities_resolved += 1

            exchange_id = _resolve_exchange_id(cursor=cursor, exchange=parsed["exchange"])
            if exchange_id is None:
                counts.observations_skipped += 1
                counts.exchanges_unknown += 1
                counts.warning_count += 1
                logger.warning(
                    "Skipping SEC listing observation with unknown exchange: "
                    "provider_observation_id=%s exchange=%s ticker_norm=%s",
                    observation.provider_observation_id,
                    parsed["exchange"],
                    parsed["ticker_norm"],
                )
                continue
            counts.exchanges_resolved += 1

            listing = _upsert_listing(
                cursor=cursor,
                security_id=security_id,
                exchange_id=exchange_id,
                ticker_raw=parsed["ticker_raw"],
                ticker_norm=parsed["ticker_norm"],
                seen_date=parsed["seen_date"],
            )
            if listing.conflict:
                counts.observations_skipped += 1
                counts.warning_count += 1
                continue
            counts.listings_created += int(listing.created)
            counts.listings_updated += int(listing.updated)

            if _insert_symbol_history(
                cursor=cursor,
                listing_id=listing.listing_id,
                ticker_raw=parsed["ticker_raw"],
                ticker_norm=parsed["ticker_norm"],
                valid_from=parsed["seen_date"],
                provider_code=observation.provider_code,
            ):
                counts.symbol_history_inserted += 1
            else:
                counts.symbol_history_skipped += 1

            if _insert_provider_evidence(
                cursor=cursor,
                provider_observation_id=observation.provider_observation_id,
                issuer_id=issuer_id,
                security_id=security_id,
                listing_id=listing.listing_id,
                ticker_norm=parsed["ticker_norm"],
                exchange=parsed["exchange"],
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
        ORDER BY created_at
        LIMIT 1
        """,
        (provider_observation_id,),
    )
    row = cursor.fetchone()
    if row is not None:
        return row[0]

    cursor.execute("SELECT issuer_id FROM stonks.issuer WHERE cik = %s", (cik_padded,))
    row = cursor.fetchone()
    return row[0] if row is not None else None


def _resolve_security_id(
    *,
    cursor: Any,
    provider_observation_id: UUID,
    issuer_id: UUID,
    ticker_norm: str,
) -> UUID | None:
    cursor.execute(
        """
        SELECT security_id
        FROM stonks.provider_evidence
        WHERE provider_observation_id = %s
          AND security_id IS NOT NULL
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
        SELECT s.security_id
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
    return row[0] if row is not None else None


def _resolve_exchange_id(*, cursor: Any, exchange: str) -> UUID | None:
    cursor.execute(
        """
        SELECT e.exchange_id
        FROM stonks.exchange_alias a
        JOIN stonks.exchange e
          ON e.exchange_id = a.exchange_id
        WHERE a.provider_code = 'SEC'
          AND a.is_active = TRUE
          AND lower(a.raw_name) = lower(%s)
        LIMIT 1
        """,
        (exchange,),
    )
    row = cursor.fetchone()
    if row is not None:
        return row[0]

    cursor.execute(
        """
        SELECT exchange_id
        FROM stonks.exchange
        WHERE is_active = TRUE
          AND (
            lower(exchange_code) = lower(%s)
            OR lower(exchange_name) = lower(%s)
          )
        LIMIT 1
        """,
        (exchange, exchange),
    )
    row = cursor.fetchone()
    return row[0] if row is not None else None


def _upsert_listing(
    *,
    cursor: Any,
    security_id: UUID,
    exchange_id: UUID,
    ticker_raw: str,
    ticker_norm: str,
    seen_date: date | None,
) -> _ListingUpsertOutcome:
    cursor.execute(
        """
        SELECT listing_id, security_id, exchange_id, ticker_norm, current_ticker, last_seen
        FROM stonks.listing
        WHERE security_id = %s
          AND exchange_id = %s
          AND valid_to IS NULL
          AND status = 'ACTIVE'
        LIMIT 1
        """,
        (security_id, exchange_id),
    )
    row = cursor.fetchone()
    if row is not None:
        listing = row_to_dict(cursor, row)
        should_update_ticker = listing.get("current_ticker") != ticker_raw
        should_update_last_seen = (
            seen_date is not None
            and (listing.get("last_seen") is None or listing["last_seen"] < seen_date)
        )
        if should_update_ticker or should_update_last_seen:
            cursor.execute(
                """
                UPDATE stonks.listing
                SET
                    current_ticker = %s,
                    ticker_norm = %s,
                    last_seen = CASE
                        WHEN %s::date IS NULL THEN last_seen
                        ELSE GREATEST(COALESCE(last_seen, %s), %s)
                    END,
                    updated_at = now()
                WHERE listing_id = %s
                """,
                (
                    ticker_raw,
                    ticker_norm,
                    seen_date if should_update_last_seen else None,
                    seen_date,
                    seen_date,
                    listing["listing_id"],
                ),
            )
        return _ListingUpsertOutcome(
            listing_id=listing["listing_id"],
            created=False,
            updated=bool(should_update_ticker or should_update_last_seen),
        )

    cursor.execute(
        """
        INSERT INTO stonks.listing (
            security_id,
            exchange_id,
            current_ticker,
            ticker_norm,
            status,
            valid_from,
            first_seen,
            last_seen
        )
        VALUES (%s, %s, %s, %s, 'ACTIVE', %s, %s, %s)
        RETURNING listing_id
        """,
        (security_id, exchange_id, ticker_raw, ticker_norm, seen_date, seen_date, seen_date),
    )
    return _ListingUpsertOutcome(
        listing_id=cursor.fetchone()[0],
        created=True,
        updated=False,
    )


def _insert_symbol_history(
    *,
    cursor: Any,
    listing_id: UUID,
    ticker_raw: str,
    ticker_norm: str,
    valid_from: date | None,
    provider_code: str,
) -> bool:
    cursor.execute(
        """
        SELECT listing_symbol_id
        FROM stonks.listing_symbol_history
        WHERE listing_id = %s
          AND ticker_norm = %s
          AND valid_to IS NULL
        LIMIT 1
        """,
        (listing_id, ticker_norm),
    )
    if cursor.fetchone() is not None:
        return False

    if valid_from is None:
        cursor.execute(
            """
            SELECT listing_symbol_id, ticker_norm
            FROM stonks.listing_symbol_history
            WHERE listing_id = %s
              AND valid_to IS NULL
            LIMIT 1
            """,
            (listing_id,),
        )
        if cursor.fetchone() is not None:
            logger.warning(
                "Blocking ambiguous listing symbol change without effective date: "
                "listing_id=%s ticker_norm=%s",
                listing_id,
                ticker_norm,
            )
            return False

    cursor.execute(
        """
        UPDATE stonks.listing_symbol_history
        SET valid_to = CASE
            WHEN %s::date IS NULL THEN valid_to
            WHEN valid_from IS NULL OR valid_from <= %s THEN %s
            ELSE valid_from
        END
        WHERE listing_id = %s
          AND valid_to IS NULL
        """,
        (valid_from, valid_from, valid_from, listing_id),
    )

    cursor.execute(
        """
        INSERT INTO stonks.listing_symbol_history (
            listing_id,
            ticker_raw,
            ticker_norm,
            ticker_display,
            valid_from,
            provider_code,
            confidence_code
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING listing_symbol_id
        """,
        (
            listing_id,
            ticker_raw,
            ticker_norm,
            ticker_raw,
            valid_from,
            provider_code,
            LISTING_SYMBOL_CONFIDENCE,
        ),
    )
    return cursor.fetchone() is not None


def _insert_provider_evidence(
    *,
    cursor: Any,
    provider_observation_id: UUID,
    issuer_id: UUID,
    security_id: UUID,
    listing_id: UUID,
    ticker_norm: str,
    exchange: str,
) -> bool:
    cursor.execute(
        """
        SELECT provider_evidence_id
        FROM stonks.provider_evidence
        WHERE provider_observation_id = %s
          AND listing_id = %s
        LIMIT 1
        """,
        (provider_observation_id, listing_id),
    )
    if cursor.fetchone() is not None:
        return False

    cursor.execute(
        """
        INSERT INTO stonks.provider_evidence (
            provider_observation_id,
            issuer_id,
            security_id,
            listing_id,
            evidence_role,
            notes
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING provider_evidence_id
        """,
        (
            provider_observation_id,
            issuer_id,
            security_id,
            listing_id,
            LISTING_EVIDENCE_ROLE,
            f"SEC observed ticker {ticker_norm} on exchange {exchange}.",
        ),
    )
    return cursor.fetchone() is not None


def _parse_observation(observation: SecListingObservation) -> dict[str, Any] | None:
    summary = observation.summary_json or {}
    cik_padded = _cik_padded(summary.get("cik_padded") or summary.get("cik"))
    ticker_raw = _clean_text(summary.get("ticker") or summary.get("ticker_norm"))
    ticker_norm = _clean_text(summary.get("ticker_norm") or summary.get("ticker"))
    exchange = _clean_text(summary.get("exchange"))
    if ticker_norm is not None:
        ticker_norm = ticker_norm.upper()
    if cik_padded is None or ticker_raw is None or ticker_norm is None or exchange is None:
        logger.warning(
            "Skipping SEC listing observation without valid CIK/ticker/exchange: "
            "provider_observation_id=%s",
            observation.provider_observation_id,
        )
        return None
    return {
        "cik_padded": cik_padded,
        "ticker_raw": ticker_raw,
        "ticker_norm": ticker_norm,
        "exchange": exchange,
        "seen_date": observation.provider_date or _date_from_datetime(observation.observed_at),
    }


def _observation_from_row(cursor: Any, row: Any) -> SecListingObservation:
    data = row_to_dict(cursor, row)
    summary_json = data["summary_json"] or {}
    if not isinstance(summary_json, dict):
        raise SecListingUpsertError("provider_observation.summary_json must be a JSON object")
    return SecListingObservation(
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
class _MutableListingCounts:
    observations_scanned: int = 0
    observations_skipped: int = 0
    issuers_resolved: int = 0
    issuers_missing: int = 0
    securities_resolved: int = 0
    securities_missing: int = 0
    exchanges_resolved: int = 0
    exchanges_unknown: int = 0
    listings_created: int = 0
    listings_updated: int = 0
    symbol_history_inserted: int = 0
    symbol_history_skipped: int = 0
    evidence_inserted: int = 0
    evidence_skipped: int = 0
    warning_count: int = 0

    def to_result(self) -> SecListingUpsertResult:
        return SecListingUpsertResult(
            observations_scanned=self.observations_scanned,
            observations_skipped=self.observations_skipped,
            issuers_resolved=self.issuers_resolved,
            issuers_missing=self.issuers_missing,
            securities_resolved=self.securities_resolved,
            securities_missing=self.securities_missing,
            exchanges_resolved=self.exchanges_resolved,
            exchanges_unknown=self.exchanges_unknown,
            listings_created=self.listings_created,
            listings_updated=self.listings_updated,
            symbol_history_inserted=self.symbol_history_inserted,
            symbol_history_skipped=self.symbol_history_skipped,
            evidence_inserted=self.evidence_inserted,
            evidence_skipped=self.evidence_skipped,
            warning_count=self.warning_count,
        )
