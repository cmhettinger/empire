"""Deterministic Yahoo Chart parsing into provider-native daily bars."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Iterable, NoReturn
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from empire_stonks_ohlcv.exceptions import (
    OHLCVCalendarError,
    OHLCVParseError,
)
from empire_stonks_ohlcv.market_sessions import (
    MarketSessionService,
    SessionPolicy,
)
from empire_stonks_ohlcv.models import DailyBar, ProviderListing
from empire_stonks_ohlcv.results import (
    ImportIssue,
    ParsedListingBatch,
    ParsedProviderOutput,
)
from empire_stonks_ohlcv.source_conventions import YAHOO_DAILY_SOURCE
from empire_stonks_ohlcv.yahoo import (
    YAHOO_MARKET,
    YAHOO_PROVIDER_CODE,
    YahooAcquisitionRequest,
)


_ISSUE_SAMPLE_LIMIT = 100
_QUOTE_FIELDS = ("open", "high", "low", "close", "volume")
_EXCHANGE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,63}$")


@dataclass(frozen=True)
class YahooAdjustedClose:
    """One optional adjusted close retained outside shared bar persistence."""

    trading_date: date
    adjusted_close: Decimal | None

    def __post_init__(self) -> None:
        if type(self.trading_date) is not date:
            raise TypeError("trading_date must be a date.")
        if self.adjusted_close is not None and (
            type(self.adjusted_close) is not Decimal
            or not self.adjusted_close.is_finite()
        ):
            raise ValueError("adjusted_close must be a finite Decimal or None.")

    def to_dict(self) -> dict[str, str | None]:
        return {
            "trading_date": self.trading_date.isoformat(),
            "adjusted_close": (
                None
                if self.adjusted_close is None
                else str(self.adjusted_close)
            ),
        }


@dataclass(frozen=True)
class YahooChartParseResult:
    """One seeded listing's accepted bars and bounded parse diagnostics."""

    request: YahooAcquisitionRequest
    session_policy_code: str
    response_timezone_name: str
    exchange_name: str
    batch: ParsedListingBatch
    input_rows: int
    invalid_rows: int
    unplanned_rows: int
    compatible_duplicate_groups: int
    collapsed_duplicate_rows: int
    conflicting_duplicate_groups: int
    conflicting_duplicate_rows: int
    adjusted_close_present: bool
    adjusted_closes: tuple[YahooAdjustedClose, ...]
    invalid_adjusted_close_rows: int
    issue_count: int
    issues: tuple[ImportIssue, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.request, YahooAcquisitionRequest):
            raise TypeError("request must be a YahooAcquisitionRequest.")
        _required_text("session_policy_code", self.session_policy_code)
        _required_text("response_timezone_name", self.response_timezone_name)
        _required_text("exchange_name", self.exchange_name)
        if not isinstance(self.batch, ParsedListingBatch):
            raise TypeError("batch must be a ParsedListingBatch.")
        for field_name in (
            "input_rows",
            "invalid_rows",
            "unplanned_rows",
            "compatible_duplicate_groups",
            "collapsed_duplicate_rows",
            "conflicting_duplicate_groups",
            "conflicting_duplicate_rows",
            "invalid_adjusted_close_rows",
            "issue_count",
        ):
            _nonnegative_int(field_name, getattr(self, field_name))
        if not isinstance(self.adjusted_close_present, bool):
            raise TypeError("adjusted_close_present must be a boolean.")
        if not isinstance(self.adjusted_closes, tuple) or any(
            not isinstance(item, YahooAdjustedClose)
            for item in self.adjusted_closes
        ):
            raise TypeError(
                "adjusted_closes must contain YahooAdjustedClose values."
            )
        if not isinstance(self.issues, tuple) or any(
            not isinstance(item, ImportIssue) for item in self.issues
        ):
            raise TypeError("issues must contain ImportIssue values.")
        if len(self.issues) > self.issue_count:
            raise ValueError("issues cannot exceed issue_count.")
        if self.adjusted_close_present:
            if len(self.adjusted_closes) != self.accepted_rows:
                raise ValueError(
                    "adjusted_closes must align with accepted bars."
                )
        elif self.adjusted_closes or self.invalid_adjusted_close_rows:
            raise ValueError(
                "adjusted-close diagnostics require an adjusted-close array."
            )
        processed_rows = (
            self.accepted_rows
            + self.invalid_rows
            + self.unplanned_rows
            + self.collapsed_duplicate_rows
            + self.conflicting_duplicate_rows
        )
        if processed_rows != self.input_rows:
            raise ValueError("Yahoo parse row counts must reconcile.")

    @property
    def accepted_rows(self) -> int:
        return self.batch.bar_count

    @property
    def rejected_rows(self) -> int:
        return (
            self.invalid_rows
            + self.unplanned_rows
            + self.conflicting_duplicate_rows
        )

    def to_parsed_provider_output(self) -> ParsedProviderOutput:
        """Return the shared provider output without adjusted-close storage."""

        return ParsedProviderOutput(
            sources=(YAHOO_DAILY_SOURCE,),
            batches=(self.batch,),
        )

    def to_dict(self) -> dict[str, Any]:
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
            "session_policy_code": self.session_policy_code,
            "response_timezone_name": self.response_timezone_name,
            "exchange_name": self.exchange_name,
            "input_rows": self.input_rows,
            "accepted_rows": self.accepted_rows,
            "rejected_rows": self.rejected_rows,
            "invalid_rows": self.invalid_rows,
            "unplanned_rows": self.unplanned_rows,
            "compatible_duplicate_groups": (
                self.compatible_duplicate_groups
            ),
            "collapsed_duplicate_rows": self.collapsed_duplicate_rows,
            "conflicting_duplicate_groups": (
                self.conflicting_duplicate_groups
            ),
            "conflicting_duplicate_rows": self.conflicting_duplicate_rows,
            "adjusted_close_present": self.adjusted_close_present,
            "adjusted_closes": [
                item.to_dict() for item in self.adjusted_closes
            ],
            "invalid_adjusted_close_rows": (
                self.invalid_adjusted_close_rows
            ),
            "issue_count": self.issue_count,
            "issues": [item.to_dict() for item in self.issues],
            "batch": self.batch.to_dict(),
        }


