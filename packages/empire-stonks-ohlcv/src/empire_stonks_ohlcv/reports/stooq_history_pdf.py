"""Branded PDF renderer for the Stooq historical backfill report."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
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
    NextPageTemplate,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


STOOQ_HISTORY_PDF_REPORT_ID = "stonks.ohlcv.stooq-history-backfill-summary"
TITLE = "Stooq History Import"
SUBTITLE = "Historical OHLCV Backfill Summary Report"
HEADER_TEXT = "EMPIRE RESEARCH DIVISION"
FOOTER_TEXT = "PROPRIETARY / INTERNAL USE ONLY"
REPORT_TIMEZONE_ENV = "EMPIRE_REPORT_TIMEZONE"
DEFAULT_REPORT_TIMEZONE = "America/New_York"
SERIES_DISPLAY_LIMIT = 25


def render_stooq_history_pdf(
    *,
    report: dict[str, Any],
    output_dir: str | Path,
    filename: str = "report.pdf",
) -> RenderResult:
    """Render the schema-v2 Stooq history JSON model as a readable PDF."""

    generated_at = _parse_datetime(report.get("generated_at")) or datetime.now(UTC)
    metadata = ReportMetadata(
        report_id=STOOQ_HISTORY_PDF_REPORT_ID,
        title=TITLE,
        subtitle=SUBTITLE,
        as_of=_parse_date(report.get("effective_date")) or generated_at.date(),
        generated_at=generated_at,
        tags=("stonks", "ohlcv", "stooq", "historical", "backfill"),
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
    header_footer = HeaderFooterSpec(
        header_center_text=HEADER_TEXT,
        footer_text=FOOTER_TEXT,
    )
    templates = renderer.default_templates(header_footer)
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
    input_section = report.get("input") or {}
    scope = input_section.get("scope") or {}
    progress = report.get("progress") or {}
    parse = progress.get("parse") or {}
    write = progress.get("write") or {}
    coverage = report.get("coverage") or {}
    markets = report.get("markets") or []
    story: list[Any] = [
        section_heading("Executive Summary", styles=renderer.styles),
        paragraph(_executive_summary(report), styles=renderer.styles),
        Spacer(1, 6),
        _overview_table(report, renderer=renderer),
        spacer(12),
        section_heading("Run Facts", styles=renderer.styles),
        _table(
            [
                ["Fact", "Value"],
                ["Provider / source", _provider_source(report)],
                ["Run status", report.get("run_status") or "unknown"],
                ["Archive acquisition date", report.get("effective_date") or ""],
                ["Generated at", _format_datetime(generated_at)],
                ["Elapsed", _format_elapsed(progress.get("elapsed_seconds"))],
                ["Report schema", report.get("schema_version") or ""],
            ],
            renderer=renderer,
            col_widths=[170, 334],
        ),
        spacer(12),
        section_heading("Import Scope", styles=renderer.styles),
        _scope_table(scope, input_section=input_section, renderer=renderer),
        spacer(12),
        section_heading("Market Coverage", styles=renderer.styles),
        _market_coverage_table(markets, renderer=renderer),
        PageBreak(),
        section_heading("Processing Results", styles=renderer.styles),
        paragraph(
            "Parser counts describe the selected archive members. Database "
            "outcomes are cumulative across independently committed chunks.",
            styles=renderer.styles,
        ),
        _parse_table(parse, renderer=renderer),
        spacer(10),
        _write_table(write, renderer=renderer),
        spacer(12),
        section_heading("Provider-Series Coverage Sample", styles=renderer.styles),
        paragraph(_series_sample_note(coverage), styles=renderer.styles),
        _series_table(coverage, renderer=renderer),
        PageBreak(),
        section_heading("Stored Input and Lineage", styles=renderer.styles),
        paragraph(
            "The operator-supplied archive is retained through the normal raw "
            "object policy. Its checksum identifies the durable source snapshot.",
            styles=renderer.styles,
        ),
        _lineage_table(input_section, renderer=renderer),
        spacer(14),
        section_heading("Warnings and Failures", styles=renderer.styles),
        paragraph(_review_summary(report), styles=renderer.styles),
        *_review_sections(report, renderer=renderer),
        spacer(14),
        section_heading("Provider Value Semantics", styles=renderer.styles),
        paragraph(
            "These limitations are part of the source contract and should be "
            "considered before using the imported series for research.",
            styles=renderer.styles,
        ),
        _key_value_table(
            report.get("native_value_semantics") or {},
            renderer=renderer,
        ),
    ]
    return story


def _executive_summary(report: dict[str, Any]) -> str:
    outcome = escape(str(report.get("outcome") or "UNKNOWN"))
    status = escape(str(report.get("run_status") or "unknown"))
    coverage = report.get("coverage") or {}
    progress = report.get("progress") or {}
    parse = progress.get("parse") or {}
    write = progress.get("write") or {}
    bars = write.get("bar_counts") or {}
    return (
        f"The Stooq historical OHLCV backfill is <b>{status}</b> with outcome "
        f"<b>{outcome}</b>. It processed {_int(parse.get('files_completed')):,} "
        f"selected files and {_int(parse.get('accepted_records')):,} accepted "
        f"records across {_int(coverage.get('series_count')):,} provider series. "
        f"Database outcomes include {_int(bars.get('inserted')):,} inserted, "
        f"{_int(bars.get('updated')):,} updated, and "
        f"{_int(bars.get('unchanged')):,} unchanged bars."
    )


def _overview_table(report: dict[str, Any], *, renderer: PdfRenderer) -> Table:
    coverage = report.get("coverage") or {}
    progress = report.get("progress") or {}
    parse = progress.get("parse") or {}
    return _table(
        [
            ["Outcome", "Status", "Markets", "Series", "Bars", "Warnings", "Failures"],
            [
                report.get("outcome") or "UNKNOWN",
                report.get("run_status") or "unknown",
                len(coverage.get("markets") or []),
                _int(coverage.get("series_count")),
                _int(parse.get("accepted_records")),
                _int((report.get("warnings") or {}).get("total_count")),
                _int((report.get("hard_failures") or {}).get("total_count")),
            ],
        ],
        renderer=renderer,
        col_widths=[72, 68, 62, 72, 82, 76, 72],
    )


def _scope_table(
    scope: dict[str, Any],
    *,
    input_section: dict[str, Any],
    renderer: PdfRenderer,
) -> Table:
    tickers = scope.get("tickers") or []
    ticker_text = (
        "All discovered tickers"
        if not tickers
        else _bounded_join(tickers, limit=12)
    )
    return _table(
        [
            ["Scope", "Value"],
            ["Markets", _bounded_join(scope.get("markets") or [], limit=10)],
            ["Ticker filter", ticker_text],
            ["Ticker filter count", len(tickers)],
            ["Inclusive start date", scope.get("start_date") or "Unbounded"],
            ["Inclusive end date", scope.get("end_date") or "Unbounded"],
            ["Chunk maximum", _fmt_int(input_section.get("chunk_size"))],
            ["Manual acquisition", _yes_no(input_section.get("manual_acquisition"))],
        ],
        renderer=renderer,
        col_widths=[170, 334],
    )


def _market_coverage_table(
    markets: list[dict[str, Any]],
    *,
    renderer: PdfRenderer,
) -> Table:
    rows: list[list[Any]] = [
        ["Market", "Series", "Active", "Scoped Bars", "Persisted Bars", "Scoped Range"]
    ]
    for market in markets:
        coverage = market.get("coverage") or {}
        rows.append(
            [
                market.get("market") or "",
                _fmt_int(coverage.get("listing_count")),
                _fmt_int(coverage.get("active_listing_count")),
                _fmt_int(coverage.get("scoped_bar_count")),
                _fmt_int(coverage.get("persisted_bar_count")),
                _date_range(
                    coverage.get("first_scoped_trading_date"),
                    coverage.get("last_scoped_trading_date"),
                ),
            ]
        )
    return _table(
        rows,
        renderer=renderer,
        col_widths=[70, 58, 58, 80, 86, 152],
    )


def _parse_table(parse: dict[str, Any], *, renderer: PdfRenderer) -> Table:
    market_counts = parse.get("market_counts") or []
    rows: list[list[Any]] = [
        [
            "Market",
            "Files",
            "Input Rows",
            "Date Filtered",
            "Accepted",
            "Rejected",
            "Duplicates",
        ]
    ]
    if market_counts:
        for item in market_counts:
            rows.append(
                [
                    item.get("market") or "",
                    _fmt_int(item.get("files_completed")),
                    _fmt_int(item.get("input_rows")),
                    _fmt_int(item.get("date_filtered_rows")),
                    _fmt_int(item.get("accepted_records")),
                    _fmt_int(item.get("rejected_records")),
                    _fmt_int(item.get("duplicate_rows_collapsed")),
                ]
            )
    else:
        rows.append(
            [
                "Current total",
                _fmt_int(parse.get("files_completed")),
                _fmt_int(parse.get("input_rows")),
                _fmt_int(parse.get("date_filtered_rows")),
                _fmt_int(parse.get("accepted_records")),
                _fmt_int(parse.get("rejected_records")),
                _fmt_int(parse.get("duplicate_rows_collapsed")),
            ]
        )
    return _table(
        rows,
        renderer=renderer,
        col_widths=[70, 54, 76, 78, 74, 74, 78],
    )


def _write_table(write: dict[str, Any], *, renderer: PdfRenderer) -> Table:
    listings = write.get("listing_counts") or {}
    bars = write.get("bar_counts") or {}
    return _table(
        [
            ["Write Outcome", "Listings", "Daily Bars"],
            [
                "Inserted",
                _fmt_int(listings.get("inserted")),
                _fmt_int(bars.get("inserted")),
            ],
            [
                "Updated",
                _fmt_int(listings.get("updated")),
                _fmt_int(bars.get("updated")),
            ],
            [
                "Unchanged",
                _fmt_int(listings.get("unchanged")),
                _fmt_int(bars.get("unchanged")),
            ],
            ["Derived repaired", "-", _fmt_int(bars.get("derived_updated"))],
            ["Skipped inactive", "-", _fmt_int(write.get("skipped_inactive_bars"))],
            ["Chunks completed", "-", _fmt_int(write.get("chunks_completed"))],
            ["Chunks failed", "-", _fmt_int(write.get("chunks_failed"))],
            ["Last committed chunk", "-", _display(write.get("last_completed_chunk"))],
        ],
        renderer=renderer,
        col_widths=[220, 142, 142],
    )


def _series_sample_note(coverage: dict[str, Any]) -> str:
    samples = coverage.get("series_samples") or []
    shown = min(len(samples), SERIES_DISPLAY_LIMIT)
    total = _int(coverage.get("series_count"))
    return (
        f"Showing {shown:,} of {len(samples):,} JSON report samples across "
        f"{total:,} scoped provider series. The JSON report remains authoritative "
        "for the complete bounded sample."
    )


def _series_table(coverage: dict[str, Any], *, renderer: PdfRenderer) -> Table:
    rows: list[list[Any]] = [
        ["Market", "Ticker", "Status", "Scoped Bars", "Persisted Bars", "Scoped Range"]
    ]
    for item in (coverage.get("series_samples") or [])[:SERIES_DISPLAY_LIMIT]:
        rows.append(
            [
                item.get("market") or "",
                item.get("ticker") or "",
                item.get("status") or "",
                _fmt_int(item.get("scoped_bar_count")),
                _fmt_int(item.get("persisted_bar_count")),
                _date_range(
                    item.get("first_scoped_trading_date"),
                    item.get("last_scoped_trading_date"),
                ),
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "No samples", "-", "0", "0", "No data"])
    return _table(
        rows,
        renderer=renderer,
        col_widths=[62, 82, 62, 74, 82, 142],
    )


def _lineage_table(input_section: dict[str, Any], *, renderer: PdfRenderer) -> Table:
    archive = input_section.get("archive") or {}
    snapshot = input_section.get("source_snapshot") or {}
    return _table(
        [
            ["Lineage Fact", "Value"],
            ["Archive filename", archive.get("filename") or "Not available"],
            ["Archive bytes", _fmt_int(archive.get("size_bytes"))],
            ["Archive SHA-256", archive.get("checksum_sha256") or "Not available"],
            ["Raw object ID", archive.get("object_id") or "Not available"],
            [
                "Source snapshot ID",
                snapshot.get("source_snapshot_id") or "Not available",
            ],
            ["Snapshot inserted", _yes_no(snapshot.get("snapshot_inserted"))],
            ["Object link inserted", _yes_no(snapshot.get("object_link_inserted"))],
        ],
        renderer=renderer,
        col_widths=[150, 354],
    )


def _review_summary(report: dict[str, Any]) -> str:
    failures = _int((report.get("hard_failures") or {}).get("total_count"))
    warnings = _int((report.get("warnings") or {}).get("total_count"))
    if failures + warnings == 0:
        return "No warnings or hard failures were reported."
    return (
        f"Review {failures:,} hard failures and {warnings:,} warnings below. "
        "Samples remain bounded exactly as they are in the JSON report."
    )


def _review_sections(report: dict[str, Any], *, renderer: PdfRenderer) -> list[Any]:
    sections: list[Any] = []
    for title, section in (
        ("Hard Failures", report.get("hard_failures") or {}),
        ("Warnings", report.get("warnings") or {}),
    ):
        total = _int(section.get("total_count"))
        if not total:
            continue
        heading = Paragraph(escape(title), renderer.styles.subheading)
        heading.keepWithNext = 1
        sections.extend(
            [
                heading,
                _key_value_table(
                    {
                        key: value
                        for key, value in section.items()
                        if key != "samples"
                    },
                    renderer=renderer,
                ),
                _sample_table(section.get("samples") or [], renderer=renderer),
                spacer(8),
            ]
        )
    return sections


def _sample_table(samples: list[Any], *, renderer: PdfRenderer) -> Table:
    rows: list[list[Any]] = [["#", "Detail"]]
    for index, sample in enumerate(samples, start=1):
        detail = (
            json.dumps(sample, sort_keys=True)
            if isinstance(sample, (dict, list))
            else str(sample)
        )
        rows.append([index, detail])
    if len(rows) == 1:
        rows.append(["-", "No samples retained."])
    return _table(rows, renderer=renderer, col_widths=[30, 474])


def _key_value_table(values: dict[str, Any], *, renderer: PdfRenderer) -> Table:
    rows = [
        ["Property", "Value"],
        *[[_humanize(key), _display(value)] for key, value in values.items()],
    ]
    return _table(rows, renderer=renderer, col_widths=[180, 324])


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


def _provider_source(report: dict[str, Any]) -> str:
    return f"{report.get('provider_code') or ''} / {report.get('source_code') or ''}"


def _bounded_join(values: list[Any], *, limit: int) -> str:
    shown = [str(value) for value in values[:limit]]
    suffix = f" (+{len(values) - limit:,} more)" if len(values) > limit else ""
    return ", ".join(shown) + suffix


def _date_range(first: Any, last: Any) -> str:
    if first is None and last is None:
        return "No data"
    return f"{first or 'Unknown'} through {last or 'Unknown'}"


def _format_elapsed(value: Any) -> str:
    try:
        return f"{float(value):,.3f} seconds"
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
        return _yes_no(value)
    return str(value)


def _yes_no(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Not available"


def _humanize(value: str) -> str:
    text = value.replace("_", " ").strip()
    return text[:1].upper() + text[1:]
