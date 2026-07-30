from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from empire_core import ObjectStore, RunContext, StorageRoot, StoredObject
from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.exceptions import OHLCVAcquisitionError
from empire_stonks_ohlcv.yahoo import (
    YAHOO_CONTENT_TYPE,
    YahooAcquisitionRequest,
    YahooAcquisitionStatus,
    YahooFailureReason,
    YahooHTTPResponse,
    YahooListingTarget,
    YahooRequestMode,
    YahooTransportError,
    acquire_yahoo_objects,
)


RUN_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
LISTING_ID = UUID("11111111-2222-4333-8444-555555555555")
SECOND_LISTING_ID = UUID("22222222-3333-4444-8555-666666666666")
THIRD_LISTING_ID = UUID("33333333-4444-4555-8666-777777777777")
STORED_AT = datetime(2026, 7, 30, 15, 30, tzinfo=UTC)
SECRET = "provider-body-secret"


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
        "job_name": "stonks_ohlcv_yahoo",
        "subject_key": "selected_series",
        "effective_date": date(2026, 7, 29),
        "run_type": "cli",
        "status": "started",
        "runner": "pytest",
    }
    values.update(overrides)
    return RunContext(**values)


def _store(tmp_path: Path) -> tuple[ObjectStore, FakeObjectRepository]:
    repository = FakeObjectRepository(tmp_path)
    return ObjectStore(repository), repository


def _target(
    *,
    listing_id: UUID = LISTING_ID,
    ticker: str = "SPX",
    yahoo_ticker: str = "^GSPC",
) -> YahooListingTarget:
    return YahooListingTarget(
        provider_listing_id=listing_id,
        ticker=ticker,
        yahoo_ticker=yahoo_ticker,
    )


def _request(
    *,
    listing: YahooListingTarget | None = None,
    start_date: date = date(2026, 7, 1),
    end_date_exclusive: date = date(2026, 7, 4),
    mode: YahooRequestMode = YahooRequestMode.DAILY,
) -> YahooAcquisitionRequest:
    return YahooAcquisitionRequest(
        listing=listing or _target(),
        start_date=start_date,
        end_date_exclusive=end_date_exclusive,
        mode=mode,
    )


def _chart_body(
    symbol: str = "^GSPC",
    timestamps: list[int] | None = None,
) -> bytes:
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": symbol},
                    "timestamp": [1751385600]
                    if timestamps is None
                    else timestamps,
                }
            ],
            "error": None,
        }
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def _response(
    body: bytes | None = None,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> YahooHTTPResponse:
    return YahooHTTPResponse(
        status_code=status,
        body=_chart_body() if body is None else body,
        headers=(
            {"Content-Type": "application/json; charset=utf-8"}
            if headers is None
            else headers
        ),
    )


def _config(**overrides: object) -> OHLCVConfig:
    values: dict[str, object] = {
        "yahoo_request_delay_seconds": 0,
        "yahoo_request_jitter_min_seconds": 0,
        "yahoo_request_jitter_max_seconds": 0,
        "yahoo_failure_cooldown_min_seconds": 0,
        "yahoo_failure_cooldown_max_seconds": 0,
    }
    values.update(overrides)
    return OHLCVConfig(**values)


def test_stores_exact_guarded_request_and_safe_identity_metadata(
    tmp_path: Path,
) -> None:
    object_store, repository = _store(tmp_path)
    calls: list[dict[str, object]] = []

    def transport(**values: object) -> YahooHTTPResponse:
        calls.append(values)
        return _response()

    result = acquire_yahoo_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(),
        requests=(_request(),),
        transport=transport,
        sleep=lambda _: None,
        random_uniform=lambda minimum, _maximum: minimum,
        clock=lambda: STORED_AT,
    )

    assert result.stored_count == 1
    assert result.missing_count == 0
    assert result.failed_count == 0
    assert len(calls) == 1
    assert calls[0] == {
        "url": "https://query2.finance.yahoo.com/v8/finance/chart/%5EGSPC",
        "query": {
            "interval": "1d",
            "includePrePost": "false",
            "events": "div,splits,capitalGains",
            "period1": "1782864000",
            "period2": "1783123200",
        },
        "timeout_seconds": 30.0,
    }

    acquired = result.stored_objects[0]
    stored = repository.objects[acquired.object_id]
    assert acquired.filename == (
        "raw-11111111-2222-4333-8444-555555555555-"
        "2026-07-01-2026-07-04.json"
    )
    assert acquired.checksum_sha256 == hashlib.sha256(_chart_body()).hexdigest()
    assert stored.metadata == {
        "schema_version": 1,
        "provider_code": "YAHOO",
        "source_code": "yahoo_daily",
        "effective_date": "2026-07-29",
        "acquired_at": "2026-07-30T15:30:00+00:00",
        "retention_days": 7,
        "parser_version": "1.0.0",
        "http_status": 200,
        "market": "XIDX",
        "provider_listing_id": str(LISTING_ID),
        "ticker": "SPX",
        "request_start_date": "2026-07-01",
        "request_end_date_exclusive": "2026-07-04",
        "request_mode": "daily",
    }
    assert object_store.get_bytes(acquired.object_id) == _chart_body()
    assert "^GSPC" not in acquired.filename
    assert "^GSPC" not in repr(stored.metadata)


