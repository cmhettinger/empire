"""Build and store durable Yahoo backfill and daily health reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any, Mapping

from empire_core import ObjectStore, RunContext, StoredObject

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.object_store import DEFAULT_STORAGE_ROOT
from empire_stonks_ohlcv.reporting import (
    REPORT_CONTENT_TYPE,
    REPORT_OBJECT_KIND,
    REPORT_SCHEMA_VERSION,
    build_report_object_key,
)
from empire_stonks_ohlcv.source_conventions import YAHOO_DAILY_SOURCE
from empire_stonks_ohlcv.validation import MAX_ISSUE_SAMPLES
from empire_stonks_ohlcv.yahoo import (
    YAHOO_PROVIDER_CODE,
    YahooAcquisitionResult,
    YahooAcquisitionStatus,
    YahooListingTarget,
)
from empire_stonks_ohlcv.yahoo_completeness import (
    YahooCompletenessStatus,
    YahooDailyCompletenessPlan,
    select_yahoo_stored_session_dates,
)
from empire_stonks_ohlcv.yahoo_import import (
    YahooImportPurpose,
    YahooImportResult,
)
from empire_stonks_ohlcv.yahoo_reconciliation import YahooReconciliationPlan


YAHOO_BACKFILL_REPORT_TYPE = "yahoo_historical_backfill"
YAHOO_BACKFILL_REPORT_LOGICAL_NAME = "yahoo_backfill_report"
YAHOO_DAILY_REPORT_TYPE = "yahoo_daily_health"
YAHOO_DAILY_REPORT_LOGICAL_NAME = "yahoo_daily_report"
YAHOO_REPORT_FILENAME = "report.json"
YAHOO_BACKFILL_REPORT_FILENAME = YAHOO_REPORT_FILENAME
YAHOO_DAILY_REPORT_FILENAME = YAHOO_REPORT_FILENAME


class YahooReportPhase(StrEnum):
    """Operational phase represented by one report result."""

    INITIAL_INGESTION = "initial_ingestion"
    DAILY_INGESTION = "daily_ingestion"
    RECONCILIATION = "reconciliation"


@dataclass(frozen=True)
class YahooReportPhaseResult:
    """Acquisition and persistence result for one explicit Yahoo phase."""

    phase: YahooReportPhase
    acquisition: YahooAcquisitionResult
    import_result: YahooImportResult
    parse_failed_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.phase, YahooReportPhase):
            raise TypeError("phase must be a YahooReportPhase.")
        if not isinstance(self.acquisition, YahooAcquisitionResult):
            raise TypeError("acquisition must be a YahooAcquisitionResult.")
        if not isinstance(self.import_result, YahooImportResult):
            raise TypeError("import_result must be a YahooImportResult.")
        _nonnegative_int("parse_failed_count", self.parse_failed_count)
        if len(self.acquisition.outcomes) != self.import_result.chunk_count:
            raise ValueError("Import results must cover every acquisition outcome.")
        purpose = (
            YahooImportPurpose.RECONCILIATION
            if self.phase is YahooReportPhase.RECONCILIATION
            else YahooImportPurpose.INGESTION
        )
        if any(
            chunk.purpose is not purpose
            for listing in self.import_result.listings
            for chunk in listing.chunks
        ):
            raise ValueError("Import purpose must match the report phase.")

    @property
    def retry_count(self) -> int:
        """Return provider calls beyond the first attempt."""

        return sum(max(item.attempts - 1, 0) for item in self.acquisition.outcomes)

    @property
    def retried_request_count(self) -> int:
        return sum(item.attempts > 1 for item in self.acquisition.outcomes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "request_count": len(self.acquisition.outcomes),
            "retry_count": self.retry_count,
            "retried_request_count": self.retried_request_count,
            "acquisition": self.acquisition.to_safe_dict(),
            "parse_failed_count": self.parse_failed_count,
            "import": self.import_result.to_dict(),
            "reconciliation": _reconciliation_summary(self.import_result),
        }


def empty_yahoo_report_phase(phase: YahooReportPhase) -> YahooReportPhaseResult:
    """Return a typed no-op phase for daily runs with no planned requests."""

    return YahooReportPhaseResult(
        phase=phase,
        acquisition=YahooAcquisitionResult(()),
        import_result=YahooImportResult(()),
    )


def build_yahoo_backfill_report(
    *,
    cursor: Any,
    run_context: RunContext,
    scope: Mapping[str, Any],
    listings: tuple[YahooListingTarget, ...],
    enumerated_listing_count: int,
    result: YahooReportPhaseResult,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a schema-v2 backfill report including persisted date coverage."""

    _validate_run_context(run_context)
    if result.phase is not YahooReportPhase.INITIAL_INGESTION:
        raise ValueError("Backfill reports require initial_ingestion results.")
    _validate_listings(listings)
    _nonnegative_int("enumerated_listing_count", enumerated_listing_count)
    if enumerated_listing_count < len(listings):
        raise ValueError("enumerated_listing_count must cover selected listings.")
    start_date = _scope_date(scope, "start_date")
    end_date_exclusive = _scope_date(scope, "end_date_exclusive")
    if end_date_exclusive <= start_date:
        raise ValueError("Backfill scope dates are invalid.")
    stored = _select_backfill_coverage(
        cursor=cursor,
        listings=listings,
        start_date=start_date,
        end_date=end_date_exclusive - timedelta(days=1),
    )
    coverage = _backfill_coverage(listings=listings, stored=stored)
    warning_count = _phase_warning_count(result)
    generated = _generated_at(generated_at)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": YAHOO_BACKFILL_REPORT_TYPE,
        "provider_code": YAHOO_PROVIDER_CODE,
        "source_code": YAHOO_DAILY_SOURCE.source_code,
        "run_id": str(run_context.run_id),
        "effective_date": run_context.effective_date.isoformat(),
        "generated_at": generated.isoformat(),
        "outcome": "WARN" if warning_count else "PASS",
        "workflow": "initial_ingestion",
        "scope": dict(scope),
        "enumerated_listing_count": enumerated_listing_count,
        "selected_listing_count": len(listings),
        "acquisition": result.acquisition.to_safe_dict(),
        "parse_failed_count": result.parse_failed_count,
        "import": result.import_result.to_dict(),
        "phase_results": [result.to_dict()],
        "coverage": coverage,
        "health": {
            "warning_count": warning_count,
            "calendar_policy_error_count": 0,
            "stale_listing_count": 0,
        },
        "native_value_semantics": _native_value_semantics(result),
    }


