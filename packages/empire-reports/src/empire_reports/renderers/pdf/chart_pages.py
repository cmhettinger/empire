from __future__ import annotations

from dataclasses import dataclass
from html import escape
from math import ceil
from pathlib import Path
from typing import Literal

from reportlab.graphics import renderPDF
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable, Paragraph
from svglib.svglib import svg2rlg

from empire_reports.branding import BrandingConfig, ReportTheme, register_brand_fonts
from empire_reports.renderers.pdf.layout import (
    ChartPageSizeName,
    Orientation,
    PageSpec,
    chart_page_template_key,
)


ChartAccentTone = Literal["grey", "red"]

_SIDE_MARGIN = 0.55 * inch
_HEADER_TOP_MARGIN = 0.48 * inch
_TITLE_DESCRIPTION_GAP = 7.0
_CHART_HEADER_GAP = 0.22 * inch
_CHART_BOTTOM = 0.78 * inch
_CHART_BORDER_PADDING = 7.0


@dataclass(frozen=True, slots=True)
class ChartBox:
    """One chart rectangle expressed in PDF points."""

    x: float
    y: float
    width: float
    height: float

    def pixel_size(self, *, dpi: float = 144.0) -> tuple[int, int]:
        """Return a render size that fully covers this box at the requested DPI."""

        if dpi <= 0:
            raise ValueError("dpi must be positive.")
        return (
            ceil((self.width / inch) * dpi),
            ceil((self.height / inch) * dpi),
        )


@dataclass(frozen=True, slots=True)
class ChartPageLayout:
    """Calculated page and chart geometry shared by callers and ChartPage."""

    page_width: float
    page_height: float
    display_title: str
    title_font_size: float
    title_y: float
    description_font_size: float
    description_y: float
    chart_area: ChartBox
    chart_box: ChartBox


def chart_page_layout(
    *,
    title: str,
    description: str,
    page_size: ChartPageSizeName = "LETTER",
    orientation: Orientation = "portrait",
    show_chart_border: bool = False,
    theme: ReportTheme | None = None,
) -> ChartPageLayout:
    """Calculate the exact chart rectangle before rendering chart artwork."""

    title = title.strip()
    description = description.strip()
    _validate_chart_page_text_and_geometry(
        title=title,
        description=description,
        page_size=page_size,
        orientation=orientation,
    )
    effective_theme = theme or register_brand_fonts()
    page_width, page_height = PageSpec(
        key=chart_page_template_key(page_size, orientation),
        size_name=page_size,
        orientation=orientation,
        role="chart",
    ).pagesize()
    content_width = page_width - (2.0 * _SIDE_MARGIN)
    title_font_size = 26.0 if orientation == "landscape" else 24.0
    display_title = _truncate_title(
        title,
        font_name=effective_theme.display_font,
        font_size=title_font_size,
        maximum_width=content_width,
    )
    header_top = page_height - _HEADER_TOP_MARGIN
    title_y = header_top - title_font_size
    title_bottom = header_top - (title_font_size * 1.16)

    _, description_height, description_font_size = _bounded_paragraph(
        description,
        font_name=effective_theme.body_font,
        maximum_font_size=11.5,
        minimum_font_size=8.5,
        color=effective_theme.dark_grey,
        width=content_width,
        maximum_lines=2,
    )
    description_y = (
        title_bottom - _TITLE_DESCRIPTION_GAP - description_height
    )
    chart_top = description_y - _CHART_HEADER_GAP
    chart_height = chart_top - _CHART_BOTTOM
    if chart_height < 2.0 * inch:
        raise ValueError(
            "ChartPage title and description leave less than two inches "
            "for the chart image."
        )

    chart_area = ChartBox(
        x=_SIDE_MARGIN,
        y=_CHART_BOTTOM,
        width=content_width,
        height=chart_height,
    )
    padding = _CHART_BORDER_PADDING if show_chart_border else 0.0
    chart_box = ChartBox(
        x=chart_area.x + padding,
        y=chart_area.y + padding,
        width=chart_area.width - (2.0 * padding),
        height=chart_area.height - (2.0 * padding),
    )
    return ChartPageLayout(
        page_width=page_width,
        page_height=page_height,
        display_title=display_title,
        title_font_size=title_font_size,
        title_y=title_y,
        description_font_size=description_font_size,
        description_y=description_y,
        chart_area=chart_area,
        chart_box=chart_box,
    )


