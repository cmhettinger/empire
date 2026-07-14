"""Environment-driven configuration for Empire stonks OHLCV ingestion."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from math import isfinite
from typing import Self

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


class EODDataCredentials:
    """Immutable EODData credentials with redacted representations."""

    __slots__ = ("_username", "_password")

    def __init__(self, *, username: str, password: str) -> None:
        if not username.strip():
            raise OHLCVConfigError(f"{EODDATA_USERNAME_ENV} is required.")
        if not password:
            raise OHLCVConfigError(f"{EODDATA_PASSWORD_ENV} is required.")
        object.__setattr__(self, "_username", username)
        object.__setattr__(self, "_password", password)

    @property
    def username(self) -> str:
        """Return the username for provider authentication only."""

        return self._username

    @property
    def password(self) -> str:
        """Return the password for provider authentication only."""

        return self._password

    def __setattr__(self, name: str, _value: object) -> None:
        raise AttributeError(
            f"{type(self).__name__} is immutable; cannot set {name}"
        )

    def __repr__(self) -> str:
        return "EODDataCredentials(username=<redacted>, password=<redacted>)"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EODDataCredentials):
            return NotImplemented
        return self.username == other.username and self.password == other.password

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

    def to_safe_dict(self) -> dict[str, str | int | float | bool]:
        """Return non-secret settings safe for operational payloads and logs."""

        return {
            "storage_key": self.storage_key,
            "raw_retention_days": self.raw_retention_days,
            "http_timeout_seconds": self.http_timeout_seconds,
            "max_retries": self.max_retries,
            "eoddata_configured": self.eoddata_credentials is not None,
        }