def build_yahoo_daily_report(
    *,
    cursor: Any,
    run_context: RunContext,
    completeness_plan: YahooDailyCompletenessPlan,
    reconciliation_plan: YahooReconciliationPlan,
    ingestion_result: YahooReportPhaseResult,
    reconciliation_result: YahooReportPhaseResult,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build calendar-aware Yahoo health from post-import persisted state."""

    _validate_run_context(run_context)
    if not isinstance(completeness_plan, YahooDailyCompletenessPlan):
        raise TypeError("completeness_plan must be a YahooDailyCompletenessPlan.")
    if not isinstance(reconciliation_plan, YahooReconciliationPlan):
        raise TypeError("reconciliation_plan must be a YahooReconciliationPlan.")
    if reconciliation_plan.completeness_plan != completeness_plan:
        raise ValueError("Reconciliation must use the reported completeness plan.")
    if ingestion_result.phase is not YahooReportPhase.DAILY_INGESTION:
        raise ValueError("ingestion_result must be daily_ingestion.")
    if reconciliation_result.phase is not YahooReportPhase.RECONCILIATION:
        raise ValueError("reconciliation_result must be reconciliation.")

    listings = tuple(item.listing for item in completeness_plan.listings)
    stored = select_yahoo_stored_session_dates(
        cursor=cursor,
        provider_listing_ids=tuple(item.provider_listing_id for item in listings),
        start_date=completeness_plan.start_date,
        end_date=completeness_plan.end_date,
    )
    coverage = _daily_coverage(completeness_plan, stored)
    phases = (ingestion_result, reconciliation_result)
    calendar_errors = tuple(
        {
            "provider_listing_id": str(item.listing.provider_listing_id),
            "ticker": item.listing.ticker,
            "policy_code": item.policy_code,
            "failure_reason": item.failure_reason.value,
        }
        for item in completeness_plan.listings
        if item.status is YahooCompletenessStatus.FAILED
        and item.failure_reason is not None
    )
    stale = tuple(
        item
        for item in coverage["listings"]
        if item["stale"]
    )
    phase_warning_count = sum(_phase_warning_count(item) for item in phases)
    corrected_count = reconciliation_result.import_result.corrected_reconciliation_bars
    warning_count = (
        phase_warning_count
        + len(calendar_errors)
        + coverage["missing_eligible_session_count"]
        + coverage["unresolved_observed_poll_count"]
        + corrected_count
    )
    generated = _generated_at(generated_at)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": YAHOO_DAILY_REPORT_TYPE,
        "provider_code": YAHOO_PROVIDER_CODE,
        "source_code": YAHOO_DAILY_SOURCE.source_code,
        "run_id": str(run_context.run_id),
        "effective_date": run_context.effective_date.isoformat(),
        "generated_at": generated.isoformat(),
        "outcome": "WARN" if warning_count else "PASS",
        "workflow": "daily_ingestion_and_reconciliation",
        "scope": {
            "start_date": completeness_plan.start_date.isoformat(),
            "end_date": completeness_plan.end_date.isoformat(),
            "planned_at": completeness_plan.planned_at.isoformat(),
            "enumerated_listing_count": (
                completeness_plan.enumerated_listing_count
            ),
            "selected_listing_count": len(completeness_plan.listings),
            "reconciliation_session_count": reconciliation_plan.session_count,
        },
        "phase_results": [item.to_dict() for item in phases],
        "coverage": coverage,
        "health": {
            "warning_count": warning_count,
            "stale_listing_count": len(stale),
            "stale_listings": _bounded(stale),
            "calendar_policy_error_count": len(calendar_errors),
            "calendar_policy_errors": _bounded(calendar_errors),
        },
        "native_value_semantics": _native_value_semantics(
            reconciliation_result
        ),
    }


def yahoo_report_to_json(report: Mapping[str, Any]) -> str:
    """Validate and serialize one Yahoo report deterministically."""

    _validate_report(report)
    return json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"


def store_yahoo_report(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    report: dict[str, Any],
    storage_root: str = DEFAULT_STORAGE_ROOT,
) -> StoredObject:
    """Store a non-expiring Yahoo report separately from expiring raw data."""

    if not isinstance(object_store, ObjectStore):
        raise TypeError("object_store must be a Core ObjectStore.")
    if not isinstance(config, OHLCVConfig):
        raise TypeError("config must be an OHLCVConfig.")
    _validate_run_context(run_context)
    _validate_report(report)
    if report["effective_date"] != run_context.effective_date.isoformat():
        raise ValueError("report effective_date must match the Core run.")
    report_type = report["report_type"]
    logical_name = {
        YAHOO_BACKFILL_REPORT_TYPE: YAHOO_BACKFILL_REPORT_LOGICAL_NAME,
        YAHOO_DAILY_REPORT_TYPE: YAHOO_DAILY_REPORT_LOGICAL_NAME,
    }[report_type]
    return object_store.put_bytes(
        run_context=run_context,
        object_scope="run",
        domain="stonks",
        logical_name=logical_name,
        storage_root=storage_root,
        object_key=build_report_object_key(
            storage_key=config.storage_key,
            run_context=run_context,
            provider_code=YAHOO_PROVIDER_CODE,
        ),
        filename=YAHOO_REPORT_FILENAME,
        data=yahoo_report_to_json(report).encode("utf-8"),
        content_type=REPORT_CONTENT_TYPE,
        object_kind=REPORT_OBJECT_KIND,
        metadata={
            "schema_version": REPORT_SCHEMA_VERSION,
            "report_type": report_type,
            "provider_code": YAHOO_PROVIDER_CODE,
            "source_code": YAHOO_DAILY_SOURCE.source_code,
            "effective_date": report["effective_date"],
            "generated_at": report["generated_at"],
            "outcome": report["outcome"],
            "workflow": report["workflow"],
        },
    )


def _daily_coverage(
    plan: YahooDailyCompletenessPlan,
    stored: Mapping[Any, tuple[date, ...]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in plan.listings:
        stored_dates = stored[item.listing.provider_listing_id]
        eligible_dates = tuple(value.session_date for value in item.eligible_sessions)
        expected_dates = tuple(value.session_date for value in item.expected_sessions)
        stored_eligible = tuple(
            value for value in eligible_dates if value in stored_dates
        )
        missing = tuple(value for value in eligible_dates if value not in stored_dates)
        candidate_dates = tuple(
            value.candidate_date for value in item.observed_poll_candidates
        )
        unresolved = tuple(
            value for value in candidate_dates if value not in stored_dates
        )
        latest_eligible = eligible_dates[-1] if eligible_dates else None
        latest_stored = stored_dates[-1] if stored_dates else None
        authoritative = not item.observed_only
        rows.append(
            {
                "provider_listing_id": str(item.listing.provider_listing_id),
                "ticker": item.listing.ticker,
                "policy_code": item.policy_code,
                "status": item.status.value,
                "coverage_basis": (
                    "observed_only" if item.observed_only else "authoritative_calendar"
                ),
                "expected_session_count": len(expected_dates),
                "eligible_session_count": len(eligible_dates),
                "ineligible_session_count": item.ineligible_session_count,
                "stored_eligible_session_count": len(stored_eligible),
                "missing_eligible_session_count": len(missing),
                "missing_eligible_dates": [value.isoformat() for value in missing],
                "observed_poll_candidate_count": len(candidate_dates),
                "unresolved_observed_poll_count": len(unresolved),
                "unresolved_observed_poll_dates": [
                    value.isoformat() for value in unresolved
                ],
                "coverage_percent": (
                    None
                    if not authoritative or not eligible_dates
                    else round(100 * len(stored_eligible) / len(eligible_dates), 2)
                ),
                "latest_eligible_session": _date_text(latest_eligible),
                "latest_stored_session": _date_text(latest_stored),
                "stale": bool(
                    authoritative
                    and latest_eligible is not None
                    and (
                        latest_stored is None
                        or latest_stored < latest_eligible
                    )
                ),
                "failure_reason": (
                    None if item.failure_reason is None else item.failure_reason.value
                ),
            }
        )
    authoritative_rows = tuple(
        row for row in rows if row["coverage_basis"] == "authoritative_calendar"
    )
    eligible = sum(row["eligible_session_count"] for row in authoritative_rows)
    stored_eligible = sum(
        row["stored_eligible_session_count"] for row in authoritative_rows
    )
    return {
        "authoritative_listing_count": len(authoritative_rows),
        "observed_only_listing_count": len(rows) - len(authoritative_rows),
        "expected_session_count": sum(
            row["expected_session_count"] for row in authoritative_rows
        ),
        "eligible_session_count": eligible,
        "ineligible_session_count": sum(
            row["ineligible_session_count"] for row in authoritative_rows
        ),
        "stored_eligible_session_count": stored_eligible,
        "missing_eligible_session_count": eligible - stored_eligible,
        "unresolved_observed_poll_count": sum(
            row["unresolved_observed_poll_count"] for row in rows
        ),
        "coverage_percent": (
            None if not eligible else round(100 * stored_eligible / eligible, 2)
        ),
        "listings": rows,
    }


def _backfill_coverage(
    *,
    listings: tuple[YahooListingTarget, ...],
    stored: Mapping[Any, tuple[int, date | None, date | None]],
) -> dict[str, Any]:
    rows = tuple(
        {
            "provider_listing_id": str(item.provider_listing_id),
            "ticker": item.ticker,
            "scoped_bar_count": stored[item.provider_listing_id][0],
            "first_scoped_trading_date": _date_text(
                stored[item.provider_listing_id][1]
            ),
            "last_scoped_trading_date": _date_text(
                stored[item.provider_listing_id][2]
            ),
        }
        for item in listings
    )
    return {
        "selected_listing_count": len(rows),
        "listings_with_scoped_bars": sum(item["scoped_bar_count"] > 0 for item in rows),
        "scoped_bar_count": sum(item["scoped_bar_count"] for item in rows),
        "listings": list(rows),
    }


def _select_backfill_coverage(
    *,
    cursor: Any,
    listings: tuple[YahooListingTarget, ...],
    start_date: date,
    end_date: date,
) -> dict[Any, tuple[int, date | None, date | None]]:
    """Aggregate a potentially large history scope without loading every date."""

    listing_ids = tuple(item.provider_listing_id for item in listings)
    result = {item: (0, None, None) for item in listing_ids}
    if not listing_ids:
        return result
    cursor.execute(
        """
        SELECT provider_listing_id,
               count(*)::bigint,
               min(trading_date),
               max(trading_date)
        FROM stonks.ohlcv_daily
        WHERE provider_listing_id = ANY(%s)
          AND trading_date BETWEEN %s AND %s
        GROUP BY provider_listing_id
        ORDER BY provider_listing_id
        """,
        (list(listing_ids), start_date, end_date),
    )
    for row in cursor.fetchall():
        if not isinstance(row, (tuple, list)) or len(row) != 4:
            raise ValueError("Yahoo backfill coverage query returned an invalid row.")
        listing_id, count, first_date, last_date = row
        if (
            listing_id not in result
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
            or type(first_date) is not date
            or type(last_date) is not date
            or first_date > last_date
        ):
            raise ValueError("Yahoo backfill coverage query returned invalid data.")
        result[listing_id] = (count, first_date, last_date)
    return result


def _reconciliation_summary(result: YahooImportResult) -> dict[str, Any] | None:
    chunks = tuple(
        chunk
        for listing in result.listings
        for chunk in listing.chunks
        if chunk.reconciliation is not None
    )
    if not chunks:
        return None
    field_counts = {name: 0 for name in ("open", "high", "low", "close", "volume")}
    for chunk in chunks:
        assert chunk.reconciliation is not None
        for name, count in chunk.reconciliation.field_difference_counts.items():
            field_counts[name] += count
    return {
        "inserted_bar_count": result.inserted_reconciliation_bars,
        "corrected_bar_count": result.corrected_reconciliation_bars,
        "unchanged_bar_count": result.unchanged_reconciliation_bars,
        "field_difference_counts": field_counts,
        "adjusted_close_response_count": sum(
            chunk.reconciliation.adjusted_close_present for chunk in chunks
            if chunk.reconciliation is not None
        ),
        "adjusted_close_difference_count": sum(
            comparison.difference_from_native not in (None, 0)
            for chunk in chunks
            if chunk.reconciliation is not None
            for comparison in chunk.reconciliation.adjusted_close_comparisons
        ),
        "invalid_adjusted_close_rows": sum(
            chunk.reconciliation.invalid_adjusted_close_rows for chunk in chunks
            if chunk.reconciliation is not None
        ),
    }


def _native_value_semantics(result: YahooReportPhaseResult) -> dict[str, Any]:
    reconciliation = _reconciliation_summary(result.import_result)
    return {
        "interval": "daily",
        "price_basis": "provider_native_unadjusted",
        "native_close_persisted": True,
        "adjusted_close_inspected_during_reconciliation": (
            result.phase is YahooReportPhase.RECONCILIATION
        ),
        "adjusted_close_persisted": False,
        "adjusted_close_note": (
            "Yahoo adjusted close is diagnostic only; the native close remains "
            "the stored close and no Yahoo-only bar column is created."
        ),
        "adjusted_close_observations": reconciliation,
        "volume_nullable": True,
        "correction_behavior": "overwrite_same_provider_listing_and_trading_date",
        "seeded_listing_writes": 0,
        "canonical_identity_mutation": False,
    }


def _phase_warning_count(result: YahooReportPhaseResult) -> int:
    return (
        result.acquisition.failed_count
        + result.acquisition.missing_count
        + result.parse_failed_count
        + result.import_result.failed_chunks
        + result.import_result.missing_chunks
    )


def _bounded(values: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    samples = values[:MAX_ISSUE_SAMPLES]
    return {
        "total_count": len(values),
        "sample_count": len(samples),
        "truncated": len(samples) < len(values),
        "samples": list(samples),
    }


def _validate_report(report: Mapping[str, Any]) -> None:
    if not isinstance(report, Mapping):
        raise TypeError("report must be a mapping.")
    required = {
        "schema_version",
        "report_type",
        "provider_code",
        "source_code",
        "run_id",
        "effective_date",
        "generated_at",
        "outcome",
        "workflow",
        "phase_results",
        "coverage",
        "health",
        "native_value_semantics",
    }
    if not required <= set(report):
        raise ValueError("Yahoo report is missing required fields.")
    if report["schema_version"] != REPORT_SCHEMA_VERSION:
        raise ValueError("Yahoo report schema_version is invalid.")
    if report["report_type"] not in {
        YAHOO_BACKFILL_REPORT_TYPE,
        YAHOO_DAILY_REPORT_TYPE,
    }:
        raise ValueError("Yahoo report_type is invalid.")
    if report["provider_code"] != YAHOO_PROVIDER_CODE:
        raise ValueError("Yahoo report provider_code is invalid.")
    if report["source_code"] != YAHOO_DAILY_SOURCE.source_code:
        raise ValueError("Yahoo report source_code is invalid.")
    if report["outcome"] not in {"PASS", "WARN", "FAIL"}:
        raise ValueError("Yahoo report outcome is invalid.")
    date.fromisoformat(report["effective_date"])
    datetime.fromisoformat(report["generated_at"])


def _validate_run_context(run_context: RunContext) -> None:
    if not isinstance(run_context, RunContext):
        raise TypeError("run_context must be a Core RunContext.")
    if run_context.effective_date is None:
        raise ValueError("run_context must have an effective_date.")


def _validate_listings(listings: tuple[YahooListingTarget, ...]) -> None:
    if not isinstance(listings, tuple) or any(
        not isinstance(item, YahooListingTarget) for item in listings
    ):
        raise TypeError("listings must contain YahooListingTarget values.")
    identities = tuple(item.provider_listing_id for item in listings)
    if len(identities) != len(set(identities)):
        raise ValueError("listings must be unique.")


def _scope_date(scope: Mapping[str, Any], key: str) -> date:
    if not isinstance(scope, Mapping):
        raise TypeError("scope must be a mapping.")
    value = scope.get(key)
    if not isinstance(value, str):
        raise ValueError(f"scope {key} must be an ISO date string.")
    return date.fromisoformat(value)


def _generated_at(value: datetime | None) -> datetime:
    current = datetime.now(UTC) if value is None else value
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise ValueError("generated_at must be an aware datetime.")
    return current.astimezone(UTC)


def _date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _nonnegative_int(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
