"""Environment-driven configuration for Empire stonks OHLCV ingestion."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from math import isfinite

from empire_stonks_ohlcv.exceptions import OHLCVConfigError


DEFAULT_STORAGE_KEY = "stonks/ohlcv"
DEFAULT_RAW_RETENTION_DAYS = 7
DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3

STORAGE_KEY_ENV = "EMPIRE_STORAGE_KEY_STONKS_OHLCV"
RAW_RETENTION_DAYS_ENV = "EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS"
HTTP_TIMEOUT_SECONDS_ENV = "EMPIRE_STONKS_OHLCV_HTTP_TIMEOUT_SECONDS"
MAX_RETRIES_ENV = "EMPIRE_STONKS_OHLCV_MAX_RETRIES"
EODDATA_USERNAME_ENV = "EMPIRE_STONKS_OHLCV_EODDATA_USERNAME"
EODDATA_PASSWORD_ENV = "EMPIRE_STONKS_OHLCV_EODDATA_PASSWORD"


def _environment_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise OHLCVConfigError(f"{name} must be an integer.") from exc


def _environment_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise OHLCVConfigError(f"{name} must be a number.") from exc


@dataclass(frozen=True)
class EODDataCredentials:
    """Credentials required by EODData acquisition."""

    username: str = field(repr=False)
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.username.strip():
            raise OHLCVConfigError(f"{EODDATA_USERNAME_ENV} is required.")
        if not self.password:
            raise OHLCVConfigError(f"{EODDATA_PASSWORD_ENV} is required.")


@dataclass(frozen=True)
class OHLCVConfig:
    """Common runtime settings and configured provider credentials."""

    storage_key: str = DEFAULT_STORAGE_KEY
    raw_retention_days: int = DEFAULT_RAW_RETENTION_DAYS
    http_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    eoddata_credentials: EODDataCredentials | None = None

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

    @classmethod
    def from_env(cls) -> "OHLCVConfig":
        """Load configuration from the process environment."""

        storage_key = os.environ.get(STORAGE_KEY_ENV, DEFAULT_STORAGE_KEY).strip()
        username = os.environ.get(EODDATA_USERNAME_ENV)
        password = os.environ.get(EODDATA_PASSWORD_ENV)

        credentials: EODDataCredentials | None = None
        if username or password:
            credentials = EODDataCredentials(
                username=username or "",
                password=password or "",
            )

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
            eoddata_credentials=credentials,
        )

    def require_eoddata_credentials(self) -> EODDataCredentials:
        """Return configured EODData credentials or raise a clear error."""

        if self.eoddata_credentials is None:
            raise OHLCVConfigError(
                f"{EODDATA_USERNAME_ENV} and {EODDATA_PASSWORD_ENV} are required "
                "for EODData acquisition."
            )
        return self.eoddata_credentials
