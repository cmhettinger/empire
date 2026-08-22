from __future__ import annotations

from pathlib import Path
from typing import Sequence

from empire_reports.artifacts import ReportArtifact
from empire_reports.assets import AssetRegistry
from empire_reports.branding import BrandingConfig, register_brand_fonts
from empire_reports.contracts import OutputFormat, RenderContext, RenderResult, ReportMetadata
from empire_reports.paths import default_output_path
from empire_reports.renderers.pdf.document import DocumentSpec, build_pdf, make_doc
from empire_reports.renderers.pdf.layout import (
    HeaderFooterSpec,
    PageSpec,
    TemplateRegistry,
    TemplateSpec,
    make_page_template,
)
from empire_reports.renderers.pdf.styles import ReportStyles, make_report_styles


class PdfRenderer:
    output_format = OutputFormat.PDF

    def __init__(
        self,
        *,
        metadata: ReportMetadata,
        context: RenderContext,
        branding: BrandingConfig | None = None,
        assets: AssetRegistry | None = None,
    ) -> None:
        self.metadata = metadata
        self.context = context
        self.assets = assets or AssetRegistry.discover()
        self.branding = branding or BrandingConfig.discover(assets=self.assets)
        self.theme = register_brand_fonts(self.branding)
        self.styles = make_report_styles(self.theme)

    def default_templates(self, header_footer: HeaderFooterSpec | None = None) -> TemplateRegistry:
        registry = TemplateRegistry()
        registry.add(
            make_page_template(
                TemplateSpec(
                    page=PageSpec(key="letter_title", role="title"),
                    header_footer=HeaderFooterSpec(show_header=False, show_footer=False, show_page_number=False),
                    theme=self.theme,
                )
            )
        )
        registry.add(
            make_page_template(
                TemplateSpec(
                    page=PageSpec(key="letter_body", role="body"),
                    header_footer=header_footer or HeaderFooterSpec(),
                    theme=self.theme,
                )
            )
        )
        return registry

    def render(
        self,
        story: Sequence[object],
        *,
        out_path: Path | None = None,
        templates: TemplateRegistry | None = None,
        header_footer: HeaderFooterSpec | None = None,
        maximum_pages: int | None = None,
        maximum_bytes: int | None = None,
    ) -> RenderResult:
        if maximum_pages is not None and maximum_pages <= 0:
            raise ValueError("maximum_pages must be positive.")
        if maximum_bytes is not None and maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be positive.")
        resolved_path = out_path or default_output_path(
            context=self.context,
            metadata=self.metadata,
            output_format=OutputFormat.PDF,
        )
        registry = templates or self.default_templates(header_footer)
        doc = make_doc(
            out_path=resolved_path,
            templates=registry.all(),
            spec=DocumentSpec(
                title=self.metadata.title,
                author=self.metadata.author,
                subject=self.metadata.description,
                keywords=self.metadata.tags,
            ),
        )
        build_pdf(doc=doc, story=story, out_path=resolved_path, branding=self.branding)
        page_count = int(doc.page)
        byte_count = resolved_path.stat().st_size
        if maximum_pages is not None and page_count > maximum_pages:
            resolved_path.unlink(missing_ok=True)
            raise ValueError(
                f"Rendered PDF has {page_count} pages; limit is {maximum_pages}."
            )
        if maximum_bytes is not None and byte_count > maximum_bytes:
            resolved_path.unlink(missing_ok=True)
            raise ValueError(
                f"Rendered PDF has {byte_count} bytes; limit is {maximum_bytes}."
            )
        artifact = ReportArtifact(
            path=resolved_path,
            output_format=OutputFormat.PDF,
            media_type="application/pdf",
            logical_name=self.metadata.report_id,
        )
        return RenderResult(
            report=self.metadata,
            artifacts=(artifact,),
            generated_at=self.metadata.generated_timestamp(),
        )
