"""Daily refresh summary report generation for the SEC security-master pipeline."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from empire_core import ObjectStore
from empire_core.db.postgres import row_to_dict

from empire_stonks_securities.acquisition import DEFAULT_STORAGE_ROOT, default_storage_key
from empire_stonks_securities.conflicts import CONFLICT_REPORT_OBJECT_KIND
from empire_stonks_securities.validation import REPORT_OBJECT_KIND as VALIDATION_REPORT_OBJECT_KIND


DAILY_SUMMARY_REPORT_NAME = "stonks_securities_daily_summary"
DAILY_SUMMARY_REPORT_OBJECT_KIND = "stonks_securities_daily_summary_report"
DAILY_SUMMARY_REPORT_LOGICAL_NAME = "stonks_securities_daily_summary"
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
        )
        conflict_object = _linked_report_object(
            cursor,
            object_kind=CONFLICT_REPORT_OBJECT_KIND,
            object_id=conflict_report_object_id,
            generated_at=generated_at,
        )
        daily_entity_deltas = _daily_entity_deltas(
            cursor,
            source_run_id=source_run_text,
            generated_at=generated_at,
        )

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
    pipeline_stage_health = build_pipeline_stage_health(
        input_freshness=input_freshness,
        daily_entity_deltas=daily_entity_deltas,
        validation_report=validation_report,
        conflict_report=conflict_report,
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
        pipeline_stage_health=pipeline_stage_health,
        validation_report=validation_report,
        conflict_report=conflict_report,
    )
    summary = {
        "status": evaluate_daily_summary_status(warnings=warnings, failures=failures),
        "warnings_total": len(warnings),
        "failures_total": len(failures),
        "inputs_seen": input_freshness["inputs_seen"],
        "inputs_missing": input_freshness["inputs_missing"],
        "inputs_unchanged": snapshot_diff["inputs_unchanged"],
        "observations_created": daily_entity_deltas["observations_created"],
        "issuers_created": daily_entity_deltas["issuers_created"],
        "issuers_updated": daily_entity_deltas["issuers_updated"],
        "securities_created": daily_entity_deltas["securities_created"],
        "securities_updated": daily_entity_deltas["securities_updated"],
        "listings_created": daily_entity_deltas["listings_created"],
        "listings_updated": daily_entity_deltas["listings_updated"],
        "validation_status": validation_report["status"],
        "conflict_status": conflict_report["status"],
    }
    return {
        "report_name": DAILY_SUMMARY_REPORT_NAME,
        "generated_at": generated_at.isoformat(),
        "run_context": resolved_run_context.to_dict(),
        "summary": summary,
        "input_freshness": input_freshness,
        "snapshot_diff": snapshot_diff,
        "pipeline_stage_health": pipeline_stage_health,
        "daily_entity_deltas": daily_entity_deltas,
        "safety_guards": safety_guards,
        "validation_report": validation_report,
        "conflict_report": conflict_report,
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
            "path": None,
            "object_id": None,
            "warnings_total": None,
            "failures_total": None,
            "conflicts_total": None,
        }
    summary = _load_report_summary(stored_object, object_store=object_store)
    return {
        "present": True,
        "status": _normalize_report_status(summary.get("status")),
        "path": f"{stored_object['object_key']}/{stored_object['filename']}",
        "object_id": stored_object["object_id"],
        "warnings_total": summary.get("warnings_total"),
        "failures_total": summary.get("failures_total"),
        "conflicts_total": summary.get("conflicts_total"),
        "generated_at": stored_object.get("report_generated_at") or stored_object.get("created_at"),
    }


def build_pipeline_stage_health(
    *,
    input_freshness: dict[str, Any],
    daily_entity_deltas: dict[str, Any],
    validation_report: dict[str, Any],
    conflict_report: dict[str, Any],
) -> dict[str, Any]:
    observations_created = daily_entity_deltas["observations_created"]
    issuer_evidence = daily_entity_deltas["issuer_evidence_inserted"]
    security_evidence = daily_entity_deltas["security_evidence_inserted"]
    listing_evidence = daily_entity_deltas["listing_evidence_inserted"]
    return {
        "scrape": _stage("PASS" if input_freshness["inputs_missing"] == 0 else "FAIL"),
        "verify": _stage("UNKNOWN", "No durable verify report is currently linked."),
        "observations": _stage("PASS" if _positive_or_zero(observations_created) else "UNKNOWN"),
        "issuers": _stage("PASS" if _positive_or_zero(issuer_evidence) else "UNKNOWN"),
        "securities": _stage("PASS" if _positive_or_zero(security_evidence) else "UNKNOWN"),
        "listings": _stage("PASS" if _positive_or_zero(listing_evidence) else "UNKNOWN"),
        "validation": _stage(validation_report["status"] if validation_report["present"] else "UNKNOWN"),
        "conflicts": _stage(conflict_report["status"] if conflict_report["present"] else "UNKNOWN"),
    }


def evaluate_daily_summary_findings(
    *,
    input_freshness: dict[str, Any],
    pipeline_stage_health: dict[str, Any],
    validation_report: dict[str, Any],
    conflict_report: dict[str, Any],
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

    for report_name, linked_report in (
        ("validation", validation_report),
        ("conflict", conflict_report),
    ):
        status = linked_report["status"]
        if not linked_report["present"]:
            failures.append(
                {
                    "code": f"{report_name}_report_missing",
                    "message": f"The daily summary could not find a {report_name} report artifact.",
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
) -> Path:
    generated_at = generated_at or datetime.now(UTC)
    root = Path(temp_dir or os.environ.get("EMPIRE_TEMP_DIR", "/tmp"))
    filename = f"stonks_securities_daily_summary_{generated_at:%Y%m%dT%H%M%SZ}.json"
    return root / "stonks" / "securities" / "summary" / filename


def write_daily_summary_report_to_object_store(
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
            "summary",
            f"{generated_at:%Y}",
            f"{generated_at:%m}",
            f"{generated_at:%d}",
        ]
    )
    filename = f"stonks_securities_daily_summary_{generated_at:%Y%m%dT%H%M%SZ}.json"
    return object_store.put_bytes(
        run_context=None,
        object_scope="manual",
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
) -> dict[str, Any] | None:
    day_key = f"stonks/securities/%/{generated_at:%Y}/{generated_at:%m}/{generated_at:%d}"
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
          AND so.object_key LIKE %s
        ORDER BY so.created_at DESC
        LIMIT 1
        """,
        (object_kind, day_key),
    )
    return rows[0] if rows else None


