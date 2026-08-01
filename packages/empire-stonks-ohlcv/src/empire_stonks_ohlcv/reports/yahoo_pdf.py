"""Branded PDF renderer for Yahoo backfill and daily health reports."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping
from xml.sax.saxutils import escape
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
from reportlab.platypus import (
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    Paragraph,
    Table,
    TableStyle,
)


YAHOO_BACKFILL_PDF_REPORT_ID = "stonks.ohlcv.yahoo-backfill-summary"
YAHOO_DAILY_PDF_REPORT_ID = "stonks.ohlcv.yahoo-daily-health"
YAHOO_BACKFILL_REPORT_TYPE = "yahoo_historical_backfill"
YAHOO_DAILY_REPORT_TYPE = "yahoo_daily_health"
HEADER_TEXT = "EMPIRE RESEARCH DIVISION"
FOOTER_TEXT = "PROPRIETARY / INTERNAL USE ONLY"
REPORT_TIMEZONE_ENV = "EMPIRE_REPORT_TIMEZONE"
DEFAULT_REPORT_TIMEZONE = "America/New_York"
LISTING_DISPLAY_LIMIT = 24
ISSUE_DISPLAY_LIMIT = 10


def render_yahoo_pdf(
    *,
    report: dict[str, Any],
    output_dir: str | Path,
    filename: str = "report.pdf",
) -> RenderResult:
    """Render one schema-v2 Yahoo JSON report as a professional PDF."""

    report_type = report.get("report_type")
    title, subtitle, report_id, tags = _identity(report_type)
    generated_at = _parse_datetime(report.get("generated_at")) or datetime.now(UTC)
    metadata = ReportMetadata(
        report_id=report_id,
        title=title,
        subtitle=subtitle,
        as_of=_parse_date(report.get("effective_date")) or generated_at.date(),
        generated_at=generated_at,
        tags=tags,
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
        NextPageTemplate("letter_body"),
        PageBreak(),
        *_body_story(report, generated_at=generated_at, renderer=renderer),
    ]
    templates = renderer.default_templates(
        HeaderFooterSpec(
            header_center_text=HEADER_TEXT,
            footer_text=FOOTER_TEXT,
        )
    )
    templates.get("letter_title").autoNextPageTemplate = "letter_body"
    templates.get("letter_body").autoNextPageTemplate = "letter_body"
    return renderer.render(
        story,
        out_path=Path(output_dir) / filename,
        templates=templates,
    )


def _body_story(
    report: dict[str, Any],
    *,
    generated_at: datetime,
    renderer: PdfRenderer,
) -> list[Any]:
    story: list[Any] = [
        section_heading("Executive Summary", styles=renderer.styles),
        paragraph(_executive_summary(report), styles=renderer.styles),
        spacer(8),
        _overview_table(report, renderer=renderer),
        spacer(12),
        section_heading("Run Facts", styles=renderer.styles),
        _table(
            [
                ["Fact", "Value"],
                ["Provider / source", _provider_source(report)],
                ["Workflow", _display(report.get("workflow"))],
                ["Effective date", _display(report.get("effective_date"))],
                ["Generated at", _format_datetime(generated_at)],
                ["Core run ID", _display(report.get("run_id"))],
                ["Report schema", _display(report.get("schema_version"))],
            ],
            renderer=renderer,
            col_widths=[150, 354],
        ),
        spacer(12),
        section_heading("Run Scope", styles=renderer.styles),
        _scope_table(report, renderer=renderer),
        spacer(12),
        section_heading("Acquisition and Persistence", styles=renderer.styles),
        paragraph(
            "Each row separates provider acquisition from parsing and durable "
            "database outcomes. Reconciliation is reported independently from "
            "new-session ingestion.",
            styles=renderer.styles,
        ),
        _phase_table(report, renderer=renderer),
        PageBreak(),
        section_heading("Provider-Series Coverage", styles=renderer.styles),
        paragraph(_coverage_note(report), styles=renderer.styles),
        _coverage_table(report, renderer=renderer),
        spacer(14),
        section_heading("Health and Review Items", styles=renderer.styles),
        paragraph(_health_summary(report), styles=renderer.styles),
        _health_table(report, renderer=renderer),
        *_health_samples(report, renderer=renderer),
        KeepTogether(
            [
                spacer(14),
                section_heading(
                    "Provider Value Semantics",
                    styles=renderer.styles,
                ),
                paragraph(
                    "These source-native rules are material to downstream "
                    "research. The JSON report remains authoritative for "
                    "complete machine-readable details and bounded evidence "
                    "samples.",
                    styles=renderer.styles,
                ),
                _key_value_table(
                    report.get("native_value_semantics") or {},
                    renderer=renderer,
                ),
            ]
        ),
    ]
    return story


def _executive_summary(report: Mapping[str, Any]) -> str:
    outcome = escape(str(report.get("outcome") or "UNKNOWN"))
    report_type = report.get("report_type")
    phases = report.get("phase_results") or []
    bars = _combined_bar_counts(phases)
    requests = sum(_int(item.get("request_count")) for item in phases)
    selected = _selected_listing_count(report)
    warnings = _int((report.get("health") or {}).get("warning_count"))
    workflow = (
        "historical backfill"
        if report_type == YAHOO_BACKFILL_REPORT_TYPE
        else "daily ingestion and reconciliation"
    )
    return (
        f"The Yahoo {workflow} completed with outcome <b>{outcome}</b>. "
        f"It evaluated {selected:,} provider listings through {requests:,} "
        f"bounded requests. Database outcomes include "
        f"{bars['inserted']:,} inserted, {bars['updated']:,} updated, and "
        f"{bars['unchanged']:,} unchanged bars. The health model recorded "
        f"{warnings:,} warning conditions."
    )


def _overview_table(report: Mapping[str, Any], *, renderer: PdfRenderer) -> Table:
    phases = report.get("phase_results") or []
    bars = _combined_bar_counts(phases)
    requests = sum(_int(item.get("request_count")) for item in phases)
    failures = sum(
        _int((item.get("acquisition") or {}).get("failed"))
        + _int((item.get("import") or {}).get("failed_chunks"))
        + _int(item.get("parse_failed_count"))
        for item in phases
    )
    return _table(
        [
            [
                "Outcome",
                "Listings",
                "Requests",
                "Inserted",
                "Updated",
                "Unchanged",
                "Failures",
            ],
            [
                report.get("outcome") or "UNKNOWN",
                _selected_listing_count(report),
                requests,
                bars["inserted"],
                bars["updated"],
                bars["unchanged"],
                failures,
            ],
        ],
        renderer=renderer,
        col_widths=[72, 68, 68, 72, 68, 82, 74],
    )


def _scope_table(report: Mapping[str, Any], *, renderer: PdfRenderer) -> Table:
    scope = dict(report.get("scope") or {})
    tickers = scope.pop("tickers", None)
    rows: list[list[Any]] = [["Scope", "Value"]]
    for key, value in scope.items():
        rows.append([_humanize(key), _display(value)])
    if tickers is not None:
        rows.append(
            [
                "Ticker filter",
                "All active Yahoo listings"
                if not tickers
                else _bounded_join(tickers, limit=18),
            ]
        )
    if "enumerated_listing_count" in report:
        rows.append(
            ["Enumerated listings", _fmt_int(report["enumerated_listing_count"])]
        )
    if "selected_listing_count" in report:
        rows.append(["Selected listings", _fmt_int(report["selected_listing_count"])])
    return _table(rows, renderer=renderer, col_widths=[170, 334])


def _phase_table(report: Mapping[str, Any], *, renderer: PdfRenderer) -> Table:
    rows: list[list[Any]] = [
        [
            "Phase",
            "Requests",
            "Stored",
            "Missing",
            "Failed",
            "Parse Failed",
            "Imported",
            "Bars I/U/N",
        ]
    ]
    for phase in report.get("phase_results") or []:
        acquisition = phase.get("acquisition") or {}
        imported = phase.get("import") or {}
        bars = imported.get("bar_counts") or {}
        rows.append(
            [
                _humanize(str(phase.get("phase") or "unknown")),
                _fmt_int(phase.get("request_count")),
                _fmt_int(acquisition.get("stored")),
                _fmt_int(acquisition.get("missing")),
                _fmt_int(acquisition.get("failed")),
                _fmt_int(phase.get("parse_failed_count")),
                _fmt_int(imported.get("imported_chunks")),
                "/".join(
                    _fmt_int(bars.get(key))
                    for key in ("inserted", "updated", "unchanged")
                ),
            ]
        )
    if len(rows) == 1:
        rows.append(["No phases", "0", "0", "0", "0", "0", "0", "0/0/0"])
    return _table(
        rows,
        renderer=renderer,
        col_widths=[92, 55, 54, 55, 52, 66, 60, 70],
    )


def _coverage_note(report: Mapping[str, Any]) -> str:
    coverage = report.get("coverage") or {}
    listings = coverage.get("listings") or []
    shown = min(len(listings), LISTING_DISPLAY_LIMIT)
    return (
        f"Showing {shown:,} of {len(listings):,} listing rows. The PDF is "
        "intentionally bounded for readability; report.json retains the full "
        "coverage model."
    )


def _coverage_table(report: Mapping[str, Any], *, renderer: PdfRenderer) -> Table:
    coverage = report.get("coverage") or {}
    listings = (coverage.get("listings") or [])[:LISTING_DISPLAY_LIMIT]
    if report.get("report_type") == YAHOO_BACKFILL_REPORT_TYPE:
        rows: list[list[Any]] = [
            ["Ticker", "Scoped Bars", "First Date", "Last Date"]
        ]
        rows.extend(
            [
                item.get("ticker") or "",
                _fmt_int(item.get("scoped_bar_count")),
                _display(item.get("first_scoped_trading_date")),
                _display(item.get("last_scoped_trading_date")),
            ]
            for item in listings
        )
        if len(rows) == 1:
            rows.append(["No listings", "0", "Not available", "Not available"])
        return _table(
            rows,
            renderer=renderer,
            col_widths=[120, 110, 137, 137],
        )

    rows = [
        [
            "Ticker",
            "Basis",
            "Eligible",
            "Stored",
            "Missing",
            "Coverage",
            "Latest Stored",
        ]
    ]
    rows.extend(
        [
            item.get("ticker") or "",
            _humanize(str(item.get("coverage_basis") or "")),
            _fmt_int(item.get("eligible_session_count")),
            _fmt_int(item.get("stored_eligible_session_count")),
            _fmt_int(item.get("missing_eligible_session_count")),
            _percent(item.get("coverage_percent")),
            _display(item.get("latest_stored_session")),
        ]
        for item in listings
    )
    if len(rows) == 1:
        rows.append(["No listings", "-", "0", "0", "0", "-", "-"])
    return _table(
        rows,
        renderer=renderer,
        col_widths=[70, 100, 58, 56, 56, 64, 100],
    )


def _health_summary(report: Mapping[str, Any]) -> str:
    health = report.get("health") or {}
    warnings = _int(health.get("warning_count"))
    if not warnings:
        return "No warning conditions were reported."
    return (
        f"The report contains {warnings:,} warning conditions. Bounded samples "
        "are displayed below; use report.json for the complete retained evidence."
    )


def _health_table(report: Mapping[str, Any], *, renderer: PdfRenderer) -> Table:
    health = report.get("health") or {}
    coverage = report.get("coverage") or {}
    return _table(
        [
            ["Health Metric", "Count / Value"],
            ["Warning conditions", _fmt_int(health.get("warning_count"))],
            ["Stale listings", _fmt_int(health.get("stale_listing_count"))],
            [
                "Calendar policy errors",
                _fmt_int(health.get("calendar_policy_error_count")),
            ],
            [
                "Missing eligible sessions",
                _fmt_int(coverage.get("missing_eligible_session_count")),
            ],
            [
                "Unresolved observed polls",
                _fmt_int(coverage.get("unresolved_observed_poll_count")),
            ],
            ["Authoritative coverage", _percent(coverage.get("coverage_percent"))],
        ],
        renderer=renderer,
        col_widths=[270, 234],
    )


def _health_samples(report: Mapping[str, Any], *, renderer: PdfRenderer) -> list[Any]:
    health = report.get("health") or {}
    story: list[Any] = []
    for title, key in (
        ("Stale Listing Samples", "stale_listings"),
        ("Calendar Policy Error Samples", "calendar_policy_errors"),
    ):
        section = health.get(key) or {}
        samples = (section.get("samples") or [])[:ISSUE_DISPLAY_LIMIT]
        if not samples:
            continue
        heading = Paragraph(escape(title), renderer.styles.subheading)
        heading.keepWithNext = 1
        story.extend(
            [
                spacer(10),
                heading,
                _sample_table(samples, renderer=renderer),
            ]
        )
    return story


def _sample_table(samples: list[Any], *, renderer: PdfRenderer) -> Table:
    rows: list[list[Any]] = [["#", "Detail"]]
    for index, sample in enumerate(samples, start=1):
        detail = json.dumps(sample, sort_keys=True, separators=(",", ":"))
        if len(detail) > 900:
            detail = detail[:897] + "..."
        rows.append([index, detail])
    return _table(rows, renderer=renderer, col_widths=[30, 474])


def _key_value_table(values: Mapping[str, Any], *, renderer: PdfRenderer) -> Table:
    rows = [
        ["Property", "Value"],
        *[[_humanize(str(key)), _display(value)] for key, value in values.items()],
    ]
    return _table(rows, renderer=renderer, col_widths=[190, 314])


def _table(
    rows: list[list[Any]],
    *,
    renderer: PdfRenderer,
    col_widths: list[float],
) -> Table:
    body_style = renderer.styles.small
    data = [
        [
            str(cell) if row_index == 0 else Paragraph(escape(str(cell)), body_style)
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


def _identity(value: Any) -> tuple[str, str, str, tuple[str, ...]]:
    if value == YAHOO_BACKFILL_REPORT_TYPE:
        return (
            "Yahoo OHLCV Backfill",
            "Historical Provider-Native Import Summary Report",
            YAHOO_BACKFILL_PDF_REPORT_ID,
            ("stonks", "ohlcv", "yahoo", "historical", "backfill"),
        )
    if value == YAHOO_DAILY_REPORT_TYPE:
        return (
            "Yahoo Daily OHLCV",
            "Session Coverage and Reconciliation Health Report",
            YAHOO_DAILY_PDF_REPORT_ID,
            ("stonks", "ohlcv", "yahoo", "daily", "health"),
        )
    raise ValueError("Yahoo PDF report_type is invalid.")


def _combined_bar_counts(phases: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        key: sum(
            _int(((phase.get("import") or {}).get("bar_counts") or {}).get(key))
            for phase in phases
        )
        for key in ("inserted", "updated", "unchanged", "derived_updated")
    }


def _selected_listing_count(report: Mapping[str, Any]) -> int:
    if "selected_listing_count" in report:
        return _int(report.get("selected_listing_count"))
    return _int((report.get("scope") or {}).get("selected_listing_count"))


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _format_datetime(value: datetime) -> str:
    timezone_name = os.environ.get(REPORT_TIMEZONE_ENV) or DEFAULT_REPORT_TIMEZONE
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo(DEFAULT_REPORT_TIMEZONE)
    return value.astimezone(timezone).strftime("%Y-%m-%d %H:%M:%S %Z")


def _provider_source(report: Mapping[str, Any]) -> str:
    return f"{report.get('provider_code') or ''} / {report.get('source_code') or ''}"


def _bounded_join(values: list[Any], *, limit: int) -> str:
    shown = [str(value) for value in values[:limit]]
    suffix = f" (+{len(values) - limit:,} more)" if len(values) > limit else ""
    return ", ".join(shown) + suffix


def _percent(value: Any) -> str:
    if value is None:
        return "Not applicable"
    try:
        return f"{float(value):,.2f}%"
    except (TypeError, ValueError):
        return "Not available"


def _fmt_int(value: Any) -> str:
    return f"{_int(value):,}"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _display(value: Any) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        text = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return text if len(text) <= 900 else text[:897] + "..."
    return str(value)


def _humanize(value: str) -> str:
    text = value.replace("_", " ").strip()
    return text[:1].upper() + text[1:]
