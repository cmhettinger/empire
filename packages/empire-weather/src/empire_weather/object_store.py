"""Empire object-store helpers for weather configuration."""

from __future__ import annotations

from uuid import UUID

from empire_core import ObjectStore

from empire_weather.config import WeatherCollectionConfig
from empire_weather.exceptions import WeatherConfigError


DEFAULT_CONFIG_LOGICAL_NAME = "weather-config"
DEFAULT_CONFIG_DOMAIN = "weather"
DEFAULT_CONFIG_OBJECT_SCOPE = "reference"
DEFAULT_CONFIG_OBJECT_KIND = "weather_config"
DEFAULT_CONFIG_FILENAME = "config.yml"
DEFAULT_CONFIG_CONTENT_TYPE = "text/yaml"


def load_config_from_object_id(
    object_store: ObjectStore,
    object_id: str | UUID,
) -> WeatherCollectionConfig:
    """Load weather config JSON from one stored object id."""

    parsed_object_id = object_id if isinstance(object_id, UUID) else UUID(str(object_id))
    data = object_store.get_bytes(parsed_object_id)
    return WeatherCollectionConfig.from_yaml(data.decode("utf-8"))


def load_config_by_logical_name(
    object_store: ObjectStore,
    *,
    logical_name: str = DEFAULT_CONFIG_LOGICAL_NAME,
    domain: str = DEFAULT_CONFIG_DOMAIN,
    object_scope: str = DEFAULT_CONFIG_OBJECT_SCOPE,
) -> WeatherCollectionConfig:
    """Load the latest weather config matching a logical name."""

    matches = object_store.find_by_logical_name(
        domain=domain,
        logical_name=logical_name,
        object_scope=object_scope,
    )
    if not matches:
        raise WeatherConfigError(
            "Weather config not found in object store: "
            f"domain={domain!r}, logical_name={logical_name!r}, "
            f"object_scope={object_scope!r}"
        )
    matches.sort(key=lambda item: item.created_at, reverse=True)
    return load_config_from_object_id(object_store, matches[0].object_id)


def find_config_object_by_logical_name(
    object_store: ObjectStore,
    *,
    logical_name: str = DEFAULT_CONFIG_LOGICAL_NAME,
    domain: str = DEFAULT_CONFIG_DOMAIN,
    object_scope: str = DEFAULT_CONFIG_OBJECT_SCOPE,
):
    """Return the latest stored config object metadata for a logical name."""

    matches = object_store.find_by_logical_name(
        domain=domain,
        logical_name=logical_name,
        object_scope=object_scope,
    )
    if not matches:
        return None
    matches.sort(key=lambda item: item.created_at, reverse=True)
    return matches[0]