@dataclass(frozen=True)
class _Observation:
    bar: DailyBar
    adjusted_close: Decimal | None


@dataclass
class _ParseDiagnostics:
    invalid_rows: int = 0
    unplanned_rows: int = 0
    invalid_adjusted_close_rows: int = 0
    issue_count: int = 0
    issues: list[ImportIssue] | None = None

    def __post_init__(self) -> None:
        if self.issues is None:
            self.issues = []

    def add_issue(
        self,
        *,
        code: str,
        message: str,
        record_reference: str,
    ) -> None:
        self.issue_count += 1
        assert self.issues is not None
        if len(self.issues) < _ISSUE_SAMPLE_LIMIT:
            self.issues.append(
                ImportIssue(
                    code=code,
                    message=message,
                    source_code=YAHOO_DAILY_SOURCE.source_code,
                    record_reference=record_reference,
                )
            )


def parse_yahoo_chart(
    payload: bytes,
    *,
    request: YahooAcquisitionRequest,
    listing: ProviderListing,
    policy: SessionPolicy,
    planned_session_dates: Iterable[date] | None,
    session_service: MarketSessionService | None = None,
) -> YahooChartParseResult:
    """Parse one successful Yahoo Chart body for one seeded listing."""

    planned = _validate_inputs(
        request=request,
        listing=listing,
        policy=policy,
        planned_session_dates=planned_session_dates,
        session_service=session_service,
    )
    value = _decode_payload(payload)
    (
        meta,
        timestamps,
        quote,
        adjusted_values,
    ) = _chart_values(value, request=request)
    response_timezone_name, response_timezone = _response_timezone(meta)
    exchange_name = _exchange_name(meta)
    service = session_service or MarketSessionService()
    diagnostics = _ParseDiagnostics()
    grouped: dict[date, list[_Observation]] = {}

    for index, timestamp in enumerate(timestamps):
        record_reference = (
            f"{request.listing.ticker}:position:{index}"
        )
        instant = _provider_instant(
            timestamp,
            diagnostics=diagnostics,
            record_reference=record_reference,
        )
        if instant is None:
            continue
        _require_timezone_alignment(
            instant=instant,
            response_timezone=response_timezone,
            policy=policy,
        )
        try:
            session_date = service.provider_session_date(
                policy=policy,
                provider_timestamp=instant,
                expected_session_dates=(
                    planned if policy.calendar_name is not None else None
                ),
            )
        except (OHLCVCalendarError, TypeError, ValueError):
            diagnostics.unplanned_rows += 1
            diagnostics.add_issue(
                code="yahoo_unplanned_session",
                message="Provider date did not match the planned sessions.",
                record_reference=record_reference,
            )
            continue
        if not _date_is_planned(
            session_date=session_date,
            request=request,
            planned=planned,
        ):
            diagnostics.unplanned_rows += 1
            diagnostics.add_issue(
                code="yahoo_unplanned_session",
                message="Provider date was outside the accepted request plan.",
                record_reference=record_reference,
            )
            continue

        bar = _daily_bar(
            session_date=session_date,
            quote=quote,
            index=index,
        )
        if bar is None:
            diagnostics.invalid_rows += 1
            diagnostics.add_issue(
                code="yahoo_invalid_ohlcv",
                message="Invalid Yahoo OHLCV observation was rejected.",
                record_reference=record_reference,
            )
            continue

        adjusted_close: Decimal | None = None
        if adjusted_values is not None:
            adjusted_close = _optional_decimal(adjusted_values[index])
            if (
                adjusted_values[index] is not None
                and adjusted_close is None
            ):
                diagnostics.invalid_adjusted_close_rows += 1
                diagnostics.add_issue(
                    code="yahoo_invalid_adjusted_close",
                    message=(
                        "Invalid adjusted close was ignored; native close "
                        "was retained."
                    ),
                    record_reference=record_reference,
                )
        grouped.setdefault(session_date, []).append(
            _Observation(
                bar=bar,
                adjusted_close=adjusted_close,
            )
        )

    accepted_bars: list[DailyBar] = []
    adjusted_closes: list[YahooAdjustedClose] = []
    compatible_duplicate_groups = 0
    collapsed_duplicate_rows = 0
    conflicting_duplicate_groups = 0
    conflicting_duplicate_rows = 0

    for session_date in sorted(grouped):
        observations = grouped[session_date]
        distinct = {
            (item.bar, item.adjusted_close) for item in observations
        }
        if len(distinct) > 1:
            conflicting_duplicate_groups += 1
            conflicting_duplicate_rows += len(observations)
            diagnostics.add_issue(
                code="yahoo_duplicate_conflict",
                message="Conflicting Yahoo observations were rejected.",
                record_reference=(
                    f"{request.listing.ticker}:{session_date.isoformat()}"
                ),
            )
            continue
        if len(observations) > 1:
            compatible_duplicate_groups += 1
            collapsed_duplicate_rows += len(observations) - 1
            diagnostics.add_issue(
                code="yahoo_duplicate_collapsed",
                message="Equal Yahoo observations were collapsed.",
                record_reference=(
                    f"{request.listing.ticker}:{session_date.isoformat()}"
                ),
            )
        observation = observations[0]
        accepted_bars.append(observation.bar)
        if adjusted_values is not None:
            adjusted_closes.append(
                YahooAdjustedClose(
                    trading_date=session_date,
                    adjusted_close=observation.adjusted_close,
                )
            )

    assert diagnostics.issues is not None
    return YahooChartParseResult(
        request=request,
        session_policy_code=policy.code,
        response_timezone_name=response_timezone_name,
        exchange_name=exchange_name,
        batch=ParsedListingBatch(
            listing=listing,
            bars=tuple(accepted_bars),
        ),
        input_rows=len(timestamps),
        invalid_rows=diagnostics.invalid_rows,
        unplanned_rows=diagnostics.unplanned_rows,
        compatible_duplicate_groups=compatible_duplicate_groups,
        collapsed_duplicate_rows=collapsed_duplicate_rows,
        conflicting_duplicate_groups=conflicting_duplicate_groups,
        conflicting_duplicate_rows=conflicting_duplicate_rows,
        adjusted_close_present=adjusted_values is not None,
        adjusted_closes=tuple(adjusted_closes),
        invalid_adjusted_close_rows=(
            diagnostics.invalid_adjusted_close_rows
        ),
        issue_count=diagnostics.issue_count,
        issues=tuple(diagnostics.issues),
    )


