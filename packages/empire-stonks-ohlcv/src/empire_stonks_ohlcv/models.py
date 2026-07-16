"""Provider-neutral records for provider-native OHLCV data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


UNKNOWN_INSTRUMENT_TYPE_CODE = "UNKNOWN"
_DATABASE_CODE_MAX_LENGTH = 32


def _validate_code(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value:
        raise ValueError(f"{field_name} is required.")
    if value != value.strip():
        raise ValueError(
            f"{field_name} must not contain leading or trailing whitespace."
        )
    if len(value) > _DATABASE_CODE_MAX_LENGTH:
        raise ValueError(
            f"{field_name} must be at most {_DATABASE_CODE_MAX_LENGTH} characters."
        )
    if value != value.upper():
        raise ValueError(f"{field_name} must be uppercase.")


def _validate_native_identity(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value or not value.strip():
        raise ValueError(f"{field_name} is required.")
    if value != value.strip():
        raise ValueError(
            f"{field_name} must not contain leading or trailing whitespace."
        )


def _validate_decimal(field_name: str, value: object) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal.")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite.")


@dataclass(frozen=True)
class ProviderListing:
    """One exact provider-native market/ticker series.

    This record preserves provider market and ticker case. It identifies a
    provider series only and makes no claim about canonical listing identity or
    real-world continuity over time.
    """

    provider_code: str
    market: str
    ticker: str
    name: str | None = None
    instrument_type_code: str = UNKNOWN_INSTRUMENT_TYPE_CODE

    def __post_init__(self) -> None:
        _validate_code("provider_code", self.provider_code)
        _validate_native_identity("market", self.market)
        _validate_native_identity("ticker", self.ticker)
        _validate_code("instrument_type_code", self.instrument_type_code)


@dataclass(frozen=True)
class DailyBar:
    """Provider-supplied source values for one daily OHLCV observation.

    Database-scale conversion and persisted derived values are intentionally
    owned by the writer rather than accepted as provider inputs.
    """

    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None

    def __post_init__(self) -> None:
        if type(self.trading_date) is not date:
            raise TypeError("trading_date must be a date.")

        _validate_decimal("open", self.open)
        _validate_decimal("high", self.high)
        _validate_decimal("low", self.low)
        _validate_decimal("close", self.close)
        if self.volume is not None:
            _validate_decimal("volume", self.volume)

        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low.")
        if self.high < self.open or self.high < self.close:
            raise ValueError("high must be greater than or equal to open and close.")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be less than or equal to open and close.")
        if self.volume is not None and self.volume < Decimal(0):
            raise ValueError("volume must be non-negative.")
