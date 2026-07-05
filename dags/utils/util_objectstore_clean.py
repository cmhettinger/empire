from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_reports.contracts import RenderContext, RenderResult, ReportMetadata
from empire_reports.renderers.pdf import (
    HeaderFooterSpec,
    PdfRenderer,
    paragraph,
    professional_letter_title_page,
    section_heading,
    spacer,
)
from empire_reports.renderers.pdf.tables import simple_table
from reportlab.platypus import PageBreak

log = logging.getLogger(__name__)

DEFAULT_CLEANUP_BATCH_SIZE = 100
DEFAULT_PURGE_BATCH_SIZE = 100
DEFAULT_STORAGE_ROOT = "global"
REPORT_STORAGE_KEY = "utils/objectstore-clean"
REPORT_TYPE = "summary"
REPORT_NAME = "util_objectstore_clean_summary"
REPORT_ID = "utils.objectstore-clean.summary"
REPORT_LOGICAL_NAME = "util_objectstore_clean_summary_pdf"
REPORT_OBJECT_KIND = "util_objectstore_clean_summary_pdf"
TITLE = "Object Store Cleanup"
SUBTITLE = "Clean and Purge Summary Report"
HEADER_TEXT = "EMPIRE OPERATIONS"
FOOTER_TEXT = "INTERNAL USE ONLY"


@dag(
    dag_id="util_objectstore_clean",
    start_date=datetime(2026, 6, 7),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["utils", "object-store"],
)
def util_objectstore_clean():
    @task(task_id="cleanup_expired_objects")
    def cleanup_expired_objects() -> dict:
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        batch_size = _cleanup_batch_size_from_conf(conf)

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            result = object_store.cleanup_expired_objects(batch_size=batch_size)

        log.info(
            "Completed object-store cleanup with batch_size=%s cleaned_count=%s "
            "cleaned_bytes=%s",
            batch_size,
            result.cleaned_count,
            _format_bytes(result.cleaned_bytes),
        )
        for root_stat in result.root_stats:
            log.info(
                "Object-store cleanup root=%s cleaned_count=%s cleaned_bytes=%s",
                root_stat.storage_root_name,
                root_stat.cleaned_count,
                _format_bytes(root_stat.cleaned_bytes),
            )
        if not result.root_stats:
            log.info("Object-store cleanup found no expired objects to clean.")

        return {
            "batch_size": batch_size,
            "cleaned_count": result.cleaned_count,
            "cleaned_bytes": result.cleaned_bytes,
            "cleaned_bytes_human": _format_bytes(result.cleaned_bytes),
            "root_stats": [
                {
                    "storage_root_name": root_stat.storage_root_name,
                    "cleaned_count": root_stat.cleaned_count,
                    "cleaned_bytes": root_stat.cleaned_bytes,
                    "cleaned_bytes_human": _format_bytes(root_stat.cleaned_bytes),
                }
                for root_stat in result.root_stats
            ],
        }

    @task(task_id="purge_deleted_objects")
    def purge_deleted_objects() -> dict:
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        batch_size = _purge_batch_size_from_conf(conf)

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            result = object_store.purge_deleted_objects_all(batch_size=batch_size)

        log.info(
            "Completed object-store purge with batch_size=%s purged_count=%s",
            batch_size,
            result.purged_count,
        )
        for root_stat in result.root_stats:
            log.info(
                "Object-store purge root=%s purged_count=%s",
                root_stat.storage_root_name,
                root_stat.purged_count,
            )
        if not result.root_stats:
            log.info("Object-store purge found no tombstoned records to purge.")

        return {
            "batch_size": batch_size,
            "purged_count": result.purged_count,
            "root_stats": [
                {
                    "storage_root_name": root_stat.storage_root_name,
                    "purged_count": root_stat.purged_count,
                }
                for root_stat in result.root_stats
            ],
        }

    @task(task_id="generate_pdf_summary")
    def generate_pdf_summary(
        purge_result: dict[str, Any],
    ) -> dict[str, Any]:
        context = get_current_context()
        task_instance = context["ti"]
        dag_run = context["dag_run"]
        logical_date = context.get("logical_date")
        generated_at = datetime.now(UTC)
        clean_result = task_instance.xcom_pull(task_ids="cleanup_expired_objects")
        if not isinstance(clean_result, dict):
            raise RuntimeError("cleanup_expired_objects did not return summary data")
        report = _build_summary_report(
            clean_result=clean_result,
            purge_result=purge_result,
            generated_at=generated_at,
            run_context={
                "dag_id": dag_run.dag_id,
                "run_id": dag_run.run_id,
                "logical_date": str(logical_date),
                "environment": "airflow",
            },
        )

        with EmpireDatabase.connect_from_env() as conn:
            run_service = RunService.from_connection(conn)
            object_store = ObjectStore.from_connection(conn)
            ctx = run_service.start_run(
                domain="utils",
                job_name="util_objectstore_clean",
                subject_key=str(dag_run.run_id),
                effective_date=_report_date(
                    logical_date=logical_date,
                    generated_at=generated_at,
                ).date(),
                run_type="airflow",
                runner="airflow",
                runner_ref={
                    "dag_id": "util_objectstore_clean",
                    "task_id": "generate_pdf_summary",
                    "airflow_run_id": dag_run.run_id,
                },
                params={
                    "clean_batch_size": clean_result.get("batch_size"),
                    "purge_batch_size": purge_result.get("batch_size"),
                },
            )
            try:
                stored = _write_summary_pdf_to_object_store(
                    report=report,
                    object_store=object_store,
                    storage_run_context=ctx,
                    generated_at=generated_at,
                    logical_date=logical_date,
                )
                summary = {
                    **report["summary"],
                    "report_object_id": str(stored.object_id),
                    "report_object_key": stored.object_key,
                    "report_filename": stored.filename,
                }
                completed = run_service.complete_run(ctx.run_id, summary=summary)
            except Exception as exc:
                run_service.fail_run(
                    ctx.run_id,
                    error_message=str(exc),
                    summary=report["summary"],
                )
                raise

        log.info(
            "Stored object-store cleanup PDF summary run_id=%s object_id=%s path=%s/%s",
            completed.run_id,
            stored.object_id,
            stored.object_key,
            stored.filename,
        )
        return {
            "run_id": str(completed.run_id),
            "object_id": str(stored.object_id),
            "object_key": stored.object_key,
            "filename": stored.filename,
            "content_type": stored.content_type,
            "summary": report["summary"],
        }

    clean_result = cleanup_expired_objects()
    purge_result = purge_deleted_objects()
    summary_result = generate_pdf_summary(purge_result)

    clean_result >> purge_result >> summary_result


