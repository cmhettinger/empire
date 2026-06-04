from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from empire_core import ObjectStore
from empire_core.object_store.models import StorageRoot, StoredObject

from empire_youtube.exceptions import YouTubeConfigError
from empire_youtube.object_store import (
    DEFAULT_CONFIG_LOGICAL_NAME,
    find_config_object_by_logical_name,
    load_config_by_logical_name,
    load_config_from_object_id,
)


CONFIG_YAML = b"""
youtube:
  name: daily_youtube_scraper
  version: 1
  lookback_hours: 26
  max_results_per_query: 10
  topic_sections:
    - key: home_automation
      name: Home Automation
      topics:
        - key: home_assistant
          name: Home Assistant
          queries:
            - "home assistant"
  followed_channels:
    - channel_name: All-In Podcast
      channel_id: UCESLZhusAkFfsNsApnjF_Cg
      handle: "@allin"
"""


def test_load_config_from_object_id(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))
    stored = _put_config(store, CONFIG_YAML)

    config = load_config_from_object_id(store, stored.object_id)

    assert config.name == "daily_youtube_scraper"
    assert config.followed_channels[0].handle == "@allin"


def test_load_config_by_logical_name_uses_latest_object(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))
    older = _put_config(store, CONFIG_YAML.replace(b"version: 1", b"version: 1"))
    newer = _put_config(store, CONFIG_YAML.replace(b"version: 1", b"version: 2"))

    repo = store.repository
    repo.objects[older.object_id] = _replace_created_at(
        repo.objects[older.object_id],
        datetime.now(UTC) - timedelta(days=1),
    )
    repo.objects[newer.object_id] = _replace_created_at(
        repo.objects[newer.object_id],
        datetime.now(UTC),
    )

    config = load_config_by_logical_name(store)
    stored = find_config_object_by_logical_name(store)

    assert config.version == 2
    assert stored.object_id == newer.object_id


def test_missing_logical_name_raises_config_error(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))

    with pytest.raises(YouTubeConfigError, match="not found"):
        load_config_by_logical_name(store)


def _put_config(store: ObjectStore, data: bytes):
    return store.put_bytes(
        run_context=None,
        object_scope="reference",
        domain="youtube",
        logical_name=DEFAULT_CONFIG_LOGICAL_NAME,
        storage_root="test_root",
        object_key="youtube/config",
        filename="config.yml",
        data=data,
        content_type="text/yaml",
        object_kind="scraper_config",
    )


def _replace_created_at(stored, created_at):
    return replace(stored, created_at=created_at)


class InMemoryObjectRepository:
    def __init__(self, base_uri: str):
        self.roots = {
            "test_root": StorageRoot(
                storage_root_id=1,
                root_name="test_root",
                backend_type="filesystem",
                base_uri=base_uri,
            )
        }
        self.objects = {}

    def get_storage_root(self, root_name: str):
        return self.roots.get(root_name)

    def insert_object(
        self,
        *,
        run_id,
        storage_root_id,
        object_key,
        filename,
        object_scope,
        domain,
        logical_name,
        content_type,
        object_kind,
        size_bytes,
        checksum_sha256,
        expires_at,
        metadata,
    ):
        root = self.roots["test_root"]
        stored = StoredObject(
            object_id=uuid4(),
            run_id=run_id,
            storage_root_id=storage_root_id,
            storage_root_name=root.root_name,
            base_uri=root.base_uri,
            object_key=object_key,
            filename=filename,
            object_scope=object_scope,
            domain=domain,
            logical_name=logical_name,
            content_type=content_type,
            object_kind=object_kind,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            expires_at=expires_at,
            deleted_at=None,
            purge_after=None,
            metadata=metadata,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.objects[stored.object_id] = stored
        return stored

    def get_object(self, object_id):
        return self.objects.get(object_id)

    def find_by_logical_name(self, *, domain, logical_name, object_scope):
        return [
            obj
            for obj in self.objects.values()
            if obj.deleted_at is None
            and obj.domain == domain
            and obj.logical_name == logical_name
            and (object_scope is None or obj.object_scope == object_scope)
        ]
