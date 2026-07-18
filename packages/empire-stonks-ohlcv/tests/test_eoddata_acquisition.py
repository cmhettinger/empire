from __future__ import annotations

import hashlib
import traceback
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from empire_core import ObjectStore, RunContext, StorageRoot, StoredObject
from empire_stonks_ohlcv import (
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
    EODDataCredentials,
    EODDataHTTPResponse,
    OHLCVAcquisitionError,
    OHLCVConfig,
    acquire_eoddata_objects,
)


RUN_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
STORED_AT = datetime(2026, 7, 17, 20, 0, tzinfo=UTC)
SECRET = "private-eoddata-acquisition-key"


class FakeObjectRepository:
    def __init__(self, base_uri: Path) -> None:
        self.root = StorageRoot(
            storage_root_id=1,
            root_name="global",
            backend_type="filesystem",
            base_uri=str(base_uri),
        )
        self.objects: dict[UUID, StoredObject] = {}

    def get_storage_root(self, root_name: str) -> StorageRoot | None:
        return self.root if root_name == "global" else None

    def insert_object(self, **values: Any) -> StoredObject:
        stored = StoredObject(
            object_id=uuid4(),
            run_id=values["run_id"],
            storage_root_id=values["storage_root_id"],
            storage_root_name=self.root.root_name,
            base_uri=self.root.base_uri,
            object_key=values["object_key"],
            filename=values["filename"],
            object_scope=values["object_scope"],
            domain=values["domain"],
            logical_name=values["logical_name"],
            content_type=values["content_type"],
            object_kind=values["object_kind"],
            size_bytes=values["size_bytes"],
            checksum_sha256=values["checksum_sha256"],
            expires_at=values["expires_at"],
            deleted_at=None,
            purge_after=None,
            metadata=values["metadata"],
            created_at=STORED_AT,
            updated_at=STORED_AT,
        )
        self.objects[stored.object_id] = stored
        return stored

    def get_object(self, object_id: UUID) -> StoredObject | None:
        return self.objects.get(object_id)


def _run_context(**overrides: object) -> RunContext:
    values = {
        "run_id": RUN_ID,
        "domain": "stonks",
        "job_name": "stonks_ohlcv_eoddata_daily",
        "subject_key": "all_series",
        "effective_date": date(2026, 7, 16),
        "run_type": "cli",
        "status": "started",
        "runner": "pytest",
    }
    values.update(overrides)
    return RunContext(**values)


def _config(**overrides: object) -> OHLCVConfig:
    values: dict[str, object] = {
        "eoddata_credentials": EODDataCredentials(api_key=SECRET),
    }
    values.update(overrides)
    return OHLCVConfig(**values)


def _store(tmp_path: Path) -> tuple[ObjectStore, FakeObjectRepository]:
    repository = FakeObjectRepository(tmp_path)
    return ObjectStore(repository), repository


def _json_response(body: bytes) -> EODDataHTTPResponse:
    return EODDataHTTPResponse(
        status_code=200,
        body=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )


def test_acquires_six_objects_in_contract_order_with_secret_safe_metadata(
    tmp_path: Path,
) -> None:
    object_store, repository = _store(tmp_path)
    calls: list[dict[str, object]] = []
    sleeps: list[float] = []

    def transport(**request: object) -> EODDataHTTPResponse:
        calls.append(request)
        url = request["url"]
        assert isinstance(url, str)
        body = b'[{"code":"EMPIRE"}]' if "/Symbol/" in url else b"[]"
        return _json_response(body)

    acquired = acquire_eoddata_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(),
        transport=transport,
        sleep=sleeps.append,
    )

    expected_urls = [
        "https://api.eoddata.com/Symbol/List/NYSE",
        "https://api.eoddata.com/Symbol/List/NASDAQ",
        "https://api.eoddata.com/Symbol/List/AMEX",
        "https://api.eoddata.com/Quote/List/NYSE",
        "https://api.eoddata.com/Quote/List/NASDAQ",
        "https://api.eoddata.com/Quote/List/AMEX",
    ]
    assert [call["url"] for call in calls] == expected_urls
    assert sleeps == [2.0] * 5
    assert [item.source_code for item in acquired] == [
        EODDATA_SYMBOL_LIST_SOURCE.source_code,
        EODDATA_SYMBOL_LIST_SOURCE.source_code,
        EODDATA_SYMBOL_LIST_SOURCE.source_code,
        EODDATA_DAILY_SOURCE.source_code,
        EODDATA_DAILY_SOURCE.source_code,
        EODDATA_DAILY_SOURCE.source_code,
    ]
    assert [item.filename for item in acquired] == [
        "raw-nyse.json",
        "raw-nasdaq.json",
        "raw-amex.json",
        "raw-nyse.json",
        "raw-nasdaq.json",
        "raw-amex.json",
    ]
    for index, call in enumerate(calls):
        query = call["query"]
        assert isinstance(query, dict)
        assert query["apiKey"] == SECRET
        if index < 3:
            assert set(query) == {"apiKey"}
        else:
            assert query["DateStamp"] == "2026-07-16"
        assert call["timeout_seconds"] == 30.0

    assert len(repository.objects) == 6
    for index, item in enumerate(acquired):
        stored = repository.objects[item.object_id]
        exchange = ("NYSE", "NASDAQ", "AMEX")[index % 3]
        assert stored.metadata["market"] == exchange
        assert stored.metadata["http_status"] == 200
        assert stored.metadata["parser_version"] == "1.0.0"
        assert SECRET not in repr(stored.metadata)
        assert SECRET not in stored.object_key
        assert SECRET not in stored.filename
        expected_body = b'[{"code":"EMPIRE"}]' if index < 3 else b"[]"
        assert item.size_bytes == len(expected_body)
        assert item.checksum_sha256 == hashlib.sha256(expected_body).hexdigest()
        assert object_store.get_bytes(item.object_id) == expected_body


