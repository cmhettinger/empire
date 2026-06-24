from __future__ import annotations

import json
from datetime import UTC, datetime

from empire_stonks_securities.validation import (
    ValidationRunContext,
    evaluate_validation_status,
    generate_phase_2a_validation_report,
    validation_report_to_json,
    write_validation_report_to_console,
    write_validation_report_to_file,
)


GENERATED_AT = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


def test_validation_report_json_shape_is_stable():
    report = generate_phase_2a_validation_report(
        connection=FakeConnection(),
        run_context=ValidationRunContext(dag_id="test_dag", run_id="test_run"),
        generated_at=GENERATED_AT,
    )

    assert list(report.keys()) == [
        "report_name",
        "generated_at",
        "status",
        "healthy",
        "run_context",
        "summary",
        "source_coverage",
        "entity_counts",
        "evidence_coverage",
        "listing_quality",
        "exchange_quality",
        "duplicates",
        "orphans",
        "conflict_candidates",
        "warnings",
        "failures",
    ]
    assert report["report_name"] == "stonks_securities_validation"
    assert report["status"] == report["summary"]["status"]
    assert report["healthy"] is True
    assert report["run_context"]["dag_id"] == "test_dag"
    assert report["summary"]["observations_total"] == 20831
    assert report["summary"]["issuers_total"] == 8026
    assert report["summary"]["securities_total"] == 10453
    assert report["summary"]["listings_total"] == 10170


def test_validation_report_scopes_source_run_by_current_source_files():
    conn = FakeConnection()
    conn.results["observations_by_object_key"] = [
        {
            "provider_code": "SEC_COMPANY_TICKERS_EXCHANGE",
            "object_key": "stonks/securities/runs/2026/06/19/run-123/sec_company_tickers_exchange",
            "observation_count": 10416,
        }
    ]

    report = generate_phase_2a_validation_report(
        connection=conn,
        run_context=ValidationRunContext(source_run_id="run-123"),
        generated_at=GENERATED_AT,
    )

    assert report["source_coverage"]["source_files_for_run"] == [
        {
            "provider_code": "SEC_COMPANY_TICKERS_EXCHANGE",
            "object_key": "stonks/securities/runs/2026/06/19/run-123/sec_company_tickers_exchange",
            "source_object_id": "source-object-1",
            "filename": "company_tickers_exchange.json",
            "sha256": "abc123",
            "size_bytes": 100,
            "created_at": GENERATED_AT,
        }
    ]
    assert report["source_coverage"]["observations_by_object_key"] == [
        {
            "provider_code": "SEC_COMPANY_TICKERS_EXCHANGE",
            "object_key": "stonks/securities/runs/2026/06/19/run-123/sec_company_tickers_exchange",
            "observation_count": 10416,
        }
    ]
    observations_sql = conn.sql_by_metric["observations_by_object_key"]
    listings_sql = conn.sql_by_metric["active_listings_total"]
    assert "core.stored_object so" in observations_sql
    assert "so.run_id = %s" in observations_sql
    assert "stonks.provider_source_snapshot_object psso" in observations_sql
    assert "psso.source_snapshot_id = po.source_snapshot_id" in observations_sql
    assert "so.checksum_sha256 = po.summary_json #>> '{source_file,sha256}'" in observations_sql
    assert "stonks.provider_source_snapshot_object psso_scope" in listings_sql
    assert "psso_scope.source_snapshot_id = po_scope.source_snapshot_id" in listings_sql
    assert "so_scope.checksum_sha256 = po_scope.summary_json #>> '{source_file,sha256}'" in listings_sql


def test_status_evaluation_pass_warn_or_fail():
    assert evaluate_validation_status(warnings=[], failures=[]) == "PASS"
    assert evaluate_validation_status(warnings=[{"code": "warn", "count": 1}], failures=[]) == "WARN"
    assert evaluate_validation_status(warnings=[], failures=[{"code": "fail", "count": 1}]) == "FAIL"


