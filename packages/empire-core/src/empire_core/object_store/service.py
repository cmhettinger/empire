"""Filesystem-backed object store service."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from empire_core.config import ObjectStoreConfig
from empire_core.exceptions import NotFoundError, StorageRootNotFoundError, ValidationError
from empire_core.object_store.models import JsonDict, StoredObject
from empire_core.object_store.repository import ObjectRepository, PostgresObjectRepository
from empire_core.object_store.storage import FilesystemStorageBackend, StorageBackend
from empire_core.run_context.models import RunContext

logger = logging.getLogger(__name__)

OBJECT_SCOPES = {"run", "reference", "audit", "manual"}


@dataclass(frozen=True)
class ObjectCleanupRootStat:
    storage_root_name: str
    cleaned_count: int = 0
    cleaned_bytes: int = 0


@dataclass(frozen=True)
class ObjectCleanupResult:
    cleaned_count: int = 0
    cleaned_bytes: int = 0
    root_stats: list[ObjectCleanupRootStat] = field(default_factory=list)


@dataclass(frozen=True)
class ObjectPurgeRootStat:
    storage_root_name: str
    purged_count: int = 0


@dataclass(frozen=True)
class ObjectPurgeResult:
    purged_count: int = 0
    root_stats: list[ObjectPurgeRootStat] = field(default_factory=list)


class ObjectStore:
    """Store bytes on a filesystem root and track metadata in Postgres."""

    def __init__(
        self,
        repository: ObjectRepository,
        *,
        tombstone_days: int = 30,
    ):
        self.repository = repository
        self.tombstone_days = tombstone_days

    @classmethod
    def from_connection(cls, connection) -> "ObjectStore":
        config = ObjectStoreConfig.from_env()
        return cls(PostgresObjectRepository(connection), tombstone_days=config.tombstone_days)

    def put_bytes(
        self,
        *,
        run_context: RunContext | None,
        storage_root: str,
        object_key: str,
        filename: str,
        data: bytes,
        object_scope: str | None = None,
        domain: str | None = None,
        logical_name: str | None = None,
        content_type: str | None = None,
        object_kind: str | None = None,
        expires_at: datetime | None = None,
        metadata: JsonDict | None = None,
        overwrite: bool = False,
    ) -> StoredObject:
        scope = object_scope or ("run" if run_context else "manual")
        _validate_scope(scope)
        if scope == "run" and run_context is None:
            raise ValidationError("object_scope='run' requires run_context")

        root = self.repository.get_storage_root(storage_root)
        if root is None:
            raise StorageRootNotFoundError(f"Storage root not found or inactive: {storage_root}")
        if root.backend_type != "filesystem":
            raise ValidationError(f"Unsupported storage backend: {root.backend_type}")

        resolved_domain = domain if domain is not None else run_context.domain if run_context else None
        backend = self._backend(root.base_uri)
        backend.write_bytes(object_key, filename, data)
        checksum = hashlib.sha256(data).hexdigest()

        logger.info("Stored object %s/%s in root %s", object_key, filename, storage_root)
        object_args = {
            "run_id": run_context.run_id if run_context else None,
            "storage_root_id": root.storage_root_id,
            "object_key": object_key,
            "filename": filename,
            "object_scope": scope,
            "domain": resolved_domain,
            "logical_name": logical_name,
            "content_type": content_type,
            "object_kind": object_kind,
            "size_bytes": len(data),
            "checksum_sha256": checksum,
            "expires_at": expires_at,
            "metadata": metadata or {},
        }
        if overwrite:
            insert_or_replace = getattr(self.repository, "insert_or_replace_object", None)
            if not callable(insert_or_replace):
                raise ValidationError("Object repository does not support overwrite")
            return insert_or_replace(**object_args)
        return self.repository.insert_object(**object_args)

    def put_file(
        self,
        *,
        run_context: RunContext | None,
        storage_root: str,
        object_key: str,
        filename: str,
        source_path: str | Path,
        move: bool = True,
        object_scope: str | None = None,
        domain: str | None = None,
        logical_name: str | None = None,
        content_type: str | None = None,
        object_kind: str | None = None,
        expires_at: datetime | None = None,
        metadata: JsonDict | None = None,
    ) -> StoredObject:
        """Store an existing local file without loading it into memory."""

        scope = object_scope or ("run" if run_context else "manual")
        _validate_scope(scope)
        if scope == "run" and run_context is None:
            raise ValidationError("object_scope='run' requires run_context")

        root = self.repository.get_storage_root(storage_root)
        if root is None:
            raise StorageRootNotFoundError(f"Storage root not found or inactive: {storage_root}")
        if root.backend_type != "filesystem":
            raise ValidationError(f"Unsupported storage backend: {root.backend_type}")

        resolved_domain = domain if domain is not None else run_context.domain if run_context else None
        backend = self._backend(root.base_uri)
        result = backend.write_file(
            object_key,
            filename,
            source_path,
            move=move,
        )

        logger.info("Stored file object %s/%s in root %s", object_key, filename, storage_root)
        return self.repository.insert_object(
            run_id=run_context.run_id if run_context else None,
            storage_root_id=root.storage_root_id,
            object_key=object_key,
            filename=filename,
            object_scope=scope,
            domain=resolved_domain,
            logical_name=logical_name,
            content_type=content_type,
            object_kind=object_kind,
            size_bytes=result.size_bytes,
            checksum_sha256=result.checksum_sha256,
            expires_at=expires_at,
            metadata=metadata or {},
        )

    def get_bytes(self, object_id: UUID) -> bytes:
        stored = self.get_object(object_id)
        return self._backend_for_object(stored).read_bytes(stored.object_key, stored.filename)

    def get_path(self, object_id: UUID) -> Path:
        """Return the validated local path for a filesystem-backed object."""

        stored = self.get_object(object_id)
        return self._backend_for_object(stored).resolve_path(
            stored.object_key,
            stored.filename,
        )

    def get_object(self, object_id: UUID) -> StoredObject:
        stored = self.repository.get_object(object_id)
        if stored is None or stored.deleted_at is not None:
            raise NotFoundError(f"Stored object not found: {object_id}")
        return stored

    def find_objects_by_run_id(self, run_id: UUID) -> list[StoredObject]:
        return self.repository.find_objects_by_run_id(run_id)

    def find_one(
        self,
        *,
        run_id: UUID | None = None,
        object_kind: str | None = None,
        filename: str | None = None,
        logical_name: str | None = None,
    ) -> StoredObject | None:
        if not any((run_id, object_kind, filename, logical_name)):
            raise ValidationError("At least one lookup field is required")
        return self.repository.find_one(
            run_id=run_id,
            object_kind=object_kind,
            filename=filename,
            logical_name=logical_name,
        )

    def find_by_logical_name(
        self,
        *,
        domain: str,
        logical_name: str,
        object_scope: str | None = None,
    ) -> list[StoredObject]:
        if object_scope is not None:
            _validate_scope(object_scope)
        return self.repository.find_by_logical_name(
            domain=domain,
            logical_name=logical_name,
            object_scope=object_scope,
        )

    def delete_object(self, object_id: UUID) -> bool:
        stored = self.repository.get_object(object_id)
        if stored is None or stored.deleted_at is not None:
            return False
        return self._delete_stored_object(stored)

    def delete_objects_by_run_id(self, run_id: UUID) -> int:
        deleted_count = 0
        for stored in self.repository.find_objects_by_run_id(run_id):
            if self._delete_stored_object(stored):
                deleted_count += 1
        return deleted_count

    def find_deleted_objects_by_run_id(
        self,
        run_id: UUID,
        *,
        ignore_purge_after: bool = False,
    ) -> list[StoredObject]:
        return self.repository.find_deleted_objects_by_run_id(
            run_id,
            ignore_purge_after=ignore_purge_after,
        )

    def delete_expired_objects(self, *, limit: int = 100) -> int:
        if limit <= 0:
            raise ValidationError("limit must be positive")
        deleted_count = 0
        for stored in self.repository.find_expired_objects(limit=limit):
            if self._delete_stored_object(stored):
                deleted_count += 1
        return deleted_count

    def cleanup_expired_objects(self, *, batch_size: int = 100) -> ObjectCleanupResult:
        if batch_size <= 0:
            raise ValidationError("batch_size must be positive")

        root_stats: dict[str, ObjectCleanupRootStat] = {}
        cleaned_count = 0
        cleaned_bytes = 0
        after_expires_at: datetime | None = None
        after_object_id: UUID | None = None

        while True:
            expired_objects = self.repository.find_expired_objects(
                limit=batch_size,
                after_expires_at=after_expires_at,
                after_object_id=after_object_id,
            )
            if not expired_objects:
                break

            for stored in expired_objects:
                after_expires_at = stored.expires_at
                after_object_id = stored.object_id
                if self._delete_stored_object(stored):
                    size_bytes = stored.size_bytes or 0
                    root_name = stored.storage_root_name or "<unknown>"
                    existing = root_stats.get(root_name)
                    if existing is None:
                        existing = ObjectCleanupRootStat(storage_root_name=root_name)
                    root_stats[root_name] = ObjectCleanupRootStat(
                        storage_root_name=root_name,
                        cleaned_count=existing.cleaned_count + 1,
                        cleaned_bytes=existing.cleaned_bytes + size_bytes,
                    )
                    cleaned_count += 1
                    cleaned_bytes += size_bytes

        return ObjectCleanupResult(
            cleaned_count=cleaned_count,
            cleaned_bytes=cleaned_bytes,
            root_stats=sorted(
                root_stats.values(),
                key=lambda stat: stat.storage_root_name,
            ),
        )

    def purge_deleted_objects(self, *, limit: int = 100) -> int:
        if limit <= 0:
            raise ValidationError("limit must be positive")
        purged_count = 0
        for stored in self.repository.find_deleted_objects_for_purge(limit=limit):
            try:
                self._backend_for_object(stored).delete(stored.object_key, stored.filename)
                self.repository.purge_metadata(stored.object_id)
                purged_count += 1
            except Exception as exc:
                logger.warning("Failed to purge deleted object %s", stored.object_id)
                self.repository.record_delete_error(stored.object_id, str(exc))
        return purged_count

    def purge_deleted_objects_all(self, *, batch_size: int = 100) -> ObjectPurgeResult:
        if batch_size <= 0:
            raise ValidationError("batch_size must be positive")

        root_stats: dict[str, ObjectPurgeRootStat] = {}
        purged_count = 0
        after_purge_after: datetime | None = None
        after_object_id: UUID | None = None

        while True:
            deleted_objects = self.repository.find_deleted_objects_for_purge(
                limit=batch_size,
                after_purge_after=after_purge_after,
                after_object_id=after_object_id,
            )
            if not deleted_objects:
                break

            for stored in deleted_objects:
                after_purge_after = stored.purge_after
                after_object_id = stored.object_id
                try:
                    self._backend_for_object(stored).delete(stored.object_key, stored.filename)
                    self.repository.purge_metadata(stored.object_id)
                    root_name = stored.storage_root_name or "<unknown>"
                    existing = root_stats.get(root_name)
                    if existing is None:
                        existing = ObjectPurgeRootStat(storage_root_name=root_name)
                    root_stats[root_name] = ObjectPurgeRootStat(
                        storage_root_name=root_name,
                        purged_count=existing.purged_count + 1,
                    )
                    purged_count += 1
                except Exception as exc:
                    logger.warning("Failed to purge deleted object %s", stored.object_id)
                    self.repository.record_delete_error(stored.object_id, str(exc))

        return ObjectPurgeResult(
            purged_count=purged_count,
            root_stats=sorted(
                root_stats.values(),
                key=lambda stat: stat.storage_root_name,
            ),
        )

    def purge_deleted_objects_by_run_id(
        self,
        run_id: UUID,
        *,
        ignore_purge_after: bool = False,
    ) -> int:
        purged_count = 0
        for stored in self.repository.find_deleted_objects_by_run_id(
            run_id,
            ignore_purge_after=ignore_purge_after,
        ):
            try:
                self._backend_for_object(stored).delete(stored.object_key, stored.filename)
                self.repository.purge_metadata(stored.object_id)
                purged_count += 1
            except Exception as exc:
                logger.warning("Failed to purge deleted object %s", stored.object_id)
                self.repository.record_delete_error(stored.object_id, str(exc))
        return purged_count

    def _backend_for_object(self, stored: StoredObject) -> StorageBackend:
        if not stored.base_uri:
            raise ValidationError("Stored object is missing storage root base_uri")
        return self._backend(stored.base_uri)

    def _backend(self, base_uri: str) -> StorageBackend:
        return FilesystemStorageBackend(base_uri)

    def _delete_stored_object(self, stored: StoredObject) -> bool:
        purge_after = datetime.now(UTC) + timedelta(days=self.tombstone_days)
        try:
            self._backend_for_object(stored).delete(stored.object_key, stored.filename)
            self.repository.mark_deleted(stored.object_id, purge_after)
            return True
        except Exception as exc:
            logger.warning("Failed to delete object %s", stored.object_id)
            self.repository.record_delete_error(stored.object_id, str(exc))
            return False


def _validate_scope(object_scope: str) -> None:
    if object_scope not in OBJECT_SCOPES:
        raise ValidationError(f"Unsupported object_scope: {object_scope}")
