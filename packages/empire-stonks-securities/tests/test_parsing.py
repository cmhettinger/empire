from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from empire_core import ObjectStore
from empire_core.object_store.models import StorageRoot, StoredObject
from empire_stonks_securities.acquisition import SEC_SOURCE_OBJECT_KIND
from empire_stonks_securities.parsing import (
    SecCompanyTickerExchangeParser,
    SecCompanyTickerParser,
    SecSourceParseError,
    get_sec_source_parser,
    parse_sec_source_path,
    parse_sec_source_records_path,
    parse_sec_source_run,
)


FIXTURES = Path(__file__).parent / "fixtures" / "sec"


def test_company_tickers_exchange_successful_parse_and_normalization():
    result = SecCompanyTickerExchangeParser().parse_path(FIXTURES / "company_tickers_exchange.json")

    assert len(result.records) == 2
    assert len(result.bad_records) == 1
    record = result.records[0]
    assert record.source_code == "sec_company_tickers_exchange"
    assert record.cik == 320193
    assert record.cik_padded == "0000320193"
    assert record.company_name == "Apple Inc."
    assert record.ticker == "aapl"
    assert record.ticker_norm == "AAPL"
    assert record.exchange == "Nasdaq"
    assert record.raw == {
        "cik": 320193,
        "name": " Apple Inc. ",
        "ticker": " aapl ",
        "exchange": " Nasdaq ",
    }
    assert result.records[1].exchange is None


def test_company_tickers_successful_parse_and_normalization():
    result = SecCompanyTickerParser().parse_path(FIXTURES / "company_tickers.json")

    assert len(result.records) == 2
    assert len(result.bad_records) == 1
    record = result.records[0]
    assert record.source_code == "sec_company_tickers"
    assert record.cik == 320193
    assert record.cik_padded == "0000320193"
    assert record.company_name == "Apple Inc."
    assert record.ticker == "aapl"
    assert record.ticker_norm == "AAPL"
    assert record.raw == {
        "cik_str": 320193,
        "ticker": " aapl ",
        "title": " Apple Inc. ",
    }


def test_malformed_rows_are_returned_without_warning_log(caplog):
    parser = SecCompanyTickerParser()

    with caplog.at_level("WARNING"):
        result = parser.parse_payload(
            {
                "0": {"cik_str": 1, "ticker": "OK", "title": "Okay Corp"},
                "1": {"cik_str": 2, "title": "Missing Ticker Corp"},
            }
        )

    assert len(result.records) == 1
    assert len(result.bad_records) == 1
    assert result.bad_records[0].row_number == "1"
    assert result.bad_records[0].error == "missing required field: ticker"
    assert "Skipping malformed SEC source record" not in caplog.text


def test_invalid_payload_shape_raises_clear_parser_exception():
    with pytest.raises(SecSourceParseError, match="object keyed by sequence number"):
        SecCompanyTickerParser().parse_payload([])


def test_parser_registry_dispatch_accepts_source_key_and_provider_code():
    assert isinstance(get_sec_source_parser("sec_company_tickers_exchange"), SecCompanyTickerExchangeParser)
    assert isinstance(get_sec_source_parser("SEC_COMPANY_TICKERS_EXCHANGE"), SecCompanyTickerExchangeParser)
    assert isinstance(get_sec_source_parser("sec_company_tickers"), SecCompanyTickerParser)
    assert isinstance(get_sec_source_parser("SEC_COMPANY_TICKERS"), SecCompanyTickerParser)


def test_parse_sec_source_path_dispatches_to_registered_parser():
    result = parse_sec_source_path(
        "SEC_COMPANY_TICKERS",
        FIXTURES / "company_tickers.json",
    )

    assert result.source_code == "sec_company_tickers"
    assert [record.ticker_norm for record in result.records] == ["AAPL", "MSFT"]
    assert [
        record.ticker_norm
        for record in parse_sec_source_records_path(
            "sec_company_tickers",
            FIXTURES / "company_tickers.json",
        )
    ] == ["AAPL", "MSFT"]


def test_parse_sec_source_run_loads_downloaded_object_from_object_store(tmp_path):
    run_id = uuid4()
    object_store = ObjectStore(FakeObjectRepository(tmp_path))
    object_store.put_bytes(
        run_context=FakeRunContext(run_id),
        object_scope="run",
        domain="stonks",
        logical_name="SEC_COMPANY_TICKERS",
        storage_root="global",
        object_key="stonks/securities/runs/2026/06/11/test/sec_company_tickers",
        filename="company_tickers.json",
        data=(FIXTURES / "company_tickers.json").read_bytes(),
        content_type="application/json",
        object_kind=SEC_SOURCE_OBJECT_KIND,
    )

    result = parse_sec_source_run("sec_company_tickers", object_store, run_id)

    assert [record.cik_padded for record in result.records] == ["0000320193", "0000789019"]


class FakeRunContext:
    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        self.domain = "stonks"


class FakeObjectRepository:
    def __init__(self, base_uri: str | Path):
        self.roots = {
            "global": StorageRoot(
                storage_root_id=1,
                root_name="global",
                backend_type="filesystem",
                base_uri=str(base_uri),
            )
        }
        self.objects: dict[UUID, StoredObject] = {}

    def get_storage_root(self, root_name: str) -> StorageRoot | None:
        return self.roots.get(root_name)

    def insert_object(self, **kwargs) -> StoredObject:
        root = self.roots["global"]
        stored = StoredObject(
            object_id=uuid4(),
            run_id=kwargs["run_id"],
            storage_root_id=kwargs["storage_root_id"],
            storage_root_name=root.root_name,
            base_uri=root.base_uri,
            object_key=kwargs["object_key"],
            filename=kwargs["filename"],
            object_scope=kwargs["object_scope"],
            domain=kwargs["domain"],
            logical_name=kwargs["logical_name"],
            content_type=kwargs["content_type"],
            object_kind=kwargs["object_kind"],
            size_bytes=kwargs["size_bytes"],
            checksum_sha256=kwargs["checksum_sha256"],
            expires_at=kwargs["expires_at"],
            deleted_at=None,
            purge_after=None,
            delete_attempts=0,
            last_delete_error=None,
            metadata=kwargs["metadata"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.objects[stored.object_id] = stored
        return stored

    def get_object(self, object_id: UUID) -> StoredObject | None:
        return self.objects.get(object_id)

    def find_one(
        self,
        *,
        run_id: UUID | None,
        object_kind: str | None,
        filename: str | None,
        logical_name: str | None,
    ) -> StoredObject | None:
        matches = [
            stored
            for stored in self.objects.values()
            if stored.deleted_at is None
            and (run_id is None or stored.run_id == run_id)
            and (object_kind is None or stored.object_kind == object_kind)
            and (filename is None or stored.filename == filename)
            and (logical_name is None or stored.logical_name == logical_name)
        ]
        matches.sort(key=lambda stored: stored.created_at or datetime.min, reverse=True)
        return matches[0] if matches else None

    def mark_deleted(self, object_id: UUID, purge_after) -> None:
        self.objects[object_id] = replace(
            self.objects[object_id],
            deleted_at=datetime.now(UTC),
            purge_after=purge_after,
            updated_at=datetime.now(UTC),
        )

    def record_delete_error(self, object_id: UUID, error_message: str) -> None:
        self.objects[object_id] = replace(
            self.objects[object_id],
            delete_attempts=self.objects[object_id].delete_attempts + 1,
            last_delete_error=error_message,
            updated_at=datetime.now(UTC),
        )
