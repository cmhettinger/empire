"""Branded PDF renderer for the YouTube daily acquisition summary."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
from reportlab.platypus import PageBreak, Paragraph, Table, TableStyle


REPORT_ID = "youtube.daily-acquisition-summary"
TITLE = "YouTube Daily Scrape"
SUBTITLE = "Jellyfin Acquisition Run Summary"
HEADER_TEXT = "EMPIRE RESEARCH DIVISION"
FOOTER_TEXT = "PROPRIETARY / INTERNAL USE ONLY"


def render_youtube_daily_summary_pdf(
    *,
    report: dict[str, Any],
    output_dir: str | Path,
    generated_at: datetime | None = None,
    filename: str | None = None,
) -> RenderResult:
    """Render a concise, human-readable YouTube acquisition report."""

    generated_at = generated_at or datetime.now(UTC)
    metadata = ReportMetadata(
        report_id=REPORT_ID,
        title=TITLE,
        subtitle=SUBTITLE,
        as_of=generated_at.date(),
        generated_at=generated_at,
        tags=("youtube", "jellyfin", "daily-acquisition"),
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
        *_body_story(report, renderer=renderer),
    ]
    return renderer.render(
        story,
        out_path=Path(output_dir) / (filename or _pdf_filename(generated_at)),
        header_footer=HeaderFooterSpec(
            header_center_text=HEADER_TEXT,
            footer_text=FOOTER_TEXT,
        ),
    )


def _body_story(report: dict[str, Any], *, renderer: PdfRenderer) -> list[Any]:
    styles = renderer.styles
    return [
        section_heading("Executive Summary", styles=styles),
        paragraph(_executive_summary(report), styles=styles),
        spacer(12),
        section_heading("Acquisition Results", styles=styles),
        simple_table(_summary_rows(report), theme=renderer.theme),
        spacer(12),
        section_heading("Run Facts", styles=styles),
        simple_table(_run_fact_rows(report), theme=renderer.theme),
        PageBreak(),
        section_heading("Download Exceptions", styles=styles),
        paragraph(
            "Entries below were not added to the Jellyfin media library. "
            "The per-video Empire run report contains the full technical error.",
            styles=styles,
        ),
        spacer(8),
        _failed_downloads_table(report, renderer=renderer),
    ]


def _executive_summary(report: dict[str, Any]) -> str:
    summary = report["summary"]
    return (
        f"The YouTube acquisition run completed with status <b>{escape(str(report['status']))}</b>. "
        f"It scraped {int(summary['scraped_video_count']):,} videos, planned "
        f"{int(summary['planned_download_count']):,} Jellyfin downloads, and completed "
        f"{int(summary['successful_download_count']):,} of {int(summary['download_total_count']):,} "
        f"download attempts ({float(summary['success_rate']):.1%})."
    )


def _summary_rows(report: dict[str, Any]) -> list[list[str]]:
    summary = report["summary"]
    return [
        ["Status", "Completed", "Failed", "Success Rate", "Required Rate"],
        [
            str(report["status"]),
            str(summary["successful_download_count"]),
            str(summary["failed_download_count"]),
            f"{float(summary['success_rate']):.1%}",
            f"{float(summary['minimum_success_rate']):.1%}",
        ],
    ]


def _run_fact_rows(report: dict[str, Any]) -> list[list[str]]:
    summary = report["summary"]
    context = report["run_context"]
    return [
        ["Fact", "Value"],
        ["Airflow DAG", str(context.get("dag_id") or "")],
        ["Airflow Run", str(context.get("run_id") or "")],
        ["Scrape Run", str(context.get("scrape_run_id") or "")],
        ["Plan Run", str(context.get("plan_run_id") or "")],
        ["Scraped Videos", str(summary["scraped_video_count"])],
        ["Planned Downloads", str(summary["planned_download_count"])],
        ["Sidecars Written / Reused", f"{summary['sidecar_object_count']} / {summary['skipped_sidecar_count']}"],
        ["Downloads Written / Already Present", f"{summary['downloaded_count']} / {summary['skipped_download_count']}"],
    ]


def _failed_downloads_table(report: dict[str, Any], *, renderer: PdfRenderer):
    failures = report.get("failed_downloads", [])
    if not failures:
        return simple_table(
            [["Status", "Detail"], ["PASS", "All planned downloads completed or were already present."]],
            theme=renderer.theme,
        )
    styles = renderer.styles
    rows: list[list[Any]] = [["Video ID", "Status", "Error"]]
    for failure in failures:
        rows.append(
            [
                Paragraph(escape(str(failure.get("video_id") or "")), styles.body),
                Paragraph(escape(str(failure.get("status") or "failed")), styles.body),
                Paragraph(escape(str(failure.get("error_message") or "No error detail recorded.")), styles.body),
            ]
        )
    table = Table(rows, colWidths=[92, 58, 354], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), renderer.theme.primary),
                ("TEXTCOLOR", (0, 0), (-1, 0), renderer.theme.white),
                ("FONTNAME", (0, 0), (-1, 0), renderer.theme.body_bold_font),
                ("GRID", (0, 0), (-1, -1), 0.25, renderer.theme.light_grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _pdf_filename(generated_at: datetime) -> str:
    return f"youtube_daily_summary_{generated_at:%Y%m%dT%H%M%SZ}.pdf"
