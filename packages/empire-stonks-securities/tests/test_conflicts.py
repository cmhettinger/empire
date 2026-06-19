from __future__ import annotations

import json
from datetime import UTC, datetime

from empire_stonks_securities.conflicts import (
    ConflictRunContext,
    conflict_report_to_json,
    evaluate_conflict_status,
    generate_phase_2a_conflict_report,
    write_conflict_report_to_console,
    write_conflict_report_to_file,
)


GENERATED_AT = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


def test_conflict_report_json_shape_is_stable():
    conn = FakeConnection()
    report = generate_phase_2a_conflict_report(
        connection=conn,
        run_context=ConflictRunContext(dag_id="test_dag", run_id="test_run"),
        generated_at=GENERATED_AT,
    )

    assert list(report.keys()) == [
        "report_name",
        "generated_at",
        "run_context",
        "summary",
        "source_priority",
        "conflicts_by_category",
        "conflicts",
    ]
    assert report["report_name"] == "stonks_securities_phase_2a_conflicts"
    assert report["run_context"]["dag_id"] == "test_dag"
    assert report["source_priority"]["sec_company_tickers_exchange"] == 100
    assert report["summary"] == {
        "status": "PASS",
        "conflicts_total": 0,
        "failures_total": 0,
        "warnings_total": 0,
        "info_total": 0,
    }


def test_conflict_sql_does_not_group_by_select_aliases():
    conn = FakeConnection()
    generate_phase_2a_conflict_report(
        connection=conn,
        run_context=ConflictRunContext(dag_id="test_dag", run_id="test_run"),
        generated_at=GENERATED_AT,
    )

    grouped_aliases = {
        "issuer_missing_cik_from_sec_evidence": "GROUP BY pe.issuer_id, cik",
        "observation_ticker_security_identifier_mismatch": (
            "GROUP BY po.provider_observation_id, pe.security_id, observation_ticker_norm"
        ),
        "unknown_exchange_mapping": "GROUP BY raw_exchange",
        "security_current_sec_multiple_exchanges": "GROUP BY pe.security_id, ticker_norm",
    }
    for metric, alias_group in grouped_aliases.items():
        assert alias_group not in conn.sql_by_metric[metric]


def test_status_evaluation_pass_warn_or_fail():
    assert evaluate_conflict_status([]) == "PASS"
    assert evaluate_conflict_status([{"severity": "INFO"}]) == "PASS"
    assert evaluate_conflict_status([{"severity": "WARN"}]) == "WARN"
    assert evaluate_conflict_status([{"severity": "FAIL"}]) == "FAIL"


def test_duplicate_cik_identifier_maps_to_multiple_issuers():
    conn = FakeConnection()
    conn.results["cik_identifier_multiple_issuers"] = [
        {"cik": "0000320193", "issuer_count": 2, "issuer_ids": ["issuer-1", "issuer-2"]}
    ]

    report = generate_phase_2a_conflict_report(connection=conn, generated_at=GENERATED_AT)

    conflict = report["conflicts"][0]
    assert report["summary"]["status"] == "FAIL"
    assert conflict["category"] == "cik_identifier_multiple_issuers"
    assert conflict["severity"] == "FAIL"
    assert conflict["entity_ids"]["issuer_ids"] == ["issuer-1", "issuer-2"]


def test_ticker_exchange_mapped_to_multiple_securities_fails():
    conn = FakeConnection()
    conn.results["ticker_exchange_multiple_securities"] = [
        {
            "ticker_norm": "ABC",
            "exchange_code": "NASDAQ",
            "exchange_id": "exchange-1",
            "security_count": 2,
            "security_ids": ["security-1", "security-2"],
            "listing_ids": ["listing-1", "listing-2"],
        }
    ]

    report = generate_phase_2a_conflict_report(connection=conn, generated_at=GENERATED_AT)

    conflict = report["conflicts"][0]
    assert report["summary"]["status"] == "FAIL"
    assert conflict["category"] == "ticker_exchange_multiple_securities"
    assert conflict["keys"] == {"ticker_norm": "ABC", "exchange_code": "NASDAQ"}


