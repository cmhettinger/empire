"""Reusable report rendering primitives for Empire."""

from empire_reports.artifacts import ReportArtifact
from empire_reports.contracts import (
    OutputFormat,
    Renderer,
    RenderContext,
    RenderResult,
    ReportMetadata,
)

__version__ = "0.1.0"

__all__ = [
    "OutputFormat",
    "Renderer",
    "RenderContext",
    "RenderResult",
    "ReportArtifact",
    "ReportMetadata",
    "__version__",
]
