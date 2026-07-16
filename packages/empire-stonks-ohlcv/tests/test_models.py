from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime
from decimal import Decimal

import pytest

from empire_stonks_ohlcv import DailyBar, ProviderListing


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


def test_daily_bar_accepts_valid_provider_values() -> None:
    bar = DailyBar(
        trading_date=date(2026, 7, 15),
        open=Decimal("210.125"),
        high=Decimal("214.25"),
        low=Decimal("209.50"),
        close=Decimal("213.75"),
        volume=Decimal("1234567.5"),
    )

    assert bar.trading_date == date(2026, 7, 15)
    assert bar.open == Decimal("210.125")
    assert bar.high == Decimal("214.25")
    assert bar.low == Decimal("209.50")
    assert bar.close == Decimal("213.75")
    assert bar.volume == Decimal("1234567.5")


def test_daily_bar_accepts_null_volume_flat_bar_and_negative_prices() -> None:
    flat_bar = DailyBar(
        trading_date=date(2026, 7, 15),
        open=Decimal("-1.5"),
        high=Decimal("-1.5"),
        low=Decimal("-1.5"),
        close=Decimal("-1.5"),
    )

    assert flat_bar.volume is None


def test_daily_bar_contains_only_provider_source_fields() -> None:
    assert [field.name for field in fields(DailyBar)] == [
        "trading_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]


def test_daily_bar_is_immutable() -> None:
    bar = DailyBar(
        trading_date=date(2026, 7, 15),
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal("11"),
    )

    with pytest.raises(FrozenInstanceError):
        bar.close = Decimal("12")  # type: ignore[misc]


@pytest.mark.parametrize(
    "invalid_date",
    ["2026-07-15", datetime(2026, 7, 15, 12, 0), None],
)
def test_daily_bar_rejects_invalid_trading_date(invalid_date: object) -> None:
    with pytest.raises(TypeError, match="trading_date must be a date"):
        DailyBar(
            trading_date=invalid_date,  # type: ignore[arg-type]
            open=Decimal("10"),
            high=Decimal("12"),
            low=Decimal("9"),
            close=Decimal("11"),
        )


@pytest.mark.parametrize("field_name", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("invalid_value", [1, 1.5, "1", None])
def test_daily_bar_rejects_non_decimal_values(
    field_name: str,
    invalid_value: object,
) -> None:
    values: dict[str, object] = {
        "trading_date": date(2026, 7, 15),
        "open": Decimal("10"),
        "high": Decimal("12"),
        "low": Decimal("9"),
        "close": Decimal("11"),
        "volume": Decimal("100"),
    }
    values[field_name] = invalid_value

    if field_name == "volume" and invalid_value is None:
        DailyBar(**values)  # type: ignore[arg-type]
        return

    with pytest.raises(TypeError, match=f"{field_name} must be a Decimal"):
        DailyBar(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("field_name", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize(
    "invalid_value",
    [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_daily_bar_rejects_non_finite_values(
    field_name: str,
    invalid_value: Decimal,
) -> None:
    values = {
        "trading_date": date(2026, 7, 15),
        "open": Decimal("10"),
        "high": Decimal("12"),
        "low": Decimal("9"),
        "close": Decimal("11"),
        "volume": Decimal("100"),
    }
    values[field_name] = invalid_value  # type: ignore[assignment]

    with pytest.raises(ValueError, match=f"{field_name} must be finite"):
        DailyBar(**values)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"high": Decimal("8")}, "high must be greater than or equal to low"),
        (
            {"open": Decimal("13")},
            "high must be greater than or equal to open and close",
        ),
        (
            {"close": Decimal("13")},
            "high must be greater than or equal to open and close",
        ),
        (
            {"open": Decimal("8")},
            "low must be less than or equal to open and close",
        ),
        (
            {"close": Decimal("8")},
            "low must be less than or equal to open and close",
        ),
        ({"volume": Decimal("-0.01")}, "volume must be non-negative"),
    ],
)
def test_daily_bar_rejects_database_invariant_violations(
    overrides: dict[str, Decimal],
    message: str,
) -> None:
    values = {
        "trading_date": date(2026, 7, 15),
        "open": Decimal("10"),
        "high": Decimal("12"),
        "low": Decimal("9"),
        "close": Decimal("11"),
        "volume": Decimal("100"),
        **overrides,
    }

    with pytest.raises(ValueError, match=message):
        DailyBar(**values)
