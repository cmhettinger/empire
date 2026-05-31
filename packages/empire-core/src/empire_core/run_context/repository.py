"""Run context repository interfaces and Postgres implementation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from empire_core.db.postgres import json_dumps, row_to_dict
from empire_core.run_context.models import JsonDict, RunContext


class RunRepository(Protocol):
    def start_run(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None,
        effective_date: date | None,
        run_type: str,
        runner: str,
        runner_ref: JsonDict,
        params: JsonDict,
        heartbeat_timeout_seconds: int | None,
    ) -> RunContext: ...

    def complete_run(self, run_id: UUID, summary: JsonDict | None) -> RunContext: ...

    def fail_run(
        self, run_id: UUID, error_message: str, summary: JsonDict | None
    ) -> RunContext: ...

    def heartbeat(self, run_id: UUID) -> RunContext: ...

    def get_run_context(self, run_id: UUID) -> RunContext | None: ...

    def find_latest_successful_run(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None,
        effective_date: date | None,
        before: datetime | None,
    ) -> RunContext | None: ...

    def find_successful_runs(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None,
        after: datetime | None,
        before: datetime | None,
        limit: int,
    ) -> list[RunContext]: ...


class PostgresRunRepository:
    """Postgres-backed run context repository."""

    def __init__(self, connection: Any):
        self.connection = connection

    def start_run(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None,
        effective_date: date | None,
        run_type: str,
        runner: str,
        runner_ref: JsonDict,
        params: JsonDict,
        heartbeat_timeout_seconds: int | None,
    ) -> RunContext:
        row = self._fetchone(
            """
            INSERT INTO core.core_run (
                domain, job_name, subject_key, effective_date,
                run_type, status, heartbeat_timeout_seconds,
                last_heartbeat_at, stale_after, runner, runner_ref, params
            )
            VALUES (
                %s, %s, %s, %s,
                %s, 'started', %s,
                CASE WHEN %s::integer IS NULL THEN NULL ELSE now() END,
                CASE WHEN %s::integer IS NULL THEN NULL ELSE now() + (%s::integer * interval '1 second') END,
                %s, %s::jsonb, %s::jsonb
            )
            RETURNING *
            """,
            (
                domain,
                job_name,
                subject_key,
                effective_date,
                run_type,
                heartbeat_timeout_seconds,
                heartbeat_timeout_seconds,
                heartbeat_timeout_seconds,
                heartbeat_timeout_seconds,
                runner,
                json_dumps(runner_ref),
                json_dumps(params),
            ),
        )
        self.connection.commit()
        return _run_from_row(row)

    def complete_run(self, run_id: UUID, summary: JsonDict | None) -> RunContext:
        row = self._fetchone(
            """
            UPDATE core.core_run
            SET status = 'succeeded',
                completed_at = now(),
                summary = %s::jsonb,
                updated_at = now()
            WHERE run_id = %s
            RETURNING *
            """,
            (json_dumps(summary or {}), run_id),
        )
        self.connection.commit()
        return _run_from_row(row)

    def fail_run(
        self, run_id: UUID, error_message: str, summary: JsonDict | None
    ) -> RunContext:
        row = self._fetchone(
            """
            UPDATE core.core_run
            SET status = 'failed',
                completed_at = now(),
                error_message = %s,
                summary = %s::jsonb,
                updated_at = now()
            WHERE run_id = %s
            RETURNING *
            """,
            (error_message, json_dumps(summary or {}), run_id),
        )
        self.connection.commit()
        return _run_from_row(row)

    def heartbeat(self, run_id: UUID) -> RunContext:
        row = self._fetchone(
            """
            UPDATE core.core_run
            SET last_heartbeat_at = now(),
                stale_after = CASE
                    WHEN heartbeat_timeout_seconds IS NULL THEN stale_after
                    ELSE now() + (heartbeat_timeout_seconds * interval '1 second')
                END,
                updated_at = now()
            WHERE run_id = %s
            RETURNING *
            """,
            (run_id,),
        )
        self.connection.commit()
        return _run_from_row(row)

    def get_run_context(self, run_id: UUID) -> RunContext | None:
        row = self._fetchone_or_none(
            "SELECT * FROM core.core_run WHERE run_id = %s",
            (run_id,),
        )
        return _run_from_row(row) if row else None

    def find_latest_successful_run(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None,
        effective_date: date | None,
        before: datetime | None,
    ) -> RunContext | None:
        rows = self._fetchall(
            """
            SELECT *
            FROM core.core_run
            WHERE domain = %s
              AND job_name = %s
              AND status = 'succeeded'
              AND (%s::text IS NULL OR subject_key = %s)
              AND (%s::date IS NULL OR effective_date = %s)
              AND (%s::timestamptz IS NULL OR completed_at <= %s)
            ORDER BY completed_at DESC NULLS LAST, started_at DESC
            LIMIT 1
            """,
            (
                domain,
                job_name,
                subject_key,
                subject_key,
                effective_date,
                effective_date,
                before,
                before,
            ),
        )
        return _run_from_row(rows[0]) if rows else None

    def find_successful_runs(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None,
        after: datetime | None,
        before: datetime | None,
        limit: int,
    ) -> list[RunContext]:
        rows = self._fetchall(
            """
            SELECT *
            FROM core.core_run
            WHERE domain = %s
              AND job_name = %s
              AND status = 'succeeded'
              AND (%s::text IS NULL OR subject_key = %s)
              AND (%s::timestamptz IS NULL OR completed_at >= %s)
              AND (%s::timestamptz IS NULL OR completed_at <= %s)
            ORDER BY completed_at DESC NULLS LAST, started_at DESC
            LIMIT %s
            """,
            (domain, job_name, subject_key, subject_key, after, after, before, before, limit),
        )
        return [_run_from_row(row) for row in rows]

    def _fetchone(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
        row = self._fetchone_or_none(sql, params)
        if row is None:
            raise LookupError("Run was not found")
        return row

    def _fetchone_or_none(
        self, sql: str, params: tuple[Any, ...]
    ) -> dict[str, Any] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return row_to_dict(cursor, row) if row is not None else None

    def _fetchall(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return [row_to_dict(cursor, row) for row in cursor.fetchall()]


def _run_from_row(row: dict[str, Any]) -> RunContext:
    return RunContext(
        run_id=row["run_id"],
        domain=row["domain"],
        job_name=row["job_name"],
        subject_key=row.get("subject_key"),
        effective_date=row.get("effective_date"),
        run_type=row["run_type"],
        status=row["status"],
        runner=row["runner"],
        params=row.get("params") or {},
        summary=row.get("summary") or {},
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        heartbeat_timeout_seconds=row.get("heartbeat_timeout_seconds"),
        last_heartbeat_at=row.get("last_heartbeat_at"),
        stale_after=row.get("stale_after"),
    )