def test_backfill_chunks_are_ascending_bounded_and_paced(tmp_path: Path) -> None:
    object_store, _ = _store(tmp_path)
    calls: list[dict[str, object]] = []
    sleeps: list[float] = []

    def transport(**values: object) -> YahooHTTPResponse:
        calls.append(values)
        return _response()

    result = acquire_yahoo_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(
            yahoo_backfill_chunk_days=10,
            yahoo_request_delay_seconds=2,
            yahoo_request_jitter_min_seconds=1,
            yahoo_request_jitter_max_seconds=1,
        ),
        requests=(
            _request(
                start_date=date(2026, 1, 1),
                end_date_exclusive=date(2026, 1, 26),
                mode=YahooRequestMode.BACKFILL,
            ),
        ),
        transport=transport,
        sleep=sleeps.append,
        random_uniform=lambda minimum, _maximum: minimum,
        clock=lambda: STORED_AT,
    )

    assert result.stored_count == 3
    assert [item.request.day_count for item in result.outcomes] == [10, 10, 5]
    assert [
        (
            item.request.start_date,
            item.request.end_date_exclusive,
        )
        for item in result.outcomes
    ] == [
        (date(2026, 1, 1), date(2026, 1, 11)),
        (date(2026, 1, 11), date(2026, 1, 21)),
        (date(2026, 1, 21), date(2026, 1, 26)),
    ]
    assert sleeps == [3.0, 3.0]
    assert [
        (
            call["query"]["period1"],  # type: ignore[index]
            call["query"]["period2"],  # type: ignore[index]
        )
        for call in calls
    ] == [
        ("1767225600", "1768089600"),
        ("1768089600", "1768953600"),
        ("1768953600", "1769385600"),
    ]


def test_daily_request_cannot_exceed_chunk_bound(tmp_path: Path) -> None:
    object_store, _ = _store(tmp_path)

    with pytest.raises(OHLCVAcquisitionError, match="exceeds"):
        acquire_yahoo_objects(
            object_store=object_store,
            run_context=_run_context(),
            config=_config(yahoo_backfill_chunk_days=2),
            requests=(_request(),),
            transport=lambda **_: pytest.fail("transport should not run"),
            sleep=lambda _: None,
        )


def test_pre_epoch_request_boundaries_are_exact_and_exclusive(
    tmp_path: Path,
) -> None:
    object_store, _ = _store(tmp_path)
    calls: list[dict[str, object]] = []

    def transport(**values: object) -> YahooHTTPResponse:
        calls.append(values)
        return _response()

    acquire_yahoo_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(),
        requests=(
            _request(
                start_date=date(1965, 1, 1),
                end_date_exclusive=date(1965, 1, 2),
                mode=YahooRequestMode.BACKFILL,
            ),
        ),
        transport=transport,
        sleep=lambda _: None,
        clock=lambda: STORED_AT,
    )

    query = calls[0]["query"]
    assert isinstance(query, Mapping)
    assert query["period1"] == "-157766400"
    assert query["period2"] == "-157680000"


@pytest.mark.parametrize("status_code", [408, 425, 429, 500, 503])
def test_retries_contract_http_status_then_succeeds(
    tmp_path: Path,
    status_code: int,
) -> None:
    object_store, _ = _store(tmp_path)
    calls = 0
    sleeps: list[float] = []

    def transport(**_: object) -> YahooHTTPResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _response(
                b"rate limited",
                status=status_code,
                headers={"Retry-After": "120"},
            )
        return _response()

    result = acquire_yahoo_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(max_retries=1),
        requests=(_request(),),
        transport=transport,
        sleep=sleeps.append,
        random_uniform=lambda minimum, _maximum: minimum,
        clock=lambda: STORED_AT,
    )

    assert result.stored_count == 1
    assert result.outcomes[0].attempts == 2
    assert calls == 2
    assert sleeps == [60.0]


