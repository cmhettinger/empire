"""Render an extensible gallery of shared Empire PDF components."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    NextPageTemplate,
    PageBreak,
    Paragraph,
    Table,
    TableStyle,
)

from empire_reports.contracts import RenderContext, RenderResult, ReportMetadata
from empire_reports.renderers.pdf import (
    HeaderFooterSpec,
    PdfRenderer,
    QuoteTileSpec,
    appendix_divider_page,
    intentionally_blank_page,
    paragraph,
    professional_letter_disclaimer_page,
    professional_letter_title_page,
    quote_tile_grid,
    section_divider_page,
    section_heading,
    spacer,
)
from empire_reports.renderers.pdf.charts import ChartBlock, ChartBlockSpec
from empire_reports.renderers.pdf.images import scaled_image
from empire_reports.renderers.pdf.tables import simple_table


REPORT_ID = "empire-reports.playground"
DEFAULT_OUTPUT_FILENAME = "report-playground.pdf"
HEADER_TEXT = "EMPIRE REPORT COMPONENT PLAYGROUND"
FOOTER_TEXT = "DEVELOPER REFERENCE / NOT A PRODUCTION REPORT"


PlaygroundBuilder = Callable[[PdfRenderer, date], Sequence[object]]


@dataclass(frozen=True, slots=True)
class PlaygroundPage:
    """One independently extensible page in the component gallery."""

    key: str
    title: str
    description: str
    options: tuple[str, ...]
    builder: PlaygroundBuilder
    template_key: str = "letter_body"
    annotate: bool = True


def playground_pages() -> tuple[PlaygroundPage, ...]:
    """Return the ordered gallery registry.

    Add a new shared component by implementing one small builder and appending
    one entry here. Standard pages automatically receive the component title,
    writeup, and options summary.
    """

    return (
        PlaygroundPage(
            key="professional-title-page",
            title="Professional title page",
            description=(
                "A full-page Empire cover for polished letter-format reports. "
                "This example uses its subtitle as the component writeup."
            ),
            options=(
                "title and subtitle",
                "report date and date label",
                "header, classification, logo, and watermark",
            ),
            builder=_professional_title_page,
            template_key="letter_title",
            annotate=False,
        ),
        PlaygroundPage(
            key="typography-and-spacing",
            title="Typography and spacing",
            description=(
                "The shared styles and small content helpers establish consistent "
                "hierarchy, rhythm, and brand typography across reports."
            ),
            options=(
                "section and subsection headings",
                "body, small, and code text",
                "explicit vertical spacing",
            ),
            builder=_typography_page,
        ),
        PlaygroundPage(
            key="quote-tile-grid",
            title="Quote tile grid",
            description=(
                "Quote tiles summarize price movement with semantic positive, "
                "negative, neutral, unavailable, and status states."
            ),
            options=(
                "four-column default grid",
                "three-column compact grid",
                "custom height and every semantic state",
            ),
            builder=_quote_tile_page,
        ),
        PlaygroundPage(
            key="simple-table",
            title="Simple table",
            description=(
                "The shared table applies branded headers, alternating rows, "
                "compact typography, grid lines, and optional repeated headers."
            ),
            options=(
                "repeating header for multi-page data",
                "non-repeating header for compact facts",
            ),
            builder=_simple_table_page,
        ),
        PlaygroundPage(
            key="scaled-image",
            title="Scaled image",
            description=(
                "The image helper preserves aspect ratio, never upscales, and "
                "fits an asset within caller-provided width and height bounds."
            ),
            options=(
                "large landscape-safe bounds",
                "compact thumbnail bounds",
            ),
            builder=_scaled_image_page,
        ),
        PlaygroundPage(
            key="chart-block",
            title="Chart block",
            description=(
                "ChartBlock keeps a raster visual and optional caption together, "
                "scaling both to the available page area."
            ),
            options=(
                "caption and caption gap",
                "padding",
                "upscaling disabled",
            ),
            builder=_chart_block_page,
        ),
        PlaygroundPage(
            key="professional-disclaimer-page",
            title="Professional disclaimer page",
            description=(
                "A full-page branded disclaimer with configurable labels, warning "
                "copy, and quote artwork."
            ),
            options=(
                "header and footer labels",
                "warning text",
                "replaceable quote image",
            ),
            builder=_professional_disclaimer_page,
            template_key="letter_title",
            annotate=False,
        ),
        PlaygroundPage(
            key="appendix-divider-grey",
            title="Appendix divider page - grey rail",
            description=(
                "A full-page appendix divider using the neutral Empire rail."
            ),
            options=(
                "appendix title and eyebrow",
                "optional description and page number",
                "grey rail tone",
            ),
            builder=_appendix_divider_grey_page,
            template_key="letter_title",
            annotate=False,
        ),
        PlaygroundPage(
            key="appendix-divider-red",
            title="Appendix divider page - red rail",
            description=(
                "The same full-page appendix divider using the primary Empire rail."
            ),
            options=(
                "appendix title and eyebrow",
                "optional description and page number",
                "red rail tone",
            ),
            builder=_appendix_divider_red_page,
            template_key="letter_title",
            annotate=False,
        ),
        PlaygroundPage(
            key="section-divider-grey",
            title="Section divider page - grey rail",
            description=(
                "A full-page section divider using the neutral Empire rail."
            ),
            options=(
                "section title and fixed eyebrow",
                "optional description and page number",
                "grey rail tone",
            ),
            builder=_section_divider_grey_page,
            template_key="letter_title",
            annotate=False,
        ),
        PlaygroundPage(
            key="section-divider-red",
            title="Section divider page - red rail",
            description=(
                "The same full-page section divider using the primary Empire rail."
            ),
            options=(
                "section title and fixed eyebrow",
                "optional description and page number",
                "red rail tone",
            ),
            builder=_section_divider_red_page,
            template_key="letter_title",
            annotate=False,
        ),
        PlaygroundPage(
            key="intentionally-blank-grey",
            title="Intentionally blank page - grey rail",
            description=(
                "A quiet branded spacer page using the neutral Empire rail."
            ),
            options=(
                "fixed plain-black message",
                "optional page number",
                "grey rail tone",
            ),
            builder=_intentionally_blank_grey_page,
            template_key="letter_title",
            annotate=False,
        ),
        PlaygroundPage(
            key="intentionally-blank-red",
            title="Intentionally blank page - red rail",
            description=(
                "The same quiet spacer page using the primary Empire rail."
            ),
            options=(
                "fixed plain-black message",
                "optional page number",
                "red rail tone",
            ),
            builder=_intentionally_blank_red_page,
            template_key="letter_title",
            annotate=False,
        ),
    )


def render_report_playground(
    *,
    output_path: str | Path | None = None,
    report_date: date | None = None,
) -> RenderResult:
    """Render the current shared-component gallery to one deterministic path."""

    effective_date = report_date or date.today()
    resolved_output_path = Path(
        output_path if output_path is not None else default_playground_output_path()
    ).expanduser().resolve()
    metadata = ReportMetadata(
        report_id=REPORT_ID,
        title="Report Component Playground",
        subtitle="Shared PDF components and their supported presentation options",
        as_of=effective_date,
        description="Developer gallery for shared empire-reports PDF components.",
        tags=("empire", "reports", "pdf", "components", "playground"),
    )
    renderer = PdfRenderer(
        metadata=metadata,
        context=RenderContext(output_dir=resolved_output_path.parent),
    )
    pages = playground_pages()
    _validate_pages(pages)
    story = _playground_story(renderer, effective_date, pages)
    return renderer.render(
        story,
        out_path=resolved_output_path,
        header_footer=HeaderFooterSpec(
            header_center_text=HEADER_TEXT,
            header_right_text=effective_date.isoformat(),
            footer_text=FOOTER_TEXT,
            page_number_offset=1,
        ),
    )


def default_playground_output_path() -> Path:
    """Resolve the playground artifact under Empire's temporary-work root."""

    temp_root = Path(os.environ.get("EMPIRE_TEMP_DIR", "/tmp"))
    return temp_root / DEFAULT_OUTPUT_FILENAME


