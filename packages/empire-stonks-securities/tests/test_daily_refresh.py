from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import empire_stonks_securities.daily_refresh as daily_refresh
from empire_stonks_securities.daily_refresh import (
    DEFAULT_DAILY_REFRESH_DAG_ID,
    DailyRefreshReportRef,
    DailyRefreshRunContext,
    DailyRefreshStageResult,
    generate_daily_refresh_summary_stage,
    verify_sec_sources_stage,
)


SOURCE_RUN_ID = UUID("00000000-0000-0000-0000-000000000123")
GENERATED_AT = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


def test_daily_refresh_context_builds_report_context():
    context = DailyRefreshRunContext(
        run_id="airflow-run-1",
        logical_date="2026-07-02T00:00:00+00:00",
        environment="airflow",
    ).for_source_run(SOURCE_RUN_ID)

    report_context = context.to_report_context(FakeReportContext)

    assert context.workflow_id == DEFAULT_DAILY_REFRESH_DAG_ID
    assert report_context.dag_id == DEFAULT_DAILY_REFRESH_DAG_ID
    assert report_context.run_id == "airflow-run-1"
    assert report_context.source_run_id == str(SOURCE_RUN_ID)
    assert report_context.logical_date == "2026-07-02T00:00:00+00:00"
    assert report_context.environment == "airflow"


def test_verify_stage_uses_explicit_source_run_context(monkeypatch):
    calls = {}
    run_service = FakeRunService()

    def fake_verify_stonks_securities_daily_sources(*, object_store, input_run_id):
        calls["verify"] = {"object_store": object_store, "input_run_id": input_run_id}
        return FakeVerifyResult(input_run_id=str(input_run_id))

    def fake_generate_verify_report(*, result, run_context, generated_at):
        calls["generate"] = {
            "result": result,
            "run_context": run_context,
            "generated_at": generated_at,
        }
        return {
            "generated_at": generated_at.isoformat(),
            "summary": {"status": "PASS"},
        }

    def fake_write_verify_report_to_object_store(**kwargs):
        calls["write"] = kwargs
        return FakeStoredObject(
            object_key="stonks/securities/runs/2026/07/02/run-reports/verify",
            filename="stonks_securities_verify_20260702T120000Z.json",
            object_id="verify-object",
        )

    monkeypatch.setattr(
        daily_refresh,
        "verify_stonks_securities_daily_sources",
        fake_verify_stonks_securities_daily_sources,
    )
    monkeypatch.setattr(daily_refresh, "generate_verify_report", fake_generate_verify_report)
    monkeypatch.setattr(
        daily_refresh,
        "write_verify_report_to_object_store",
        fake_write_verify_report_to_object_store,
    )

    result = verify_sec_sources_stage(
        object_store="object-store",
        run_service=run_service,
        source_run_id=SOURCE_RUN_ID,
        run_context=DailyRefreshRunContext(
            workflow_id="stonks_securities_sec_daily_scrape",
            run_id="scheduled-run",
            logical_date="2026-07-02",
            environment="airflow",
        ),
        generated_at=GENERATED_AT,
    )

    assert calls["verify"]["input_run_id"] == SOURCE_RUN_ID
    assert calls["generate"]["run_context"].dag_id == "stonks_securities_sec_daily_scrape"
    assert calls["generate"]["run_context"].source_run_id == str(SOURCE_RUN_ID)
    assert calls["write"]["storage_run_context"] == run_service.context
    assert calls["write"]["logical_date"] == "2026-07-02"
    assert result.to_dict() == {
        "stage": "verify",
        "source_run_id": str(SOURCE_RUN_ID),
        "input_run_id": str(SOURCE_RUN_ID),
        "summary": {"status": "PASS"},
        "object_key": "stonks/securities/runs/2026/07/02/run-reports/verify",
        "filename": "stonks_securities_verify_20260702T120000Z.json",
        "object_id": "verify-object",
    }


