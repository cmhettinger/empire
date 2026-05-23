from __future__ import annotations

from datetime import date, timedelta

from empire_core import RunService

from tests.fakes import InMemoryRunRepository


def test_start_complete_and_fail_run():
    repo = InMemoryRunRepository()
    service = RunService(repo)

    ctx = service.start_run(
        domain="weather",
        job_name="weather_refresh",
        subject_key="ashburn-va",
        effective_date=date(2026, 5, 23),
        run_type="airflow",
        runner="airflow",
        params={"source": "openweather"},
    )

    assert ctx.status == "started"
    assert ctx.params == {"source": "openweather"}

    completed = service.complete_run(ctx.run_id, summary={"stored_object_count": 1})
    assert completed.status == "succeeded"
    assert completed.completed_at is not None
    assert completed.summary == {"stored_object_count": 1}

    failed_ctx = service.start_run(
        domain="weather",
        job_name="weather_refresh",
        run_type="cli",
        runner="cli",
    )
    failed = service.fail_run(failed_ctx.run_id, "provider unavailable")
    assert failed.status == "failed"
    assert failed.completed_at is not None


def test_heartbeat_extends_stale_after():
    repo = InMemoryRunRepository()
    service = RunService(repo)

    ctx = service.start_run(
        domain="weather",
        job_name="weather_refresh",
        run_type="airflow",
        runner="airflow",
        heartbeat_timeout_seconds=1800,
    )
    original_stale_after = ctx.stale_after
    repo.runs[ctx.run_id] = repo.runs[ctx.run_id].__class__(
        **{
            **repo.runs[ctx.run_id].__dict__,
            "stale_after": original_stale_after - timedelta(minutes=10),
        }
    )

    heartbeat = service.heartbeat(ctx.run_id)

    assert heartbeat.last_heartbeat_at is not None
    assert heartbeat.stale_after is not None
    assert heartbeat.stale_after > original_stale_after - timedelta(minutes=10)


def test_latest_successful_run_selection():
    repo = InMemoryRunRepository()
    service = RunService(repo)

    older = service.start_run(
        domain="weather",
        job_name="weather_refresh",
        subject_key="ashburn-va",
        effective_date=date(2026, 5, 23),
        run_type="airflow",
        runner="airflow",
    )
    service.complete_run(older.run_id)

    newer = service.start_run(
        domain="weather",
        job_name="weather_refresh",
        subject_key="ashburn-va",
        effective_date=date(2026, 5, 23),
        run_type="airflow",
        runner="airflow",
    )
    service.complete_run(newer.run_id)

    latest = service.find_latest_successful_run(
        domain="weather",
        job_name="weather_refresh",
        subject_key="ashburn-va",
        effective_date=date(2026, 5, 23),
    )

    assert latest is not None
    assert latest.run_id == newer.run_id

    runs = service.find_successful_runs(
        domain="weather",
        job_name="weather_refresh",
        subject_key="ashburn-va",
    )
    assert [run.run_id for run in runs] == [newer.run_id, older.run_id]