def _playground_story(
    renderer: PdfRenderer,
    report_date: date,
    pages: Sequence[PlaygroundPage],
) -> list[object]:
    story: list[object] = []
    for index, page in enumerate(pages):
        if index:
            story.extend([NextPageTemplate(page.template_key), PageBreak()])
        if page.annotate:
            story.extend(_page_annotation(renderer, page))
        story.extend(page.builder(renderer, report_date))
    return story


def _page_annotation(
    renderer: PdfRenderer,
    page: PlaygroundPage,
) -> list[object]:
    options = "; ".join(page.options)
    return [
        section_heading(page.title, styles=renderer.styles),
        paragraph(page.description, styles=renderer.styles),
        Paragraph(f"<b>Options shown:</b> {options}.", renderer.styles.small),
        spacer(12),
    ]


def _professional_title_page(
    renderer: PdfRenderer,
    report_date: date,
) -> Sequence[object]:
    return professional_letter_title_page(
        title="Report Playground",
        subtitle=(
            "Configurable title, subtitle, date, labels, logo, and watermark"
        ),
        report_date=report_date,
        date_label="BUILD",
        header_text=HEADER_TEXT,
        footer_text=FOOTER_TEXT,
        classification_text=FOOTER_TEXT,
        branding=renderer.branding,
        theme=renderer.theme,
    )


