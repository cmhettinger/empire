from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from empire_stonks_securities.conflicts import write_conflict_report_to_object_store
from empire_stonks_securities.daily_summary import write_daily_summary_report_to_object_store
from empire_stonks_securities.report_paths import run_report_object_key, run_report_path
from empire_stonks_securities.validation import write_validation_report_to_object_store


def test_run_report_object_key_uses_logical_date_and_report_type():
    key = run_report_object_key(
        storage_key="stonks/securities",
        report_type="verify",
        logical_date=datetime(2026, 6, 21, 13, 22, tzinfo=UTC),
    )

    assert key == "stonks/securities/runs/2026/06/21/run-reports/verify"


def test_run_report_path_matches_run_report_layout(tmp_path):
    path = run_report_path(
        root=tmp_path,
        report_type="conflicts",
        filename="report.json",
        logical_date="2026-06-21 13:22:05.122401+00:00",
    )

    assert path == (
        tmp_path
        / "stonks"
        / "securities"
        / "runs"
        / "2026"
        / "06"
        / "21"
        / "run-reports"
        / "conflicts"
        / "report.json"
    )


def test_existing_daily_report_writers_use_run_report_layout():
    generated_at = datetime(2026, 6, 21, 13, 22, tzinfo=UTC)
    report = {
        "generated_at": generated_at.isoformat(),
        "run_context": {"logical_date": generated_at.isoformat()},
    }

    validation_store = FakeObjectStore()
    conflict_store = FakeObjectStore()
    summary_store = FakeObjectStore()

    write_validation_report_to_object_store(
        report=report,
        object_store=validation_store,
        generated_at=generated_at,
    )
    write_conflict_report_to_object_store(
        report=report,
        object_store=conflict_store,
        generated_at=generated_at,
    )
    write_daily_summary_report_to_object_store(
        report=report,
        object_store=summary_store,
        generated_at=generated_at,
    )

    assert validation_store.calls[0]["object_key"] == (
        "stonks/securities/runs/2026/06/21/run-reports/validation"
    )
    assert conflict_store.calls[0]["object_key"] == (
        "stonks/securities/runs/2026/06/21/run-reports/conflicts"
    )
    assert summary_store.calls[0]["object_key"] == (
        "stonks/securities/runs/2026/06/21/run-reports/summary"
    )


class FakeObjectStore:
    def __init__(self) -> None:
        self.calls = []

    def put_bytes(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            object_key=kwargs["object_key"],
            filename=kwargs["filename"],
            object_kind=kwargs["object_kind"],
        )
