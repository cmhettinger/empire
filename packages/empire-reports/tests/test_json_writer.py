from __future__ import annotations

import json
from pathlib import Path

from empire_reports.contracts import OutputFormat, RenderContext, ReportMetadata
from empire_reports.renderers.json import write_json_report


def test_write_json_report(tmp_path: Path) -> None:
    metadata = ReportMetadata(report_id="example", title="Example")
    result = write_json_report(
        metadata=metadata,
        context=RenderContext(output_dir=tmp_path),
        payload={"ok": True},
    )

    artifact = result.primary_artifact
    assert artifact.output_format == OutputFormat.JSON
    assert json.loads(artifact.resolved_path().read_text()) == {"ok": True}
