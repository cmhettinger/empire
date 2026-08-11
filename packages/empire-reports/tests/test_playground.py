from __future__ import annotations

from datetime import date
from pathlib import Path

from empire_reports.playground import (
    default_playground_output_path,
    playground_pages,
    render_report_playground,
)


def test_playground_registry_has_unique_page_keys() -> None:
    pages = playground_pages()

    assert pages[0].key == "professional-title-page"
    assert len(pages) >= 7
    assert len({page.key for page in pages}) == len(pages)
    assert all(page.description for page in pages)
    assert all(page.options for page in pages)


def test_report_playground_renders_to_requested_path(tmp_path: Path) -> None:
    output_path = tmp_path / "report-playground.pdf"

    result = render_report_playground(
        output_path=output_path,
        report_date=date(2026, 8, 11),
    )

    artifact = result.primary_artifact
    assert artifact.resolved_path() == output_path.resolve()
    assert artifact.exists
    assert artifact.resolved_path().stat().st_size > 50_000


def test_default_playground_path_uses_empire_temp_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("EMPIRE_TEMP_DIR", str(tmp_path))

    assert default_playground_output_path() == tmp_path / "report-playground.pdf"
