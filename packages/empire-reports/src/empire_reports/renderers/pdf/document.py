from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from reportlab.platypus import BaseDocTemplate, PageTemplate

from empire_reports.branding import BrandingConfig, register_brand_fonts


@dataclass(frozen=True, slots=True)
class DocumentSpec:
    title: str
    author: str = "Empire"
    subject: str | None = None
    creator: str = "empire-reports"
    keywords: tuple[str, ...] = ()


PdfDocument = BaseDocTemplate


def make_doc(
    *,
    out_path: Path,
    templates: Sequence[PageTemplate],
    spec: DocumentSpec,
) -> BaseDocTemplate:
    out_path = Path(out_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = BaseDocTemplate(str(out_path))
    doc.title = spec.title
    doc.author = spec.author
    doc.creator = spec.creator
    if spec.subject:
        doc.subject = spec.subject
    if spec.keywords:
        doc.keywords = ", ".join(spec.keywords)
    doc.addPageTemplates(list(templates))
    return doc


def build_pdf(
    *,
    doc: BaseDocTemplate,
    story: Sequence[object],
    out_path: Path,
    branding: BrandingConfig | None = None,
) -> Path:
    register_brand_fonts(branding)
    resolved = Path(out_path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    doc.build(list(story))
    return resolved
