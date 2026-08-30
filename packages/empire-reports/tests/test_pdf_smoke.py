from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from reportlab.platypus import NextPageTemplate, PageBreak

from empire_reports.contracts import RenderContext, ReportMetadata
from empire_reports.renderers.pdf.components import _quote_tile_palette
from empire_reports.renderers.pdf import (
    HeaderFooterSpec,
    ChartPage,
    IntentionallyBlankPage,
    MetricCardSpec,
    MetricDetailRow,
    MetricDetailSection,
    MetricsPage,
    NotesPage,
    PdfRenderer,
    QuoteTileSpec,
    SectionDividerPage,
    appendix_divider_page,
    chart_page,
    chart_page_layout,
    chart_page_template_key,
    intentionally_blank_page,
    metrics_page,
    notes_page,
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


def test_notes_page_renders_both_rail_tones(tmp_path: Path) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(
            report_id="notes-page",
            title="Notes Page",
        ),
        context=RenderContext(output_dir=tmp_path),
    )
    grey_page = notes_page(
        rail_tone="grey",
        branding=renderer.branding,
        theme=renderer.theme,
    )
    red_page = notes_page(
        rail_tone="red",
        show_page_number=False,
        branding=renderer.branding,
        theme=renderer.theme,
    )

    assert isinstance(grey_page[0], NotesPage)
    assert grey_page[0].rail_tone == "grey"

    result = renderer.render([*grey_page, PageBreak(), *red_page])

    artifact = result.primary_artifact
    assert artifact.exists
    assert artifact.resolved_path().stat().st_size > 20_000


def test_metrics_page_renders_maximum_configuration_both_rail_tones(
    tmp_path: Path,
) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(
            report_id="metrics-page",
            title="Metrics Page",
        ),
        context=RenderContext(output_dir=tmp_path),
    )
    icon = renderer.assets.icon_path
    metrics = (
        MetricCardSpec("128", "Pages", icon("document-1.svg")),
        MetricCardSpec("6", "Data Sources", icon("database-1.svg")),
        MetricCardSpec("24", "Figures", icon("bar-chart-1.svg")),
        MetricCardSpec("1.8", "Runtime", icon("stopwatch-1.svg"), "sec"),
    )
    sections = tuple(
        MetricDetailSection(
            f"Section {index}",
            tuple(
                MetricDetailRow(f"Detail {row}", f"Value {index}.{row}")
                for row in range(1, 5)
            ),
            icon("document-3.svg"),
        )
        for index in range(1, 9)
    )
    grey_page = metrics_page(
        title="REPORT INFORMATION",
        metrics=metrics,
        sections=sections,
        rail_tone="grey",
        branding=renderer.branding,
        theme=renderer.theme,
    )
    red_page = metrics_page(
        title="REPORT INFORMATION",
        metrics=metrics[:2],
        sections=sections[:3],
        rail_tone="red",
        show_page_number=False,
        branding=renderer.branding,
        theme=renderer.theme,
    )

    assert isinstance(grey_page[0], MetricsPage)
    assert len(grey_page[0].metrics) == 4
    assert len(grey_page[0].sections) == 8

    result = renderer.render([*grey_page, PageBreak(), *red_page])

    artifact = result.primary_artifact
    assert artifact.exists
    assert artifact.resolved_path().stat().st_size > 20_000


def test_metrics_page_enforces_configuration_bounds(tmp_path: Path) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(report_id="metric-bounds", title="Metric Bounds"),
        context=RenderContext(output_dir=tmp_path),
    )
    icon = renderer.assets.icon_path("document-1.svg")
    metric = MetricCardSpec("1", "Metric", icon)
    section = MetricDetailSection(
        "Section",
        (MetricDetailRow("Label", "Value"),),
        icon,
    )

    with pytest.raises(ValueError, match="between 1 and 4 metric cards"):
        metrics_page(title="Metrics", metrics=(), sections=(section,))
    with pytest.raises(ValueError, match="between 1 and 8 detail sections"):
        metrics_page(title="Metrics", metrics=(metric,), sections=())
    with pytest.raises(ValueError, match="between 1 and 8 detail sections"):
        metrics_page(
            title="Metrics",
            metrics=(metric,),
            sections=tuple(section for _ in range(9)),
        )


def test_metrics_page_rejects_detail_content_that_cannot_fit(tmp_path: Path) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(report_id="metric-overflow", title="Metric Overflow"),
        context=RenderContext(output_dir=tmp_path),
    )
    icon = renderer.assets.icon_path("document-1.svg")
    page = metrics_page(
        title="Metrics",
        metrics=(MetricCardSpec("1", "Metric", icon),),
        sections=(
            MetricDetailSection(
                "Oversized",
                tuple(
                    MetricDetailRow(f"Label {index}", f"Value {index}")
                    for index in range(30)
                ),
                icon,
            ),
        ),
        branding=renderer.branding,
        theme=renderer.theme,
    )

    with pytest.raises(ValueError, match="Reduce the number of detail rows"):
        renderer.render(page)


