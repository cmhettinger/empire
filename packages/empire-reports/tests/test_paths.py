from __future__ import annotations

from datetime import date
from pathlib import Path

from empire_reports.contracts import OutputFormat, RenderContext, ReportMetadata
from empire_reports.paths import default_output_path, report_filename, slugify


def test_slugify_and_report_filename() -> None:
    metadata = ReportMetadata(
        report_id="Stonks Securities / Daily Summary",
        title="Daily Summary",
        as_of=date(2026, 6, 28),
    )

    assert slugify(metadata.report_id) == "stonks-securities-daily-summary"
    assert report_filename(metadata, OutputFormat.PDF) == "2026-06-28-stonks-securities-daily-summary.pdf"


def test_default_output_path_creates_target_dir(tmp_path: Path) -> None:
    metadata = ReportMetadata(report_id="Example Report", title="Example")
    context = RenderContext(output_dir=tmp_path)

    path = default_output_path(
        context=context,
        metadata=metadata,
        output_format=OutputFormat.JSON,
    )

    assert path == tmp_path / "json" / "example-report" / "example-report.json"
    assert path.parent.exists()
