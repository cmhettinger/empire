from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from empire_core import RunContext, RunService
from empire_stonks_ohlcv import (
    AcquiredObject,
    EODDataCredentials,
    ImportIssue,
    OHLCVConfig,
    OHLCVConfigError,
    OHLCVWorkflowError,
    PersistenceCounts,
    ProviderImportResult,
    SAFE_FAILURE_MESSAGE,
    run_provider_import,
)


SECRET = "private-eoddata-runner-key"
EFFECTIVE_DATE = date(2026, 7, 16)


class FakeRunRepository:
    """In-memory Core run repository with persisted params and failures."""

    def __init__(self) -> None:
        self.runs: dict[UUID, RunContext] = {}
        self.runner_refs: dict[UUID, dict[str, object]] = {}
        self.failure_messages: dict[UUID, str] = {}

    def start_run(self, **values: object) -> RunContext:
        now = datetime.now(UTC)
        run_context = RunContext(
            run_id=uuid4(),
            domain=values["domain"],
            job_name=values["job_name"],
            subject_key=values["subject_key"],
            effective_date=values["effective_date"],
            run_type=values["run_type"],
            status="started",
            runner=values["runner"],
            params=values["params"],
            started_at=now,
        )
        self.runs[run_context.run_id] = run_context
        self.runner_refs[run_context.run_id] = values["runner_ref"]
        return run_context

    def complete_run(
        self,
        run_id: UUID,
        summary: dict[str, object] | None,
    ) -> RunContext:
        completed = replace(
            self.runs[run_id],
            status="succeeded",
            summary=summary or {},
            completed_at=datetime.now(UTC),
        )
        self.runs[run_id] = completed
        return completed

    def fail_run(
        self,
        run_id: UUID,
        error_message: str,
        summary: dict[str, object] | None,
    ) -> RunContext:
        failed = replace(
            self.runs[run_id],
            status="failed",
            summary=summary or {},
            completed_at=datetime.now(UTC),
        )
        self.runs[run_id] = failed
        self.failure_messages[run_id] = error_message
        return failed


def configured() -> OHLCVConfig:
    return OHLCVConfig(
        eoddata_credentials=EODDataCredentials(api_key=SECRET),
    )


def import_result() -> ProviderImportResult:
    return ProviderImportResult(
        provider_code="EODDATA",
        acquired_objects=(
            AcquiredObject(
                source_code="eoddata_daily",
                object_id=UUID("10000000-0000-4000-8000-000000000001"),
                object_key="stonks/ohlcv/eoddata/run/raw",
                filename="raw.csv",
                size_bytes=42,
                checksum_sha256="ab" * 32,
            ),
        ),
        listing_counts=PersistenceCounts(inserted=2, unchanged=1),
        bar_counts=PersistenceCounts(
            inserted=10,
            updated=2,
            unchanged=3,
            derived_updated=1,
        ),
        rejected=1,
        failures=(
            ImportIssue(code="bad_row", message=f"failure containing {SECRET}"),
        ),
        warnings=(ImportIssue(code="gap", message="weekday-shaped gap"),),
    )


def test_success_starts_completes_and_returns_compact_summary() -> None:
    repository = FakeRunRepository()
    seen_contexts: list[RunContext] = []

    def work(run_context: RunContext) -> ProviderImportResult:
        seen_contexts.append(run_context)
        return import_result()

    result = run_provider_import(
        run_service=RunService(repository),
        config=configured(),
        provider_code="EODDATA",
        job_name="stonks_ohlcv_eoddata_daily",
        effective_date=EFFECTIVE_DATE,
        run_type="cli",
        runner="pytest",
        runner_ref={"command": "test"},
        work=work,
    )

    stored = repository.runs[result.run_context.run_id]
    assert seen_contexts[0].status == "started"
    assert seen_contexts[0].effective_date == EFFECTIVE_DATE
    assert result.run_context.status == "succeeded"
    assert stored.summary == {
        "provider_code": "EODDATA",
        "acquired_object_count": 1,
        "listing_counts": {
            "inserted": 2,
            "updated": 0,
            "unchanged": 1,
            "derived_updated": 0,
        },
        "bar_counts": {
            "inserted": 10,
            "updated": 2,
            "unchanged": 3,
            "derived_updated": 1,
        },
        "accepted": 15,
        "rejected": 1,
        "failure_count": 1,
        "warning_count": 1,
    }
    assert result.to_dict() == {
        "run_id": str(result.run_context.run_id),
        "status": "succeeded",
        "summary": stored.summary,
    }
    serialized_core_fields = repr(
        {
            "params": stored.params,
            "summary": stored.summary,
            "runner_ref": repository.runner_refs[stored.run_id],
        }
    )
    assert SECRET not in serialized_core_fields
    assert stored.params["configuration"]["eoddata_configured"] is True


