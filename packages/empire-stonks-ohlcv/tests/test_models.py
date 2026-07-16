from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from empire_stonks_ohlcv import ProviderListing


def test_provider_listing_defaults_and_preserves_native_identity() -> None:
    listing = ProviderListing(
        provider_code="EODDATA",
        market="Nasdaq",
        ticker="aapl.US",
    )

    assert listing.provider_code == "EODDATA"
    assert listing.market == "Nasdaq"
    assert listing.ticker == "aapl.US"
    assert listing.name is None
    assert listing.instrument_type_code == "UNKNOWN"


def test_provider_listing_accepts_optional_metadata() -> None:
    listing = ProviderListing(
        provider_code="STOOQ",
        market="US",
        ticker="AAPL.US",
        name="Apple Inc.",
        instrument_type_code="COMMON_STOCK",
    )

    assert listing.name == "Apple Inc."
    assert listing.instrument_type_code == "COMMON_STOCK"


def test_provider_listing_is_immutable() -> None:
    listing = ProviderListing(
        provider_code="YAHOO",
        market="NMS",
        ticker="AAPL",
    )

    with pytest.raises(FrozenInstanceError):
        listing.ticker = "MSFT"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "error_type", "message"),
    [
        ("provider_code", "", ValueError, "required"),
        ("provider_code", " EODDATA", ValueError, "whitespace"),
        ("provider_code", "eoddata", ValueError, "uppercase"),
        ("provider_code", "X" * 33, ValueError, "at most 32"),
        ("provider_code", None, TypeError, "string"),
        ("market", "", ValueError, "required"),
        ("market", "   ", ValueError, "required"),
        ("market", "NYSE ", ValueError, "whitespace"),
        ("market", None, TypeError, "string"),
        ("ticker", "", ValueError, "required"),
        ("ticker", "\t", ValueError, "required"),
        ("ticker", " AAPL", ValueError, "whitespace"),
        ("ticker", None, TypeError, "string"),
    ],
)
def test_provider_listing_rejects_invalid_identity_fields(
    field_name: str,
    invalid_value: object,
    error_type: type[Exception],
    message: str,
) -> None:
    values: dict[str, object] = {
        "provider_code": "EODDATA",
        "market": "NASDAQ",
        "ticker": "AAPL",
    }
    values[field_name] = invalid_value

    with pytest.raises(error_type, match=message):
        ProviderListing(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("instrument_type_code", "message"),
    [
        ("", "required"),
        (" COMMON_STOCK", "whitespace"),
        ("common_stock", "uppercase"),
        ("X" * 33, "at most 32"),
    ],
)
def test_provider_listing_rejects_invalid_instrument_type_code(
    instrument_type_code: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ProviderListing(
            provider_code="EODDATA",
            market="NASDAQ",
            ticker="AAPL",
            instrument_type_code=instrument_type_code,
        )
