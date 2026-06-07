"""Empire object-store helpers for stonks securities configuration."""

from __future__ import annotations

from uuid import UUID

from empire_core import ObjectStore

from empire_stonks_securities.config import StonksSecuritiesConfig
from empire_stonks_securities.exceptions import StonksSecuritiesConfigError


DEFAULT_CONFIG_LOGICAL_NAME = "stonks-securities-config"
DEFAULT_CONFIG_DOMAIN = "stonks"
DEFAULT_CONFIG_OBJECT_SCOPE = "reference"
DEFAULT_CONFIG_OBJECT_KIND = "stonks_securities_config"
DEFAULT_CONFIG_FILENAME = "config.yml"
DEFAULT_CONFIG_CONTENT_TYPE = "text/yaml"


def load_config_from_object_id(
    object_store: ObjectStore,
    object_id: str | UUID,
) -> StonksSecuritiesConfig:
    """Load stonks securities config from one stored object id."""

    parsed_object_id = object_id if isinstance(object_id, UUID) else UUID(str(object_id))
    data = object_store.get_bytes(parsed_object_id)
    return StonksSecuritiesConfig.from_yaml(data.decode("utf-8"))


def load_config_by_logical_name(
    object_store: ObjectStore,
    *,
    logical_name: str = DEFAULT_CONFIG_LOGICAL_NAME,
    domain: str = DEFAULT_CONFIG_DOMAIN,
    object_scope: str = DEFAULT_CONFIG_OBJECT_SCOPE,
) -> StonksSecuritiesConfig:
    """Load the latest stonks securities config matching a logical name."""

    matches = object_store.find_by_logical_name(
        domain=domain,
        logical_name=logical_name,
        object_scope=object_scope,
    )
    if not matches:
        raise StonksSecuritiesConfigError(
            "Stonks securities config not found in object store: "
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
