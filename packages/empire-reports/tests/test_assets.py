from __future__ import annotations

from pathlib import Path

import pytest

from empire_reports.assets import AssetRegistry
from empire_reports.branding import BrandingConfig
from empire_reports.contracts import RenderContext, ReportMetadata
from empire_reports.renderers.pdf import PdfRenderer


def test_asset_registry_discovers_repo_resources() -> None:
    assets = AssetRegistry.discover(Path(__file__))

    assert assets.root.name == "resources"
    assert assets.image_path("buffett-no-crying.png").exists()
    assert assets.icon_path("bar-chart-1.svg").exists()


def test_asset_registry_uses_environment_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resources_root = tmp_path / "runtime-resources"
    images_dir = resources_root / "images"
    icons_dir = images_dir / "icons"
    icons_dir.mkdir(parents=True)
    image_path = images_dir / "example.png"
    icon_path = icons_dir / "example.svg"
    image_path.write_bytes(b"image")
    icon_path.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setenv("EMPIRE_RESOURCES_ROOT", str(resources_root))

    assets = AssetRegistry.discover()

    assert assets.root == resources_root
    assert assets.image_path("example.png") == image_path
    assert assets.icon_path("example.svg") == icon_path
    assert BrandingConfig.discover().root == resources_root / "branding"


def test_asset_registry_rejects_missing_and_escaping_paths(tmp_path: Path) -> None:
    assets = AssetRegistry(root=tmp_path)

    with pytest.raises(FileNotFoundError, match="Image not found"):
        assets.image_path("missing.png")
    with pytest.raises(ValueError, match="escapes"):
        assets.icon_path("../outside.svg")


def test_pdf_renderer_uses_its_asset_registry_for_branding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EMPIRE_BRANDING_ROOT", raising=False)
    resources_root = tmp_path / "resources"
    assets = AssetRegistry(root=resources_root)

    renderer = PdfRenderer(
        metadata=ReportMetadata(report_id="assets", title="Assets"),
        context=RenderContext(output_dir=tmp_path / "output"),
        assets=assets,
    )

    assert renderer.assets is assets
    assert renderer.branding.root == assets.branding_dir
