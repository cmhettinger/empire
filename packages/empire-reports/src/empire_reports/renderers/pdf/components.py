from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from math import ceil
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable, Image, Paragraph, Spacer

from empire_reports.branding import BrandingConfig, ReportTheme
from empire_reports.renderers.pdf.styles import ReportStyles


def paragraph(text: str, *, styles: ReportStyles) -> Paragraph:
    return Paragraph(text, styles.body)


def section_heading(text: str, *, styles: ReportStyles) -> Paragraph:
    return Paragraph(text, styles.heading)


def spacer(height: float = 12.0) -> Spacer:
    return Spacer(1, height)


@dataclass(frozen=True, slots=True)
class QuoteTileSpec:
    """Display values for one reusable market-performance tile."""

    ticker: str
    price: float
    change: float | None
    change_pct: float | None


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
        palette = _quote_tile_palette(tile.change_pct, theme=theme)
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

        price_text = f"{tile.price:,.2f}"
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

        change_text = "-" if tile.change is None else f"{tile.change:+,.2f}"
        canvas.setFont(theme.body_font, 8.0)
        canvas.setFillColor(palette.value)
        canvas.drawCentredString(
            x + (width / 2.0),
            y + percent_height + 4.0,
            change_text,
        )

        percent_text = (
            "NO PRIOR CLOSE"
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
        branding: BrandingConfig | None = None,
        theme: ReportTheme | None = None,
        quote_image_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.header_text = header_text
        self.footer_text = footer_text
        self.warning_text = warning_text
        self.branding = branding or BrandingConfig.discover()
        self.theme = theme or ReportTheme()
        self.quote_image_path = quote_image_path or (
            self.branding.root / "images" / "buffett-no-crying.png"
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
    branding: BrandingConfig | None = None,
    theme: ReportTheme | None = None,
    quote_image_path: Path | None = None,
) -> list[Flowable]:
    return [
        ProfessionalLetterDisclaimerPage(
            header_text=header_text,
            footer_text=footer_text,
            warning_text=warning_text,
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
            minimum=28.0,
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
