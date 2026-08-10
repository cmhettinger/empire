"""Empire-branded PDF renderer for active Yahoo benchmarks."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from empire_reports.contracts import RenderContext, RenderResult, ReportMetadata
from empire_reports.renderers.pdf import (
    HeaderFooterSpec,
    PdfRenderer,
    QuoteTileSpec,
    paragraph,
    professional_letter_disclaimer_page,
    professional_letter_title_page,
    quote_tile_grid,
    section_heading,
    spacer,
)
from empire_stonks_ohlcv.yahoo_benchmark_reporting import (
    YahooBenchmarkRow,
    YahooBenchmarkSection,
    YahooBenchmarkStatus,
    YahooDailyBenchmarkReport,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    NextPageTemplate,
    PageBreak,
    Paragraph,
    Table,
    TableStyle,
)


YAHOO_DAILY_BENCHMARK_PDF_REPORT_ID = "stonks.ohlcv.yahoo-daily-benchmark"
TITLE = "Daily Benchmark Report"
SUBTITLE = "Yahoo Global Indices, Rates and Commodities"
HEADER_TEXT = "EMPIRE RESEARCH DIVISION"
FOOTER_TEXT = "PROPRIETARY / INTERNAL USE ONLY"
ROWS_PER_PAGE = 12


def render_yahoo_daily_benchmark_pdf(
    *,
    report: YahooDailyBenchmarkReport,
    output_dir: str | Path,
    filename: str = "daily-benchmark-report.pdf",
) -> RenderResult:
    """Render one exact-date Yahoo benchmark report."""

    if not isinstance(report, YahooDailyBenchmarkReport):
        raise TypeError("report must be a YahooDailyBenchmarkReport.")
    metadata = ReportMetadata(
        report_id=YAHOO_DAILY_BENCHMARK_PDF_REPORT_ID,
        title=TITLE,
        subtitle=SUBTITLE,
        as_of=report.trading_date,
        generated_at=report.generated_at,
        description="Active Yahoo benchmarks for one exact calendar date.",
        tags=("stonks", "ohlcv", "yahoo", "daily", "benchmark"),
    )
    renderer = PdfRenderer(
        metadata=metadata,
        context=RenderContext(output_dir=Path(output_dir)),
    )
    story: list[Any] = [
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
        NextPageTemplate("letter_title"),
        PageBreak(),
        *professional_letter_disclaimer_page(
            header_text=HEADER_TEXT,
            footer_text=FOOTER_TEXT,
            assets=renderer.assets,
            branding=renderer.branding,
            theme=renderer.theme,
        ),
        NextPageTemplate("letter_body"),
        PageBreak(),
        *_body_story(report, renderer=renderer),
    ]
    templates = renderer.default_templates(
        HeaderFooterSpec(
            header_center_text=HEADER_TEXT,
            header_right_text=report.trading_date.isoformat(),
            footer_text=FOOTER_TEXT,
            page_number_offset=2,
        )
    )
    templates.get("letter_title").autoNextPageTemplate = "letter_title"
    templates.get("letter_body").autoNextPageTemplate = "letter_body"
    return renderer.render(
        story,
        out_path=Path(output_dir) / filename,
        templates=templates,
    )


def _body_story(
    report: YahooDailyBenchmarkReport,
    *,
    renderer: PdfRenderer,
) -> list[Any]:
    story: list[Any] = [
        section_heading("Executive Summary", styles=renderer.styles),
        paragraph(_executive_summary(report), styles=renderer.styles),
        _summary_metrics(report, renderer=renderer),
        spacer(14),
        section_heading("Section Coverage", styles=renderer.styles),
        _section_coverage_table(report.sections, renderer=renderer),
    ]
    for section in report.sections:
        for page_number, rows in enumerate(_chunks(section.rows, ROWS_PER_PAGE), 1):
            story.extend(
                _section_page(
                    section=section,
                    rows=rows,
                    page_number=page_number,
                    page_count=(len(section.rows) + ROWS_PER_PAGE - 1)
                    // ROWS_PER_PAGE,
                    renderer=renderer,
                )
            )
    story.extend(
        [
            PageBreak(),
            section_heading("Methodology and Scope", styles=renderer.styles),
            paragraph(
                "<b>Provider and universe.</b> This report uses provider-native "
                "Yahoo daily bars from active YAHOO listings only. Inactive "
                "listings are excluded from pages, tables, annotations and "
                "coverage counts.",
                styles=renderer.styles,
            ),
            paragraph(
                "<b>Date alignment.</b> Every displayed observation has a stored "
                "trading date exactly equal to the report date. The report does "
                "not carry an earlier close forward across holidays or missing "
                "provider observations.",
                styles=renderer.styles,
            ),
            paragraph(
                "<b>Daily performance.</b> Change is the report-date close minus "
                "the latest preceding stored close for the same Yahoo listing. "
                "Percentage change divides that difference by the preceding "
                "close. A reported first observation can therefore have no prior "
                "comparison.",
                styles=renderer.styles,
            ),
            paragraph(
                "<b>Unavailable states.</b> Market Closed means the authoritative "
                "calendar has no session for the date. Not Yet Eligible means the "
                "configured publication time had not passed when the report was "
                "generated. No Data means an eligible date had no stored Yahoo "
                "bar, or its configured calendar could not be resolved.",
                styles=renderer.styles,
            ),
            paragraph(
                "<b>Continuous futures.</b> Futures rows represent provider-native "
                "continuous contracts rather than a specific deliverable contract. "
                "They can include provider roll behavior and are not adjusted into "
                "a custom Empire continuous series.",
                styles=renderer.styles,
            ),
            paragraph(
                "<b>Interpretation.</b> The document is descriptive research, not "
                "investment advice. Cross-market returns reflect distinct local "
                "sessions, currencies, calendars and publication conventions.",
                styles=renderer.styles,
            ),
        ]
    )
    return story


def _section_page(
    *,
    section: YahooBenchmarkSection,
    rows: tuple[YahooBenchmarkRow, ...],
    page_number: int,
    page_count: int,
    renderer: PdfRenderer,
) -> list[Any]:
    title = section.title
    if page_count > 1:
        title = f"{title} ({page_number} of {page_count})"
    reported = sum(row.status is YahooBenchmarkStatus.REPORTED for row in rows)
    story: list[Any] = [
        PageBreak(),
        section_heading(title, styles=renderer.styles),
        paragraph(
            f"Exact-date coverage: <b>{reported} of {len(rows)}</b> active "
            f"listings reported for the page. Membership version: "
            f"{escape(section.membership_version)}.",
            styles=renderer.styles,
        ),
        quote_tile_grid(
            [_quote_tile(row) for row in rows],
            columns=4,
            tile_height=62,
            theme=renderer.theme,
        ),
        spacer(9),
        _benchmark_table(rows, renderer=renderer),
    ]
    note = _unavailable_note(rows)
    if note:
        story.extend([spacer(7), paragraph(note, styles=renderer.styles)])
    return story


def _quote_tile(row: YahooBenchmarkRow) -> QuoteTileSpec:
    if row.status is not YahooBenchmarkStatus.REPORTED:
        return QuoteTileSpec(
            ticker=row.ticker,
            price=None,
            change=None,
            change_pct=None,
            status=row.status.value,
        )
    return QuoteTileSpec(
        ticker=row.ticker,
        price=float(row.close) if row.close is not None else None,
        change=None if row.change is None else float(row.change),
        change_pct=(
            None
            if row.changepct is None
            else float(row.changepct * Decimal(100))
        ),
    )


def _benchmark_table(
    rows: Sequence[YahooBenchmarkRow],
    *,
    renderer: PdfRenderer,
) -> Table:
    name_style = ParagraphStyle(
        "benchmark-table-name",
        parent=renderer.styles.body,
        fontSize=7.2,
        leading=8.3,
        spaceAfter=0,
    )
    values: list[list[object]] = [
        ["Ticker", "Benchmark", "Close", "Change", "Return", "Prior", "Status"]
    ]
    for row in rows:
        values.append(
            [
                row.ticker,
                Paragraph(escape(row.name), name_style),
                _number(row.close),
                _signed_number(row.change),
                _percent(row.changepct),
                (
                    "-"
                    if row.previous_trading_date is None
                    else row.previous_trading_date.isoformat()
                ),
                _status_label(row),
            ]
        )
    return _table(
        values,
        renderer=renderer,
        col_widths=[50, 174, 66, 62, 58, 70, 70],
        alignments={2: TA_RIGHT, 3: TA_RIGHT, 4: TA_RIGHT, 5: TA_CENTER},
    )


def _summary_metrics(
    report: YahooDailyBenchmarkReport,
    *,
    renderer: PdfRenderer,
) -> Table:
    return _table(
        [
            ["Active", "Reported", "Market Closed", "Not Eligible", "No Data"],
            [
                str(report.active_listing_count),
                str(report.reported_count),
                str(report.market_closed_count),
                str(report.not_yet_eligible_count),
                str(report.no_data_count),
            ],
        ],
        renderer=renderer,
        col_widths=[100.8] * 5,
        centered=True,
    )


def _section_coverage_table(
    sections: Sequence[YahooBenchmarkSection],
    *,
    renderer: PdfRenderer,
) -> Table:
    values: list[list[object]] = [["Section", "Active", "Reported", "Unavailable"]]
    values.extend(
        [
            section.title,
            str(len(section.rows)),
            str(section.reported_count),
            str(section.unavailable_count),
        ]
        for section in sections
    )
    return _table(
        values,
        renderer=renderer,
        col_widths=[300, 68, 68, 68],
        centered=True,
    )


def _table(
    rows: Sequence[Sequence[object]],
    *,
    renderer: PdfRenderer,
    col_widths: Sequence[float],
    alignments: dict[int, int] | None = None,
    centered: bool = False,
) -> Table:
    table = Table(rows, colWidths=list(col_widths), repeatRows=1)
    commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), renderer.theme.primary),
        ("TEXTCOLOR", (0, 0), (-1, 0), renderer.theme.white),
        ("FONTNAME", (0, 0), (-1, 0), renderer.theme.body_semibold_font),
        ("FONTNAME", (0, 1), (-1, -1), renderer.theme.body_font),
        ("FONTSIZE", (0, 0), (-1, -1), 7.3),
        ("LEADING", (0, 0), (-1, -1), 8.4),
        ("GRID", (0, 0), (-1, -1), 0.35, renderer.theme.light_grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        (
            "ROWBACKGROUNDS",
            (0, 1),
            (-1, -1),
            [renderer.theme.white, "#F7F7F7"],
        ),
    ]
    if centered:
        commands.append(("ALIGN", (1, 0), (-1, -1), "CENTER"))
    for column, alignment in (alignments or {}).items():
        value = "RIGHT" if alignment == TA_RIGHT else "CENTER"
        commands.append(("ALIGN", (column, 1), (column, -1), value))
    table.setStyle(TableStyle(commands))
    return table


def _executive_summary(report: YahooDailyBenchmarkReport) -> str:
    return (
        f"Yahoo supplied exact-date observations for <b>{report.reported_count} "
        f"of {report.active_listing_count} active benchmark listings</b> on "
        f"{report.trading_date.isoformat()}. The report spans equity indices, "
        "volatility, Treasury yield and currency indices, equity index futures, "
        "commodity benchmarks and continuous commodity futures. Missing states "
        "are retained explicitly and no prior close is substituted for the "
        "report date."
    )


def _unavailable_note(rows: Sequence[YahooBenchmarkRow]) -> str:
    unavailable = [
        row for row in rows if row.status is not YahooBenchmarkStatus.REPORTED
    ]
    if not unavailable:
        return ""
    values = "; ".join(
        f"<b>{escape(row.ticker)}</b>: {escape(row.status.value.title())}"
        for row in unavailable
    )
    return f"<b>Unavailable observations.</b> {values}."


def _status_label(row: YahooBenchmarkRow) -> str:
    if row.status is not YahooBenchmarkStatus.REPORTED:
        return row.status.value.title()
    return "Reported" if row.changepct is not None else "No prior close"


def _number(value: Decimal | None) -> str:
    return "-" if value is None else f"{value:,.2f}"


def _signed_number(value: Decimal | None) -> str:
    return "-" if value is None else f"{value:+,.2f}"


def _percent(value: Decimal | None) -> str:
    return "-" if value is None else f"{value * Decimal(100):+.2f}%"


def _chunks(
    rows: tuple[YahooBenchmarkRow, ...],
    size: int,
) -> tuple[tuple[YahooBenchmarkRow, ...], ...]:
    return tuple(rows[index : index + size] for index in range(0, len(rows), size))


__all__ = [
    "YAHOO_DAILY_BENCHMARK_PDF_REPORT_ID",
    "render_yahoo_daily_benchmark_pdf",
]
