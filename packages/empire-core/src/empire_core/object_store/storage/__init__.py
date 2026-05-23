"""Storage backends for empire-core."""

from empire_core.object_store.storage.base import StorageBackend
from empire_core.object_store.storage.filesystem import FilesystemStorageBackend

__all__ = ["FilesystemStorageBackend", "StorageBackend"]
