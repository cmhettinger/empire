from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle

from empire_reports.branding import ReportTheme


@dataclass(frozen=True, slots=True)
class ReportStyles:
    title: ParagraphStyle
    subtitle: ParagraphStyle
    heading: ParagraphStyle
    subheading: ParagraphStyle
    body: ParagraphStyle
    small: ParagraphStyle
    code: ParagraphStyle


def make_report_styles(theme: ReportTheme) -> ReportStyles:
    body = ParagraphStyle(
        name="EmpireBody",
        fontName=theme.body_font,
        fontSize=10,
        leading=14,
        textColor=theme.dark_grey,
        spaceAfter=8,
    )
    return ReportStyles(
        title=ParagraphStyle(
            name="EmpireTitle",
            fontName=theme.display_font,
            fontSize=28,
            leading=34,
            textColor=theme.primary,
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        subtitle=ParagraphStyle(
            name="EmpireSubtitle",
            fontName=theme.body_light_font,
            fontSize=12,
            leading=16,
            textColor=theme.dark_grey,
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        heading=ParagraphStyle(
            name="EmpireHeading",
            fontName=theme.body_semibold_font,
            fontSize=16,
            leading=20,
            textColor=theme.primary,
            spaceBefore=4,
            spaceAfter=8,
        ),
        subheading=ParagraphStyle(
            name="EmpireSubheading",
            fontName=theme.body_semibold_font,
            fontSize=12,
            leading=16,
            textColor=theme.dark_grey,
            spaceBefore=4,
            spaceAfter=6,
        ),
        body=body,
        small=ParagraphStyle(
            name="EmpireSmall",
            parent=body,
            fontSize=8,
            leading=10,
            textColor=theme.dark_grey,
        ),
        code=ParagraphStyle(
            name="EmpireCode",
            parent=body,
            fontName=theme.code_font,
            fontSize=8,
            leading=10,
        ),
    )
