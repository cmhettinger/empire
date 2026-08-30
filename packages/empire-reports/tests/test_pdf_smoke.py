from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from reportlab.platypus import PageBreak

from empire_reports.contracts import RenderContext, ReportMetadata
from empire_reports.renderers.pdf.components import _quote_tile_palette
from empire_reports.renderers.pdf import (
    HeaderFooterSpec,
    IntentionallyBlankPage,
    PdfRenderer,
    QuoteTileSpec,
    SectionDividerPage,
    appendix_divider_page,
    intentionally_blank_page,
    paragraph,
    professional_letter_disclaimer_page,
    professional_letter_title_page,
    quote_tile_grid,
    section_divider_page,
    section_heading,
)


def test_simple_pdf_smoke(tmp_path: Path) -> None:
    metadata = ReportMetadata(
        report_id="smoke",
        title="Smoke Report",
        subtitle="PDF framework smoke test",
        as_of=date(2026, 6, 28),
    )
    renderer = PdfRenderer(metadata=metadata, context=RenderContext(output_dir=tmp_path))
    story = [
        *professional_letter_title_page(
            title=metadata.title,
            subtitle=metadata.subtitle,
            report_date=metadata.as_of,
            classification_text="CONFIDENTIAL",
            branding=renderer.branding,
            theme=renderer.theme,
        ),
        PageBreak(),
        section_heading("Overview", styles=renderer.styles),
        paragraph(
            "This verifies the reusable PDF renderer can build a branded document.",
            styles=renderer.styles,
        ),
    ]

    result = renderer.render(
        story,
        header_footer=HeaderFooterSpec(header_center_text="INTERNAL USE ONLY"),
    )

    artifact = result.primary_artifact
    assert artifact.exists
    assert artifact.resolved_path().suffix == ".pdf"
    assert artifact.resolved_path().stat().st_size > 500


def test_professional_title_page_without_date(tmp_path: Path) -> None:
    metadata = ReportMetadata(
        report_id="no-date-smoke",
        title="No Date Report",
    )
    renderer = PdfRenderer(metadata=metadata, context=RenderContext(output_dir=tmp_path))
    story = professional_letter_title_page(
        title=metadata.title,
        subtitle="No date block",
        report_date=None,
        show_date=False,
        classification_text="PUBLIC",
        branding=renderer.branding,
        theme=renderer.theme,
    )

    result = renderer.render(story)

    artifact = result.primary_artifact
    assert artifact.exists
    assert artifact.resolved_path().stat().st_size > 500


def test_pdf_renderer_enforces_page_and_byte_bounds(tmp_path: Path) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(report_id="bounded", title="Bounded Report"),
        context=RenderContext(output_dir=tmp_path),
    )
    page_path = tmp_path / "too-many-pages.pdf"
    with pytest.raises(ValueError, match="2 pages; limit is 1"):
        renderer.render(
            [
                paragraph("One", styles=renderer.styles),
                PageBreak(),
                paragraph("Two", styles=renderer.styles),
            ],
            out_path=page_path,
            maximum_pages=1,
        )
    assert not page_path.exists()

    byte_path = tmp_path / "too-many-bytes.pdf"
    with pytest.raises(ValueError, match="bytes; limit is 1"):
        renderer.render(
            [paragraph("One", styles=renderer.styles)],
            out_path=byte_path,
            maximum_bytes=1,
        )
    assert not byte_path.exists()


def test_professional_disclaimer_page_uses_brand_assets(tmp_path: Path) -> None:
    metadata = ReportMetadata(
        report_id="disclaimer-smoke",
        title="Disclaimer Report",
    )
    renderer = PdfRenderer(
        metadata=metadata,
        context=RenderContext(output_dir=tmp_path),
    )
    story = professional_letter_disclaimer_page(
        assets=renderer.assets,
        branding=renderer.branding,
        theme=renderer.theme,
    )

    result = renderer.render(story)

    artifact = result.primary_artifact
    assert artifact.exists
    assert artifact.resolved_path().stat().st_size > 10_000


