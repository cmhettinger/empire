"""Storage backend interface."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class StorageBackend(Protocol):
    def write_bytes(self, object_key: str, filename: str, data: bytes) -> Path: ...

    def read_bytes(self, object_key: str, filename: str) -> bytes: ...

    def exists(self, object_key: str, filename: str) -> bool: ...

    def delete(self, object_key: str, filename: str) -> None: ...

    def resolve_path(self, object_key: str, filename: str) -> Path: ...
