"""Bounded Yahoo Chart acquisition for the controlled XIDX universe."""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from empire_core import ObjectStore, RunContext

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.exceptions import OHLCVAcquisitionError
from empire_stonks_ohlcv.object_store import Clock, store_raw_bytes
from empire_stonks_ohlcv.results import AcquiredObject
from empire_stonks_ohlcv.source_conventions import YAHOO_DAILY_SOURCE


YAHOO_PROVIDER_CODE = "YAHOO"
YAHOO_MARKET = "XIDX"
YAHOO_CONTENT_TYPE = "application/json"
YAHOO_USER_AGENT = "empire-stonks-ohlcv/0.1"

_RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, *range(500, 600)})
_MAX_RETRY_DELAY_SECONDS = 60.0
_MAX_TICKER_LENGTH = 64

Sleep = Callable[[float], None]
RandomUniform = Callable[[float, float], float]


class YahooRequestMode(StrEnum):
    """Supported bounded acquisition modes."""

    DAILY = "daily"
    BACKFILL = "backfill"


class YahooAcquisitionStatus(StrEnum):
    """Outcome of one concrete, already chunked request."""

    STORED = "stored"
    MISSING = "missing"
    FAILED = "failed"


class YahooFailureReason(StrEnum):
    """Secret-safe classifications for acquisition failures."""

    TRANSPORT = "transport"
    HTTP = "http"
    CONTENT_TYPE = "content_type"
    EMPTY_BODY = "empty_body"
    INVALID_JSON = "invalid_json"
    INVALID_CHART = "invalid_chart"
    PROVIDER_ERROR = "provider_error"
    SYMBOL_MISMATCH = "symbol_mismatch"
    NO_BACKFILL_DATA = "no_backfill_data"
    RAW_STORAGE = "raw_storage"


@dataclass(frozen=True)
class YahooHTTPResponse:
    """One transport response without its full request URL."""

    status_code: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status_code, bool) or not isinstance(
            self.status_code,
            int,
        ):
            raise TypeError("status_code must be an integer.")
        if not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be a valid HTTP status.")
        if not isinstance(self.body, bytes):
            raise TypeError("body must be bytes.")
        if not isinstance(self.headers, Mapping):
            raise TypeError("headers must be a mapping.")
        normalized: dict[str, str] = {}
        for key, value in self.headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("headers must contain string keys and values.")
            normalized[key.lower()] = value
        object.__setattr__(self, "headers", MappingProxyType(normalized))


