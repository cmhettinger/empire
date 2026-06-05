"""Configuration loading for Empire weather collection."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from empire_weather.exceptions import WeatherConfigError


DEFAULT_UNITS = "imperial"
DEFAULT_STORE_RAW_RESPONSES = True
DEFAULT_RETENTION_DAYS = 7
DEFAULT_OPENWEATHER_BASE_URL = "https://api.openweathermap.org"
DEFAULT_NWS_BASE_URL = "https://api.weather.gov"
DEFAULT_NWS_USER_AGENT = "empire-weather/0.1"
DEFAULT_ACCUWEATHER_BASE_URL = "https://www.accuweather.com"
DEFAULT_ACCUWEATHER_USER_AGENT = "empire-weather/0.1 personal daily weather digest"


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise WeatherConfigError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class NWSGridConfig:
    """Authoritative National Weather Service grid location."""

    grid_id: str
    grid_x: int
    grid_y: int

    @classmethod
    def from_mapping(cls, data: dict[str, Any], *, field_name: str) -> "NWSGridConfig":
        if not isinstance(data, dict):
            raise WeatherConfigError(f"{field_name} must be a mapping.")
        return cls(
            grid_id=_as_str(data.get("gridId") or data.get("grid_id"), f"{field_name}.gridId"),
            grid_x=_as_int(data.get("gridX") or data.get("grid_x"), f"{field_name}.gridX"),
            grid_y=_as_int(data.get("gridY") or data.get("grid_y"), f"{field_name}.gridY"),
        )


@dataclass(frozen=True)
class WeatherLocationConfig:
    """A configured weather collection location."""

    key: str
    name: str
    county: str
    state: str
    lat: float
    lon: float
    nws: NWSGridConfig
    accuweather_health_activities_url: str | None = None
    enabled: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "WeatherLocationConfig":
        if not isinstance(data, dict):
            raise WeatherConfigError("weather.locations[] must be a mapping.")
        return cls(
            key=_as_key(data.get("key"), "weather.locations[].key"),
            name=_as_str(data.get("name"), "weather.locations[].name"),
            county=_as_str(data.get("county"), "weather.locations[].county"),
            state=_as_str(data.get("state"), "weather.locations[].state"),
            lat=_as_float(data.get("lat"), "weather.locations[].lat"),
            lon=_as_float(data.get("lon"), "weather.locations[].lon"),
            nws=NWSGridConfig.from_mapping(
                data.get("nws"),
                field_name="weather.locations[].nws",
            ),
            accuweather_health_activities_url=_optional_str(
                data.get("accuweather_health_activities_url"),
                "weather.locations[].accuweather_health_activities_url",
            ),
            enabled=_as_bool(data.get("enabled", True), "weather.locations[].enabled"),
        )


@dataclass(frozen=True)
class OpenWeatherConfig:
    """OpenWeather API connection settings."""

    api_key: str
    base_url: str = DEFAULT_OPENWEATHER_BASE_URL
    units: str = DEFAULT_UNITS
    timeout_seconds: float = 30.0
    collect_air_quality: bool = True
    collect_minutely: bool = True
    collect_quarter_hourly: bool = True
    collect_alert_details: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None, *, units: str) -> "OpenWeatherConfig":
        if data is not None and not isinstance(data, dict):
            raise WeatherConfigError("weather.providers.openweather must be a mapping.")
        data = data or {}
        return cls(
            api_key=str(data.get("api_key") or required_env("EMPIRE_WEATHER_OPENWEATHER_API_KEY")),
            base_url=_as_str(
                data.get("base_url", DEFAULT_OPENWEATHER_BASE_URL),
                "weather.providers.openweather.base_url",
            ),
            units=_as_str(data.get("units", units), "weather.providers.openweather.units"),
            timeout_seconds=_as_float(
                data.get("timeout_seconds", 30.0),
                "weather.providers.openweather.timeout_seconds",
            ),
            collect_air_quality=_as_bool(
                data.get("collect_air_quality", True),
                "weather.providers.openweather.collect_air_quality",
            ),
            collect_minutely=_as_bool(
                data.get("collect_minutely", True),
                "weather.providers.openweather.collect_minutely",
            ),
            collect_quarter_hourly=_as_bool(
                data.get("collect_quarter_hourly", True),
                "weather.providers.openweather.collect_quarter_hourly",
            ),
            collect_alert_details=_as_bool(
                data.get("collect_alert_details", True),
                "weather.providers.openweather.collect_alert_details",
            ),
        )


@dataclass(frozen=True)
class NWSConfig:
    """National Weather Service API connection settings."""

    base_url: str = DEFAULT_NWS_BASE_URL
    user_agent: str = DEFAULT_NWS_USER_AGENT
    timeout_seconds: float = 30.0
    collect_forecast_discussion: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "NWSConfig":
        if data is not None and not isinstance(data, dict):
            raise WeatherConfigError("weather.providers.nws must be a mapping.")
        data = data or {}
        return cls(
            base_url=_as_str(data.get("base_url", DEFAULT_NWS_BASE_URL), "weather.providers.nws.base_url"),
            user_agent=_as_str(
                data.get("user_agent", os.environ.get("EMPIRE_WEATHER_NWS_USER_AGENT", DEFAULT_NWS_USER_AGENT)),
                "weather.providers.nws.user_agent",
            ),
            timeout_seconds=_as_float(
                data.get("timeout_seconds", 30.0),
                "weather.providers.nws.timeout_seconds",
            ),
            collect_forecast_discussion=_as_bool(
                data.get("collect_forecast_discussion", True),
                "weather.providers.nws.collect_forecast_discussion",
            ),
        )


@dataclass(frozen=True)
class AccuWeatherConfig:
    """Personal-use AccuWeather health/activity page collection settings."""

    enabled: bool = False
    base_url: str = DEFAULT_ACCUWEATHER_BASE_URL
    user_agent: str = DEFAULT_ACCUWEATHER_USER_AGENT
    timeout_seconds: float = 30.0

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "AccuWeatherConfig":
        if data is not None and not isinstance(data, dict):
            raise WeatherConfigError("weather.providers.accuweather must be a mapping.")
        data = data or {}
        return cls(
            enabled=_as_bool(data.get("enabled", False), "weather.providers.accuweather.enabled"),
            base_url=_as_str(
                data.get("base_url", DEFAULT_ACCUWEATHER_BASE_URL),
                "weather.providers.accuweather.base_url",
            ),
            user_agent=_as_str(
                data.get(
                    "user_agent",
                    os.environ.get("EMPIRE_WEATHER_ACCUWEATHER_USER_AGENT", DEFAULT_ACCUWEATHER_USER_AGENT),
                ),
                "weather.providers.accuweather.user_agent",
            ),
            timeout_seconds=_as_float(
                data.get("timeout_seconds", 30.0),
                "weather.providers.accuweather.timeout_seconds",
            ),
        )


@dataclass(frozen=True)
class WeatherProviderConfig:
    """Provider configuration for one weather collection job."""

    openweather: OpenWeatherConfig
    nws: NWSConfig = field(default_factory=NWSConfig)
    accuweather: AccuWeatherConfig = field(default_factory=AccuWeatherConfig)

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None, *, units: str) -> "WeatherProviderConfig":
        if data is not None and not isinstance(data, dict):
            raise WeatherConfigError("weather.providers must be a mapping.")
        data = data or {}
        return cls(
            openweather=OpenWeatherConfig.from_mapping(data.get("openweather"), units=units),
            nws=NWSConfig.from_mapping(data.get("nws")),
            accuweather=AccuWeatherConfig.from_mapping(data.get("accuweather")),
        )


@dataclass(frozen=True)
class WeatherCollectionConfig:
    """Run configuration for weather collection."""

    name: str
    version: int
    locations: list[WeatherLocationConfig]
    providers: WeatherProviderConfig
    units: str = DEFAULT_UNITS
    store_raw_responses: bool = DEFAULT_STORE_RAW_RESPONSES
    retention_days: int = DEFAULT_RETENTION_DAYS

    @classmethod
    def from_file(cls, path: str | Path) -> "WeatherCollectionConfig":
        return cls.from_yaml(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def from_yaml(cls, text: str) -> "WeatherCollectionConfig":
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise WeatherConfigError(f"Invalid weather config YAML: {exc}") from exc
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "WeatherCollectionConfig":
        if not isinstance(data, dict):
            raise WeatherConfigError("Weather config must be a mapping.")
        weather = data.get("weather", data)
        if not isinstance(weather, dict):
            raise WeatherConfigError("weather must be a mapping.")
        locations_data = weather.get("locations", [])
        if not isinstance(locations_data, list):
            raise WeatherConfigError("weather.locations must be a list.")
        locations = [WeatherLocationConfig.from_mapping(item) for item in locations_data]
        enabled_locations = [location for location in locations if location.enabled]
        if not enabled_locations:
            raise WeatherConfigError("weather.locations must include at least one enabled location.")
        _validate_unique([location.key for location in locations], "weather.locations[].key")
        units = _as_str(weather.get("units", DEFAULT_UNITS), "weather.units")
        retention_days = _as_int(weather.get("retention_days", DEFAULT_RETENTION_DAYS), "weather.retention_days")
        if retention_days < 1:
            raise WeatherConfigError("weather.retention_days must be greater than zero.")
        return cls(
            name=_as_str(weather.get("name"), "weather.name"),
            version=_as_int(weather.get("version"), "weather.version"),
            units=units,
            locations=locations,
            providers=WeatherProviderConfig.from_mapping(weather.get("providers"), units=units),
            store_raw_responses=_as_bool(
                weather.get("store_raw_responses", DEFAULT_STORE_RAW_RESPONSES),
                "weather.store_raw_responses",
            ),
            retention_days=retention_days,
        )

    @property
    def enabled_locations(self) -> list[WeatherLocationConfig]:
        return [location for location in self.locations if location.enabled]


def _as_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WeatherConfigError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _optional_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _as_str(value, field_name)


def _as_key(value: Any, field_name: str) -> str:
    key = _as_str(value, field_name)
    if not all(char.islower() or char.isdigit() or char == "_" for char in key):
        raise WeatherConfigError(f"{field_name} must use lowercase letters, digits, and underscores.")
    return key


def _as_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise WeatherConfigError(f"{field_name} must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise WeatherConfigError(f"{field_name} must be an integer.") from exc


def _as_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise WeatherConfigError(f"{field_name} must be a number.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WeatherConfigError(f"{field_name} must be a number.") from exc


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise WeatherConfigError(f"{field_name} must be a boolean.")


def _validate_unique(values: list[str], field_name: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise WeatherConfigError(
            f"{field_name} must be unique. Duplicate value(s): {', '.join(duplicates)}"
        )
