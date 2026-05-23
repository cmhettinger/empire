"""Run context models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class RunContext:
    run_id: UUID
    domain: str
    job_name: str
    subject_key: str | None
    effective_date: date | None
    run_type: str
    status: str
    runner: str
    params: JsonDict = field(default_factory=dict)
    summary: JsonDict = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    heartbeat_timeout_seconds: int | None = None
    last_heartbeat_at: datetime | None = None
    stale_after: datetime | None = None