def test_summary_stage_passes_report_object_ids(monkeypatch):
    calls = {}
    run_service = FakeRunService()

    def fake_generate_daily_refresh_summary_report(**kwargs):
        calls["generate"] = kwargs
        return {
            "generated_at": GENERATED_AT.isoformat(),
            "summary": {"status": "WARN"},
        }

    def fake_write_daily_summary_report_to_object_store(**kwargs):
        calls["write_json"] = kwargs
        return FakeStoredObject(
            object_key="stonks/securities/runs/2026/07/02/run-reports/summary",
            filename="stonks_securities_daily_summary_20260702T120000Z.json",
            object_id="summary-object",
        )

    def fake_write_daily_summary_pdf_to_object_store(**kwargs):
        calls["write_pdf"] = kwargs
        return FakeStoredObject(
            object_key="stonks/securities/runs/2026/07/02/run-reports/summary",
            filename="stonks_securities_daily_summary_20260702T120000Z.pdf",
            object_id="summary-pdf-object",
        )

    monkeypatch.setattr(
        daily_refresh,
        "generate_daily_refresh_summary_report",
        fake_generate_daily_refresh_summary_report,
    )
    monkeypatch.setattr(
        daily_refresh,
        "write_daily_summary_report_to_object_store",
        fake_write_daily_summary_report_to_object_store,
    )
    monkeypatch.setattr(
        daily_refresh,
        "write_daily_summary_pdf_to_object_store",
        fake_write_daily_summary_pdf_to_object_store,
    )

    result = generate_daily_refresh_summary_stage(
        connection="connection",
        object_store="object-store",
        run_service=run_service,
        source_run_id=SOURCE_RUN_ID,
        run_context=DailyRefreshRunContext(
            run_id="scheduled-run",
            logical_date="2026-07-02",
            environment="airflow",
        ),
        verify_report_object_id="verify-object",
        validation_report_object_id="validation-object",
        conflict_report_object_id="conflict-object",
        generated_at=GENERATED_AT,
    )

    assert calls["generate"]["source_run_id"] == str(SOURCE_RUN_ID)
    assert calls["generate"]["verify_report_object_id"] == "verify-object"
    assert calls["generate"]["validation_report_object_id"] == "validation-object"
    assert calls["generate"]["conflict_report_object_id"] == "conflict-object"
    assert calls["generate"]["run_context"].source_run_id == str(SOURCE_RUN_ID)
    assert calls["write_json"]["storage_run_context"] == run_service.context
    assert calls["write_pdf"]["storage_run_context"] == run_service.context
    assert result.to_dict()["object_id"] == "summary-object"
    assert result.to_dict()["pdf_object_id"] == "summary-pdf-object"


def test_stage_result_serializes_report_refs():
    result = DailyRefreshStageResult(
        stage="validation",
        source_run_id=str(SOURCE_RUN_ID),
        payload={"summary": {"status": "PASS"}},
        report=DailyRefreshReportRef(
            object_key="reports/validation",
            filename="validation.json",
            object_id="validation-object",
        ),
    )

    assert result.to_dict() == {
        "stage": "validation",
        "source_run_id": str(SOURCE_RUN_ID),
        "summary": {"status": "PASS"},
        "object_key": "reports/validation",
        "filename": "validation.json",
        "object_id": "validation-object",
    }


@dataclass(frozen=True)
class FakeReportContext:
    dag_id: str | None = None
    run_id: str | None = None
    source_run_id: str | None = None
    logical_date: str | None = None
    environment: str | None = None


@dataclass(frozen=True)
class FakeVerifyResult:
    input_run_id: str

    def to_dict(self):
        return {"input_run_id": self.input_run_id}


@dataclass(frozen=True)
class FakeStoredObject:
    object_key: str
    filename: str
    object_id: str


class FakeRunService:
    def __init__(self):
        self.context = SimpleNamespace(run_id=SOURCE_RUN_ID)

    def get_run_context(self, source_run_id):
        assert source_run_id == SOURCE_RUN_ID
        return self.context
