from __future__ import annotations

import os
from datetime import date
from typing import Iterator
from uuid import uuid4

import pytest

from empire_core import RunContext, RunService
from empire_core.db.connection import EmpireDatabase
from empire_stonks_ohlcv import (
    OHLCVConfig,
    ProviderImportResult,
    SAFE_FAILURE_MESSAGE,
    run_provider_import,
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


def test_run_wrapper_records_success_and_failure_in_postgres(
    database_connection: object,
) -> None:
    connection = database_connection
    marker = str(uuid4())
    success_subject = f"c45-success:{marker}"
    failure_subject = f"c45-failure:{marker}"
    run_service = RunService.from_connection(connection)

    try:
        succeeded = run_provider_import(
            run_service=run_service,
            config=OHLCVConfig(),
            provider_code="EODDATA",
            job_name="stonks_ohlcv_eoddata_daily",
            effective_date=date(2026, 7, 16),
            run_type="cli",
            runner="pytest",
            subject_key=success_subject,
            work=lambda _context: ProviderImportResult(provider_code="EODDATA"),
        )

        def fail_work(_context: RunContext) -> ProviderImportResult:
            raise RuntimeError("provider detail must not enter Core")

        with pytest.raises(RuntimeError, match="must not enter Core"):
            run_provider_import(
                run_service=run_service,
                config=OHLCVConfig(),
                provider_code="EODDATA",
                job_name="stonks_ohlcv_eoddata_daily",
                effective_date=date(2026, 7, 16),
                run_type="cli",
                runner="pytest",
                subject_key=failure_subject,
                work=fail_work,
            )

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT status, params, summary, error_message
                FROM core.core_run
                WHERE subject_key = %s
                """,
                (success_subject,),
            )
            success_row = cursor.fetchone()
            assert success_row == (
                "succeeded",
                {
                    "provider_code": "EODDATA",
                    "configuration": OHLCVConfig().to_safe_dict(),
                },
                succeeded.summary,
                None,
            )
            cursor.execute(
                """
                SELECT status, params, summary, error_message
                FROM core.core_run
                WHERE subject_key = %s
                """,
                (failure_subject,),
            )
            failed_row = cursor.fetchone()
            assert failed_row == (
                "failed",
                {
                    "provider_code": "EODDATA",
                    "configuration": OHLCVConfig().to_safe_dict(),
                },
                {"provider_code": "EODDATA", "outcome": "failed"},
                SAFE_FAILURE_MESSAGE,
            )
            assert "provider detail" not in repr(failed_row)
    finally:
        connection.rollback()
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                DELETE FROM core.core_run
                WHERE subject_key IN (%s, %s)
                """,
                (success_subject, failure_subject),
            )
        connection.commit()
