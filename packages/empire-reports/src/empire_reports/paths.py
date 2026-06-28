from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from empire_reports.contracts import OutputFormat, RenderContext, ReportMetadata


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return slug or "report"


def report_filename(
    metadata: ReportMetadata,
    output_format: OutputFormat,
    *,
    as_of: date | None = None,
) -> str:
    effective_date = as_of or metadata.as_of
    date_prefix = f"{effective_date.isoformat()}-" if effective_date else ""
    return f"{date_prefix}{slugify(metadata.report_id)}.{output_format.value}"


def default_output_path(
    *,
    context: RenderContext,
    metadata: ReportMetadata,
    output_format: OutputFormat,
    filename: str | None = None,
) -> Path:
    out_dir = context.resolved_output_dir() / output_format.value / slugify(metadata.report_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / (filename or report_filename(metadata, output_format))
