from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from empire_stonks_securities.daily_summary import (
    DailySummaryRunContext,
    build_snapshot_diff,
    daily_summary_report_to_json,
    evaluate_daily_summary_status,
    evaluate_input_freshness,
    generate_daily_refresh_summary_report,
    write_daily_summary_report_to_console,
    write_daily_summary_report_to_file,
)


GENERATED_AT = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


def test_daily_summary_report_json_shape_is_stable():
    conn = FakeConnection()
    report = generate_daily_refresh_summary_report(
        connection=conn,
        object_store=FakeObjectStore(),
        run_context=DailySummaryRunContext(dag_id="test_dag", run_id="test_run"),
        source_run_id="run-123",
        generated_at=GENERATED_AT,
    )

    assert list(report.keys()) == [
        "report_name",
        "generated_at",
        "run_context",
        "summary",
        "input_freshness",
        "snapshot_diff",
        "pipeline_stage_health",
        "daily_entity_deltas",
        "safety_guards",
        "validation_report",
        "conflict_report",
        "warnings",
        "failures",
    ]
    assert report["report_name"] == "stonks_securities_daily_summary"
    assert report["run_context"]["dag_id"] == "test_dag"
    assert report["summary"]["inputs_seen"] == 2
    assert report["summary"]["inputs_missing"] == 0
    assert report["summary"]["inputs_unchanged"] == 1
    assert report["summary"]["validation_status"] == "PASS"
    assert report["summary"]["conflict_status"] == "WARN"
    assert report["safety_guards"]["listings_closed_by_daily_refresh"] == 0


def test_freshness_pass_warn_fail_and_missing_source():
    current_sources = {
        "sec_company_tickers_exchange": _source_row(
            "sec_company_tickers_exchange",
            downloaded_at=GENERATED_AT - timedelta(hours=1),
        ),
        "sec_company_tickers": _source_row(
            "sec_company_tickers",
            downloaded_at=GENERATED_AT - timedelta(hours=48),
        ),
    }

    freshness = evaluate_input_freshness(
        current_sources=current_sources,
        generated_at=GENERATED_AT,
        stale_warn_hours=36,
        stale_fail_hours=96,
    )
    assert freshness["sources"]["sec_company_tickers_exchange"]["status"] == "PASS"
    assert freshness["sources"]["sec_company_tickers"]["status"] == "WARN"

    fail_freshness = evaluate_input_freshness(
        current_sources={
            "sec_company_tickers_exchange": _source_row(
                "sec_company_tickers_exchange",
                downloaded_at=GENERATED_AT - timedelta(hours=120),
            )
        },
        generated_at=GENERATED_AT,
        stale_warn_hours=36,
        stale_fail_hours=96,
    )
    assert fail_freshness["sources"]["sec_company_tickers_exchange"]["status"] == "FAIL"
    assert fail_freshness["sources"]["sec_company_tickers"]["present"] is False


def test_unchanged_source_is_snapshot_info_not_failure():
    current = {"sec_company_tickers": _source_row("sec_company_tickers", sha256="same")}
    previous = {"sec_company_tickers": _source_row("sec_company_tickers", sha256="same")}

    diff = build_snapshot_diff(current_sources=current, previous_sources=previous)

    assert diff["inputs_unchanged"] == 1
    assert diff["sources"]["sec_company_tickers"]["unchanged"] is True
    assert evaluate_daily_summary_status(warnings=[], failures=[]) == "PASS"


def test_missing_required_source_fails_report():
    conn = FakeConnection()
    conn.results["daily_summary_current_source_files"] = [
        _source_row("sec_company_tickers_exchange")
    ]

    report = generate_daily_refresh_summary_report(
        connection=conn,
        object_store=FakeObjectStore(),
        generated_at=GENERATED_AT,
    )

    assert report["summary"]["status"] == "FAIL"
    missing_failure = next(
        failure for failure in report["failures"] if failure["code"] == "required_source_missing"
    )
    assert missing_failure["source_code"] == "sec_company_tickers"
    assert "was not found" in missing_failure["message"]


def test_validation_and_conflict_report_summary_linking():
    report = generate_daily_refresh_summary_report(
        connection=FakeConnection(),
        object_store=FakeObjectStore(),
        generated_at=GENERATED_AT,
    )

    assert report["validation_report"]["path"] == (
        "stonks/securities/validation/2026/06/19/"
        "stonks_securities_validation_20260619T120000Z.json"
    )
    assert report["validation_report"]["status"] == "PASS"
    assert report["conflict_report"]["status"] == "WARN"
    assert report["conflict_report"]["conflicts_total"] == 34
    conflict_warning = next(
        warning for warning in report["warnings"] if warning["code"] == "conflict_report_warn"
    )
    verify_warning = next(
        warning for warning in report["warnings"] if warning["code"] == "stage_health_unknown"
    )
    assert conflict_warning["path"] == report["conflict_report"]["path"]
    assert conflict_warning["conflicts_total"] == 34
    assert "completed with WARN status" in conflict_warning["message"]
    assert verify_warning["stage"] == "verify"
    assert "No durable verify report" in verify_warning["message"]


