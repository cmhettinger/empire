"""Storage backend interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class FileWriteResult:
    """Result of writing a local file into a storage backend."""

    path: Path
    size_bytes: int
    checksum_sha256: str


class StorageBackend(Protocol):
    def write_bytes(self, object_key: str, filename: str, data: bytes) -> Path: ...

    def write_file(
        self,
        object_key: str,
        filename: str,
        source_path: str | Path,
        *,
        move: bool = True,
    ) -> FileWriteResult: ...

    def read_bytes(self, object_key: str, filename: str) -> bytes: ...

    def exists(self, object_key: str, filename: str) -> bool: ...

    def delete(self, object_key: str, filename: str) -> None: ...

    def resolve_path(self, object_key: str, filename: str) -> Path: ...
