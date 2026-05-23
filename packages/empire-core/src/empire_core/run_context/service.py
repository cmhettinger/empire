"""Run context service."""

from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import UUID

from empire_core.exceptions import NotFoundError, ValidationError
from empire_core.run_context.models import JsonDict, RunContext
from empire_core.run_context.repository import PostgresRunRepository, RunRepository

logger = logging.getLogger(__name__)

RUN_TYPES = {"airflow", "cli", "api", "manual", "agent"}


class RunService:
    """Lightweight run tracking service for Empire business lineage."""

    def __init__(self, repository: RunRepository):
        self.repository = repository

    @classmethod
    def from_connection(cls, connection) -> "RunService":
        return cls(PostgresRunRepository(connection))

    def start_run(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None = None,
        effective_date: date | None = None,
        run_type: str,
        runner: str,
        runner_ref: JsonDict | None = None,
        params: JsonDict | None = None,
        heartbeat_timeout_seconds: int | None = None,
    ) -> RunContext:
        _require_text(domain, "domain")
        _require_text(job_name, "job_name")
        _require_text(runner, "runner")
        if run_type not in RUN_TYPES:
            raise ValidationError(f"Unsupported run_type: {run_type}")
        if heartbeat_timeout_seconds is not None and heartbeat_timeout_seconds <= 0:
            raise ValidationError("heartbeat_timeout_seconds must be positive")

        logger.info("Starting run for %s.%s", domain, job_name)
        return self.repository.start_run(
            domain=domain,
            job_name=job_name,
            subject_key=subject_key,
            effective_date=effective_date,
            run_type=run_type,
            runner=runner,
            runner_ref=runner_ref or {},
            params=params or {},
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
        )

    def complete_run(self, run_id: UUID, summary: JsonDict | None = None) -> RunContext:
        logger.info("Completing run %s", run_id)
        return self.repository.complete_run(run_id, summary or {})

    def fail_run(
        self,
        run_id: UUID,
        error_message: str,
        summary: JsonDict | None = None,
    ) -> RunContext:
        _require_text(error_message, "error_message")
        logger.info("Failing run %s", run_id)
        return self.repository.fail_run(run_id, error_message, summary or {})

    def heartbeat(self, run_id: UUID) -> RunContext:
        logger.debug("Recording heartbeat for run %s", run_id)
        return self.repository.heartbeat(run_id)

    def get_run_context(self, run_id: UUID) -> RunContext:
        ctx = self.repository.get_run_context(run_id)
        if ctx is None:
            raise NotFoundError(f"Run not found: {run_id}")
        return ctx

    def find_latest_successful_run(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None = None,
        effective_date: date | None = None,
        before: datetime | None = None,
    ) -> RunContext | None:
        return self.repository.find_latest_successful_run(
            domain=domain,
            job_name=job_name,
            subject_key=subject_key,
            effective_date=effective_date,
            before=before,
        )

    def find_successful_runs(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[RunContext]:
        if limit <= 0:
            raise ValidationError("limit must be positive")
        return self.repository.find_successful_runs(
            domain=domain,
            job_name=job_name,
            subject_key=subject_key,
            after=after,
            before=before,
            limit=limit,
        )


def _require_text(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValidationError(f"{name} is required")