def _typography_page(renderer: PdfRenderer, report_date: date) -> Sequence[object]:
    _ = report_date
    return [
        Paragraph("Subsection heading", renderer.styles.subheading),
        paragraph(
            "Body text is optimized for readable report narrative. It uses the "
            "shared body font, color, line height, and paragraph spacing.",
            styles=renderer.styles,
        ),
        spacer(10),
        Paragraph(
            "Small text supports captions, annotations, and secondary facts "
            "without competing with the report narrative.",
            renderer.styles.small,
        ),
        spacer(16),
        Paragraph(
            "report_id = 'empire-reports.playground'<br/>"
            "renderer.render(story, out_path=output_path)",
            renderer.styles.code,
        ),
    ]


def _quote_tile_page(renderer: PdfRenderer, report_date: date) -> Sequence[object]:
    _ = report_date
    return [
        Paragraph("Default grid", renderer.styles.subheading),
        quote_tile_grid(
            (
                QuoteTileSpec("UP", 101.25, 1.25, 1.25),
                QuoteTileSpec("DOWN", 98.75, -1.25, -1.25),
                QuoteTileSpec("FLAT", 100.00, 0.00, 0.00),
                QuoteTileSpec("NEW", 12.00, None, None),
                QuoteTileSpec("CLOSED", None, None, None, "MARKET CLOSED"),
            ),
            columns=4,
            tile_height=72,
            theme=renderer.theme,
        ),
        spacer(16),
        Paragraph("Compact grid", renderer.styles.subheading),
        quote_tile_grid(
            (
                QuoteTileSpec("GAIN", 42.40, 2.40, 6.00),
                QuoteTileSpec("LOSS", 18.80, -1.20, -6.00),
                QuoteTileSpec("PENDING", None, None, None, "NO DATA"),
            ),
            columns=3,
            tile_height=56,
            theme=renderer.theme,
        ),
    ]


def _simple_table_page(renderer: PdfRenderer, report_date: date) -> Sequence[object]:
    return [
        Paragraph("Repeatable data header", renderer.styles.subheading),
        simple_table(
            (
                ("Component", "State", "As of", "Notes"),
                ("Title page", "Ready", report_date.isoformat(), "Full-page"),
                ("Quote tiles", "Ready", report_date.isoformat(), "Responsive"),
                ("Simple table", "Ready", report_date.isoformat(), "Repeatable header"),
                ("Chart block", "Ready", report_date.isoformat(), "Caption aware"),
            ),
            theme=renderer.theme,
            repeat_header=True,
        ),
        spacer(22),
        Paragraph("Compact fact table", renderer.styles.subheading),
        simple_table(
            (
                ("Fact", "Value"),
                ("Output", "PDF"),
                ("Page size", "US Letter"),
                ("Audience", "Report developers"),
            ),
            theme=renderer.theme,
            repeat_header=False,
        ),
    ]


def _scaled_image_page(renderer: PdfRenderer, report_date: date) -> Sequence[object]:
    _ = report_date
    image_path = renderer.assets.image_path("buffett-no-crying.png")
    large = scaled_image(image_path, max_width=260, max_height=230)
    small = scaled_image(image_path, max_width=130, max_height=115)
    label_style = ParagraphStyle(
        "PlaygroundImageLabel",
        parent=renderer.styles.small,
        alignment=TA_CENTER,
    )
    table = Table(
        (
            (large, small),
            (
                Paragraph("max 260 x 230 pt", label_style),
                Paragraph("max 130 x 115 pt", label_style),
            ),
        ),
        colWidths=(300, 160),
    )
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return [table]


