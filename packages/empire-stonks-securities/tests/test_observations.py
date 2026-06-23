from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from empire_stonks_securities.observations import (
    SecObservationWriteError,
    SecSourceFileMetadata,
    build_sec_observation,
    compute_row_hash,
    summary_json_for_record,
    write_sec_observations,
)
from empire_stonks_securities.parsing import (
    SecCompanyTickerExchangeRecord,
    SecCompanyTickerRecord,
)


DOWNLOADED_AT = datetime(2026, 6, 18, 12, 30, tzinfo=UTC)


def test_writes_observations_for_ticker_exchange_records():
    conn = FakeConnection()
    record = ticker_exchange_record()
    metadata = source_metadata("sec_company_tickers_exchange")

    summary = write_sec_observations(
        connection=conn,
        records=[record],
        source_metadata=metadata,
    )

    assert summary.to_dict() == {
        "source_code": "sec_company_tickers_exchange",
        "provider_code": "SEC_COMPANY_TICKERS_EXCHANGE",
        "input_count": 1,
        "inserted_count": 1,
        "skipped_count": 0,
        "failed_count": 0,
    }
    assert conn.commit_count == 1
    inserted = conn.observations[0]
    assert inserted["provider_code"] == "SEC_COMPANY_TICKERS_EXCHANGE"
    assert inserted["provider_date"].isoformat() == "2026-06-18"
    assert inserted["observed_at"] == DOWNLOADED_AT
    assert inserted["object_id"] == metadata.object_id
    assert inserted["object_key"] == metadata.object_key
    assert inserted["source_url"] == metadata.source_url
    assert inserted["summary_json"]["exchange"] == "Nasdaq"
    assert inserted["summary_json"]["raw"] == record.raw
    assert inserted["summary_json"]["source_file"]["sha256"] == "file-sha"


def test_writes_observations_for_ticker_records():
    conn = FakeConnection()
    record = ticker_record()

    summary = write_sec_observations(
        connection=conn,
        records=[record],
        source_metadata=source_metadata("sec_company_tickers"),
    )

    assert summary.provider_code == "SEC_COMPANY_TICKERS"
    assert summary.inserted_count == 1
    inserted = conn.observations[0]
    assert inserted["provider_code"] == "SEC_COMPANY_TICKERS"
    assert inserted["summary_json"]["source_code"] == "sec_company_tickers"
    assert inserted["summary_json"]["cik_padded"] == "0000320193"
    assert "exchange" not in inserted["summary_json"]


def test_summary_raw_json_is_preserved():
    record = ticker_exchange_record()

    summary = summary_json_for_record(record)

    assert summary == {
        "source_code": "sec_company_tickers_exchange",
        "cik": 320193,
        "cik_padded": "0000320193",
        "ticker": "aapl",
        "ticker_norm": "AAPL",
        "company_name": "Apple Inc.",
        "exchange": "Nasdaq",
        "raw": {
            "cik": 320193,
            "name": " Apple Inc. ",
            "ticker": " aapl ",
            "exchange": " Nasdaq ",
        },
    }


def test_row_hash_is_deterministic():
    first = compute_row_hash(summary_json_for_record(ticker_exchange_record()))
    second = compute_row_hash(summary_json_for_record(ticker_exchange_record()))
    changed = summary_json_for_record(ticker_exchange_record(exchange="NYSE"))

    assert first == second
    assert first != compute_row_hash(changed)


def test_idempotent_rerun_skips_duplicate_observations():
    conn = FakeConnection()
    record = ticker_exchange_record()
    metadata = source_metadata("sec_company_tickers_exchange")

    first = write_sec_observations(
        connection=conn,
        records=[record],
        source_metadata=metadata,
    )
    second = write_sec_observations(
        connection=conn,
        records=[record],
        source_metadata=metadata,
    )

    assert first.inserted_count == 1
    assert first.skipped_count == 0
    assert second.inserted_count == 0
    assert second.skipped_count == 1
    assert len(conn.observations) == 1


