from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from empire_reports.branding import BrandingConfig, EMPIRE_PRIMARY_RED, register_brand_fonts


def test_branding_discovers_repo_assets() -> None:
    config = BrandingConfig.discover(Path(__file__))

    assert config.root.name == "branding"
    assert config.logo_path(color="red", lockup="horizontal", size="256h").exists()
    assert config.fonts_dir.exists()


def test_register_brand_fonts_returns_usable_theme() -> None:
    theme = register_brand_fonts(BrandingConfig.discover(Path(__file__)))

    assert EMPIRE_PRIMARY_RED == "#8B0000"
    assert theme.body_font == "SourceSans3-Regular"
    assert theme.body_semibold_font == "SourceSans3-SemiBold"
    assert theme.display_font == "Cinzel-Bold"
    assert theme.code_font == "SourceCodePro-Regular"


def test_all_branding_fonts_register_with_reportlab() -> None:
    config = BrandingConfig.discover(Path(__file__))
    font_paths = sorted(config.fonts_dir.rglob("*.otf")) + sorted(config.fonts_dir.rglob("*.ttf"))

    assert font_paths
    for font_path in font_paths:
        pdfmetrics.registerFont(TTFont(f"Test-{font_path.stem}", str(font_path)))
