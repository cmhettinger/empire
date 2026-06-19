"""Validation report generation for the SEC security-master pipeline."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from empire_core import ObjectStore
from empire_core.db.postgres import row_to_dict

from empire_stonks_securities.acquisition import DEFAULT_STORAGE_ROOT, default_storage_key


REPORT_NAME = "stonks_securities_validation"
REPORT_OBJECT_KIND = "stonks_securities_validation_report"
REPORT_LOGICAL_NAME = "stonks_securities_validation"


@dataclass(frozen=True)
class ValidationRunContext:
    dag_id: str | None = None
    run_id: str | None = None
    source_run_id: str | None = None
    logical_date: str | None = None
    environment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dag_id": self.dag_id,
            "run_id": self.run_id,
            "source_run_id": self.source_run_id,
            "logical_date": self.logical_date,
            "environment": self.environment,
        }


def generate_phase_2a_validation_report(
    *,
    connection: Any,
    run_context: ValidationRunContext | None = None,
    source_run_id: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Generate a JSON-ready validation report from stonks DB state."""

    generated_at = generated_at or datetime.now(UTC)
    resolved_run_context = run_context or ValidationRunContext(source_run_id=source_run_id)
    resolved_source_run_id = source_run_id or resolved_run_context.source_run_id
    with connection.cursor() as cursor:
        source_coverage = _source_coverage(cursor, source_run_id=resolved_source_run_id)
        entity_counts = _entity_counts(cursor, source_run_id=resolved_source_run_id)
        evidence_coverage = _evidence_coverage(cursor, source_run_id=resolved_source_run_id)
        listing_quality = _listing_quality(cursor, source_run_id=resolved_source_run_id)
        exchange_quality = _exchange_quality(cursor, source_run_id=resolved_source_run_id)
        duplicates = _duplicates(cursor)
        orphans = _orphans(cursor)
        conflict_candidates = _conflict_candidates(cursor)

    warnings, failures = evaluate_validation_findings(
        source_coverage=source_coverage,
        evidence_coverage=evidence_coverage,
        listing_quality=listing_quality,
        exchange_quality=exchange_quality,
        duplicates=duplicates,
        orphans=orphans,
        conflict_candidates=conflict_candidates,
    )
    status = evaluate_validation_status(warnings=warnings, failures=failures)
    summary = {
        "status": status,
        "observations_total": source_coverage["observations_total"],
        "issuers_total": entity_counts["issuers_total"],
        "securities_total": entity_counts["securities_total"],
        "listings_total": entity_counts["listings_total"],
        "active_listings_total": listing_quality["active_listings_total"],
        "warnings_total": len(warnings),
        "failures_total": len(failures),
    }
    return {
        "report_name": REPORT_NAME,
        "generated_at": generated_at.isoformat(),
        "run_context": resolved_run_context.to_dict(),
        "summary": summary,
        "source_coverage": source_coverage,
        "entity_counts": entity_counts,
        "evidence_coverage": evidence_coverage,
        "listing_quality": listing_quality,
        "exchange_quality": exchange_quality,
        "duplicates": duplicates,
        "orphans": orphans,
        "conflict_candidates": conflict_candidates,
        "warnings": warnings,
        "failures": failures,
    }


