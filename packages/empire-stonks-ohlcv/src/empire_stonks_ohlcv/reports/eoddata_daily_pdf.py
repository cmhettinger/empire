"""Branded PDF renderer for the EODData daily OHLCV report."""

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


EODDATA_DAILY_PDF_REPORT_ID = "stonks.ohlcv.eoddata-daily-summary"
TITLE = "EODData Daily Scrape"
SUBTITLE = "Stonks OHLCV Summary Report"
HEADER_TEXT = "EMPIRE RESEARCH DIVISION"
FOOTER_TEXT = "PROPRIETARY / INTERNAL USE ONLY"
REPORT_TIMEZONE_ENV = "EMPIRE_REPORT_TIMEZONE"
DEFAULT_REPORT_TIMEZONE = "America/New_York"


def render_eoddata_daily_pdf(
    *,
    report: dict[str, Any],
    output_dir: str | Path,
    filename: str = "report.pdf",
) -> RenderResult:
    """Render the schema-v2 EODData JSON model as a human-readable PDF."""

    generated_at = _parse_datetime(report.get("generated_at")) or datetime.now(UTC)
    metadata = ReportMetadata(
        report_id=EODDATA_DAILY_PDF_REPORT_ID,
        title=TITLE,
        subtitle=SUBTITLE,
        as_of=_parse_date(report.get("effective_date")) or generated_at.date(),
        generated_at=generated_at,
        tags=("stonks", "ohlcv", "eoddata", "daily"),
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
                ["Provider", report.get("provider_code") or ""],
                ["Effective Date", report.get("effective_date") or ""],
                ["Generated At", _format_datetime(generated_at)],
                ["Report Schema", report.get("schema_version") or ""],
            ],
            renderer=renderer,
            col_widths=[150, 354],
        ),
        spacer(12),
        section_heading("Market Overview", styles=renderer.styles),
        paragraph(
            "Coverage and freshness reflect active EODData listings at the report effective date.",
            styles=renderer.styles,
        ),
        _market_overview_table(markets, renderer=renderer),
        PageBreak(),
        section_heading("Market Detail", styles=renderer.styles),
    ]
    for index, market in enumerate(markets):
        story.extend(_market_detail(market, renderer=renderer))
        if index < len(markets) - 1:
            story.append(PageBreak())
    story.extend(
        [
            PageBreak(),
            section_heading("Sources and Stored Inputs", styles=renderer.styles),
            paragraph(
                "Each source partition below is retained in Core object storage "
                "for run lineage and replay.",
                styles=renderer.styles,
            ),
            _sources_table(report.get("sources") or [], renderer=renderer),
            spacer(14),
            section_heading("Inactive Series", styles=renderer.styles),
            _inactive_table(report.get("inactive_series") or {}, renderer=renderer),
            PageBreak(),
            section_heading("Warnings, Rejections, and Errors", styles=renderer.styles),
            paragraph(_review_summary(report), styles=renderer.styles),
            *_review_sections(report, renderer=renderer),
            spacer(14),
            section_heading("Provider Value Semantics", styles=renderer.styles),
            _key_value_table(
                report.get("native_value_semantics") or {}, renderer=renderer
            ),
        ]
    )
    return story


def _executive_summary(report: dict[str, Any]) -> str:
    outcome = escape(str(report.get("outcome") or "UNKNOWN"))
    markets = report.get("markets") or []
    warnings = _int((report.get("warnings") or {}).get("total_count"))
    rejections = _int((report.get("row_rejections") or {}).get("rejected_records"))
    failures = _int((report.get("hard_failures") or {}).get("total_count"))
    return (
        f"The EODData daily OHLCV run completed with outcome <b>{outcome}</b> across "
        f"{len(markets)} markets. It recorded {warnings:,} import warnings, "
        f"{rejections:,} rejected records, and {failures:,} hard failures."
    )


def _overview_table(report: dict[str, Any], *, renderer: PdfRenderer) -> Table:
    markets = report.get("markets") or []
    coverage = [market.get("coverage") or {} for market in markets]
    return _table(
        [
            ["Outcome", "Markets", "Listings", "Bars", "Warnings", "Rejected"],
            [
                report.get("outcome") or "UNKNOWN",
                len(markets),
                sum(_int(item.get("listing_count")) for item in coverage),
                sum(_int(item.get("bar_count")) for item in coverage),
                _int((report.get("warnings") or {}).get("total_count")),
                _int((report.get("row_rejections") or {}).get("rejected_records")),
            ],
        ],
        renderer=renderer,
        col_widths=[84] * 6,
    )


