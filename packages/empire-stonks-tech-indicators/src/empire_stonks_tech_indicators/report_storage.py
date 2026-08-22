"""Core storage for durable schema-V1 technical-indicator reports."""

from __future__ import annotations

import os
import re
from pathlib import Path
from types import MappingProxyType

from empire_core import ObjectStore, RunContext, StoredObject

from empire_stonks_tech_indicators.config import TechIndicatorsConfig
from empire_stonks_tech_indicators.reports import (
    BACKFILL_CORE_JOB_NAME,
    DAILY_CORE_JOB_NAME,
    TechIndicatorsReport,
    WorkflowKind,
    render_tech_indicators_report_json,
)
from empire_stonks_tech_indicators.report_pdf import (
    render_tech_indicators_report_pdf,
)


DEFAULT_REPORT_STORAGE_ROOT = "global"
JSON_REPORT_FILENAME = "report.json"
JSON_REPORT_CONTENT_TYPE = "application/json"
JSON_REPORT_OBJECT_KIND = "stonks_tech_indicators_report"
DAILY_JSON_REPORT_LOGICAL_NAME = "tech_indicators_daily_report"
BACKFILL_JSON_REPORT_LOGICAL_NAME = "tech_indicators_backfill_report"
PDF_REPORT_FILENAME = "report.pdf"
PDF_REPORT_CONTENT_TYPE = "application/pdf"
PDF_REPORT_OBJECT_KIND = "stonks_tech_indicators_pdf_report"
DAILY_PDF_REPORT_LOGICAL_NAME = "tech_indicators_daily_pdf_report"
BACKFILL_PDF_REPORT_LOGICAL_NAME = "tech_indicators_backfill_pdf_report"

JSON_REPORT_LOGICAL_NAMES = MappingProxyType(
    {
        WorkflowKind.DAILY: DAILY_JSON_REPORT_LOGICAL_NAME,
        WorkflowKind.BACKFILL: BACKFILL_JSON_REPORT_LOGICAL_NAME,
    }
)

PDF_REPORT_LOGICAL_NAMES = MappingProxyType(
    {
        WorkflowKind.DAILY: DAILY_PDF_REPORT_LOGICAL_NAME,
        WorkflowKind.BACKFILL: BACKFILL_PDF_REPORT_LOGICAL_NAME,
    }
)

_PATH_SEGMENT_PATTERN = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")


def build_tech_indicators_report_object_key(
    *,
    storage_key: str,
    run_context: RunContext,
) -> str:
    """Build the frozen date/run-scoped Core reports key."""

    _validate_active_run_context(run_context)
    prefix = _validate_storage_key(storage_key)
    effective_date = run_context.effective_date
    assert effective_date is not None
    return "/".join(
        (
            prefix,
            "runs",
            f"{effective_date:%Y}",
            f"{effective_date:%m}",
            f"{effective_date:%d}",
            str(run_context.run_id),
            "reports",
        )
    )


def tech_indicators_report_metadata(
    report: TechIndicatorsReport,
) -> dict[str, str | int | None]:
    """Return the exact secret-safe Core metadata allowlist for one report."""

    if not isinstance(report, TechIndicatorsReport):
        raise TypeError("report must be a TechIndicatorsReport.")
    return {
        "schema_version": report.schema_version,
        "report_id": report.report_id,
        "workflow_kind": report.workflow_kind.value,
        "outcome": report.outcome.value,
        "effective_date": report.identity.effective_date.isoformat(),
        "calculation_version": report.versions.calculation_version,
        "scope_hash": report.scope.scope_hash,
        "publication_id": (
            None
            if report.identity.publication_id is None
            else str(report.identity.publication_id)
        ),
        "generated_at": report.generated_at.isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
    }


def store_tech_indicators_json_report(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: TechIndicatorsConfig,
    report: TechIndicatorsReport,
    storage_root: str = DEFAULT_REPORT_STORAGE_ROOT,
) -> StoredObject:
    """Render and store one non-expiring report.json under its Core run."""

    if not isinstance(object_store, ObjectStore):
        raise TypeError("object_store must be a Core ObjectStore.")
    if not isinstance(config, TechIndicatorsConfig):
        raise TypeError("config must be a TechIndicatorsConfig.")
    if not isinstance(report, TechIndicatorsReport):
        raise TypeError("report must be a TechIndicatorsReport.")
    _validate_storage_root(storage_root)
    _validate_report_run_relationship(run_context, report, config)

    return object_store.put_bytes(
        run_context=run_context,
        object_scope="run",
        domain="stonks",
        logical_name=JSON_REPORT_LOGICAL_NAMES[report.workflow_kind],
        storage_root=storage_root,
        object_key=build_tech_indicators_report_object_key(
            storage_key=config.storage_key,
            run_context=run_context,
        ),
        filename=JSON_REPORT_FILENAME,
        data=render_tech_indicators_report_json(report),
        content_type=JSON_REPORT_CONTENT_TYPE,
        object_kind=JSON_REPORT_OBJECT_KIND,
        expires_at=None,
        metadata=tech_indicators_report_metadata(report),
    )


