from __future__ import annotations

from pathlib import Path

import pytest

from empire_stonks_ohlcv import EODDataCredentials, OHLCVConfig, OHLCVConfigError
from empire_stonks_ohlcv.config import (
    EODDATA_API_KEY_ENV,
    EODDATA_BASE_URL_ENV,
    EODDATA_EXCHANGES_ENV,
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
    EODDATA_API_KEY_ENV,
    EODDATA_BASE_URL_ENV,
    EODDATA_EXCHANGES_ENV,
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
    assert config.eoddata_base_url == "https://api.eoddata.com"
    assert config.eoddata_exchanges == ("NYSE", "NASDAQ", "AMEX")
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
    monkeypatch.setenv(EODDATA_API_KEY_ENV, "market-api-key")

    config = OHLCVConfig.from_env()

    assert config.eoddata_credentials == EODDataCredentials(
        api_key="market-api-key",
    )
    assert config.require_eoddata_credentials() == config.eoddata_credentials


def test_eoddata_credentials_can_be_required() -> None:
    with pytest.raises(OHLCVConfigError, match=EODDATA_API_KEY_ENV):
        OHLCVConfig.from_env().require_eoddata_credentials()


def test_config_loads_eoddata_source_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(EODDATA_BASE_URL_ENV, "https://market.example.test/")
    monkeypatch.setenv(EODDATA_EXCHANGES_ENV, "NYSE, NASDAQ, AMEX")

    config = OHLCVConfig.from_env()

    assert config.eoddata_base_url == "https://market.example.test"
    assert config.eoddata_exchanges == ("NYSE", "NASDAQ", "AMEX")


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
        (EODDATA_BASE_URL_ENV, "http://api.eoddata.com", "HTTPS origin"),
        (EODDATA_BASE_URL_ENV, "https://user@example.test", "without credentials"),
        (EODDATA_BASE_URL_ENV, "https://example.test/api", "without credentials"),
        (EODDATA_BASE_URL_ENV, "https://example.test?key=value", "without credentials"),
        (EODDATA_EXCHANGES_ENV, "NASDAQ,NYSE,AMEX", "NYSE,NASDAQ,AMEX"),
        (EODDATA_EXCHANGES_ENV, "NYSE,NASDAQ", "NYSE,NASDAQ,AMEX"),
        (EODDATA_EXCHANGES_ENV, "NYSE,NASDAQ,AMEX,AMEX", "NYSE,NASDAQ,AMEX"),
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
        f"{EODDATA_API_KEY_ENV}=file-api-key\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = OHLCVConfig.from_env()

    assert config.eoddata_credentials is None
