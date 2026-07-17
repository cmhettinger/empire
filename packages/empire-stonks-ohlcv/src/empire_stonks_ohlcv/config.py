"""Environment-driven configuration for Empire stonks OHLCV ingestion."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from math import isfinite
from typing import Self
from urllib.parse import urlsplit

from empire_stonks_ohlcv.exceptions import OHLCVConfigError


DEFAULT_STORAGE_KEY = "stonks/ohlcv"
DEFAULT_RAW_RETENTION_DAYS = 7
DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_EODDATA_BASE_URL = "https://api.eoddata.com"
DEFAULT_EODDATA_EXCHANGES = ("NYSE", "NASDAQ", "AMEX")

STORAGE_KEY_ENV = "EMPIRE_STORAGE_KEY_STONKS_OHLCV"
RAW_RETENTION_DAYS_ENV = "EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS"
HTTP_TIMEOUT_SECONDS_ENV = "EMPIRE_STONKS_OHLCV_HTTP_TIMEOUT_SECONDS"
MAX_RETRIES_ENV = "EMPIRE_STONKS_OHLCV_MAX_RETRIES"
EODDATA_API_KEY_ENV = "EMPIRE_STONKS_OHLCV_EODDATA_API_KEY"
EODDATA_BASE_URL_ENV = "EMPIRE_STONKS_OHLCV_EODDATA_BASE_URL"
EODDATA_EXCHANGES_ENV = "EMPIRE_STONKS_OHLCV_EODDATA_EXCHANGES"


def _environment_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        pass
    raise OHLCVConfigError(f"{name} must be an integer.")


def _environment_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        pass
    raise OHLCVConfigError(f"{name} must be a number.")


def _environment_eoddata_exchanges() -> tuple[str, ...]:
    raw_value = os.environ.get(EODDATA_EXCHANGES_ENV)
    if raw_value is None:
        return DEFAULT_EODDATA_EXCHANGES
    return tuple(item.strip() for item in raw_value.split(","))


def _validate_eoddata_base_url(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise OHLCVConfigError(f"{EODDATA_BASE_URL_ENV} is required.")
    if value != value.strip() or value.endswith("/"):
        raise OHLCVConfigError(
            f"{EODDATA_BASE_URL_ENV} must not contain whitespace or a trailing slash."
        )
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise OHLCVConfigError(f"{EODDATA_BASE_URL_ENV} is invalid.") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port is not None and not 1 <= port <= 65535
    ):
        raise OHLCVConfigError(
            f"{EODDATA_BASE_URL_ENV} must be an HTTPS origin without credentials, "
            "path, query, or fragment."
        )


def _validate_eoddata_exchanges(value: object) -> None:
    if value != DEFAULT_EODDATA_EXCHANGES:
        raise OHLCVConfigError(
            f"{EODDATA_EXCHANGES_ENV} must be NYSE,NASDAQ,AMEX in that order."
        )


class EODDataCredentials:
    """Immutable EODData credentials with redacted representations."""

    __slots__ = ("_api_key",)

    def __init__(self, *, api_key: str) -> None:
        if not api_key:
            raise OHLCVConfigError(f"{EODDATA_API_KEY_ENV} is required.")
        object.__setattr__(self, "_api_key", api_key)

    @property
    def api_key(self) -> str:
        """Return the API key for provider authentication only."""

        return self._api_key

    def __setattr__(self, name: str, _value: object) -> None:
        raise AttributeError(
            f"{type(self).__name__} is immutable; cannot set {name}"
        )

    def __repr__(self) -> str:
        return "EODDataCredentials(api_key=<redacted>)"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EODDataCredentials):
            return NotImplemented
        return self.api_key == other.api_key

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self


@dataclass(frozen=True)
class OHLCVConfig:
    """Common runtime settings and configured provider credentials."""

    storage_key: str = DEFAULT_STORAGE_KEY
    raw_retention_days: int = DEFAULT_RAW_RETENTION_DAYS
    http_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    eoddata_base_url: str = DEFAULT_EODDATA_BASE_URL
    eoddata_exchanges: tuple[str, ...] = DEFAULT_EODDATA_EXCHANGES
    eoddata_credentials: EODDataCredentials | None = field(
        default=None,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not self.storage_key.strip():
            raise OHLCVConfigError(f"{STORAGE_KEY_ENV} is required.")
        if self.raw_retention_days <= 0:
            raise OHLCVConfigError(
                f"{RAW_RETENTION_DAYS_ENV} must be greater than zero."
            )
        if (
            not isfinite(self.http_timeout_seconds)
            or self.http_timeout_seconds <= 0
        ):
            raise OHLCVConfigError(
                f"{HTTP_TIMEOUT_SECONDS_ENV} must be greater than zero."
            )
        if self.max_retries < 0:
            raise OHLCVConfigError(f"{MAX_RETRIES_ENV} cannot be negative.")
        _validate_eoddata_base_url(self.eoddata_base_url)
        _validate_eoddata_exchanges(self.eoddata_exchanges)

    @classmethod
    def from_env(cls) -> "OHLCVConfig":
        """Load configuration from the process environment."""

        storage_key = os.environ.get(STORAGE_KEY_ENV, DEFAULT_STORAGE_KEY).strip()
        api_key = os.environ.get(EODDATA_API_KEY_ENV)
        eoddata_base_url = os.environ.get(
            EODDATA_BASE_URL_ENV,
            DEFAULT_EODDATA_BASE_URL,
        ).strip().rstrip("/")

        credentials: EODDataCredentials | None = None
        if api_key:
            credentials = EODDataCredentials(api_key=api_key)

        return cls(
            storage_key=storage_key,
            raw_retention_days=_environment_int(
                RAW_RETENTION_DAYS_ENV,
                DEFAULT_RAW_RETENTION_DAYS,
            ),
            http_timeout_seconds=_environment_float(
                HTTP_TIMEOUT_SECONDS_ENV,
                DEFAULT_HTTP_TIMEOUT_SECONDS,
            ),
            max_retries=_environment_int(MAX_RETRIES_ENV, DEFAULT_MAX_RETRIES),
            eoddata_base_url=eoddata_base_url,
            eoddata_exchanges=_environment_eoddata_exchanges(),
            eoddata_credentials=credentials,
        )

    def require_eoddata_credentials(self) -> EODDataCredentials:
        """Return configured EODData credentials or raise a clear error."""

        if self.eoddata_credentials is None:
            raise OHLCVConfigError(
                f"{EODDATA_API_KEY_ENV} is required for EODData acquisition."
            )
        return self.eoddata_credentials

    def to_safe_dict(self) -> dict[str, str | int | float | bool]:
        """Return non-secret settings safe for operational payloads and logs."""

        return {
            "storage_key": self.storage_key,
            "raw_retention_days": self.raw_retention_days,
            "http_timeout_seconds": self.http_timeout_seconds,
            "max_retries": self.max_retries,
            "eoddata_base_url": self.eoddata_base_url,
            "eoddata_exchanges": ",".join(self.eoddata_exchanges),
            "eoddata_configured": self.eoddata_credentials is not None,
        }