class YahooHTTPTransport(Protocol):
    """Injected HTTP seam for one exact Yahoo Chart request."""

    def __call__(
        self,
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> YahooHTTPResponse: ...


class YahooTransportError(Exception):
    """Sanitized retryable error emitted by a Yahoo transport."""


@dataclass(frozen=True)
class YahooListingTarget:
    """One active seeded Yahoo listing and its exact request symbol."""

    provider_listing_id: UUID
    ticker: str
    yahoo_ticker: str

    def __post_init__(self) -> None:
        if not isinstance(self.provider_listing_id, UUID):
            raise TypeError("provider_listing_id must be a UUID.")
        _required_text("ticker", self.ticker, maximum=_MAX_TICKER_LENGTH)
        _required_text(
            "yahoo_ticker",
            self.yahoo_ticker,
            maximum=_MAX_TICKER_LENGTH,
        )


@dataclass(frozen=True)
class YahooAcquisitionRequest:
    """One caller-planned inclusive/exclusive listing range."""

    listing: YahooListingTarget
    start_date: date
    end_date_exclusive: date
    mode: YahooRequestMode

    def __post_init__(self) -> None:
        if not isinstance(self.listing, YahooListingTarget):
            raise TypeError("listing must be a YahooListingTarget.")
        _date_range(self.start_date, self.end_date_exclusive)
        if not isinstance(self.mode, YahooRequestMode):
            raise TypeError("mode must be a YahooRequestMode.")

    @property
    def day_count(self) -> int:
        """Return the number of calendar days in this half-open range."""

        return (self.end_date_exclusive - self.start_date).days


@dataclass(frozen=True)
class YahooAcquisitionOutcome:
    """Safe result for one concrete Yahoo request chunk."""

    request: YahooAcquisitionRequest
    status: YahooAcquisitionStatus
    attempts: int
    http_status: int | None = None
    acquired_object: AcquiredObject | None = None
    failure_reason: YahooFailureReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, YahooAcquisitionRequest):
            raise TypeError("request must be a YahooAcquisitionRequest.")
        if not isinstance(self.status, YahooAcquisitionStatus):
            raise TypeError("status must be a YahooAcquisitionStatus.")
        if (
            isinstance(self.attempts, bool)
            or not isinstance(self.attempts, int)
            or self.attempts <= 0
        ):
            raise ValueError("attempts must be a positive integer.")
        if self.http_status is not None and (
            isinstance(self.http_status, bool)
            or not isinstance(self.http_status, int)
            or not 100 <= self.http_status <= 599
        ):
            raise ValueError("http_status must be a valid HTTP status or None.")
        if self.acquired_object is not None and not isinstance(
            self.acquired_object,
            AcquiredObject,
        ):
            raise TypeError("acquired_object must be an AcquiredObject or None.")
        if self.failure_reason is not None and not isinstance(
            self.failure_reason,
            YahooFailureReason,
        ):
            raise TypeError("failure_reason must be a YahooFailureReason or None.")

        if self.status is YahooAcquisitionStatus.STORED:
            if self.acquired_object is None or self.failure_reason is not None:
                raise ValueError(
                    "STORED requires an object and forbids failure_reason."
                )
        elif self.status is YahooAcquisitionStatus.MISSING:
            if self.acquired_object is None or self.failure_reason is not None:
                raise ValueError(
                    "MISSING requires an object and forbids failure_reason."
                )
        elif self.failure_reason is None:
            raise ValueError("FAILED requires failure_reason.")

    def to_safe_dict(self) -> dict[str, str | int | None]:
        """Return safe outcome details without Yahoo body or URL content."""

        return {
            "provider_listing_id": str(
                self.request.listing.provider_listing_id
            ),
            "ticker": self.request.listing.ticker,
            "request_start_date": self.request.start_date.isoformat(),
            "request_end_date_exclusive": (
                self.request.end_date_exclusive.isoformat()
            ),
            "request_mode": self.request.mode.value,
            "status": self.status.value,
            "attempts": self.attempts,
            "http_status": self.http_status,
            "failure_reason": (
                None
                if self.failure_reason is None
                else self.failure_reason.value
            ),
            "object_id": (
                None
                if self.acquired_object is None
                else str(self.acquired_object.object_id)
            ),
        }


@dataclass(frozen=True)
class YahooAcquisitionResult:
    """Ordered outcomes for one bounded acquisition call."""

    outcomes: tuple[YahooAcquisitionOutcome, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.outcomes, tuple):
            raise TypeError("outcomes must be a tuple.")
        if any(
            not isinstance(item, YahooAcquisitionOutcome)
            for item in self.outcomes
        ):
            raise TypeError(
                "outcomes must contain YahooAcquisitionOutcome values."
            )

    @property
    def stored_objects(self) -> tuple[AcquiredObject, ...]:
        """Return every HTTP 200 body durably stored through Core."""

        return tuple(
            item.acquired_object
            for item in self.outcomes
            if item.acquired_object is not None
        )

    @property
    def stored_count(self) -> int:
        return sum(
            item.status is YahooAcquisitionStatus.STORED
            for item in self.outcomes
        )

    @property
    def missing_count(self) -> int:
        return sum(
            item.status is YahooAcquisitionStatus.MISSING
            for item in self.outcomes
        )

    @property
    def failed_count(self) -> int:
        return sum(
            item.status is YahooAcquisitionStatus.FAILED
            for item in self.outcomes
        )

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "stored": self.stored_count,
            "missing": self.missing_count,
            "failed": self.failed_count,
            "outcomes": [item.to_safe_dict() for item in self.outcomes],
        }


@dataclass(frozen=True)
class _ResponseClassification:
    status: YahooAcquisitionStatus
    failure_reason: YahooFailureReason | None = None


