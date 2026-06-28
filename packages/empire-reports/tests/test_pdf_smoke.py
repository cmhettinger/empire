from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.platypus import PageBreak

from empire_reports.contracts import RenderContext, ReportMetadata
from empire_reports.renderers.pdf import (
    HeaderFooterSpec,
    PdfRenderer,
    paragraph,
    professional_letter_title_page,
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
        paragraph("This verifies the reusable PDF renderer can build a branded document.", styles=renderer.styles),
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