def test_validation_report_warns_for_missing_or_unmapped_exchange_not_eligible_listing_gap():
    report = generate_phase_2a_validation_report(
        connection=FakeConnection(),
        generated_at=GENERATED_AT,
    )

    assert report["summary"]["status"] == "WARN"
    assert report["healthy"] is True
    warning_codes = {warning["code"] for warning in report["warnings"]}
    assert "ticker_exchange_observations_missing_exchange" in warning_codes
    assert "ticker_exchange_observations_eligible_missing_listing_evidence" not in warning_codes
    assert "raw_sec_exchange_values_unmapped" in warning_codes
    assert (
        report["evidence_coverage"]["ticker_exchange_observations_missing_listing_evidence"]
        == 246
    )
    assert (
        report["evidence_coverage"][
            "ticker_exchange_observations_missing_listing_evidence_due_to_missing_exchange"
        ]
        == 219
    )
    assert (
        report["evidence_coverage"][
            "ticker_exchange_observations_missing_listing_evidence_due_to_unmapped_exchange"
        ]
        == 27
    )
    assert (
        report["evidence_coverage"]["ticker_exchange_observations_eligible_missing_listing_evidence"]
        == 0
    )
    assert report["failures"] == []


def test_validation_report_warns_for_eligible_listing_evidence_gap():
    conn = FakeConnection()
    conn.results["ticker_exchange_observations_eligible_missing_listing_evidence"] = 5

    report = generate_phase_2a_validation_report(
        connection=conn,
        generated_at=GENERATED_AT,
    )

    warning_codes = {warning["code"] for warning in report["warnings"]}
    assert "ticker_exchange_observations_eligible_missing_listing_evidence" in warning_codes


def test_validation_report_fails_for_duplicate_cik_and_ticker_exchange_conflict():
    conn = FakeConnection()
    conn.results["duplicate_cik_issuers"] = [{"cik": "0000000001", "issuer_count": 2}]
    conn.results["same_exchange_ticker_multi_security"] = [
        {"exchange_id": "exchange-1", "ticker_norm": "ABC", "security_count": 2}
    ]

    report = generate_phase_2a_validation_report(connection=conn, generated_at=GENERATED_AT)

    assert report["summary"]["status"] == "FAIL"
    assert report["healthy"] is False
    failure_codes = {failure["code"] for failure in report["failures"]}
    assert "duplicate_cik_issuers" in failure_codes
    assert "same_exchange_ticker_multiple_securities" in failure_codes


def test_validation_report_fails_for_duplicate_active_security_exchange_listings():
    conn = FakeConnection()
    conn.results["same_security_exchange_active_listing"] = [
        {"security_id": "security-1", "exchange_id": "exchange-1", "listing_count": 2}
    ]

    report = generate_phase_2a_validation_report(connection=conn, generated_at=GENERATED_AT)

    assert report["summary"]["status"] == "FAIL"
    failure_codes = {failure["code"] for failure in report["failures"]}
    assert "same_security_exchange_multiple_active_listings" in failure_codes


def test_validation_report_fails_for_duplicate_active_listing_symbols():
    conn = FakeConnection()
    conn.results["same_listing_multiple_active_symbols"] = [
        {"listing_id": "listing-1", "active_symbol_count": 2}
    ]

    report = generate_phase_2a_validation_report(connection=conn, generated_at=GENERATED_AT)

    assert report["summary"]["status"] == "FAIL"
    failure_codes = {failure["code"] for failure in report["failures"]}
    assert "same_listing_multiple_active_symbols" in failure_codes


def test_validation_report_to_json_is_pretty_and_deterministic():
    report = generate_phase_2a_validation_report(
        connection=FakeConnection(),
        generated_at=GENERATED_AT,
    )

    rendered = validation_report_to_json(report)

    assert rendered.endswith("\n")
    assert json.loads(rendered)["generated_at"] == "2026-06-19T12:00:00+00:00"
    assert "\n  \"summary\": {" in rendered


def test_console_and_file_output(tmp_path, capsys):
    report = generate_phase_2a_validation_report(
        connection=FakeConnection(),
        generated_at=GENERATED_AT,
    )
    output_path = tmp_path / "validation.json"

    write_validation_report_to_console(report)
    write_validation_report_to_file(report, output_path)

    assert json.loads(capsys.readouterr().out)["report_name"] == "stonks_securities_validation"
    assert json.loads(output_path.read_text(encoding="utf-8"))["summary"]["listings_total"] == 10170


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


