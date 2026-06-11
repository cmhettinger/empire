from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from empire_core import RunService
from empire_core.run_context.models import RunContext
from empire_stonks_securities.acquisition import SecDownloadResult
from empire_stonks_securities.config import StonksSecuritiesConfig
from empire_stonks_securities.runner import run_stonks_securities_daily_to_object_store

from test_config import CONFIG


def test_daily_runner_uses_run_id_for_acquisition_folder():
    config = StonksSecuritiesConfig.from_mapping(CONFIG)
    run_repo = FakeRunRepository()
    run_service = RunService(run_repo)
    downloader = FakeDownloader()

    result = run_stonks_securities_daily_to_object_store(
        config=config,
        downloader=downloader,
        run_service=run_service,
        object_store=object(),
        run_type="airflow",
        runner="airflow",
        runner_ref={"dag_id": "stonks_securities_daily_scrape"},
        source_keys=("sec_company_tickers",),
        effective_date=date(2026, 6, 11),
        storage_key_prefix="stonks/securities",
    )

    assert result.run_context.status == "started"
    assert result.run_context.job_name == "stonks_securities_daily_scrape"
    assert run_repo.completed[0]["run_id"] == result.run_context.run_id
    assert run_repo.completed[0]["summary"] == {
        "downloaded_count": 1,
        "skipped_count": 0,
        "source_count": 1,
    }
    assert downloader.calls[0]["run_context"].run_id == result.run_context.run_id
    assert downloader.calls[0]["target"].object_key == (
        f"stonks/securities/runs/2026/06/11/{result.run_context.run_id}/sec_company_tickers"
    )


class FakeDownloader:
    def __init__(self) -> None:
        self.calls = []

    def download_target(self, **kwargs):
        self.calls.append(kwargs)
        target = kwargs["target"]
        return SecDownloadResult(
            source_code=target.source_code,
            source_url=target.source_url,
            object_key=target.object_key,
            filename=target.filename,
            metadata_filename=target.metadata_filename,
            status="downloaded",
            object_id=str(uuid4()),
            metadata_object_id=str(uuid4()),
        )


class FakeRunRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, RunContext] = {}
        self.completed = []
        self.failed = []

    def start_run(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None,
        effective_date: date | None,
        run_type: str,
        runner: str,
        runner_ref: dict,
        params: dict,
        heartbeat_timeout_seconds: int | None,
    ) -> RunContext:
        now = datetime.now(UTC)
        ctx = RunContext(
            run_id=uuid4(),
            domain=domain,
            job_name=job_name,
            subject_key=subject_key,
            effective_date=effective_date,
            run_type=run_type,
            status="started",
            runner=runner,
            params=params,
            summary={},
            started_at=now,
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
            last_heartbeat_at=now if heartbeat_timeout_seconds else None,
            stale_after=(
                now + timedelta(seconds=heartbeat_timeout_seconds)
                if heartbeat_timeout_seconds
                else None
            ),
        )
        self.runs[ctx.run_id] = ctx
        return ctx

    def complete_run(self, run_id: UUID, summary: dict | None) -> RunContext:
        self.completed.append({"run_id": run_id, "summary": summary})
        return replace(
            self.runs[run_id],
            status="succeeded",
            completed_at=datetime.now(UTC),
            summary=summary or {},
        )

    def fail_run(self, run_id: UUID, error_message: str, summary: dict | None) -> RunContext:
        self.failed.append({"run_id": run_id, "error_message": error_message, "summary": summary})
        return replace(
            self.runs[run_id],
            status="failed",
            completed_at=datetime.now(UTC),
            summary=summary or {},
        )

    def heartbeat(self, run_id: UUID) -> RunContext:
        return self.runs[run_id]

    def get_run_context(self, run_id: UUID) -> RunContext | None:
        return self.runs.get(run_id)

    def find_latest_successful_run(self, **kwargs):
        return None

    def find_successful_runs(self, **kwargs):
        return []