def _decode_payload(payload: bytes) -> dict[str, Any]:
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes.")
    try:
        value = json.loads(
            payload,
            parse_float=Decimal,
            parse_int=int,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise OHLCVParseError("Yahoo Chart payload is invalid JSON.") from None
    if not isinstance(value, dict):
        raise OHLCVParseError(
            "Yahoo Chart payload must be a JSON object."
        )
    return value


def _chart_values(
    value: dict[str, Any],
    *,
    request: YahooAcquisitionRequest,
) -> tuple[
    dict[str, Any],
    list[Any],
    dict[str, list[Any]],
    list[Any] | None,
]:
    chart = value.get("chart")
    if not isinstance(chart, dict):
        raise _shape_error()
    if "error" not in chart or chart["error"] is not None:
        raise _shape_error()
    result = chart.get("result")
    if not isinstance(result, list) or len(result) != 1:
        raise _shape_error()
    series = result[0]
    if not isinstance(series, dict):
        raise _shape_error()
    meta = series.get("meta")
    timestamps = series.get("timestamp")
    indicators = series.get("indicators")
    if (
        not isinstance(meta, dict)
        or not isinstance(timestamps, list)
        or not timestamps
        or not isinstance(indicators, dict)
    ):
        raise _shape_error()
    if meta.get("symbol") != request.listing.yahoo_ticker:
        raise OHLCVParseError(
            "Yahoo Chart response symbol does not match the request."
        )
    quote_values = indicators.get("quote")
    if (
        not isinstance(quote_values, list)
        or len(quote_values) != 1
        or not isinstance(quote_values[0], dict)
    ):
        raise _shape_error()
    quote = quote_values[0]
    for field_name in _QUOTE_FIELDS:
        field_values = quote.get(field_name)
        if (
            not isinstance(field_values, list)
            or len(field_values) != len(timestamps)
        ):
            raise OHLCVParseError(
                "Yahoo Chart quote arrays must align with timestamps."
            )

    adjusted_values: list[Any] | None = None
    if "adjclose" in indicators:
        adjusted = indicators["adjclose"]
        if (
            not isinstance(adjusted, list)
            or len(adjusted) != 1
            or not isinstance(adjusted[0], dict)
            or not isinstance(adjusted[0].get("adjclose"), list)
            or len(adjusted[0]["adjclose"]) != len(timestamps)
        ):
            raise OHLCVParseError(
                "Yahoo Chart adjusted-close array must align with timestamps."
            )
        adjusted_values = adjusted[0]["adjclose"]
    return meta, timestamps, quote, adjusted_values


def _shape_error() -> OHLCVParseError:
    return OHLCVParseError("Yahoo Chart payload has an invalid response shape.")


def _response_timezone(
    meta: dict[str, Any],
) -> tuple[str, ZoneInfo]:
    timezone_name = _required_meta_text(meta, "exchangeTimezoneName")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        raise OHLCVParseError(
            "Yahoo Chart response has an unknown exchange timezone."
        ) from None
    return timezone_name, timezone


def _exchange_name(meta: dict[str, Any]) -> str:
    value = _required_meta_text(meta, "exchangeName")
    if not _EXCHANGE_NAME_PATTERN.fullmatch(value):
        raise OHLCVParseError(
            "Yahoo Chart response has an invalid exchangeName."
        )
    return value


def _required_meta_text(meta: dict[str, Any], field_name: str) -> str:
    value = meta.get(field_name)
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
    ):
        raise OHLCVParseError(
            f"Yahoo Chart response has an invalid {field_name}."
        )
    return value


