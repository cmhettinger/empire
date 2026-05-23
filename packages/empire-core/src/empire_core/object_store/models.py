"""Object store models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class StorageRoot:
    storage_root_id: int
    root_name: str
    backend_type: str
    base_uri: str
    is_active: bool = True
    config: JsonDict = field(default_factory=dict)


@dataclass(frozen=True)
class StoredObject:
    object_id: UUID
    run_id: UUID | None
    storage_root_id: int
    storage_root_name: str | None
    base_uri: str | None
    object_key: str
    filename: str
    object_scope: str
    domain: str | None
    logical_name: str | None
    content_type: str | None
    object_kind: str | None
    size_bytes: int | None
    checksum_sha256: str | None
    expires_at: datetime | None
    deleted_at: datetime | None
    purge_after: datetime | None
    delete_attempts: int = 0
    last_delete_error: str | None = None
    metadata: JsonDict = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