def _chart_block_page(renderer: PdfRenderer, report_date: date) -> Sequence[object]:
    _ = report_date
    chart_path = renderer.branding.logo_path(
        color="color",
        lockup="horizontal",
        size="512h",
    )
    return [
        ChartBlock(
            ChartBlockSpec(
                image_path=chart_path,
                caption=(
                    "Example raster visual with a caption kept inside the same "
                    "flowable. Production reports can supply any generated chart image."
                ),
                caption_gap=8,
                allow_upscale=False,
                pad=8,
            ),
            styles=renderer.styles,
        )
    ]


def _professional_disclaimer_page(
    renderer: PdfRenderer,
    report_date: date,
) -> Sequence[object]:
    _ = report_date
    return professional_letter_disclaimer_page(
        header_text=f"{HEADER_TEXT} / DISCLAIMER COMPONENT",
        footer_text=FOOTER_TEXT,
        warning_text=(
            "Full-page component with configurable labels, warning text, and quote image"
        ),
        assets=renderer.assets,
        branding=renderer.branding,
        theme=renderer.theme,
    )


def _appendix_divider_grey_page(
    renderer: PdfRenderer,
    report_date: date,
) -> Sequence[object]:
    _ = report_date
    return appendix_divider_page(
        title="APPENDIX A",
        description=(
            "Supporting information, reference data, and additional material."
        ),
        rail_tone="grey",
        page_number_offset=1,
        branding=renderer.branding,
        theme=renderer.theme,
    )


def _appendix_divider_red_page(
    renderer: PdfRenderer,
    report_date: date,
) -> Sequence[object]:
    _ = report_date
    return appendix_divider_page(
        title="APPENDIX B",
        description="Methodology, definitions, and supporting schedules.",
        rail_tone="red",
        page_number_offset=1,
        branding=renderer.branding,
        theme=renderer.theme,
    )


def _section_divider_grey_page(
    renderer: PdfRenderer,
    report_date: date,
) -> Sequence[object]:
    _ = report_date
    return section_divider_page(
        title="PORTFOLIO ANALYSIS",
        description="Positioning, exposures, performance, and key observations.",
        rail_tone="grey",
        page_number_offset=1,
        branding=renderer.branding,
        theme=renderer.theme,
    )


def _section_divider_red_page(
    renderer: PdfRenderer,
    report_date: date,
) -> Sequence[object]:
    _ = report_date
    return section_divider_page(
        title="MARKET OVERVIEW",
        description=(
            "A summary of current market conditions, trends, and key indicators."
        ),
        rail_tone="red",
        page_number_offset=1,
        branding=renderer.branding,
        theme=renderer.theme,
    )


def _intentionally_blank_grey_page(
    renderer: PdfRenderer,
    report_date: date,
) -> Sequence[object]:
    _ = report_date
    return intentionally_blank_page(
        rail_tone="grey",
        page_number_offset=1,
        branding=renderer.branding,
        theme=renderer.theme,
    )


def _intentionally_blank_red_page(
    renderer: PdfRenderer,
    report_date: date,
) -> Sequence[object]:
    _ = report_date
    return intentionally_blank_page(
        rail_tone="red",
        page_number_offset=1,
        branding=renderer.branding,
        theme=renderer.theme,
    )


def _validate_pages(pages: Sequence[PlaygroundPage]) -> None:
    keys = [page.key for page in pages]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"Duplicate playground page keys: {duplicates}")
    if not pages:
        raise ValueError("The report playground must contain at least one page.")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m empire_reports.playground",
        description="Render the shared Empire PDF component playground.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output PDF path (default: "
            "$EMPIRE_TEMP_DIR/report-playground.pdf, or /tmp when unset)."
        ),
    )
    parser.add_argument(
        "--date",
        type=_parse_date,
        default=date.today(),
        help="Date displayed by date-aware components (default: today).",
    )
    args = parser.parse_args(argv)
    result = render_report_playground(
        output_path=args.output,
        report_date=args.date,
    )
    print(result.primary_artifact.resolved_path())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