def test_transient_transport_retry_uses_exponential_jitter(
    tmp_path: Path,
) -> None:
    object_store, _ = _store(tmp_path)
    calls = 0
    sleeps: list[float] = []

    def transport(**_: object) -> YahooHTTPResponse:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise YahooTransportError(f"transient {SECRET}")
        return _response()

    result = acquire_yahoo_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(
            max_retries=2,
            yahoo_request_jitter_min_seconds=3,
            yahoo_request_jitter_max_seconds=3,
        ),
        requests=(_request(),),
        transport=transport,
        sleep=sleeps.append,
        random_uniform=lambda minimum, _maximum: minimum,
        clock=lambda: STORED_AT,
    )

    assert result.stored_count == 1
    assert result.outcomes[0].attempts == 3
    assert sleeps == [4.0, 5.0]
    assert SECRET not in repr(result.to_safe_dict())


def test_nonretryable_http_failure_is_safe_and_not_stored(
    tmp_path: Path,
) -> None:
    object_store, repository = _store(tmp_path)

    result = acquire_yahoo_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(max_retries=3),
        requests=(_request(),),
        transport=lambda **_: _response(SECRET.encode(), status=401),
        sleep=lambda _: pytest.fail("nonretryable response must not sleep"),
    )

    outcome = result.outcomes[0]
    assert outcome.status is YahooAcquisitionStatus.FAILED
    assert outcome.failure_reason is YahooFailureReason.HTTP
    assert outcome.http_status == 401
    assert outcome.attempts == 1
    assert outcome.acquired_object is None
    assert repository.objects == {}
    assert SECRET not in repr(result.to_safe_dict())


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (
            _response(
                b"<html>challenge</html>",
                headers={"Content-Type": "text/html"},
            ),
            YahooFailureReason.CONTENT_TYPE,
        ),
        (_response(b""), YahooFailureReason.EMPTY_BODY),
        (_response(b"{not json"), YahooFailureReason.INVALID_JSON),
        (_response(b'{"wrong":{}}'), YahooFailureReason.INVALID_CHART),
        (
            _response(
                json.dumps(
                    {
                        "chart": {
                            "result": None,
                            "error": {"description": SECRET},
                        }
                    }
                ).encode()
            ),
            YahooFailureReason.PROVIDER_ERROR,
        ),
        (_response(_chart_body("^WRONG")), YahooFailureReason.SYMBOL_MISMATCH),
    ],
)
def test_http_200_errors_are_stored_before_safe_classification(
    tmp_path: Path,
    response: YahooHTTPResponse,
    reason: YahooFailureReason,
) -> None:
    object_store, repository = _store(tmp_path)

    result = acquire_yahoo_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(),
        requests=(_request(),),
        transport=lambda **_: response,
        sleep=lambda _: None,
        clock=lambda: STORED_AT,
    )

    outcome = result.outcomes[0]
    assert outcome.status is YahooAcquisitionStatus.FAILED
    assert outcome.failure_reason is reason
    assert outcome.acquired_object is not None
    assert len(result.stored_objects) == 1
    assert len(repository.objects) == 1
    assert object_store.get_bytes(outcome.acquired_object.object_id) == response.body
    assert SECRET not in repr(result.to_safe_dict())


@pytest.mark.parametrize(
    "body",
    [
        b'{"chart":{"result":null,"error":null}}',
        b'{"chart":{"result":[],"error":null}}',
        _chart_body(timestamps=[]),
    ],
)
def test_daily_no_data_is_stored_missing_and_retryable(
    tmp_path: Path,
    body: bytes,
) -> None:
    object_store, _ = _store(tmp_path)

    result = acquire_yahoo_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(),
        requests=(_request(),),
        transport=lambda **_: _response(body),
        sleep=lambda _: None,
        clock=lambda: STORED_AT,
    )

    assert result.stored_count == 0
    assert result.missing_count == 1
    assert result.failed_count == 0
    assert len(result.stored_objects) == 1
    assert result.outcomes[0].failure_reason is None


def test_empty_backfill_is_a_stored_failure(tmp_path: Path) -> None:
    object_store, _ = _store(tmp_path)

    result = acquire_yahoo_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(),
        requests=(_request(mode=YahooRequestMode.BACKFILL),),
        transport=lambda **_: _response(
            b'{"chart":{"result":null,"error":null}}'
        ),
        sleep=lambda _: None,
        clock=lambda: STORED_AT,
    )

    assert result.failed_count == 1
    assert len(result.stored_objects) == 1
    assert (
        result.outcomes[0].failure_reason
        is YahooFailureReason.NO_BACKFILL_DATA
    )


