"""Shared report object-store path helpers for stonks securities."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPORT_AREA = "stonks/securities"


def run_report_object_key(
    *,
    storage_key: str,
    report_type: str,
    logical_date: Any = None,
    generated_at: datetime | None = None,
) -> str:
    report_date = _report_date(logical_date=logical_date, generated_at=generated_at)
    return "/".join(
        [
            storage_key.strip("/"),
            "runs",
            f"{report_date:%Y}",
            f"{report_date:%m}",
            f"{report_date:%d}",
            "run-reports",
            report_type.strip("/"),
        ]
    )


def run_report_path(
    *,
    root: str | Path,
    report_type: str,
    filename: str,
    logical_date: Any = None,
    generated_at: datetime | None = None,
) -> Path:
    report_date = _report_date(logical_date=logical_date, generated_at=generated_at)
    return (
        Path(root)
        / REPORT_AREA
        / "runs"
        / f"{report_date:%Y}"
        / f"{report_date:%m}"
        / f"{report_date:%d}"
        / "run-reports"
        / report_type.strip("/")
        / filename
    )


def _report_date(*, logical_date: Any, generated_at: datetime | None) -> datetime:
    parsed = _parse_datetime(logical_date)
    if parsed is not None:
        return parsed
    fallback = generated_at or datetime.now(UTC)
    return fallback if fallback.tzinfo else fallback.replace(tzinfo=UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