def test_same_issuer_ticker_mapped_to_multiple_securities_warns():
    conn = FakeConnection()
    conn.results["same_issuer_ticker_multiple_securities"] = [
        {
            "issuer_id": "issuer-1",
            "ticker_norm": "ABC",
            "security_count": 2,
            "security_ids": ["security-1", "security-2"],
        }
    ]

    report = generate_phase_2a_conflict_report(connection=conn, generated_at=GENERATED_AT)

    assert report["summary"]["status"] == "WARN"
    assert report["conflicts"][0]["category"] == "same_issuer_ticker_multiple_securities"
    assert report["conflicts"][0]["severity"] == "WARN"


def test_unknown_exchange_and_missing_listing_evidence_warn():
    conn = FakeConnection()
    conn.results["unknown_exchange_mapping"] = [
        {
            "raw_exchange": "CBOE",
            "observation_count": 27,
            "observation_ids": ["obs-1", "obs-2"],
        }
    ]
    conn.results["exchange_observation_missing_listing_evidence"] = [
        {
            "provider_observation_id": "obs-3",
            "ticker_norm": "XYZ",
            "raw_exchange": "NYSE",
            "cik": "0000000001",
        }
    ]

    report = generate_phase_2a_conflict_report(connection=conn, generated_at=GENERATED_AT)

    categories = {conflict["category"] for conflict in report["conflicts"]}
    assert report["summary"]["status"] == "WARN"
    assert categories == {
        "unknown_exchange_mapping",
        "exchange_observation_missing_listing_evidence",
    }


def test_name_conflict_classification_warns_for_material_variants():
    conn = FakeConnection()
    conn.results["cik_name_variants"] = [
        {
            "cik": "0000320193",
            "name_count": 2,
            "material_name_count": 2,
            "company_names": ["Apple Inc.", "Orange Holdings Ltd."],
        }
    ]

    report = generate_phase_2a_conflict_report(connection=conn, generated_at=GENERATED_AT)

    assert report["summary"]["status"] == "WARN"
    assert report["conflicts"][0]["category"] == "cik_name_variants"
    assert report["conflicts"][0]["severity"] == "WARN"


def test_conflict_report_to_json_is_pretty_and_deterministic():
    report = generate_phase_2a_conflict_report(
        connection=FakeConnection(),
        generated_at=GENERATED_AT,
    )

    rendered = conflict_report_to_json(report)

    assert rendered.endswith("\n")
    assert json.loads(rendered)["generated_at"] == "2026-06-19T12:00:00+00:00"
    assert "\n  \"summary\": {" in rendered


def test_console_and_file_output(tmp_path, capsys):
    report = generate_phase_2a_conflict_report(
        connection=FakeConnection(),
        generated_at=GENERATED_AT,
    )
    output_path = tmp_path / "conflicts.json"

    write_conflict_report_to_console(report)
    write_conflict_report_to_file(report, output_path)

    assert json.loads(capsys.readouterr().out)["report_name"] == "stonks_securities_phase_2a_conflicts"
    assert json.loads(output_path.read_text(encoding="utf-8"))["summary"]["conflicts_total"] == 0


class FakeConnection:
    def __init__(self) -> None:
        self.results = {metric: [] for metric in DEFAULT_METRICS}
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

    def fetchall(self):
        return self.result


DEFAULT_METRICS = [
    "cik_identifier_multiple_issuers",
    "issuer_missing_cik_from_sec_evidence",
    "observation_cik_issuer_identifier_mismatch",
    "same_issuer_ticker_multiple_securities",
    "ticker_exchange_multiple_securities",
    "ticker_exchange_multiple_issuers",
    "observation_ticker_security_identifier_mismatch",
    "ticker_exchange_multiple_active_listings",
    "security_exchange_multiple_active_listings",
    "active_listing_missing_current_symbol",
    "listing_multiple_current_symbols",
    "cik_name_variants",
    "unknown_exchange_mapping",
    "listing_exchange_observation_disagreement",
    "security_current_sec_multiple_exchanges",
    "exchange_observation_missing_listing_evidence",
    "evidence_missing_target_rows",
    "observation_multiple_targets",
]
