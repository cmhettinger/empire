from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
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

    for writer, report_type, report_name, expected_kind in (
        (
            write_verify_report_to_object_store,
            "verify",
            "stonks_securities_verify",
            "stonks_securities_verify_report",
        ),
        (
            write_validation_report_to_object_store,
            "validation",
            "stonks_securities_validation",
            "stonks_securities_validation_report",
        ),
        (
            write_conflict_report_to_object_store,
            "conflicts",
            "stonks_securities_conflicts",
            "stonks_securities_conflict_report",
        ),
        (
            write_daily_summary_report_to_object_store,
            "summary",
            "stonks_securities_daily_summary",
            "stonks_securities_daily_summary_report",
        ),
    ):
        report = _report(report_name)
        stored = writer(
            report=report,
            object_store=object_store,
            generated_at=GENERATED_AT,
            storage_run_context=storage_run_context,
        )

        expected_object_key = f"stonks/securities/runs/2026/06/21/run-reports/{report_type}"
        expected_filename = f"{report_name}_20260621T132200Z.json"
        stored_path = Path(stored.base_uri) / stored.object_key / stored.filename

        assert stored.object_key == expected_object_key
        assert stored.filename == expected_filename
        assert stored_path.is_file()
        assert json.loads(stored_path.read_text(encoding="utf-8")) == report
        assert stored.object_scope == "run"
        assert stored.run_id == run_id
        assert stored.object_kind == expected_kind
        assert stored.metadata == {
            "report_name": report_name,
            "generated_at": GENERATED_AT.isoformat(),
        }


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
