"""Environment-driven configuration for Empire stonks OHLCV ingestion."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
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
DEFAULT_EODDATA_REQUEST_DELAY_SECONDS = 2.0
DEFAULT_YAHOO_BASE_URL = "https://query2.finance.yahoo.com"
DEFAULT_YAHOO_REQUEST_DELAY_SECONDS = 25.0
DEFAULT_YAHOO_REQUEST_JITTER_MIN_SECONDS = 5.0
DEFAULT_YAHOO_REQUEST_JITTER_MAX_SECONDS = 10.0
DEFAULT_YAHOO_FAILURE_COOLDOWN_MIN_SECONDS = 8.0
DEFAULT_YAHOO_FAILURE_COOLDOWN_MAX_SECONDS = 18.0
DEFAULT_YAHOO_BACKFILL_START_DATE = "1965-01-01"
DEFAULT_YAHOO_BACKFILL_CHUNK_DAYS = 3650
DEFAULT_YAHOO_DAILY_LOOKBACK_DAYS = 30
DEFAULT_YAHOO_DAILY_REQUEST_MAX_DAYS = 30
DEFAULT_YAHOO_RECONCILIATION_SESSIONS = 7
MAX_YAHOO_BACKFILL_CHUNK_DAYS = 3650
MAX_YAHOO_DAILY_LOOKBACK_DAYS = 365
MAX_YAHOO_DAILY_REQUEST_DAYS = 90
MAX_YAHOO_RECONCILIATION_SESSIONS = 30

STORAGE_KEY_ENV = "EMPIRE_STORAGE_KEY_STONKS_OHLCV"
RAW_RETENTION_DAYS_ENV = "EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS"
HTTP_TIMEOUT_SECONDS_ENV = "EMPIRE_STONKS_OHLCV_HTTP_TIMEOUT_SECONDS"
MAX_RETRIES_ENV = "EMPIRE_STONKS_OHLCV_MAX_RETRIES"
EODDATA_API_KEY_ENV = "EMPIRE_STONKS_OHLCV_EODDATA_API_KEY"
EODDATA_BASE_URL_ENV = "EMPIRE_STONKS_OHLCV_EODDATA_BASE_URL"
EODDATA_EXCHANGES_ENV = "EMPIRE_STONKS_OHLCV_EODDATA_EXCHANGES"
EODDATA_REQUEST_DELAY_SECONDS_ENV = (
    "EMPIRE_STONKS_OHLCV_EODDATA_REQUEST_DELAY_SECONDS"
)
YAHOO_BASE_URL_ENV = "EMPIRE_STONKS_OHLCV_YAHOO_BASE_URL"
YAHOO_REQUEST_DELAY_SECONDS_ENV = (
    "EMPIRE_STONKS_OHLCV_YAHOO_REQUEST_DELAY_SECONDS"
)
YAHOO_REQUEST_JITTER_MIN_SECONDS_ENV = (
    "EMPIRE_STONKS_OHLCV_YAHOO_REQUEST_JITTER_MIN_SECONDS"
)
YAHOO_REQUEST_JITTER_MAX_SECONDS_ENV = (
    "EMPIRE_STONKS_OHLCV_YAHOO_REQUEST_JITTER_MAX_SECONDS"
)
YAHOO_FAILURE_COOLDOWN_MIN_SECONDS_ENV = (
    "EMPIRE_STONKS_OHLCV_YAHOO_FAILURE_COOLDOWN_MIN_SECONDS"
)
YAHOO_FAILURE_COOLDOWN_MAX_SECONDS_ENV = (
    "EMPIRE_STONKS_OHLCV_YAHOO_FAILURE_COOLDOWN_MAX_SECONDS"
)
YAHOO_BACKFILL_START_DATE_ENV = (
    "EMPIRE_STONKS_OHLCV_YAHOO_BACKFILL_START_DATE"
)
YAHOO_BACKFILL_CHUNK_DAYS_ENV = (
    "EMPIRE_STONKS_OHLCV_YAHOO_BACKFILL_CHUNK_DAYS"
)
YAHOO_DAILY_LOOKBACK_DAYS_ENV = (
    "EMPIRE_STONKS_OHLCV_YAHOO_DAILY_LOOKBACK_DAYS"
)
YAHOO_DAILY_REQUEST_MAX_DAYS_ENV = (
    "EMPIRE_STONKS_OHLCV_YAHOO_DAILY_REQUEST_MAX_DAYS"
)
YAHOO_RECONCILIATION_SESSIONS_ENV = (
    "EMPIRE_STONKS_OHLCV_YAHOO_RECONCILIATION_SESSIONS"
)


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


def _validate_yahoo_base_url(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise OHLCVConfigError(f"{YAHOO_BASE_URL_ENV} is required.")
    if value != value.strip() or value.endswith("/"):
        raise OHLCVConfigError(
            f"{YAHOO_BASE_URL_ENV} must not contain whitespace or a trailing slash."
        )
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise OHLCVConfigError(f"{YAHOO_BASE_URL_ENV} is invalid.") from None
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
            f"{YAHOO_BASE_URL_ENV} must be an HTTPS origin without credentials, "
            "path, query, or fragment."
        )


def _validate_nonnegative_float(name: str, value: float) -> None:
    if not isfinite(value) or value < 0:
        raise OHLCVConfigError(f"{name} cannot be negative.")


def _validate_ordered_range(
    *,
    minimum_name: str,
    minimum: float,
    maximum_name: str,
    maximum: float,
) -> None:
    _validate_nonnegative_float(minimum_name, minimum)
    _validate_nonnegative_float(maximum_name, maximum)
    if minimum > maximum:
        raise OHLCVConfigError(
            f"{minimum_name} cannot be greater than {maximum_name}."
        )


def _validate_iso_date(name: str, value: str) -> None:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise OHLCVConfigError(f"{name} must be a YYYY-MM-DD date.") from None
    if parsed.isoformat() != value:
        raise OHLCVConfigError(f"{name} must be a YYYY-MM-DD date.")


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
    eoddata_request_delay_seconds: float = DEFAULT_EODDATA_REQUEST_DELAY_SECONDS
    yahoo_base_url: str = DEFAULT_YAHOO_BASE_URL
    yahoo_request_delay_seconds: float = DEFAULT_YAHOO_REQUEST_DELAY_SECONDS
    yahoo_request_jitter_min_seconds: float = (
        DEFAULT_YAHOO_REQUEST_JITTER_MIN_SECONDS
    )
    yahoo_request_jitter_max_seconds: float = (
        DEFAULT_YAHOO_REQUEST_JITTER_MAX_SECONDS
    )
    yahoo_failure_cooldown_min_seconds: float = (
        DEFAULT_YAHOO_FAILURE_COOLDOWN_MIN_SECONDS
    )
    yahoo_failure_cooldown_max_seconds: float = (
        DEFAULT_YAHOO_FAILURE_COOLDOWN_MAX_SECONDS
    )
    yahoo_backfill_start_date: str = DEFAULT_YAHOO_BACKFILL_START_DATE
    yahoo_backfill_chunk_days: int = DEFAULT_YAHOO_BACKFILL_CHUNK_DAYS
    yahoo_daily_lookback_days: int = DEFAULT_YAHOO_DAILY_LOOKBACK_DAYS
    yahoo_daily_request_max_days: int = DEFAULT_YAHOO_DAILY_REQUEST_MAX_DAYS
    yahoo_reconciliation_sessions: int = DEFAULT_YAHOO_RECONCILIATION_SESSIONS
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
        if (
            not isfinite(self.eoddata_request_delay_seconds)
            or self.eoddata_request_delay_seconds < 0
        ):
            raise OHLCVConfigError(
                f"{EODDATA_REQUEST_DELAY_SECONDS_ENV} cannot be negative."
            )
        _validate_yahoo_base_url(self.yahoo_base_url)
        _validate_nonnegative_float(
            YAHOO_REQUEST_DELAY_SECONDS_ENV,
            self.yahoo_request_delay_seconds,
        )
        _validate_ordered_range(
            minimum_name=YAHOO_REQUEST_JITTER_MIN_SECONDS_ENV,
            minimum=self.yahoo_request_jitter_min_seconds,
            maximum_name=YAHOO_REQUEST_JITTER_MAX_SECONDS_ENV,
            maximum=self.yahoo_request_jitter_max_seconds,
        )
        _validate_ordered_range(
            minimum_name=YAHOO_FAILURE_COOLDOWN_MIN_SECONDS_ENV,
            minimum=self.yahoo_failure_cooldown_min_seconds,
            maximum_name=YAHOO_FAILURE_COOLDOWN_MAX_SECONDS_ENV,
            maximum=self.yahoo_failure_cooldown_max_seconds,
        )
        _validate_iso_date(
            YAHOO_BACKFILL_START_DATE_ENV,
            self.yahoo_backfill_start_date,
        )
        if not 1 <= self.yahoo_backfill_chunk_days <= MAX_YAHOO_BACKFILL_CHUNK_DAYS:
            raise OHLCVConfigError(
                f"{YAHOO_BACKFILL_CHUNK_DAYS_ENV} must be between 1 and "
                f"{MAX_YAHOO_BACKFILL_CHUNK_DAYS}."
            )
        if not 1 <= self.yahoo_daily_lookback_days <= MAX_YAHOO_DAILY_LOOKBACK_DAYS:
            raise OHLCVConfigError(
                f"{YAHOO_DAILY_LOOKBACK_DAYS_ENV} must be between 1 and "
                f"{MAX_YAHOO_DAILY_LOOKBACK_DAYS}."
            )
        if not (
            1
            <= self.yahoo_daily_request_max_days
            <= MAX_YAHOO_DAILY_REQUEST_DAYS
        ):
            raise OHLCVConfigError(
                f"{YAHOO_DAILY_REQUEST_MAX_DAYS_ENV} must be between 1 and "
                f"{MAX_YAHOO_DAILY_REQUEST_DAYS}."
            )
        if not (
            1
            <= self.yahoo_reconciliation_sessions
            <= MAX_YAHOO_RECONCILIATION_SESSIONS
        ):
            raise OHLCVConfigError(
                f"{YAHOO_RECONCILIATION_SESSIONS_ENV} must be between 1 and "
                f"{MAX_YAHOO_RECONCILIATION_SESSIONS}."
            )

    @classmethod
    def from_env(cls) -> "OHLCVConfig":
        """Load configuration from the process environment."""

        storage_key = os.environ.get(STORAGE_KEY_ENV, DEFAULT_STORAGE_KEY).strip()
        api_key = os.environ.get(EODDATA_API_KEY_ENV)
        eoddata_base_url = os.environ.get(
            EODDATA_BASE_URL_ENV,
            DEFAULT_EODDATA_BASE_URL,
        ).strip().rstrip("/")
        yahoo_base_url = os.environ.get(
            YAHOO_BASE_URL_ENV,
            DEFAULT_YAHOO_BASE_URL,
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
            eoddata_request_delay_seconds=_environment_float(
                EODDATA_REQUEST_DELAY_SECONDS_ENV,
                DEFAULT_EODDATA_REQUEST_DELAY_SECONDS,
            ),
            yahoo_base_url=yahoo_base_url,
            yahoo_request_delay_seconds=_environment_float(
                YAHOO_REQUEST_DELAY_SECONDS_ENV,
                DEFAULT_YAHOO_REQUEST_DELAY_SECONDS,
            ),
            yahoo_request_jitter_min_seconds=_environment_float(
                YAHOO_REQUEST_JITTER_MIN_SECONDS_ENV,
                DEFAULT_YAHOO_REQUEST_JITTER_MIN_SECONDS,
            ),
            yahoo_request_jitter_max_seconds=_environment_float(
                YAHOO_REQUEST_JITTER_MAX_SECONDS_ENV,
                DEFAULT_YAHOO_REQUEST_JITTER_MAX_SECONDS,
            ),
            yahoo_failure_cooldown_min_seconds=_environment_float(
                YAHOO_FAILURE_COOLDOWN_MIN_SECONDS_ENV,
                DEFAULT_YAHOO_FAILURE_COOLDOWN_MIN_SECONDS,
            ),
            yahoo_failure_cooldown_max_seconds=_environment_float(
                YAHOO_FAILURE_COOLDOWN_MAX_SECONDS_ENV,
                DEFAULT_YAHOO_FAILURE_COOLDOWN_MAX_SECONDS,
            ),
            yahoo_backfill_start_date=os.environ.get(
                YAHOO_BACKFILL_START_DATE_ENV,
                DEFAULT_YAHOO_BACKFILL_START_DATE,
            ).strip(),
            yahoo_backfill_chunk_days=_environment_int(
                YAHOO_BACKFILL_CHUNK_DAYS_ENV,
                DEFAULT_YAHOO_BACKFILL_CHUNK_DAYS,
            ),
            yahoo_daily_lookback_days=_environment_int(
                YAHOO_DAILY_LOOKBACK_DAYS_ENV,
                DEFAULT_YAHOO_DAILY_LOOKBACK_DAYS,
            ),
            yahoo_daily_request_max_days=_environment_int(
                YAHOO_DAILY_REQUEST_MAX_DAYS_ENV,
                DEFAULT_YAHOO_DAILY_REQUEST_MAX_DAYS,
            ),
            yahoo_reconciliation_sessions=_environment_int(
                YAHOO_RECONCILIATION_SESSIONS_ENV,
                DEFAULT_YAHOO_RECONCILIATION_SESSIONS,
            ),
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
            "eoddata_request_delay_seconds": self.eoddata_request_delay_seconds,
            "eoddata_configured": self.eoddata_credentials is not None,
            "yahoo_base_url": self.yahoo_base_url,
            "yahoo_request_delay_seconds": self.yahoo_request_delay_seconds,
            "yahoo_request_jitter_min_seconds": (
                self.yahoo_request_jitter_min_seconds
            ),
            "yahoo_request_jitter_max_seconds": (
                self.yahoo_request_jitter_max_seconds
            ),
            "yahoo_failure_cooldown_min_seconds": (
                self.yahoo_failure_cooldown_min_seconds
            ),
            "yahoo_failure_cooldown_max_seconds": (
                self.yahoo_failure_cooldown_max_seconds
            ),
            "yahoo_backfill_start_date": self.yahoo_backfill_start_date,
            "yahoo_backfill_chunk_days": self.yahoo_backfill_chunk_days,
            "yahoo_daily_lookback_days": self.yahoo_daily_lookback_days,
            "yahoo_daily_request_max_days": self.yahoo_daily_request_max_days,
            "yahoo_reconciliation_sessions": self.yahoo_reconciliation_sessions,
        }
