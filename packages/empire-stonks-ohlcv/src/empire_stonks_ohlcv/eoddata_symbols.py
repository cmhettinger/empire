"""EODData exchange-scoped Symbol List parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from empire_stonks_ohlcv.config import DEFAULT_EODDATA_EXCHANGES
from empire_stonks_ohlcv.eoddata import EODDATA_PROVIDER_CODE
from empire_stonks_ohlcv.exceptions import OHLCVParseError
from empire_stonks_ohlcv.models import (
    UNKNOWN_INSTRUMENT_TYPE_CODE,
    ProviderListing,
)
from empire_stonks_ohlcv.results import (
    ImportIssue,
    ParsedListingBatch,
    ParsedProviderOutput,
)
from empire_stonks_ohlcv.source_conventions import EODDATA_SYMBOL_LIST_SOURCE


_ISSUE_SAMPLE_LIMIT = 100
_OPTIONAL_FIELDS = ("name", "type", "currency")
_DUPLICATE_CONFLICT_CODE = "eoddata_symbol_duplicate_conflict"


@dataclass(frozen=True)
class EODDataSymbolListParseResult:
    """Accepted listings and deterministic duplicate diagnostics."""

    exchange: str
    row_count: int
    listings: tuple[ProviderListing, ...]
    compatible_duplicate_groups: int
    collapsed_duplicate_rows: int
    conflicting_duplicate_groups: int
    rejected_rows: int
    issue_count: int
    issues: tuple[ImportIssue, ...]

    @property
    def listing_count(self) -> int:
        return len(self.listings)

    def to_parsed_provider_output(self) -> ParsedProviderOutput:
        """Adapt listing discovery to the provider-neutral parser boundary."""

        return ParsedProviderOutput(
            sources=(EODDATA_SYMBOL_LIST_SOURCE,),
            batches=tuple(
                ParsedListingBatch(listing=listing, bars=())
                for listing in self.listings
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "row_count": self.row_count,
            "listing_count": self.listing_count,
            "listings": [listing.to_dict() for listing in self.listings],
            "compatible_duplicate_groups": self.compatible_duplicate_groups,
            "collapsed_duplicate_rows": self.collapsed_duplicate_rows,
            "conflicting_duplicate_groups": self.conflicting_duplicate_groups,
            "rejected_rows": self.rejected_rows,
            "issue_count": self.issue_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def parse_eoddata_symbol_list(
    payload: bytes,
    *,
    exchange: str,
) -> EODDataSymbolListParseResult:
    """Parse one trusted EODData exchange partition into unique listings."""

    if exchange not in DEFAULT_EODDATA_EXCHANGES:
        raise ValueError("exchange must be one of NYSE, NASDAQ, or AMEX.")
    rows = _decode_rows(payload)

    groups: dict[str, list[dict[str, Any]]] = {}
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise OHLCVParseError(
                f"EODData Symbol List row {row_number} must be an object."
            )
        code = row.get("code")
        if (
            not isinstance(code, str)
            or not code
            or not code.strip()
            or code != code.strip()
        ):
            raise OHLCVParseError(
                f"EODData Symbol List row {row_number} has an invalid code."
            )
        groups.setdefault(code, []).append(row)

    listings: list[ProviderListing] = []
    issues: list[ImportIssue] = []
    compatible_duplicate_groups = 0
    collapsed_duplicate_rows = 0
    conflicting_duplicate_groups = 0
    rejected_rows = 0

    for code in sorted(groups):
        group = groups[code]
        values = {
            field_name: _distinct_usable_values(group, field_name)
            for field_name in _OPTIONAL_FIELDS
        }
        conflicts = tuple(
            field_name
            for field_name in _OPTIONAL_FIELDS
            if len(values[field_name]) > 1
        )
        if conflicts:
            conflicting_duplicate_groups += 1
            rejected_rows += len(group)
            if len(issues) < _ISSUE_SAMPLE_LIMIT:
                issues.append(
                    ImportIssue(
                        code=_DUPLICATE_CONFLICT_CODE,
                        message=(
                            "Conflicting duplicate Symbol List fields were "
                            f"rejected: {','.join(conflicts)}."
                        ),
                        source_code=EODDATA_SYMBOL_LIST_SOURCE.source_code,
                        record_reference=f"{exchange}:{code}",
                    )
                )
            continue

        if len(group) > 1:
            compatible_duplicate_groups += 1
            collapsed_duplicate_rows += len(group) - 1

        name = _only_value(values["name"])
        type_value = _only_value(values["type"])
        currency = _only_value(values["currency"])
        metadata = {
            key: value
            for key, value in (("type", type_value), ("currency", currency))
            if value is not None
        }
        listings.append(
            ProviderListing(
                provider_code=EODDATA_PROVIDER_CODE,
                market=exchange,
                ticker=code,
                name=name,
                instrument_type_code=UNKNOWN_INSTRUMENT_TYPE_CODE,
                metadata=metadata or None,
            )
        )

    return EODDataSymbolListParseResult(
        exchange=exchange,
        row_count=len(rows),
        listings=tuple(listings),
        compatible_duplicate_groups=compatible_duplicate_groups,
        collapsed_duplicate_rows=collapsed_duplicate_rows,
        conflicting_duplicate_groups=conflicting_duplicate_groups,
        rejected_rows=rejected_rows,
        issue_count=conflicting_duplicate_groups,
        issues=tuple(issues),
    )


def _decode_rows(payload: bytes) -> list[Any]:
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes.")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OHLCVParseError(
            "EODData Symbol List payload is invalid JSON."
        ) from None
    if not isinstance(value, list):
        raise OHLCVParseError(
            "EODData Symbol List payload must be a JSON array."
        )
    if not value:
        raise OHLCVParseError("EODData Symbol List payload must not be empty.")
    return value


def _distinct_usable_values(
    rows: list[dict[str, Any]],
    field_name: str,
) -> tuple[str, ...]:
    values = {
        value
        for row in rows
        if isinstance((value := row.get(field_name)), str) and value.strip()
    }
    return tuple(sorted(values))


def _only_value(values: tuple[str, ...]) -> str | None:
    return values[0] if values else None