def test_chart_page_renders_all_supported_page_geometries(tmp_path: Path) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(report_id="chart-pages", title="Chart Pages"),
        context=RenderContext(output_dir=tmp_path),
    )
    chart_path = renderer.assets.image_path("chart-page-example.svg")
    raster_path = renderer.assets.image_path("buffett-no-crying.png")
    combinations = (
        ("LETTER", "portrait"),
        ("LETTER", "landscape"),
        ("LEGAL", "portrait"),
        ("LEGAL", "landscape"),
    )
    story: list[object] = [paragraph("Chart page geometry test", styles=renderer.styles)]
    for index, (page_size, orientation) in enumerate(combinations):
        template_key = chart_page_template_key(page_size, orientation)
        page = chart_page(
            title=f"{page_size} {orientation}",
            description="Chart artwork includes its axes, legend, and source.",
            chart_image_path=raster_path if index == 0 else chart_path,
            page_size=page_size,
            orientation=orientation,
            accent_tone="red" if index % 2 else "grey",
            show_chart_border=bool(index % 2),
            branding=renderer.branding,
            theme=renderer.theme,
        )
        assert isinstance(page[0], ChartPage)
        assert page[0].required_template_key == template_key
        story.extend([NextPageTemplate(template_key), PageBreak(), *page])

    result = renderer.render(story)

    artifact = result.primary_artifact
    assert artifact.exists
    assert artifact.resolved_path().stat().st_size > 20_000


def test_chart_page_requires_matching_page_template(tmp_path: Path) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(
            report_id="chart-page-template",
            title="Chart Page Template",
        ),
        context=RenderContext(output_dir=tmp_path),
    )
    page = chart_page(
        title="Landscape chart",
        description="This page requires the landscape chart template.",
        chart_image_path=renderer.assets.image_path("chart-page-example.svg"),
        orientation="landscape",
        branding=renderer.branding,
        theme=renderer.theme,
    )

    with pytest.raises(ValueError, match="chart_letter_landscape"):
        renderer.render(page)


def test_chart_page_layout_reports_exact_chart_box_before_rendering(
    tmp_path: Path,
) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(report_id="chart-layout", title="Chart Layout"),
        context=RenderContext(output_dir=tmp_path),
    )
    title = (
        "AN INTENTIONALLY LONG CHART TITLE THAT CANNOT FIT ON ONE PORTRAIT "
        "LETTER LINE"
    )
    layout = chart_page_layout(
        title=title,
        description="A concise description beneath the chart title.",
        page_size="LETTER",
        orientation="portrait",
        show_chart_border=False,
        theme=renderer.theme,
    )
    bordered = chart_page_layout(
        title=title,
        description="A concise description beneath the chart title.",
        page_size="LETTER",
        orientation="portrait",
        show_chart_border=True,
        theme=renderer.theme,
    )

    assert layout.page_width == pytest.approx(612.0)
    assert layout.page_height == pytest.approx(792.0)
    assert layout.display_title.endswith("...")
    assert "\n" not in layout.display_title
    assert layout.chart_area == layout.chart_box
    assert bordered.chart_box.width == pytest.approx(
        bordered.chart_area.width - 14.0
    )
    assert bordered.chart_box.height == pytest.approx(
        bordered.chart_area.height - 14.0
    )
    assert layout.chart_box.pixel_size(dpi=144) == (
        1066,
        1275,
    )
    with pytest.raises(ValueError, match="dpi must be positive"):
        layout.chart_box.pixel_size(dpi=0)


def test_chart_page_validates_public_parameters(tmp_path: Path) -> None:
    renderer = PdfRenderer(
        metadata=ReportMetadata(report_id="chart-validation", title="Chart Validation"),
        context=RenderContext(output_dir=tmp_path),
    )
    chart_path = renderer.assets.image_path("chart-page-example.svg")

    with pytest.raises(ValueError, match="page_size"):
        chart_page(
            title="Chart",
            description="Description",
            chart_image_path=chart_path,
            page_size="A4",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="accent_tone"):
        chart_page(
            title="Chart",
            description="Description",
            chart_image_path=chart_path,
            accent_tone="blue",  # type: ignore[arg-type]
        )
    with pytest.raises(FileNotFoundError, match="Chart image not found"):
        chart_page(
            title="Chart",
            description="Description",
            chart_image_path=tmp_path / "missing.png",
        )


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