def _build_summary_report(
    *,
    clean_result: dict[str, Any],
    purge_result: dict[str, Any],
    generated_at: datetime,
    run_context: dict[str, Any],
) -> dict[str, Any]:
    cleaned_count = int(clean_result.get("cleaned_count") or 0)
    cleaned_bytes = int(clean_result.get("cleaned_bytes") or 0)
    purged_count = int(purge_result.get("purged_count") or 0)
    summary = {
        "status": "PASS",
        "clean_batch_size": clean_result.get("batch_size"),
        "purge_batch_size": purge_result.get("batch_size"),
        "files_freed": cleaned_count,
        "disk_space_freed_bytes": cleaned_bytes,
        "disk_space_freed_human": _format_bytes(cleaned_bytes),
        "metadata_rows_purged": purged_count,
        "cleanup_root_count": len(clean_result.get("root_stats") or []),
        "purge_root_count": len(purge_result.get("root_stats") or []),
    }
    return {
        "report_name": REPORT_NAME,
        "report_id": REPORT_ID,
        "generated_at": generated_at.isoformat(),
        "status": "PASS",
        "healthy": True,
        "run_context": run_context,
        "summary": summary,
        "clean": clean_result,
        "purge": purge_result,
    }


def _write_summary_pdf_to_object_store(
    *,
    report: dict[str, Any],
    object_store: ObjectStore,
    storage_run_context,
    generated_at: datetime,
    logical_date: Any = None,
    storage_root: str = DEFAULT_STORAGE_ROOT,
    storage_key: str = REPORT_STORAGE_KEY,
):
    object_key = _run_report_object_key(
        storage_key=storage_key,
        report_type=REPORT_TYPE,
        logical_date=logical_date or report.get("run_context", {}).get("logical_date"),
        generated_at=generated_at,
    )
    filename = f"util-objectstore-clean-summary-{storage_run_context.run_id}.pdf"
    render_root = Path(os.environ.get("EMPIRE_TEMP_DIR", "/tmp"))
    render_dir = _run_report_path(
        root=render_root,
        report_type=REPORT_TYPE,
        filename="pdf-render",
        logical_date=logical_date or report.get("run_context", {}).get("logical_date"),
        generated_at=generated_at,
    ).parent
    result = _render_summary_pdf(
        report=report,
        output_dir=render_dir,
        generated_at=generated_at,
        filename=filename,
    )
    return object_store.put_file(
        run_context=storage_run_context,
        object_scope="run",
        domain="utils",
        logical_name=REPORT_LOGICAL_NAME,
        storage_root=storage_root,
        object_key=object_key,
        filename=filename,
        source_path=result.primary_artifact.path,
        move=False,
        content_type="application/pdf",
        object_kind=REPORT_OBJECT_KIND,
        metadata={
            "report_name": REPORT_NAME,
            "report_id": result.report.report_id,
            "generated_at": report["generated_at"],
        },
    )


