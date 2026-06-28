from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from empire_reports.contracts import OutputFormat


@dataclass(frozen=True, slots=True)
class ReportArtifact:
    path: Path
    output_format: OutputFormat
    media_type: str
    logical_name: str | None = None
    object_key: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def resolved_path(self) -> Path:
        return Path(self.path).expanduser().resolve()

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def exists(self) -> bool:
        return self.resolved_path().exists()
