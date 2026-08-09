"""Environment-driven configuration for Empire stonks technical indicators."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from empire_stonks_tech_indicators.exceptions import TechIndicatorsConfigError


DEFAULT_CALCULATION_VERSION = "TECH_INDICATORS_V1"
DEFAULT_STORAGE_KEY = "stonks/tech-indicators"
DEFAULT_BENCHMARK_PROVIDER_CODE = "YAHOO"
DEFAULT_BENCHMARK_MARKET = "XIDX"
DEFAULT_BENCHMARK_TICKER = "SPX"
DEFAULT_BENCHMARK_INSTRUMENT_TYPE_CODE = "EQUITY_INDEX"
DEFAULT_BENCHMARK_YAHOO_TICKER = "^GSPC"
DEFAULT_SOURCE_READ_PAGE_SIZE = 10_000
MIN_SOURCE_READ_PAGE_SIZE = 1_000
MAX_SOURCE_READ_PAGE_SIZE = 50_000
DEFAULT_WRITE_BATCH_SIZE = 5_000
MIN_WRITE_BATCH_SIZE = 1_000
MAX_WRITE_BATCH_SIZE = 10_000
HARD_MAX_TRANSACTION_ROWS = 25_000
DEFAULT_DIAGNOSTIC_SAMPLE_LIMIT = 100
MAX_DIAGNOSTIC_SAMPLE_LIMIT = 100

CALCULATION_VERSION_ENV = (
    "EMPIRE_STONKS_TECH_INDICATORS_CALCULATION_VERSION"
)
STORAGE_KEY_ENV = "EMPIRE_STORAGE_KEY_STONKS_TECH_INDICATORS"
BENCHMARK_PROVIDER_CODE_ENV = (
    "EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_PROVIDER_CODE"
)
BENCHMARK_MARKET_ENV = "EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_MARKET"
BENCHMARK_TICKER_ENV = "EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_TICKER"
BENCHMARK_INSTRUMENT_TYPE_CODE_ENV = (
    "EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_INSTRUMENT_TYPE_CODE"
)
BENCHMARK_YAHOO_TICKER_ENV = (
    "EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_YAHOO_TICKER"
)
SOURCE_READ_PAGE_SIZE_ENV = (
    "EMPIRE_STONKS_TECH_INDICATORS_SOURCE_READ_PAGE_SIZE"
)
WRITE_BATCH_SIZE_ENV = "EMPIRE_STONKS_TECH_INDICATORS_WRITE_BATCH_SIZE"
DIAGNOSTIC_SAMPLE_LIMIT_ENV = (
    "EMPIRE_STONKS_TECH_INDICATORS_DIAGNOSTIC_SAMPLE_LIMIT"
)


def _environment_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        raise TechIndicatorsConfigError(f"{name} must be an integer.") from None


def _validate_exact(name: str, value: object, expected: str) -> None:
    if value != expected:
        raise TechIndicatorsConfigError(f"{name} must be {expected}.")


def _validate_int_range(
    name: str,
    value: object,
    minimum: int,
    maximum: int,
) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise TechIndicatorsConfigError(
            f"{name} must be between {minimum} and {maximum}."
        )


def _validate_storage_key(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise TechIndicatorsConfigError(f"{STORAGE_KEY_ENV} is required.")
    parts = value.split("/")
    if value != value.strip() or any(part in {"", ".", ".."} for part in parts):
        raise TechIndicatorsConfigError(
            f"{STORAGE_KEY_ENV} must be a normalized relative storage prefix."
        )


@dataclass(frozen=True)
class BenchmarkConfig:
    """Frozen V1 SPX benchmark identity and resolution expectations."""

    provider_code: str = DEFAULT_BENCHMARK_PROVIDER_CODE
    market: str = DEFAULT_BENCHMARK_MARKET
    ticker: str = DEFAULT_BENCHMARK_TICKER
    instrument_type_code: str = DEFAULT_BENCHMARK_INSTRUMENT_TYPE_CODE
    yahoo_ticker: str = DEFAULT_BENCHMARK_YAHOO_TICKER

    def __post_init__(self) -> None:
        _validate_exact(
            BENCHMARK_PROVIDER_CODE_ENV,
            self.provider_code,
            DEFAULT_BENCHMARK_PROVIDER_CODE,
        )
        _validate_exact(
            BENCHMARK_MARKET_ENV,
            self.market,
            DEFAULT_BENCHMARK_MARKET,
        )
        _validate_exact(
            BENCHMARK_TICKER_ENV,
            self.ticker,
            DEFAULT_BENCHMARK_TICKER,
        )
        _validate_exact(
            BENCHMARK_INSTRUMENT_TYPE_CODE_ENV,
            self.instrument_type_code,
            DEFAULT_BENCHMARK_INSTRUMENT_TYPE_CODE,
        )
        _validate_exact(
            BENCHMARK_YAHOO_TICKER_ENV,
            self.yahoo_ticker,
            DEFAULT_BENCHMARK_YAHOO_TICKER,
        )

    @classmethod
    def from_env(cls) -> BenchmarkConfig:
        """Load the exact V1 benchmark expectations from the environment."""

        return cls(
            provider_code=os.environ.get(
                BENCHMARK_PROVIDER_CODE_ENV,
                DEFAULT_BENCHMARK_PROVIDER_CODE,
            ),
            market=os.environ.get(
                BENCHMARK_MARKET_ENV,
                DEFAULT_BENCHMARK_MARKET,
            ),
            ticker=os.environ.get(
                BENCHMARK_TICKER_ENV,
                DEFAULT_BENCHMARK_TICKER,
            ),
            instrument_type_code=os.environ.get(
                BENCHMARK_INSTRUMENT_TYPE_CODE_ENV,
                DEFAULT_BENCHMARK_INSTRUMENT_TYPE_CODE,
            ),
            yahoo_ticker=os.environ.get(
                BENCHMARK_YAHOO_TICKER_ENV,
                DEFAULT_BENCHMARK_YAHOO_TICKER,
            ),
        )

    def to_safe_dict(self) -> dict[str, str]:
        """Return the non-secret benchmark expectations."""

        return {
            "provider_code": self.provider_code,
            "market": self.market,
            "ticker": self.ticker,
            "instrument_type_code": self.instrument_type_code,
            "yahoo_ticker": self.yahoo_ticker,
        }


@dataclass(frozen=True)
class TechIndicatorsConfig:
    """Validated runtime settings for technical-indicator workflows."""

    calculation_version: str = DEFAULT_CALCULATION_VERSION
    storage_key: str = DEFAULT_STORAGE_KEY
    benchmark: BenchmarkConfig = field(default_factory=BenchmarkConfig)
    source_read_page_size: int = DEFAULT_SOURCE_READ_PAGE_SIZE
    write_batch_size: int = DEFAULT_WRITE_BATCH_SIZE
    diagnostic_sample_limit: int = DEFAULT_DIAGNOSTIC_SAMPLE_LIMIT

    def __post_init__(self) -> None:
        _validate_exact(
            CALCULATION_VERSION_ENV,
            self.calculation_version,
            DEFAULT_CALCULATION_VERSION,
        )
        _validate_storage_key(self.storage_key)
        if not isinstance(self.benchmark, BenchmarkConfig):
            raise TechIndicatorsConfigError(
                "benchmark must be a BenchmarkConfig."
            )
        _validate_int_range(
            SOURCE_READ_PAGE_SIZE_ENV,
            self.source_read_page_size,
            MIN_SOURCE_READ_PAGE_SIZE,
            MAX_SOURCE_READ_PAGE_SIZE,
        )
        _validate_int_range(
            WRITE_BATCH_SIZE_ENV,
            self.write_batch_size,
            MIN_WRITE_BATCH_SIZE,
            MAX_WRITE_BATCH_SIZE,
        )
        _validate_int_range(
            DIAGNOSTIC_SAMPLE_LIMIT_ENV,
            self.diagnostic_sample_limit,
            1,
            MAX_DIAGNOSTIC_SAMPLE_LIMIT,
        )

    @classmethod
    def from_env(cls) -> TechIndicatorsConfig:
        """Load configuration only from the process environment."""

        return cls(
            calculation_version=os.environ.get(
                CALCULATION_VERSION_ENV,
                DEFAULT_CALCULATION_VERSION,
            ),
            storage_key=os.environ.get(STORAGE_KEY_ENV, DEFAULT_STORAGE_KEY),
            benchmark=BenchmarkConfig.from_env(),
            source_read_page_size=_environment_int(
                SOURCE_READ_PAGE_SIZE_ENV,
                DEFAULT_SOURCE_READ_PAGE_SIZE,
            ),
            write_batch_size=_environment_int(
                WRITE_BATCH_SIZE_ENV,
                DEFAULT_WRITE_BATCH_SIZE,
            ),
            diagnostic_sample_limit=_environment_int(
                DIAGNOSTIC_SAMPLE_LIMIT_ENV,
                DEFAULT_DIAGNOSTIC_SAMPLE_LIMIT,
            ),
        )

    def to_safe_dict(self) -> dict[str, str | int | dict[str, str]]:
        """Return bounded non-secret settings for operational output."""

        return {
            "calculation_version": self.calculation_version,
            "storage_key": self.storage_key,
            "benchmark": self.benchmark.to_safe_dict(),
            "source_read_page_size": self.source_read_page_size,
            "write_batch_size": self.write_batch_size,
            "diagnostic_sample_limit": self.diagnostic_sample_limit,
        }
