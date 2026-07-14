from __future__ import annotations

from pathlib import Path

import pytest

from empire_stonks_ohlcv import EODDataCredentials, OHLCVConfig, OHLCVConfigError
from empire_stonks_ohlcv.config import (
    EODDATA_PASSWORD_ENV,
    EODDATA_USERNAME_ENV,
    HTTP_TIMEOUT_SECONDS_ENV,
    MAX_RETRIES_ENV,
    RAW_RETENTION_DAYS_ENV,
    STORAGE_KEY_ENV,
)


OHLCV_ENV_VARS = (
    STORAGE_KEY_ENV,
    RAW_RETENTION_DAYS_ENV,
    HTTP_TIMEOUT_SECONDS_ENV,
    MAX_RETRIES_ENV,
    EODDATA_USERNAME_ENV,
    EODDATA_PASSWORD_ENV,
)


@pytest.fixture(autouse=True)
def clear_ohlcv_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in OHLCV_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_config_uses_defaults() -> None:
    config = OHLCVConfig.from_env()

    assert config.storage_key == "stonks/ohlcv"
    assert config.raw_retention_days == 7
    assert config.http_timeout_seconds == 30.0
    assert config.max_retries == 3
    assert config.eoddata_credentials is None


def test_config_loads_common_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STORAGE_KEY_ENV, "custom/ohlcv")
    monkeypatch.setenv(RAW_RETENTION_DAYS_ENV, "14")
    monkeypatch.setenv(HTTP_TIMEOUT_SECONDS_ENV, "45.5")
    monkeypatch.setenv(MAX_RETRIES_ENV, "5")

    config = OHLCVConfig.from_env()

    assert config.storage_key == "custom/ohlcv"
    assert config.raw_retention_days == 14
    assert config.http_timeout_seconds == 45.5
    assert config.max_retries == 5


def test_config_loads_eoddata_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(EODDATA_USERNAME_ENV, "market-user")
    monkeypatch.setenv(EODDATA_PASSWORD_ENV, "market-password")

    config = OHLCVConfig.from_env()

    assert config.eoddata_credentials == EODDataCredentials(
        username="market-user",
        password="market-password",
    )
    assert config.require_eoddata_credentials() == config.eoddata_credentials


@pytest.mark.parametrize(
    ("present_name", "present_value", "missing_name"),
    [
        (EODDATA_USERNAME_ENV, "market-user", EODDATA_PASSWORD_ENV),
        (EODDATA_PASSWORD_ENV, "market-password", EODDATA_USERNAME_ENV),
    ],
)
def test_config_rejects_incomplete_eoddata_credentials(
    monkeypatch: pytest.MonkeyPatch,
    present_name: str,
    present_value: str,
    missing_name: str,
) -> None:
    monkeypatch.setenv(present_name, present_value)

    with pytest.raises(OHLCVConfigError, match=missing_name):
        OHLCVConfig.from_env()


def test_eoddata_credentials_can_be_required() -> None:
    with pytest.raises(OHLCVConfigError, match=EODDATA_USERNAME_ENV):
        OHLCVConfig.from_env().require_eoddata_credentials()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        (STORAGE_KEY_ENV, " ", "required"),
        (RAW_RETENTION_DAYS_ENV, "0", "greater than zero"),
        (HTTP_TIMEOUT_SECONDS_ENV, "0", "greater than zero"),
        (HTTP_TIMEOUT_SECONDS_ENV, "nan", "greater than zero"),
        (MAX_RETRIES_ENV, "-1", "cannot be negative"),
        (RAW_RETENTION_DAYS_ENV, "seven", "integer"),
        (HTTP_TIMEOUT_SECONDS_ENV, "slow", "number"),
    ],
)
def test_config_rejects_invalid_common_values(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(OHLCVConfigError, match=message):
        OHLCVConfig.from_env()


def test_config_does_not_load_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        f"{EODDATA_USERNAME_ENV}=file-user\n"
        f"{EODDATA_PASSWORD_ENV}=file-password\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = OHLCVConfig.from_env()

    assert config.eoddata_credentials is None