class ChartPage(Flowable):
    """Minimal full-page branded frame for one caller-provided chart image."""

    def __init__(
        self,
        *,
        title: str,
        description: str,
        chart_image_path: Path,
        page_size: ChartPageSizeName = "LETTER",
        orientation: Orientation = "portrait",
        accent_tone: ChartAccentTone = "red",
        show_chart_border: bool = False,
        show_page_number: bool = True,
        page_number_offset: int = 0,
        allow_upscale: bool = False,
        branding: BrandingConfig | None = None,
        theme: ReportTheme | None = None,
        logo_path: Path | None = None,
    ) -> None:
        super().__init__()
        title = title.strip()
        description = description.strip()
        chart_image_path = Path(chart_image_path)
        _validate_chart_page_text_and_geometry(
            title=title,
            description=description,
            page_size=page_size,
            orientation=orientation,
        )
        if accent_tone not in {"grey", "red"}:
            raise ValueError("accent_tone must be 'grey' or 'red'.")
        if page_number_offset < 0:
            raise ValueError("page_number_offset cannot be negative.")
        if not chart_image_path.is_file():
            raise FileNotFoundError(f"Chart image not found: {chart_image_path}")

        self.title = title
        self.description = description
        self.chart_image_path = chart_image_path
        self.page_size = page_size
        self.orientation = orientation
        self.accent_tone = accent_tone
        self.show_chart_border = show_chart_border
        self.show_page_number = show_page_number
        self.page_number_offset = page_number_offset
        self.allow_upscale = allow_upscale
        self.branding = branding or BrandingConfig.discover()
        self.theme = theme or ReportTheme()
        self.logo_path = logo_path or self.branding.logo_path(
            color="color",
            lockup="horizontal",
            size="512h",
        )
        self.required_template_key = chart_page_template_key(
            self.page_size,
            self.orientation,
        )

    def wrap(
        self,
        available_width: float,
        available_height: float,
    ) -> tuple[float, float]:
        return available_width, available_height

    def drawOn(self, canvas, x, y, _sW=0):  # noqa: N802
        self.canv = canvas
        self._sW = _sW
        self.draw()

    def draw(self) -> None:
        canvas = self.canv
        page_width, page_height = canvas._pagesize
        layout = chart_page_layout(
            title=self.title,
            description=self.description,
            page_size=self.page_size,
            orientation=self.orientation,
            show_chart_border=self.show_chart_border,
            theme=self.theme,
        )
        if (
            abs(page_width - layout.page_width) > 0.5
            or abs(page_height - layout.page_height) > 0.5
        ):
            raise ValueError(
                f"ChartPage requires template '{self.required_template_key}' "
                f"with page size {layout.page_width:.1f} x "
                f"{layout.page_height:.1f} points."
            )

        canvas.saveState()
        canvas.setFillColor(self.theme.white)
        canvas.rect(0, 0, page_width, page_height, fill=1, stroke=0)

        accent_color = (
            self.theme.dark_grey
            if self.accent_tone == "grey"
            else self.theme.primary
        )
        canvas.setFillColor(accent_color)
        canvas.setFont(self.theme.display_font, layout.title_font_size)
        canvas.drawString(
            _SIDE_MARGIN,
            layout.title_y,
            layout.display_title,
        )

        description = _paragraph_at_size(
            self.description,
            font_name=self.theme.body_font,
            font_size=layout.description_font_size,
            color=self.theme.dark_grey,
        )
        description.wrap(
            page_width - (2.0 * _SIDE_MARGIN),
            page_height,
        )
        description.drawOn(canvas, _SIDE_MARGIN, layout.description_y)

        self._draw_chart(
            canvas,
            chart_area=layout.chart_area,
            chart_box=layout.chart_box,
        )
        self._draw_footer(
            canvas,
            page_width=page_width,
        )
        canvas.restoreState()

    def _draw_chart(
        self,
        canvas,
        *,
        chart_area: ChartBox,
        chart_box: ChartBox,
    ) -> None:
        if self.show_chart_border:
            canvas.setStrokeColor(self.theme.light_grey)
            canvas.setLineWidth(0.6)
            canvas.rect(
                chart_area.x,
                chart_area.y,
                chart_area.width,
                chart_area.height,
                fill=0,
                stroke=1,
            )

        if self.chart_image_path.suffix.lower() == ".svg":
            drawing = svg2rlg(str(self.chart_image_path))
            if drawing is None or drawing.width <= 0 or drawing.height <= 0:
                raise ValueError(
                    f"Unable to render SVG chart image: {self.chart_image_path}"
                )
            scale = min(
                chart_box.width / float(drawing.width),
                chart_box.height / float(drawing.height),
            )
            if not self.allow_upscale:
                scale = min(scale, 1.0)
            draw_width = float(drawing.width) * scale
            draw_height = float(drawing.height) * scale
            drawing.scale(scale, scale)
            renderPDF.draw(
                drawing,
                canvas,
                chart_box.x + ((chart_box.width - draw_width) / 2.0),
                chart_box.y + chart_box.height - draw_height,
            )
            return

        reader = ImageReader(str(self.chart_image_path))
        source_width, source_height = reader.getSize()
        scale = min(
            chart_box.width / float(source_width),
            chart_box.height / float(source_height),
        )
        if not self.allow_upscale:
            scale = min(scale, 1.0)
        draw_width = float(source_width) * scale
        draw_height = float(source_height) * scale
        canvas.drawImage(
            reader,
            chart_box.x + ((chart_box.width - draw_width) / 2.0),
            chart_box.y + chart_box.height - draw_height,
            width=draw_width,
            height=draw_height,
            mask="auto",
            preserveAspectRatio=True,
        )

    def _draw_footer(
        self,
        canvas,
        *,
        page_width: float,
    ) -> None:
        if self.logo_path.is_file():
            reader = ImageReader(str(self.logo_path))
            source_width, source_height = reader.getSize()
            logo_width = 0.92 * inch
            logo_height = logo_width * (
                float(source_height) / float(source_width)
            )
            canvas.drawImage(
                reader,
                _SIDE_MARGIN,
                0.16 * inch,
                width=logo_width,
                height=logo_height,
                mask="auto",
                preserveAspectRatio=True,
            )
        if self.show_page_number:
            page_number = max(
                1,
                int(canvas.getPageNumber()) - self.page_number_offset,
            )
            canvas.setFillColor(self.theme.dark_grey)
            canvas.setFont(self.theme.body_semibold_font, 10.5)
            canvas.drawRightString(
                page_width - _SIDE_MARGIN,
                0.27 * inch,
                str(page_number),
            )