def evaluate_validation_status(
    *,
    warnings: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> str:
    if failures:
        return "FAIL"
    return "SUCCESS"


def evaluate_validation_findings(
    *,
    source_coverage: dict[str, Any],
    evidence_coverage: dict[str, Any],
    listing_quality: dict[str, Any],
    exchange_quality: dict[str, Any],
    duplicates: dict[str, Any],
    orphans: dict[str, Any],
    conflict_candidates: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    _warn_if(warnings, "observations_missing_cik", source_coverage["observations_missing_cik"])
    _warn_if(warnings, "observations_missing_ticker", source_coverage["observations_missing_ticker"])
    _warn_if(
        warnings,
        "ticker_exchange_observations_missing_exchange",
        source_coverage["ticker_exchange_observations_missing_exchange"],
    )
    _warn_if(
        warnings,
        "observations_with_empty_summary_json",
        source_coverage["observations_with_empty_summary_json"],
    )
    _warn_if(
        warnings,
        "observations_with_cik_missing_issuer_evidence",
        evidence_coverage["observations_with_cik_missing_issuer_evidence"],
    )
    _warn_if(
        warnings,
        "observations_with_ticker_cik_missing_security_evidence",
        evidence_coverage["observations_with_ticker_cik_missing_security_evidence"],
    )
    _warn_if(
        warnings,
        "ticker_exchange_observations_missing_listing_evidence",
        evidence_coverage["ticker_exchange_observations_missing_listing_evidence"],
    )
    _warn_if(
        warnings,
        "raw_sec_exchange_values_unmapped",
        exchange_quality["raw_sec_exchange_values_unmapped_count"],
    )
    _warn_if(
        warnings,
        "securities_missing_ticker_identifier",
        duplicates["securities_missing_ticker_identifier"],
    )

    _fail_if(failures, "duplicate_cik_issuers", duplicates["duplicate_cik_issuer_count"])
    _fail_if(
        failures,
        "duplicate_cik_identifiers_to_multiple_issuers",
        duplicates["duplicate_cik_identifier_multi_issuer_count"],
    )
    _fail_if(
        failures,
        "same_issuer_ticker_multiple_securities",
        duplicates["same_issuer_ticker_multi_security_count"],
    )
    _fail_if(
        failures,
        "same_exchange_ticker_multiple_securities",
        conflict_candidates["same_exchange_ticker_multi_security_count"],
    )
    _fail_if(failures, "listings_missing_security", listing_quality["listings_missing_security"])
    _fail_if(failures, "listings_missing_exchange", listing_quality["listings_missing_exchange"])
    _fail_if(
        failures,
        "evidence_missing_targets",
        orphans["evidence_missing_target_rows"],
    )
    return warnings, failures


def validation_report_to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def write_validation_report_to_console(report: dict[str, Any]) -> None:
    print(validation_report_to_json(report), end="")


def write_validation_report_to_file(report: dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(validation_report_to_json(report), encoding="utf-8")
    return output_path


def default_validation_report_path(
    *,
    temp_dir: str | Path | None = None,
    generated_at: datetime | None = None,
) -> Path:
    generated_at = generated_at or datetime.now(UTC)
    root = Path(temp_dir or os.environ.get("EMPIRE_TEMP_DIR", "/tmp"))
    filename = f"stonks_securities_validation_{generated_at:%Y%m%dT%H%M%SZ}.json"
    return root / "stonks" / "securities" / "validation" / filename


def write_validation_report_to_object_store(
    *,
    report: dict[str, Any],
    object_store: ObjectStore,
    storage_root: str = DEFAULT_STORAGE_ROOT,
    storage_key: str | None = None,
    generated_at: datetime | None = None,
):
    generated_at = generated_at or datetime.now(UTC)
    resolved_storage_key = (storage_key or default_storage_key()).strip("/")
    object_key = "/".join(
        [
            resolved_storage_key,
            "validation",
            f"{generated_at:%Y}",
            f"{generated_at:%m}",
            f"{generated_at:%d}",
        ]
    )
    filename = f"stonks_securities_validation_{generated_at:%Y%m%dT%H%M%SZ}.json"
    return object_store.put_bytes(
        run_context=None,
        object_scope="manual",
        domain="stonks",
        logical_name=REPORT_LOGICAL_NAME,
        storage_root=storage_root,
        object_key=object_key,
        filename=filename,
        data=validation_report_to_json(report).encode("utf-8"),
        content_type="application/json",
        object_kind=REPORT_OBJECT_KIND,
        metadata={"report_name": REPORT_NAME, "generated_at": report["generated_at"]},
    )


def _source_coverage(cursor: Any, *, source_run_id: str | None) -> dict[str, Any]:
    obs_from, obs_params = _observation_scope_sql(source_run_id)
    source_files_for_run = _source_files_for_run(cursor, source_run_id=source_run_id)
    by_source = _fetchall(
        cursor,
        "observations_by_source",
        f"""
        SELECT po.provider_code, COUNT(*) AS observation_count
        FROM {obs_from}
        GROUP BY provider_code
        ORDER BY provider_code
        """,
        obs_params,
    )
    by_object_key = _observations_by_object_key(cursor, obs_from, obs_params, source_run_id)
    return {
        "observations_total": _scalar(
            cursor,
            "observations_total",
            f"SELECT COUNT(*) FROM {obs_from}",
            obs_params,
        ),
        "observations_by_source": by_source,
        "source_files_for_run": source_files_for_run,
        "observations_by_object_key": by_object_key,
        "observations_missing_cik": _scalar(
            cursor,
            "observations_missing_cik",
            f"""
            SELECT COUNT(*)
            FROM {obs_from}
            WHERE NULLIF(TRIM(po.summary_json ->> 'cik_padded'), '') IS NULL
              AND NULLIF(TRIM(po.summary_json ->> 'cik'), '') IS NULL
            """,
            obs_params,
        ),
        "observations_missing_ticker": _scalar(
            cursor,
            "observations_missing_ticker",
            f"""
            SELECT COUNT(*)
            FROM {obs_from}
            WHERE NULLIF(TRIM(po.summary_json ->> 'ticker_norm'), '') IS NULL
              AND NULLIF(TRIM(po.summary_json ->> 'ticker'), '') IS NULL
            """,
            obs_params,
        ),
        "ticker_exchange_observations_missing_exchange": _scalar(
            cursor,
            "ticker_exchange_observations_missing_exchange",
            f"""
            SELECT COUNT(*)
            FROM {obs_from}
            WHERE po.provider_code = 'SEC_COMPANY_TICKERS_EXCHANGE'
              AND NULLIF(TRIM(po.summary_json ->> 'exchange'), '') IS NULL
            """,
            obs_params,
        ),
        "observations_with_empty_summary_json": _scalar(
            cursor,
            "observations_with_empty_summary_json",
            f"""
            SELECT COUNT(*)
            FROM {obs_from}
            WHERE po.summary_json IS NULL OR po.summary_json = '{{}}'::jsonb
            """,
            obs_params,
        ),
    }


def _source_files_for_run(cursor: Any, *, source_run_id: str | None) -> list[dict[str, Any]]:
    if source_run_id is None:
        return []
    return _fetchall(
        cursor,
        "source_files_for_run",
        """
        SELECT
          upper(so.logical_name) AS provider_code,
          so.object_key,
          so.object_id::text AS source_object_id,
          so.filename,
          so.checksum_sha256 AS sha256,
          so.size_bytes,
          so.created_at
        FROM core.stored_object so
        WHERE so.run_id = %s
          AND so.object_kind = 'sec_source_file'
          AND so.deleted_at IS NULL
        ORDER BY provider_code, object_key
        """,
        (source_run_id,),
    )


def _observations_by_object_key(
    cursor: Any,
    obs_from: str,
    obs_params: tuple[Any, ...],
    source_run_id: str | None,
) -> list[dict[str, Any]]:
    if source_run_id is None:
        return _fetchall(
            cursor,
            "observations_by_object_key",
            f"""
            SELECT po.provider_code, po.object_key, COUNT(*) AS observation_count
            FROM {obs_from}
            GROUP BY provider_code, object_key
            ORDER BY provider_code, object_key
            """,
            obs_params,
        )
    return _fetchall(
        cursor,
        "observations_by_object_key",
        """
        SELECT
          COALESCE(po.provider_code, upper(so.logical_name)) AS provider_code,
          so.object_key,
          COUNT(DISTINCT po.provider_observation_id) AS observation_count
        FROM core.stored_object so
        LEFT JOIN stonks.provider_observation po
          ON (
            so.object_id = po.object_id
            OR so.checksum_sha256 = po.summary_json #>> '{source_file,sha256}'
            OR so.object_key = po.summary_json #>> '{source_file,object_key}'
          )
        WHERE so.run_id = %s
          AND so.object_kind = 'sec_source_file'
          AND so.deleted_at IS NULL
        GROUP BY COALESCE(po.provider_code, upper(so.logical_name)), so.object_key
        ORDER BY provider_code, so.object_key
        """,
        (source_run_id,),
    )


def _entity_counts(cursor: Any, *, source_run_id: str | None) -> dict[str, Any]:
    obs_from, obs_params = _observation_scope_sql(source_run_id)
    return {
        "issuers_total": _scalar(
            cursor,
            "issuers_total",
            f"""
            SELECT COUNT(DISTINCT pe.issuer_id)
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            WHERE pe.issuer_id IS NOT NULL
            """,
            obs_params,
        ),
        "issuers_with_cik": _scalar(
            cursor,
            "issuers_with_cik",
            f"""
            SELECT COUNT(DISTINCT i.issuer_id)
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            JOIN stonks.issuer i
              ON i.issuer_id = pe.issuer_id
            WHERE i.cik IS NOT NULL
            """,
            obs_params,
        ),
        "issuers_from_sec_evidence": _scalar(
            cursor,
            "issuers_from_sec_evidence",
            f"""
            SELECT COUNT(DISTINCT issuer_id)
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            WHERE pe.issuer_id IS NOT NULL
            """,
            obs_params,
        ),
        "securities_total": _scalar(
            cursor,
            "securities_total",
            f"""
            SELECT COUNT(DISTINCT pe.security_id)
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            WHERE pe.security_id IS NOT NULL
            """,
            obs_params,
        ),
        "securities_from_sec_evidence": _scalar(
            cursor,
            "securities_from_sec_evidence",
            f"""
            SELECT COUNT(DISTINCT security_id)
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            WHERE pe.security_id IS NOT NULL
            """,
            obs_params,
        ),
        "listings_total": _scalar(
            cursor,
            "listings_total",
            f"""
            SELECT COUNT(DISTINCT pe.listing_id)
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            WHERE pe.listing_id IS NOT NULL
            """,
            obs_params,
        ),
        "listings_from_sec_evidence": _scalar(
            cursor,
            "listings_from_sec_evidence",
            f"""
            SELECT COUNT(DISTINCT listing_id)
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            WHERE pe.listing_id IS NOT NULL
            """,
            obs_params,
        ),
    }


def _evidence_coverage(cursor: Any, *, source_run_id: str | None) -> dict[str, Any]:
    obs_from, obs_params = _observation_scope_sql(source_run_id)
    return {
        "evidence_rows_by_target_type": _fetchall(
            cursor,
            "evidence_rows_by_target_type",
            f"""
            SELECT
              CASE
                WHEN pe.listing_id IS NOT NULL THEN 'listing'
                WHEN pe.security_id IS NOT NULL THEN 'security'
                WHEN pe.issuer_id IS NOT NULL THEN 'issuer'
                WHEN pe.event_id IS NOT NULL THEN 'event'
                ELSE 'none'
              END AS target_type,
              COUNT(*) AS evidence_count
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            GROUP BY 1
            ORDER BY 1
            """,
            obs_params,
        ),
        "observations_with_issuer_evidence": _scalar(
            cursor,
            "observations_with_issuer_evidence",
            f"""
            SELECT COUNT(DISTINCT pe.provider_observation_id)
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            WHERE pe.issuer_id IS NOT NULL
            """,
            obs_params,
        ),
        "observations_with_security_evidence": _scalar(
            cursor,
            "observations_with_security_evidence",
            f"""
            SELECT COUNT(DISTINCT pe.provider_observation_id)
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            WHERE pe.security_id IS NOT NULL
            """,
            obs_params,
        ),
        "observations_with_listing_evidence": _scalar(
            cursor,
            "observations_with_listing_evidence",
            f"""
            SELECT COUNT(DISTINCT pe.provider_observation_id)
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            WHERE pe.listing_id IS NOT NULL
            """,
            obs_params,
        ),
        "observations_with_cik_missing_issuer_evidence": _scalar(
            cursor,
            "observations_with_cik_missing_issuer_evidence",
            f"""
            SELECT COUNT(*)
            FROM {obs_from}
            WHERE COALESCE(NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''), NULLIF(TRIM(po.summary_json ->> 'cik'), '')) IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM stonks.provider_evidence pe
                WHERE pe.provider_observation_id = po.provider_observation_id
                  AND pe.issuer_id IS NOT NULL
              )
            """,
            obs_params,
        ),
        "observations_with_ticker_cik_missing_security_evidence": _scalar(
            cursor,
            "observations_with_ticker_cik_missing_security_evidence",
            f"""
            SELECT COUNT(*)
            FROM {obs_from}
            WHERE COALESCE(NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''), NULLIF(TRIM(po.summary_json ->> 'cik'), '')) IS NOT NULL
              AND COALESCE(NULLIF(TRIM(po.summary_json ->> 'ticker_norm'), ''), NULLIF(TRIM(po.summary_json ->> 'ticker'), '')) IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM stonks.provider_evidence pe
                WHERE pe.provider_observation_id = po.provider_observation_id
                  AND pe.security_id IS NOT NULL
              )
            """,
            obs_params,
        ),
        "ticker_exchange_observations_missing_listing_evidence": _scalar(
            cursor,
            "ticker_exchange_observations_missing_listing_evidence",
            f"""
            SELECT COUNT(*)
            FROM {obs_from}
            WHERE po.provider_code = 'SEC_COMPANY_TICKERS_EXCHANGE'
              AND NOT EXISTS (
                SELECT 1 FROM stonks.provider_evidence pe
                WHERE pe.provider_observation_id = po.provider_observation_id
                  AND pe.listing_id IS NOT NULL
              )
            """,
            obs_params,
        ),
    }


def _listing_quality(cursor: Any, *, source_run_id: str | None) -> dict[str, Any]:
    scoped_listings, listing_params = _scoped_listings_sql(source_run_id)
    return {
        "active_listings_total": _scalar(
            cursor,
            "active_listings_total",
            f"""
            SELECT COUNT(DISTINCT l.listing_id)
            FROM {scoped_listings}
            WHERE l.status = 'ACTIVE' AND l.valid_to IS NULL
            """,
            listing_params,
        ),
        "listings_missing_security": _scalar(
            cursor,
            "listings_missing_security",
            f"""
            SELECT COUNT(*)
            FROM {scoped_listings}
            LEFT JOIN stonks.security s ON s.security_id = l.security_id
            WHERE s.security_id IS NULL
            """,
            listing_params,
        ),
        "listings_missing_exchange": _scalar(
            cursor,
            "listings_missing_exchange",
            f"""
            SELECT COUNT(*)
            FROM {scoped_listings}
            LEFT JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
            WHERE e.exchange_id IS NULL
            """,
            listing_params,
        ),
        "listings_missing_symbol_history": _scalar(
            cursor,
            "listings_missing_symbol_history",
            f"""
            SELECT COUNT(*)
            FROM {scoped_listings}
            WHERE NOT EXISTS (
              SELECT 1 FROM stonks.listing_symbol_history h
              WHERE h.listing_id = l.listing_id
            )
            """,
            listing_params,
        ),
        "active_listings_without_active_symbol_history": _scalar(
            cursor,
            "active_listings_without_active_symbol_history",
            f"""
            SELECT COUNT(*)
            FROM {scoped_listings}
            WHERE l.status = 'ACTIVE'
              AND l.valid_to IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM stonks.listing_symbol_history h
                WHERE h.listing_id = l.listing_id
                  AND h.valid_to IS NULL
              )
            """,
            listing_params,
        ),
    }


def _exchange_quality(cursor: Any, *, source_run_id: str | None) -> dict[str, Any]:
    obs_from, obs_params = _observation_scope_sql(source_run_id)
    scoped_listings, listing_params = _scoped_listings_sql(source_run_id)
    raw_unmapped = _fetchall(
        cursor,
        "raw_sec_exchange_values_unmapped",
        f"""
        SELECT po.summary_json ->> 'exchange' AS raw_exchange, COUNT(*) AS observation_count
        FROM {obs_from}
        WHERE po.provider_code = 'SEC_COMPANY_TICKERS_EXCHANGE'
          AND NULLIF(TRIM(po.summary_json ->> 'exchange'), '') IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM stonks.exchange_alias ea
            WHERE ea.provider_code = 'SEC'
              AND ea.is_active = TRUE
              AND lower(ea.raw_name) = lower(po.summary_json ->> 'exchange')
          )
        GROUP BY 1
        ORDER BY observation_count DESC, raw_exchange
        """,
        obs_params,
    )
    return {
        "listings_by_exchange": _fetchall(
            cursor,
            "listings_by_exchange",
            f"""
            SELECT e.exchange_code, e.exchange_name, COUNT(*) AS listing_count
            FROM {scoped_listings}
            JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
            WHERE l.status = 'ACTIVE' AND l.valid_to IS NULL
            GROUP BY e.exchange_code, e.exchange_name
            ORDER BY listing_count DESC, e.exchange_code
            """,
            listing_params,
        ),
        "raw_sec_exchange_values": _fetchall(
            cursor,
            "raw_sec_exchange_values",
            f"""
            SELECT po.summary_json ->> 'exchange' AS raw_exchange, COUNT(*) AS observation_count
            FROM {obs_from}
            WHERE po.provider_code = 'SEC_COMPANY_TICKERS_EXCHANGE'
            GROUP BY 1
            ORDER BY observation_count DESC NULLS LAST
            """,
            obs_params,
        ),
        "raw_sec_exchange_values_unmapped": raw_unmapped,
        "raw_sec_exchange_values_unmapped_count": sum(
            int(row["observation_count"]) for row in raw_unmapped
        ),
    }


def _duplicates(cursor: Any) -> dict[str, Any]:
    duplicate_cik_issuers = _fetchall(
        cursor,
        "duplicate_cik_issuers",
        """
        SELECT cik, COUNT(*) AS issuer_count
        FROM stonks.issuer
        WHERE cik IS NOT NULL
        GROUP BY cik
        HAVING COUNT(*) > 1
        ORDER BY issuer_count DESC, cik
        """,
    )
    duplicate_cik_identifiers = _fetchall(
        cursor,
        "duplicate_cik_identifiers_to_multiple_issuers",
        """
        SELECT id_value AS cik, COUNT(DISTINCT issuer_id) AS issuer_count
        FROM stonks.issuer_identifier
        WHERE id_type = 'CIK'
        GROUP BY id_value
        HAVING COUNT(DISTINCT issuer_id) > 1
        ORDER BY issuer_count DESC, cik
        """,
    )
    same_issuer_ticker_multi_security = _fetchall(
        cursor,
        "same_issuer_ticker_multi_security",
        """
        SELECT s.issuer_id, si.id_value AS ticker_norm, COUNT(DISTINCT s.security_id) AS security_count
        FROM stonks.security s
        JOIN stonks.security_identifier si ON si.security_id = s.security_id
        WHERE si.id_type = 'TICKER'
        GROUP BY s.issuer_id, si.id_value
        HAVING COUNT(DISTINCT s.security_id) > 1
        ORDER BY security_count DESC, ticker_norm
        """,
    )
    return {
        "duplicate_cik_issuers": duplicate_cik_issuers,
        "duplicate_cik_issuer_count": len(duplicate_cik_issuers),
        "duplicate_cik_identifiers_to_multiple_issuers": duplicate_cik_identifiers,
        "duplicate_cik_identifier_multi_issuer_count": len(duplicate_cik_identifiers),
        "same_issuer_ticker_multiple_securities": same_issuer_ticker_multi_security,
        "same_issuer_ticker_multi_security_count": len(same_issuer_ticker_multi_security),
        "securities_missing_ticker_identifier": _scalar(
            cursor,
            "securities_missing_ticker_identifier",
            """
            SELECT COUNT(*)
            FROM stonks.security s
            WHERE NOT EXISTS (
              SELECT 1 FROM stonks.security_identifier si
              WHERE si.security_id = s.security_id
                AND si.id_type = 'TICKER'
            )
            """,
        ),
    }


def _orphans(cursor: Any) -> dict[str, Any]:
    return {
        "evidence_missing_target_rows": _scalar(
            cursor,
            "evidence_missing_target_rows",
            """
            SELECT COUNT(*)
            FROM stonks.provider_evidence pe
            LEFT JOIN stonks.issuer i ON i.issuer_id = pe.issuer_id
            LEFT JOIN stonks.security s ON s.security_id = pe.security_id
            LEFT JOIN stonks.listing l ON l.listing_id = pe.listing_id
            LEFT JOIN stonks.security_event ev ON ev.event_id = pe.event_id
            WHERE (pe.issuer_id IS NOT NULL AND i.issuer_id IS NULL)
               OR (pe.security_id IS NOT NULL AND s.security_id IS NULL)
               OR (pe.listing_id IS NOT NULL AND l.listing_id IS NULL)
               OR (pe.event_id IS NOT NULL AND ev.event_id IS NULL)
            """,
        )
    }


def _conflict_candidates(cursor: Any) -> dict[str, Any]:
    same_exchange_ticker_multi_security = _fetchall(
        cursor,
        "same_exchange_ticker_multi_security",
        """
        SELECT l.exchange_id, l.ticker_norm, COUNT(DISTINCT l.security_id) AS security_count
        FROM stonks.listing l
        WHERE l.valid_to IS NULL
          AND l.ticker_norm IS NOT NULL
        GROUP BY l.exchange_id, l.ticker_norm
        HAVING COUNT(DISTINCT l.security_id) > 1
        ORDER BY security_count DESC, ticker_norm
        """,
    )
    same_exchange_ticker_multi_issuer = _fetchall(
        cursor,
        "same_exchange_ticker_multi_issuer",
        """
        SELECT l.exchange_id, l.ticker_norm, COUNT(DISTINCT s.issuer_id) AS issuer_count
        FROM stonks.listing l
        JOIN stonks.security s ON s.security_id = l.security_id
        WHERE l.valid_to IS NULL
          AND l.ticker_norm IS NOT NULL
        GROUP BY l.exchange_id, l.ticker_norm
        HAVING COUNT(DISTINCT s.issuer_id) > 1
        ORDER BY issuer_count DESC, ticker_norm
        """,
    )
    cik_multi_names = _fetchall(
        cursor,
        "same_cik_multiple_issuer_names",
        """
        SELECT i.cik, COUNT(DISTINCT h.name) AS issuer_name_count
        FROM stonks.issuer i
        JOIN stonks.issuer_name_history h ON h.issuer_id = i.issuer_id
        WHERE i.cik IS NOT NULL
        GROUP BY i.cik
        HAVING COUNT(DISTINCT h.name) > 1
        ORDER BY issuer_name_count DESC, i.cik
        """,
    )
    listing_multi_active_symbols = _fetchall(
        cursor,
        "same_listing_multiple_active_symbols",
        """
        SELECT listing_id, COUNT(DISTINCT ticker_norm) AS active_symbol_count
        FROM stonks.listing_symbol_history
        WHERE valid_to IS NULL
        GROUP BY listing_id
        HAVING COUNT(DISTINCT ticker_norm) > 1
        ORDER BY active_symbol_count DESC, listing_id
        """,
    )
    return {
        "same_exchange_ticker_multiple_securities": same_exchange_ticker_multi_security,
        "same_exchange_ticker_multi_security_count": len(same_exchange_ticker_multi_security),
        "same_exchange_ticker_multiple_issuers": same_exchange_ticker_multi_issuer,
        "same_exchange_ticker_multi_issuer_count": len(same_exchange_ticker_multi_issuer),
        "same_cik_multiple_issuer_names": cik_multi_names,
        "same_cik_multiple_issuer_names_count": len(cik_multi_names),
        "same_listing_multiple_active_symbols": listing_multi_active_symbols,
        "same_listing_multiple_active_symbols_count": len(listing_multi_active_symbols),
    }


def _observation_scope_sql(source_run_id: str | None) -> tuple[str, tuple[Any, ...]]:
    if source_run_id is None:
        return "stonks.provider_observation po", ()
    return (
        """
        (
            SELECT po.*
            FROM stonks.provider_observation po
            WHERE EXISTS (
                SELECT 1
                FROM core.stored_object so
                WHERE so.run_id = %s
                  AND so.object_kind = 'sec_source_file'
                  AND (
                    so.object_id = po.object_id
                    OR so.checksum_sha256 = po.summary_json #>> '{source_file,sha256}'
                    OR so.object_key = po.summary_json #>> '{source_file,object_key}'
                  )
            )
        ) po
        """,
        (source_run_id,),
    )


def _scoped_listings_sql(source_run_id: str | None) -> tuple[str, tuple[Any, ...]]:
    if source_run_id is None:
        return "stonks.listing l", ()
    return (
        """
        (
            SELECT DISTINCT l.*
            FROM stonks.listing l
            JOIN stonks.provider_evidence pe_scope
              ON pe_scope.listing_id = l.listing_id
            JOIN stonks.provider_observation po_scope
              ON po_scope.provider_observation_id = pe_scope.provider_observation_id
            WHERE EXISTS (
                SELECT 1
                FROM core.stored_object so_scope
                WHERE so_scope.run_id = %s
                  AND so_scope.object_kind = 'sec_source_file'
                  AND (
                    so_scope.object_id = po_scope.object_id
                    OR so_scope.checksum_sha256 = po_scope.summary_json #>> '{source_file,sha256}'
                    OR so_scope.object_key = po_scope.summary_json #>> '{source_file,object_key}'
                  )
            )
        ) l
        """,
        (source_run_id,),
    )


def _scalar(cursor: Any, metric: str, sql: str, params: tuple[Any, ...] = ()) -> int:
    cursor.execute(_tag(metric, sql), params)
    row = cursor.fetchone()
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(next(iter(row.values())))
    return int(row[0])


def _fetchall(cursor: Any, metric: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor.execute(_tag(metric, sql), params)
    return [row_to_dict(cursor, row) for row in cursor.fetchall()]


def _tag(metric: str, sql: str) -> str:
    return f"/* metric: {metric} */\n{sql}"


def _warn_if(warnings: list[dict[str, Any]], code: str, count: int) -> None:
    if count:
        warnings.append({"code": code, "count": int(count)})


def _fail_if(failures: list[dict[str, Any]], code: str, count: int) -> None:
    if count:
        failures.append({"code": code, "count": int(count)})
