"""Empire-branded PDF renderer for provider-native EODData market analysis."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
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
from empire_stonks_ohlcv.config import DEFAULT_EODDATA_EXCHANGES
from empire_stonks_ohlcv.daily_market_reporting import (
    DailyEquityRow,
    DailyMarketBasketSnapshot,
    EODDataDailyMarketReport,
    HighVolumeLowMovementRow,
    PriceAnomaly,
    VolumeAnomaly,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    LongTable,
    NextPageTemplate,
    PageBreak,
    Paragraph,
    Table,
    TableStyle,
)


EODDATA_DAILY_MARKET_PDF_REPORT_ID = "stonks.ohlcv.eoddata-daily-market"
TITLE = "Daily Market Report"
SUBTITLE = "EODData Equity Performance"
HEADER_TEXT = "EMPIRE RESEARCH DIVISION"
FOOTER_TEXT = "PROPRIETARY / INTERNAL USE ONLY"


def render_eoddata_daily_market_pdf(
    *,
    report: EODDataDailyMarketReport,
    output_dir: str | Path,
    filename: str = "daily-market-report.pdf",
) -> RenderResult:
    """Render one date-scoped EODData equity report."""

    if not isinstance(report, EODDataDailyMarketReport):
        raise TypeError("report must be an EODDataDailyMarketReport.")
    metadata = ReportMetadata(
        report_id=EODDATA_DAILY_MARKET_PDF_REPORT_ID,
        title=TITLE,
        subtitle=SUBTITLE,
        as_of=report.trading_date,
        generated_at=report.generated_at,
        description=(
            "Provider-native EODData equity performance for one trading date."
        ),
        tags=("stonks", "ohlcv", "eoddata", "daily", "market"),
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
            branding=renderer.branding,
            theme=renderer.theme,
        ),
        NextPageTemplate("letter_body"),
        PageBreak(),
        *_body_story(report, renderer=renderer),
    ]
    header_footer = HeaderFooterSpec(
        header_center_text=HEADER_TEXT,
        header_right_text=report.trading_date.isoformat(),
        footer_text=FOOTER_TEXT,
        page_number_offset=2,
    )
    templates = renderer.default_templates(header_footer)
    templates.get("letter_title").autoNextPageTemplate = "letter_title"
    templates.get("letter_body").autoNextPageTemplate = "letter_body"
    return renderer.render(
        story,
        out_path=Path(output_dir) / filename,
        templates=templates,
    )


def _body_story(
    report: EODDataDailyMarketReport,
    *,
    renderer: PdfRenderer,
) -> list[Any]:
    story: list[Any] = [
        section_heading("Executive Summary", styles=renderer.styles),
        paragraph(_executive_summary(report), styles=renderer.styles),
        _key_metrics_table(report, renderer=renderer),
        spacer(14),
        section_heading("Exchange Breadth", styles=renderer.styles),
        paragraph(
            "Advancers and decliners use close-to-close returns calculated from "
            "the latest preceding EODData bar for the same provider listing.",
            styles=renderer.styles,
        ),
        _breadth_table(report, renderer=renderer),
    ]
    if report.move_buckets:
        story.extend(
            [
                spacer(14),
                section_heading("Return Distribution", styles=renderer.styles),
                _move_bucket_table(report, renderer=renderer),
            ]
        )

    highlight_winners = tuple(
        sorted(
            report.winners,
            key=lambda row: row.changepct or Decimal(0),
            reverse=True,
        )[:12]
    )
    highlight_losers = tuple(
        sorted(
            report.losers,
            key=lambda row: row.changepct or Decimal(0),
        )[:12]
    )
    if highlight_winners:
        story.extend(
            _ranked_equity_page(
                title="Market Highlights - Session Leaders",
                subtitle=_market_tone(report),
                rows=highlight_winners,
                renderer=renderer,
            )
        )
    if highlight_losers:
        story.extend(
            _ranked_equity_page(
                title="Market Highlights - Session Laggards",
                subtitle=_market_tone(report),
                rows=highlight_losers,
                renderer=renderer,
            )
        )

    for market in DEFAULT_EODDATA_EXCHANGES:
        winners = tuple(row for row in report.winners if row.market == market)
        losers = tuple(row for row in report.losers if row.market == market)
        if winners:
            story.extend(
                _ranked_equity_page(
                    title=f"{market} Leading Advancers",
                    subtitle=(
                        "Ranked by strongest calculated close-to-close return for "
                        "the report date."
                    ),
                    rows=winners,
                    renderer=renderer,
                )
            )
        if losers:
            story.extend(
                _ranked_equity_page(
                    title=f"{market} Leading Decliners",
                    subtitle=(
                        "Ranked by weakest calculated close-to-close return for "
                        "the report date."
                    ),
                    rows=losers,
                    renderer=renderer,
                )
            )

    story.extend(_high_volume_low_movement_story(report, renderer=renderer))
    story.extend(_configured_basket_story(report, renderer=renderer))

    for market in DEFAULT_EODDATA_EXCHANGES:
        leaders = tuple(
            row for row in report.volume_leaders if row.market == market
        )
        if not leaders:
            continue
        story.extend(
            _ranked_equity_page(
                title=f"{market} Volume Leaders",
                subtitle=(
                    "The most actively traded EODData equities by reported share "
                    "volume for the day."
                ),
                rows=leaders,
                renderer=renderer,
            )
        )

    if report.price_anomalies:
        story.extend(
            [
                PageBreak(),
                section_heading("Price Anomalies", styles=renderer.styles),
                paragraph(
                    "Large close-to-close returns and unusually wide intraday "
                    "ranges are highlighted for review; a flag is not a confirmed "
                    "corporate action.",
                    styles=renderer.styles,
                ),
                _price_anomaly_table(report.price_anomalies, renderer=renderer),
            ]
        )

    if report.volume_anomalies:
        story.extend(
            [
                PageBreak(),
                section_heading("Volume Anomalies", styles=renderer.styles),
                paragraph(
                    "Volume anomalies require 20 prior EODData volume observations "
                    "and compare today's volume with that trailing average.",
                    styles=renderer.styles,
                ),
                _volume_anomaly_table(report.volume_anomalies, renderer=renderer),
            ]
        )

    story.extend(
        [
            PageBreak(),
            section_heading("Methodology and Scope", styles=renderer.styles),
            paragraph(
                "<b>Universe.</b> The report includes persisted bars whose provider "
                "is EODDATA, whose trading date matches the report date, and whose "
                "retained EODData symbol type is Equity. Funds, other classified "
                "instruments, and unclassified listings are excluded from analysis.",
                styles=renderer.styles,
            ),
            paragraph(
                "<b>Daily performance.</b> Change is the current close minus the "
                "latest preceding close for the same provider-native listing. "
                "Percentage change is that difference divided by the preceding "
                "close. Listings without a preceding bar remain in volume and "
                "coverage totals but cannot be ranked by daily return.",
                styles=renderer.styles,
            ),
            paragraph(
                "<b>High-volume, low movement.</b> Each exchange section shows up "
                "to 12 equities with an absolute calculated close-to-close return "
                "no greater than 0.50%, ranked by reported share volume and then "
                "by smallest absolute return.",
                styles=renderer.styles,
            ),
            paragraph(
                "<b>Configured baskets.</b> Magnificent Seven, Dow 30, and "
                "Nasdaq-100 pages use versioned ticker sets owned by this report. "
                "They are analytical cohorts, not authoritative or historically "
                "effective-dated index membership. Missing configured tickers are "
                "omitted and disclosed through section coverage.",
                styles=renderer.styles,
            ),
            paragraph(
                "<b>Current capability boundary.</b> No index-level benchmark, "
                "sector, industry, commodity, or precomputed technical-indicator "
                "claims are made because those capabilities are not yet represented "
                "in the provider-native OHLCV schema.",
                styles=renderer.styles,
            ),
            _scope_table(report, renderer=renderer),
        ]
    )
    return story


def _executive_summary(report: EODDataDailyMarketReport) -> str:
    universe = report.universe
    if universe.equity_bar_count == 0:
        return (
            f"No EODData equities were available for {report.trading_date.isoformat()}. "
            f"The database contained {universe.source_bar_count:,} provider bars for "
            "the date, but none were classified by EODData as Equity."
        )
    direction = (
        "more advancers than decliners"
        if report.advancers > report.decliners
        else "more decliners than advancers"
        if report.decliners > report.advancers
        else "an even split between advancers and decliners"
    )
    return (
        f"EODData recorded <b>{universe.equity_bar_count:,} equities</b> across "
        f"NYSE, NASDAQ, and AMEX for {report.trading_date.isoformat()}. Among the "
        f"{report.comparable_count:,} equities with a preceding close, the session "
        f"finished with {direction}: {report.advancers:,} advanced, "
        f"{report.decliners:,} declined, and {report.unchanged:,} were unchanged."
    )


def _market_tone(report: EODDataDailyMarketReport) -> str:
    top_winner = max(
        (row for row in report.winners if row.changepct is not None),
        key=lambda row: row.changepct or Decimal(0),
        default=None,
    )
    top_loser = min(
        (row for row in report.losers if row.changepct is not None),
        key=lambda row: row.changepct or Decimal(0),
        default=None,
    )
    statements = [
        f"The broad equity universe produced {report.advancers:,} advancers and "
        f"{report.decliners:,} decliners."
    ]
    if top_winner is not None:
        statements.append(
            f"The strongest reported move was {escape(top_winner.ticker)} "
            f"({escape(top_winner.market)}) at {_percent(top_winner.changepct)}."
        )
    if top_loser is not None:
        statements.append(
            f"The weakest reported move was {escape(top_loser.ticker)} "
            f"({escape(top_loser.market)}) at {_percent(top_loser.changepct)}."
        )
    return " ".join(statements)


def _key_metrics_table(
    report: EODDataDailyMarketReport,
    *,
    renderer: PdfRenderer,
) -> Table:
    return _table(
        [
            ["Equities", "Comparable", "Advancers", "Decliners", "Unchanged", "Volume"],
            [
                f"{report.universe.equity_bar_count:,}",
                f"{report.comparable_count:,}",
                f"{report.advancers:,}",
                f"{report.decliners:,}",
                f"{report.unchanged:,}",
                _compact_number(report.total_volume),
            ],
        ],
        renderer=renderer,
        col_widths=[84] * 6,
        centered=True,
    )


def _breadth_table(
    report: EODDataDailyMarketReport,
    *,
    renderer: PdfRenderer,
) -> Table:
    rows: list[list[object]] = [
        ["Market", "Equities", "Compared", "Up", "Down", "Flat", "No Prior", "Avg Return", "Volume"]
    ]
    for item in report.breadth:
        rows.append(
            [
                item.market,
                f"{item.equity_count:,}",
                f"{item.comparable_count:,}",
                f"{item.advancers:,}",
                f"{item.decliners:,}",
                f"{item.unchanged:,}",
                f"{item.missing_comparison:,}",
                _percent(item.average_return),
                _compact_number(item.total_volume),
            ]
        )
    return _table(
        rows,
        renderer=renderer,
        col_widths=[54, 55, 58, 40, 43, 38, 50, 68, 63],
        centered=True,
    )


def _move_bucket_table(
    report: EODDataDailyMarketReport,
    *,
    renderer: PdfRenderer,
) -> Table:
    rows: list[list[object]] = [["Return Bucket", "NYSE", "NASDAQ", "AMEX", "Total"]]
    rows.extend(
        [
            item.label,
            f"{item.nyse_count:,}",
            f"{item.nasdaq_count:,}",
            f"{item.amex_count:,}",
            f"{item.total_count:,}",
        ]
        for item in report.move_buckets
    )
    return _table(
        rows,
        renderer=renderer,
        col_widths=[180, 81, 81, 81, 81],
        centered=True,
    )


def _ranked_equity_page(
    *,
    title: str,
    subtitle: str,
    rows: Sequence[DailyEquityRow],
    renderer: PdfRenderer,
) -> list[Any]:
    return [
        PageBreak(),
        section_heading(title, styles=renderer.styles),
        paragraph(subtitle, styles=renderer.styles),
        quote_tile_grid(
            [_quote_tile(row) for row in rows],
            columns=4,
            tile_height=62,
            theme=renderer.theme,
        ),
        spacer(10),
        _equity_table(rows, renderer=renderer),
    ]


def _quote_tile(row: DailyEquityRow) -> QuoteTileSpec:
    return QuoteTileSpec(
        ticker=row.ticker,
        price=float(row.close),
        change=None if row.change is None else float(row.change),
        change_pct=(
            None
            if row.changepct is None
            else float(row.changepct * Decimal(100))
        ),
    )


def _configured_basket_story(
    report: EODDataDailyMarketReport,
    *,
    renderer: PdfRenderer,
) -> list[Any]:
    story: list[Any] = []
    mag7 = report.basket("MAG7")
    if mag7 is not None and mag7.rows:
        rows = _sorted_returns(mag7.rows, reverse=True, include_missing=True)
        story.extend(
            _ranked_equity_page(
                title=mag7.title,
                subtitle=_basket_coverage_text(mag7),
                rows=rows,
                renderer=renderer,
            )
        )

    dow30 = report.basket("DOW30")
    if dow30 is not None and dow30.rows:
        rows = _sorted_returns(dow30.rows, reverse=True, include_missing=True)
        story.extend(
            _basket_tiles_and_table(
                basket=dow30,
                rows=rows,
                renderer=renderer,
                columns=5,
                tile_height=62,
            )
        )

    nasdaq100 = report.basket("NASDAQ100")
    if nasdaq100 is not None and nasdaq100.rows:
        comparable = tuple(
            row for row in nasdaq100.rows if row.changepct is not None
        )
        leaders = _sorted_returns(
            comparable,
            reverse=True,
            include_missing=False,
        )[:30]
        laggards = _sorted_returns(
            comparable,
            reverse=False,
            include_missing=False,
        )[:30]
        if leaders:
            story.extend(
                _basket_tiles_and_table(
                    basket=nasdaq100,
                    rows=leaders,
                    renderer=renderer,
                    columns=5,
                    tile_height=62,
                    section_suffix="Leaders",
                    detail_suffix="Leaders Detail",
                )
            )
        if laggards:
            story.extend(
                _basket_tiles_and_table(
                    basket=nasdaq100,
                    rows=laggards,
                    renderer=renderer,
                    columns=5,
                    tile_height=62,
                    section_suffix="Laggards",
                    detail_suffix="Laggards Detail",
                )
            )
    return story


def _high_volume_low_movement_story(
    report: EODDataDailyMarketReport,
    *,
    renderer: PdfRenderer,
) -> list[Any]:
    story: list[Any] = []
    for market in DEFAULT_EODDATA_EXCHANGES:
        rows = tuple(
            row
            for row in report.high_volume_low_movement
            if row.market == market
        )
        if not rows:
            continue
        story.extend(
            [
                PageBreak(),
                section_heading(
                    f"High-Volume, Low Movement - {market}",
                    styles=renderer.styles,
                ),
                paragraph(
                    f"The {len(rows)} highest-volume EODData equities on {market} "
                    "whose absolute calculated close-to-close return was no greater "
                    "than 0.50%.",
                    styles=renderer.styles,
                ),
                quote_tile_grid(
                    [_high_volume_quote_tile(row) for row in rows],
                    columns=4,
                    tile_height=62,
                    theme=renderer.theme,
                ),
                spacer(10),
                _high_volume_low_movement_table(rows, renderer=renderer),
            ]
        )
    return story


def _high_volume_quote_tile(row: HighVolumeLowMovementRow) -> QuoteTileSpec:
    return QuoteTileSpec(
        ticker=row.ticker,
        price=float(row.close),
        change=float(row.change),
        change_pct=float(row.changepct * Decimal(100)),
    )


def _high_volume_low_movement_table(
    rows: Sequence[HighVolumeLowMovementRow],
    *,
    renderer: PdfRenderer,
) -> LongTable:
    table_rows: list[list[object]] = [
        [
            "Ticker",
            "Company",
            "Open",
            "High",
            "Low",
            "Close",
            "Change",
            "Return",
            "Volume",
        ]
    ]
    table_rows.extend(
        [
            row.ticker,
            row.name,
            f"{row.open:,.4f}",
            f"{row.high:,.4f}",
            f"{row.low:,.4f}",
            f"{row.close:,.4f}",
            _signed_number(row.change),
            _percent(row.changepct),
            _integer(row.volume),
        ]
        for row in rows
    )
    return _table(
        table_rows,
        renderer=renderer,
        col_widths=[42, 110, 45, 45, 45, 48, 50, 55, 64],
        numeric_columns=(2, 3, 4, 5, 6, 7, 8),
        return_column=7,
        font_size=6.2,
        long=True,
    )


def _basket_tiles_and_table(
    *,
    basket: DailyMarketBasketSnapshot,
    rows: Sequence[DailyEquityRow],
    renderer: PdfRenderer,
    columns: int,
    tile_height: float,
    section_suffix: str | None = None,
    detail_suffix: str = "Daily Detail",
) -> list[Any]:
    title = basket.title
    section_title = f"{title} - {section_suffix}" if section_suffix else title
    return [
        PageBreak(),
        section_heading(section_title, styles=renderer.styles),
        paragraph(_basket_coverage_text(basket), styles=renderer.styles),
        quote_tile_grid(
            [_quote_tile(row) for row in rows],
            columns=columns,
            tile_height=tile_height,
            theme=renderer.theme,
        ),
        PageBreak(),
        section_heading(f"{title} - {detail_suffix}", styles=renderer.styles),
        paragraph(
            "Rows are ranked by calculated close-to-close return for the report date.",
            styles=renderer.styles,
        ),
        _equity_table(rows, renderer=renderer),
    ]


def _basket_coverage_text(basket: DailyMarketBasketSnapshot) -> str:
    text = (
        f"Configured basket {escape(basket.membership_version)}: "
        f"<b>{basket.available_count} of {basket.configured_count}</b> tickers have "
        f"EODData equity rows; {basket.comparable_count} have a preceding close."
    )
    if basket.missing_tickers:
        text += " Missing: " + ", ".join(
            escape(ticker) for ticker in basket.missing_tickers
        ) + "."
    return text


def _sorted_returns(
    rows: Sequence[DailyEquityRow],
    *,
    reverse: bool,
    include_missing: bool,
) -> tuple[DailyEquityRow, ...]:
    selected = rows if include_missing else tuple(
        row for row in rows if row.changepct is not None
    )
    return tuple(
        sorted(
            selected,
            key=lambda row: (
                row.changepct is not None,
                row.changepct if row.changepct is not None else Decimal(0),
                row.ticker,
            ),
            reverse=reverse,
        )
    )


def _equity_table(
    rows: Sequence[DailyEquityRow],
    *,
    renderer: PdfRenderer,
) -> LongTable:
    table_rows: list[list[object]] = [
        ["Market", "Ticker", "Company", "Close", "Change", "Return", "Volume"]
    ]
    table_rows.extend(
        [
            row.market,
            row.ticker,
            row.name,
            _price(row.close, row.currency),
            _signed_number(row.change),
            _percent(row.changepct),
            _integer(row.volume),
        ]
        for row in rows
    )
    return _table(
        table_rows,
        renderer=renderer,
        col_widths=[48, 55, 160, 60, 58, 60, 63],
        numeric_columns=(3, 4, 5, 6),
        return_column=5,
        long=True,
    )


def _price_anomaly_table(
    rows: Sequence[PriceAnomaly],
    *,
    renderer: PdfRenderer,
) -> LongTable:
    table_rows: list[list[object]] = [
        ["Market", "Ticker", "Company", "Flag", "Close", "Return", "Range", "Volume"]
    ]
    table_rows.extend(
        [
            row.market,
            row.ticker,
            row.name,
            row.anomaly_type.replace("_", " ").title(),
            _price(row.close, None),
            _percent(row.changepct),
            _percent(row.intraday_range_pct),
            _integer(row.volume),
        ]
        for row in rows
    )
    return _table(
        table_rows,
        renderer=renderer,
        col_widths=[43, 48, 120, 105, 50, 50, 45, 43],
        numeric_columns=(4, 5, 6, 7),
        return_column=5,
        font_size=6.6,
        long=True,
    )


def _volume_anomaly_table(
    rows: Sequence[VolumeAnomaly],
    *,
    renderer: PdfRenderer,
) -> LongTable:
    table_rows: list[list[object]] = [
        ["Market", "Ticker", "Company", "Volume", "20-Day Avg", "Multiple", "Return"]
    ]
    table_rows.extend(
        [
            row.market,
            row.ticker,
            row.name,
            _integer(row.volume),
            _integer(row.average_volume_20d),
            f"{row.volume_multiple:.2f}x",
            _percent(row.changepct),
        ]
        for row in rows
    )
    return _table(
        table_rows,
        renderer=renderer,
        col_widths=[48, 55, 164, 67, 67, 52, 51],
        numeric_columns=(3, 4, 5, 6),
        return_column=6,
        long=True,
    )


def _scope_table(
    report: EODDataDailyMarketReport,
    *,
    renderer: PdfRenderer,
) -> Table:
    universe = report.universe
    return _table(
        [
            ["Scope Fact", "Count"],
            ["All EODData bars on date", f"{universe.source_bar_count:,}"],
            ["Equity bars analyzed", f"{universe.equity_bar_count:,}"],
            ["Non-equity bars excluded", f"{universe.non_equity_bar_count:,}"],
            ["Unclassified bars excluded", f"{universe.unclassified_bar_count:,}"],
            ["Equities without preceding close", f"{report.missing_comparison:,}"],
        ],
        renderer=renderer,
        col_widths=[380, 124],
        numeric_columns=(1,),
    )


def _table(
    rows: Sequence[Sequence[object]],
    *,
    renderer: PdfRenderer,
    col_widths: Sequence[float],
    numeric_columns: Iterable[int] = (),
    return_column: int | None = None,
    centered: bool = False,
    font_size: float = 7.4,
    long: bool = False,
) -> Any:
    numeric = frozenset(numeric_columns)
    cell_style = ParagraphStyle(
        "DailyMarketCell",
        parent=renderer.styles.small,
        fontSize=font_size,
        leading=font_size + 1.8,
    )
    numeric_style = ParagraphStyle(
        "DailyMarketNumericCell",
        parent=cell_style,
        alignment=TA_RIGHT,
    )
    centered_style = ParagraphStyle(
        "DailyMarketCenteredCell",
        parent=cell_style,
        alignment=TA_CENTER,
    )
    header_style = ParagraphStyle(
        "DailyMarketHeaderCell",
        parent=cell_style,
        fontName=renderer.theme.body_semibold_font,
        textColor=renderer.theme.white,
        alignment=TA_CENTER if centered else cell_style.alignment,
    )
    wrapped = [
        [
            Paragraph(
                escape(str(value)),
                header_style
                if row_index == 0
                else numeric_style
                if index in numeric
                else centered_style
                if centered
                else cell_style,
            )
            for index, value in enumerate(row)
        ]
        for row_index, row in enumerate(rows)
    ]
    table_class = LongTable if long else Table
    table = table_class(wrapped, colWidths=list(col_widths), repeatRows=1)
    commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), renderer.theme.primary),
        ("TEXTCOLOR", (0, 0), (-1, 0), renderer.theme.white),
        ("FONTNAME", (0, 0), (-1, 0), renderer.theme.body_semibold_font),
        ("GRID", (0, 0), (-1, -1), 0.35, renderer.theme.light_grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [renderer.theme.white, "#F7F7F7"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if centered:
        commands.append(("ALIGN", (1, 1), (-1, -1), "CENTER"))
    if return_column is not None:
        for row_index, row in enumerate(rows[1:], start=1):
            raw = str(row[return_column]).strip()
            if raw.startswith("-"):
                commands.append(
                    (
                        "TEXTCOLOR",
                        (return_column, row_index),
                        (return_column, row_index),
                        renderer.theme.accent,
                    )
                )
    table.setStyle(TableStyle(commands))
    return table


def _percent(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value * Decimal(100):+.2f}%"


def _signed_number(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value:+,.4f}"


def _price(value: Decimal, currency: str | None) -> str:
    prefix = "$" if currency == "USD" else ""
    suffix = "" if currency in {None, "USD"} else f" {currency}"
    return f"{prefix}{value:,.4f}{suffix}"


def _integer(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.0f}"


def _compact_number(value: Decimal) -> str:
    absolute = abs(value)
    for divisor, suffix in (
        (Decimal("1000000000000"), "T"),
        (Decimal("1000000000"), "B"),
        (Decimal("1000000"), "M"),
        (Decimal("1000"), "K"),
    ):
        if absolute >= divisor:
            return f"{value / divisor:,.1f}{suffix}"
    return f"{value:,.0f}"
