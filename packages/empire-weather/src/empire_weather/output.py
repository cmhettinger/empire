"""Filesystem output helpers for local weather debugging."""

from __future__ import annotations

from pathlib import Path

from empire_weather.models import WeatherCollectionResult


def write_result_to_file(result: WeatherCollectionResult, output_file: str | Path) -> Path:
    """Write normalized weather JSON to a local path."""

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.to_json(), encoding="utf-8")
    return output_path
