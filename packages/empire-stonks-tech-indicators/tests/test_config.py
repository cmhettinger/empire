from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from empire_stonks_tech_indicators import (
    BenchmarkConfig,
    TechIndicatorsConfig,
    TechIndicatorsConfigError,
)
from empire_stonks_tech_indicators.config import (
    BENCHMARK_INSTRUMENT_TYPE_CODE_ENV,
    BENCHMARK_MARKET_ENV,
    BENCHMARK_PROVIDER_CODE_ENV,
    BENCHMARK_TICKER_ENV,
    BENCHMARK_YAHOO_TICKER_ENV,
    CALCULATION_VERSION_ENV,
    DIAGNOSTIC_SAMPLE_LIMIT_ENV,
    SOURCE_READ_PAGE_SIZE_ENV,
    STORAGE_KEY_ENV,
    WRITE_BATCH_SIZE_ENV,
)


CONFIG_ENV_VARS = (
    CALCULATION_VERSION_ENV,
    STORAGE_KEY_ENV,
    BENCHMARK_PROVIDER_CODE_ENV,
    BENCHMARK_MARKET_ENV,
    BENCHMARK_TICKER_ENV,
    BENCHMARK_INSTRUMENT_TYPE_CODE_ENV,
    BENCHMARK_YAHOO_TICKER_ENV,
    SOURCE_READ_PAGE_SIZE_ENV,
    WRITE_BATCH_SIZE_ENV,
    DIAGNOSTIC_SAMPLE_LIMIT_ENV,
)


@pytest.fixture(autouse=True)
def clear_config_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CONFIG_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_config_uses_frozen_defaults() -> None:
    config = TechIndicatorsConfig.from_env()

    assert config.calculation_version == "TECH_INDICATORS_V1"
    assert config.storage_key == "stonks/tech-indicators"
    assert config.benchmark == BenchmarkConfig(
        provider_code="YAHOO",
        market="XIDX",
        ticker="SPX",
        instrument_type_code="EQUITY_INDEX",
        yahoo_ticker="^GSPC",
    )
    assert config.source_read_page_size == 10_000
    assert config.write_batch_size == 5_000
    assert config.diagnostic_sample_limit == 100


def test_config_loads_safe_tunable_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STORAGE_KEY_ENV, "custom/tech-indicators")
    monkeypatch.setenv(SOURCE_READ_PAGE_SIZE_ENV, "25000")
    monkeypatch.setenv(WRITE_BATCH_SIZE_ENV, "7500")
    monkeypatch.setenv(DIAGNOSTIC_SAMPLE_LIMIT_ENV, "25")

    config = TechIndicatorsConfig.from_env()

    assert config.storage_key == "custom/tech-indicators"
    assert config.source_read_page_size == 25_000
    assert config.write_batch_size == 7_500
    assert config.diagnostic_sample_limit == 25


@pytest.mark.parametrize(
    ("name", "value", "attribute", "expected"),
    [
        (SOURCE_READ_PAGE_SIZE_ENV, "1000", "source_read_page_size", 1_000),
        (SOURCE_READ_PAGE_SIZE_ENV, "50000", "source_read_page_size", 50_000),
        (WRITE_BATCH_SIZE_ENV, "1000", "write_batch_size", 1_000),
        (WRITE_BATCH_SIZE_ENV, "10000", "write_batch_size", 10_000),
        (DIAGNOSTIC_SAMPLE_LIMIT_ENV, "1", "diagnostic_sample_limit", 1),
        (DIAGNOSTIC_SAMPLE_LIMIT_ENV, "100", "diagnostic_sample_limit", 100),
    ],
)
def test_config_accepts_inclusive_tuning_bounds(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    attribute: str,
    expected: int,
) -> None:
    monkeypatch.setenv(name, value)

    assert getattr(TechIndicatorsConfig.from_env(), attribute) == expected


def test_config_accepts_explicit_frozen_identity_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        CALCULATION_VERSION_ENV: "TECH_INDICATORS_V1",
        BENCHMARK_PROVIDER_CODE_ENV: "YAHOO",
        BENCHMARK_MARKET_ENV: "XIDX",
        BENCHMARK_TICKER_ENV: "SPX",
        BENCHMARK_INSTRUMENT_TYPE_CODE_ENV: "EQUITY_INDEX",
        BENCHMARK_YAHOO_TICKER_ENV: "^GSPC",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    assert TechIndicatorsConfig.from_env() == TechIndicatorsConfig()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        (CALCULATION_VERSION_ENV, "TECH_INDICATORS_V2", "TECH_INDICATORS_V1"),
        (STORAGE_KEY_ENV, "", "required"),
        (STORAGE_KEY_ENV, " /absolute", "normalized relative"),
        (STORAGE_KEY_ENV, "stonks//tech", "normalized relative"),
        (SOURCE_READ_PAGE_SIZE_ENV, "999", "between 1000 and 50000"),
        (SOURCE_READ_PAGE_SIZE_ENV, "50001", "between 1000 and 50000"),
        (WRITE_BATCH_SIZE_ENV, "999", "between 1000 and 10000"),
        (WRITE_BATCH_SIZE_ENV, "10001", "between 1000 and 10000"),
        (DIAGNOSTIC_SAMPLE_LIMIT_ENV, "0", "between 1 and 100"),
        (DIAGNOSTIC_SAMPLE_LIMIT_ENV, "101", "between 1 and 100"),
        (SOURCE_READ_PAGE_SIZE_ENV, "many", "integer"),
    ],
)
def test_config_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(TechIndicatorsConfigError, match=message):
        TechIndicatorsConfig.from_env()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (BENCHMARK_PROVIDER_CODE_ENV, "STOOQ"),
        (BENCHMARK_MARKET_ENV, "xidx"),
        (BENCHMARK_TICKER_ENV, "^GSPC"),
        (BENCHMARK_INSTRUMENT_TYPE_CODE_ENV, "UNKNOWN"),
        (BENCHMARK_YAHOO_TICKER_ENV, "SPX"),
    ],
)
def test_config_rejects_benchmark_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(TechIndicatorsConfigError, match=name):
        TechIndicatorsConfig.from_env()


def test_direct_config_rejects_non_integer_bool() -> None:
    with pytest.raises(TechIndicatorsConfigError, match=SOURCE_READ_PAGE_SIZE_ENV):
        TechIndicatorsConfig(source_read_page_size=True)


def test_config_is_immutable() -> None:
    config = TechIndicatorsConfig()

    with pytest.raises(FrozenInstanceError):
        config.write_batch_size = 1_000  # type: ignore[misc]


def test_config_safe_dict_is_bounded_and_secret_free() -> None:
    config = TechIndicatorsConfig()

    assert config.to_safe_dict() == {
        "calculation_version": "TECH_INDICATORS_V1",
        "storage_key": "stonks/tech-indicators",
        "benchmark": {
            "provider_code": "YAHOO",
            "market": "XIDX",
            "ticker": "SPX",
            "instrument_type_code": "EQUITY_INDEX",
            "yahoo_ticker": "^GSPC",
        },
        "source_read_page_size": 10_000,
        "write_batch_size": 5_000,
        "diagnostic_sample_limit": 100,
    }


def test_config_does_not_load_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        f"{WRITE_BATCH_SIZE_ENV}=7500\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = TechIndicatorsConfig.from_env()

    assert config.write_batch_size == 5_000