def test_appendix_divider_page_renders_both_rail_tones(tmp_path: Path) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(
            report_id="appendix-divider",
            title="Appendix Divider",
        ),
        context=RenderContext(output_dir=tmp_path),
    )
    story = [
        *appendix_divider_page(
            title="APPENDIX A",
            description="Supporting information and reference data.",
            rail_tone="grey",
            branding=renderer.branding,
            theme=renderer.theme,
        ),
        PageBreak(),
        *appendix_divider_page(
            title="APPENDIX B",
            description="Methodology and supporting schedules.",
            rail_tone="red",
            show_page_number=False,
            branding=renderer.branding,
            theme=renderer.theme,
        ),
    ]

    result = renderer.render(story)

    artifact = result.primary_artifact
    assert artifact.exists
    assert artifact.resolved_path().stat().st_size > 20_000


def test_appendix_divider_page_rejects_unknown_rail_tone() -> None:
    with pytest.raises(ValueError, match="rail_tone"):
        appendix_divider_page(
            title="APPENDIX A",
            rail_tone="blue",  # type: ignore[arg-type]
        )


def test_section_divider_page_reuses_divider_geometry(tmp_path: Path) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(
            report_id="section-divider",
            title="Section Divider",
        ),
        context=RenderContext(output_dir=tmp_path),
    )
    grey_page = section_divider_page(
        title="PORTFOLIO ANALYSIS",
        description="Positioning, exposures, and performance.",
        rail_tone="grey",
        branding=renderer.branding,
        theme=renderer.theme,
    )
    red_page = section_divider_page(
        title="MARKET OVERVIEW",
        description="Current conditions, trends, and key indicators.",
        rail_tone="red",
        branding=renderer.branding,
        theme=renderer.theme,
    )

    assert isinstance(grey_page[0], SectionDividerPage)
    assert grey_page[0].eyebrow_text == "SECTION"

    result = renderer.render([*grey_page, PageBreak(), *red_page])

    artifact = result.primary_artifact
    assert artifact.exists
    assert artifact.resolved_path().stat().st_size > 20_000


def test_intentionally_blank_page_renders_both_rail_tones(tmp_path: Path) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(
            report_id="intentionally-blank",
            title="Intentionally Blank",
        ),
        context=RenderContext(output_dir=tmp_path),
    )
    grey_page = intentionally_blank_page(
        rail_tone="grey",
        branding=renderer.branding,
        theme=renderer.theme,
    )
    red_page = intentionally_blank_page(
        rail_tone="red",
        show_page_number=False,
        branding=renderer.branding,
        theme=renderer.theme,
    )

    assert isinstance(grey_page[0], IntentionallyBlankPage)
    assert grey_page[0].rail_tone == "grey"

    result = renderer.render([*grey_page, PageBreak(), *red_page])

    artifact = result.primary_artifact
    assert artifact.exists
    assert artifact.resolved_path().stat().st_size > 20_000


def test_quote_tile_grid_renders_semantic_market_colors(tmp_path: Path) -> None:
    metadata = ReportMetadata(report_id="quote-tiles", title="Quote Tiles")
    renderer = PdfRenderer(
        metadata=metadata,
        context=RenderContext(output_dir=tmp_path),
    )
    story = [
        quote_tile_grid(
            (
                QuoteTileSpec("UP", 101.25, 1.25, 1.25),
                QuoteTileSpec("DOWN", 98.75, -1.25, -1.25),
                QuoteTileSpec("FLAT", 100.00, 0.00, 0.00),
                QuoteTileSpec("NEW", 12.00, None, None),
                QuoteTileSpec("CLOSED", None, None, None, "MARKET CLOSED"),
            ),
            theme=renderer.theme,
        )
    ]

    result = renderer.render(story)

    artifact = result.primary_artifact
    assert artifact.exists
    assert artifact.resolved_path().stat().st_size > 1_000


def test_quote_tile_headers_and_frames_follow_direction() -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(report_id="quote-palette", title="Quote Palette"),
        context=RenderContext(output_dir=Path(".")),
    )

    positive = _quote_tile_palette(1.0, theme=renderer.theme)
    negative = _quote_tile_palette(-1.0, theme=renderer.theme)
    neutral = _quote_tile_palette(0.0, theme=renderer.theme)

    assert positive.frame.hexval() == "0x1f6b45"
    assert negative.frame == renderer.theme.primary
    assert neutral.frame == renderer.theme.dark_grey
    assert len({positive.frame, negative.frame, neutral.frame}) == 3