def store_tech_indicators_pdf_report(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: TechIndicatorsConfig,
    report: TechIndicatorsReport,
    storage_root: str = DEFAULT_REPORT_STORAGE_ROOT,
    output_dir: str | Path | None = None,
) -> StoredObject:
    """Render and store one non-expiring report.pdf under its Core run."""

    if not isinstance(object_store, ObjectStore):
        raise TypeError("object_store must be a Core ObjectStore.")
    if not isinstance(config, TechIndicatorsConfig):
        raise TypeError("config must be a TechIndicatorsConfig.")
    if not isinstance(report, TechIndicatorsReport):
        raise TypeError("report must be a TechIndicatorsReport.")
    _validate_storage_root(storage_root)
    _validate_report_run_relationship(run_context, report, config)

    render_root = Path(output_dir or os.environ.get("EMPIRE_TEMP_DIR", "/tmp"))
    render_dir = (
        render_root
        / "empire"
        / "stonks-tech-indicators"
        / str(run_context.run_id)
        / "reports"
    )
    result = render_tech_indicators_report_pdf(
        report,
        output_dir=render_dir,
        filename=PDF_REPORT_FILENAME,
    )
    return object_store.put_file(
        run_context=run_context,
        object_scope="run",
        domain="stonks",
        logical_name=PDF_REPORT_LOGICAL_NAMES[report.workflow_kind],
        storage_root=storage_root,
        object_key=build_tech_indicators_report_object_key(
            storage_key=config.storage_key,
            run_context=run_context,
        ),
        filename=PDF_REPORT_FILENAME,
        source_path=result.primary_artifact.path,
        move=False,
        content_type=PDF_REPORT_CONTENT_TYPE,
        object_kind=PDF_REPORT_OBJECT_KIND,
        expires_at=None,
        metadata=tech_indicators_report_metadata(report),
    )


def _validate_report_run_relationship(
    run_context: RunContext,
    report: TechIndicatorsReport,
    config: TechIndicatorsConfig,
) -> None:
    _validate_active_run_context(run_context)
    expected_job = {
        WorkflowKind.DAILY: DAILY_CORE_JOB_NAME,
        WorkflowKind.BACKFILL: BACKFILL_CORE_JOB_NAME,
    }[report.workflow_kind]
    if run_context.run_id != report.identity.run_id:
        raise ValueError("report run_id must match the active Core run.")
    if run_context.job_name != expected_job:
        raise ValueError("report workflow must match the active Core job.")
    if run_context.subject_key != report.identity.core_subject_key:
        raise ValueError("report subject key must match the active Core run.")
    if run_context.effective_date != report.identity.effective_date:
        raise ValueError("report effective date must match the active Core run.")
    if config.calculation_version != report.versions.calculation_version:
        raise ValueError("report calculation version must match configuration.")


def _validate_active_run_context(run_context: RunContext) -> None:
    if not isinstance(run_context, RunContext):
        raise TypeError("run_context must be a Core RunContext.")
    if run_context.domain != "stonks" or run_context.status != "started":
        raise ValueError("run_context must be an active stonks run.")
    if run_context.effective_date is None:
        raise ValueError("run_context effective_date is required.")


def _validate_storage_key(storage_key: object) -> str:
    if not isinstance(storage_key, str) or not storage_key:
        raise ValueError("storage_key must be a non-empty string.")
    segments = storage_key.split("/")
    if any(not _PATH_SEGMENT_PATTERN.fullmatch(item) for item in segments):
        raise ValueError("storage_key must contain path-safe segments.")
    return storage_key


def _validate_storage_root(storage_root: object) -> None:
    if not isinstance(storage_root, str) or not _PATH_SEGMENT_PATTERN.fullmatch(
        storage_root
    ):
        raise ValueError("storage_root must be a path-safe Core root name.")


__all__ = [
    "BACKFILL_PDF_REPORT_LOGICAL_NAME",
    "BACKFILL_JSON_REPORT_LOGICAL_NAME",
    "DAILY_PDF_REPORT_LOGICAL_NAME",
    "DAILY_JSON_REPORT_LOGICAL_NAME",
    "DEFAULT_REPORT_STORAGE_ROOT",
    "JSON_REPORT_CONTENT_TYPE",
    "JSON_REPORT_FILENAME",
    "JSON_REPORT_LOGICAL_NAMES",
    "JSON_REPORT_OBJECT_KIND",
    "PDF_REPORT_CONTENT_TYPE",
    "PDF_REPORT_FILENAME",
    "PDF_REPORT_LOGICAL_NAMES",
    "PDF_REPORT_OBJECT_KIND",
    "build_tech_indicators_report_object_key",
    "store_tech_indicators_json_report",
    "store_tech_indicators_pdf_report",
    "tech_indicators_report_metadata",
]
