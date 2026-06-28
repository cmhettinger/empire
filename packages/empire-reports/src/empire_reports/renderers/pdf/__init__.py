"""ReportLab-based PDF rendering helpers."""

from empire_reports.renderers.pdf.components import (
    ProfessionalLetterTitlePage,
    cover_page,
    paragraph,
    professional_letter_title_page,
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
    "ProfessionalLetterTitlePage",
    "TemplateRegistry",
    "TemplateSpec",
    "build_pdf",
    "cover_page",
    "inches",
    "make_doc",
    "make_page_template",
    "paragraph",
    "professional_letter_title_page",
    "section_heading",
    "spacer",
]