def test_json_and_console_output(tmp_path, capsys):
    report = generate_daily_refresh_summary_report(
        connection=FakeConnection(),
        object_store=FakeObjectStore(),
        generated_at=GENERATED_AT,
    )
    output_path = tmp_path / "daily-summary.json"

    write_daily_summary_report_to_console(report)
    write_daily_summary_report_to_file(report, output_path)
    rendered = daily_summary_report_to_json(report)

    assert "stonks_securities_daily_summary status=" in capsys.readouterr().out
    assert json.loads(output_path.read_text(encoding="utf-8"))["report_name"] == (
        "stonks_securities_daily_summary"
    )
    assert json.loads(rendered)["generated_at"] == "2026-06-19T12:00:00+00:00"


class FakeObjectStore:
    def get_bytes(self, object_id):
        object_id_text = str(object_id)
        if object_id_text == "00000000-0000-0000-0000-000000000001":
            return json.dumps(
                {
                    "summary": {
                        "status": "SUCCESS",
                        "warnings_total": 0,
                        "failures_total": 0,
                    }
                }
            ).encode("utf-8")
        if object_id_text == "00000000-0000-0000-0000-000000000002":
            return json.dumps(
                {
                    "summary": {
                        "status": "WARN",
                        "warnings_total": 33,
                        "failures_total": 0,
                        "conflicts_total": 34,
                    }
                }
            ).encode("utf-8")
        raise KeyError(object_id_text)


class FakeConnection:
    def __init__(self) -> None:
        self.results = dict(DEFAULT_RESULTS)
        self.sql_by_metric = {}

    def cursor(self):
        return FakeCursor(self)


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql: str, params=()) -> None:
        marker = "/* metric: "
        start = sql.index(marker) + len(marker)
        end = sql.index(" */", start)
        metric = sql[start:end]
        self.connection.sql_by_metric[metric] = sql
        self.result = self.connection.results[metric]

    def fetchone(self):
        if isinstance(self.result, list):
            return self.result[0] if self.result else None
        return (self.result,)

    def fetchall(self):
        return self.result if isinstance(self.result, list) else [(self.result,)]


def _source_row(
    source_code: str,
    *,
    sha256: str | None = None,
    downloaded_at: datetime | None = None,
) -> dict:
    suffix = "1" if source_code == "sec_company_tickers_exchange" else "2"
    return {
        "source_code": source_code,
        "object_id": f"00000000-0000-0000-0000-0000000000{suffix}0",
        "object_key": f"stonks/securities/runs/2026/06/19/run-123/{source_code}",
        "filename": f"{source_code}.json",
        "size_bytes": 100,
        "sha256": sha256 or f"sha-{source_code}",
        "etag": '"test"',
        "last_modified": "Fri, 19 Jun 2026 00:00:00 GMT",
        "downloaded_at": (downloaded_at or GENERATED_AT - timedelta(hours=1)).isoformat(),
        "created_at": downloaded_at or GENERATED_AT - timedelta(hours=1),
    }


DEFAULT_RESULTS = {
    "daily_summary_current_source_files": [
        _source_row("sec_company_tickers_exchange", sha256="same"),
        _source_row("sec_company_tickers", sha256="new"),
    ],
    "daily_summary_previous_source_files": [
        _source_row("sec_company_tickers_exchange", sha256="same"),
        _source_row("sec_company_tickers", sha256="old"),
    ],
    "daily_summary_latest_stonks_securities_validation_report": [
        {
            "object_id": "00000000-0000-0000-0000-000000000001",
            "object_key": "stonks/securities/validation/2026/06/19",
            "filename": "stonks_securities_validation_20260619T120000Z.json",
            "object_kind": "stonks_securities_validation_report",
            "report_generated_at": GENERATED_AT.isoformat(),
            "created_at": GENERATED_AT,
        }
    ],
    "daily_summary_latest_stonks_securities_conflict_report": [
        {
            "object_id": "00000000-0000-0000-0000-000000000002",
            "object_key": "stonks/securities/conflicts/2026/06/19",
            "filename": "stonks_securities_conflicts_20260619T120000Z.json",
            "object_kind": "stonks_securities_conflict_report",
            "report_generated_at": GENERATED_AT.isoformat(),
            "created_at": GENERATED_AT,
        }
    ],
    "daily_summary_observations_created": 20831,
    "daily_summary_issuer_id_evidence_inserted": 20831,
    "daily_summary_security_id_evidence_inserted": 20831,
    "daily_summary_listing_id_evidence_inserted": 10170,
    "daily_summary_issuer_created": 8026,
    "daily_summary_issuer_updated": 0,
    "daily_summary_security_created": 10453,
    "daily_summary_security_updated": 0,
    "daily_summary_listing_created": 10170,
    "daily_summary_listing_updated": 0,
}
