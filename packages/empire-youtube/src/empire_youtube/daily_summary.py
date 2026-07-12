"""Daily YouTube/Jellyfin acquisition summary reporting."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from empire_core import ObjectStore, RunContext, RunService, StoredObject

from empire_youtube.reports.daily_summary.pdf.render import render_youtube_daily_summary_pdf
from empire_youtube.retention import youtube_expires_at
from empire_youtube.runner import DEFAULT_STORAGE_KEY, youtube_run_object_key


YOUTUBE_DAILY_SUMMARY_PDF_LOGICAL_NAME = "youtube_daily_summary_pdf"
YOUTUBE_DAILY_SUMMARY_PDF_OBJECT_KIND = "youtube_daily_summary_pdf"


@dataclass(frozen=True)
class YouTubeDailySummaryResult:
    report: dict[str, Any]
    run_context: RunContext
    stored_object: StoredObject

    def to_dict(self) -> dict[str, object]:
        return {
            "report": self.report,
            "run_id": str(self.run_context.run_id),
            "stored_object_id": str(self.stored_object.object_id),
            "object_key": self.stored_object.object_key,
            "filename": self.stored_object.filename,
        }


def build_youtube_daily_summary_report(
    *,
    scrape_result: dict[str, object],
    plan_result: dict[str, object],
    download_results: list[dict[str, object]],
    dag_id: str,
    dag_run_id: str,
    minimum_success_rate: float,
    scrape_payload: dict[str, object] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the stable, JSON-ready data model used by the PDF report."""

    generated_at = generated_at or datetime.now(UTC)
    successful = [
        result
        for result in download_results
        if result.get("status") in {"downloaded", "skipped"}
    ]
    failed = [
        {
            "video_id": str(result.get("video_id") or ""),
            "status": str(result.get("status") or "failed"),
            "error_message": str(result.get("error_message") or "")[:500],
        }
        for result in download_results
        if result.get("status") not in {"downloaded", "skipped"}
    ]
    total_count = len(download_results)
    success_rate = len(successful) / total_count if total_count else 1.0
    status = "PASS" if not failed else "WARN"
    if success_rate < minimum_success_rate:
        status = "FAIL"
    return {
        "report_name": "youtube_daily_summary",
        "generated_at": generated_at.isoformat(),
        "status": status,
        "healthy": status != "FAIL",
        "run_context": {
            "dag_id": dag_id,
            "run_id": dag_run_id,
            "scrape_run_id": str(scrape_result.get("run_id") or ""),
            "plan_run_id": str(plan_result.get("run_id") or ""),
        },
        "summary": {
            "scraped_video_count": int(scrape_result.get("video_count") or 0),
            "source_video_count": int(plan_result.get("source_video_count") or 0),
            "planned_download_count": int(plan_result.get("plan_entry_count") or 0),
            "sidecar_object_count": int(plan_result.get("sidecar_object_count") or 0),
            "skipped_sidecar_count": int(plan_result.get("skipped_sidecar_count") or 0),
            "download_total_count": total_count,
            "successful_download_count": len(successful),
            "failed_download_count": len(failed),
            "downloaded_count": sum(result.get("status") == "downloaded" for result in successful),
            "skipped_download_count": sum(result.get("status") == "skipped" for result in successful),
            "success_rate": success_rate,
            "minimum_success_rate": minimum_success_rate,
        },
        "failed_downloads": failed,
        "video_outcomes": _video_outcomes(
            scrape_payload=scrape_payload or {},
            download_results=download_results,
        ),
    }