def chart_page(
    *,
    title: str,
    description: str,
    chart_image_path: Path,
    page_size: ChartPageSizeName = "LETTER",
    orientation: Orientation = "portrait",
    accent_tone: ChartAccentTone = "red",
    show_chart_border: bool = False,
    show_page_number: bool = True,
    page_number_offset: int = 0,
    allow_upscale: bool = False,
    branding: BrandingConfig | None = None,
    theme: ReportTheme | None = None,
    logo_path: Path | None = None,
) -> list[Flowable]:
    """Build one full-page chart using its matching named page template."""

    return [
        ChartPage(
            title=title,
            description=description,
            chart_image_path=chart_image_path,
            page_size=page_size,
            orientation=orientation,
            accent_tone=accent_tone,
            show_chart_border=show_chart_border,
            show_page_number=show_page_number,
            page_number_offset=page_number_offset,
            allow_upscale=allow_upscale,
            branding=branding,
            theme=theme,
            logo_path=logo_path,
        )
    ]


def _bounded_paragraph(
    text: str,
    *,
    font_name: str,
    maximum_font_size: float,
    minimum_font_size: float,
    color: object,
    width: float,
    maximum_lines: int,
) -> tuple[Paragraph, float, float]:
    font_size = maximum_font_size
    while font_size >= minimum_font_size:
        leading = font_size * 1.16
        paragraph = _paragraph_at_size(
            text,
            font_name=font_name,
            font_size=font_size,
            color=color,
        )
        _, height = paragraph.wrap(width, leading * maximum_lines)
        if height <= (leading * maximum_lines) + 0.1:
            return paragraph, height, font_size
        font_size -= 0.5
    raise ValueError(
        f"Text cannot fit within {maximum_lines} lines at the minimum font size: "
        f"{text}"
    )


def _paragraph_at_size(
    text: str,
    *,
    font_name: str,
    font_size: float,
    color: object,
) -> Paragraph:
    return Paragraph(
        escape(text),
        ParagraphStyle(
            name="chart-page-text",
            fontName=font_name,
            fontSize=font_size,
            leading=font_size * 1.16,
            textColor=color,
            spaceAfter=0,
            spaceBefore=0,
        ),
    )


def _truncate_title(
    text: str,
    *,
    font_name: str,
    font_size: float,
    maximum_width: float,
) -> str:
    if stringWidth(text, font_name, font_size) <= maximum_width:
        return text

    suffix = "..."
    available_width = maximum_width - stringWidth(suffix, font_name, font_size)
    if available_width <= 0:
        raise ValueError("ChartPage title area is too narrow for an ellipsis.")
    truncated = text
    while truncated and stringWidth(
        truncated.rstrip(),
        font_name,
        font_size,
    ) > available_width:
        truncated = truncated[:-1]
    truncated = truncated.rstrip()
    if " " in truncated:
        complete_words = truncated.rsplit(" ", 1)[0].rstrip()
        if complete_words:
            truncated = complete_words
    return f"{truncated}{suffix}"


def _validate_chart_page_text_and_geometry(
    *,
    title: str,
    description: str,
    page_size: str,
    orientation: str,
) -> None:
    if not title:
        raise ValueError("title cannot be empty.")
    if not description:
        raise ValueError("description cannot be empty.")
    if page_size not in {"LETTER", "LEGAL"}:
        raise ValueError("page_size must be 'LETTER' or 'LEGAL'.")
    if orientation not in {"portrait", "landscape"}:
        raise ValueError("orientation must be 'portrait' or 'landscape'.")