def _market_overview_table(markets: list[dict[str, Any]], *, renderer: PdfRenderer) -> Table:
    rows: list[list[Any]] = [
        [
            "Market",
            "Freshness",
            "Listings",
            "With Bars",
            "No Bars",
            "Bars",
            "Latest Date",
        ]
    ]
    for market in markets:
        coverage = market.get("coverage") or {}
        freshness = market.get("freshness") or {}
        rows.append(
            [
                market.get("market") or "",
                freshness.get("status") or "unknown",
                _fmt_int(coverage.get("listing_count")),
                _fmt_int(coverage.get("listings_with_bars")),
                _fmt_int(coverage.get("listings_without_bars")),
                _fmt_int(coverage.get("bar_count")),
                coverage.get("last_trading_date") or "No data",
            ]
        )
    return _table(rows, renderer=renderer, col_widths=[56, 70, 66, 66, 60, 82, 104])


def _market_detail(market: dict[str, Any], *, renderer: PdfRenderer) -> list[Any]:
    coverage = market.get("coverage") or {}
    freshness = market.get("freshness") or {}
    listing_feed = market.get("listing_feed") or {}
    bar_feed = market.get("quote_or_bar_feed") or {}
    listing_write = market.get("listing_write") or {}
    bar_write = market.get("bar_write") or {}
    listing_counts = listing_write.get("counts") or {}
    bar_counts = bar_write.get("counts") or {}
    cross_feed = market.get("cross_feed_outcomes") or {}
    duplicate = market.get("duplicate_outcomes") or {}
    rows = [
        ["Metric", "Listings", "Daily Bars"],
        [
            "Input rows",
            _fmt_int(listing_feed.get("input_rows")),
            _fmt_int(bar_feed.get("input_rows")),
        ],
        [
            "Accepted records",
            _fmt_int(listing_feed.get("accepted_records")),
            _fmt_int(bar_feed.get("accepted_records")),
        ],
        [
            "Inserted",
            _fmt_int(listing_counts.get("inserted")),
            _fmt_int(bar_counts.get("inserted")),
        ],
        ["Updated", _fmt_int(listing_counts.get("updated")), _fmt_int(bar_counts.get("updated"))],
        [
            "Unchanged",
            _fmt_int(listing_counts.get("unchanged")),
            _fmt_int(bar_counts.get("unchanged")),
        ],
        ["Skipped inactive", "-", _fmt_int(bar_write.get("skipped_inactive"))],
        [
            "Duplicates collapsed",
            _fmt_int(duplicate.get("listing_rows_collapsed")),
            _fmt_int(duplicate.get("bar_rows_collapsed")),
        ],
    ]
    facts = [
        ["Health Fact", "Value"],
        ["Freshness", freshness.get("status") or "unknown"],
        ["Latest bar weekday age", _display(freshness.get("latest_bar_weekday_age"))],
        [
            "Coverage date range",
            f"{coverage.get('first_trading_date') or 'No data'} through "
            f"{coverage.get('last_trading_date') or 'No data'}",
        ],
        ["Listings without bars", _fmt_int(cross_feed.get("listings_without_bars"))],
        ["Bars without listings", _fmt_int(cross_feed.get("bars_without_listings"))],
        ["Stale candidates", _fmt_int((market.get("stale_candidates") or {}).get("total_count"))],
        [
            "No-data candidates",
            _fmt_int((market.get("no_data_candidates") or {}).get("total_count")),
        ],
        ["Weekday gaps", _fmt_int((market.get("weekday_gap_warnings") or {}).get("total_count"))],
        [
            "Rejected records / rows",
            f"{_fmt_int((market.get('row_rejections') or {}).get('rejected_records'))} / "
            f"{_fmt_int((market.get('row_rejections') or {}).get('rejected_rows'))}",
        ],
    ]
    return [
        Paragraph(
            escape(str(market.get("market") or "Unknown market")),
            renderer.styles.subheading,
        ),
        _table(rows, renderer=renderer, col_widths=[168, 168, 168]),
        spacer(6),
        _table(facts, renderer=renderer, col_widths=[190, 314]),
    ]