def acquire_yahoo_objects(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    requests: Iterable[YahooAcquisitionRequest],
    transport: YahooHTTPTransport | None = None,
    sleep: Sleep = time.sleep,
    random_uniform: RandomUniform = random.uniform,
    clock: Clock | None = None,
) -> YahooAcquisitionResult:
    """Acquire bounded Yahoo ranges serially while isolating chunk failures."""

    prepared = _validate_inputs(
        run_context=run_context,
        config=config,
        requests=requests,
        sleep=sleep,
        random_uniform=random_uniform,
        transport=transport,
        clock=clock,
    )
    request_transport = transport or _urllib_transport
    chunks = tuple(
        chunk
        for request in prepared
        for chunk in _chunk_request(request, config.yahoo_backfill_chunk_days)
    )
    _validate_request_identities(chunks)

    outcomes: list[YahooAcquisitionOutcome] = []
    previous_failed = False
    for index, request in enumerate(chunks):
        if index:
            if previous_failed:
                sleep(
                    _random_delay(
                        random_uniform,
                        config.yahoo_failure_cooldown_min_seconds,
                        config.yahoo_failure_cooldown_max_seconds,
                    )
                )
            else:
                sleep(
                    config.yahoo_request_delay_seconds
                    + _random_delay(
                        random_uniform,
                        config.yahoo_request_jitter_min_seconds,
                        config.yahoo_request_jitter_max_seconds,
                    )
                )

        outcome = _acquire_chunk(
            object_store=object_store,
            run_context=run_context,
            config=config,
            request=request,
            transport=request_transport,
            sleep=sleep,
            random_uniform=random_uniform,
            clock=clock,
        )
        outcomes.append(outcome)
        previous_failed = outcome.status is YahooAcquisitionStatus.FAILED

    return YahooAcquisitionResult(tuple(outcomes))


def _acquire_chunk(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    request: YahooAcquisitionRequest,
    transport: YahooHTTPTransport,
    sleep: Sleep,
    random_uniform: RandomUniform,
    clock: Clock | None,
) -> YahooAcquisitionOutcome:
    response, attempts, failure = _request_with_retries(
        transport=transport,
        url=_request_url(config.yahoo_base_url, request.listing.yahoo_ticker),
        query=_request_query(request),
        timeout_seconds=config.http_timeout_seconds,
        max_retries=config.max_retries,
        sleep=sleep,
        random_uniform=random_uniform,
        jitter_min=config.yahoo_request_jitter_min_seconds,
        jitter_max=config.yahoo_request_jitter_max_seconds,
    )
    if response is None:
        return YahooAcquisitionOutcome(
            request=request,
            status=YahooAcquisitionStatus.FAILED,
            attempts=attempts,
            http_status=(
                None if failure is None else failure[1]
            ),
            failure_reason=(
                YahooFailureReason.TRANSPORT
                if failure is None
                else failure[0]
            ),
        )

    try:
        store_arguments: dict[str, object] = {}
        if clock is not None:
            store_arguments["clock"] = clock
        acquired = store_raw_bytes(
            object_store=object_store,
            run_context=run_context,
            config=config,
            provider_code=YAHOO_PROVIDER_CODE,
            source_code=YAHOO_DAILY_SOURCE.source_code,
            format_suffix="json",
            data=response.body,
            content_type=YAHOO_CONTENT_TYPE,
            part_key=_part_key(request),
            parser_version=YAHOO_DAILY_SOURCE.parser_version,
            provider_metadata={
                "http_status": response.status_code,
                "market": YAHOO_MARKET,
                "provider_listing_id": str(
                    request.listing.provider_listing_id
                ).lower(),
                "ticker": request.listing.ticker,
                "request_start_date": request.start_date.isoformat(),
                "request_end_date_exclusive": (
                    request.end_date_exclusive.isoformat()
                ),
                "request_mode": request.mode.value,
            },
            **store_arguments,
        )
    except Exception:
        return YahooAcquisitionOutcome(
            request=request,
            status=YahooAcquisitionStatus.FAILED,
            attempts=attempts,
            http_status=response.status_code,
            failure_reason=YahooFailureReason.RAW_STORAGE,
        )

    classification = _classify_response(response=response, request=request)
    return YahooAcquisitionOutcome(
        request=request,
        status=classification.status,
        attempts=attempts,
        http_status=response.status_code,
        acquired_object=acquired,
        failure_reason=classification.failure_reason,
    )


