from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from empire_reports.artifacts import ReportArtifact


class OutputFormat(StrEnum):
    PDF = "pdf"
    AUDIO = "audio"
    VIDEO = "video"
    JSON = "json"
    XLSX = "xlsx"
    HTML = "html"
    EMAIL = "email"


@dataclass(frozen=True, slots=True)
class ReportMetadata:
    report_id: str
    title: str
    as_of: date | None = None
    subtitle: str | None = None
    description: str | None = None
    author: str = "Empire"
    generated_at: datetime | None = None
    tags: tuple[str, ...] = ()

    def generated_timestamp(self) -> datetime:
        return self.generated_at or datetime.now().astimezone()


@dataclass(frozen=True, slots=True)
class RenderContext:
    output_dir: Path
    run_id: UUID | None = None
    object_scope: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def resolved_output_dir(self) -> Path:
        return Path(self.output_dir).expanduser().resolve()


@dataclass(frozen=True, slots=True)
class RenderResult:
    report: ReportMetadata
    artifacts: tuple["ReportArtifact", ...]
    generated_at: datetime

    @property
    def primary_artifact(self) -> "ReportArtifact":
        if not self.artifacts:
            raise ValueError("RenderResult has no artifacts")
        return self.artifacts[0]


class Renderer(Protocol):
    output_format: OutputFormat

    def render(self) -> RenderResult: ...
