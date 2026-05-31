"""Reusable weather collection utilities for Empire."""

from empire_weather.collector import WeatherCollector
from empire_weather.config import (
    NWSConfig,
    NWSGridConfig,
    OpenWeatherConfig,
    WeatherCollectionConfig,
    WeatherLocationConfig,
    WeatherProviderConfig,
)
from empire_weather.object_store import (
    DEFAULT_CONFIG_LOGICAL_NAME,
    find_config_object_by_logical_name,
    load_config_by_logical_name,
    load_config_from_object_id,
)
from empire_weather.output import write_result_to_file
from empire_weather.providers import NWSProvider, OpenWeatherProvider
from empire_weather.runner import (
    WeatherCollectionRunResult,
    run_weather_collection_to_object_store,
)

__all__ = [
    "DEFAULT_CONFIG_LOGICAL_NAME",
    "NWSConfig",
    "NWSGridConfig",
    "NWSProvider",
    "OpenWeatherConfig",
    "OpenWeatherProvider",
    "WeatherCollectionConfig",
    "WeatherCollectionRunResult",
    "WeatherCollector",
    "WeatherLocationConfig",
    "WeatherProviderConfig",
    "find_config_object_by_logical_name",
    "load_config_by_logical_name",
    "load_config_from_object_id",
    "run_weather_collection_to_object_store",
    "write_result_to_file",
]