def _required_text(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty and trimmed.")


def _nonnegative_int(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")


def _provider_instant(
    value: Any,
    *,
    diagnostics: _ParseDiagnostics,
    record_reference: str,
) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int):
        diagnostics.invalid_rows += 1
        diagnostics.add_issue(
            code="yahoo_invalid_timestamp",
            message="Invalid Yahoo provider timestamp was rejected.",
            record_reference=record_reference,
        )
        return None
    try:
        return datetime.fromtimestamp(value, UTC)
    except (OverflowError, OSError, ValueError):
        diagnostics.invalid_rows += 1
        diagnostics.add_issue(
            code="yahoo_invalid_timestamp",
            message="Invalid Yahoo provider timestamp was rejected.",
            record_reference=record_reference,
        )
        return None


def _require_timezone_alignment(
    *,
    instant: datetime,
    response_timezone: ZoneInfo,
    policy: SessionPolicy,
) -> None:
    try:
        policy_timezone = ZoneInfo(policy.timezone_name)
    except ZoneInfoNotFoundError:
        raise OHLCVParseError(
            "Yahoo session policy has an unknown timezone."
        ) from None
    response_local = instant.astimezone(response_timezone)
    policy_local = instant.astimezone(policy_timezone)
    if (
        response_local.utcoffset() != policy_local.utcoffset()
        or response_local.date() != policy_local.date()
    ):
        raise OHLCVParseError(
            "Yahoo response timezone does not match the session policy."
        )


def _daily_bar(
    *,
    session_date: date,
    quote: dict[str, list[Any]],
    index: int,
) -> DailyBar | None:
    values: dict[str, Decimal | None] = {
        field_name: _optional_decimal(quote[field_name][index])
        for field_name in _QUOTE_FIELDS
    }
    if any(values[field_name] is None for field_name in _QUOTE_FIELDS[:4]):
        return None
    volume_value = quote["volume"][index]
    if volume_value is not None and values["volume"] is None:
        return None
    try:
        return DailyBar(
            trading_date=session_date,
            open=values["open"],  # type: ignore[arg-type]
            high=values["high"],  # type: ignore[arg-type]
            low=values["low"],  # type: ignore[arg-type]
            close=values["close"],  # type: ignore[arg-type]
            volume=values["volume"],
        )
    except (TypeError, ValueError):
        return None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        value = Decimal(value)
    if type(value) is not Decimal or not value.is_finite():
        return None
    return value


def _date_is_planned(
    *,
    session_date: date,
    request: YahooAcquisitionRequest,
    planned: frozenset[date] | None,
) -> bool:
    if not request.start_date <= session_date < request.end_date_exclusive:
        return False
    return planned is None or session_date in planned


def _validate_inputs(
    *,
    request: YahooAcquisitionRequest,
    listing: ProviderListing,
    policy: SessionPolicy,
    planned_session_dates: Iterable[date] | None,
    session_service: MarketSessionService | None,
) -> frozenset[date] | None:
    if not isinstance(request, YahooAcquisitionRequest):
        raise TypeError("request must be a YahooAcquisitionRequest.")
    if not isinstance(listing, ProviderListing):
        raise TypeError("listing must be a ProviderListing.")
    if listing.provider_code != YAHOO_PROVIDER_CODE:
        raise ValueError("listing provider_code must be YAHOO.")
    if listing.market != YAHOO_MARKET:
        raise ValueError("listing market must be XIDX.")
    if listing.ticker != request.listing.ticker:
        raise ValueError("listing ticker must match the acquisition target.")
    metadata = listing.metadata
    if (
        not isinstance(metadata, dict)
        or metadata.get("YahooTicker") != request.listing.yahoo_ticker
    ):
        raise ValueError(
            "listing metadata.YahooTicker must match the acquisition target."
        )
    if not isinstance(policy, SessionPolicy):
        raise TypeError("policy must be a SessionPolicy.")
    if session_service is not None and not isinstance(
        session_service,
        MarketSessionService,
    ):
        raise TypeError("session_service must be a MarketSessionService.")
    planned = _planned_dates(planned_session_dates)
    if policy.calendar_name is not None and planned is None:
        raise ValueError(
            "calendar-backed Yahoo parsing requires planned_session_dates."
        )
    if planned is not None and any(
        not request.start_date <= item < request.end_date_exclusive
        for item in planned
    ):
        raise ValueError(
            "planned_session_dates must be inside the acquisition range."
        )
    return planned


def _planned_dates(
    values: Iterable[date] | None,
) -> frozenset[date] | None:
    if values is None:
        return None
    if isinstance(values, (str, bytes)):
        raise TypeError("planned_session_dates must be dates or None.")
    try:
        result = frozenset(values)
    except TypeError as exc:
        raise TypeError(
            "planned_session_dates must be dates or None."
        ) from exc
    if any(type(item) is not date for item in result):
        raise TypeError("planned_session_dates must contain dates.")
    return result


def _reject_json_constant(_value: str) -> NoReturn:
    raise ValueError("non-standard JSON numeric constant")