def _linked_report_object(
    cursor: Any,
    *,
    object_kind: str,
    object_id: str | UUID | None,
    generated_at: datetime,
) -> dict[str, Any] | None:
    if object_id is None:
        return _latest_report_object(
            cursor,
            object_kind=object_kind,
            generated_at=generated_at,
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
    generated_at: datetime,
) -> dict[str, Any]:
    day_start = generated_at.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    obs_from, obs_params = _observation_scope_sql(source_run_id)
    return {
        "observations_created": _scalar(
            cursor,
            "daily_summary_observations_created",
            f"SELECT COUNT(*) FROM {obs_from}",
            obs_params,
        ),
        "issuer_evidence_inserted": _evidence_count(cursor, obs_from, obs_params, "issuer_id"),
        "security_evidence_inserted": _evidence_count(cursor, obs_from, obs_params, "security_id"),
        "listing_evidence_inserted": _evidence_count(cursor, obs_from, obs_params, "listing_id"),
        "issuers_created": _created_count(cursor, "issuer", day_start, day_end),
        "issuers_updated": _updated_count(cursor, "issuer", day_start, day_end),
        "securities_created": _created_count(cursor, "security", day_start, day_end),
        "securities_updated": _updated_count(cursor, "security", day_start, day_end),
        "listings_created": _created_count(cursor, "listing", day_start, day_end),
        "listings_updated": _updated_count(cursor, "listing", day_start, day_end),
    }


def _evidence_count(cursor: Any, obs_from: str, obs_params: tuple[Any, ...], column: str) -> int:
    return _scalar(
        cursor,
        f"daily_summary_{column}_evidence_inserted",
        f"""
        SELECT COUNT(*)
        FROM stonks.provider_evidence pe
        JOIN {obs_from}
          ON po.provider_observation_id = pe.provider_observation_id
        WHERE pe.{column} IS NOT NULL
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


def _load_report_summary(
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
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else {}


def _normalize_report_status(value: Any) -> str:
    if value == "SUCCESS":
        return "PASS"
    if value in {"PASS", "WARN", "FAIL"}:
        return str(value)
    return "UNKNOWN"


def _stage(status: str, note: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": _normalize_report_status(status)}
    if note:
        result["note"] = note
    return result


def _positive_or_zero(value: Any) -> bool:
    return value is not None and int(value) >= 0


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
