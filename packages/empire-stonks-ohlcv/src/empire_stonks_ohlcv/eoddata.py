"""EODData nightly Symbol List and Quote List acquisition."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from empire_core import ObjectStore, RunContext

from empire_stonks_ohlcv.config import DEFAULT_EODDATA_EXCHANGES, OHLCVConfig
from empire_stonks_ohlcv.exceptions import OHLCVAcquisitionError
from empire_stonks_ohlcv.object_store import store_raw_bytes
from empire_stonks_ohlcv.results import AcquiredObject
from empire_stonks_ohlcv.source_conventions import (
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
)


EODDATA_PROVIDER_CODE = "EODDATA"
EODDATA_CONTENT_TYPE = "application/json"
EODDATA_USER_AGENT = "empire-stonks-ohlcv/0.1"

_RETRYABLE_HTTP_STATUSES = frozenset({429, *range(500, 600)})
_DEFAULT_RETRY_BACKOFF_SECONDS = 2.0
_MAX_RETRY_DELAY_SECONDS = 60.0

Sleep = Callable[[float], None]
RetrySink = Callable[["EODDataRetryEvent"], None]


@dataclass(frozen=True)
class EODDataRetryEvent:
    """One secret-safe retry performed for an exchange partition."""

    source_code: str
    exchange: str
    retry_number: int
    delay_seconds: float
    reason: str

    def __post_init__(self) -> None:
        if self.source_code not in {
            EODDATA_SYMBOL_LIST_SOURCE.source_code,
            EODDATA_DAILY_SOURCE.source_code,
        }:
            raise ValueError("source_code is not an EODData source.")
        if self.exchange not in DEFAULT_EODDATA_EXCHANGES:
            raise ValueError("exchange is not a configured EODData exchange.")
        if (
            isinstance(self.retry_number, bool)
            or not isinstance(self.retry_number, int)
            or self.retry_number < 1
        ):
            raise ValueError("retry_number must be a positive integer.")
        if (
            isinstance(self.delay_seconds, bool)
            or not isinstance(self.delay_seconds, (int, float))
            or not isfinite(self.delay_seconds)
            or self.delay_seconds < 0
        ):
            raise ValueError("delay_seconds must be finite and non-negative.")
        if self.reason not in {"transport", "http_429", "http_5xx"}:
            raise ValueError("reason is not a supported retry reason.")


@dataclass(frozen=True)
class EODDataHTTPResponse:
    """One transport response without a credential-bearing request URL."""

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


class EODDataHTTPTransport(Protocol):
    """Injected HTTP seam that keeps credentials separate from the base URL."""

    def __call__(
        self,
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> EODDataHTTPResponse: ...


@dataclass(frozen=True)
class _RequestSpec:
    source_code: str
    parser_version: str
    exchange: str
    endpoint_name: str
    path: str
    allow_empty: bool


class _TransportFailure(Exception):
    """Internal sanitized marker for a retryable urllib failure."""


def acquire_eoddata_objects(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    transport: EODDataHTTPTransport | None = None,
    sleep: Sleep = time.sleep,
    exchanges: tuple[str, ...] | None = None,
    retry_sink: RetrySink | None = None,
) -> tuple[AcquiredObject, ...]:
    """Acquire and store an ordered exchange subset, listing source first."""

    _validate_inputs(run_context=run_context, config=config, sleep=sleep)
    selected_exchanges = _selected_exchanges(exchanges)
    if retry_sink is not None and not callable(retry_sink):
        raise TypeError("retry_sink must be callable.")
    credentials = config.require_eoddata_credentials()
    request_transport = transport or _urllib_transport
    if not callable(request_transport):
        raise TypeError("transport must be callable.")

    acquired: list[AcquiredObject] = []
    for request_index, spec in enumerate(
        _request_specs(exchanges=selected_exchanges)
    ):
        if request_index:
            sleep(config.eoddata_request_delay_seconds)
        query = {"apiKey": credentials.api_key}
        if spec.source_code == EODDATA_DAILY_SOURCE.source_code:
            effective_date = run_context.effective_date
            assert effective_date is not None
            query["DateStamp"] = effective_date.isoformat()

        response = _request_with_retries(
            transport=request_transport,
            url=f"{config.eoddata_base_url}{spec.path}",
            query=query,
            timeout_seconds=config.http_timeout_seconds,
            max_retries=config.max_retries,
            sleep=sleep,
            spec=spec,
            retry_sink=retry_sink,
        )
        _validate_json_array(response=response, spec=spec)
        try:
            stored = store_raw_bytes(
                object_store=object_store,
                run_context=run_context,
                config=config,
                provider_code=EODDATA_PROVIDER_CODE,
                source_code=spec.source_code,
                format_suffix="json",
                data=response.body,
                content_type=EODDATA_CONTENT_TYPE,
                part_key=spec.exchange.lower(),
                parser_version=spec.parser_version,
                provider_metadata={
                    "http_status": response.status_code,
                    "market": spec.exchange,
                },
            )
        except Exception:
            raise _acquisition_error(spec, "raw-object storage failed") from None
        acquired.append(stored)
    return tuple(acquired)


def _request_specs(
    *,
    exchanges: tuple[str, ...],
) -> tuple[_RequestSpec, ...]:
    symbols = tuple(
        _RequestSpec(
            source_code=EODDATA_SYMBOL_LIST_SOURCE.source_code,
            parser_version=EODDATA_SYMBOL_LIST_SOURCE.parser_version,
            exchange=exchange,
            endpoint_name="Symbol List",
            path=f"/Symbol/List/{exchange}",
            allow_empty=False,
        )
        for exchange in exchanges
    )
    quotes = tuple(
        _RequestSpec(
            source_code=EODDATA_DAILY_SOURCE.source_code,
            parser_version=EODDATA_DAILY_SOURCE.parser_version,
            exchange=exchange,
            endpoint_name="Quote List",
            path=f"/Quote/List/{exchange}",
            allow_empty=True,
        )
        for exchange in exchanges
    )
    return symbols + quotes


def _request_with_retries(
    *,
    transport: EODDataHTTPTransport,
    url: str,
    query: Mapping[str, str],
    timeout_seconds: float,
    max_retries: int,
    sleep: Sleep,
    spec: _RequestSpec,
    retry_sink: RetrySink | None,
) -> EODDataHTTPResponse:
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            response = transport(
                url=url,
                query=query,
                timeout_seconds=timeout_seconds,
            )
            if not isinstance(response, EODDataHTTPResponse):
                raise TypeError("transport returned an unsupported response")
        except Exception:
            if attempt < max_retries:
                delay = _retry_delay(attempt=attempt, headers={})
                _emit_retry(
                    retry_sink,
                    spec=spec,
                    retry_number=attempt + 1,
                    delay_seconds=delay,
                    reason="transport",
                )
                sleep(delay)
                continue
            raise _acquisition_error(
                spec, f"transport failed after {attempts} attempts"
            ) from None

        if response.status_code == 200:
            return response
        if response.status_code in _RETRYABLE_HTTP_STATUSES and attempt < max_retries:
            delay = _retry_delay(attempt=attempt, headers=response.headers)
            _emit_retry(
                retry_sink,
                spec=spec,
                retry_number=attempt + 1,
                delay_seconds=delay,
                reason=(
                    "http_429"
                    if response.status_code == 429
                    else "http_5xx"
                ),
            )
            sleep(delay)
            continue
        qualifier = " after retries" if attempt else ""
        raise _acquisition_error(
            spec,
            f"returned HTTP {response.status_code}{qualifier}",
        )
    raise AssertionError("bounded EODData retry loop did not return or raise")


def _retry_delay(*, attempt: int, headers: Mapping[str, str]) -> float:
    retry_after = headers.get("retry-after")
    if retry_after is not None:
        try:
            delay = float(retry_after)
        except ValueError:
            delay = -1.0
        if isfinite(delay) and delay >= 0:
            return min(delay, _MAX_RETRY_DELAY_SECONDS)
    exponential = _DEFAULT_RETRY_BACKOFF_SECONDS * (2**attempt)
    return min(exponential, _MAX_RETRY_DELAY_SECONDS)


def _emit_retry(
    retry_sink: RetrySink | None,
    *,
    spec: _RequestSpec,
    retry_number: int,
    delay_seconds: float,
    reason: str,
) -> None:
    if retry_sink is None:
        return
    retry_sink(
        EODDataRetryEvent(
            source_code=spec.source_code,
            exchange=spec.exchange,
            retry_number=retry_number,
            delay_seconds=delay_seconds,
            reason=reason,
        )
    )


def _selected_exchanges(values: tuple[str, ...] | None) -> tuple[str, ...]:
    exchanges = DEFAULT_EODDATA_EXCHANGES if values is None else values
    if not isinstance(exchanges, tuple) or not exchanges:
        raise ValueError("exchanges must be a non-empty tuple.")
    selected = tuple(
        exchange
        for exchange in DEFAULT_EODDATA_EXCHANGES
        if exchange in exchanges
    )
    if selected != exchanges or len(selected) != len(set(selected)):
        raise ValueError(
            "exchanges must be an ordered configured EODData subset."
        )
    return selected


def _validate_json_array(
    *,
    response: EODDataHTTPResponse,
    spec: _RequestSpec,
) -> None:
    content_type = response.headers.get("content-type")
    if content_type is not None:
        media_type = content_type.partition(";")[0].strip().lower()
        if media_type != EODDATA_CONTENT_TYPE and not media_type.endswith("+json"):
            raise _acquisition_error(spec, "returned a non-JSON content type")
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _acquisition_error(spec, "returned invalid JSON") from None
    if not isinstance(payload, list):
        raise _acquisition_error(spec, "returned a non-array JSON payload")
    if not payload and not spec.allow_empty:
        raise _acquisition_error(spec, "returned an empty required payload")


def _safe_failure(spec: _RequestSpec, detail: str) -> str:
    return f"EODData {spec.endpoint_name} for {spec.exchange} {detail}."


def _acquisition_error(
    spec: _RequestSpec,
    detail: str,
) -> OHLCVAcquisitionError:
    return OHLCVAcquisitionError(
        _safe_failure(spec, detail),
        market=spec.exchange,
        source_code=spec.source_code,
    )


def _validate_inputs(
    *,
    run_context: RunContext,
    config: OHLCVConfig,
    sleep: Sleep,
) -> None:
    if not isinstance(run_context, RunContext):
        raise TypeError("run_context must be a Core RunContext.")
    if run_context.domain != "stonks" or run_context.status != "started":
        raise ValueError("run_context must be an active stonks run.")
    if run_context.effective_date is None:
        raise ValueError("run_context effective_date is required.")
    if not isinstance(config, OHLCVConfig):
        raise TypeError("config must be an OHLCVConfig.")
    if not callable(sleep):
        raise TypeError("sleep must be callable.")


def _urllib_transport(
    *,
    url: str,
    query: Mapping[str, str],
    timeout_seconds: float,
) -> EODDataHTTPResponse:
    request_url = f"{url}?{urlencode(query)}"
    request = Request(
        request_url,
        headers={
            "Accept": EODDATA_CONTENT_TYPE,
            "User-Agent": EODDATA_USER_AGENT,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return EODDataHTTPResponse(
                status_code=response.status,
                body=response.read(),
                headers=dict(response.headers.items()),
            )
    except HTTPError as exc:
        return EODDataHTTPResponse(
            status_code=exc.code,
            body=exc.read(),
            headers=dict(exc.headers.items()) if exc.headers else {},
        )
    except (TimeoutError, URLError, OSError):
        raise _TransportFailure("EODData transport request failed.") from None