def generate_youtube_daily_summary_pdf_stage(
    *,
    scrape_result: dict[str, object],
    plan_result: dict[str, object],
    download_results: list[dict[str, object]],
    dag_id: str,
    dag_run_id: str,
    minimum_success_rate: float,
    object_store: ObjectStore,
    run_service: RunService,
    run_context: RunContext,
    generated_at: datetime | None = None,
    output_dir: str | Path | None = None,
) -> YouTubeDailySummaryResult:
    """Render, store, and track a branded daily YouTube summary PDF."""

    generated_at = generated_at or datetime.now(UTC)
    scrape_payload = _load_scrape_payload(
        object_store=object_store,
        stored_object_id=scrape_result.get("stored_object_id"),
    )
    report = build_youtube_daily_summary_report(
        scrape_result=scrape_result,
        plan_result=plan_result,
        download_results=download_results,
        dag_id=dag_id,
        dag_run_id=dag_run_id,
        minimum_success_rate=minimum_success_rate,
        scrape_payload=scrape_payload,
        generated_at=generated_at,
    )
    try:
        render_dir = Path(output_dir or os.environ.get("EMPIRE_TEMP_DIR", "/tmp")) / "youtube" / "reports" / str(run_context.run_id)
        filename = f"youtube_daily_summary_{generated_at:%Y%m%dT%H%M%SZ}.pdf"
        render_result = render_youtube_daily_summary_pdf(
            report=report,
            output_dir=render_dir,
            generated_at=generated_at,
            filename=filename,
        )
        stored = object_store.put_file(
            run_context=run_context,
            storage_root="global",
            object_key=youtube_run_object_key(
                storage_key_prefix=os.environ.get("EMPIRE_STORAGE_KEY_YOUTUBE", DEFAULT_STORAGE_KEY),
                effective_date=run_context.effective_date,
                run_id=str(run_context.run_id),
                suffix="reports",
            ),
            filename=filename,
            source_path=render_result.primary_artifact.path,
            move=True,
            content_type="application/pdf",
            object_kind=YOUTUBE_DAILY_SUMMARY_PDF_OBJECT_KIND,
            logical_name=YOUTUBE_DAILY_SUMMARY_PDF_LOGICAL_NAME,
            expires_at=youtube_expires_at(),
            metadata={
                "report_name": report["report_name"],
                "report_id": render_result.report.report_id,
                "status": report["status"],
                "success_rate": report["summary"]["success_rate"],
            },
        )
        return YouTubeDailySummaryResult(report=report, run_context=run_context, stored_object=stored)
    except Exception as exc:
        run_service.fail_run(
            run_context.run_id,
            error_message=str(exc),
            summary={"failed_step": "youtube_daily_summary_pdf"},
        )
        raise


def _load_scrape_payload(
    *, object_store: ObjectStore,
    stored_object_id: object,
) -> dict[str, object]:
    if not stored_object_id:
        return {}
    payload = json.loads(object_store.get_bytes(UUID(str(stored_object_id))).decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _video_outcomes(
    *,
    scrape_payload: dict[str, object],
    download_results: list[dict[str, object]],
) -> list[dict[str, str]]:
    """Join download results to scraper provenance for the human report."""

    videos = scrape_payload.get("videos")
    video_list = videos if isinstance(videos, list) else []
    videos_by_id = {
        str(video.get("video_id")): video
        for video in video_list
        if isinstance(video, dict)
    }
    config = scrape_payload.get("config")
    section_names = (
        config.get("topic_section_names", {}) if isinstance(config, dict) else {}
    )
    outcomes: list[dict[str, str]] = []
    for result in download_results:
        video_id = str(result.get("video_id") or "")
        video = videos_by_id.get(video_id, {})
        title = str(result.get("title") or video.get("title") or video_id)
        diagnostics = result.get("access_diagnostics")
        diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
        outcomes.append(
            {
                "video_id": video_id,
                "title": title,
                "length": _format_duration(video),
                "status": str(result.get("status") or "unknown"),
                "selection_reason": _selection_reason(video, section_names),
                "deno": str(diagnostics.get("deno") or "not observed"),
                "po_token": str(diagnostics.get("po_token") or "not observed"),
            }
        )
    return outcomes


def _format_duration(video: dict[str, object]) -> str:
    content = video.get("content")
    seconds = content.get("duration_seconds") if isinstance(content, dict) else None
    if not isinstance(seconds, int) or seconds < 0:
        return "Unknown"
    hours, remaining = divmod(seconds, 3600)
    minutes, seconds = divmod(remaining, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def _selection_reason(video: dict[str, object], section_names: object) -> str:
    sources = {str(source) for source in video.get("discovery_sources", [])}
    reasons: list[str] = []
    if "channel_watch" in sources:
        channels = video.get("matched_channels")
        channel_list = channels if isinstance(channels, list) else []
        names = [
            str(channel.get("channel_name"))
            for channel in channel_list
            if isinstance(channel, dict)
            if channel.get("channel_name")
        ]
        reasons.append(
            "Followed channel: " + (", ".join(names) if names else "matched channel")
        )
    if "topic_search" in sources:
        sections = video.get("matched_sections")
        section_list = sections if isinstance(sections, list) else []
        names = [
            str(section_names.get(str(section), section))
            for section in section_list
        ] if isinstance(section_names, dict) else [str(section) for section in section_list]
        reasons.append(
            "Topic section: " + (", ".join(names) if names else "matched metadata")
        )
    return "; ".join(reasons) or "Scraper discovery"
