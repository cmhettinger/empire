from __future__ import annotations

from datetime import date
from pathlib import Path

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
        _draw_centered_text(canvas, self.header_text, theme.body_font, 11, side_margin, content_width, top_label_y)
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
                canvas.drawCentredString(date_center_x, date_year_y + 4.0, self.date_label.upper())
                canvas.setFont(theme.body_bold_font, 16)
                canvas.drawCentredString(date_center_x, date_month_day_y, self.report_date.isoformat())
            else:
                canvas.setFont(theme.body_bold_font, 21)
                canvas.drawCentredString(date_center_x, date_year_y, self.report_date.strftime("%Y"))
                canvas.drawCentredString(date_center_x, date_month_day_y, self.report_date.strftime("%b %d").upper())

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
    resolved_logo = logo_path or branding_config.logo_path(color="red", lockup="horizontal", size="256h")

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
