"""EODData exchange-scoped Quote List parsing and reconciliation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, NoReturn

from empire_stonks_ohlcv.config import DEFAULT_EODDATA_EXCHANGES
from empire_stonks_ohlcv.eoddata_symbols import EODDataSymbolListParseResult
from empire_stonks_ohlcv.exceptions import OHLCVParseError
from empire_stonks_ohlcv.models import DailyBar
from empire_stonks_ohlcv.results import (
    ImportIssue,
    ParsedListingBatch,
    ParsedProviderOutput,
)
from empire_stonks_ohlcv.source_conventions import (
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
)


_ISSUE_SAMPLE_LIMIT = 100
_VALUE_FIELDS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class EODDataQuoteListParseResult:
    """Reconciled listing batches and deterministic quote diagnostics."""

    exchange: str
    effective_date: date
    row_count: int
    batches: tuple[ParsedListingBatch, ...]
    compatible_duplicate_groups: int
    collapsed_duplicate_rows: int
    conflicting_duplicate_groups: int
    conflicting_duplicate_rows: int
    invalid_quote_groups: int
    invalid_quote_rows: int
    unmatched_quote_groups: int
    unmatched_quote_rows: int
    symbols_without_quotes: int
    empty_quote_list: bool
    issue_count: int
    issues: tuple[ImportIssue, ...]

    @property
    def listing_count(self) -> int:
        return len(self.batches)

    @property
    def bar_count(self) -> int:
        return sum(batch.bar_count for batch in self.batches)

    @property
    def rejected_rows(self) -> int:
        return (
            self.conflicting_duplicate_rows
            + self.invalid_quote_rows
            + self.unmatched_quote_rows
        )

    def to_parsed_provider_output(self) -> ParsedProviderOutput:
        """Return the reconciled shared output for later persistence."""

        return ParsedProviderOutput(
            sources=(EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE),
            batches=self.batches,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "effective_date": self.effective_date.isoformat(),
            "row_count": self.row_count,
            "listing_count": self.listing_count,
            "bar_count": self.bar_count,
            "batches": [batch.to_dict() for batch in self.batches],
            "compatible_duplicate_groups": self.compatible_duplicate_groups,
            "collapsed_duplicate_rows": self.collapsed_duplicate_rows,
            "conflicting_duplicate_groups": self.conflicting_duplicate_groups,
            "conflicting_duplicate_rows": self.conflicting_duplicate_rows,
            "invalid_quote_groups": self.invalid_quote_groups,
            "invalid_quote_rows": self.invalid_quote_rows,
            "unmatched_quote_groups": self.unmatched_quote_groups,
            "unmatched_quote_rows": self.unmatched_quote_rows,
            "symbols_without_quotes": self.symbols_without_quotes,
            "empty_quote_list": self.empty_quote_list,
            "rejected_rows": self.rejected_rows,
            "issue_count": self.issue_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def parse_eoddata_quote_list(
    payload: bytes,
    *,
    exchange: str,
    effective_date: date,
    symbol_list: EODDataSymbolListParseResult,
) -> EODDataQuoteListParseResult:
    """Parse and reconcile one EODData Quote List request partition."""

    _validate_scope_inputs(
        exchange=exchange,
        effective_date=effective_date,
        symbol_list=symbol_list,
    )
    rows = _decode_rows(payload)
    groups = _validate_and_group_rows(
        rows,
        exchange=exchange,
        effective_date=effective_date,
    )
    listings_by_ticker = {
        listing.ticker: listing for listing in symbol_list.listings
    }

    accepted_bars: dict[str, DailyBar] = {}
    issues: list[ImportIssue] = []
    compatible_duplicate_groups = 0
    collapsed_duplicate_rows = 0
    conflicting_duplicate_groups = 0
    conflicting_duplicate_rows = 0
    invalid_quote_groups = 0
    invalid_quote_rows = 0
    unmatched_quote_groups = 0
    unmatched_quote_rows = 0
    issue_count = 0

    for ticker in sorted(groups):
        group = groups[ticker]
        try:
            bars = tuple(
                _parse_bar(row, effective_date=effective_date) for row in group
            )
        except ValueError:
            invalid_quote_groups += 1
            invalid_quote_rows += len(group)
            issue_count += 1
            _append_issue(
                issues,
                code="eoddata_quote_invalid_ohlcv",
                message="Invalid Quote List OHLCV rows were rejected.",
                exchange=exchange,
                ticker=ticker,
            )
            continue

        distinct_bars = set(bars)
        if len(distinct_bars) > 1:
            conflicting_duplicate_groups += 1
            conflicting_duplicate_rows += len(group)
            issue_count += 1
            conflicting_fields = _conflicting_value_fields(bars)
            _append_issue(
                issues,
                code="eoddata_quote_duplicate_conflict",
                message=(
                    "Conflicting duplicate Quote List fields were rejected: "
                    f"{','.join(conflicting_fields)}."
                ),
                exchange=exchange,
                ticker=ticker,
            )
            continue

        if len(group) > 1:
            compatible_duplicate_groups += 1
            collapsed_duplicate_rows += len(group) - 1

        if ticker not in listings_by_ticker:
            unmatched_quote_groups += 1
            unmatched_quote_rows += len(group)
            issue_count += 1
            _append_issue(
                issues,
                code="eoddata_quote_without_listing",
                message=(
                    "Quote List identity has no accepted same-exchange "
                    "Symbol List identity."
                ),
                exchange=exchange,
                ticker=ticker,
            )
            continue

        accepted_bars[ticker] = bars[0]

    batches = tuple(
        ParsedListingBatch(
            listing=listings_by_ticker[ticker],
            bars=(accepted_bars[ticker],) if ticker in accepted_bars else (),
        )
        for ticker in sorted(listings_by_ticker)
    )
    symbols_without_quotes = sum(
        ticker not in groups for ticker in listings_by_ticker
    )
    return EODDataQuoteListParseResult(
        exchange=exchange,
        effective_date=effective_date,
        row_count=len(rows),
        batches=batches,
        compatible_duplicate_groups=compatible_duplicate_groups,
        collapsed_duplicate_rows=collapsed_duplicate_rows,
        conflicting_duplicate_groups=conflicting_duplicate_groups,
        conflicting_duplicate_rows=conflicting_duplicate_rows,
        invalid_quote_groups=invalid_quote_groups,
        invalid_quote_rows=invalid_quote_rows,
        unmatched_quote_groups=unmatched_quote_groups,
        unmatched_quote_rows=unmatched_quote_rows,
        symbols_without_quotes=symbols_without_quotes,
        empty_quote_list=not rows,
        issue_count=issue_count,
        issues=tuple(issues),
    )


def _validate_scope_inputs(
    *,
    exchange: str,
    effective_date: date,
    symbol_list: EODDataSymbolListParseResult,
) -> None:
    if exchange not in DEFAULT_EODDATA_EXCHANGES:
        raise ValueError("exchange must be one of NYSE, NASDAQ, or AMEX.")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a date.")
    if not isinstance(symbol_list, EODDataSymbolListParseResult):
        raise TypeError("symbol_list must be an EODDataSymbolListParseResult.")
    if symbol_list.exchange != exchange:
        raise ValueError("symbol_list exchange must match the Quote List exchange.")


def _decode_rows(payload: bytes) -> list[Any]:
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes.")
    try:
        value = json.loads(
            payload,
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise OHLCVParseError(
            "EODData Quote List payload is invalid JSON."
        ) from None
    if not isinstance(value, list):
        raise OHLCVParseError(
            "EODData Quote List payload must be a JSON array."
        )
    return value


def _reject_json_constant(_value: str) -> NoReturn:
    raise ValueError("non-standard JSON numeric constant")


def _validate_and_group_rows(
    rows: list[Any],
    *,
    exchange: str,
    effective_date: date,
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    expected_date = effective_date.isoformat()
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise OHLCVParseError(
                f"EODData Quote List row {row_number} must be an object."
            )
        if row.get("exchangeCode") != exchange:
            raise OHLCVParseError(
                f"EODData Quote List row {row_number} has an exchange mismatch."
            )
        if row.get("interval") != "d":
            raise OHLCVParseError(
                f"EODData Quote List row {row_number} has an interval mismatch."
            )
        if row.get("dateStamp") != expected_date:
            raise OHLCVParseError(
                f"EODData Quote List row {row_number} has a date mismatch."
            )
        ticker = row.get("symbolCode")
        if (
            not isinstance(ticker, str)
            or not ticker
            or not ticker.strip()
            or ticker != ticker.strip()
        ):
            raise OHLCVParseError(
                f"EODData Quote List row {row_number} has an invalid symbolCode."
            )
        groups.setdefault(ticker, []).append(row)
    return groups


def _parse_bar(row: dict[str, Any], *, effective_date: date) -> DailyBar:
    values: dict[str, Decimal] = {}
    for field_name in _VALUE_FIELDS:
        value = row.get(field_name)
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError("invalid OHLCV value")
        values[field_name] = value
    if values["volume"] < 0:
        raise ValueError("invalid volume")
    try:
        return DailyBar(trading_date=effective_date, **values)
    except (TypeError, ValueError):
        raise ValueError("invalid OHLCV relationship") from None


def _conflicting_value_fields(bars: tuple[DailyBar, ...]) -> tuple[str, ...]:
    return tuple(
        field_name
        for field_name in _VALUE_FIELDS
        if len({getattr(bar, field_name) for bar in bars}) > 1
    )


def _append_issue(
    issues: list[ImportIssue],
    *,
    code: str,
    message: str,
    exchange: str,
    ticker: str,
) -> None:
    if len(issues) >= _ISSUE_SAMPLE_LIMIT:
        return
    issues.append(
        ImportIssue(
            code=code,
            message=message,
            source_code=EODDATA_DAILY_SOURCE.source_code,
            record_reference=f"{exchange}:{ticker}",
        )
    )