def _request_with_retries(
    *,
    transport: YahooHTTPTransport,
    url: str,
    query: Mapping[str, str],
    timeout_seconds: float,
    max_retries: int,
    sleep: Sleep,
    random_uniform: RandomUniform,
    jitter_min: float,
    jitter_max: float,
) -> tuple[
    YahooHTTPResponse | None,
    int,
    tuple[YahooFailureReason, int | None] | None,
]:
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            response = transport(
                url=url,
                query=query,
                timeout_seconds=timeout_seconds,
            )
        except (YahooTransportError, TimeoutError, ConnectionError, OSError):
            if attempt < max_retries:
                sleep(
                    _retry_delay(
                        attempt=attempt,
                        headers={},
                        random_uniform=random_uniform,
                        jitter_min=jitter_min,
                        jitter_max=jitter_max,
                    )
                )
                continue
            return None, attempt + 1, None
        except Exception:
            return None, attempt + 1, None

        if not isinstance(response, YahooHTTPResponse):
            return None, attempt + 1, None
        if response.status_code == 200:
            return response, attempt + 1, None
        if (
            response.status_code in _RETRYABLE_HTTP_STATUSES
            and attempt < max_retries
        ):
            sleep(
                _retry_delay(
                    attempt=attempt,
                    headers=response.headers,
                    random_uniform=random_uniform,
                    jitter_min=jitter_min,
                    jitter_max=jitter_max,
                )
            )
            continue
        return (
            None,
            attempt + 1,
            (YahooFailureReason.HTTP, response.status_code),
        )
    raise AssertionError("bounded Yahoo retry loop did not return")


def _classify_response(
    *,
    response: YahooHTTPResponse,
    request: YahooAcquisitionRequest,
) -> _ResponseClassification:
    content_type = response.headers.get("content-type")
    if content_type is not None:
        media_type = content_type.partition(";")[0].strip().lower()
        if media_type != YAHOO_CONTENT_TYPE and not media_type.endswith("+json"):
            return _ResponseClassification(
                YahooAcquisitionStatus.FAILED,
                YahooFailureReason.CONTENT_TYPE,
            )
    if not response.body:
        return _ResponseClassification(
            YahooAcquisitionStatus.FAILED,
            YahooFailureReason.EMPTY_BODY,
        )
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _ResponseClassification(
            YahooAcquisitionStatus.FAILED,
            YahooFailureReason.INVALID_JSON,
        )
    if not isinstance(payload, dict):
        return _invalid_chart()
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        return _invalid_chart()
    if "error" not in chart or "result" not in chart:
        return _invalid_chart()
    if chart.get("error") is not None:
        return _ResponseClassification(
            YahooAcquisitionStatus.FAILED,
            YahooFailureReason.PROVIDER_ERROR,
        )
    result = chart.get("result")
    if result is None or result == []:
        if request.mode is YahooRequestMode.BACKFILL:
            return _ResponseClassification(
                YahooAcquisitionStatus.FAILED,
                YahooFailureReason.NO_BACKFILL_DATA,
            )
        return _ResponseClassification(YahooAcquisitionStatus.MISSING)
    if not isinstance(result, list) or len(result) != 1:
        return _invalid_chart()
    series = result[0]
    if not isinstance(series, dict):
        return _invalid_chart()
    meta = series.get("meta")
    timestamps = series.get("timestamp")
    if not isinstance(meta, dict) or not isinstance(timestamps, list):
        return _invalid_chart()
    if meta.get("symbol") != request.listing.yahoo_ticker:
        return _ResponseClassification(
            YahooAcquisitionStatus.FAILED,
            YahooFailureReason.SYMBOL_MISMATCH,
        )
    if not timestamps:
        if request.mode is YahooRequestMode.BACKFILL:
            return _ResponseClassification(
                YahooAcquisitionStatus.FAILED,
                YahooFailureReason.NO_BACKFILL_DATA,
            )
        return _ResponseClassification(YahooAcquisitionStatus.MISSING)
    return _ResponseClassification(YahooAcquisitionStatus.STORED)


