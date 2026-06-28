from __future__ import annotations

from datetime import date
from pathlib import Path

from empire_reports.artifacts import ReportArtifact
from empire_reports.contracts import OutputFormat, RenderContext, RenderResult, ReportMetadata


def test_artifact_and_result_models(tmp_path: Path) -> None:
    path = tmp_path / "report.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    metadata = ReportMetadata(
        report_id="example.report",
        title="Example Report",
        as_of=date(2026, 6, 28),
    )
    artifact = ReportArtifact(
        path=path,
        output_format=OutputFormat.PDF,
        media_type="application/pdf",
    )
    result = RenderResult(
        report=metadata,
        artifacts=(artifact,),
        generated_at=metadata.generated_timestamp(),
    )

    assert artifact.filename == "report.pdf"
    assert artifact.exists
    assert result.primary_artifact is artifact


def test_render_context_resolves_output_dir(tmp_path: Path) -> None:
    context = RenderContext(output_dir=tmp_path / "nested")

    assert context.resolved_output_dir() == (tmp_path / "nested").resolve()