@pytest.mark.parametrize(
    ("status_code", "headers", "expected_delay"),
    [
        (429, {"Retry-After": "120"}, 60.0),
        (503, {}, 2.0),
    ],
)
def test_retries_transient_http_failure_then_succeeds(
    tmp_path: Path,
    status_code: int,
    headers: dict[str, str],
    expected_delay: float,
) -> None:
    object_store, repository = _store(tmp_path)
    calls = 0
    sleeps: list[float] = []

    def transport(**request: object) -> EODDataHTTPResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return EODDataHTTPResponse(
                status_code=status_code,
                body=b"transient provider response",
                headers=headers,
            )
        url = request["url"]
        assert isinstance(url, str)
        return _json_response(b"[{}]" if "/Symbol/" in url else b"[]")

    acquired = acquire_eoddata_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(max_retries=1),
        transport=transport,
        sleep=sleeps.append,
    )

    assert len(acquired) == 6
    assert len(repository.objects) == 6
    assert calls == 7
    assert sleeps == [expected_delay, *([2.0] * 5)]


def test_non_retryable_failure_retains_prior_raw_objects(tmp_path: Path) -> None:
    object_store, repository = _store(tmp_path)
    calls: list[str] = []

    def transport(**request: object) -> EODDataHTTPResponse:
        url = request["url"]
        assert isinstance(url, str)
        calls.append(url)
        if url.endswith("/Symbol/List/AMEX"):
            return EODDataHTTPResponse(status_code=401, body=SECRET.encode())
        return _json_response(b"[{}]")

    with pytest.raises(
        OHLCVAcquisitionError,
        match="Symbol List for AMEX returned HTTP 401",
    ) as caught:
        acquire_eoddata_objects(
            object_store=object_store,
            run_context=_run_context(),
            config=_config(max_retries=3),
            transport=transport,
            sleep=lambda _seconds: None,
        )

    assert len(calls) == 3
    assert len(repository.objects) == 2
    assert caught.value.market == "AMEX"
    assert caught.value.source_code == "eoddata_symbol_list"
    assert SECRET not in str(caught.value)


def test_transport_failure_is_bounded_and_secret_safe(tmp_path: Path) -> None:
    object_store, repository = _store(tmp_path)
    calls = 0
    sleeps: list[float] = []

    def transport(**_request: object) -> EODDataHTTPResponse:
        nonlocal calls
        calls += 1
        raise RuntimeError(f"failed request with {SECRET}")

    with pytest.raises(OHLCVAcquisitionError) as caught:
        acquire_eoddata_objects(
            object_store=object_store,
            run_context=_run_context(),
            config=_config(max_retries=2),
            transport=transport,
            sleep=sleeps.append,
        )

    formatted = "".join(
        traceback.format_exception(
            type(caught.value),
            caught.value,
            caught.value.__traceback__,
        )
    )
    assert calls == 3
    assert sleeps == [2.0, 4.0]
    assert len(repository.objects) == 0
    assert SECRET not in formatted
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_json_response(b"not-json"), "invalid JSON"),
        (_json_response(b'{"code":"EMPIRE"}'), "non-array JSON"),
        (_json_response(b"[]"), "empty required payload"),
        (
            EODDataHTTPResponse(
                status_code=200,
                body=b"[{}]",
                headers={"Content-Type": "text/html"},
            ),
            "non-JSON content type",
        ),
    ],
)
def test_rejects_invalid_symbol_content_before_storage(
    tmp_path: Path,
    response: EODDataHTTPResponse,
    message: str,
) -> None:
    object_store, repository = _store(tmp_path)

    with pytest.raises(OHLCVAcquisitionError, match=message):
        acquire_eoddata_objects(
            object_store=object_store,
            run_context=_run_context(),
            config=_config(max_retries=0),
            transport=lambda **_request: response,
            sleep=lambda _seconds: None,
        )

    assert len(repository.objects) == 0


def test_wraps_object_storage_failure_without_exposing_secret() -> None:
    class FailingObjectStore:
        def put_bytes(self, **_values: object) -> StoredObject:
            raise RuntimeError(f"object storage exposed {SECRET}")

    with pytest.raises(OHLCVAcquisitionError) as caught:
        acquire_eoddata_objects(
            object_store=FailingObjectStore(),  # type: ignore[arg-type]
            run_context=_run_context(),
            config=_config(max_retries=0),
            transport=lambda **_request: _json_response(b"[{}]"),
            sleep=lambda _seconds: None,
        )

    assert "raw-object storage failed" in str(caught.value)
    assert SECRET not in str(caught.value)
    assert caught.value.__cause__ is None