def _render_summary_pdf(
    *,
    report: dict[str, Any],
    output_dir: str | Path,
    generated_at: datetime,
    filename: str,
) -> RenderResult:
    generated_at = (
        generated_at if generated_at.tzinfo else generated_at.replace(tzinfo=UTC)
    )
    metadata = ReportMetadata(
        report_id=REPORT_ID,
        title=TITLE,
        subtitle=SUBTITLE,
        as_of=generated_at.date(),
        generated_at=generated_at,
        tags=("utils", "object-store", "cleanup"),
    )
    renderer = PdfRenderer(
        metadata=metadata,
        context=RenderContext(output_dir=Path(output_dir)),
    )
    story = [
        *professional_letter_title_page(
            title=metadata.title,
            subtitle=metadata.subtitle or "",
            report_date=metadata.as_of,
            header_text=HEADER_TEXT,
            footer_text=FOOTER_TEXT,
            classification_text=FOOTER_TEXT,
            branding=renderer.branding,
            theme=renderer.theme,
        ),
        PageBreak(),
        *_summary_story(report=report, generated_at=generated_at, renderer=renderer),
    ]
    out_path = Path(output_dir) / filename
    return renderer.render(
        story,
        out_path=out_path,
        header_footer=HeaderFooterSpec(
            header_center_text=HEADER_TEXT,
            footer_text=FOOTER_TEXT,
        ),
    )


def _summary_story(
    *,
    report: dict[str, Any],
    generated_at: datetime,
    renderer: PdfRenderer,
) -> list[Any]:
    styles = renderer.styles
    return [
        section_heading("Summary", styles=styles),
        paragraph(_executive_summary(report), styles=styles),
        spacer(8),
        simple_table(
            _summary_rows(report, generated_at=generated_at),
            theme=renderer.theme,
        ),
        spacer(14),
        section_heading("Clean Task Statistics", styles=styles),
        simple_table(_clean_rows(report), theme=renderer.theme),
        spacer(14),
        section_heading("Purge Task Statistics", styles=styles),
        simple_table(_purge_rows(report), theme=renderer.theme),
        spacer(14),
        section_heading("Run Facts", styles=styles),
        simple_table(
            _run_fact_rows(report, generated_at=generated_at),
            theme=renderer.theme,
        ),
    ]


def _executive_summary(report: dict[str, Any]) -> str:
    summary = report["summary"]
    return (
        "The object store cleanup completed successfully. "
        f"It freed <b>{_fmt_int(summary['files_freed'])}</b> files and "
        f"<b>{summary['disk_space_freed_human']}</b> of disk space, then purged "
        f"<b>{_fmt_int(summary['metadata_rows_purged'])}</b> deleted metadata rows."
    )


def _summary_rows(report: dict[str, Any], *, generated_at: datetime) -> list[list[str]]:
    summary = report["summary"]
    return [
        ["Metric", "Value"],
        ["Status", str(summary["status"])],
        ["Generated At", generated_at.isoformat()],
        ["Files Freed", _fmt_int(summary["files_freed"])],
        ["Disk Space Freed", summary["disk_space_freed_human"]],
        ["Disk Space Freed (Bytes)", _fmt_int(summary["disk_space_freed_bytes"])],
        ["Metadata Rows Purged", _fmt_int(summary["metadata_rows_purged"])],
    ]


