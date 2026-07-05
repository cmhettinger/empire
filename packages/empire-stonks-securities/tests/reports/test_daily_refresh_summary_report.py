from __future__ import annotations

from datetime import UTC, datetime

from empire_stonks_securities.reports.daily_refresh_summary.data import (
    load_canonical_market_snapshot,
)
from empire_stonks_securities.reports.daily_refresh_summary.pdf.render import (
    DEFAULT_REPORT_TIMEZONE,
    _market_table_rows,
    _report_timezone,
    _run_facts_rows,
    render_daily_refresh_summary_pdf,
)


GENERATED_AT = datetime(2026, 6, 21, 13, 22, tzinfo=UTC)


def test_canonical_market_snapshot_groups_smaller_markets():
    conn = FakeConnection()

    with conn.cursor() as cursor:
        snapshot = load_canonical_market_snapshot(cursor, market_group_limit=3)

    assert snapshot["markets_represented"] == 4
    assert snapshot["markets_reported"] == 3
    assert snapshot["totals"] == {
        "issuers_total": 17,
        "securities_total": 23,
        "securities_provisional_total": 20,
        "securities_confirmed_total": 3,
        "securities_unknown_identity_status_total": 0,
        "listings_total": 29,
    }
    assert [market["exchange_code"] for market in snapshot["markets"]] == [
        "XNAS",
        "XNYS",
        "OTHER",
    ]
    assert snapshot["markets"][-1] == {
        "exchange_code": "OTHER",
        "exchange_name": "Other represented markets",
        "market_count": 2,
        "issuers_total": 3,
        "securities_total": 5,
        "securities_provisional_total": 5,
        "securities_confirmed_total": 0,
        "securities_unknown_identity_status_total": 0,
        "listings_total": 7,
    }


def test_daily_refresh_summary_pdf_smoke_render(tmp_path):
    result = render_daily_refresh_summary_pdf(
        report=_report(),
        output_dir=tmp_path,
        generated_at=GENERATED_AT,
    )

    artifact = result.primary_artifact
    assert artifact.path.is_file()
    assert artifact.path.suffix == ".pdf"
    assert artifact.media_type == "application/pdf"
    assert artifact.path.stat().st_size > 1000


def test_canonical_market_snapshot_pdf_rows_include_totals_row():
    rows = _market_table_rows(_report())

    assert rows[-1] == ["Total", "8,026", "10,453", "10,170"]
    assert all("Overall canonical totals" not in " ".join(row) for row in rows)


def test_canonical_market_snapshot_pdf_totals_row_sums_rendered_markets():
    report = _report()
    report["market_snapshot"]["markets"].append(
        {
            "exchange_code": "XNYS",
            "exchange_name": "NEW YORK STOCK EXCHANGE",
            "market_count": 1,
            "issuers_total": 4,
            "securities_total": 5,
            "listings_total": 6,
        }
    )

    rows = _market_table_rows(report)

    assert rows[-1] == ["Total", "8,030", "10,458", "10,176"]


def test_run_facts_pdf_converts_utc_times_to_configured_report_timezone(monkeypatch):
    monkeypatch.setenv("EMPIRE_REPORT_TIMEZONE", "America/Los_Angeles")

    rows = _run_facts_rows(
        _report(),
        generated_at=GENERATED_AT,
        report_timezone=_report_timezone(),
    )

    assert ["Generated At", "2026-06-21 06:22:00 PDT"] in rows
    assert ["SEC File Date - Exchange", "2026-06-18 12:38:29 PDT (65.7 hours old)"] in rows


def test_missing_report_timezone_falls_back_to_eastern_time(monkeypatch):
    monkeypatch.delenv("EMPIRE_REPORT_TIMEZONE", raising=False)

    report_timezone = _report_timezone()
    rows = _run_facts_rows(
        _report(),
        generated_at=GENERATED_AT,
        report_timezone=report_timezone,
    )

    assert report_timezone.key == DEFAULT_REPORT_TIMEZONE
    assert ["Generated At", "2026-06-21 09:22:00 EDT"] in rows
    assert ["SEC File Date - Exchange", "2026-06-18 15:38:29 EDT (65.7 hours old)"] in rows


