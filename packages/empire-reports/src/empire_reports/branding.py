from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


EMPIRE_PRIMARY_RED: Final[str] = "#8B0000"
EMPIRE_ACCENT_RED: Final[str] = "#C1121F"
EMPIRE_LIGHT_GREY: Final[str] = "#C9C9C9"
EMPIRE_DARK_GREY: Final[str] = "#2B2B2B"
WHITE: Final[str] = "#FFFFFF"
BLACK: Final[str] = "#000000"


@dataclass(frozen=True, slots=True)
class BrandingConfig:
    root: Path

    @classmethod
    def discover(cls, start: Path | None = None) -> "BrandingConfig":
        env_root = os.environ.get("EMPIRE_BRANDING_ROOT")
        if env_root:
            return cls(root=Path(env_root).expanduser().resolve())

        start_path = Path(start or Path.cwd()).expanduser().resolve()
        for candidate in (start_path, *start_path.parents):
            branding_root = candidate / "resources" / "branding"
            if branding_root.exists():
                return cls(root=branding_root)

        package_root = Path(__file__).resolve()
        for candidate in package_root.parents:
            branding_root = candidate / "resources" / "branding"
            if branding_root.exists():
                return cls(root=branding_root)

        return cls(root=(start_path / "resources" / "branding").resolve())

    @property
    def fonts_dir(self) -> Path:
        return self.root / "fonts"

    @property
    def logo_dir(self) -> Path:
        return self.root / "logo"

    def logo_path(
        self,
        *,
        color: str = "red",
        lockup: str = "horizontal",
        size: str = "256h",
        extension: str = "png",
    ) -> Path:
        suffix = f"-{lockup}" if lockup in {"horizontal", "vertical"} else ""
        folder = "SVG" if extension.lower() == "svg" else size
        return self.logo_dir / color / folder / f"empire-logo{suffix}.{extension}"


@dataclass(frozen=True, slots=True)
class ReportTheme:
    primary: object = HexColor(EMPIRE_PRIMARY_RED)
    accent: object = HexColor(EMPIRE_ACCENT_RED)
    light_grey: object = HexColor(EMPIRE_LIGHT_GREY)
    dark_grey: object = HexColor(EMPIRE_DARK_GREY)
    white: object = HexColor(WHITE)
    black: object = HexColor(BLACK)
    body_font: str = "SourceSans3-Regular"
    body_bold_font: str = "SourceSans3-Bold"
    body_semibold_font: str = "SourceSans3-SemiBold"
    body_light_font: str = "SourceSans3-Light"
    display_font: str = "Cinzel-Bold"
    code_font: str = "SourceCodePro-Regular"

    def reportlab_fonts(self) -> "ReportTheme":
        return self


def _is_font_registered(font_name: str) -> bool:
    try:
        pdfmetrics.getFont(font_name)
        return True
    except KeyError:
        return False


def register_brand_fonts(config: BrandingConfig | None = None) -> ReportTheme:
    branding = config or BrandingConfig.discover()
    if branding.fonts_dir.exists():
        for font_path in sorted(branding.fonts_dir.rglob("*.otf")) + sorted(branding.fonts_dir.rglob("*.ttf")):
            font_name = font_path.stem
            if not _is_font_registered(font_name):
                pdfmetrics.registerFont(TTFont(font_name, str(font_path)))

    theme = ReportTheme()
    return _theme_with_fallbacks(theme)


def _theme_with_fallbacks(theme: ReportTheme) -> ReportTheme:
    return ReportTheme(
        primary=theme.primary,
        accent=theme.accent,
        light_grey=theme.light_grey,
        dark_grey=theme.dark_grey,
        white=theme.white,
        black=theme.black,
        body_font=_font_or_fallback(theme.body_font, "Helvetica"),
        body_bold_font=_font_or_fallback(theme.body_bold_font, "Helvetica-Bold"),
        body_semibold_font=_font_or_fallback(theme.body_semibold_font, "Helvetica-Bold"),
        body_light_font=_font_or_fallback(theme.body_light_font, "Helvetica"),
        display_font=_font_or_fallback(theme.display_font, "Times-Bold"),
        code_font=_font_or_fallback(theme.code_font, "Courier"),
    )


def _font_or_fallback(font_name: str, fallback: str) -> str:
    return font_name if _is_font_registered(font_name) else fallback
