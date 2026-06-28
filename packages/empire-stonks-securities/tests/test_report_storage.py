from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from empire_core import ObjectStore
from empire_stonks_securities.conflicts import write_conflict_report_to_object_store
from empire_stonks_securities.daily_summary import (
    DAILY_SUMMARY_PDF_RETENTION_DAYS,
    write_daily_summary_pdf_to_object_store,
    write_daily_summary_report_to_object_store,
)
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


def test_daily_summary_pdf_writer_stores_distinct_expiring_pdf(tmp_path):
    object_store = ObjectStore(FakeObjectRepository(tmp_path))
    run_id = uuid4()
    storage_run_context = FakeRunContext(run_id)

    stored = write_daily_summary_pdf_to_object_store(
        report=_pdf_report(),
        object_store=object_store,
        generated_at=GENERATED_AT,
        storage_run_context=storage_run_context,
        output_dir=tmp_path / "render",
    )

    stored_path = Path(stored.base_uri) / stored.object_key / stored.filename

    assert stored.object_key == "stonks/securities/runs/2026/06/21/run-reports/summary"
    assert stored.filename == "stonks_securities_daily_summary_20260621T132200Z.pdf"
    assert stored_path.is_file()
    assert stored_path.stat().st_size > 1000
    assert stored.object_scope == "run"
    assert stored.run_id == run_id
    assert stored.content_type == "application/pdf"
    assert stored.logical_name == "stonks_securities_daily_summary_pdf"
    assert stored.object_kind == "stonks_securities_daily_summary_pdf"
    assert stored.expires_at == timedelta(days=DAILY_SUMMARY_PDF_RETENTION_DAYS) + GENERATED_AT
    assert stored.metadata == {
        "report_name": "stonks_securities_daily_summary",
        "report_id": "stonks.securities.daily-refresh-summary",
        "generated_at": GENERATED_AT.isoformat(),
        "retention_days": DAILY_SUMMARY_PDF_RETENTION_DAYS,
    }


def _report(report_name: str) -> dict:
    return {
        "report_name": report_name,
        "generated_at": GENERATED_AT.isoformat(),
        "run_context": {"logical_date": GENERATED_AT.isoformat()},
        "status": "PASS",
        "healthy": True,
        "summary": {"status": "PASS"},
    }


def _pdf_report() -> dict:
    report = _report("stonks_securities_daily_summary")
    report["summary"] = {
        "status": "PASS",
        "warnings_total": 0,
        "failures_total": 0,
        "inputs_seen": 2,
        "inputs_missing": 0,
        "inputs_unchanged": 0,
        "observations_created": 100,
        "issuers_created": 25,
        "issuers_updated": 1,
        "securities_created": 40,
        "securities_updated": 2,
        "listings_created": 35,
        "listings_updated": 3,
        "validation_status": "PASS",
        "conflict_status": "PASS",
        "verify_status": "PASS",
        "canonical_issuers_total": 25,
        "canonical_securities_total": 40,
        "canonical_listings_total": 35,
        "canonical_markets_represented": 2,
    }
    report["warnings"] = []
    report["failures"] = []
    report["market_snapshot"] = {
        "markets": [
            {
                "exchange_code": "XNAS",
                "exchange_name": "NASDAQ",
                "market_count": 1,
                "issuers_total": 20,
                "securities_total": 30,
                "listings_total": 25,
            },
            {
                "exchange_code": "OTHER",
                "exchange_name": "Other represented markets",
                "market_count": 2,
                "issuers_total": 5,
                "securities_total": 10,
                "listings_total": 10,
            },
        ],
    }
    return report