def test_partial_listing_failure_retains_success_and_uses_cooldown(
    tmp_path: Path,
) -> None:
    object_store, repository = _store(tmp_path)
    sleeps: list[float] = []
    requests = (
        _request(),
        _request(
            listing=_target(
                listing_id=SECOND_LISTING_ID,
                ticker="DJI",
                yahoo_ticker="^DJI",
            )
        ),
        _request(
            listing=_target(
                listing_id=THIRD_LISTING_ID,
                ticker="NDX",
                yahoo_ticker="^NDX",
            )
        ),
    )

    def transport(**values: object) -> YahooHTTPResponse:
        url = values["url"]
        assert isinstance(url, str)
        if url.endswith("%5EDJI"):
            return _response(b"denied", status=403)
        if url.endswith("%5ENDX"):
            return _response(_chart_body("^NDX"))
        return _response()

    result = acquire_yahoo_objects(
        object_store=object_store,
        run_context=_run_context(),
        config=_config(
            yahoo_request_delay_seconds=10,
            yahoo_request_jitter_min_seconds=2,
            yahoo_request_jitter_max_seconds=2,
            yahoo_failure_cooldown_min_seconds=7,
            yahoo_failure_cooldown_max_seconds=7,
        ),
        requests=requests,
        transport=transport,
        sleep=sleeps.append,
        random_uniform=lambda minimum, _maximum: minimum,
        clock=lambda: STORED_AT,
    )

    assert [item.status for item in result.outcomes] == [
        YahooAcquisitionStatus.STORED,
        YahooAcquisitionStatus.FAILED,
        YahooAcquisitionStatus.STORED,
    ]
    assert result.stored_count == 2
    assert result.failed_count == 1
    assert len(repository.objects) == 2
    assert sleeps == [12.0, 7.0]


def test_raw_storage_failure_is_isolated_and_secret_safe() -> None:
    class FailingObjectStore:
        def put_bytes(self, **_: object) -> StoredObject:
            raise RuntimeError(f"storage leaked {SECRET}")

    result = acquire_yahoo_objects(
        object_store=FailingObjectStore(),  # type: ignore[arg-type]
        run_context=_run_context(),
        config=_config(),
        requests=(_request(),),
        transport=lambda **_: _response(),
        sleep=lambda _: None,
        clock=lambda: STORED_AT,
    )

    assert result.failed_count == 1
    assert result.outcomes[0].failure_reason is YahooFailureReason.RAW_STORAGE
    assert result.outcomes[0].acquired_object is None
    assert SECRET not in repr(result.to_safe_dict())


def test_models_reject_ambiguous_identity_and_date_bounds() -> None:
    with pytest.raises(ValueError, match="yahoo_ticker is required"):
        _target(yahoo_ticker=" ")
    with pytest.raises(ValueError, match="must be after"):
        _request(
            start_date=date(2026, 7, 1),
            end_date_exclusive=date(2026, 7, 1),
        )
    with pytest.raises(TypeError, match="YahooRequestMode"):
        YahooAcquisitionRequest(
            listing=_target(),
            start_date=date(2026, 7, 1),
            end_date_exclusive=date(2026, 7, 2),
            mode="daily",  # type: ignore[arg-type]
        )


def test_batch_rejects_duplicate_or_ambiguous_listing_identity(
    tmp_path: Path,
) -> None:
    object_store, _ = _store(tmp_path)

    with pytest.raises(OHLCVAcquisitionError, match="duplicated"):
        acquire_yahoo_objects(
            object_store=object_store,
            run_context=_run_context(),
            config=_config(),
            requests=(_request(), _request()),
            transport=lambda **_: pytest.fail("transport should not run"),
            sleep=lambda _: None,
        )

    with pytest.raises(OHLCVAcquisitionError, match="multiple provider"):
        acquire_yahoo_objects(
            object_store=object_store,
            run_context=_run_context(),
            config=_config(),
            requests=(
                _request(),
                _request(
                    listing=_target(
                        listing_id=SECOND_LISTING_ID,
                        ticker="OTHER",
                        yahoo_ticker="^GSPC",
                    )
                ),
            ),
            transport=lambda **_: pytest.fail("transport should not run"),
            sleep=lambda _: None,
        )


def test_response_normalizes_headers_to_immutable_lowercase_mapping() -> None:
    response = YahooHTTPResponse(
        status_code=200,
        body=b"{}",
        headers={"Retry-After": "3", "Content-Type": YAHOO_CONTENT_TYPE},
    )

    assert response.headers == {
        "retry-after": "3",
        "content-type": YAHOO_CONTENT_TYPE,
    }
    with pytest.raises(TypeError):
        response.headers["other"] = "value"  # type: ignore[index]