def test_failure_marks_run_with_safe_details_and_reraises() -> None:
    repository = FakeRunRepository()

    def work(_run_context: RunContext) -> ProviderImportResult:
        raise RuntimeError(f"provider error containing {SECRET}")

    with pytest.raises(RuntimeError, match=SECRET):
        run_provider_import(
            run_service=RunService(repository),
            config=configured(),
            provider_code="EODDATA",
            job_name="stonks_ohlcv_eoddata_daily",
            effective_date=EFFECTIVE_DATE,
            run_type="cli",
            runner="pytest",
            work=work,
        )

    failed = next(iter(repository.runs.values()))
    assert failed.status == "failed"
    assert failed.summary == {
        "provider_code": "EODDATA",
        "outcome": "failed",
    }
    assert repository.failure_messages[failed.run_id] == SAFE_FAILURE_MESSAGE
    assert SECRET not in repr(failed)
    assert SECRET not in repository.failure_messages[failed.run_id]


def test_workflow_failure_records_only_the_safe_failed_stage() -> None:
    repository = FakeRunRepository()

    def work(_run_context: RunContext) -> ProviderImportResult:
        raise OHLCVWorkflowError("parsing") from RuntimeError(SECRET)

    with pytest.raises(OHLCVWorkflowError, match="parsing"):
        run_provider_import(
            run_service=RunService(repository),
            config=configured(),
            provider_code="EODDATA",
            job_name="stonks_ohlcv_eoddata_daily",
            effective_date=EFFECTIVE_DATE,
            run_type="cli",
            runner="pytest",
            work=work,
        )

    failed = next(iter(repository.runs.values()))
    assert failed.summary == {
        "provider_code": "EODDATA",
        "outcome": "failed",
        "failed_stage": "parsing",
    }
    assert SECRET not in repr(failed.summary)


@pytest.mark.parametrize(
    ("provider_code", "job_name", "message"),
    [
        ("EODDATA", "unknown_job", "job_name"),
        ("YAHOO", "stonks_ohlcv_eoddata_daily", "does not match"),
    ],
)
def test_invalid_job_contract_does_not_start_run(
    provider_code: str,
    job_name: str,
    message: str,
) -> None:
    repository = FakeRunRepository()

    with pytest.raises(OHLCVConfigError, match=message):
        run_provider_import(
            run_service=RunService(repository),
            config=OHLCVConfig(),
            provider_code=provider_code,
            job_name=job_name,
            effective_date=EFFECTIVE_DATE,
            run_type="cli",
            runner="pytest",
            work=lambda _context: ProviderImportResult(
                provider_code=provider_code,
            ),
        )

    assert repository.runs == {}


def test_wrong_provider_result_fails_started_run() -> None:
    repository = FakeRunRepository()

    with pytest.raises(ValueError, match="different provider"):
        run_provider_import(
            run_service=RunService(repository),
            config=OHLCVConfig(),
            provider_code="EODDATA",
            job_name="stonks_ohlcv_eoddata_daily",
            effective_date=EFFECTIVE_DATE,
            run_type="cli",
            runner="pytest",
            work=lambda _context: ProviderImportResult(provider_code="YAHOO"),
        )

    failed = next(iter(repository.runs.values()))
    assert failed.status == "failed"
