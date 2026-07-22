"""ReportLab-based PDF rendering helpers."""

from empire_reports.renderers.pdf.components import (
    ProfessionalLetterDisclaimerPage,
    ProfessionalLetterTitlePage,
    QuoteTileGrid,
    QuoteTileSpec,
    cover_page,
    paragraph,
    professional_letter_disclaimer_page,
    professional_letter_title_page,
    quote_tile_grid,
    section_heading,
    spacer,
)
from empire_reports.renderers.pdf.document import (
    DocumentSpec,
    PdfDocument,
    build_pdf,
    make_doc,
)
from empire_reports.renderers.pdf.layout import (
    FrameSpec,
    HeaderFooterSpec,
    Margins,
    PageSpec,
    TemplateRegistry,
    TemplateSpec,
    inches,
    make_page_template,
)
from empire_reports.renderers.pdf.renderer import PdfRenderer

__all__ = [
    "DocumentSpec",
    "FrameSpec",
    "HeaderFooterSpec",
    "Margins",
    "PageSpec",
    "PdfDocument",
    "PdfRenderer",
    "ProfessionalLetterDisclaimerPage",
    "ProfessionalLetterTitlePage",
    "QuoteTileGrid",
    "QuoteTileSpec",
    "TemplateRegistry",
    "TemplateSpec",
    "build_pdf",
    "cover_page",
    "inches",
    "make_doc",
    "make_page_template",
    "paragraph",
    "professional_letter_disclaimer_page",
    "professional_letter_title_page",
    "quote_tile_grid",
    "section_heading",
    "spacer",
]
