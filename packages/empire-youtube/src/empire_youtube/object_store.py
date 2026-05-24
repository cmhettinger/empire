"""Empire object-store helpers for YouTube scraper configuration."""

from __future__ import annotations

from uuid import UUID

from empire_core import ObjectStore
from empire_youtube.config import YouTubeScraperConfig
from empire_youtube.exceptions import YouTubeConfigError


DEFAULT_CONFIG_LOGICAL_NAME = "youtube-daily-config"
DEFAULT_CONFIG_DOMAIN = "youtube"
DEFAULT_CONFIG_OBJECT_SCOPE = "reference"
DEFAULT_CONFIG_OBJECT_KIND = "scraper_config"


def load_config_from_object_id(
    object_store: ObjectStore,
    object_id: str | UUID,
) -> YouTubeScraperConfig:
    """Load YouTube scraper config YAML from one stored object id."""

    parsed_object_id = object_id if isinstance(object_id, UUID) else UUID(str(object_id))
    data = object_store.get_bytes(parsed_object_id)
    return YouTubeScraperConfig.from_yaml(data.decode("utf-8"))


def load_config_by_logical_name(
    object_store: ObjectStore,
    *,
    logical_name: str = DEFAULT_CONFIG_LOGICAL_NAME,
    domain: str = DEFAULT_CONFIG_DOMAIN,
    object_scope: str = DEFAULT_CONFIG_OBJECT_SCOPE,
) -> YouTubeScraperConfig:
    """Load the latest YouTube scraper config matching a logical name."""

    matches = object_store.find_by_logical_name(
        domain=domain,
        logical_name=logical_name,
        object_scope=object_scope,
    )
    if not matches:
        raise YouTubeConfigError(
            "YouTube scraper config not found in object store: "
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