def _clean_rows(report: dict[str, Any]) -> list[list[str]]:
    clean = report["clean"]
    rows = [
        ["Storage Root", "Files Freed", "Disk Space Freed", "Bytes Freed"],
        [
            "All roots",
            _fmt_int(clean.get("cleaned_count")),
            str(
                clean.get("cleaned_bytes_human")
                or _format_bytes(int(clean.get("cleaned_bytes") or 0))
            ),
            _fmt_int(clean.get("cleaned_bytes")),
        ],
    ]
    for root in clean.get("root_stats") or []:
        rows.append(
            [
                str(root.get("storage_root_name") or ""),
                _fmt_int(root.get("cleaned_count")),
                str(
                    root.get("cleaned_bytes_human")
                    or _format_bytes(int(root.get("cleaned_bytes") or 0))
                ),
                _fmt_int(root.get("cleaned_bytes")),
            ]
        )
    return rows


def _purge_rows(report: dict[str, Any]) -> list[list[str]]:
    purge = report["purge"]
    rows = [["Storage Root", "Metadata Rows Purged"]]
    rows.append(["All roots", _fmt_int(purge.get("purged_count"))])
    for root in purge.get("root_stats") or []:
        rows.append(
            [
                str(root.get("storage_root_name") or ""),
                _fmt_int(root.get("purged_count")),
            ]
        )
    return rows


def _run_fact_rows(report: dict[str, Any], *, generated_at: datetime) -> list[list[str]]:
    run_context = report.get("run_context", {})
    summary = report["summary"]
    return [
        ["Fact", "Value"],
        ["DAG ID", str(run_context.get("dag_id") or "")],
        ["Airflow Run ID", str(run_context.get("run_id") or "")],
        ["Logical Date", str(run_context.get("logical_date") or "")],
        ["Generated At", generated_at.isoformat()],
        ["Clean Batch Size", _fmt_int(summary.get("clean_batch_size"))],
        ["Purge Batch Size", _fmt_int(summary.get("purge_batch_size"))],
    ]


def _run_report_object_key(
    *,
    storage_key: str,
    report_type: str,
    logical_date: Any = None,
    generated_at: datetime | None = None,
) -> str:
    report_date = _report_date(logical_date=logical_date, generated_at=generated_at)
    return "/".join(
        [
            storage_key.strip("/"),
            "runs",
            f"{report_date:%Y}",
            f"{report_date:%m}",
            f"{report_date:%d}",
            "run-reports",
            report_type.strip("/"),
        ]
    )


def _run_report_path(
    *,
    root: str | Path,
    report_type: str,
    filename: str,
    logical_date: Any = None,
    generated_at: datetime | None = None,
) -> Path:
    report_date = _report_date(logical_date=logical_date, generated_at=generated_at)
    return (
        Path(root)
        / REPORT_STORAGE_KEY
        / "runs"
        / f"{report_date:%Y}"
        / f"{report_date:%m}"
        / f"{report_date:%d}"
        / "run-reports"
        / report_type.strip("/")
        / filename
    )


def _report_date(*, logical_date: Any, generated_at: datetime | None) -> datetime:
    parsed = _parse_datetime(logical_date)
    if parsed is not None:
        return parsed
    fallback = generated_at or datetime.now(UTC)
    return fallback if fallback.tzinfo else fallback.replace(tzinfo=UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _fmt_int(value: Any) -> str:
    return f"{int(value or 0):,}"


def _cleanup_batch_size_from_conf(conf: dict) -> int:
    raw_batch_size = conf.get("batch_size", DEFAULT_CLEANUP_BATCH_SIZE)
    return _positive_batch_size(raw_batch_size, "dag_run.conf batch_size")


def _purge_batch_size_from_conf(conf: dict) -> int:
    if "purge_batch_size" in conf:
        return _positive_batch_size(
            conf["purge_batch_size"],
            "dag_run.conf purge_batch_size",
        )
    return _positive_batch_size(
        conf.get("batch_size", DEFAULT_PURGE_BATCH_SIZE),
        "dag_run.conf batch_size",
    )


def _positive_batch_size(raw_batch_size, label: str) -> int:
    batch_size = int(raw_batch_size)
    if batch_size <= 0:
        raise RuntimeError(f"{label} must be positive")
    return batch_size


def _format_bytes(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024


util_objectstore_clean_dag = util_objectstore_clean()
