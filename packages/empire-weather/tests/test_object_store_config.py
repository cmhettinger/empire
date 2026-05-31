from __future__ import annotations

import yaml

from empire_core import ObjectStore

from empire_weather.object_store import (
    DEFAULT_CONFIG_CONTENT_TYPE,
    DEFAULT_CONFIG_DOMAIN,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_CONFIG_LOGICAL_NAME,
    DEFAULT_CONFIG_OBJECT_KIND,
    DEFAULT_CONFIG_OBJECT_SCOPE,
    load_config_by_logical_name,
)

from fakes import InMemoryObjectRepository
from test_config import CONFIG


def test_load_config_by_logical_name_from_fixed_weather_path(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))
    stored = store.put_bytes(
        run_context=None,
        object_scope=DEFAULT_CONFIG_OBJECT_SCOPE,
        domain=DEFAULT_CONFIG_DOMAIN,
        logical_name=DEFAULT_CONFIG_LOGICAL_NAME,
        storage_root="global",
        object_key="scraper/weather/config",
        filename=DEFAULT_CONFIG_FILENAME,
        data=yaml.safe_dump(CONFIG).encode("utf-8"),
        content_type=DEFAULT_CONFIG_CONTENT_TYPE,
        object_kind=DEFAULT_CONFIG_OBJECT_KIND,
    )

    config = load_config_by_logical_name(store)

    assert stored.object_key == "scraper/weather/config"
    assert stored.filename == "config.yml"
    assert config.name == "daily_weather"
