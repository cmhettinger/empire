"""Object store repository interfaces and Postgres implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from empire_core.db.postgres import json_dumps, row_to_dict
from empire_core.object_store.models import JsonDict, StorageRoot, StoredObject


class ObjectRepository(Protocol):
    def get_storage_root(self, root_name: str) -> StorageRoot | None: ...

    def insert_object(
        self,
        *,
        run_id: UUID | None,
        storage_root_id: int,
        object_key: str,
        filename: str,
        object_scope: str,
        domain: str | None,
        logical_name: str | None,
        content_type: str | None,
        object_kind: str | None,
        size_bytes: int,
        checksum_sha256: str,
        expires_at: datetime | None,
        metadata: JsonDict,
    ) -> StoredObject: ...

    def get_object(self, object_id: UUID) -> StoredObject | None: ...

    def find_objects_by_run_id(self, run_id: UUID) -> list[StoredObject]: ...

    def find_one(
        self,
        *,
        run_id: UUID | None,
        object_kind: str | None,
        filename: str | None,
        logical_name: str | None,
    ) -> StoredObject | None: ...

    def find_by_logical_name(
        self,
        *,
        domain: str,
        logical_name: str,
        object_scope: str | None,
    ) -> list[StoredObject]: ...

    def find_expired_objects(self, *, limit: int) -> list[StoredObject]: ...

    def mark_deleted(self, object_id: UUID, purge_after: datetime | None) -> None: ...

    def record_delete_error(self, object_id: UUID, error_message: str) -> None: ...

    def find_deleted_objects_for_purge(self, *, limit: int) -> list[StoredObject]: ...

    def find_deleted_objects_by_run_id(
        self, run_id: UUID, *, ignore_purge_after: bool
    ) -> list[StoredObject]: ...

    def purge_metadata(self, object_id: UUID) -> None: ...


class PostgresObjectRepository:
    """Postgres-backed object metadata repository."""

    def __init__(self, connection: Any):
        self.connection = connection

    def get_storage_root(self, root_name: str) -> StorageRoot | None:
        row = self._fetchone_or_none(
            """
            SELECT *
            FROM core.storage_root
            WHERE root_name = %s
              AND is_active = true
            """,
            (root_name,),
        )
        return _storage_root_from_row(row) if row else None

    def insert_object(
        self,
        *,
        run_id: UUID | None,
        storage_root_id: int,
        object_key: str,
        filename: str,
        object_scope: str,
        domain: str | None,
        logical_name: str | None,
        content_type: str | None,
        object_kind: str | None,
        size_bytes: int,
        checksum_sha256: str,
        expires_at: datetime | None,
        metadata: JsonDict,
    ) -> StoredObject:
        row = self._fetchone(
            """
            INSERT INTO core.stored_object (
                run_id, storage_root_id, object_key, filename,
                object_scope, domain, logical_name, content_type, object_kind,
                size_bytes, checksum_sha256, expires_at, metadata
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s::jsonb
            )
            RETURNING *
            """,
            (
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
                json_dumps(metadata),
            ),
        )
        self.connection.commit()
        return self._with_root(row)

    def get_object(self, object_id: UUID) -> StoredObject | None:
        row = self._fetchone_or_none(
            _stored_object_select("o.object_id = %s"),
            (object_id,),
        )
        return _stored_object_from_row(row) if row else None

    def find_objects_by_run_id(self, run_id: UUID) -> list[StoredObject]:
        rows = self._fetchall(
            _stored_object_select(
                "o.run_id = %s AND o.deleted_at IS NULL",
                "ORDER BY o.object_key, o.filename",
            ),
            (run_id,),
        )
        return [_stored_object_from_row(row) for row in rows]

    def find_one(
        self,
        *,
        run_id: UUID | None,
        object_kind: str | None,
        filename: str | None,
        logical_name: str | None,
    ) -> StoredObject | None:
        rows = self._fetchall(
            """
            SELECT o.*, r.root_name AS storage_root_name, r.base_uri
            FROM core.stored_object o
            JOIN core.storage_root r ON r.storage_root_id = o.storage_root_id
            WHERE o.deleted_at IS NULL
              AND (%s IS NULL OR o.run_id = %s)
              AND (%s IS NULL OR o.object_kind = %s)
              AND (%s IS NULL OR o.filename = %s)
              AND (%s IS NULL OR o.logical_name = %s)
            ORDER BY o.created_at DESC
            LIMIT 1
            """,
            (
                run_id,
                run_id,
                object_kind,
                object_kind,
                filename,
                filename,
                logical_name,
                logical_name,
            ),
        )
        return _stored_object_from_row(rows[0]) if rows else None

    def find_by_logical_name(
        self,
        *,
        domain: str,
        logical_name: str,
        object_scope: str | None,
    ) -> list[StoredObject]:
        rows = self._fetchall(
            """
            SELECT o.*, r.root_name AS storage_root_name, r.base_uri
            FROM core.stored_object o
            JOIN core.storage_root r ON r.storage_root_id = o.storage_root_id
            WHERE o.domain = %s
              AND o.logical_name = %s
              AND o.deleted_at IS NULL
              AND (%s IS NULL OR o.object_scope = %s)
            ORDER BY o.created_at DESC
            """,
            (domain, logical_name, object_scope, object_scope),
        )
        return [_stored_object_from_row(row) for row in rows]

    def find_expired_objects(self, *, limit: int) -> list[StoredObject]:
        rows = self._fetchall(
            _stored_object_select(
                "o.deleted_at IS NULL AND o.expires_at IS NOT NULL AND o.expires_at <= now()",
                "ORDER BY o.expires_at LIMIT %s",
            ),
            (limit,),
        )
        return [_stored_object_from_row(row) for row in rows]

    def mark_deleted(self, object_id: UUID, purge_after: datetime | None) -> None:
        self._execute(
            """
            UPDATE core.stored_object
            SET deleted_at = now(),
                purge_after = %s,
                updated_at = now()
            WHERE object_id = %s
            """,
            (purge_after, object_id),
        )

    def record_delete_error(self, object_id: UUID, error_message: str) -> None:
        self._execute(
            """
            UPDATE core.stored_object
            SET delete_attempts = delete_attempts + 1,
                last_delete_error = %s,
                updated_at = now()
            WHERE object_id = %s
            """,
            (error_message, object_id),
        )

    def find_deleted_objects_for_purge(self, *, limit: int) -> list[StoredObject]:
        rows = self._fetchall(
            _stored_object_select(
                "o.deleted_at IS NOT NULL AND o.purge_after IS NOT NULL AND o.purge_after <= now()",
                "ORDER BY o.purge_after LIMIT %s",
            ),
            (limit,),
        )
        return [_stored_object_from_row(row) for row in rows]

    def find_deleted_objects_by_run_id(
        self, run_id: UUID, *, ignore_purge_after: bool
    ) -> list[StoredObject]:
        purge_filter = "true" if ignore_purge_after else "o.purge_after IS NOT NULL AND o.purge_after <= now()"
        rows = self._fetchall(
            _stored_object_select(
                f"o.run_id = %s AND o.deleted_at IS NOT NULL AND {purge_filter}",
                "ORDER BY o.deleted_at, o.object_key, o.filename",
            ),
            (run_id,),
        )
        return [_stored_object_from_row(row) for row in rows]

    def purge_metadata(self, object_id: UUID) -> None:
        self._execute("DELETE FROM core.stored_object WHERE object_id = %s", (object_id,))

    def _with_root(self, row: dict[str, Any]) -> StoredObject:
        root_row = self._fetchone_or_none(
            "SELECT root_name AS storage_root_name, base_uri FROM core.storage_root WHERE storage_root_id = %s",
            (row["storage_root_id"],),
        )
        if root_row:
            row = {**row, **root_row}
        return _stored_object_from_row(row)

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
        self.connection.commit()

    def _fetchone(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
        row = self._fetchone_or_none(sql, params)
        if row is None:
            raise LookupError("Object was not found")
        return row

    def _fetchone_or_none(
        self, sql: str, params: tuple[Any, ...]
    ) -> dict[str, Any] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return row_to_dict(cursor, row) if row is not None else None

    def _fetchall(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return [row_to_dict(cursor, row) for row in cursor.fetchall()]


def _storage_root_from_row(row: dict[str, Any]) -> StorageRoot:
    return StorageRoot(
        storage_root_id=row["storage_root_id"],
        root_name=row["root_name"],
        backend_type=row["backend_type"],
        base_uri=row["base_uri"],
        is_active=row.get("is_active", True),
        config=row.get("config") or {},
    )


def _stored_object_from_row(row: dict[str, Any]) -> StoredObject:
    return StoredObject(
        object_id=row["object_id"],
        run_id=row.get("run_id"),
        storage_root_id=row["storage_root_id"],
        storage_root_name=row.get("storage_root_name"),
        base_uri=row.get("base_uri"),
        object_key=row["object_key"],
        filename=row["filename"],
        object_scope=row["object_scope"],
        domain=row.get("domain"),
        logical_name=row.get("logical_name"),
        content_type=row.get("content_type"),
        object_kind=row.get("object_kind"),
        size_bytes=row.get("size_bytes"),
        checksum_sha256=row.get("checksum_sha256"),
        expires_at=row.get("expires_at"),
        deleted_at=row.get("deleted_at"),
        purge_after=row.get("purge_after"),
        delete_attempts=row.get("delete_attempts", 0),
        last_delete_error=row.get("last_delete_error"),
        metadata=row.get("metadata") or {},
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _stored_object_select(where: str, suffix: str = "") -> str:
    return f"""
        SELECT o.*, r.root_name AS storage_root_name, r.base_uri
        FROM core.stored_object o
        JOIN core.storage_root r ON r.storage_root_id = o.storage_root_id
        WHERE {where}
        {suffix}
    """
