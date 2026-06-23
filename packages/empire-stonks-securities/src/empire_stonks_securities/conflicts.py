"""Conflict report generation for the SEC security-master pipeline."""

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
from empire_stonks_securities.report_paths import run_report_object_key, run_report_path


CONFLICT_REPORT_NAME = "stonks_securities_phase_2a_conflicts"
CONFLICT_REPORT_OBJECT_KIND = "stonks_securities_conflict_report"
CONFLICT_REPORT_LOGICAL_NAME = "stonks_securities_conflicts"

SOURCE_PRIORITY = {
    "sec_company_tickers_exchange": 100,
    "sec_company_tickers": 90,
    "sec_submissions": 80,
    "sec_edgar_index": 40,
}


@dataclass(frozen=True)
class ConflictRunContext:
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


def generate_phase_2a_conflict_report(
    *,
    connection: Any,
    run_context: ConflictRunContext | None = None,
    source_run_id: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Generate a JSON-ready conflict report from current stonks DB state."""

    generated_at = generated_at or datetime.now(UTC)
    resolved_run_context = run_context or ConflictRunContext(source_run_id=source_run_id)
    resolved_source_run_id = source_run_id or resolved_run_context.source_run_id
    with connection.cursor() as cursor:
        candidate_rows = detect_conflict_candidates(
            cursor=cursor,
            source_run_id=resolved_source_run_id,
        )

    conflicts = build_conflicts(candidate_rows)
    summary = summarize_conflicts(conflicts)
    return {
        "report_name": CONFLICT_REPORT_NAME,
        "generated_at": generated_at.isoformat(),
        "healthy": summary["status"] in {"PASS", "WARN"},
        "run_context": resolved_run_context.to_dict(),
        "summary": summary,
        "source_priority": SOURCE_PRIORITY,
        "conflicts_by_category": conflicts_by_category(conflicts),
        "conflicts": conflicts,
    }


def detect_conflict_candidates(*, cursor: Any, source_run_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    obs_from, obs_params = _observation_scope_sql(source_run_id)
    scoped_listings, listing_params = _scoped_listings_sql(source_run_id)
    return {
        "cik_identifier_multiple_issuers": _fetchall(
            cursor,
            "cik_identifier_multiple_issuers",
            """
            SELECT
              id_value AS cik,
              COUNT(DISTINCT issuer_id) AS issuer_count,
              ARRAY_AGG(DISTINCT issuer_id::text ORDER BY issuer_id::text) AS issuer_ids
            FROM stonks.issuer_identifier
            WHERE id_type = 'CIK'
            GROUP BY id_value
            HAVING COUNT(DISTINCT issuer_id) > 1
            ORDER BY issuer_count DESC, cik
            """,
        ),
        "issuer_missing_cik_from_sec_evidence": _fetchall(
            cursor,
            "issuer_missing_cik_from_sec_evidence",
            f"""
            SELECT
              pe.issuer_id::text AS issuer_id,
              COALESCE(NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''), NULLIF(TRIM(po.summary_json ->> 'cik'), '')) AS cik,
              COUNT(DISTINCT po.provider_observation_id) AS observation_count,
              ARRAY_AGG(DISTINCT po.provider_observation_id::text ORDER BY po.provider_observation_id::text) AS observation_ids
            FROM stonks.provider_evidence pe
            JOIN {obs_from}
              ON po.provider_observation_id = pe.provider_observation_id
            JOIN stonks.issuer i
              ON i.issuer_id = pe.issuer_id
            WHERE pe.issuer_id IS NOT NULL
              AND i.cik IS NULL
              AND COALESCE(NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''), NULLIF(TRIM(po.summary_json ->> 'cik'), '')) IS NOT NULL
            GROUP BY
              pe.issuer_id,
              COALESCE(NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''), NULLIF(TRIM(po.summary_json ->> 'cik'), ''))
            ORDER BY observation_count DESC, cik
            """,
            obs_params,
        ),
        "observation_cik_issuer_identifier_mismatch": _fetchall(
            cursor,
            "observation_cik_issuer_identifier_mismatch",
            f"""
            SELECT
              po.provider_observation_id::text AS provider_observation_id,
              pe.issuer_id::text AS evidence_issuer_id,
              ii.issuer_id::text AS identifier_issuer_id,
              COALESCE(NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''), NULLIF(TRIM(po.summary_json ->> 'cik'), '')) AS cik
            FROM {obs_from}
            JOIN stonks.provider_evidence pe
              ON pe.provider_observation_id = po.provider_observation_id
             AND pe.issuer_id IS NOT NULL
            JOIN stonks.issuer_identifier ii
              ON ii.id_type = 'CIK'
             AND ii.id_value = COALESCE(NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''), NULLIF(TRIM(po.summary_json ->> 'cik'), ''))
            WHERE ii.issuer_id <> pe.issuer_id
            ORDER BY cik, po.provider_observation_id
            """,
            obs_params,
        ),
        "same_issuer_ticker_multiple_securities": _fetchall(
            cursor,
            "same_issuer_ticker_multiple_securities",
            """
            SELECT
              s.issuer_id::text AS issuer_id,
              si.id_value AS ticker_norm,
              COUNT(DISTINCT s.security_id) AS security_count,
              ARRAY_AGG(DISTINCT s.security_id::text ORDER BY s.security_id::text) AS security_ids
            FROM stonks.security s
            JOIN stonks.security_identifier si ON si.security_id = s.security_id
            WHERE si.id_type = 'TICKER'
            GROUP BY s.issuer_id, si.id_value
            HAVING COUNT(DISTINCT s.security_id) > 1
            ORDER BY security_count DESC, ticker_norm
            """,
        ),
        "ticker_exchange_multiple_securities": _fetchall(
            cursor,
            "ticker_exchange_multiple_securities",
            f"""
            SELECT
              l.ticker_norm,
              e.exchange_code,
              l.exchange_id::text AS exchange_id,
              COUNT(DISTINCT l.security_id) AS security_count,
              ARRAY_AGG(DISTINCT l.security_id::text ORDER BY l.security_id::text) AS security_ids,
              ARRAY_AGG(DISTINCT l.listing_id::text ORDER BY l.listing_id::text) AS listing_ids
            FROM {scoped_listings}
            JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
            WHERE l.status = 'ACTIVE'
              AND l.valid_to IS NULL
              AND l.ticker_norm IS NOT NULL
            GROUP BY l.ticker_norm, e.exchange_code, l.exchange_id
            HAVING COUNT(DISTINCT l.security_id) > 1
            ORDER BY security_count DESC, l.ticker_norm, e.exchange_code
            """,
            listing_params,
        ),
        "ticker_exchange_multiple_issuers": _fetchall(
            cursor,
            "ticker_exchange_multiple_issuers",
            f"""
            SELECT
              l.ticker_norm,
              e.exchange_code,
              COUNT(DISTINCT s.issuer_id) AS issuer_count,
              ARRAY_AGG(DISTINCT s.issuer_id::text ORDER BY s.issuer_id::text) AS issuer_ids,
              ARRAY_AGG(DISTINCT s.security_id::text ORDER BY s.security_id::text) AS security_ids
            FROM {scoped_listings}
            JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
            JOIN stonks.security s ON s.security_id = l.security_id
            WHERE l.status = 'ACTIVE'
              AND l.valid_to IS NULL
              AND l.ticker_norm IS NOT NULL
            GROUP BY l.ticker_norm, e.exchange_code
            HAVING COUNT(DISTINCT s.issuer_id) > 1
            ORDER BY issuer_count DESC, l.ticker_norm, e.exchange_code
            """,
            listing_params,
        ),
        "observation_ticker_security_identifier_mismatch": _fetchall(
            cursor,
            "observation_ticker_security_identifier_mismatch",
            f"""
            SELECT
              po.provider_observation_id::text AS provider_observation_id,
              pe.security_id::text AS security_id,
              COALESCE(NULLIF(TRIM(po.summary_json ->> 'ticker_norm'), ''), NULLIF(TRIM(po.summary_json ->> 'ticker'), '')) AS observation_ticker_norm,
              ARRAY_AGG(DISTINCT si.id_value ORDER BY si.id_value) AS security_ticker_norms
            FROM {obs_from}
            JOIN stonks.provider_evidence pe
              ON pe.provider_observation_id = po.provider_observation_id
             AND pe.security_id IS NOT NULL
            JOIN stonks.security_identifier si
              ON si.security_id = pe.security_id
             AND si.id_type = 'TICKER'
            WHERE COALESCE(NULLIF(TRIM(po.summary_json ->> 'ticker_norm'), ''), NULLIF(TRIM(po.summary_json ->> 'ticker'), '')) IS NOT NULL
            GROUP BY
              po.provider_observation_id,
              pe.security_id,
              COALESCE(NULLIF(TRIM(po.summary_json ->> 'ticker_norm'), ''), NULLIF(TRIM(po.summary_json ->> 'ticker'), ''))
            HAVING NOT BOOL_OR(
              si.id_value = COALESCE(NULLIF(TRIM(po.summary_json ->> 'ticker_norm'), ''), NULLIF(TRIM(po.summary_json ->> 'ticker'), ''))
            )
            ORDER BY observation_ticker_norm, po.provider_observation_id
            """,
            obs_params,
        ),
        "ticker_exchange_multiple_active_listings": _fetchall(
            cursor,
            "ticker_exchange_multiple_active_listings",
            f"""
            SELECT
              l.ticker_norm,
              e.exchange_code,
              COUNT(DISTINCT l.listing_id) AS listing_count,
              ARRAY_AGG(DISTINCT l.listing_id::text ORDER BY l.listing_id::text) AS listing_ids
            FROM {scoped_listings}
            JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
            WHERE l.status = 'ACTIVE'
              AND l.valid_to IS NULL
              AND l.ticker_norm IS NOT NULL
            GROUP BY l.ticker_norm, e.exchange_code
            HAVING COUNT(DISTINCT l.listing_id) > 1
            ORDER BY listing_count DESC, l.ticker_norm, e.exchange_code
            """,
            listing_params,
        ),
        "security_exchange_multiple_active_listings": _fetchall(
            cursor,
            "security_exchange_multiple_active_listings",
            f"""
            SELECT
              l.security_id::text AS security_id,
              e.exchange_code,
              COUNT(DISTINCT l.listing_id) AS listing_count,
              ARRAY_AGG(DISTINCT l.listing_id::text ORDER BY l.listing_id::text) AS listing_ids
            FROM {scoped_listings}
            JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
            WHERE l.status = 'ACTIVE'
              AND l.valid_to IS NULL
            GROUP BY l.security_id, e.exchange_code
            HAVING COUNT(DISTINCT l.listing_id) > 1
            ORDER BY listing_count DESC, l.security_id, e.exchange_code
            """,
            listing_params,
        ),
        "active_listing_missing_current_symbol": _fetchall(
            cursor,
            "active_listing_missing_current_symbol",
            f"""
            SELECT l.listing_id::text AS listing_id, l.security_id::text AS security_id, e.exchange_code
            FROM {scoped_listings}
            JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
            WHERE l.status = 'ACTIVE'
              AND l.valid_to IS NULL
              AND NOT EXISTS (
                SELECT 1
                FROM stonks.listing_symbol_history h
                WHERE h.listing_id = l.listing_id
                  AND h.valid_to IS NULL
              )
            ORDER BY e.exchange_code, l.listing_id
            """,
            listing_params,
        ),
        "listing_multiple_current_symbols": _fetchall(
            cursor,
            "listing_multiple_current_symbols",
            """
            SELECT
              h.listing_id::text AS listing_id,
              l.security_id::text AS security_id,
              l.exchange_id::text AS exchange_id,
              e.exchange_code,
              COUNT(DISTINCT h.ticker_norm) AS active_symbol_count,
              ARRAY_AGG(DISTINCT h.ticker_norm ORDER BY h.ticker_norm) AS ticker_norms
            FROM stonks.listing_symbol_history h
            JOIN stonks.listing l ON l.listing_id = h.listing_id
            JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
            WHERE h.valid_to IS NULL
            GROUP BY h.listing_id, l.security_id, l.exchange_id, e.exchange_code
            HAVING COUNT(DISTINCT h.ticker_norm) > 1
            ORDER BY active_symbol_count DESC, h.listing_id
            """,
        ),
        "cik_name_variants": _fetchall(
            cursor,
            "cik_name_variants",
            f"""
            WITH names AS (
              SELECT
                COALESCE(NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''), NULLIF(TRIM(po.summary_json ->> 'cik'), '')) AS cik,
                NULLIF(TRIM(po.summary_json ->> 'company_name'), '') AS company_name,
                regexp_replace(
                  regexp_replace(lower(NULLIF(TRIM(po.summary_json ->> 'company_name'), '')), '[^a-z0-9]+', ' ', 'g'),
                  '\\m(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|class|common|stock)\\M',
                  '',
                  'g'
                ) AS normalized_name
              FROM {obs_from}
              WHERE COALESCE(NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''), NULLIF(TRIM(po.summary_json ->> 'cik'), '')) IS NOT NULL
                AND NULLIF(TRIM(po.summary_json ->> 'company_name'), '') IS NOT NULL
            )
            SELECT
              cik,
              COUNT(DISTINCT company_name) AS name_count,
              COUNT(DISTINCT NULLIF(TRIM(normalized_name), '')) AS material_name_count,
              ARRAY_AGG(DISTINCT company_name ORDER BY company_name) AS company_names
            FROM names
            GROUP BY cik
            HAVING COUNT(DISTINCT company_name) > 1
            ORDER BY material_name_count DESC, name_count DESC, cik
            """,
            obs_params,
        ),
        "unknown_exchange_mapping": _fetchall(
            cursor,
            "unknown_exchange_mapping",
            f"""
            SELECT
              po.summary_json ->> 'exchange' AS raw_exchange,
              COUNT(DISTINCT po.provider_observation_id) AS observation_count,
              ARRAY_AGG(DISTINCT po.provider_observation_id::text ORDER BY po.provider_observation_id::text) AS observation_ids
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
            GROUP BY po.summary_json ->> 'exchange'
            ORDER BY observation_count DESC, raw_exchange
            """,
            obs_params,
        ),
        "listing_exchange_observation_disagreement": _fetchall(
            cursor,
            "listing_exchange_observation_disagreement",
            f"""
            SELECT
              po.provider_observation_id::text AS provider_observation_id,
              pe.listing_id::text AS listing_id,
              po.summary_json ->> 'exchange' AS raw_exchange,
              e.exchange_code AS listing_exchange_code,
              ea.exchange_id::text AS observed_exchange_id
            FROM {obs_from}
            JOIN stonks.provider_evidence pe
              ON pe.provider_observation_id = po.provider_observation_id
             AND pe.listing_id IS NOT NULL
            JOIN stonks.listing l
              ON l.listing_id = pe.listing_id
            JOIN stonks.exchange e
              ON e.exchange_id = l.exchange_id
            JOIN stonks.exchange_alias ea
              ON ea.provider_code = 'SEC'
             AND ea.is_active = TRUE
             AND lower(ea.raw_name) = lower(po.summary_json ->> 'exchange')
            WHERE po.provider_code = 'SEC_COMPANY_TICKERS_EXCHANGE'
              AND ea.exchange_id <> l.exchange_id
            ORDER BY po.provider_observation_id
            """,
            obs_params,
        ),
        "security_current_sec_multiple_exchanges": _fetchall(
            cursor,
            "security_current_sec_multiple_exchanges",
            f"""
            SELECT
              pe.security_id::text AS security_id,
              COALESCE(NULLIF(TRIM(po.summary_json ->> 'ticker_norm'), ''), NULLIF(TRIM(po.summary_json ->> 'ticker'), '')) AS ticker_norm,
              COUNT(DISTINCT ea.exchange_id) AS exchange_count,
              ARRAY_AGG(DISTINCT e.exchange_code ORDER BY e.exchange_code) AS exchange_codes
            FROM {obs_from}
            JOIN stonks.provider_evidence pe
              ON pe.provider_observation_id = po.provider_observation_id
             AND pe.security_id IS NOT NULL
            JOIN stonks.exchange_alias ea
              ON ea.provider_code = 'SEC'
             AND ea.is_active = TRUE
             AND lower(ea.raw_name) = lower(po.summary_json ->> 'exchange')
            JOIN stonks.exchange e
              ON e.exchange_id = ea.exchange_id
            WHERE po.provider_code = 'SEC_COMPANY_TICKERS_EXCHANGE'
              AND COALESCE(NULLIF(TRIM(po.summary_json ->> 'ticker_norm'), ''), NULLIF(TRIM(po.summary_json ->> 'ticker'), '')) IS NOT NULL
            GROUP BY
              pe.security_id,
              COALESCE(NULLIF(TRIM(po.summary_json ->> 'ticker_norm'), ''), NULLIF(TRIM(po.summary_json ->> 'ticker'), ''))
            HAVING COUNT(DISTINCT ea.exchange_id) > 1
            ORDER BY exchange_count DESC, ticker_norm
            """,
            obs_params,
        ),
        "exchange_observation_missing_listing_evidence": _fetchall(
            cursor,
            "exchange_observation_missing_listing_evidence",
            f"""
            SELECT
              po.provider_observation_id::text AS provider_observation_id,
              COALESCE(NULLIF(TRIM(po.summary_json ->> 'ticker_norm'), ''), NULLIF(TRIM(po.summary_json ->> 'ticker'), '')) AS ticker_norm,
              po.summary_json ->> 'exchange' AS raw_exchange,
              COALESCE(NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''), NULLIF(TRIM(po.summary_json ->> 'cik'), '')) AS cik
            FROM {obs_from}
            WHERE po.provider_code = 'SEC_COMPANY_TICKERS_EXCHANGE'
              AND NULLIF(TRIM(po.summary_json ->> 'exchange'), '') IS NOT NULL
              AND NOT EXISTS (
                SELECT 1
                FROM stonks.provider_evidence pe
                WHERE pe.provider_observation_id = po.provider_observation_id
                  AND pe.listing_id IS NOT NULL
              )
            ORDER BY ticker_norm, raw_exchange, po.provider_observation_id
            """,
            obs_params,
        ),
        "evidence_missing_target_rows": _fetchall(
            cursor,
            "evidence_missing_target_rows",
            """
            SELECT
              pe.provider_evidence_id::text AS provider_evidence_id,
              pe.provider_observation_id::text AS provider_observation_id,
              pe.issuer_id::text AS issuer_id,
              pe.security_id::text AS security_id,
              pe.listing_id::text AS listing_id,
              pe.event_id::text AS event_id
            FROM stonks.provider_evidence pe
            LEFT JOIN stonks.issuer i ON i.issuer_id = pe.issuer_id
            LEFT JOIN stonks.security s ON s.security_id = pe.security_id
            LEFT JOIN stonks.listing l ON l.listing_id = pe.listing_id
            LEFT JOIN stonks.security_event ev ON ev.event_id = pe.event_id
            WHERE (pe.issuer_id IS NOT NULL AND i.issuer_id IS NULL)
               OR (pe.security_id IS NOT NULL AND s.security_id IS NULL)
               OR (pe.listing_id IS NOT NULL AND l.listing_id IS NULL)
               OR (pe.event_id IS NOT NULL AND ev.event_id IS NULL)
            ORDER BY pe.provider_evidence_id
            """,
        ),
        "observation_multiple_targets": _fetchall(
            cursor,
            "observation_multiple_targets",
            f"""
            SELECT
              po.provider_observation_id::text AS provider_observation_id,
              COUNT(DISTINCT pe.issuer_id) FILTER (WHERE pe.issuer_id IS NOT NULL) AS issuer_count,
              COUNT(DISTINCT pe.security_id) FILTER (WHERE pe.security_id IS NOT NULL) AS security_count,
              COUNT(DISTINCT pe.listing_id) FILTER (WHERE pe.listing_id IS NOT NULL) AS listing_count,
              ARRAY_AGG(DISTINCT pe.issuer_id::text) FILTER (WHERE pe.issuer_id IS NOT NULL) AS issuer_ids,
              ARRAY_AGG(DISTINCT pe.security_id::text) FILTER (WHERE pe.security_id IS NOT NULL) AS security_ids,
              ARRAY_AGG(DISTINCT pe.listing_id::text) FILTER (WHERE pe.listing_id IS NOT NULL) AS listing_ids
            FROM {obs_from}
            JOIN stonks.provider_evidence pe
              ON pe.provider_observation_id = po.provider_observation_id
            GROUP BY po.provider_observation_id
            HAVING COUNT(DISTINCT pe.issuer_id) FILTER (WHERE pe.issuer_id IS NOT NULL) > 1
                OR COUNT(DISTINCT pe.security_id) FILTER (WHERE pe.security_id IS NOT NULL) > 1
                OR COUNT(DISTINCT pe.listing_id) FILTER (WHERE pe.listing_id IS NOT NULL) > 1
            ORDER BY po.provider_observation_id
            """,
            obs_params,
        ),
    }


def build_conflicts(candidate_rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    add = conflicts.append

    for row in candidate_rows["cik_identifier_multiple_issuers"]:
        add(_conflict("cik_identifier_multiple_issuers", "FAIL", f"CIK {row['cik']} maps to multiple issuers.", {"cik": row["cik"]}, issuer_ids=row.get("issuer_ids"), recommended_action="Review issuer identity and merge or correct CIK identifiers manually."))
    for row in candidate_rows["issuer_missing_cik_from_sec_evidence"]:
        add(_conflict("issuer_missing_cik_from_sec_evidence", "WARN", f"Issuer {row['issuer_id']} has SEC observation evidence for CIK {row['cik']} but no issuer CIK.", {"cik": row["cik"]}, issuer_ids=[row["issuer_id"]], observation_ids=row.get("observation_ids"), recommended_action="Review issuer row and add a CIK identifier if the SEC evidence is authoritative."))
    for row in candidate_rows["observation_cik_issuer_identifier_mismatch"]:
        add(_conflict("observation_cik_issuer_identifier_mismatch", "WARN", f"Observation CIK {row['cik']} links to issuer {row['evidence_issuer_id']} but the CIK identifier belongs to issuer {row['identifier_issuer_id']}.", {"cik": row["cik"]}, issuer_ids=[row["evidence_issuer_id"], row["identifier_issuer_id"]], observation_ids=[row["provider_observation_id"]], recommended_action="Review issuer evidence and CIK identifier ownership before any merge."))
    for row in candidate_rows["same_issuer_ticker_multiple_securities"]:
        add(_conflict("same_issuer_ticker_multiple_securities", "WARN", f"Issuer {row['issuer_id']} has ticker {row['ticker_norm']} mapped to multiple securities.", {"ticker_norm": row["ticker_norm"]}, issuer_ids=[row["issuer_id"]], security_ids=row.get("security_ids"), recommended_action="Review whether securities represent distinct instruments or duplicate security rows."))
    for row in candidate_rows["ticker_exchange_multiple_securities"]:
        add(_conflict("ticker_exchange_multiple_securities", "FAIL", f"Active ticker {row['ticker_norm']} on {row['exchange_code']} maps to multiple securities.", {"ticker_norm": row["ticker_norm"], "exchange_code": row["exchange_code"]}, security_ids=row.get("security_ids"), listing_ids=row.get("listing_ids"), recommended_action="Block automated resolution and review active listing/security mappings."))
    for row in candidate_rows["ticker_exchange_multiple_issuers"]:
        add(_conflict("ticker_exchange_multiple_issuers", "WARN", f"Active ticker {row['ticker_norm']} on {row['exchange_code']} maps to multiple issuers.", {"ticker_norm": row["ticker_norm"], "exchange_code": row["exchange_code"]}, issuer_ids=row.get("issuer_ids"), security_ids=row.get("security_ids"), recommended_action="Review issuer/security ownership for the active ticker and exchange."))
    for row in candidate_rows["observation_ticker_security_identifier_mismatch"]:
        add(_conflict("observation_ticker_security_identifier_mismatch", "WARN", f"Observation ticker {row['observation_ticker_norm']} disagrees with security ticker identifiers.", {"ticker_norm": row["observation_ticker_norm"]}, security_ids=[row["security_id"]], observation_ids=[row["provider_observation_id"]], recommended_action="Review security identifier history and provider evidence target."))
    for row in candidate_rows["ticker_exchange_multiple_active_listings"]:
        add(_conflict("ticker_exchange_multiple_active_listings", "FAIL", f"Active ticker {row['ticker_norm']} on {row['exchange_code']} has multiple active listings.", {"ticker_norm": row["ticker_norm"], "exchange_code": row["exchange_code"]}, listing_ids=row.get("listing_ids"), recommended_action="Review active listings before closing or merging any records."))
    for row in candidate_rows["security_exchange_multiple_active_listings"]:
        add(_conflict("security_exchange_multiple_active_listings", "WARN", f"Security {row['security_id']} has multiple active listings on {row['exchange_code']}.", {"exchange_code": row["exchange_code"]}, security_ids=[row["security_id"]], listing_ids=row.get("listing_ids"), recommended_action="Review listing lifecycle and symbol history for duplicate active listings."))
    for row in candidate_rows["active_listing_missing_current_symbol"]:
        add(_conflict("active_listing_missing_current_symbol", "WARN", f"Active listing {row['listing_id']} has no current symbol history.", {"exchange_code": row["exchange_code"]}, security_ids=[row["security_id"]], listing_ids=[row["listing_id"]], recommended_action="Review listing symbol history and add a current symbol if supported by evidence."))
    for row in candidate_rows["listing_multiple_current_symbols"]:
        add(_conflict("listing_multiple_current_symbols", "WARN", f"Listing {row['listing_id']} has multiple current symbols.", {"exchange_id": row.get("exchange_id"), "exchange_code": row.get("exchange_code"), "ticker_norms": row.get("ticker_norms")}, security_ids=[row["security_id"]], listing_ids=[row["listing_id"]], recommended_action="Review symbol history validity windows and close all but one active symbol before backfill."))
    for row in candidate_rows["cik_name_variants"]:
        severity = "WARN" if int(row.get("material_name_count") or 0) > 1 else "INFO"
        add(_conflict("cik_name_variants", severity, f"CIK {row['cik']} appears with multiple company name variants.", {"cik": row["cik"], "company_names": row.get("company_names")}, recommended_action="Treat minor suffix/punctuation variants as informational; review material name differences."))
    for row in candidate_rows["unknown_exchange_mapping"]:
        add(_conflict("unknown_exchange_mapping", "WARN", f"SEC raw exchange {row['raw_exchange']} has no active exchange alias mapping.", {"raw_exchange": row["raw_exchange"]}, observation_ids=row.get("observation_ids"), recommended_action="Add or update exchange_alias mapping if this exchange should produce listings."))
    for row in candidate_rows["listing_exchange_observation_disagreement"]:
        add(_conflict("listing_exchange_observation_disagreement", "WARN", f"Observation exchange {row['raw_exchange']} disagrees with listing exchange {row['listing_exchange_code']}.", {"raw_exchange": row["raw_exchange"], "exchange_code": row["listing_exchange_code"]}, listing_ids=[row["listing_id"]], observation_ids=[row["provider_observation_id"]], recommended_action="Review listing target and exchange alias mapping."))
    for row in candidate_rows["security_current_sec_multiple_exchanges"]:
        add(_conflict("security_current_sec_multiple_exchanges", "INFO", f"Security {row['security_id']} ticker {row['ticker_norm']} appears on multiple current SEC exchanges.", {"ticker_norm": row["ticker_norm"], "exchange_codes": row.get("exchange_codes")}, security_ids=[row["security_id"]], recommended_action="Confirm whether multiple active exchange listings are expected."))
    for row in candidate_rows["exchange_observation_missing_listing_evidence"]:
        add(_conflict("exchange_observation_missing_listing_evidence", "WARN", f"Exchange observation for ticker {row['ticker_norm']} lacks listing evidence.", {"ticker_norm": row["ticker_norm"], "raw_exchange": row["raw_exchange"], "cik": row["cik"]}, observation_ids=[row["provider_observation_id"]], recommended_action="Review why listing upsert did not create or link listing evidence."))
    for row in candidate_rows["evidence_missing_target_rows"]:
        add(_conflict("evidence_missing_target_rows", "FAIL", "Provider evidence points to a missing target row.", {}, issuer_ids=[row.get("issuer_id")], security_ids=[row.get("security_id")], listing_ids=[row.get("listing_id")], observation_ids=[row.get("provider_observation_id")], recommended_action="Repair orphaned provider evidence before relying on conflict resolution."))
    for row in candidate_rows["observation_multiple_targets"]:
        add(_conflict("observation_multiple_targets", "WARN", f"Observation {row['provider_observation_id']} links to multiple targets unexpectedly.", {}, issuer_ids=row.get("issuer_ids"), security_ids=row.get("security_ids"), listing_ids=row.get("listing_ids"), observation_ids=[row["provider_observation_id"]], recommended_action="Review evidence fan-out before automated resolution."))
    return conflicts


def summarize_conflicts(conflicts: list[dict[str, Any]]) -> dict[str, Any]:
    failures_total = sum(1 for conflict in conflicts if conflict["severity"] == "FAIL")
    warnings_total = sum(1 for conflict in conflicts if conflict["severity"] == "WARN")
    info_total = sum(1 for conflict in conflicts if conflict["severity"] == "INFO")
    return {
        "status": evaluate_conflict_status(conflicts),
        "conflicts_total": len(conflicts),
        "failures_total": failures_total,
        "warnings_total": warnings_total,
        "info_total": info_total,
    }


def evaluate_conflict_status(conflicts: list[dict[str, Any]]) -> str:
    severities = {conflict["severity"] for conflict in conflicts}
    if "FAIL" in severities:
        return "FAIL"
    if "WARN" in severities:
        return "WARN"
    return "PASS"


def conflicts_by_category(conflicts: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    categories: dict[str, dict[str, int]] = {}
    for conflict in conflicts:
        bucket = categories.setdefault(
            conflict["category"],
            {"total": 0, "failures": 0, "warnings": 0, "info": 0},
        )
        bucket["total"] += 1
        if conflict["severity"] == "FAIL":
            bucket["failures"] += 1
        elif conflict["severity"] == "WARN":
            bucket["warnings"] += 1
        elif conflict["severity"] == "INFO":
            bucket["info"] += 1
    return dict(sorted(categories.items()))


def conflict_report_to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def write_conflict_report_to_console(report: dict[str, Any]) -> None:
    print(conflict_report_to_json(report), end="")


def write_conflict_report_to_file(report: dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(conflict_report_to_json(report), encoding="utf-8")
    return output_path


def default_conflict_report_path(
    *,
    temp_dir: str | Path | None = None,
    generated_at: datetime | None = None,
    logical_date: Any = None,
) -> Path:
    generated_at = generated_at or datetime.now(UTC)
    root = Path(temp_dir or os.environ.get("EMPIRE_TEMP_DIR", "/tmp"))
    filename = f"stonks_securities_conflicts_{generated_at:%Y%m%dT%H%M%SZ}.json"
    return run_report_path(
        root=root,
        report_type="conflicts",
        filename=filename,
        logical_date=logical_date,
        generated_at=generated_at,
    )


def write_conflict_report_to_object_store(
    *,
    report: dict[str, Any],
    object_store: ObjectStore,
    storage_root: str = DEFAULT_STORAGE_ROOT,
    storage_key: str | None = None,
    generated_at: datetime | None = None,
    logical_date: Any = None,
):
    generated_at = generated_at or datetime.now(UTC)
    resolved_storage_key = (storage_key or default_storage_key()).strip("/")
    object_key = run_report_object_key(
        storage_key=resolved_storage_key,
        report_type="conflicts",
        logical_date=logical_date or report.get("run_context", {}).get("logical_date"),
        generated_at=generated_at,
    )
    filename = f"stonks_securities_conflicts_{generated_at:%Y%m%dT%H%M%SZ}.json"
    return object_store.put_bytes(
        run_context=None,
        object_scope="manual",
        domain="stonks",
        logical_name=CONFLICT_REPORT_LOGICAL_NAME,
        storage_root=storage_root,
        object_key=object_key,
        filename=filename,
        data=conflict_report_to_json(report).encode("utf-8"),
        content_type="application/json",
        object_kind=CONFLICT_REPORT_OBJECT_KIND,
        metadata={"report_name": CONFLICT_REPORT_NAME, "generated_at": report["generated_at"]},
    )


def _conflict(
    category: str,
    severity: str,
    message: str,
    keys: dict[str, Any],
    *,
    issuer_ids: list[Any] | None = None,
    security_ids: list[Any] | None = None,
    listing_ids: list[Any] | None = None,
    observation_ids: list[Any] | None = None,
    recommended_action: str,
) -> dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "message": message,
        "keys": keys,
        "entity_ids": {
            "issuer_ids": _clean_ids(issuer_ids),
            "security_ids": _clean_ids(security_ids),
            "listing_ids": _clean_ids(listing_ids),
            "observation_ids": _clean_ids(observation_ids),
        },
        "recommended_action": recommended_action,
    }


def _clean_ids(values: list[Any] | None) -> list[str]:
    if not values:
        return []
    return [str(value) for value in values if value is not None]


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
                LEFT JOIN stonks.provider_source_snapshot_object psso
                  ON psso.object_id = so.object_id
                WHERE so.run_id = %s
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
                LEFT JOIN stonks.provider_source_snapshot_object psso_scope
                  ON psso_scope.object_id = so_scope.object_id
                WHERE so_scope.run_id = %s
                  AND so_scope.object_kind = 'sec_source_file'
                  AND (
                    psso_scope.source_snapshot_id = po_scope.source_snapshot_id
                    OR (
                      po_scope.source_snapshot_id IS NULL
                      AND (
                        so_scope.object_id = po_scope.object_id
                        OR so_scope.checksum_sha256 = po_scope.summary_json #>> '{source_file,sha256}'
                        OR so_scope.object_key = po_scope.summary_json #>> '{source_file,object_key}'
                      )
                    )
                  )
            )
        ) l
        """,
        (source_run_id,),
    )


def _fetchall(cursor: Any, metric: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor.execute(_tag(metric, sql), params)
    return [row_to_dict(cursor, row) for row in cursor.fetchall()]


def _tag(metric: str, sql: str) -> str:
    return f"/* metric: {metric} */\n{sql}"