def _invalid_chart() -> _ResponseClassification:
    return _ResponseClassification(
        YahooAcquisitionStatus.FAILED,
        YahooFailureReason.INVALID_CHART,
    )


def _chunk_request(
    request: YahooAcquisitionRequest,
    chunk_days: int,
) -> tuple[YahooAcquisitionRequest, ...]:
    if request.mode is YahooRequestMode.DAILY:
        if request.day_count > chunk_days:
            raise OHLCVAcquisitionError(
                "Yahoo daily request exceeds the configured chunk bound.",
                market=YAHOO_MARKET,
                source_code=YAHOO_DAILY_SOURCE.source_code,
            )
        return (request,)

    chunks: list[YahooAcquisitionRequest] = []
    cursor = request.start_date
    while cursor < request.end_date_exclusive:
        remaining = (request.end_date_exclusive - cursor).days
        chunk_end = cursor + timedelta(days=min(remaining, chunk_days))
        chunks.append(
            YahooAcquisitionRequest(
                listing=request.listing,
                start_date=cursor,
                end_date_exclusive=chunk_end,
                mode=request.mode,
            )
        )
        cursor = chunk_end
    return tuple(chunks)


def _request_url(base_url: str, yahoo_ticker: str) -> str:
    encoded_symbol = quote(yahoo_ticker, safe="")
    return f"{base_url}/v8/finance/chart/{encoded_symbol}"


def _request_query(request: YahooAcquisitionRequest) -> Mapping[str, str]:
    return MappingProxyType(
        {
            "interval": "1d",
            "includePrePost": "false",
            "events": "div,splits,capitalGains",
            "period1": str(_unix_seconds(request.start_date)),
            "period2": str(_unix_seconds(request.end_date_exclusive)),
        }
    )


def _unix_seconds(value: date) -> int:
    return (value - date(1970, 1, 1)).days * 24 * 60 * 60


def _part_key(request: YahooAcquisitionRequest) -> str:
    return "-".join(
        (
            str(request.listing.provider_listing_id).lower(),
            request.start_date.isoformat(),
            request.end_date_exclusive.isoformat(),
        )
    )


def _retry_delay(
    *,
    attempt: int,
    headers: Mapping[str, str],
    random_uniform: RandomUniform,
    jitter_min: float,
    jitter_max: float,
) -> float:
    retry_after = headers.get("retry-after")
    if retry_after is not None:
        try:
            delay = float(retry_after)
        except ValueError:
            delay = -1.0
        if isfinite(delay) and delay >= 0:
            return min(delay, _MAX_RETRY_DELAY_SECONDS)
    exponential = float(2**attempt)
    return min(
        exponential
        + _random_delay(random_uniform, jitter_min, jitter_max),
        _MAX_RETRY_DELAY_SECONDS,
    )


def _random_delay(
    random_uniform: RandomUniform,
    minimum: float,
    maximum: float,
) -> float:
    value = random_uniform(minimum, maximum)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise OHLCVAcquisitionError(
            "random_uniform returned a value outside its requested bounds.",
            market=YAHOO_MARKET,
            source_code=YAHOO_DAILY_SOURCE.source_code,
        )
    return float(value)