class FakeConnection:
    def __init__(self) -> None:
        self.results = {
            "daily_summary_canonical_market_totals": {
                "issuers_total": 17,
                "securities_total": 23,
                "securities_provisional_total": 20,
                "securities_confirmed_total": 3,
                "securities_unknown_identity_status_total": 0,
                "listings_total": 29,
            },
            "daily_summary_canonical_markets": [
                {
                    "exchange_code": "XNAS",
                    "exchange_name": "NASDAQ",
                    "issuers_total": 10,
                    "securities_total": 12,
                    "securities_provisional_total": 10,
                    "securities_confirmed_total": 2,
                    "securities_unknown_identity_status_total": 0,
                    "listings_total": 13,
                },
                {
                    "exchange_code": "XNYS",
                    "exchange_name": "NEW YORK STOCK EXCHANGE",
                    "issuers_total": 4,
                    "securities_total": 6,
                    "securities_provisional_total": 5,
                    "securities_confirmed_total": 1,
                    "securities_unknown_identity_status_total": 0,
                    "listings_total": 9,
                },
                {
                    "exchange_code": "ARCX",
                    "exchange_name": "NYSE ARCA",
                    "issuers_total": 2,
                    "securities_total": 3,
                    "securities_provisional_total": 3,
                    "securities_confirmed_total": 0,
                    "securities_unknown_identity_status_total": 0,
                    "listings_total": 5,
                },
                {
                    "exchange_code": "OTCM",
                    "exchange_name": "OTC MARKETS",
                    "issuers_total": 1,
                    "securities_total": 2,
                    "securities_provisional_total": 2,
                    "securities_confirmed_total": 0,
                    "securities_unknown_identity_status_total": 0,
                    "listings_total": 2,
                },
            ],
        }

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
        self.result = self.connection.results[metric]

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


def _report() -> dict:
    return {
        "report_name": "stonks_securities_daily_summary",
        "generated_at": GENERATED_AT.isoformat(),
        "status": "WARN",
        "healthy": True,
        "run_context": {
            "dag_id": "stonks_securities_daily_refresh_summary",
            "run_id": "manual__2026-06-21T13:22:00+00:00",
            "source_run_id": "00000000-0000-0000-0000-000000000001",
            "logical_date": GENERATED_AT.isoformat(),
            "environment": "airflow",
        },
        "summary": {
            "status": "WARN",
            "warnings_total": 1,
            "failures_total": 0,
            "inputs_seen": 2,
            "inputs_missing": 0,
            "inputs_unchanged": 1,
            "observations_created": 20831,
            "issuers_created": 8026,
            "issuers_updated": 0,
            "securities_created": 10453,
            "securities_updated": 0,
            "listings_created": 10170,
            "listings_updated": 0,
            "validation_status": "PASS",
            "conflict_status": "WARN",
            "verify_status": "UNKNOWN",
            "canonical_issuers_total": 8026,
            "canonical_securities_total": 10453,
            "canonical_listings_total": 10170,
            "canonical_markets_represented": 3,
        },
        "warnings": [{"code": "conflict_report_warn", "message": "Conflict report completed with WARN status."}],
        "failures": [],
        "market_snapshot": {
            "markets": [
                {
                    "exchange_code": "XNAS",
                    "exchange_name": "NASDAQ",
                    "market_count": 1,
                    "issuers_total": 3900,
                    "securities_total": 5200,
                    "listings_total": 5300,
                },
                {
                    "exchange_code": "OTHER",
                    "exchange_name": "Other represented markets",
                    "market_count": 2,
                    "issuers_total": 4126,
                    "securities_total": 5253,
                    "listings_total": 4870,
                },
            ],
        },
        "input_freshness": {
            "sources": {
                "sec_company_tickers_exchange": {
                    "present": True,
                    "last_modified": "Thu, 18 Jun 2026 19:38:29 GMT",
                }
            }
        },
    }
