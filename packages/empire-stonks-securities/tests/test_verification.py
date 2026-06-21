from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from empire_core import ObjectStore
from empire_stonks_securities.acquisition import (
    SEC_SOURCE_METADATA_OBJECT_KIND,
    SEC_SOURCE_OBJECT_KIND,
)
from empire_stonks_securities.verification import (
    VerifyRunContext,
    generate_verify_report,
    verify_stonks_securities_daily_sources,
    write_verify_report_to_object_store,
)

from test_parsing import FIXTURES, FakeObjectRepository, FakeRunContext


def test_verify_daily_sources_logs_counts_and_bad_records(tmp_path, caplog):
    run_id = uuid4()
    object_store = ObjectStore(FakeObjectRepository(tmp_path))
    _put_source(
        object_store=object_store,
        run_id=run_id,
        logical_name="SEC_COMPANY_TICKERS_EXCHANGE",
        object_key="stonks/securities/runs/2026/06/11/test/sec_company_tickers_exchange",
        filename="company_tickers_exchange.json",
        fixture_name="company_tickers_exchange.json",
    )
    _put_source(
        object_store=object_store,
        run_id=run_id,
        logical_name="SEC_COMPANY_TICKERS",
        object_key="stonks/securities/runs/2026/06/11/test/sec_company_tickers",
        filename="company_tickers.json",
        fixture_name="company_tickers.json",
    )

    with caplog.at_level("INFO"):
        result = verify_stonks_securities_daily_sources(
            object_store=object_store,
            input_run_id=run_id,
        )

    assert result.good_record_count == 4
    assert result.parse_error_count == 2
    assert result.failed_source_count == 0
    assert result.exchange_null_count == 1
    assert [summary.bad_record_count for summary in result.source_summaries] == [1, 1]
    assert [summary.exchange_null_count for summary in result.source_summaries] == [1, 0]
    assert [summary.checksum_status for summary in result.source_summaries] == ["PASS", "PASS"]
    assert result.to_dict()["exchange_null_count"] == 1
    assert result.to_dict()["source_summaries"][0]["exchange_null_count"] == 1
    assert "Verified SEC source: source_code=sec_company_tickers_exchange" in caplog.text
    assert "exchange_null_count=1" in caplog.text
    assert "Malformed SEC source row: source_code=sec_company_tickers" in caplog.text
    assert "raw_preview=" in caplog.text


def test_verify_daily_sources_reports_missing_source_object(tmp_path, caplog):
    run_id = uuid4()
    object_store = ObjectStore(FakeObjectRepository(tmp_path))

    with caplog.at_level("ERROR"):
        result = verify_stonks_securities_daily_sources(
            object_store=object_store,
            input_run_id=run_id,
            source_codes=("sec_company_tickers",),
        )

    assert result.good_record_count == 0
    assert result.parse_error_count == 1
    assert result.failed_source_count == 1
    assert result.exchange_null_count == 0
    assert result.source_summaries[0].failed is True
    assert result.source_summaries[0].filename == "company_tickers.json"
    assert "SEC source object not found for verify" in caplog.text


def test_verify_report_warns_with_sources_metadata_checksums_and_bad_records(tmp_path):
    run_id = uuid4()
    generated_at = datetime(2026, 6, 21, 13, 22, tzinfo=UTC)
    object_store = ObjectStore(FakeObjectRepository(tmp_path))
    _put_source(
        object_store=object_store,
        run_id=run_id,
        logical_name="SEC_COMPANY_TICKERS",
        object_key="stonks/securities/runs/2026/06/21/test/sec_company_tickers",
        filename="company_tickers.json",
        fixture_name="company_tickers.json",
    )

    result = verify_stonks_securities_daily_sources(
        object_store=object_store,
        input_run_id=run_id,
        source_codes=("sec_company_tickers",),
    )
    report = generate_verify_report(
        result=result,
        run_context=VerifyRunContext(source_run_id=str(run_id)),
        generated_at=generated_at,
    )

    assert report["summary"]["status"] == "WARN"
    assert report["summary"]["healthy"] is True
    assert report["summary"]["inputs_checked"] == 1
    assert report["summary"]["inputs_present"] == 1
    assert report["summary"]["metadata_files_present"] == 1
    assert report["summary"]["checksum_verified"] == 1
    assert report["sources"][0]["checksum_status"] == "PASS"