def _validate_inputs(
    *,
    run_context: RunContext,
    config: OHLCVConfig,
    requests: Iterable[YahooAcquisitionRequest],
    sleep: Sleep,
    random_uniform: RandomUniform,
    transport: YahooHTTPTransport | None,
    clock: Clock | None,
) -> tuple[YahooAcquisitionRequest, ...]:
    if not isinstance(run_context, RunContext):
        raise TypeError("run_context must be a Core RunContext.")
    if run_context.domain != "stonks" or run_context.status != "started":
        raise ValueError("run_context must be an active stonks run.")
    if run_context.effective_date is None:
        raise ValueError("run_context effective_date is required.")
    if not isinstance(config, OHLCVConfig):
        raise TypeError("config must be an OHLCVConfig.")
    if isinstance(requests, (str, bytes)):
        raise TypeError("requests must be an iterable of Yahoo requests.")
    try:
        prepared = tuple(requests)
    except TypeError as exc:
        raise TypeError(
            "requests must be an iterable of Yahoo requests."
        ) from exc
    if any(not isinstance(item, YahooAcquisitionRequest) for item in prepared):
        raise TypeError("requests must contain YahooAcquisitionRequest values.")
    _validate_request_identities(prepared)
    if not callable(sleep):
        raise TypeError("sleep must be callable.")
    if not callable(random_uniform):
        raise TypeError("random_uniform must be callable.")
    if transport is not None and not callable(transport):
        raise TypeError("transport must be callable.")
    if clock is not None and not callable(clock):
        raise TypeError("clock must be callable.")
    return prepared


def _validate_request_identities(
    requests: tuple[YahooAcquisitionRequest, ...],
) -> None:
    listings_by_id: dict[UUID, tuple[str, str]] = {}
    ids_by_yahoo_ticker: dict[str, UUID] = {}
    ranges: set[tuple[UUID, date, date]] = set()
    for request in requests:
        listing = request.listing
        identity = (listing.ticker, listing.yahoo_ticker)
        prior_identity = listings_by_id.setdefault(
            listing.provider_listing_id,
            identity,
        )
        if prior_identity != identity:
            raise OHLCVAcquisitionError(
                "Yahoo provider listing has conflicting request identity.",
                market=YAHOO_MARKET,
                source_code=YAHOO_DAILY_SOURCE.source_code,
            )
        prior_id = ids_by_yahoo_ticker.setdefault(
            listing.yahoo_ticker,
            listing.provider_listing_id,
        )
        if prior_id != listing.provider_listing_id:
            raise OHLCVAcquisitionError(
                "Yahoo request symbol identifies multiple provider listings.",
                market=YAHOO_MARKET,
                source_code=YAHOO_DAILY_SOURCE.source_code,
            )
        range_identity = (
            listing.provider_listing_id,
            request.start_date,
            request.end_date_exclusive,
        )
        if range_identity in ranges:
            raise OHLCVAcquisitionError(
                "Yahoo acquisition request is duplicated.",
                market=YAHOO_MARKET,
                source_code=YAHOO_DAILY_SOURCE.source_code,
            )
        ranges.add(range_identity)


def _required_text(field_name: str, value: object, *, maximum: int) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value or not value.strip():
        raise ValueError(f"{field_name} is required.")
    if value != value.strip():
        raise ValueError(
            f"{field_name} must not contain leading or trailing whitespace."
        )
    if len(value) > maximum:
        raise ValueError(f"{field_name} must be at most {maximum} characters.")


def _date_range(start_date: object, end_date_exclusive: object) -> None:
    if type(start_date) is not date:
        raise TypeError("start_date must be a date.")
    if type(end_date_exclusive) is not date:
        raise TypeError("end_date_exclusive must be a date.")
    if end_date_exclusive <= start_date:
        raise ValueError("end_date_exclusive must be after start_date.")


def _urllib_transport(
    *,
    url: str,
    query: Mapping[str, str],
    timeout_seconds: float,
) -> YahooHTTPResponse:
    request_url = f"{url}?{urlencode(query)}"
    request = Request(
        request_url,
        headers={
            "Accept": YAHOO_CONTENT_TYPE,
            "User-Agent": YAHOO_USER_AGENT,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return YahooHTTPResponse(
                status_code=response.status,
                body=response.read(),
                headers=dict(response.headers.items()),
            )
    except HTTPError as exc:
        return YahooHTTPResponse(
            status_code=exc.code,
            body=exc.read(),
            headers=dict(exc.headers.items()) if exc.headers else {},
        )
    except (TimeoutError, URLError, OSError):
        raise YahooTransportError("Yahoo transport request failed.") from None
