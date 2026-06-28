from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from empire_reports.artifacts import ReportArtifact
from empire_reports.contracts import OutputFormat, RenderContext, RenderResult, ReportMetadata
from empire_reports.paths import default_output_path


def write_json_report(
    *,
    metadata: ReportMetadata,
    context: RenderContext,
    payload: Any,
    out_path: Path | None = None,
    indent: int = 2,
) -> RenderResult:
    path = out_path or default_output_path(
        context=context,
        metadata=metadata,
        output_format=OutputFormat.JSON,
    )
    resolved = Path(path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, indent=indent, sort_keys=True, default=str) + "\n")
    artifact = ReportArtifact(
        path=resolved,
        output_format=OutputFormat.JSON,
        media_type="application/json",
        logical_name=metadata.report_id,
    )
    return RenderResult(
        report=metadata,
        artifacts=(artifact,),
        generated_at=metadata.generated_timestamp(),
    )
