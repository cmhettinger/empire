"""Storage backends for empire-core."""

from empire_core.object_store.storage.base import FileWriteResult, StorageBackend
from empire_core.object_store.storage.filesystem import FilesystemStorageBackend

__all__ = ["FileWriteResult", "FilesystemStorageBackend", "StorageBackend"]
