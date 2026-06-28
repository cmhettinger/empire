from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from reportlab.lib.pagesizes import landscape, legal, letter, portrait
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Frame, PageTemplate

from empire_reports.branding import ReportTheme


Orientation = Literal["portrait", "landscape"]
PageSizeName = Literal["LETTER", "LEGAL", "CUSTOM"]
TemplateRole = Literal["title", "body", "chart"]


def inches(value: float) -> float:
    return float(value) * inch


@dataclass(frozen=True, slots=True)
class Margins:
    left: float
    right: float
    top: float
    bottom: float

    @classmethod
    def inches(cls, left: float, right: float, top: float, bottom: float) -> "Margins":
        return cls(
            left=inches(left),
            right=inches(right),
            top=inches(top),
            bottom=inches(bottom),
        )


@dataclass(frozen=True, slots=True)
class PageSpec:
    key: str
    size_name: PageSizeName = "LETTER"
    orientation: Orientation = "portrait"
    margins: Margins = Margins.inches(0.75, 0.75, 0.75, 0.75)
    role: TemplateRole = "body"
    custom_size: tuple[float, float] | None = None

    def pagesize(self) -> tuple[float, float]:
        if self.size_name == "LETTER":
            base = letter
        elif self.size_name == "LEGAL":
            base = legal
        elif self.size_name == "CUSTOM":
            if self.custom_size is None:
                raise ValueError("custom_size is required when size_name='CUSTOM'")
            base = self.custom_size
        else:
            raise ValueError(f"Unsupported page size: {self.size_name}")

        return portrait(base) if self.orientation == "portrait" else landscape(base)


@dataclass(frozen=True, slots=True)
class FrameSpec:
    id: str = "body"
    show_boundary: bool = False


@dataclass(frozen=True, slots=True)
class HeaderFooterSpec:
    header_text: str | None = None
    header_center_text: str | None = None
    header_right_text: str | None = None
    footer_text: str = "INTERNAL USE ONLY"
    show_header: bool | None = None
    show_footer: bool | None = None
    show_page_number: bool | None = None
    page_number_offset: int = 0


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    page: PageSpec
    frame: FrameSpec = FrameSpec()
    header_footer: HeaderFooterSpec = HeaderFooterSpec()
    theme: ReportTheme = ReportTheme()


def make_body_frame(page_spec: PageSpec, frame_spec: FrameSpec) -> Frame:
    width, height = page_spec.pagesize()
    margins = page_spec.margins
    return Frame(
        margins.left,
        margins.bottom,
        width - margins.left - margins.right,
        height - margins.top - margins.bottom,
        id=frame_spec.id,
        showBoundary=int(frame_spec.show_boundary),
    )


def make_page_template(spec: TemplateSpec) -> PageTemplate:
    frame = make_body_frame(spec.page, spec.frame)

    def _on_page(canvas: Canvas, doc: object) -> None:
        draw_header_footer(canvas, page_spec=spec.page, spec=spec.header_footer, theme=spec.theme)

    return PageTemplate(
        id=spec.page.key,
        pagesize=spec.page.pagesize(),
        frames=[frame],
        onPage=_on_page,
    )


class TemplateRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, PageTemplate] = {}

    def add(self, template: PageTemplate) -> None:
        self._templates[template.id] = template

    def get(self, key: str) -> PageTemplate:
        if key not in self._templates:
            raise KeyError(f"Unknown template key: {key}; known={sorted(self._templates)}")
        return self._templates[key]

    def all(self) -> list[PageTemplate]:
        return list(self._templates.values())


def draw_header_footer(
    canvas: Canvas,
    *,
    page_spec: PageSpec,
    spec: HeaderFooterSpec,
    theme: ReportTheme,
) -> None:
    canvas.saveState()
    width, height = page_spec.pagesize()
    margins = page_spec.margins

    default_header, default_footer, default_number = _defaults_for_role(page_spec.role)
    show_header = default_header if spec.show_header is None else spec.show_header
    show_footer = default_footer if spec.show_footer is None else spec.show_footer
    show_number = default_number if spec.show_page_number is None else spec.show_page_number

    header_rule_y = height - margins.top + 2
    header_text_y = height - margins.top + 10
    footer_rule_y = margins.bottom - 8
    footer_text_y = margins.bottom - 22

    canvas.setFont(theme.body_font, 9)

    if show_header and (spec.header_text or spec.header_center_text or spec.header_right_text):
        canvas.setFillColor(theme.dark_grey)
        if spec.header_text:
            canvas.drawString(margins.left, header_text_y, spec.header_text)
        if spec.header_center_text:
            canvas.drawCentredString(width / 2.0, header_text_y, spec.header_center_text)
        if spec.header_right_text:
            canvas.drawRightString(width - margins.right, header_text_y, spec.header_right_text)
        canvas.setStrokeColor(theme.primary)
        canvas.setLineWidth(1.25)
        canvas.line(margins.left, header_rule_y, width - margins.right, header_rule_y)

    if show_footer:
        canvas.setStrokeColor(theme.light_grey)
        canvas.setLineWidth(1.0)
        canvas.line(margins.left, footer_rule_y, width - margins.right, footer_rule_y)
        canvas.setFillColor(theme.dark_grey)
        canvas.drawCentredString(width / 2.0, footer_text_y, spec.footer_text)

    if show_number:
        page_number = max(1, int(canvas.getPageNumber()) - int(spec.page_number_offset))
        canvas.setFillColor(theme.dark_grey)
        canvas.drawRightString(width - margins.right, footer_text_y, f"Page {page_number}")

    canvas.restoreState()


def _defaults_for_role(role: str) -> tuple[bool, bool, bool]:
    if (role or "body").lower() == "title":
        return False, False, False
    return True, True, True