def _sources_table(sources: list[dict[str, Any]], *, renderer: PdfRenderer) -> Table:
    rows: list[list[Any]] = [["Source", "Parser", "Market", "Filename", "Bytes", "Object ID"]]
    for source in sources:
        for item in source.get("acquired_objects") or []:
            rows.append(
                [
                    source.get("source_code") or "",
                    source.get("parser_version") or "",
                    item.get("market") or "",
                    item.get("filename") or "",
                    _fmt_int(item.get("size_bytes")),
                    item.get("object_id") or "",
                ]
            )
    return _table(rows, renderer=renderer, col_widths=[94, 62, 44, 86, 54, 164])


def _inactive_table(section: dict[str, Any], *, renderer: PdfRenderer) -> Table:
    rows: list[list[Any]] = [["Market", "Listings", "With Bars", "Without Bars", "Bars"]]
    for market in section.get("markets") or []:
        rows.append(
            [
                market.get("market") or "",
                _fmt_int(market.get("listing_count")),
                _fmt_int(market.get("listings_with_bars")),
                _fmt_int(market.get("listings_without_bars")),
                _fmt_int(market.get("bar_count")),
            ]
        )
    rows.append(["Total", _fmt_int(section.get("total_count")), "", "", ""])
    return _table(rows, renderer=renderer, col_widths=[104, 100, 100, 100, 100])


def _review_summary(report: dict[str, Any]) -> str:
    failures = _int((report.get("hard_failures") or {}).get("total_count"))
    warnings = _int((report.get("warnings") or {}).get("total_count"))
    rejected = _int((report.get("row_rejections") or {}).get("rejected_records"))
    if failures + warnings + rejected == 0:
        return "No warnings, rejected records, or hard failures were reported."
    return (
        f"Review {failures:,} hard failures, {warnings:,} import warnings, and "
        f"{rejected:,} rejected records below. Samples are bounded exactly as "
        "they are in the JSON report."
    )


def _review_sections(report: dict[str, Any], *, renderer: PdfRenderer) -> list[Any]:
    sections: list[Any] = []
    summary_sections = [
        ("Hard Failures", report.get("hard_failures") or {}),
        ("Import Warnings", report.get("warnings") or {}),
    ]
    for market in report.get("markets") or []:
        label = str(market.get("market") or "Unknown")
        summary_sections.extend(
            [
                (f"{label} Stale Candidates", market.get("stale_candidates") or {}),
                (f"{label} No-data Candidates", market.get("no_data_candidates") or {}),
                (f"{label} Weekday Gap Warnings", market.get("weekday_gap_warnings") or {}),
            ]
        )
    for title, section in summary_sections:
        total = _int(section.get("total_count"))
        if not total:
            continue
        heading = Paragraph(escape(title), renderer.styles.subheading)
        heading.keepWithNext = 1
        summary = paragraph(
            f"{total:,} total; "
            f"{_int(section.get('sample_count')):,} samples shown"
            + (
                "; sample list truncated."
                if section.get("truncated")
                else "."
            ),
            styles=renderer.styles,
        )
        summary.keepWithNext = 1
        sections.extend(
            [
                heading,
                summary,
                _sample_table(section.get("samples") or [], renderer=renderer),
                spacer(8),
            ]
        )
    rejections = report.get("row_rejections") or {}
    if _int(rejections.get("rejected_records")):
        heading = Paragraph(
            "Row Rejection Reasons", renderer.styles.subheading
        )
        heading.keepWithNext = 1
        sections.extend(
            [
                heading,
                _sample_table(
                    rejections.get("reasons") or [], renderer=renderer
                ),
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
    rows = [["Property", "Value"], *[[_humanize(key), value] for key, value in values.items()]]
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


def _fmt_int(value: Any) -> str:
    return f"{_int(value):,}"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _display(value: Any) -> str:
    return "Not available" if value is None else str(value)


def _humanize(value: str) -> str:
    text = value.replace("_", " ").strip()
    return text[:1].upper() + text[1:]
