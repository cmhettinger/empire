"""Filesystem storage backend."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from empire_core.exceptions import ValidationError


class FilesystemStorageBackend:
    """Store objects safely beneath a configured filesystem root."""

    def __init__(self, base_uri: str):
        self.base_path = Path(base_uri).expanduser().resolve()

    def write_bytes(self, object_key: str, filename: str, data: bytes) -> Path:
        path = self.resolve_path(object_key, filename)
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(fd, "wb") as temp_file:
                temp_file.write(data)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
        return path

    def read_bytes(self, object_key: str, filename: str) -> bytes:
        return self.resolve_path(object_key, filename).read_bytes()

    def exists(self, object_key: str, filename: str) -> bool:
        return self.resolve_path(object_key, filename).exists()

    def delete(self, object_key: str, filename: str) -> None:
        path = self.resolve_path(object_key, filename)
        try:
            path.unlink()
        except FileNotFoundError:
            return
        self._prune_empty_parents(path.parent)

    def resolve_path(self, object_key: str, filename: str) -> Path:
        _validate_object_key(object_key)
        _validate_filename(filename)
        path = (self.base_path / object_key / filename).resolve()
        if path != self.base_path and self.base_path not in path.parents:
            raise ValidationError("Object path escapes the storage root")
        return path

    def _prune_empty_parents(self, start: Path) -> None:
        current = start
        while current != self.base_path and self.base_path in current.parents:
            try:
                current.rmdir()
            except OSError:
                return
            current = current.parent


def _validate_object_key(object_key: str) -> None:
    if not object_key or object_key.startswith("/"):
        raise ValidationError("object_key must be a relative path")
    parts = Path(object_key).parts
    if any(part in ("", ".", "..") for part in parts):
        raise ValidationError("object_key contains an unsafe path segment")


def _validate_filename(filename: str) -> None:
    if not filename or filename in (".", ".."):
        raise ValidationError("filename is required")
    path = Path(filename)
    if len(path.parts) != 1 or path.is_absolute():
        raise ValidationError("filename must be a single path segment")
