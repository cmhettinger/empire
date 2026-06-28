"""Daily refresh summary report generation for the SEC security-master pipeline."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from empire_core import ObjectStore, RunContext as CoreRunContext
from empire_core.db.postgres import row_to_dict

from empire_stonks_securities.acquisition import DEFAULT_STORAGE_ROOT, default_storage_key
from empire_stonks_securities.conflicts import CONFLICT_REPORT_OBJECT_KIND
from empire_stonks_securities.reports.daily_refresh_summary.data import (
    load_canonical_market_snapshot,
)
from empire_stonks_securities.reports.daily_refresh_summary.pdf.render import (
    DAILY_SUMMARY_PDF_LOGICAL_NAME,
    DAILY_SUMMARY_PDF_OBJECT_KIND,
    render_daily_refresh_summary_pdf,
)
from empire_stonks_securities.report_paths import run_report_object_key, run_report_path
from empire_stonks_securities.validation import REPORT_OBJECT_KIND as VALIDATION_REPORT_OBJECT_KIND
from empire_stonks_securities.verification import VERIFY_REPORT_OBJECT_KIND


DAILY_SUMMARY_REPORT_NAME = "stonks_securities_daily_summary"
DAILY_SUMMARY_REPORT_OBJECT_KIND = "stonks_securities_daily_summary_report"
DAILY_SUMMARY_REPORT_LOGICAL_NAME = "stonks_securities_daily_summary"
DAILY_SUMMARY_PDF_RETENTION_DAYS = 7
REQUIRED_DAILY_SOURCES = ("sec_company_tickers_exchange", "sec_company_tickers")
DEFAULT_STALE_WARN_HOURS = 36
DEFAULT_STALE_FAIL_HOURS = 96


@dataclass(frozen=True)
class DailySummaryRunContext:
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


def generate_daily_refresh_summary_report(
    *,
    connection: Any,
    object_store: ObjectStore | None = None,
    run_context: DailySummaryRunContext | None = None,
    source_run_id: str | UUID | None = None,
    verify_report_object_id: str | UUID | None = None,
    validation_report_object_id: str | UUID | None = None,
    conflict_report_object_id: str | UUID | None = None,
    generated_at: datetime | None = None,
    stale_warn_hours: int = DEFAULT_STALE_WARN_HOURS,
    stale_fail_hours: int = DEFAULT_STALE_FAIL_HOURS,
) -> dict[str, Any]:
    """Generate a JSON-ready final daily refresh summary report."""

    generated_at = generated_at or datetime.now(UTC)
    resolved_run_context = run_context or DailySummaryRunContext(
        source_run_id=str(source_run_id) if source_run_id is not None else None
    )
    resolved_source_run_id = source_run_id or resolved_run_context.source_run_id
    source_run_text = str(resolved_source_run_id) if resolved_source_run_id is not None else None

    with connection.cursor() as cursor:
        current_sources = _current_source_files(cursor, source_run_id=source_run_text)
        previous_sources = _previous_source_files(cursor, current_sources=current_sources)
        validation_object = _linked_report_object(
            cursor,
            object_kind=VALIDATION_REPORT_OBJECT_KIND,
            object_id=validation_report_object_id,
            generated_at=generated_at,
            report_type="validation",
            logical_date=resolved_run_context.logical_date,
        )
        conflict_object = _linked_report_object(
            cursor,
            object_kind=CONFLICT_REPORT_OBJECT_KIND,
            object_id=conflict_report_object_id,
            generated_at=generated_at,
            report_type="conflicts",
            logical_date=resolved_run_context.logical_date,
        )
        verify_object = _linked_report_object(
            cursor,
            object_kind=VERIFY_REPORT_OBJECT_KIND,
            object_id=verify_report_object_id,
            generated_at=generated_at,
            report_type="verify",
            logical_date=resolved_run_context.logical_date,
        )
        daily_entity_deltas = _daily_entity_deltas(
            cursor,
            source_run_id=source_run_text,
            current_sources=current_sources,
            generated_at=generated_at,
        )
        market_snapshot = load_canonical_market_snapshot(cursor)

    input_freshness = evaluate_input_freshness(
        current_sources=current_sources,
        generated_at=generated_at,
        stale_warn_hours=stale_warn_hours,
        stale_fail_hours=stale_fail_hours,
    )
    snapshot_diff = build_snapshot_diff(
        current_sources=current_sources,
        previous_sources=previous_sources,
    )
    validation_report = summarize_report_object(validation_object, object_store=object_store)
    conflict_report = summarize_report_object(conflict_object, object_store=object_store)
    verify_report = summarize_report_object(verify_object, object_store=object_store)
    zero_delta_analysis = build_zero_delta_analysis(
        input_freshness=input_freshness,
        snapshot_diff=snapshot_diff,
        daily_entity_deltas=daily_entity_deltas,
        validation_report=validation_report,
        conflict_report=conflict_report,
    )
    pipeline_stage_health = build_pipeline_stage_health(
        input_freshness=input_freshness,
        daily_entity_deltas=daily_entity_deltas,
        zero_delta_analysis=zero_delta_analysis,
        validation_report=validation_report,
        conflict_report=conflict_report,
        verify_report=verify_report,
    )
    safety_guards = {
        "listings_closed_by_daily_refresh": 0,
        "securities_deactivated_by_daily_refresh": 0,
        "issuers_deactivated_by_daily_refresh": 0,
        "policy": (
            "Daily refresh does not close listings or deactivate entities solely "
            "because a source row disappears."
        ),
    }
    warnings, failures = evaluate_daily_summary_findings(
        input_freshness=input_freshness,
        zero_delta_analysis=zero_delta_analysis,
        pipeline_stage_health=pipeline_stage_health,
        validation_report=validation_report,
        conflict_report=conflict_report,
        verify_report=verify_report,
    )
    summary = {
        "status": evaluate_daily_summary_status(warnings=warnings, failures=failures),
        "warnings_total": len(warnings),
        "failures_total": len(failures),
        "inputs_seen": input_freshness["inputs_seen"],
        "inputs_missing": input_freshness["inputs_missing"],
        "inputs_unchanged": snapshot_diff["inputs_unchanged"],
        "observations_available": daily_entity_deltas["observations_available"],
        "observations_created": daily_entity_deltas["observations_created"],
        "issuers_created": daily_entity_deltas["issuers_created"],
        "issuers_updated": daily_entity_deltas["issuers_updated"],
        "securities_created": daily_entity_deltas["securities_created"],
        "securities_updated": daily_entity_deltas["securities_updated"],
        "listings_created": daily_entity_deltas["listings_created"],
        "listings_updated": daily_entity_deltas["listings_updated"],
        "validation_status": validation_report["status"],
        "conflict_status": conflict_report["status"],
        "verify_status": verify_report["status"],
        "canonical_issuers_total": market_snapshot["totals"]["issuers_total"],
        "canonical_securities_total": market_snapshot["totals"]["securities_total"],
        "canonical_listings_total": market_snapshot["totals"]["listings_total"],
        "canonical_markets_represented": market_snapshot["markets_represented"],
    }
    return {
        "report_name": DAILY_SUMMARY_REPORT_NAME,
        "generated_at": generated_at.isoformat(),
        "status": summary["status"],
        "healthy": summary["status"] in {"PASS", "WARN"},
        "run_context": resolved_run_context.to_dict(),
        "summary": summary,
        "input_freshness": input_freshness,
        "snapshot_diff": snapshot_diff,
        "pipeline_stage_health": pipeline_stage_health,
        "daily_entity_deltas": daily_entity_deltas,
        "zero_observations_reason": zero_delta_analysis["zero_observations_reason"],
        "zero_evidence_reason": zero_delta_analysis["zero_evidence_reason"],
        "unchanged_sources": zero_delta_analysis["unchanged_sources"],
        "changed_sources": zero_delta_analysis["changed_sources"],
        "canonical_observations_available": zero_delta_analysis[
            "canonical_observations_available"
        ],
        "unreconciled_observations_count": zero_delta_analysis[
            "unreconciled_observations_count"
        ],
        "stage_starvation_detected": zero_delta_analysis["stage_starvation_detected"],
        "safety_guards": safety_guards,
        "market_snapshot": market_snapshot,
        "validation_report": validation_report,
        "conflict_report": conflict_report,
        "verify_report": verify_report,
        "human_review_items": build_human_review_items(
            daily_warnings=warnings,
            daily_failures=failures,
            validation_report=validation_report,
            conflict_report=conflict_report,
            verify_report=verify_report,
        ),
        "warnings": warnings,
        "failures": failures,
    }


def evaluate_input_freshness(
    *,
    current_sources: dict[str, dict[str, Any]],
    generated_at: datetime,
    stale_warn_hours: int = DEFAULT_STALE_WARN_HOURS,
    stale_fail_hours: int = DEFAULT_STALE_FAIL_HOURS,
) -> dict[str, Any]:
    sources: dict[str, dict[str, Any]] = {}
    for source_code in REQUIRED_DAILY_SOURCES:
        row = current_sources.get(source_code)
        if row is None:
            sources[source_code] = {
                "source_code": source_code,
                "present": False,
                "status": "FAIL",
                "age_hours": None,
                "object_key": None,
                "filename": None,
                "downloaded_at": None,
                "size_bytes": None,
                "sha256": None,
                "etag": None,
                "last_modified": None,
            }
            continue
        downloaded_at = _parse_datetime(
            row.get("downloaded_at") or row.get("created_at")
        )
        age_hours = _age_hours(generated_at, downloaded_at)
        status = "PASS"
        if age_hours is not None and age_hours >= stale_fail_hours:
            status = "FAIL"
        elif age_hours is not None and age_hours >= stale_warn_hours:
            status = "WARN"
        sources[source_code] = {
            "source_code": source_code,
            "present": True,
            "status": status,
            "age_hours": age_hours,
            "object_id": row.get("object_id"),
            "object_key": row.get("object_key"),
            "filename": row.get("filename"),
            "downloaded_at": downloaded_at.isoformat() if downloaded_at else None,
            "size_bytes": row.get("size_bytes"),
            "sha256": row.get("sha256"),
            "etag": row.get("etag"),
            "last_modified": row.get("last_modified"),
        }
    return {
        "required_sources": list(REQUIRED_DAILY_SOURCES),
        "stale_warn_hours": stale_warn_hours,
        "stale_fail_hours": stale_fail_hours,
        "inputs_seen": sum(1 for source in sources.values() if source["present"]),
        "inputs_missing": sum(1 for source in sources.values() if not source["present"]),
        "sources": sources,
    }


def build_snapshot_diff(
    *,
    current_sources: dict[str, dict[str, Any]],
    previous_sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    sources: dict[str, dict[str, Any]] = {}
    for source_code in REQUIRED_DAILY_SOURCES:
        current = current_sources.get(source_code)
        previous = previous_sources.get(source_code)
        current_sha = current.get("sha256") if current else None
        previous_sha = previous.get("sha256") if previous else None
        current_size = current.get("size_bytes") if current else None
        previous_size = previous.get("size_bytes") if previous else None
        changed = None
        if current_sha is not None and previous_sha is not None:
            changed = current_sha != previous_sha
        sources[source_code] = {
            "source_code": source_code,
            "current_sha256": current_sha,
            "previous_sha256": previous_sha,
            "changed": changed,
            "unchanged": changed is False,
            "current_size_bytes": current_size,
            "previous_size_bytes": previous_size,
            "size_delta_bytes": _size_delta(current_size, previous_size),
            "current_downloaded_at": current.get("downloaded_at") if current else None,
            "previous_downloaded_at": previous.get("downloaded_at") if previous else None,
            "current_object_key": current.get("object_key") if current else None,
            "previous_object_key": previous.get("object_key") if previous else None,
        }
    return {
        "inputs_unchanged": sum(1 for source in sources.values() if source["unchanged"]),
        "sources": sources,
    }


def summarize_report_object(
    stored_object: dict[str, Any] | None,
    *,
    object_store: ObjectStore | None,
) -> dict[str, Any]:
    if stored_object is None:
        return {
            "present": False,
            "status": "UNKNOWN",
            "healthy": None,
            "path": None,
            "object_id": None,
            "warnings_total": None,
            "failures_total": None,
            "conflicts_total": None,
        }
    payload = _load_report_payload(stored_object, object_store=object_store)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    status = _normalize_report_status(summary.get("status"))
    return {
        "present": True,
        "status": status,
        "healthy": summary.get("healthy", status in {"PASS", "WARN"}),
        "path": f"{stored_object['object_key']}/{stored_object['filename']}",
        "object_id": stored_object["object_id"],
        "warnings_total": summary.get("warnings_total"),
        "failures_total": summary.get("failures_total"),
        "conflicts_total": summary.get("conflicts_total"),
        "generated_at": stored_object.get("report_generated_at") or stored_object.get("created_at"),
        "review_items": _report_review_items(payload),
    }


def build_human_review_items(
    *,
    daily_warnings: list[dict[str, Any]],
    daily_failures: list[dict[str, Any]],
    validation_report: dict[str, Any],
    conflict_report: dict[str, Any],
    verify_report: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for severity, findings in (("FAIL", daily_failures), ("WARN", daily_warnings)):
        for finding in findings:
            if str(finding.get("code", "")).endswith("_report_warn"):
                continue
            items.append(
                {
                    "source_report": "daily_summary",
                    "severity": severity,
                    "code": finding.get("code"),
                    "count": _finding_count(finding),
                    "message": finding.get("message") or _humanize_code(finding.get("code")),
                    "path": finding.get("path"),
                }
            )
    for report_name, report in (
        ("verify", verify_report),
        ("validation", validation_report),
        ("conflicts", conflict_report),
    ):
        for item in report.get("review_items", []):
            items.append({**item, "source_report": report_name, "path": report.get("path")})
    return items


def build_pipeline_stage_health(
    *,
    input_freshness: dict[str, Any],
    daily_entity_deltas: dict[str, Any],
    zero_delta_analysis: dict[str, Any],
    validation_report: dict[str, Any],
    conflict_report: dict[str, Any],
    verify_report: dict[str, Any],
) -> dict[str, Any]:
    observations_created = daily_entity_deltas["observations_created"]
    issuer_evidence = daily_entity_deltas["issuer_evidence_inserted"]
    security_evidence = daily_entity_deltas["security_evidence_inserted"]
    listing_evidence = daily_entity_deltas["listing_evidence_inserted"]
    zero_evidence_reason = zero_delta_analysis["zero_evidence_reason"]
    return {
        "scrape": _stage("PASS" if input_freshness["inputs_missing"] == 0 else "FAIL"),
        "verify": _stage(
            verify_report["status"] if verify_report["present"] else "UNKNOWN",
            None if verify_report["present"] else "No durable verify report is currently linked.",
        ),
        "observations": _stage(
            _zero_count_stage_status(
                count=observations_created,
                safe_zero_reasons={
                    "unchanged_sources_no_new_observations",
                    "canonical_observations_available",
                },
                reason=zero_delta_analysis["zero_observations_reason"],
            )
        ),
        "issuers": _stage(
            _zero_count_stage_status(
                count=issuer_evidence,
                safe_zero_reasons={"all_eligible_observations_reconciled"},
                reason=zero_evidence_reason["issuers"],
            )
        ),
        "securities": _stage(
            _zero_count_stage_status(
                count=security_evidence,
                safe_zero_reasons={"all_eligible_observations_reconciled"},
                reason=zero_evidence_reason["securities"],
            )
        ),
        "listings": _stage(
            _zero_count_stage_status(
                count=listing_evidence,
                safe_zero_reasons={"all_eligible_observations_reconciled"},
                reason=zero_evidence_reason["listings"],
            )
        ),
        "validation": _stage(validation_report["status"] if validation_report["present"] else "UNKNOWN"),
        "conflicts": _stage(conflict_report["status"] if conflict_report["present"] else "UNKNOWN"),
    }


def build_zero_delta_analysis(
    *,
    input_freshness: dict[str, Any],
    snapshot_diff: dict[str, Any],
    daily_entity_deltas: dict[str, Any],
    validation_report: dict[str, Any],
    conflict_report: dict[str, Any],
) -> dict[str, Any]:
    changed_sources = [
        source_code
        for source_code, source in snapshot_diff["sources"].items()
        if source["changed"] is True
    ]
    unchanged_sources = [
        source_code
        for source_code, source in snapshot_diff["sources"].items()
        if source["unchanged"] is True
    ]
    observations_created = int(daily_entity_deltas["observations_created"] or 0)
    observations_available = int(daily_entity_deltas["observations_available"] or 0)
    canonical_observations_available = observations_available > 0
    unreconciled_by_stage = {
        "issuers": int(daily_entity_deltas["unreconciled_issuer_observations"] or 0),
        "securities": int(daily_entity_deltas["unreconciled_security_observations"] or 0),
        "listings": int(daily_entity_deltas["unreconciled_listing_observations"] or 0),
    }
    unreconciled_observations_count = sum(unreconciled_by_stage.values())
    all_inputs_unchanged = len(unchanged_sources) == len(REQUIRED_DAILY_SOURCES)
    reports_usable = (
        validation_report["status"] in {"PASS", "WARN"}
        and conflict_report["status"] in {"PASS", "WARN"}
    )
    zero_observations_reason = _zero_observations_reason(
        observations_created=observations_created,
        canonical_observations_available=canonical_observations_available,
        input_freshness=input_freshness,
        changed_sources=changed_sources,
        all_inputs_unchanged=all_inputs_unchanged,
        reports_usable=reports_usable,
    )
    zero_evidence_reason = {
        "issuers": _zero_evidence_reason(
            count=daily_entity_deltas["issuer_evidence_inserted"],
            unreconciled_count=unreconciled_by_stage["issuers"],
            canonical_observations_available=canonical_observations_available,
        ),
        "securities": _zero_evidence_reason(
            count=daily_entity_deltas["security_evidence_inserted"],
            unreconciled_count=unreconciled_by_stage["securities"],
            canonical_observations_available=canonical_observations_available,
        ),
        "listings": _zero_evidence_reason(
            count=daily_entity_deltas["listing_evidence_inserted"],
            unreconciled_count=unreconciled_by_stage["listings"],
            canonical_observations_available=canonical_observations_available,
        ),
    }
    stage_starvation_detected = (
        zero_observations_reason
        in {
            "sources_changed_but_no_observations",
            "no_canonical_observations_for_unchanged_sources",
            "required_source_missing",
        }
        or any(reason == "unreconciled_observations_exist" for reason in zero_evidence_reason.values())
    )
    return {
        "zero_observations_reason": zero_observations_reason,
        "zero_evidence_reason": zero_evidence_reason,
        "unchanged_sources": unchanged_sources,
        "changed_sources": changed_sources,
        "canonical_observations_available": canonical_observations_available,
        "unreconciled_observations_count": unreconciled_observations_count,
        "unreconciled_observations_by_stage": unreconciled_by_stage,
        "stage_starvation_detected": stage_starvation_detected,
    }


def evaluate_daily_summary_findings(
    *,
    input_freshness: dict[str, Any],
    zero_delta_analysis: dict[str, Any],
    pipeline_stage_health: dict[str, Any],
    validation_report: dict[str, Any],
    conflict_report: dict[str, Any],
    verify_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for source_code, source in input_freshness["sources"].items():
        if not source["present"]:
            failures.append(
                {
                    "code": "required_source_missing",
                    "source_code": source_code,
                    "message": f"Required SEC source {source_code} was not found for this run.",
                }
            )
        elif source["status"] == "FAIL":
            failures.append(
                {
                    "code": "required_source_too_stale",
                    "source_code": source_code,
                    "age_hours": source["age_hours"],
                    "message": (
                        f"Required SEC source {source_code} is older than the hard-fail "
                        "freshness threshold."
                    ),
                }
            )
        elif source["status"] == "WARN":
            warnings.append(
                {
                    "code": "required_source_stale",
                    "source_code": source_code,
                    "age_hours": source["age_hours"],
                    "message": (
                        f"Required SEC source {source_code} is older than the warning "
                        "freshness threshold but not old enough to fail the run."
                    ),
                }
            )

    zero_observations_reason = zero_delta_analysis["zero_observations_reason"]
    if zero_observations_reason == "sources_changed_but_no_observations":
        warnings.append(
            {
                "code": "changed_sources_zero_observations",
                "changed_sources": zero_delta_analysis["changed_sources"],
                "message": (
                    "One or more required SEC source files changed, but no canonical "
                    "observations were available for the current source identity."
                ),
            }
        )
    elif zero_observations_reason == "no_canonical_observations_for_unchanged_sources":
        warnings.append(
            {
                "code": "unchanged_sources_without_canonical_observations",
                "message": (
                    "Required SEC source files were unchanged, but no canonical observations "
                    "were available to prove the run was safely already reconciled."
                ),
            }
        )

    for stage_name, reason in zero_delta_analysis["zero_evidence_reason"].items():
        if reason == "unreconciled_observations_exist":
            warnings.append(
                {
                    "code": "zero_evidence_with_unreconciled_observations",
                    "stage": stage_name,
                    "unreconciled_observations": zero_delta_analysis[
                        "unreconciled_observations_by_stage"
                    ][stage_name],
                    "message": (
                        f"No {stage_name} evidence was available for the current source "
                        "identity while unreconciled eligible observations remain."
                    ),
                }
            )

    for report_name, linked_report in (
        ("verify", verify_report),
        ("validation", validation_report),
        ("conflict", conflict_report),
    ):
        status = linked_report["status"]
        if not linked_report["present"]:
            finding = {
                "code": f"{report_name}_report_missing",
                "message": f"The daily summary could not find a {report_name} report artifact.",
            }
            if report_name == "verify":
                warnings.append(finding)
                continue
            failures.append(
                {
                    **finding,
                }
            )
        elif status == "FAIL":
            failures.append(
                {
                    "code": f"{report_name}_report_failed",
                    "path": linked_report["path"],
                    "failures_total": linked_report["failures_total"],
                    "message": f"The linked {report_name} report has FAIL status.",
                }
            )
        elif status == "WARN":
            warnings.append(
                {
                    "code": f"{report_name}_report_warn",
                    "path": linked_report["path"],
                    "warnings_total": linked_report["warnings_total"],
                    "failures_total": linked_report["failures_total"],
                    "conflicts_total": linked_report["conflicts_total"],
                    "message": (
                        f"The linked {report_name} report completed with WARN status; "
                        "review the linked report for details."
                    ),
                }
            )

    for stage_name, stage in pipeline_stage_health.items():
        if stage["status"] == "UNKNOWN":
            warnings.append(
                {
                    "code": "stage_health_unknown",
                    "stage": stage_name,
                    "message": stage.get(
                        "note",
                        f"Stage health for {stage_name} could not be inferred from current artifacts.",
                    ),
                }
            )
        elif stage["status"] == "FAIL":
            failures.append(
                {
                    "code": "stage_health_failed",
                    "stage": stage_name,
                    "message": f"Stage health for {stage_name} is FAIL.",
                }
            )

    return warnings, failures


def evaluate_daily_summary_status(
    *,
    warnings: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> str:
    if failures:
        return "FAIL"
    if warnings:
        return "WARN"
    return "PASS"


def daily_summary_report_to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def write_daily_summary_report_to_console(report: dict[str, Any], *, json_output: bool = False) -> None:
    if json_output:
        print(daily_summary_report_to_json(report), end="")
        return
    summary = report["summary"]
    print(
        "stonks_securities_daily_summary "
        f"status={summary['status']} "
        f"inputs_seen={summary['inputs_seen']} "
        f"inputs_missing={summary['inputs_missing']} "
        f"inputs_unchanged={summary['inputs_unchanged']} "
        f"validation_status={summary['validation_status']} "
        f"conflict_status={summary['conflict_status']} "
        f"warnings={summary['warnings_total']} "
        f"failures={summary['failures_total']}"
    )


def write_daily_summary_report_to_file(report: dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(daily_summary_report_to_json(report), encoding="utf-8")
    return output_path


def default_daily_summary_report_path(
    *,
    temp_dir: str | Path | None = None,
    generated_at: datetime | None = None,
    logical_date: Any = None,
) -> Path:
    generated_at = generated_at or datetime.now(UTC)
    root = Path(temp_dir or os.environ.get("EMPIRE_TEMP_DIR", "/tmp"))
    filename = f"stonks_securities_daily_summary_{generated_at:%Y%m%dT%H%M%SZ}.json"
    return run_report_path(
        root=root,
        report_type="summary",
        filename=filename,
        logical_date=logical_date,
        generated_at=generated_at,
    )


def write_daily_summary_report_to_object_store(
    *,
    report: dict[str, Any],
    object_store: ObjectStore,
    storage_root: str = DEFAULT_STORAGE_ROOT,
    storage_key: str | None = None,
    generated_at: datetime | None = None,
    logical_date: Any = None,
    storage_run_context: CoreRunContext | None = None,
):
    generated_at = generated_at or datetime.now(UTC)
    resolved_storage_key = (storage_key or default_storage_key()).strip("/")
    object_key = run_report_object_key(
        storage_key=resolved_storage_key,
        report_type="summary",
        logical_date=logical_date or report.get("run_context", {}).get("logical_date"),
        generated_at=generated_at,
    )
    filename = f"stonks_securities_daily_summary_{generated_at:%Y%m%dT%H%M%SZ}.json"
    return object_store.put_bytes(
        run_context=storage_run_context,
        object_scope="run" if storage_run_context is not None else "manual",
        domain="stonks",
        logical_name=DAILY_SUMMARY_REPORT_LOGICAL_NAME,
        storage_root=storage_root,
        object_key=object_key,
        filename=filename,
        data=daily_summary_report_to_json(report).encode("utf-8"),
        content_type="application/json",
        object_kind=DAILY_SUMMARY_REPORT_OBJECT_KIND,
        metadata={"report_name": DAILY_SUMMARY_REPORT_NAME, "generated_at": report["generated_at"]},
    )


def write_daily_summary_pdf_to_object_store(
    *,
    report: dict[str, Any],
    object_store: ObjectStore,
    storage_root: str = DEFAULT_STORAGE_ROOT,
    storage_key: str | None = None,
    generated_at: datetime | None = None,
    logical_date: Any = None,
    storage_run_context: CoreRunContext | None = None,
    output_dir: str | Path | None = None,
):
    generated_at = generated_at or datetime.now(UTC)
    resolved_storage_key = (storage_key or default_storage_key()).strip("/")
    object_key = run_report_object_key(
        storage_key=resolved_storage_key,
        report_type="summary",
        logical_date=logical_date or report.get("run_context", {}).get("logical_date"),
        generated_at=generated_at,
    )
    filename = f"stonks_securities_daily_summary_{generated_at:%Y%m%dT%H%M%SZ}.pdf"
    render_root = Path(output_dir or os.environ.get("EMPIRE_TEMP_DIR", "/tmp"))
    render_dir = run_report_path(
        root=render_root,
        report_type="summary",
        filename="pdf-render",
        logical_date=logical_date or report.get("run_context", {}).get("logical_date"),
        generated_at=generated_at,
    ).parent
    result = render_daily_refresh_summary_pdf(
        report=report,
        output_dir=render_dir,
        generated_at=generated_at,
        filename=filename,
    )
    expires_at = generated_at + timedelta(days=DAILY_SUMMARY_PDF_RETENTION_DAYS)
    return object_store.put_file(
        run_context=storage_run_context,
        object_scope="run" if storage_run_context is not None else "manual",
        domain="stonks",
        logical_name=DAILY_SUMMARY_PDF_LOGICAL_NAME,
        storage_root=storage_root,
        object_key=object_key,
        filename=filename,
        source_path=result.primary_artifact.path,
        move=False,
        content_type="application/pdf",
        object_kind=DAILY_SUMMARY_PDF_OBJECT_KIND,
        expires_at=expires_at,
        metadata={
            "report_name": DAILY_SUMMARY_REPORT_NAME,
            "report_id": result.report.report_id,
            "generated_at": report["generated_at"],
            "retention_days": DAILY_SUMMARY_PDF_RETENTION_DAYS,
        },
    )


def _current_source_files(cursor: Any, *, source_run_id: str | None) -> dict[str, dict[str, Any]]:
    if source_run_id:
        rows = _fetchall(
            cursor,
            "daily_summary_current_source_files",
            """
            SELECT
              lower(so.logical_name) AS source_code,
              so.object_id::text AS object_id,
              so.object_key,
              so.filename,
              so.size_bytes,
              so.checksum_sha256 AS sha256,
              so.metadata ->> 'etag' AS etag,
              so.metadata ->> 'last_modified' AS last_modified,
              COALESCE(so.metadata ->> 'downloaded_at', so.created_at::text) AS downloaded_at,
              so.created_at
            FROM core.stored_object so
            WHERE so.run_id = %s
              AND so.object_kind = 'sec_source_file'
              AND so.deleted_at IS NULL
              AND lower(so.logical_name) = ANY(%s)
            ORDER BY lower(so.logical_name), so.created_at DESC
            """,
            (source_run_id, list(REQUIRED_DAILY_SOURCES)),
        )
    else:
        rows = _fetchall(
            cursor,
            "daily_summary_current_source_files",
            """
            SELECT DISTINCT ON (lower(so.logical_name))
              lower(so.logical_name) AS source_code,
              so.object_id::text AS object_id,
              so.object_key,
              so.filename,
              so.size_bytes,
              so.checksum_sha256 AS sha256,
              so.metadata ->> 'etag' AS etag,
              so.metadata ->> 'last_modified' AS last_modified,
              COALESCE(so.metadata ->> 'downloaded_at', so.created_at::text) AS downloaded_at,
              so.created_at
            FROM core.stored_object so
            WHERE so.object_kind = 'sec_source_file'
              AND so.deleted_at IS NULL
              AND lower(so.logical_name) = ANY(%s)
            ORDER BY lower(so.logical_name), so.created_at DESC
            """,
            (list(REQUIRED_DAILY_SOURCES),),
        )
    return {row["source_code"]: row for row in rows}


def _previous_source_files(
    cursor: Any,
    *,
    current_sources: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not current_sources:
        return {}
    rows = _fetchall(
        cursor,
        "daily_summary_previous_source_files",
        """
        SELECT DISTINCT ON (lower(so.logical_name))
          lower(so.logical_name) AS source_code,
          so.object_id::text AS object_id,
          so.object_key,
          so.filename,
          so.size_bytes,
          so.checksum_sha256 AS sha256,
          so.metadata ->> 'etag' AS etag,
          so.metadata ->> 'last_modified' AS last_modified,
          COALESCE(so.metadata ->> 'downloaded_at', so.created_at::text) AS downloaded_at,
          so.created_at
        FROM core.stored_object so
        WHERE so.object_kind = 'sec_source_file'
          AND so.deleted_at IS NULL
          AND lower(so.logical_name) = ANY(%s)
          AND so.object_id <> ALL(%s::uuid[])
        ORDER BY lower(so.logical_name), so.created_at DESC
        """,
        (
            list(REQUIRED_DAILY_SOURCES),
            [row["object_id"] for row in current_sources.values()],
        ),
    )
    return {row["source_code"]: row for row in rows}


def _latest_report_object(
    cursor: Any,
    *,
    object_kind: str,
    generated_at: datetime,
    report_type: str,
    logical_date: Any = None,
) -> dict[str, Any] | None:
    new_key = run_report_object_key(
        storage_key=default_storage_key(),
        report_type=report_type,
        logical_date=logical_date,
        generated_at=generated_at,
    )
    rows = _fetchall(
        cursor,
        f"daily_summary_latest_{object_kind}",
        """
        SELECT
          so.object_id::text AS object_id,
          so.object_key,
          so.filename,
          so.object_kind,
          so.metadata ->> 'generated_at' AS report_generated_at,
          so.created_at
        FROM core.stored_object so
        WHERE so.object_kind = %s
          AND so.deleted_at IS NULL
          AND so.object_key = %s
        ORDER BY so.created_at DESC
        LIMIT 1
        """,
        (object_kind, new_key),
    )
    if rows:
        return rows[0]
    old_day_key = f"stonks/securities/%/{generated_at:%Y}/{generated_at:%m}/{generated_at:%d}"
    rows = _fetchall(
        cursor,
        f"daily_summary_latest_{object_kind}_legacy",
        """
        SELECT
          so.object_id::text AS object_id,
          so.object_key,
          so.filename,
          so.object_kind,
          so.metadata ->> 'generated_at' AS report_generated_at,
          so.created_at
        FROM core.stored_object so
        WHERE so.object_kind = %s
          AND so.deleted_at IS NULL
          AND so.object_key LIKE %s
        ORDER BY so.created_at DESC
        LIMIT 1
        """,
        (object_kind, old_day_key),
    )
    return rows[0] if rows else None


def _linked_report_object(
    cursor: Any,
    *,
    object_kind: str,
    object_id: str | UUID | None,
    generated_at: datetime,
    report_type: str,
    logical_date: Any = None,
) -> dict[str, Any] | None:
    if object_id is None:
        return _latest_report_object(
            cursor,
            object_kind=object_kind,
            generated_at=generated_at,
            report_type=report_type,
            logical_date=logical_date,
        )
    rows = _fetchall(
        cursor,
        f"daily_summary_linked_{object_kind}",
        """
        SELECT
          so.object_id::text AS object_id,
          so.object_key,
          so.filename,
          so.object_kind,
          so.metadata ->> 'generated_at' AS report_generated_at,
          so.created_at
        FROM core.stored_object so
        WHERE so.object_id = %s
          AND so.object_kind = %s
          AND so.deleted_at IS NULL
        LIMIT 1
        """,
        (str(object_id), object_kind),
    )
    return rows[0] if rows else None


def _daily_entity_deltas(
    cursor: Any,
    *,
    source_run_id: str | None,
    current_sources: dict[str, dict[str, Any]],
    generated_at: datetime,
) -> dict[str, Any]:
    run_start, run_end = _run_window(current_sources=current_sources, generated_at=generated_at)
    obs_from, obs_params = _observation_scope_sql(source_run_id)
    current_object_ids = [row["object_id"] for row in current_sources.values() if row.get("object_id")]
    return {
        "observations_available": _scalar(
            cursor,
            "daily_summary_observations_available",
            f"SELECT COUNT(*) FROM {obs_from}",
            obs_params,
        ),
        "observations_created": _scalar(
            cursor,
            "daily_summary_observations_created",
            """
            SELECT COUNT(*)
            FROM stonks.provider_observation po
            WHERE po.object_id = ANY(%s::uuid[])
              AND po.created_at >= %s
              AND po.created_at < %s
            """,
            (current_object_ids, run_start, run_end),
        ),
        "issuer_evidence_inserted": _evidence_count(
            cursor, obs_from, obs_params, "issuer_id", run_start, run_end
        ),
        "security_evidence_inserted": _evidence_count(
            cursor, obs_from, obs_params, "security_id", run_start, run_end
        ),
        "listing_evidence_inserted": _evidence_count(
            cursor, obs_from, obs_params, "listing_id", run_start, run_end
        ),
        "unreconciled_issuer_observations": _unreconciled_evidence_count(
            cursor,
            obs_from,
            obs_params,
            "issuer_id",
            """
            COALESCE(
                NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''),
                NULLIF(TRIM(po.summary_json ->> 'cik'), '')
            ) IS NOT NULL
            """,
        ),
        "unreconciled_security_observations": _unreconciled_evidence_count(
            cursor,
            obs_from,
            obs_params,
            "security_id",
            """
            COALESCE(
                NULLIF(TRIM(po.summary_json ->> 'cik_padded'), ''),
                NULLIF(TRIM(po.summary_json ->> 'cik'), '')
            ) IS NOT NULL
              AND COALESCE(
                NULLIF(TRIM(po.summary_json ->> 'ticker_norm'), ''),
                NULLIF(TRIM(po.summary_json ->> 'ticker'), '')
              ) IS NOT NULL
            """,
        ),
        "unreconciled_listing_observations": _unreconciled_evidence_count(
            cursor,
            obs_from,
            obs_params,
            "listing_id",
            """
            po.provider_code = 'SEC_COMPANY_TICKERS_EXCHANGE'
              AND NULLIF(TRIM(po.summary_json ->> 'exchange'), '') IS NOT NULL
              AND EXISTS (
                SELECT 1
                FROM stonks.exchange_alias ea
                WHERE ea.provider_code = 'SEC'
                  AND ea.is_active = TRUE
                  AND lower(ea.raw_name) = lower(po.summary_json ->> 'exchange')
              )
            """,
        ),
        "issuers_created": _created_count(cursor, "issuer", run_start, run_end),
        "issuers_updated": _updated_count(cursor, "issuer", run_start, run_end),
        "securities_created": _created_count(cursor, "security", run_start, run_end),
        "securities_updated": _updated_count(cursor, "security", run_start, run_end),
        "listings_created": _created_count(cursor, "listing", run_start, run_end),
        "listings_updated": _updated_count(cursor, "listing", run_start, run_end),
    }


def _run_window(
    *,
    current_sources: dict[str, dict[str, Any]],
    generated_at: datetime,
) -> tuple[datetime, datetime]:
    created_values = [
        parsed
        for parsed in (_parse_datetime(row.get("created_at")) for row in current_sources.values())
        if parsed is not None
    ]
    run_end = generated_at.astimezone(UTC)
    if not created_values:
        return run_end, run_end
    run_start = min(value.astimezone(UTC) for value in created_values)
    return run_start, run_end


def _evidence_count(
    cursor: Any,
    obs_from: str,
    obs_params: tuple[Any, ...],
    column: str,
    run_start: datetime,
    run_end: datetime,
) -> int:
    return _scalar(
        cursor,
        f"daily_summary_{column}_evidence_inserted",
        f"""
        SELECT COUNT(*)
        FROM stonks.provider_evidence pe
        JOIN {obs_from}
          ON po.provider_observation_id = pe.provider_observation_id
        WHERE pe.{column} IS NOT NULL
          AND pe.created_at >= %s
          AND pe.created_at < %s
        """,
        (*obs_params, run_start, run_end),
    )


def _unreconciled_evidence_count(
    cursor: Any,
    obs_from: str,
    obs_params: tuple[Any, ...],
    column: str,
    eligibility_sql: str,
) -> int:
    metric_name = {
        "issuer_id": "daily_summary_unreconciled_issuer_observations",
        "security_id": "daily_summary_unreconciled_security_observations",
        "listing_id": "daily_summary_unreconciled_listing_observations",
    }[column]
    return _scalar(
        cursor,
        metric_name,
        f"""
        SELECT COUNT(*)
        FROM {obs_from}
        WHERE {eligibility_sql}
          AND NOT EXISTS (
            SELECT 1
            FROM stonks.provider_evidence pe
            WHERE pe.provider_observation_id = po.provider_observation_id
              AND pe.{column} IS NOT NULL
          )
        """,
        obs_params,
    )


def _created_count(cursor: Any, table_name: str, day_start: datetime, day_end: datetime) -> int:
    return _scalar(
        cursor,
        f"daily_summary_{table_name}_created",
        f"""
        SELECT COUNT(*)
        FROM stonks.{table_name}
        WHERE created_at >= %s AND created_at < %s
        """,
        (day_start, day_end),
    )


def _updated_count(cursor: Any, table_name: str, day_start: datetime, day_end: datetime) -> int:
    return _scalar(
        cursor,
        f"daily_summary_{table_name}_updated",
        f"""
        SELECT COUNT(*)
        FROM stonks.{table_name}
        WHERE updated_at >= %s
          AND updated_at < %s
          AND updated_at > created_at
        """,
        (day_start, day_end),
    )


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


def _report_review_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for severity, key in (("FAIL", "failures"), ("WARN", "warnings")):
        for finding in report.get(key, [])[:25]:
            items.append(
                {
                    "severity": severity,
                    "code": finding.get("code"),
                    "count": _finding_count(finding),
                    "message": _review_message(finding),
                    "recommended_action": _recommended_action(finding),
                }
            )
    if items:
        return items

    conflicts_by_category = report.get("conflicts_by_category")
    if isinstance(conflicts_by_category, dict):
        for category, counts in list(conflicts_by_category.items())[:25]:
            if not isinstance(counts, dict):
                continue
            total = int(counts.get("total") or 0)
            if total == 0:
                continue
            severity = "FAIL" if int(counts.get("failures") or 0) else "WARN"
            items.append(
                {
                    "severity": severity,
                    "code": category,
                    "count": total,
                    "message": f"{_humanize_code(category)} has {total} open item(s).",
                    "recommended_action": "Review the conflict report category details.",
                }
            )
    return items


def _review_message(finding: dict[str, Any]) -> str:
    if finding.get("message"):
        return str(finding["message"])
    code = finding.get("code")
    count = _finding_count(finding)
    if count is not None:
        return f"{_humanize_code(code)} count is {count}."
    return _humanize_code(code)


def _recommended_action(finding: dict[str, Any]) -> str | None:
    conflict = finding.get("conflict")
    if isinstance(conflict, dict) and conflict.get("recommended_action"):
        return str(conflict["recommended_action"])
    return None


def _finding_count(finding: dict[str, Any]) -> int | None:
    for key in (
        "count",
        "conflicts_total",
        "failures_total",
        "warnings_total",
        "unreconciled_observations",
    ):
        value = finding.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _humanize_code(value: Any) -> str:
    text = str(value or "review_item").replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def _load_report_payload(
    stored_object: dict[str, Any],
    *,
    object_store: ObjectStore | None,
) -> dict[str, Any]:
    if object_store is None:
        return {}
    try:
        data = object_store.get_bytes(UUID(str(stored_object["object_id"])))
        report = json.loads(data.decode("utf-8"))
    except Exception:
        return {}
    return report if isinstance(report, dict) else {}


def _normalize_report_status(value: Any) -> str:
    if value in {"PASS", "WARN", "FAIL"}:
        return str(value)
    return "UNKNOWN"


def _stage(status: str, note: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": _normalize_report_status(status)}
    if note:
        result["note"] = note
    return result


def _zero_count_stage_status(
    *,
    count: Any,
    safe_zero_reasons: set[str],
    reason: str,
) -> str:
    if count is None:
        return "UNKNOWN"
    if int(count) > 0:
        return "PASS"
    if reason in safe_zero_reasons:
        return "PASS"
    if reason in {
        "required_source_missing",
        "validation_or_conflict_failed",
    }:
        return "FAIL"
    if reason in {
        "sources_changed_but_no_observations",
        "no_canonical_observations_for_unchanged_sources",
        "unreconciled_observations_exist",
        "no_canonical_observations_available",
        "insufficient_context",
    }:
        return "WARN"
    return "UNKNOWN"


def _zero_observations_reason(
    *,
    observations_created: int,
    canonical_observations_available: bool,
    input_freshness: dict[str, Any],
    changed_sources: list[str],
    all_inputs_unchanged: bool,
    reports_usable: bool,
) -> str:
    if observations_created > 0:
        return "canonical_observations_available"
    if input_freshness["inputs_missing"] > 0:
        return "required_source_missing"
    if changed_sources:
        return "sources_changed_but_no_observations"
    if all_inputs_unchanged and reports_usable and canonical_observations_available:
        return "unchanged_sources_no_new_observations"
    if all_inputs_unchanged and reports_usable:
        return "no_canonical_observations_for_unchanged_sources"
    if not reports_usable:
        return "validation_or_conflict_failed"
    return "insufficient_context"


def _zero_evidence_reason(
    *,
    count: Any,
    unreconciled_count: int,
    canonical_observations_available: bool,
) -> str:
    if count is None:
        return "insufficient_context"
    if int(count) > 0:
        return "evidence_available"
    if unreconciled_count > 0:
        return "unreconciled_observations_exist"
    if canonical_observations_available:
        return "all_eligible_observations_reconciled"
    return "no_canonical_observations_available"


def _size_delta(current_size: Any, previous_size: Any) -> int | None:
    if current_size is None or previous_size is None:
        return None
    return int(current_size) - int(previous_size)


def _age_hours(generated_at: datetime, downloaded_at: datetime | None) -> float | None:
    if downloaded_at is None:
        return None
    generated = generated_at if generated_at.tzinfo else generated_at.replace(tzinfo=UTC)
    downloaded = downloaded_at if downloaded_at.tzinfo else downloaded_at.replace(tzinfo=UTC)
    return round((generated - downloaded).total_seconds() / 3600, 2)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


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
