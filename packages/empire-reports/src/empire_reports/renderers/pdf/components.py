from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from math import ceil
from pathlib import Path
from typing import Literal

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable, Image, Paragraph, Spacer

from empire_reports.assets import AssetRegistry
from empire_reports.branding import BrandingConfig, ReportTheme
from empire_reports.renderers.pdf.styles import ReportStyles


def paragraph(text: str, *, styles: ReportStyles) -> Paragraph:
    return Paragraph(text, styles.body)


def section_heading(text: str, *, styles: ReportStyles) -> Paragraph:
    return Paragraph(text, styles.heading)


def spacer(height: float = 12.0) -> Spacer:
    return Spacer(1, height)


RailTone = Literal["grey", "red"]


@dataclass(frozen=True, slots=True)
class _RailPageGeometry:
    page_width: float
    page_height: float
    rail_width: float
    body_x: float
    body_width: float
    content_x: float
    content_right: float
    content_width: float
    rail_color: object


class _ProfessionalRailPage(Flowable):
    """Shared branded chrome for full-page portrait US Letter components."""

    def __init__(
        self,
        *,
        rail_tone: RailTone = "grey",
        show_page_number: bool = True,
        page_number_offset: int = 0,
        branding: BrandingConfig | None = None,
        theme: ReportTheme | None = None,
        logo_path: Path | None = None,
        body_watermark_path: Path | None = None,
        rail_watermark_path: Path | None = None,
    ) -> None:
        super().__init__()
        if rail_tone not in {"grey", "red"}:
            raise ValueError("rail_tone must be 'grey' or 'red'.")
        if page_number_offset < 0:
            raise ValueError("page_number_offset cannot be negative.")
        self.rail_tone = rail_tone
        self.show_page_number = show_page_number
        self.page_number_offset = page_number_offset
        self.branding = branding or BrandingConfig.discover()
        self.theme = theme or ReportTheme()
        self.logo_path = logo_path or self.branding.logo_path(
            color="color",
            lockup="horizontal",
            size="512h",
        )
        self.body_watermark_path = body_watermark_path or self.branding.logo_path(
            color="light-grey",
            lockup="icon",
            size="512h",
        )
        self.rail_watermark_path = rail_watermark_path or self.branding.logo_path(
            color="white",
            lockup="icon",
            size="512h",
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
        geometry = self._geometry(canvas)
        canvas.saveState()
        self._draw_background(canvas, geometry=geometry)
        self._draw_content(canvas, geometry=geometry)
        self._draw_logo(
            canvas,
            body_x=geometry.body_x,
            body_width=geometry.body_width,
        )
        self._draw_footer(canvas, geometry=geometry)
        canvas.restoreState()

    def _geometry(self, canvas) -> _RailPageGeometry:
        page_width, page_height = canvas._pagesize
        if (
            abs(page_width - letter[0]) > 0.5
            or abs(page_height - letter[1]) > 0.5
        ):
            raise ValueError(
                f"{type(self).__name__} requires portrait US Letter page geometry."
            )

        theme = self.theme
        rail_width = 1.14 * inch
        separator_width = 0.035 * inch
        body_x = rail_width + separator_width
        body_width = page_width - body_x
        content_x = body_x + (0.47 * inch)
        content_right = page_width - (0.55 * inch)
        content_width = content_right - content_x
        rail_color = theme.dark_grey if self.rail_tone == "grey" else theme.primary
        return _RailPageGeometry(
            page_width=page_width,
            page_height=page_height,
            rail_width=rail_width,
            body_x=body_x,
            body_width=body_width,
            content_x=content_x,
            content_right=content_right,
            content_width=content_width,
            rail_color=rail_color,
        )

    def _draw_background(
        self,
        canvas,
        *,
        geometry: _RailPageGeometry,
    ) -> None:
        separator_width = 0.035 * inch
        canvas.setFillColor(self.theme.white)
        canvas.rect(
            0,
            0,
            geometry.page_width,
            geometry.page_height,
            fill=1,
            stroke=0,
        )

        self._draw_body_watermark(
            canvas,
            page_width=geometry.page_width,
            page_height=geometry.page_height,
        )

        canvas.setFillColor(geometry.rail_color)
        canvas.rect(
            0,
            0,
            geometry.rail_width,
            geometry.page_height,
            fill=1,
            stroke=0,
        )
        canvas.setFillColor(self.theme.white)
        canvas.rect(
            geometry.rail_width,
            0,
            separator_width,
            geometry.page_height,
            fill=1,
            stroke=0,
        )
        self._draw_rail_watermark(canvas, rail_width=geometry.rail_width)

    def _draw_content(
        self,
        canvas,
        *,
        geometry: _RailPageGeometry,
    ) -> None:
        raise NotImplementedError

    def _draw_footer(
        self,
        canvas,
        *,
        geometry: _RailPageGeometry,
    ) -> None:
        footer_rule_y = 0.72 * inch
        canvas.setStrokeColor(geometry.rail_color)
        canvas.setLineWidth(1.0)
        canvas.line(
            geometry.body_x,
            footer_rule_y,
            geometry.page_width,
            footer_rule_y,
        )
        if self.show_page_number:
            page_number = max(
                1,
                int(canvas.getPageNumber()) - self.page_number_offset,
            )
            canvas.setFillColor(self.theme.dark_grey)
            canvas.setFont(self.theme.body_semibold_font, 12)
            canvas.drawRightString(
                geometry.page_width - (0.54 * inch),
                0.28 * inch,
                str(page_number),
            )

    def _draw_body_watermark(
        self,
        canvas,
        *,
        page_width: float,
        page_height: float,
    ) -> None:
        if not self.body_watermark_path.exists():
            return
        reader = ImageReader(str(self.body_watermark_path))
        image_width, image_height = reader.getSize()
        draw_width = 6.85 * inch
        draw_height = draw_width * (float(image_height) / float(image_width))
        canvas.saveState()
        canvas.setFillAlpha(0.10)
        canvas.drawImage(
            reader,
            page_width - (5.15 * inch),
            page_height - (6.75 * inch),
            width=draw_width,
            height=draw_height,
            mask="auto",
            preserveAspectRatio=True,
        )
        canvas.restoreState()

    def _draw_rail_watermark(self, canvas, *, rail_width: float) -> None:
        if not self.rail_watermark_path.exists():
            return
        reader = ImageReader(str(self.rail_watermark_path))
        image_width, image_height = reader.getSize()
        draw_width = 4.0 * inch
        draw_height = draw_width * (float(image_height) / float(image_width))
        draw_x = (rail_width - draw_width) / 2.0
        canvas.saveState()
        canvas.setFillAlpha(0.085 if self.rail_tone == "grey" else 0.075)
        canvas.drawImage(
            reader,
            draw_x,
            -0.12 * inch,
            width=draw_width,
            height=draw_height,
            mask="auto",
            preserveAspectRatio=True,
        )
        canvas.restoreState()

    def _draw_logo(self, canvas, *, body_x: float, body_width: float) -> None:
        if not self.logo_path.exists():
            return
        reader = ImageReader(str(self.logo_path))
        image_width, image_height = reader.getSize()
        draw_width = 2.25 * inch
        draw_height = draw_width * (float(image_height) / float(image_width))
        draw_x = body_x + ((body_width - draw_width) / 2.0)
        canvas.drawImage(
            reader,
            draw_x,
            0.93 * inch,
            width=draw_width,
            height=draw_height,
            mask="auto",
            preserveAspectRatio=True,
        )


class AppendixDividerPage(_ProfessionalRailPage):
    """Full-page Empire appendix divider for portrait US Letter reports."""

    def __init__(
        self,
        *,
        title: str,
        description: str | None = None,
        eyebrow_text: str = "APPENDIX",
        rail_tone: RailTone = "grey",
        show_page_number: bool = True,
        page_number_offset: int = 0,
        branding: BrandingConfig | None = None,
        theme: ReportTheme | None = None,
        logo_path: Path | None = None,
        body_watermark_path: Path | None = None,
        rail_watermark_path: Path | None = None,
    ) -> None:
        if not title.strip():
            raise ValueError("title cannot be empty.")
        if not eyebrow_text.strip():
            raise ValueError("eyebrow_text cannot be empty.")
        super().__init__(
            rail_tone=rail_tone,
            show_page_number=show_page_number,
            page_number_offset=page_number_offset,
            branding=branding,
            theme=theme,
            logo_path=logo_path,
            body_watermark_path=body_watermark_path,
            rail_watermark_path=rail_watermark_path,
        )
        self.title = title
        self.description = description
        self.eyebrow_text = eyebrow_text

    def _draw_content(
        self,
        canvas,
        *,
        geometry: _RailPageGeometry,
    ) -> None:
        theme = self.theme

        canvas.saveState()
        eyebrow = canvas.beginText()
        eyebrow.setTextOrigin(geometry.content_x, 7.08 * inch)
        eyebrow.setFont(theme.body_semibold_font, 11)
        eyebrow.setFillColor(theme.dark_grey)
        eyebrow.setCharSpace(4.2)
        eyebrow.textLine(self.eyebrow_text.upper())
        canvas.drawText(eyebrow)
        canvas.restoreState()

        fitted_title_size = _fit_font_size(
            self.title,
            theme.display_font,
            43.0,
            geometry.content_width,
            minimum=20.0,
        )
        canvas.setFillColor(theme.primary)
        canvas.setFont(theme.display_font, fitted_title_size)
        canvas.drawString(geometry.content_x, 6.25 * inch, self.title)

        rule_y = 5.83 * inch
        rule_end_x = min(
            geometry.content_x + (3.45 * inch),
            geometry.content_right - 10.0,
        )
        canvas.setStrokeColor(geometry.rail_color)
        canvas.setLineWidth(1.25)
        canvas.line(geometry.content_x, rule_y, rule_end_x, rule_y)

        if self.description:
            _draw_wrapped_text(
                canvas,
                self.description.upper(),
                font_name=theme.body_semibold_font,
                font_size=10.5,
                leading=18.0,
                text_color=theme.dark_grey,
                x=geometry.content_x,
                y=5.42 * inch,
                max_width=min(geometry.content_width, 4.45 * inch),
            )


class SectionDividerPage(AppendixDividerPage):
    """Full-page Empire section divider sharing the appendix geometry."""

    def __init__(
        self,
        *,
        title: str,
        description: str | None = None,
        rail_tone: RailTone = "grey",
        show_page_number: bool = True,
        page_number_offset: int = 0,
        branding: BrandingConfig | None = None,
        theme: ReportTheme | None = None,
        logo_path: Path | None = None,
        body_watermark_path: Path | None = None,
        rail_watermark_path: Path | None = None,
    ) -> None:
        super().__init__(
            title=title,
            description=description,
            eyebrow_text="SECTION",
            rail_tone=rail_tone,
            show_page_number=show_page_number,
            page_number_offset=page_number_offset,
            branding=branding,
            theme=theme,
            logo_path=logo_path,
            body_watermark_path=body_watermark_path,
            rail_watermark_path=rail_watermark_path,
        )


class IntentionallyBlankPage(_ProfessionalRailPage):
    """Quiet branded page reserved to preserve intentional document spacing."""

    def _draw_content(
        self,
        canvas,
        *,
        geometry: _RailPageGeometry,
    ) -> None:
        center_x = geometry.body_x + (geometry.body_width / 2.0)
        canvas.setFillColor(self.theme.black)
        canvas.setFont(self.theme.body_font, 16)
        canvas.drawCentredString(
            center_x,
            5.82 * inch,
            "THIS PAGE INTENTIONALLY",
        )
        canvas.drawCentredString(
            center_x,
            5.52 * inch,
            "LEFT BLANK",
        )


class NotesPage(_ProfessionalRailPage):
    """Branded ruled page for handwritten report notes."""

    def _draw_content(
        self,
        canvas,
        *,
        geometry: _RailPageGeometry,
    ) -> None:
        canvas.setFillColor(geometry.rail_color)
        canvas.setFont(self.theme.display_font, 22)
        canvas.drawString(geometry.content_x, 9.85 * inch, "NOTES")

        heading_rule_y = 9.54 * inch
        canvas.setStrokeColor(geometry.rail_color)
        canvas.setLineWidth(1.25)
        canvas.line(
            geometry.content_x,
            heading_rule_y,
            geometry.content_x + (2.1 * inch),
            heading_rule_y,
        )

        canvas.setStrokeColor(self.theme.light_grey)
        canvas.setLineWidth(0.45)
        line_y = 8.95 * inch
        final_line_y = 1.95 * inch
        line_spacing = 0.36 * inch
        while line_y >= final_line_y:
            canvas.line(
                geometry.content_x,
                line_y,
                geometry.content_right,
                line_y,
            )
            line_y -= line_spacing


def appendix_divider_page(
    *,
    title: str,
    description: str | None = None,
    eyebrow_text: str = "APPENDIX",
    rail_tone: RailTone = "grey",
    show_page_number: bool = True,
    page_number_offset: int = 0,
    branding: BrandingConfig | None = None,
    theme: ReportTheme | None = None,
    logo_path: Path | None = None,
    body_watermark_path: Path | None = None,
    rail_watermark_path: Path | None = None,
) -> list[Flowable]:
    """Build one reusable appendix divider page."""

    return [
        AppendixDividerPage(
            title=title,
            description=description,
            eyebrow_text=eyebrow_text,
            rail_tone=rail_tone,
            show_page_number=show_page_number,
            page_number_offset=page_number_offset,
            branding=branding,
            theme=theme,
            logo_path=logo_path,
            body_watermark_path=body_watermark_path,
            rail_watermark_path=rail_watermark_path,
        )
    ]


def section_divider_page(
    *,
    title: str,
    description: str | None = None,
    rail_tone: RailTone = "grey",
    show_page_number: bool = True,
    page_number_offset: int = 0,
    branding: BrandingConfig | None = None,
    theme: ReportTheme | None = None,
    logo_path: Path | None = None,
    body_watermark_path: Path | None = None,
    rail_watermark_path: Path | None = None,
) -> list[Flowable]:
    """Build one reusable section divider page."""

    return [
        SectionDividerPage(
            title=title,
            description=description,
            rail_tone=rail_tone,
            show_page_number=show_page_number,
            page_number_offset=page_number_offset,
            branding=branding,
            theme=theme,
            logo_path=logo_path,
            body_watermark_path=body_watermark_path,
            rail_watermark_path=rail_watermark_path,
        )
    ]


def intentionally_blank_page(
    *,
    rail_tone: RailTone = "grey",
    show_page_number: bool = True,
    page_number_offset: int = 0,
    branding: BrandingConfig | None = None,
    theme: ReportTheme | None = None,
    logo_path: Path | None = None,
    body_watermark_path: Path | None = None,
    rail_watermark_path: Path | None = None,
) -> list[Flowable]:
    """Build one reusable intentionally blank page."""

    return [
        IntentionallyBlankPage(
            rail_tone=rail_tone,
            show_page_number=show_page_number,
            page_number_offset=page_number_offset,
            branding=branding,
            theme=theme,
            logo_path=logo_path,
            body_watermark_path=body_watermark_path,
            rail_watermark_path=rail_watermark_path,
        )
    ]


def notes_page(
    *,
    rail_tone: RailTone = "grey",
    show_page_number: bool = True,
    page_number_offset: int = 0,
    branding: BrandingConfig | None = None,
    theme: ReportTheme | None = None,
    logo_path: Path | None = None,
    body_watermark_path: Path | None = None,
    rail_watermark_path: Path | None = None,
) -> list[Flowable]:
    """Build one reusable ruled notes page."""

    return [
        NotesPage(
            rail_tone=rail_tone,
            show_page_number=show_page_number,
            page_number_offset=page_number_offset,
            branding=branding,
            theme=theme,
            logo_path=logo_path,
            body_watermark_path=body_watermark_path,
            rail_watermark_path=rail_watermark_path,
        )
    ]


@dataclass(frozen=True, slots=True)
class QuoteTileSpec:
    """Display values for one reusable market-performance tile."""

    ticker: str
    price: float | None
    change: float | None
    change_pct: float | None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class _QuoteTilePalette:
    frame: object
    body: object
    band: object
    value: object


class QuoteTileGrid(Flowable):
    """Responsive Empire-branded red, green, and neutral quote tiles."""

    def __init__(
        self,
        tiles: Sequence[QuoteTileSpec],
        *,
        columns: int = 4,
        tile_height: float = 82.0,
        horizontal_gap: float = 7.0,
        vertical_gap: float = 7.0,
        theme: ReportTheme | None = None,
    ) -> None:
        super().__init__()
        if columns <= 0:
            raise ValueError("columns must be positive.")
        if tile_height <= 0:
            raise ValueError("tile_height must be positive.")
        self.tiles = tuple(tiles)
        self.columns = columns
        self.tile_height = float(tile_height)
        self.horizontal_gap = float(horizontal_gap)
        self.vertical_gap = float(vertical_gap)
        self.theme = theme or ReportTheme()
        self._available_width = 0.0

    def wrap(
        self,
        available_width: float,
        available_height: float,
    ) -> tuple[float, float]:
        _ = available_height
        self._available_width = float(available_width)
        rows = ceil(len(self.tiles) / self.columns) if self.tiles else 0
        height = (rows * self.tile_height) + (
            max(0, rows - 1) * self.vertical_gap
        )
        return self._available_width, height

    def draw(self) -> None:
        if not self.tiles:
            return
        width = self._available_width or self.width
        tile_width = (
            width - ((self.columns - 1) * self.horizontal_gap)
        ) / self.columns
        row_count = ceil(len(self.tiles) / self.columns)
        total_height = (row_count * self.tile_height) + (
            max(0, row_count - 1) * self.vertical_gap
        )
        for index, tile in enumerate(self.tiles):
            row = index // self.columns
            column = index % self.columns
            x = column * (tile_width + self.horizontal_gap)
            y = total_height - ((row + 1) * self.tile_height) - (
                row * self.vertical_gap
            )
            self._draw_tile(tile=tile, x=x, y=y, width=tile_width)

    def _draw_tile(
        self,
        *,
        tile: QuoteTileSpec,
        x: float,
        y: float,
        width: float,
    ) -> None:
        canvas = self.canv
        theme = self.theme
        palette = _quote_tile_palette(
            None if tile.status is not None else tile.change_pct,
            theme=theme,
        )
        header_height = self.tile_height * 0.23
        percent_height = self.tile_height * 0.27

        canvas.saveState()
        canvas.setFillColor(palette.body)
        canvas.roundRect(x, y, width, self.tile_height, 4, fill=1, stroke=0)

        canvas.setFillColor(palette.frame)
        canvas.rect(
            x,
            y + self.tile_height - header_height,
            width,
            header_height,
            fill=1,
            stroke=0,
        )
        canvas.setFillColor(palette.band)
        canvas.rect(x, y, width, percent_height, fill=1, stroke=0)
        canvas.setFillColor(palette.body)
        canvas.setStrokeColor(palette.frame)
        canvas.setLineWidth(1.0)
        canvas.roundRect(x, y, width, self.tile_height, 4, fill=0, stroke=1)

        ticker_size = _fit_font_size(
            tile.ticker,
            theme.body_bold_font,
            10.0,
            width - 10.0,
            minimum=6.0,
        )
        canvas.setFont(theme.body_bold_font, ticker_size)
        canvas.setFillColor(theme.white)
        canvas.drawCentredString(
            x + (width / 2.0),
            y + self.tile_height - header_height + 5.0,
            tile.ticker,
        )

        price_text = "-" if tile.price is None else f"{tile.price:,.2f}"
        price_size = _fit_font_size(
            price_text,
            theme.body_bold_font,
            14.0,
            width - 10.0,
            minimum=8.0,
        )
        canvas.setFillColor(theme.dark_grey)
        canvas.setFont(theme.body_bold_font, price_size)
        canvas.drawCentredString(
            x + (width / 2.0),
            y + percent_height + 14.0,
            price_text,
        )

        change_text = (
            ""
            if tile.status is not None
            else "-"
            if tile.change is None
            else f"{tile.change:+,.2f}"
        )
        canvas.setFont(theme.body_font, 8.0)
        canvas.setFillColor(palette.value)
        canvas.drawCentredString(
            x + (width / 2.0),
            y + percent_height + 4.0,
            change_text,
        )

        percent_text = (
            tile.status
            if tile.status is not None
            else "NO PRIOR CLOSE"
            if tile.change_pct is None
            else "UNCHANGED"
            if abs(tile.change_pct) < 1e-12
            else f"{tile.change_pct:+.2f}%"
        )
        percent_size = _fit_font_size(
            percent_text,
            theme.body_semibold_font,
            9.5,
            width - 8.0,
            minimum=5.5,
        )
        canvas.setFont(theme.body_semibold_font, percent_size)
        canvas.setFillColor(palette.value)
        canvas.drawCentredString(
            x + (width / 2.0),
            y + 5.0,
            percent_text,
        )
        canvas.restoreState()


def quote_tile_grid(
    tiles: Sequence[QuoteTileSpec],
    *,
    columns: int = 4,
    tile_height: float = 82.0,
    horizontal_gap: float = 7.0,
    vertical_gap: float = 7.0,
    theme: ReportTheme | None = None,
) -> QuoteTileGrid:
    return QuoteTileGrid(
        tiles,
        columns=columns,
        tile_height=tile_height,
        horizontal_gap=horizontal_gap,
        vertical_gap=vertical_gap,
        theme=theme,
    )


def _quote_direction(value: float | None) -> str:
    if value is None or abs(value) < 1e-12:
        return "neutral"
    return "positive" if value > 0 else "negative"


def _quote_tile_palette(
    value: float | None,
    *,
    theme: ReportTheme,
) -> _QuoteTilePalette:
    direction = _quote_direction(value)
    return {
        "positive": _QuoteTilePalette(
            frame=HexColor("#1F6B45"),
            body=HexColor("#E4F1E9"),
            band=HexColor("#CDE5D7"),
            value=HexColor("#1F6B45"),
        ),
        "negative": _QuoteTilePalette(
            frame=theme.primary,
            body=HexColor("#F8E5E7"),
            band=HexColor("#F0CDD1"),
            value=theme.accent,
        ),
        "neutral": _QuoteTilePalette(
            frame=theme.dark_grey,
            body=HexColor("#EEEEEE"),
            band=HexColor("#DCDCDC"),
            value=theme.dark_grey,
        ),
    }[direction]


class ProfessionalLetterDisclaimerPage(Flowable):
    """Reusable Empire-branded disclaimer page for research reports."""

    def __init__(
        self,
        *,
        header_text: str = "EMPIRE RESEARCH DIVISION",
        footer_text: str = "PROPRIETARY / INTERNAL USE ONLY",
        warning_text: str = (
            "This system is currently in development and not intended for live trading"
        ),
        assets: AssetRegistry | None = None,
        branding: BrandingConfig | None = None,
        theme: ReportTheme | None = None,
        quote_image_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.header_text = header_text
        self.footer_text = footer_text
        self.warning_text = warning_text
        self.assets = assets or AssetRegistry.discover()
        self.branding = branding or BrandingConfig.discover(assets=self.assets)
        self.theme = theme or ReportTheme()
        self.quote_image_path = quote_image_path or self.assets.image_path(
            "buffett-no-crying.png"
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
        theme = self.theme

        side_margin = 0.5 * inch
        content_width = page_width - (2.0 * side_margin)
        top_rule_y = page_height - (0.75 * inch)
        bottom_rule_y = 0.75 * inch
        banner_x = 0.56 * inch
        banner_y = 8.88 * inch
        banner_width = page_width - (2.0 * banner_x)
        banner_height = 0.58 * inch
        quote_width = 6.73 * inch
        quote_x = (page_width - quote_width) / 2.0
        quote_y = 6.05 * inch

        canvas.saveState()
        canvas.setStrokeColor(theme.dark_grey)
        canvas.setLineWidth(1.7)
        canvas.line(side_margin, top_rule_y, page_width - side_margin, top_rule_y)
        canvas.line(side_margin, bottom_rule_y, page_width - side_margin, bottom_rule_y)

        canvas.setFillColor(theme.dark_grey)
        canvas.setFont(theme.body_font, 11)
        _draw_centered_text(
            canvas,
            self.header_text,
            theme.body_font,
            11,
            side_margin,
            content_width,
            top_rule_y + 5.0,
        )
        _draw_centered_text(
            canvas,
            self.footer_text,
            theme.body_font,
            11,
            side_margin,
            content_width,
            bottom_rule_y - 17.0,
        )

        canvas.setFillColor(theme.primary)
        canvas.rect(
            banner_x,
            banner_y,
            banner_width,
            banner_height,
            fill=1,
            stroke=0,
        )
        canvas.setFillColor(theme.white)
        canvas.setFont(theme.body_bold_font, 22)
        canvas.drawCentredString(
            page_width / 2.0,
            banner_y + (0.18 * inch),
            "DISCLAIMER",
        )

        if self.quote_image_path.exists():
            reader = ImageReader(str(self.quote_image_path))
            image_width, image_height = reader.getSize()
            quote_height = quote_width * (float(image_height) / float(image_width))
            canvas.drawImage(
                reader,
                quote_x,
                quote_y,
                width=quote_width,
                height=quote_height,
                mask="auto",
                preserveAspectRatio=True,
            )

        warning_size = _fit_font_size(
            self.warning_text,
            theme.body_semibold_font,
            14.0,
            content_width,
            minimum=10.0,
        )
        canvas.setFillColor(theme.dark_grey)
        canvas.setFont(theme.body_semibold_font, warning_size)
        canvas.drawCentredString(page_width / 2.0, 3.92 * inch, self.warning_text)
        canvas.restoreState()


def professional_letter_disclaimer_page(
    *,
    header_text: str = "EMPIRE RESEARCH DIVISION",
    footer_text: str = "PROPRIETARY / INTERNAL USE ONLY",
    warning_text: str = (
        "This system is currently in development and not intended for live trading"
    ),
    assets: AssetRegistry | None = None,
    branding: BrandingConfig | None = None,
    theme: ReportTheme | None = None,
    quote_image_path: Path | None = None,
) -> list[Flowable]:
    return [
        ProfessionalLetterDisclaimerPage(
            header_text=header_text,
            footer_text=footer_text,
            warning_text=warning_text,
            assets=assets,
            branding=branding,
            theme=theme,
            quote_image_path=quote_image_path,
        )
    ]


class ProfessionalLetterTitlePage(Flowable):
    """Reusable Empire-branded letter title page.

    This is intentionally a full-page flowable: it draws directly on the
    canvas so domain reports can reuse a polished cover without owning title
    page geometry.
    """

    def __init__(
        self,
        *,
        title: str,
        subtitle: str,
        report_date: date | None,
        header_text: str = "EMPIRE REPORT",
        footer_text: str = "INTERNAL USE ONLY",
        classification_text: str | None = None,
        date_label: str | None = None,
        show_date: bool = True,
        branding: BrandingConfig | None = None,
        theme: ReportTheme | None = None,
        logo_path: Path | None = None,
        watermark_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.subtitle = subtitle
        self.report_date = report_date
        self.header_text = header_text
        self.footer_text = footer_text
        self.classification_text = classification_text or footer_text
        self.date_label = date_label
        self.show_date = show_date
        self.branding = branding or BrandingConfig.discover()
        self.theme = theme or ReportTheme()
        self.logo_path = logo_path or self.branding.logo_path(
            color="color",
            lockup="horizontal",
            size="512h",
        )
        self.watermark_path = watermark_path or self.branding.logo_path(
            color="light-grey",
            lockup="icon",
            size="512h",
        )

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        return available_width, available_height

    def drawOn(self, canvas, x, y, _sW=0):  # noqa: N802
        self.canv = canvas
        self._sW = _sW
        self.draw()

    def draw(self) -> None:
        canvas = self.canv
        page_width, page_height = canvas._pagesize
        theme = self.theme

        side_margin = 0.5 * inch
        content_width = page_width - (2.0 * side_margin)
        title_x = 1.02 * inch
        title_y = 7.65 * inch
        title_size = 43.0
        subtitle_size = 18.0
        subtitle_gap = 0.42 * inch
        divider_x = 6.08 * inch
        date_x = 6.30 * inch
        date_rule_width = 1.22 * inch

        title_top_y = title_y + (title_size * 0.30)
        title_visual_top_y = title_y + (title_size * 0.62)
        subtitle_baseline_y = title_y - subtitle_gap
        subtitle_bottom_y = subtitle_baseline_y - (subtitle_size * 0.35)
        divider_top_y = title_visual_top_y
        divider_bottom_y = subtitle_bottom_y
        divider_center_y = (divider_top_y + divider_bottom_y) / 2.0
        date_month_day_y = subtitle_baseline_y
        date_year_y = title_top_y - (21.0 * 0.30)

        rule_offset = 0.75 * inch
        label_gap = 5.0
        top_rule_y = page_height - rule_offset
        top_label_y = top_rule_y + label_gap
        bottom_rule_y = rule_offset
        bottom_label_y = bottom_rule_y - 12.0 - label_gap

        watermark_width = 4.75 * inch
        watermark_x = page_width - side_margin - watermark_width
        watermark_y = bottom_rule_y + 0.15 * inch
        logo_width = 2.585 * inch
        logo_height = 0.803 * inch
        logo_x = (page_width - logo_width) / 2.0
        logo_y = bottom_rule_y + 0.31 * inch

        canvas.saveState()

        if self.watermark_path.exists():
            reader = ImageReader(str(self.watermark_path))
            image_width, image_height = reader.getSize()
            watermark_height = watermark_width * (float(image_height) / float(image_width))
            canvas.saveState()
            canvas.setFillAlpha(0.12)
            canvas.drawImage(
                reader,
                watermark_x,
                watermark_y,
                width=watermark_width,
                height=watermark_height,
                mask="auto",
                preserveAspectRatio=True,
            )
            canvas.restoreState()

        if self.logo_path.exists():
            canvas.drawImage(
                ImageReader(str(self.logo_path)),
                logo_x,
                logo_y,
                width=logo_width,
                height=logo_height,
                mask="auto",
                preserveAspectRatio=True,
            )

        canvas.setStrokeColor(theme.dark_grey)
        canvas.setLineWidth(1.7)
        canvas.line(side_margin, top_rule_y, page_width - side_margin, top_rule_y)
        canvas.line(side_margin, bottom_rule_y, page_width - side_margin, bottom_rule_y)

        canvas.setFillColor(theme.dark_grey)
        canvas.setFont(theme.body_font, 11)
        _draw_centered_text(
            canvas,
            self.header_text,
            theme.body_font,
            11,
            side_margin,
            content_width,
            top_label_y,
        )
        _draw_centered_text(
            canvas,
            self.classification_text,
            theme.body_font,
            11,
            side_margin,
            content_width,
            bottom_label_y,
        )

        title_max_width = divider_x - title_x - 0.35 * inch
        fitted_title_size = _fit_font_size(
            self.title,
            theme.display_font,
            title_size,
            title_max_width,
            minimum=16.0,
        )
        canvas.setFillColor(theme.primary)
        canvas.setFont(theme.display_font, fitted_title_size)
        canvas.drawString(title_x, title_y, self.title)

        subtitle_max_width = divider_x - title_x - 0.35 * inch
        fitted_subtitle_size = _fit_font_size(
            self.subtitle,
            theme.body_light_font,
            subtitle_size,
            subtitle_max_width,
            minimum=11.0,
        )
        canvas.setFillColor(theme.dark_grey)
        canvas.setFont(theme.body_light_font, fitted_subtitle_size)
        canvas.drawString(title_x + 0.04 * inch, subtitle_baseline_y, self.subtitle)

        if self.show_date and self.report_date is not None:
            canvas.setStrokeColor(theme.dark_grey)
            canvas.setLineWidth(0.8)
            canvas.line(divider_x, divider_bottom_y, divider_x, divider_top_y)
            canvas.setStrokeColor(theme.primary)
            canvas.line(date_x, divider_center_y, date_x + date_rule_width, divider_center_y)

            date_center_x = date_x + (date_rule_width / 2.0)
            canvas.setFillColor(theme.dark_grey)
            if self.date_label:
                canvas.setFont(theme.body_semibold_font, 10)
                canvas.drawCentredString(
                    date_center_x,
                    date_year_y + 4.0,
                    self.date_label.upper(),
                )
                canvas.setFont(theme.body_bold_font, 16)
                canvas.drawCentredString(
                    date_center_x,
                    date_month_day_y,
                    self.report_date.isoformat(),
                )
            else:
                canvas.setFont(theme.body_bold_font, 21)
                canvas.drawCentredString(
                    date_center_x,
                    date_year_y,
                    self.report_date.strftime("%Y"),
                )
                canvas.drawCentredString(
                    date_center_x,
                    date_month_day_y,
                    self.report_date.strftime("%b %d").upper(),
                )

        canvas.restoreState()


def professional_letter_title_page(
    *,
    title: str,
    subtitle: str,
    report_date: date | None,
    header_text: str = "EMPIRE REPORT",
    footer_text: str = "INTERNAL USE ONLY",
    classification_text: str | None = None,
    date_label: str | None = None,
    show_date: bool = True,
    branding: BrandingConfig | None = None,
    theme: ReportTheme | None = None,
    logo_path: Path | None = None,
    watermark_path: Path | None = None,
) -> list[Flowable]:
    return [
        ProfessionalLetterTitlePage(
            title=title,
            subtitle=subtitle,
            report_date=report_date,
            header_text=header_text,
            footer_text=footer_text,
            classification_text=classification_text,
            date_label=date_label,
            show_date=show_date,
            branding=branding,
            theme=theme,
            logo_path=logo_path,
            watermark_path=watermark_path,
        )
    ]


def cover_page(
    *,
    title: str,
    styles: ReportStyles,
    subtitle: str | None = None,
    as_of: date | None = None,
    branding: BrandingConfig | None = None,
    logo_path: Path | None = None,
) -> list[Flowable]:
    branding_config = branding or BrandingConfig.discover()
    resolved_logo = logo_path or branding_config.logo_path(
        color="red",
        lockup="horizontal",
        size="256h",
    )

    flowables: list[Flowable] = [Spacer(1, 1.4 * inch)]
    if resolved_logo.exists():
        logo = Image(str(resolved_logo), width=2.35 * inch, height=0.73 * inch)
        logo.hAlign = "CENTER"
        flowables.extend([logo, Spacer(1, 0.55 * inch)])

    flowables.append(Paragraph(title, styles.title))
    if subtitle:
        flowables.append(Paragraph(subtitle, styles.subtitle))
    if as_of:
        flowables.append(Paragraph(f"As of {as_of.isoformat()}", styles.subtitle))
    return flowables


def _draw_centered_text(
    canvas,
    text: str,
    font_name: str,
    font_size: float,
    x: float,
    width: float,
    y: float,
) -> None:
    text_width = stringWidth(text, font_name, font_size)
    canvas.drawString(x + ((width - text_width) / 2.0), y, text)


def _draw_wrapped_text(
    canvas,
    text: str,
    *,
    font_name: str,
    font_size: float,
    leading: float,
    text_color: object,
    x: float,
    y: float,
    max_width: float,
) -> None:
    lines: list[str] = []
    for paragraph_text in text.splitlines() or [text]:
        words = paragraph_text.split()
        if not words:
            lines.append("")
            continue
        line = words[0]
        for word in words[1:]:
            candidate = f"{line} {word}"
            if stringWidth(candidate, font_name, font_size) <= max_width:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)

    canvas.setFillColor(text_color)
    canvas.setFont(font_name, font_size)
    for index, line in enumerate(lines):
        canvas.drawString(x, y - (index * leading), line)


def _fit_font_size(
    text: str,
    font_name: str,
    preferred: float,
    max_width: float,
    *,
    minimum: float,
) -> float:
    size = preferred
    while size > minimum and stringWidth(text, font_name, size) > max_width:
        size -= 1.0
    return size
