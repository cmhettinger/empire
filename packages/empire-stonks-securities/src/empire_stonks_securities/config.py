"""Configuration loading for Empire stonks securities."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from empire_stonks_securities.exceptions import StonksSecuritiesConfigError


DEFAULT_SEC_BASE_URL = "https://www.sec.gov"
DEFAULT_SEC_ARCHIVES_URL = "https://www.sec.gov/Archives"
SUPPORTED_PROVIDER_FORMATS = frozenset({"idx", "json", "sgml", "zip"})


@dataclass(frozen=True)
class SecConfig:
    """SEC connection settings."""

    user_agent: str
    base_url: str = DEFAULT_SEC_BASE_URL
    archives_url: str = DEFAULT_SEC_ARCHIVES_URL

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SecConfig":
        if not isinstance(data, dict):
            raise StonksSecuritiesConfigError("stonks_securities.sec must be a mapping.")
        return cls(
            user_agent=_as_str(data.get("user_agent"), "stonks_securities.sec.user_agent"),
            base_url=_as_url(
                data.get("base_url", DEFAULT_SEC_BASE_URL),
                "stonks_securities.sec.base_url",
            ),
            archives_url=_as_url(
                data.get("archives_url", DEFAULT_SEC_ARCHIVES_URL),
                "stonks_securities.sec.archives_url",
            ),
        )


@dataclass(frozen=True)
class RateLimitConfig:
    """Request throttling settings for SEC traffic."""

    requests_per_second: float
    burst_size: int
    throttle_on_429: bool = True
    retry_after_header: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "RateLimitConfig":
        if data is not None and not isinstance(data, dict):
            raise StonksSecuritiesConfigError("stonks_securities.rate_limit must be a mapping.")
        data = data or {}
        requests_per_second = _as_float(
            data.get("requests_per_second", 5),
            "stonks_securities.rate_limit.requests_per_second",
        )
        if requests_per_second <= 0:
            raise StonksSecuritiesConfigError(
                "stonks_securities.rate_limit.requests_per_second must be greater than zero."
            )
        burst_size = _as_int(
            data.get("burst_size", 10),
            "stonks_securities.rate_limit.burst_size",
        )
        if burst_size < 1:
            raise StonksSecuritiesConfigError(
                "stonks_securities.rate_limit.burst_size must be greater than zero."
            )
        return cls(
            requests_per_second=requests_per_second,
            burst_size=burst_size,
            throttle_on_429=_as_bool(
                data.get("throttle_on_429", True),
                "stonks_securities.rate_limit.throttle_on_429",
            ),
            retry_after_header=_as_bool(
                data.get("retry_after_header", True),
                "stonks_securities.rate_limit.retry_after_header",
            ),
        )


@dataclass(frozen=True)
class StorageConfig:
    """Raw and processed object retention settings."""

    store_raw_files: bool = True
    delete_processed_files_after_processing: bool = True
    retention_days_raw: int = 5
    retention_days_processed: int = 5

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "StorageConfig":
        if data is not None and not isinstance(data, dict):
            raise StonksSecuritiesConfigError("stonks_securities.storage must be a mapping.")
        data = data or {}
        retention_days_raw = _as_int(
            data.get("retention_days_raw", 5),
            "stonks_securities.storage.retention_days_raw",
        )
        retention_days_processed = _as_int(
            data.get("retention_days_processed", 5),
            "stonks_securities.storage.retention_days_processed",
        )
        if retention_days_raw < 0:
            raise StonksSecuritiesConfigError(
                "stonks_securities.storage.retention_days_raw cannot be negative."
            )
        if retention_days_processed < 0:
            raise StonksSecuritiesConfigError(
                "stonks_securities.storage.retention_days_processed cannot be negative."
            )
        return cls(
            store_raw_files=_as_bool(
                data.get("store_raw_files", True),
                "stonks_securities.storage.store_raw_files",
            ),
            delete_processed_files_after_processing=_as_bool(
                data.get("delete_processed_files_after_processing", True),
                "stonks_securities.storage.delete_processed_files_after_processing",
            ),
            retention_days_raw=retention_days_raw,
            retention_days_processed=retention_days_processed,
        )


@dataclass(frozen=True)
class QuarterlyMasterIndexConfig:
    """Quarterly EDGAR master index acquisition range."""

    start_year: int = 1995
    end_year: int | None = None
    quarters: tuple[int, ...] = (1, 2, 3, 4)

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "QuarterlyMasterIndexConfig":
        if data is not None and not isinstance(data, dict):
            raise StonksSecuritiesConfigError(
                "stonks_securities.download.quarterly_master_index must be a mapping."
            )
        data = data or {}
        quarters_data = data.get("quarters", [1, 2, 3, 4])
        if not isinstance(quarters_data, list) or not quarters_data:
            raise StonksSecuritiesConfigError(
                "stonks_securities.download.quarterly_master_index.quarters must be a non-empty list."
            )
        quarters = tuple(
            _as_int(
                quarter,
                "stonks_securities.download.quarterly_master_index.quarters[]",
            )
            for quarter in quarters_data
        )
        invalid_quarters = [quarter for quarter in quarters if quarter < 1 or quarter > 4]
        if invalid_quarters:
            raise StonksSecuritiesConfigError(
                "stonks_securities.download.quarterly_master_index.quarters must contain values 1-4."
            )
        return cls(
            start_year=_as_int(
                data.get("start_year", 1995),
                "stonks_securities.download.quarterly_master_index.start_year",
            ),
            end_year=_optional_int(
                data.get("end_year"),
                "stonks_securities.download.quarterly_master_index.end_year",
            ),
            quarters=quarters,
        )


@dataclass(frozen=True)
class DownloadConfig:
    """Download behavior for source files."""

    checksum_validation: bool = True
    resume_partial_downloads: bool = True
    overwrite_existing: bool = False
    quarterly_master_index: QuarterlyMasterIndexConfig = field(
        default_factory=QuarterlyMasterIndexConfig
    )

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "DownloadConfig":
        if data is not None and not isinstance(data, dict):
            raise StonksSecuritiesConfigError("stonks_securities.download must be a mapping.")
        data = data or {}
        return cls(
            checksum_validation=_as_bool(
                data.get("checksum_validation", True),
                "stonks_securities.download.checksum_validation",
            ),
            resume_partial_downloads=_as_bool(
                data.get("resume_partial_downloads", True),
                "stonks_securities.download.resume_partial_downloads",
            ),
            overwrite_existing=_as_bool(
                data.get("overwrite_existing", False),
                "stonks_securities.download.overwrite_existing",
            ),
            quarterly_master_index=QuarterlyMasterIndexConfig.from_mapping(
                data.get("quarterly_master_index")
            ),
        )


@dataclass(frozen=True)
class ProviderConfig:
    """One configured securities reference-data provider endpoint."""

    key: str
    provider_code: str
    enabled: bool
    expected_format: str
    description: str
    url: str | None = None
    url_template: str | None = None

    @classmethod
    def from_mapping(cls, key: str, data: dict[str, Any]) -> "ProviderConfig":
        if not isinstance(data, dict):
            raise StonksSecuritiesConfigError(
                f"stonks_securities.providers.{key} must be a mapping."
            )
        url = _optional_url(data.get("url"), f"stonks_securities.providers.{key}.url")
        url_template = _optional_url_template(
            data.get("url_template"),
            f"stonks_securities.providers.{key}.url_template",
        )
        if not url and not url_template:
            raise StonksSecuritiesConfigError(
                f"stonks_securities.providers.{key} must define url or url_template."
            )
        if url and url_template:
            raise StonksSecuritiesConfigError(
                f"stonks_securities.providers.{key} cannot define both url and url_template."
            )
        expected_format = _as_str(
            data.get("expected_format"),
            f"stonks_securities.providers.{key}.expected_format",
        )
        if expected_format not in SUPPORTED_PROVIDER_FORMATS:
            raise StonksSecuritiesConfigError(
                f"stonks_securities.providers.{key}.expected_format must be one of: "
                f"{', '.join(sorted(SUPPORTED_PROVIDER_FORMATS))}."
            )
        return cls(
            key=key,
            provider_code=_as_str(
                data.get("provider_code"),
                f"stonks_securities.providers.{key}.provider_code",
            ),
            enabled=_as_bool(data.get("enabled", True), f"stonks_securities.providers.{key}.enabled"),
            url=url,
            url_template=url_template,
            expected_format=expected_format,
            description=_as_str(
                data.get("description"),
                f"stonks_securities.providers.{key}.description",
            ),
        )


@dataclass(frozen=True)
class HistoricalBackfillConfig:
    """Historical backfill date range."""

    start_date: str
    end_date: str | None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "HistoricalBackfillConfig":
        if data is not None and not isinstance(data, dict):
            raise StonksSecuritiesConfigError(
                "stonks_securities.processing.historical_backfill must be a mapping."
            )
        data = data or {}
        return cls(
            start_date=_as_str(
                data.get("start_date"),
                "stonks_securities.processing.historical_backfill.start_date",
            ),
            end_date=_optional_str(
                data.get("end_date"),
                "stonks_securities.processing.historical_backfill.end_date",
            ),
        )


@dataclass(frozen=True)
class DailyRefreshConfig:
    """Daily refresh settings."""

    enabled: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "DailyRefreshConfig":
        if data is not None and not isinstance(data, dict):
            raise StonksSecuritiesConfigError(
                "stonks_securities.processing.daily_refresh must be a mapping."
            )
        data = data or {}
        return cls(
            enabled=_as_bool(
                data.get("enabled", True),
                "stonks_securities.processing.daily_refresh.enabled",
            )
        )


@dataclass(frozen=True)
class ValidationConfig:
    """Downloaded file validation switches."""

    verify_content_type: bool = True
    verify_non_empty_file: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "ValidationConfig":
        if data is not None and not isinstance(data, dict):
            raise StonksSecuritiesConfigError(
                "stonks_securities.processing.validation must be a mapping."
            )
        data = data or {}
        return cls(
            verify_content_type=_as_bool(
                data.get("verify_content_type", True),
                "stonks_securities.processing.validation.verify_content_type",
            ),
            verify_non_empty_file=_as_bool(
                data.get("verify_non_empty_file", True),
                "stonks_securities.processing.validation.verify_non_empty_file",
            ),
        )


@dataclass(frozen=True)
class ProcessingConfig:
    """Processing policy for securities reference data."""

    historical_backfill: HistoricalBackfillConfig
    daily_refresh: DailyRefreshConfig = field(default_factory=DailyRefreshConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "ProcessingConfig":
        if data is not None and not isinstance(data, dict):
            raise StonksSecuritiesConfigError("stonks_securities.processing must be a mapping.")
        data = data or {}
        return cls(
            historical_backfill=HistoricalBackfillConfig.from_mapping(
                data.get("historical_backfill")
            ),
            daily_refresh=DailyRefreshConfig.from_mapping(data.get("daily_refresh")),
            validation=ValidationConfig.from_mapping(data.get("validation")),
        )


@dataclass(frozen=True)
class StonksSecuritiesConfig:
    """Run configuration for stonks securities reference data."""

    name: str
    version: int
    sec: SecConfig
    providers: list[ProviderConfig]
    processing: ProcessingConfig
    timeout_seconds: float = 60.0
    max_retries: int = 5
    retry_backoff_seconds: float = 5.0
    respect_rate_limits: bool = True
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)

    @classmethod
    def from_file(cls, path: str | Path) -> "StonksSecuritiesConfig":
        return cls.from_yaml(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def from_yaml(cls, text: str) -> "StonksSecuritiesConfig":
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise StonksSecuritiesConfigError(
                f"Invalid stonks securities config YAML: {exc}"
            ) from exc
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "StonksSecuritiesConfig":
        if not isinstance(data, dict):
            raise StonksSecuritiesConfigError("Stonks securities config must be a mapping.")
        config = data.get("stonks_securities", data)
        if not isinstance(config, dict):
            raise StonksSecuritiesConfigError("stonks_securities must be a mapping.")
        providers_data = config.get("providers")
        if not isinstance(providers_data, dict) or not providers_data:
            raise StonksSecuritiesConfigError(
                "stonks_securities.providers must be a non-empty mapping."
            )
        providers = [
            ProviderConfig.from_mapping(key, provider_data)
            for key, provider_data in providers_data.items()
        ]
        enabled_providers = [provider for provider in providers if provider.enabled]
        if not enabled_providers:
            raise StonksSecuritiesConfigError(
                "stonks_securities.providers must include at least one enabled provider."
            )
        _validate_unique(
            [provider.provider_code for provider in providers],
            "stonks_securities.providers[].provider_code",
        )
        timeout_seconds = _as_float(
            config.get("timeout_seconds", 60.0),
            "stonks_securities.timeout_seconds",
        )
        if timeout_seconds <= 0:
            raise StonksSecuritiesConfigError(
                "stonks_securities.timeout_seconds must be greater than zero."
            )
        max_retries = _as_int(config.get("max_retries", 5), "stonks_securities.max_retries")
        if max_retries < 0:
            raise StonksSecuritiesConfigError("stonks_securities.max_retries cannot be negative.")
        retry_backoff_seconds = _as_float(
            config.get("retry_backoff_seconds", 5.0),
            "stonks_securities.retry_backoff_seconds",
        )
        if retry_backoff_seconds < 0:
            raise StonksSecuritiesConfigError(
                "stonks_securities.retry_backoff_seconds cannot be negative."
            )
        return cls(
            name=_as_str(config.get("name"), "stonks_securities.name"),
            version=_as_int(config.get("version"), "stonks_securities.version"),
            sec=SecConfig.from_mapping(config.get("sec")),
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            respect_rate_limits=_as_bool(
                config.get("respect_rate_limits", True),
                "stonks_securities.respect_rate_limits",
            ),
            rate_limit=RateLimitConfig.from_mapping(config.get("rate_limit")),
            storage=StorageConfig.from_mapping(config.get("storage")),
            download=DownloadConfig.from_mapping(config.get("download")),
            providers=providers,
            processing=ProcessingConfig.from_mapping(config.get("processing")),
        )

    @property
    def enabled_providers(self) -> list[ProviderConfig]:
        return [provider for provider in self.providers if provider.enabled]


def _as_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StonksSecuritiesConfigError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _optional_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _as_str(value, field_name)


def _as_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise StonksSecuritiesConfigError(f"{field_name} must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise StonksSecuritiesConfigError(f"{field_name} must be an integer.") from exc


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    return _as_int(value, field_name)


def _as_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise StonksSecuritiesConfigError(f"{field_name} must be a number.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise StonksSecuritiesConfigError(f"{field_name} must be a number.") from exc


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise StonksSecuritiesConfigError(f"{field_name} must be a boolean.")


def _optional_url(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _as_url(value, field_name)


def _optional_url_template(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _as_url_template(value, field_name)


def _as_url(value: Any, field_name: str) -> str:
    url = _as_str(value, field_name)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise StonksSecuritiesConfigError(f"{field_name} must be an https URL.")
    return url


def _as_url_template(value: Any, field_name: str) -> str:
    template = _as_str(value, field_name)
    probe = template.replace("{year}", "2026").replace("{quarter}", "1")
    parsed = urlparse(probe)
    if parsed.scheme != "https" or not parsed.netloc:
        raise StonksSecuritiesConfigError(f"{field_name} must be an https URL template.")
    return template


def _validate_unique(values: list[str], field_name: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise StonksSecuritiesConfigError(
            f"{field_name} must be unique. Duplicate value(s): {', '.join(duplicates)}"
        )