DEFAULT_RESULTS = {
    "observations_by_source": [
        {"provider_code": "SEC_COMPANY_TICKERS", "observation_count": 10415},
        {"provider_code": "SEC_COMPANY_TICKERS_EXCHANGE", "observation_count": 10416},
    ],
    "observations_by_object_key": [
        {
            "provider_code": "SEC_COMPANY_TICKERS_EXCHANGE",
            "object_key": "stonks/securities/test",
            "observation_count": 10416,
        }
    ],
    "source_files_for_run": [
        {
            "provider_code": "SEC_COMPANY_TICKERS_EXCHANGE",
            "object_key": "stonks/securities/runs/2026/06/19/run-123/sec_company_tickers_exchange",
            "source_object_id": "source-object-1",
            "filename": "company_tickers_exchange.json",
            "sha256": "abc123",
            "size_bytes": 100,
            "created_at": GENERATED_AT,
        }
    ],
    "observations_total": 20831,
    "observations_missing_cik": 0,
    "observations_missing_ticker": 0,
    "ticker_exchange_observations_missing_exchange": 219,
    "observations_with_empty_summary_json": 0,
    "issuers_total": 8026,
    "issuers_with_cik": 8026,
    "issuers_from_sec_evidence": 8026,
    "securities_total": 10453,
    "securities_from_sec_evidence": 10453,
    "listings_total": 10170,
    "listings_from_sec_evidence": 10170,
    "evidence_rows_by_target_type": [
        {"target_type": "issuer", "evidence_count": 20831},
        {"target_type": "listing", "evidence_count": 10170},
        {"target_type": "security", "evidence_count": 20831},
    ],
    "observations_with_issuer_evidence": 20831,
    "observations_with_security_evidence": 20831,
    "observations_with_listing_evidence": 10170,
    "observations_with_cik_missing_issuer_evidence": 0,
    "observations_with_ticker_cik_missing_security_evidence": 0,
    "ticker_exchange_observations_missing_listing_evidence": 246,
    "ticker_exchange_observations_missing_listing_evidence_due_to_missing_exchange": 219,
    "ticker_exchange_observations_missing_listing_evidence_due_to_unmapped_exchange": 27,
    "ticker_exchange_observations_eligible_missing_listing_evidence": 0,
    "active_listings_total": 10170,
    "listings_missing_security": 0,
    "listings_missing_exchange": 0,
    "listings_missing_symbol_history": 0,
    "active_listings_without_active_symbol_history": 0,
    "raw_sec_exchange_values_unmapped": [{"raw_exchange": "CBOE", "observation_count": 27}],
    "listings_by_exchange": [
        {"exchange_code": "NASDAQ", "exchange_name": "Nasdaq Stock Market", "listing_count": 4307},
        {"exchange_code": "NYSE", "exchange_name": "New York Stock Exchange", "listing_count": 3303},
        {"exchange_code": "OTC", "exchange_name": "Over-the-Counter Markets", "listing_count": 2560},
    ],
    "raw_sec_exchange_values": [
        {"raw_exchange": "Nasdaq", "observation_count": 4307},
        {"raw_exchange": "NYSE", "observation_count": 3303},
        {"raw_exchange": "OTC", "observation_count": 2560},
        {"raw_exchange": None, "observation_count": 219},
        {"raw_exchange": "CBOE", "observation_count": 27},
    ],
    "duplicate_cik_issuers": [],
    "duplicate_cik_identifiers_to_multiple_issuers": [],
    "same_issuer_ticker_multi_security": [],
    "securities_missing_ticker_identifier": 0,
    "evidence_missing_target_rows": 0,
    "same_exchange_ticker_multi_security": [],
    "same_exchange_ticker_multi_issuer": [],
    "same_security_exchange_active_listing": [],
    "same_cik_multiple_issuer_names": [
        {"cik": "0000036104", "issuer_name_count": 2},
    ],
    "same_listing_multiple_active_symbols": [],
}
