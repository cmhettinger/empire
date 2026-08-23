from __future__ import annotations

import os
from datetime import date
from typing import Iterator
from uuid import UUID

import pytest

from empire_core import RunService
from empire_core.db.connection import EmpireDatabase
from empire_stonks_tech_indicators import (
    FeatureCounts,
    ReasonCount,
    ReportOutcome,
    TECH_INDICATORS_SAFE_FAILURE_MESSAGE,
    TechIndicatorsCoreRun,
    TechIndicatorsSummary,
    WorkflowKind,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)


@pytest.fixture
def database_connection() -> Iterator[object]:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")

    connection = EmpireDatabase.connect_from_env()
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def test_core_lifecycle_persists_heartbeat_success_and_safe_failure(
    database_connection: object,
) -> None:
    connection = database_connection
    run_service = RunService.from_connection(connection)
    run_ids: list[UUID] = []

    try:
        succeeded = TechIndicatorsCoreRun.start(
            run_service=run_service,
            workflow_kind=WorkflowKind.DAILY,
            effective_date=date(2026, 8, 22),
            run_type="cli",
            runner="pytest",
        )
        run_ids.append(succeeded.run_context.run_id)
        initial_heartbeat = succeeded.run_context.last_heartbeat_at
        heartbeat = succeeded.heartbeat()
        completed = succeeded.succeed(
            outcome=ReportOutcome.NO_OP,
            summary=TechIndicatorsSummary(
                counts=FeatureCounts(selected_listings=2),
            ),
        )

        failed = TechIndicatorsCoreRun.start(
            run_service=run_service,
            workflow_kind=WorkflowKind.BACKFILL,
            effective_date=date(2026, 8, 22),
            run_type="cli",
            runner="pytest",
        )
        run_ids.append(failed.run_context.run_id)
        failed_context = failed.fail(
            outcome=ReportOutcome.FAIL,
            summary=TechIndicatorsSummary(
                reason_counts=(ReasonCount("VALIDATION_FAILED", 1),),
                total_issue_count=1,
            ),
        )

        assert heartbeat.last_heartbeat_at is not None
        assert initial_heartbeat is not None
        assert heartbeat.last_heartbeat_at >= initial_heartbeat
        assert completed.status == "succeeded"
        assert completed.summary["heartbeat_count"] == 1
        assert failed_context.status == "failed"

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT
                    job_name,
                    subject_key,
                    status,
                    params,
                    summary,
                    error_message
                FROM core.core_run
                WHERE run_id = ANY(%s::uuid[])
                ORDER BY job_name
                """,
                ([str(run_id) for run_id in run_ids],),
            )
            rows = cursor.fetchall()

        assert [row[0] for row in rows] == [
            "stonks_tech_indicators_backfill",
            "stonks_tech_indicators_daily",
        ]
        assert all(row[1] == "all_series" for row in rows)
        assert {row[2] for row in rows} == {"failed", "succeeded"}
        assert all(
            set(row[3]) == {"workflow_kind", "calculation_version"}
            for row in rows
        )
        failed_row = next(row for row in rows if row[2] == "failed")
        assert failed_row[4]["reason_counts"] == [
            {"code": "VALIDATION_FAILED", "count": 1}
        ]
        assert failed_row[5] == TECH_INDICATORS_SAFE_FAILURE_MESSAGE
        assert "source" not in repr(rows).lower()
        assert "feature" not in repr(rows).lower()
    finally:
        connection.rollback()
        if run_ids:
            with connection.cursor() as cursor:  # type: ignore[union-attr]
                cursor.execute(
                    "DELETE FROM core.core_run WHERE run_id = ANY(%s::uuid[])",
                    ([str(run_id) for run_id in run_ids],),
                )
            connection.commit()
            with connection.cursor() as cursor:  # type: ignore[union-attr]
                cursor.execute(
                    "SELECT count(*) FROM core.core_run WHERE run_id = ANY(%s::uuid[])",
                    ([str(run_id) for run_id in run_ids],),
                )
                assert cursor.fetchone() == (0,)
