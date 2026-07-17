from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation

from empire_stonks_ohlcv import (
    DailyBar,
    EODDATA_DAILY_SOURCE,
    OHLCVParseError,
    ParsedListingBatch,
    ParsedProviderOutput,
    ProviderListing,
)
from parser_contract import (
    InvalidParserCase,
    ValidParserCase,
    assert_parser_contract,
)


def _reference_parser(payload: bytes) -> ParsedProviderOutput:
    """Test-only parser proving the reusable assertions themselves."""

    try:
        raw = json.loads(payload)
        listing = ProviderListing(
            provider_code="EODDATA",
            market=raw["market"],
            ticker=raw["ticker"],
        )
        bar = DailyBar(
            trading_date=date.fromisoformat(raw["date"]),
            open=Decimal(raw["open"]),
            high=Decimal(raw["high"]),
            low=Decimal(raw["low"]),
            close=Decimal(raw["close"]),
            volume=None if raw["volume"] is None else Decimal(raw["volume"]),
        )
    except (
        InvalidOperation,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise OHLCVParseError("Provider row is structurally invalid.") from exc
    return ParsedProviderOutput(
        sources=(EODDATA_DAILY_SOURCE,),
        batches=(ParsedListingBatch(listing=listing, bars=(bar,)),),
    )


def _payload(*, volume: str | None) -> bytes:
    return json.dumps(
        {
            "market": "NasDaq.X",
            "ticker": "aB.c-D",
            "date": "2026-07-15",
            "open": "10.2500",
            "high": "10.8750",
            "low": "10.1250",
            "close": "10.7500",
            "volume": volume,
        },
        sort_keys=True,
    ).encode("utf-8")


def _expected(*, volume: Decimal | None) -> ParsedProviderOutput:
    return ParsedProviderOutput(
        sources=(EODDATA_DAILY_SOURCE,),
        batches=(
            ParsedListingBatch(
                listing=ProviderListing(
                    provider_code="EODDATA",
                    market="NasDaq.X",
                    ticker="aB.c-D",
                ),
                bars=(
                    DailyBar(
                        trading_date=date(2026, 7, 15),
                        open=Decimal("10.2500"),
                        high=Decimal("10.8750"),
                        low=Decimal("10.1250"),
                        close=Decimal("10.7500"),
                        volume=volume,
                    ),
                ),
            ),
        ),
    )


def test_reference_parser_passes_shared_contract() -> None:
    assert_parser_contract(
        parse=_reference_parser,
        provider_code="EODDATA",
        volume_is_optional=True,
        valid_cases=(
            ValidParserCase(
                name="populated volume and exact native identity",
                payload=_payload(volume="125000.00"),
                expected=_expected(volume=Decimal("125000.00")),
            ),
            ValidParserCase(
                name="optional volume",
                payload=_payload(volume=None),
                expected=_expected(volume=None),
            ),
        ),
        invalid_cases=(
            InvalidParserCase(
                name="invalid negative volume",
                payload=_payload(volume="-1"),
            ),
            InvalidParserCase(
                name="invalid JSON",
                payload=b"not-json",
            ),
        ),
    )
