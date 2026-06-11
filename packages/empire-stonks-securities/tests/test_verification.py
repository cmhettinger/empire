from __future__ import annotations

from uuid import uuid4

from empire_core import ObjectStore
from empire_stonks_securities.acquisition import SEC_SOURCE_OBJECT_KIND
from empire_stonks_securities.verification import verify_stonks_securities_daily_sources

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


def _put_source(
    *,
    object_store: ObjectStore,
    run_id,
    logical_name: str,
    object_key: str,
    filename: str,
    fixture_name: str,
) -> None:
    object_store.put_bytes(
        run_context=FakeRunContext(run_id),
        object_scope="run",
        domain="stonks",
        logical_name=logical_name,
        storage_root="global",
        object_key=object_key,
        filename=filename,
        data=(FIXTURES / fixture_name).read_bytes(),
        content_type="application/json",
        object_kind=SEC_SOURCE_OBJECT_KIND,
    )
