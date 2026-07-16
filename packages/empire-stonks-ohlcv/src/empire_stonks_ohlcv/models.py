"""Provider-neutral records for provider-native OHLCV data."""

from __future__ import annotations

from dataclasses import dataclass


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