def test_verify_report_passes_with_clean_required_source(tmp_path):
    run_id = uuid4()
    object_store = ObjectStore(FakeObjectRepository(tmp_path))
    data = json.dumps(
        {"0": {"cik_str": 1, "ticker": "ABC", "title": "ABC Corp"}}
    ).encode("utf-8")
    _put_source_bytes(
        object_store=object_store,
        run_id=run_id,
        logical_name="SEC_COMPANY_TICKERS",
        object_key="stonks/securities/runs/2026/06/21/test/sec_company_tickers",
        filename="company_tickers.json",
        data=data,
    )

    result = verify_stonks_securities_daily_sources(
        object_store=object_store,
        input_run_id=run_id,
        source_codes=("sec_company_tickers",),
    )
    report = generate_verify_report(result=result)

    assert report["summary"]["status"] == "PASS"
    assert report["healthy"] is True
    assert report["warnings"] == []
    assert report["failures"] == []


def test_verify_report_fails_on_missing_required_source(tmp_path):
    run_id = uuid4()
    object_store = ObjectStore(FakeObjectRepository(tmp_path))

    result = verify_stonks_securities_daily_sources(
        object_store=object_store,
        input_run_id=run_id,
        source_codes=("sec_company_tickers",),
    )
    report = generate_verify_report(result=result)

    assert report["summary"]["status"] == "FAIL"
    assert report["healthy"] is False
    assert report["summary"]["inputs_missing"] == 1
    assert report["failures"]


def test_verify_report_fails_on_checksum_mismatch(tmp_path):
    run_id = uuid4()
    object_store = ObjectStore(FakeObjectRepository(tmp_path))
    _put_source(
        object_store=object_store,
        run_id=run_id,
        logical_name="SEC_COMPANY_TICKERS",
        object_key="stonks/securities/runs/2026/06/21/test/sec_company_tickers",
        filename="company_tickers.json",
        fixture_name="company_tickers.json",
        metadata_sha256="wrong",
    )

    result = verify_stonks_securities_daily_sources(
        object_store=object_store,
        input_run_id=run_id,
        source_codes=("sec_company_tickers",),
    )
    report = generate_verify_report(result=result)

    assert report["summary"]["status"] == "FAIL"
    assert report["summary"]["checksum_failed"] == 1
    assert report["sources"][0]["checksum_status"] == "FAIL"


def test_write_verify_report_to_object_store_uses_run_report_path(tmp_path):
    object_store = ObjectStore(FakeObjectRepository(tmp_path))
    report = {
        "report_name": "stonks_securities_verify",
        "generated_at": "2026-06-21T13:22:00+00:00",
        "run_context": {"logical_date": "2026-06-21T13:22:00+00:00"},
        "healthy": True,
        "summary": {"status": "PASS"},
    }

    stored = write_verify_report_to_object_store(
        report=report,
        object_store=object_store,
        generated_at=datetime(2026, 6, 21, 13, 22, tzinfo=UTC),
    )

    assert stored.object_key == "stonks/securities/runs/2026/06/21/run-reports/verify"
    assert stored.object_kind == "stonks_securities_verify_report"


def _put_source(
    *,
    object_store: ObjectStore,
    run_id,
    logical_name: str,
    object_key: str,
    filename: str,
    fixture_name: str,
    metadata_sha256: str | None = None,
) -> None:
    data = (FIXTURES / fixture_name).read_bytes()
    _put_source_bytes(
        object_store=object_store,
        run_id=run_id,
        logical_name=logical_name,
        object_key=object_key,
        filename=filename,
        data=data,
        metadata_sha256=metadata_sha256,
    )


def _put_source_bytes(
    *,
    object_store: ObjectStore,
    run_id,
    logical_name: str,
    object_key: str,
    filename: str,
    data: bytes,
    metadata_sha256: str | None = None,
) -> None:
    stored = object_store.put_bytes(
        run_context=FakeRunContext(run_id),
        object_scope="run",
        domain="stonks",
        logical_name=logical_name,
        storage_root="global",
        object_key=object_key,
        filename=filename,
        data=data,
        content_type="application/json",
        object_kind=SEC_SOURCE_OBJECT_KIND,
    )
    metadata_digest = metadata_sha256 or stored.checksum_sha256 or sha256(data).hexdigest()
    metadata = {
        "source_code": logical_name.lower(),
        "file_path": f"{object_key}/{filename}",
        "size_bytes": len(data),
        "sha256": metadata_digest,
        "downloaded_at": "2026-06-21T13:22:00+00:00",
        "etag": '"test"',
        "last_modified": "Sun, 21 Jun 2026 13:22:00 GMT",
    }
    object_store.put_bytes(
        run_context=FakeRunContext(run_id),
        object_scope="run",
        domain="stonks",
        logical_name=f"{logical_name}.metadata",
        storage_root="global",
        object_key=object_key,
        filename=f"{filename}.metadata.json",
        data=json.dumps(metadata).encode("utf-8"),
        content_type="application/json",
        object_kind=SEC_SOURCE_METADATA_OBJECT_KIND,
    )
