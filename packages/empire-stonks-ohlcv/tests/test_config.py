from __future__ import annotations

from pathlib import Path

import pytest

from empire_stonks_ohlcv import EODDataCredentials, OHLCVConfig, OHLCVConfigError
from empire_stonks_ohlcv.config import (
    EODDATA_API_KEY_ENV,
    EODDATA_BASE_URL_ENV,
    EODDATA_EXCHANGES_ENV,
    EODDATA_REQUEST_DELAY_SECONDS_ENV,
    HTTP_TIMEOUT_SECONDS_ENV,
    MAX_RETRIES_ENV,
    RAW_RETENTION_DAYS_ENV,
    STORAGE_KEY_ENV,
    YAHOO_BACKFILL_CHUNK_DAYS_ENV,
    YAHOO_BACKFILL_START_DATE_ENV,
    YAHOO_BASE_URL_ENV,
    YAHOO_DAILY_LOOKBACK_DAYS_ENV,
    YAHOO_DAILY_REQUEST_MAX_DAYS_ENV,
    YAHOO_FAILURE_COOLDOWN_MAX_SECONDS_ENV,
    YAHOO_FAILURE_COOLDOWN_MIN_SECONDS_ENV,
    YAHOO_RECONCILIATION_SESSIONS_ENV,
    YAHOO_REQUEST_DELAY_SECONDS_ENV,
    YAHOO_REQUEST_JITTER_MAX_SECONDS_ENV,
    YAHOO_REQUEST_JITTER_MIN_SECONDS_ENV,
)


