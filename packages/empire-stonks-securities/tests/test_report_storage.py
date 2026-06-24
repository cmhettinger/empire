from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from empire_core import ObjectStore
from empire_stonks_securities.conflicts import write_conflict_report_to_object_store
from empire_stonks_securities.daily_summary import write_daily_summary_report_to_object_store
from empire_stonks_securities.validation import write_validation_report_to_object_store
from empire_stonks_securities.verification import write_verify_report_to_object_store

from test_parsing import FakeObjectRepository, FakeRunContext


GENERATED_AT = datetime(2026, 6, 21, 13, 22, tzinfo=UTC)


def test_report_writers_store_run_scoped_objects_when_run_context_is_provided(tmp_path):
    object_store = ObjectStore(FakeObjectRepository(tmp_path))
    run_id = uuid4()
    storage_run_context = FakeRunContext(run_id)

    for writer, report_name, expected_kind in (
        (
            write_verify_report_to_object_store,
            "stonks_securities_verify",
            "stonks_securities_verify_report",
        ),
        (
            write_validation_report_to_object_store,
            "stonks_securities_validation",
            "stonks_securities_validation_report",
        ),
        (
            write_conflict_report_to_object_store,
            "stonks_securities_conflicts",
            "stonks_securities_conflict_report",
        ),
        (
            write_daily_summary_report_to_object_store,
            "stonks_securities_daily_summary",
            "stonks_securities_daily_summary_report",
        ),
    ):
        stored = writer(
            report=_report(report_name),
            object_store=object_store,
            generated_at=GENERATED_AT,
            storage_run_context=storage_run_context,
        )

        assert stored.object_scope == "run"
        assert stored.run_id == run_id
        assert stored.object_kind == expected_kind
        assert stored.metadata["report_name"] == report_name


def test_report_writers_default_to_manual_scope_without_run_context(tmp_path):
    object_store = ObjectStore(FakeObjectRepository(tmp_path))

    for writer, report_name in (
        (write_verify_report_to_object_store, "stonks_securities_verify"),
        (write_validation_report_to_object_store, "stonks_securities_validation"),
        (write_conflict_report_to_object_store, "stonks_securities_conflicts"),
        (write_daily_summary_report_to_object_store, "stonks_securities_daily_summary"),
    ):
        stored = writer(
            report=_report(report_name),
            object_store=object_store,
            generated_at=GENERATED_AT,
        )

        assert stored.object_scope == "manual"
        assert stored.run_id is None


def _report(report_name: str) -> dict:
    return {
        "report_name": report_name,
        "generated_at": GENERATED_AT.isoformat(),
        "run_context": {"logical_date": GENERATED_AT.isoformat()},
        "status": "PASS",
        "healthy": True,
        "summary": {"status": "PASS"},
    }
