from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from empire_core import RunContext, RunService
from empire_stonks_ohlcv import (
    AcquiredObject,
    EODDATA_DAILY_SOURCE,
    OHLCVConfig,
    OHLCVWorkflowError,
    ParsedProviderOutput,
    ProviderImportResult,
    run_provider_pipeline,
)
from empire_stonks_ohlcv import runner as runner_module


RUN_ID = UUID("10000000-0000-4000-8000-000000000001")
OBJECT_ID = UUID("20000000-0000-4000-8000-000000000002")
EFFECTIVE_DATE = date(2026, 7, 16)


class FakeRunRepository:
    def __init__(self) -> None:
        self.run: RunContext | None = None

    def start_run(self, **values: object) -> RunContext:
        self.run = RunContext(
            run_id=RUN_ID,
            domain=values["domain"],
            job_name=values["job_name"],
            subject_key=values["subject_key"],
            effective_date=values["effective_date"],
            run_type=values["run_type"],
            status="started",
            runner=values["runner"],
            params=values["params"],
            started_at=datetime.now(UTC),
        )
        return self.run

    def complete_run(
        self,
        run_id: UUID,
        summary: dict[str, object] | None,
    ) -> RunContext:
        assert self.run is not None and run_id == self.run.run_id
        self.run = replace(self.run, status="succeeded", summary=summary or {})
        return self.run

    def fail_run(
        self,
        run_id: UUID,
        error_message: str,
        summary: dict[str, object] | None,
    ) -> RunContext:
        assert self.run is not None and run_id == self.run.run_id
        self.run = replace(self.run, status="failed", summary=summary or {})
        return self.run


class FakeConnection:
    def cursor(self) -> None:
        raise AssertionError("mocked boundary must own database behavior")

    def commit(self) -> None:
        raise AssertionError("mocked boundary must own database behavior")

    def rollback(self) -> None:
        raise AssertionError("mocked boundary must own database behavior")


def _acquired() -> AcquiredObject:
    return AcquiredObject(
        source_code=EODDATA_DAILY_SOURCE.source_code,
        object_id=OBJECT_ID,
        object_key="stonks/ohlcv/eoddata/run/raw",
        filename="raw.json",
        size_bytes=42,
        checksum_sha256="ab" * 32,
    )


def test_pipeline_passes_injected_collaborators_without_network_or_framework(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeRunRepository()
    connection = FakeConnection()
    acquired = _acquired()
    parsed = ParsedProviderOutput(sources=(EODDATA_DAILY_SOURCE,), batches=())
    events: list[str] = []

    def acquire(run_context: RunContext) -> tuple[AcquiredObject, ...]:
        assert run_context.status == "started"
        events.append("acquire")
        return (acquired,)

    def parse(objects: tuple[AcquiredObject, ...]) -> ParsedProviderOutput:
        assert objects == (acquired,)
        events.append("parse")
        return parsed

    def boundary(**values: object) -> ProviderImportResult:
        assert values["connection"] is connection
        assert values["provider_code"] == "EODDATA"
        events.append("boundary")
        objects = values["acquire"](values["run_context"])
        assert values["parse"](objects) == parsed
        return ProviderImportResult(
            provider_code="EODDATA",
            acquired_objects=objects,
        )

    monkeypatch.setattr(runner_module, "execute_import_boundary", boundary)

    result = run_provider_pipeline(
        run_service=RunService(repository),
        connection=connection,
        config=OHLCVConfig(),
        provider_code="EODDATA",
        job_name="stonks_ohlcv_eoddata_daily",
        effective_date=EFFECTIVE_DATE,
        run_type="airflow",
        runner="pytest",
        acquire=acquire,
        parse=parse,
    )

    assert events == ["boundary", "acquire", "parse"]
    assert result.run_context.status == "succeeded"
    assert result.import_result.acquired_objects == (acquired,)


def test_pipeline_failure_keeps_core_summary_stage_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeRunRepository()

    def fail_boundary(**_values: object) -> ProviderImportResult:
        raise OHLCVWorkflowError("parsing") from RuntimeError("provider detail")

    monkeypatch.setattr(runner_module, "execute_import_boundary", fail_boundary)

    with pytest.raises(OHLCVWorkflowError, match="parsing"):
        run_provider_pipeline(
            run_service=RunService(repository),
            connection=FakeConnection(),
            config=OHLCVConfig(),
            provider_code="EODDATA",
            job_name="stonks_ohlcv_eoddata_daily",
            effective_date=EFFECTIVE_DATE,
            run_type="airflow",
            runner="pytest",
            acquire=lambda _context: (_acquired(),),
            parse=lambda _objects: ParsedProviderOutput(
                sources=(EODDATA_DAILY_SOURCE,),
                batches=(),
            ),
        )

    assert repository.run is not None
    assert repository.run.status == "failed"
    assert repository.run.summary == {
        "provider_code": "EODDATA",
        "outcome": "failed",
        "failed_stage": "parsing",
    }


@pytest.mark.parametrize("invalid_field", ["connection", "acquire", "parse"])
def test_invalid_pipeline_collaborator_does_not_start_core_run(
    invalid_field: str,
) -> None:
    repository = FakeRunRepository()
    values: dict[str, object] = {
        "run_service": RunService(repository),
        "connection": FakeConnection(),
        "config": OHLCVConfig(),
        "provider_code": "EODDATA",
        "job_name": "stonks_ohlcv_eoddata_daily",
        "effective_date": EFFECTIVE_DATE,
        "run_type": "airflow",
        "runner": "pytest",
        "acquire": lambda _context: (_acquired(),),
        "parse": lambda _objects: ParsedProviderOutput(
            sources=(EODDATA_DAILY_SOURCE,),
            batches=(),
        ),
    }
    values[invalid_field] = object()

    with pytest.raises(TypeError, match=invalid_field):
        run_provider_pipeline(**values)  # type: ignore[arg-type]

    assert repository.run is None
