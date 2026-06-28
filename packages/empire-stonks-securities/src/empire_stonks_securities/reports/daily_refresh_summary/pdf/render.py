"""PDF renderer for the stonks securities daily refresh summary."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle


DAILY_SUMMARY_PDF_REPORT_ID = "stonks.securities.daily-refresh-summary"
DAILY_SUMMARY_PDF_LOGICAL_NAME = "stonks_securities_daily_summary_pdf"
DAILY_SUMMARY_PDF_OBJECT_KIND = "stonks_securities_daily_summary_pdf"
TITLE = "SEC Daily Scrape"
SUBTITLE = "Stonks Securities Summary Report"
HEADER_TEXT = "EMPIRE RESEARCH DIVISION"
FOOTER_TEXT = "PROPRIETARY / INTERNAL USE ONLY"
REPORT_TIMEZONE_ENV = "EMPIRE_REPORT_TIMEZONE"
DEFAULT_REPORT_TIMEZONE = "America/New_York"


def render_daily_refresh_summary_pdf(
    *,
    report: dict[str, Any],
    output_dir: str | Path,
    generated_at: datetime | None = None,
    filename: str | None = None,
) -> RenderResult:
    """Render the human-friendly daily refresh summary PDF."""

    generated_at = generated_at or _parse_datetime(report.get("generated_at")) or datetime.now(UTC)
    report_timezone = _report_timezone()
    display_generated_at = generated_at.astimezone(report_timezone)
    metadata = ReportMetadata(
        report_id=DAILY_SUMMARY_PDF_REPORT_ID,
        title=TITLE,
        subtitle=SUBTITLE,
        as_of=display_generated_at.date(),
        generated_at=generated_at,
        tags=("stonks", "securities", "daily-refresh"),
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
        *_body_story(
            report=report,
            generated_at=generated_at,
            report_timezone=report_timezone,
            renderer=renderer,
        ),
    ]
    out_path = Path(output_dir) / (filename or _pdf_filename(generated_at))
    return renderer.render(
        story,
        out_path=out_path,
        header_footer=HeaderFooterSpec(
            header_center_text=HEADER_TEXT,
            footer_text=FOOTER_TEXT,
        ),
    )


def _body_story(
    *,
    report: dict[str, Any],
    generated_at: datetime,
    report_timezone: ZoneInfo,
    renderer: PdfRenderer,
) -> list[Any]:
    styles = renderer.styles
    story: list[Any] = [
        section_heading("Executive Summary", styles=styles),
        paragraph(_executive_summary(report), styles=styles),
        Spacer(1, 6),
        _summary_table(report, renderer=renderer),
        spacer(12),
        section_heading("Run Facts", styles=styles),
        _run_facts_table(
            report,
            generated_at=generated_at,
            report_timezone=report_timezone,
            renderer=renderer,
        ),
        spacer(12),
        section_heading("Canonical Market Snapshot", styles=styles),
        paragraph(
            "Counts reflect the current canonical state anchored on active listings.",
            styles=styles,
        ),
        _market_table(report, renderer=renderer),
        PageBreak(),
        section_heading("REVIEW ITEMS", styles=styles),
        paragraph(
            "Rows below come from the daily summary and linked verify, validation, and conflict reports. Use this page to decide whether deeper report review is needed.",
            styles=styles,
        ),
        _review_items_table(report, renderer=renderer),
    ]
    return story


def _executive_summary(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    status = summary.get("status", "UNKNOWN")
    warnings_total = int(summary.get("warnings_total") or 0)
    failures_total = int(summary.get("failures_total") or 0)
    inputs_seen = int(summary.get("inputs_seen") or 0)
    inputs_missing = int(summary.get("inputs_missing") or 0)
    return (
        f"The daily securities refresh completed with status <b>{status}</b>. "
        f"It saw {inputs_seen} required input files with {inputs_missing} missing, "
        f"and recorded {warnings_total} warnings and {failures_total} failures."
    )


def _summary_table(report: dict[str, Any], *, renderer: PdfRenderer):
    summary = report.get("summary", {})
    rows = [
        ["Status", "Warnings", "Failures", "Validation", "Conflicts", "Verify"],
        [
            summary.get("status", "UNKNOWN"),
            _fmt_int(summary.get("warnings_total")),
            _fmt_int(summary.get("failures_total")),
            summary.get("validation_status", "UNKNOWN"),
            summary.get("conflict_status", "UNKNOWN"),
            summary.get("verify_status", "UNKNOWN"),
        ],
    ]
    return simple_table(rows, theme=renderer.theme)


def _run_facts_table(
    report: dict[str, Any],
    *,
    generated_at: datetime,
    report_timezone: ZoneInfo,
    renderer: PdfRenderer,
):
    rows = _run_facts_rows(
        report,
        generated_at=generated_at,
        report_timezone=report_timezone,
    )
    return simple_table(rows, theme=renderer.theme)


def _run_facts_rows(
    report: dict[str, Any],
    *,
    generated_at: datetime,
    report_timezone: ZoneInfo,
) -> list[list[str]]:
    summary = report.get("summary", {})
    run_context = report.get("run_context", {})
    return [
        ["Fact", "Value"],
        ["Generated At", _format_report_datetime(generated_at, report_timezone=report_timezone)],
        *_sec_file_date_rows(report, report_timezone=report_timezone),
        ["Source Run ID", run_context.get("source_run_id") or ""],
        ["Airflow Run ID", run_context.get("run_id") or ""],
        ["Inputs Seen", _fmt_int(summary.get("inputs_seen"))],
        ["Inputs Unchanged", _fmt_int(summary.get("inputs_unchanged"))],
        ["Observations Created", _fmt_int(summary.get("observations_created"))],
        [
            "Issuers Created / Updated",
            f"{_fmt_int(summary.get('issuers_created'))} / {_fmt_int(summary.get('issuers_updated'))}",
        ],
        [
            "Securities Created / Updated",
            f"{_fmt_int(summary.get('securities_created'))} / {_fmt_int(summary.get('securities_updated'))}",
        ],
        [
            "Listings Created / Updated",
            f"{_fmt_int(summary.get('listings_created'))} / {_fmt_int(summary.get('listings_updated'))}",
        ],
    ]


def _sec_file_date_rows(report: dict[str, Any], *, report_timezone: ZoneInfo) -> list[list[str]]:
    sources = report.get("input_freshness", {}).get("sources", {})
    rows: list[list[str]] = []
    for source_code in ("sec_company_tickers_exchange", "sec_company_tickers"):
        source = sources.get(source_code)
        if not isinstance(source, dict) or not source.get("present"):
            continue
        file_date = source.get("last_modified") or source.get("downloaded_at") or ""
        file_datetime = _parse_http_datetime(file_date) or _parse_datetime(file_date)
        display_file_date = (
            _format_report_datetime(file_datetime, report_timezone=report_timezone)
            if file_datetime is not None
            else str(file_date)
        )
        age_hours = _source_age_hours(report, source, file_date=file_date)
        age_text = f" ({age_hours:.1f} hours old)" if age_hours is not None else ""
        rows.append(
            [
                f"SEC File Date - {_source_label(source_code)}",
                f"{display_file_date}{age_text}",
            ]
        )
    return rows


def _review_items_table(report: dict[str, Any], *, renderer: PdfRenderer):
    items = report.get("human_review_items", [])
    if not items:
        items = [
            {
                "source_report": "daily_summary",
                "severity": "PASS",
                "code": "no_review_items",
                "count": None,
                "message": "No warnings, failures, or linked-report review items were reported.",
                "recommended_action": "",
            }
        ]
    rows = [["Source", "Severity", "Item", "Count", "Review Detail"]]
    for item in items:
        detail = str(item.get("message") or "")
        action = item.get("recommended_action")
        if action:
            detail = f"{detail} Action: {action}"
        rows.append(
            [
                str(item.get("source_report") or ""),
                str(item.get("severity") or ""),
                _humanize_code(item.get("code")),
                "" if item.get("count") is None else _fmt_int(item.get("count")),
                detail,
            ]
        )
    return _wrapped_table(rows, renderer=renderer, col_widths=[60, 48, 112, 36, 248])


def _market_table(report: dict[str, Any], *, renderer: PdfRenderer):
    rows = _market_table_rows(report)
    table = simple_table(rows, theme=renderer.theme)
    total_row_index = len(rows) - 1
    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, total_row_index),
                    (-1, total_row_index),
                    renderer.theme.light_grey,
                ),
                (
                    "FONTNAME",
                    (0, total_row_index),
                    (-1, total_row_index),
                    renderer.theme.body_semibold_font,
                ),
                (
                    "LINEABOVE",
                    (0, total_row_index),
                    (-1, total_row_index),
                    0.5,
                    renderer.theme.primary,
                ),
                (
                    "LINEBELOW",
                    (0, total_row_index),
                    (-1, total_row_index),
                    0.5,
                    renderer.theme.primary,
                ),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ]
        )
    )
    return table


def _market_table_rows(report: dict[str, Any]) -> list[list[str]]:
    snapshot = report.get("market_snapshot", {})
    rows = [["Market", "Issuers", "Securities", "Active Listings"]]
    issuers_total = 0
    securities_total = 0
    listings_total = 0
    for market in snapshot.get("markets", []):
        name = market.get("exchange_code") or "UNKNOWN"
        if market.get("exchange_code") == "OTHER":
            name = f"Other ({_fmt_int(market.get('market_count'))} markets)"
        issuers_total += _int_value(market.get("issuers_total"))
        securities_total += _int_value(market.get("securities_total"))
        listings_total += _int_value(market.get("listings_total"))
        rows.append(
            [
                name,
                _fmt_int(market.get("issuers_total")),
                _fmt_int(market.get("securities_total")),
                _fmt_int(market.get("listings_total")),
            ]
        )
    if len(rows) == 1:
        rows.append(["No represented markets", "0", "0", "0"])
    rows.append(
        [
            "Total",
            _fmt_int(issuers_total),
            _fmt_int(securities_total),
            _fmt_int(listings_total),
        ]
    )
    return rows


def _wrapped_table(rows: list[list[str]], *, renderer: PdfRenderer, col_widths: list[float]) -> Table:
    styles = renderer.styles
    body = styles.small
    data = [
        [
            str(cell) if row_index == 0 else Paragraph(str(cell), body)
            for cell in row
        ]
        for row_index, row in enumerate(rows)
    ]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), renderer.theme.primary),
                ("TEXTCOLOR", (0, 0), (-1, 0), renderer.theme.white),
                ("FONTNAME", (0, 0), (-1, 0), renderer.theme.body_semibold_font),
                ("FONTNAME", (0, 1), (-1, -1), renderer.theme.body_font),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.25, renderer.theme.light_grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [renderer.theme.white, "#F7F7F7"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _pdf_filename(generated_at: datetime) -> str:
    return f"stonks_securities_daily_summary_{generated_at:%Y%m%dT%H%M%SZ}.pdf"


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "0"


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _report_timezone() -> ZoneInfo:
    timezone_name = os.environ.get(REPORT_TIMEZONE_ENV) or DEFAULT_REPORT_TIMEZONE
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_REPORT_TIMEZONE)


def _format_report_datetime(value: datetime, *, report_timezone: ZoneInfo) -> str:
    return value.astimezone(report_timezone).strftime("%Y-%m-%d %H:%M:%S %Z")


def _source_label(source_code: str) -> str:
    return {
        "sec_company_tickers_exchange": "Exchange",
        "sec_company_tickers": "Company Tickers",
    }.get(source_code, source_code)


def _humanize_code(value: Any) -> str:
    text = str(value or "review_item").replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _source_age_hours(report: dict[str, Any], source: dict[str, Any], *, file_date: Any) -> float | None:
    generated_at = _parse_datetime(report.get("generated_at"))
    file_datetime = _parse_http_datetime(file_date) or _parse_datetime(file_date)
    if generated_at is not None and file_datetime is not None:
        return max(0.0, (generated_at - file_datetime).total_seconds() / 3600.0)
    age_hours = source.get("age_hours")
    if age_hours is None:
        return None
    try:
        return float(age_hours)
    except (TypeError, ValueError):
        return None


def _parse_http_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