def test_unchanged_file_with_new_object_identity_skips_duplicate_observations():
    conn = FakeConnection()
    record = ticker_exchange_record()
    first_metadata = source_metadata("sec_company_tickers_exchange")
    second_metadata = SecSourceFileMetadata(
        source_code=first_metadata.source_code,
        source_url=first_metadata.source_url,
        downloaded_at=first_metadata.downloaded_at,
        file_path="/tmp/rerun/company_tickers_exchange.json",
        object_id=uuid4(),
        object_key="stonks/securities/runs/2026/06/19/rerun/sec_company_tickers_exchange",
        size_bytes=first_metadata.size_bytes,
        sha256=first_metadata.sha256,
        etag=first_metadata.etag,
        last_modified=first_metadata.last_modified,
    )

    first = write_sec_observations(
        connection=conn,
        records=[record],
        source_metadata=first_metadata,
    )
    second = write_sec_observations(
        connection=conn,
        records=[record],
        source_metadata=second_metadata,
    )

    assert first.inserted_count == 1
    assert second.inserted_count == 0
    assert second.skipped_count == 1
    assert len(conn.observations) == 1
    assert conn.observations[0]["object_id"] == first_metadata.object_id


def test_malformed_record_fails_clearly():
    record = SecCompanyTickerRecord(
        source_code="sec_company_tickers",
        cik=320193,
        cik_padded="0000320193",
        company_name="Apple Inc.",
        ticker="aapl",
        ticker_norm="",
        raw={"cik_str": 320193, "ticker": "aapl", "title": "Apple Inc."},
    )

    with pytest.raises(SecObservationWriteError, match="ticker_norm cannot be blank"):
        build_sec_observation(record)


def ticker_exchange_record(exchange: str | None = "Nasdaq") -> SecCompanyTickerExchangeRecord:
    return SecCompanyTickerExchangeRecord(
        source_code="sec_company_tickers_exchange",
        cik=320193,
        cik_padded="0000320193",
        company_name="Apple Inc.",
        ticker="aapl",
        ticker_norm="AAPL",
        exchange=exchange,
        raw={
            "cik": 320193,
            "name": " Apple Inc. ",
            "ticker": " aapl ",
            "exchange": f" {exchange} " if exchange else "",
        },
    )


def ticker_record() -> SecCompanyTickerRecord:
    return SecCompanyTickerRecord(
        source_code="sec_company_tickers",
        cik=320193,
        cik_padded="0000320193",
        company_name="Apple Inc.",
        ticker="aapl",
        ticker_norm="AAPL",
        raw={"cik_str": 320193, "ticker": " aapl ", "title": " Apple Inc. "},
    )


def source_metadata(source_code: str) -> SecSourceFileMetadata:
    return SecSourceFileMetadata(
        source_code=source_code,
        source_url=f"https://www.sec.gov/files/{source_code}.json",
        downloaded_at=DOWNLOADED_AT,
        file_path=f"/tmp/{source_code}.json",
        object_id=uuid4(),
        object_key=f"stonks/securities/runs/2026/06/18/test/{source_code}",
        size_bytes=123,
        sha256="file-sha",
        etag='"etag"',
        last_modified="Thu, 18 Jun 2026 12:00:00 GMT",
    )


class FakeConnection:
    def __init__(self) -> None:
        self.observations: list[dict] = []
        self.raw_keys: set[tuple[str, str]] = set()
        self.commit_count = 0
        self.last_fetchone = None

    def cursor(self):
        return FakeCursor(self)

    def commit(self) -> None:
        self.commit_count += 1


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql: str, params=None) -> None:
        if "INSERT INTO stonks.provider_observation" not in sql:
            self.connection.last_fetchone = None
            return
        provider_code = params[0]
        raw_key = params[6]
        dedupe_key = (provider_code, raw_key)
        if dedupe_key in self.connection.raw_keys:
            self.connection.last_fetchone = None
            return
        self.connection.raw_keys.add(dedupe_key)
        self.connection.observations.append(
            {
                "provider_code": provider_code,
                "provider_date": params[1],
                "observed_at": params[2],
                "object_id": params[3],
                "object_key": params[4],
                "source_url": params[5],
                "raw_key": raw_key,
                "summary_json": json.loads(params[7]),
            }
        )
        self.connection.last_fetchone = (uuid4(),)

    def fetchone(self):
        return self.connection.last_fetchone