OHLCV_ENV_VARS = (
    STORAGE_KEY_ENV,
    RAW_RETENTION_DAYS_ENV,
    HTTP_TIMEOUT_SECONDS_ENV,
    MAX_RETRIES_ENV,
    EODDATA_API_KEY_ENV,
    EODDATA_BASE_URL_ENV,
    EODDATA_EXCHANGES_ENV,
    EODDATA_REQUEST_DELAY_SECONDS_ENV,
    YAHOO_BASE_URL_ENV,
    YAHOO_REQUEST_DELAY_SECONDS_ENV,
    YAHOO_REQUEST_JITTER_MIN_SECONDS_ENV,
    YAHOO_REQUEST_JITTER_MAX_SECONDS_ENV,
    YAHOO_FAILURE_COOLDOWN_MIN_SECONDS_ENV,
    YAHOO_FAILURE_COOLDOWN_MAX_SECONDS_ENV,
    YAHOO_BACKFILL_START_DATE_ENV,
    YAHOO_BACKFILL_CHUNK_DAYS_ENV,
    YAHOO_DAILY_LOOKBACK_DAYS_ENV,
    YAHOO_DAILY_REQUEST_MAX_DAYS_ENV,
    YAHOO_RECONCILIATION_SESSIONS_ENV,
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
    assert config.eoddata_request_delay_seconds == 2.0
    assert config.eoddata_credentials is None
    assert config.yahoo_base_url == "https://query2.finance.yahoo.com"
    assert config.yahoo_request_delay_seconds == 25.0
    assert config.yahoo_request_jitter_min_seconds == 5.0
    assert config.yahoo_request_jitter_max_seconds == 10.0
    assert config.yahoo_failure_cooldown_min_seconds == 8.0
    assert config.yahoo_failure_cooldown_max_seconds == 18.0
    assert config.yahoo_backfill_start_date == "1965-01-01"
    assert config.yahoo_backfill_chunk_days == 3650
    assert config.yahoo_daily_lookback_days == 30
    assert config.yahoo_daily_request_max_days == 30
    assert config.yahoo_reconciliation_sessions == 7


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
    monkeypatch.setenv(EODDATA_REQUEST_DELAY_SECONDS_ENV, "3.5")

    config = OHLCVConfig.from_env()

    assert config.eoddata_base_url == "https://market.example.test"
    assert config.eoddata_exchanges == ("NYSE", "NASDAQ", "AMEX")
    assert config.eoddata_request_delay_seconds == 3.5


def test_config_loads_yahoo_source_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(YAHOO_BASE_URL_ENV, "https://market.example.test/")
    monkeypatch.setenv(YAHOO_REQUEST_DELAY_SECONDS_ENV, "12.5")
    monkeypatch.setenv(YAHOO_REQUEST_JITTER_MIN_SECONDS_ENV, "1.5")
    monkeypatch.setenv(YAHOO_REQUEST_JITTER_MAX_SECONDS_ENV, "4.5")
    monkeypatch.setenv(YAHOO_FAILURE_COOLDOWN_MIN_SECONDS_ENV, "20")
    monkeypatch.setenv(YAHOO_FAILURE_COOLDOWN_MAX_SECONDS_ENV, "40")
    monkeypatch.setenv(YAHOO_BACKFILL_START_DATE_ENV, "1970-01-01")
    monkeypatch.setenv(YAHOO_BACKFILL_CHUNK_DAYS_ENV, "730")
    monkeypatch.setenv(YAHOO_DAILY_LOOKBACK_DAYS_ENV, "45")
    monkeypatch.setenv(YAHOO_DAILY_REQUEST_MAX_DAYS_ENV, "15")
    monkeypatch.setenv(YAHOO_RECONCILIATION_SESSIONS_ENV, "5")

    config = OHLCVConfig.from_env()

    assert config.yahoo_base_url == "https://market.example.test"
    assert config.yahoo_request_delay_seconds == 12.5
    assert config.yahoo_request_jitter_min_seconds == 1.5
    assert config.yahoo_request_jitter_max_seconds == 4.5
    assert config.yahoo_failure_cooldown_min_seconds == 20.0
    assert config.yahoo_failure_cooldown_max_seconds == 40.0
    assert config.yahoo_backfill_start_date == "1970-01-01"
    assert config.yahoo_backfill_chunk_days == 730
    assert config.yahoo_daily_lookback_days == 45
    assert config.yahoo_daily_request_max_days == 15
    assert config.yahoo_reconciliation_sessions == 5


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
        (EODDATA_REQUEST_DELAY_SECONDS_ENV, "-1", "cannot be negative"),
        (EODDATA_REQUEST_DELAY_SECONDS_ENV, "nan", "cannot be negative"),
        (EODDATA_REQUEST_DELAY_SECONDS_ENV, "slow", "number"),
        (YAHOO_BASE_URL_ENV, "http://query2.finance.yahoo.com", "HTTPS origin"),
        (YAHOO_BASE_URL_ENV, "https://user@example.test", "without credentials"),
        (YAHOO_BASE_URL_ENV, "https://example.test/api", "without credentials"),
        (YAHOO_REQUEST_DELAY_SECONDS_ENV, "-1", "cannot be negative"),
        (YAHOO_REQUEST_DELAY_SECONDS_ENV, "nan", "cannot be negative"),
        (YAHOO_REQUEST_DELAY_SECONDS_ENV, "slow", "number"),
        (
            YAHOO_REQUEST_JITTER_MIN_SECONDS_ENV,
            "-1",
            "cannot be negative",
        ),
        (
            YAHOO_REQUEST_JITTER_MAX_SECONDS_ENV,
            "nan",
            "cannot be negative",
        ),
        (
            YAHOO_FAILURE_COOLDOWN_MIN_SECONDS_ENV,
            "-1",
            "cannot be negative",
        ),
        (
            YAHOO_FAILURE_COOLDOWN_MAX_SECONDS_ENV,
            "slow",
            "number",
        ),
        (YAHOO_BACKFILL_START_DATE_ENV, "01-01-1965", "YYYY-MM-DD"),
        (YAHOO_BACKFILL_CHUNK_DAYS_ENV, "0", "between 1 and 3650"),
        (YAHOO_BACKFILL_CHUNK_DAYS_ENV, "3651", "between 1 and 3650"),
        (YAHOO_DAILY_LOOKBACK_DAYS_ENV, "0", "between 1 and 365"),
        (YAHOO_DAILY_LOOKBACK_DAYS_ENV, "366", "between 1 and 365"),
        (YAHOO_DAILY_REQUEST_MAX_DAYS_ENV, "0", "between 1 and 90"),
        (YAHOO_DAILY_REQUEST_MAX_DAYS_ENV, "91", "between 1 and 90"),
        (YAHOO_RECONCILIATION_SESSIONS_ENV, "0", "between 1 and 30"),
        (YAHOO_RECONCILIATION_SESSIONS_ENV, "31", "between 1 and 30"),
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


@pytest.mark.parametrize(
    ("minimum_name", "maximum_name"),
    [
        (
            YAHOO_REQUEST_JITTER_MIN_SECONDS_ENV,
            YAHOO_REQUEST_JITTER_MAX_SECONDS_ENV,
        ),
        (
            YAHOO_FAILURE_COOLDOWN_MIN_SECONDS_ENV,
            YAHOO_FAILURE_COOLDOWN_MAX_SECONDS_ENV,
        ),
    ],
)
def test_config_rejects_reversed_yahoo_ranges(
    monkeypatch: pytest.MonkeyPatch,
    minimum_name: str,
    maximum_name: str,
) -> None:
    monkeypatch.setenv(minimum_name, "5")
    monkeypatch.setenv(maximum_name, "4")

    with pytest.raises(OHLCVConfigError, match="cannot be greater"):
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
