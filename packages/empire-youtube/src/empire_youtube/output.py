"""Output helpers for YouTube scrape results."""

from __future__ import annotations

from pathlib import Path

from empire_youtube.models import YouTubeScrapeResult


def write_result_to_file(
    result: YouTubeScrapeResult,
    path: str | Path,
) -> Path:
    """Write a scrape result JSON payload to an explicit filesystem path."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.to_json(), encoding="utf-8")
    return output_path
