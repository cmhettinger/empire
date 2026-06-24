"""Verification helpers for cached SEC security-master source files."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

from empire_core import ObjectStore, RunContext as CoreRunContext
from empire_core.object_store.models import StoredObject

from empire_stonks_securities.acquisition import (
    DEFAULT_STORAGE_ROOT,
    SEC_SOURCE_METADATA_OBJECT_KIND,
    SEC_SOURCE_OBJECT_KIND,
    default_storage_key,
)
from empire_stonks_securities.parsing import (
    SecSourceParseError,
    SecSourceParser,
    get_sec_source_parser,
)
from empire_stonks_securities.report_paths import run_report_object_key, run_report_path
from empire_stonks_securities.runner import DEFAULT_DAILY_SOURCE_KEYS


logger = logging.getLogger(__name__)

VERIFY_REPORT_NAME = "stonks_securities_verify"
VERIFY_REPORT_OBJECT_KIND = "stonks_securities_verify_report"
VERIFY_REPORT_LOGICAL_NAME = "stonks_securities_verify"


@dataclass(frozen=True)
class SecSourceVerifySummary:
    """Verification counts for one SEC source file."""

    source_code: str
    object_id: str | None
    object_key: str | None
    filename: str | None
    good_record_count: int
    parse_error_count: int
    bad_record_count: int
    exchange_null_count: int = 0
    failed: bool = False
    error: str | None = None
    metadata_object_id: str | None = None
    metadata_path: str | None = None
    metadata_present: bool = False
    size_bytes: int | None = None
    sha256: str | None = None
    metadata_sha256: str | None = None
    checksum_status: str = "UNKNOWN"
    downloaded_at: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    warnings: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_code": self.source_code,
            "object_id": self.object_id,
            "object_key": self.object_key,
            "filename": self.filename,
            "good_record_count": self.good_record_count,
            "parse_error_count": self.parse_error_count,
            "bad_record_count": self.bad_record_count,
            "exchange_null_count": self.exchange_null_count,
            "failed": self.failed,
            "error": self.error,
            "metadata_object_id": self.metadata_object_id,
            "metadata_path": self.metadata_path,
            "metadata_present": self.metadata_present,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "metadata_sha256": self.metadata_sha256,
            "checksum_status": self.checksum_status,
            "downloaded_at": self.downloaded_at,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "warnings": list(self.warnings),
            "failures": list(self.failures),
        }


@dataclass(frozen=True)
class StonksSecuritiesDailyVerifyResult:
    """Verification result for a stonks securities acquisition run."""

    input_run_id: str
    source_summaries: list[SecSourceVerifySummary]

    @property
    def good_record_count(self) -> int:
        return sum(summary.good_record_count for summary in self.source_summaries)

    @property
    def parse_error_count(self) -> int:
        return sum(summary.parse_error_count for summary in self.source_summaries)

    @property
    def failed_source_count(self) -> int:
        return sum(1 for summary in self.source_summaries if summary.failed)

    @property
    def exchange_null_count(self) -> int:
        return sum(summary.exchange_null_count for summary in self.source_summaries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_run_id": self.input_run_id,
            "good_record_count": self.good_record_count,
            "parse_error_count": self.parse_error_count,
            "failed_source_count": self.failed_source_count,
            "exchange_null_count": self.exchange_null_count,
            "source_summaries": [summary.to_dict() for summary in self.source_summaries],
        }


def verify_stonks_securities_daily_sources(
    *,
    object_store: ObjectStore,
    input_run_id: str | UUID,
    source_codes: Iterable[str] = DEFAULT_DAILY_SOURCE_KEYS,
    raw_preview_chars: int = 1000,
) -> StonksSecuritiesDailyVerifyResult:
    """Parse downloaded daily SEC sources and log verification counts."""

    parsed_run_id = input_run_id if isinstance(input_run_id, UUID) else UUID(str(input_run_id))
    summaries = [
        verify_sec_source(
            object_store=object_store,
            input_run_id=parsed_run_id,
            source_code=source_code,
            raw_preview_chars=raw_preview_chars,
        )
        for source_code in source_codes
    ]
    result = StonksSecuritiesDailyVerifyResult(
        input_run_id=str(parsed_run_id),
        source_summaries=summaries,
    )
    logger.info(
        "Completed stonks securities daily verify for input_run_id=%s: "
        "good_record_count=%s parse_error_count=%s failed_source_count=%s "
        "exchange_null_count=%s",
        result.input_run_id,
        result.good_record_count,
        result.parse_error_count,
        result.failed_source_count,
        result.exchange_null_count,
    )
    return result


def verify_sec_source(
    *,
    object_store: ObjectStore,
    input_run_id: UUID,
    source_code: str,
    raw_preview_chars: int = 1000,
) -> SecSourceVerifySummary:
    """Parse one source object and log enough context to investigate bad rows."""

    parser = get_sec_source_parser(source_code)
    stored = _find_source_object(
        object_store=object_store,
        input_run_id=input_run_id,
        parser=parser,
    )
    if stored is None:
        error = (
            "SEC source object not found for verify: "
            f"input_run_id={input_run_id}, source_code={parser.source_code}, "
            f"filename={parser.filename}"
        )
        logger.error(error)
        return SecSourceVerifySummary(
            source_code=parser.source_code,
            object_id=None,
            object_key=None,
            filename=parser.filename,
            good_record_count=0,
            parse_error_count=1,
            bad_record_count=0,
            failed=True,
            error=error,
            checksum_status="UNKNOWN",
            failures=(error,),
        )

    metadata_result = _load_source_metadata(
        object_store=object_store,
        input_run_id=input_run_id,
        parser=parser,
    )
    source_failures = list(metadata_result["failures"])
    checksum_status = metadata_result["checksum_status"]
    metadata = metadata_result["metadata"]
    metadata_sha256 = metadata.get("sha256") if isinstance(metadata, dict) else None
    if metadata_sha256 is not None and stored.checksum_sha256 != metadata_sha256:
        checksum_status = "FAIL"
        source_failures.append(
            "Source checksum does not match SEC source metadata sidecar."
        )

    try:
        parsed = parser.parse_object(object_store, stored.object_id)
    except SecSourceParseError as exc:
        source_failures.append(str(exc))
        logger.exception(
            "Failed to parse SEC source object: source_code=%s object_id=%s "
            "object_key=%s filename=%s error=%s",
            parser.source_code,
            stored.object_id,
            stored.object_key,
            stored.filename,
            exc,
        )
        return SecSourceVerifySummary(
            source_code=parser.source_code,
            object_id=str(stored.object_id),
            object_key=stored.object_key,
            filename=stored.filename,
            good_record_count=0,
            parse_error_count=1,
            bad_record_count=0,
            failed=True,
            error=str(exc),
            metadata_object_id=metadata_result["metadata_object_id"],
            metadata_path=metadata_result["metadata_path"],
            metadata_present=metadata_result["metadata_present"],
            size_bytes=stored.size_bytes,
            sha256=stored.checksum_sha256,
            metadata_sha256=metadata_sha256,
            checksum_status=checksum_status,
            downloaded_at=metadata.get("downloaded_at") if isinstance(metadata, dict) else None,
            etag=metadata.get("etag") if isinstance(metadata, dict) else None,
            last_modified=metadata.get("last_modified") if isinstance(metadata, dict) else None,
            failures=tuple(source_failures),
        )

    for bad_record in parsed.bad_records:
        logger.warning(
            "Malformed SEC source row: source_code=%s object_id=%s object_key=%s "
            "filename=%s row_number=%s error=%s raw_preview=%s",
            parser.source_code,
            stored.object_id,
            stored.object_key,
            stored.filename,
            bad_record.row_number,
            bad_record.error,
            _raw_preview(bad_record.raw, raw_preview_chars),
        )

    warnings = [
        f"{len(parsed.bad_records)} malformed records found."
    ] if parsed.bad_records else []
    summary = SecSourceVerifySummary(
        source_code=parser.source_code,
        object_id=str(stored.object_id),
        object_key=stored.object_key,
        filename=stored.filename,
        good_record_count=len(parsed.records),
        parse_error_count=len(parsed.bad_records),
        bad_record_count=len(parsed.bad_records),
        exchange_null_count=_exchange_null_count(parsed.records),
        failed=bool(source_failures),
        error="; ".join(source_failures) if source_failures else None,
        metadata_object_id=metadata_result["metadata_object_id"],
        metadata_path=metadata_result["metadata_path"],
        metadata_present=metadata_result["metadata_present"],
        size_bytes=stored.size_bytes,
        sha256=stored.checksum_sha256,
        metadata_sha256=metadata_sha256,
        checksum_status=checksum_status,
        downloaded_at=metadata.get("downloaded_at") if isinstance(metadata, dict) else None,
        etag=metadata.get("etag") if isinstance(metadata, dict) else None,
        last_modified=metadata.get("last_modified") if isinstance(metadata, dict) else None,
        warnings=tuple(warnings),
        failures=tuple(source_failures),
    )
    logger.info(
        "Verified SEC source: source_code=%s object_id=%s object_key=%s filename=%s "
        "good_record_count=%s parse_error_count=%s exchange_null_count=%s",
        summary.source_code,
        summary.object_id,
        summary.object_key,
        summary.filename,
        summary.good_record_count,
        summary.parse_error_count,
        summary.exchange_null_count,
    )
    return summary


@dataclass(frozen=True)
class VerifyRunContext:
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


def generate_verify_report(
    *,
    result: StonksSecuritiesDailyVerifyResult,
    run_context: VerifyRunContext | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(UTC)
    resolved_run_context = run_context or VerifyRunContext(source_run_id=result.input_run_id)
    sources = [_verify_source_report(summary) for summary in result.source_summaries]
    warnings = [
        {"code": "verify_source_warning", "source_code": source["source_code"], "message": warning}
        for source in sources
        for warning in source["warnings"]
    ]
    failures = [
        {"code": "verify_source_failure", "source_code": source["source_code"], "message": failure}
        for source in sources
        for failure in source["failures"]
    ]
    status = _verify_status(warnings=warnings, failures=failures)
    summary = {
        "status": status,
        "healthy": status in {"PASS", "WARN"},
        "inputs_checked": len(sources),
        "inputs_present": sum(1 for source in sources if source["present"]),
        "inputs_missing": sum(1 for source in sources if not source["present"]),
        "metadata_files_present": sum(1 for source in sources if source["metadata_present"]),
        "metadata_files_missing": sum(1 for source in sources if not source["metadata_present"]),
        "checksum_verified": sum(1 for source in sources if source["checksum_status"] == "PASS"),
        "checksum_failed": sum(1 for source in sources if source["checksum_status"] == "FAIL"),
        "warnings_total": len(warnings),
        "failures_total": len(failures),
        "good_record_count": result.good_record_count,
        "parse_error_count": result.parse_error_count,
        "exchange_null_count": result.exchange_null_count,
    }
    return {
        "report_name": VERIFY_REPORT_NAME,
        "generated_at": generated_at.isoformat(),
        "status": summary["status"],
        "healthy": summary["healthy"],
        "run_context": resolved_run_context.to_dict(),
        "summary": summary,
        "sources": sources,
        "warnings": warnings,
        "failures": failures,
    }


def verify_report_to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def write_verify_report_to_file(report: dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(verify_report_to_json(report), encoding="utf-8")
    return output_path


def default_verify_report_path(
    *,
    temp_dir: str | Path | None = None,
    generated_at: datetime | None = None,
    logical_date: Any = None,
) -> Path:
    generated_at = generated_at or datetime.now(UTC)
    root = Path(temp_dir or os.environ.get("EMPIRE_TEMP_DIR", "/tmp"))
    filename = f"stonks_securities_verify_{generated_at:%Y%m%dT%H%M%SZ}.json"
    return run_report_path(
        root=root,
        report_type="verify",
        filename=filename,
        logical_date=logical_date,
        generated_at=generated_at,
    )


def write_verify_report_to_object_store(
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
        report_type="verify",
        logical_date=logical_date or report.get("run_context", {}).get("logical_date"),
        generated_at=generated_at,
    )
    filename = f"stonks_securities_verify_{generated_at:%Y%m%dT%H%M%SZ}.json"
    return object_store.put_bytes(
        run_context=storage_run_context,
        object_scope="run" if storage_run_context is not None else "manual",
        domain="stonks",
        logical_name=VERIFY_REPORT_LOGICAL_NAME,
        storage_root=storage_root,
        object_key=object_key,
        filename=filename,
        data=verify_report_to_json(report).encode("utf-8"),
        content_type="application/json",
        object_kind=VERIFY_REPORT_OBJECT_KIND,
        metadata={"report_name": VERIFY_REPORT_NAME, "generated_at": report["generated_at"]},
    )


def _find_source_object(
    *,
    object_store: ObjectStore,
    input_run_id: UUID,
    parser: SecSourceParser,
) -> StoredObject | None:
    for logical_name in (parser.provider_code, parser.source_code):
        stored = object_store.find_one(
            run_id=input_run_id,
            object_kind=SEC_SOURCE_OBJECT_KIND,
            filename=parser.filename,
            logical_name=logical_name,
        )
        if stored is not None:
            return stored
    return None


def _find_metadata_object(
    *,
    object_store: ObjectStore,
    input_run_id: UUID,
    parser: SecSourceParser,
) -> StoredObject | None:
    for logical_name in (
        f"{parser.provider_code}.metadata",
        f"{parser.source_code}.metadata",
    ):
        stored = object_store.find_one(
            run_id=input_run_id,
            object_kind=SEC_SOURCE_METADATA_OBJECT_KIND,
            filename=f"{parser.filename}.metadata.json",
            logical_name=logical_name,
        )
        if stored is not None:
            return stored
    return None


def _load_source_metadata(
    *,
    object_store: ObjectStore,
    input_run_id: UUID,
    parser: SecSourceParser,
) -> dict[str, Any]:
    stored = _find_metadata_object(
        object_store=object_store,
        input_run_id=input_run_id,
        parser=parser,
    )
    if stored is None:
        return {
            "metadata": {},
            "metadata_object_id": None,
            "metadata_path": None,
            "metadata_present": False,
            "checksum_status": "UNKNOWN",
            "failures": ("Required SEC source metadata sidecar was not found.",),
        }
    try:
        metadata = json.loads(object_store.get_bytes(stored.object_id).decode("utf-8"))
    except Exception as exc:
        return {
            "metadata": {},
            "metadata_object_id": str(stored.object_id),
            "metadata_path": f"{stored.object_key}/{stored.filename}",
            "metadata_present": True,
            "checksum_status": "UNKNOWN",
            "failures": (f"Required SEC source metadata sidecar could not be read: {exc}",),
        }
    metadata_sha256 = metadata.get("sha256") if isinstance(metadata, dict) else None
    return {
        "metadata": metadata if isinstance(metadata, dict) else {},
        "metadata_object_id": str(stored.object_id),
        "metadata_path": f"{stored.object_key}/{stored.filename}",
        "metadata_present": True,
        "checksum_status": "PASS" if metadata_sha256 else "UNKNOWN",
        "failures": () if metadata_sha256 else ("Required SEC source metadata lacks sha256.",),
    }


def _verify_source_report(summary: SecSourceVerifySummary) -> dict[str, Any]:
    return {
        "source_code": summary.source_code,
        "expected": True,
        "file_path": (
            f"{summary.object_key}/{summary.filename}"
            if summary.object_key and summary.filename
            else None
        ),
        "metadata_path": summary.metadata_path,
        "present": summary.object_id is not None,
        "metadata_present": summary.metadata_present,
        "size_bytes": summary.size_bytes,
        "sha256": summary.sha256,
        "metadata_sha256": summary.metadata_sha256,
        "checksum_status": summary.checksum_status,
        "downloaded_at": summary.downloaded_at,
        "etag": summary.etag,
        "last_modified": summary.last_modified,
        "good_record_count": summary.good_record_count,
        "parse_error_count": summary.parse_error_count,
        "bad_record_count": summary.bad_record_count,
        "exchange_null_count": summary.exchange_null_count,
        "warnings": list(summary.warnings),
        "failures": list(summary.failures),
    }


def _verify_status(*, warnings: list[dict[str, Any]], failures: list[dict[str, Any]]) -> str:
    if failures:
        return "FAIL"
    if warnings:
        return "WARN"
    return "PASS"


def _raw_preview(raw: Any, max_chars: int) -> str:
    try:
        rendered = json.dumps(raw, sort_keys=True, default=str)
    except TypeError:
        rendered = repr(raw)
    if len(rendered) <= max_chars:
        return rendered
    return f"{rendered[:max_chars]}..."


def _exchange_null_count(records: Iterable[Any]) -> int:
    return sum(
        1
        for record in records
        if hasattr(record, "exchange") and getattr(record, "exchange") is None
    )
