from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from empire_core.object_store.models import StorageRoot, StoredObject
from empire_core.run_context.models import JsonDict, RunContext


class InMemoryRunRepository:
    def __init__(self):
        self.runs: dict[UUID, RunContext] = {}

    def start_run(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None,
        effective_date: date | None,
        run_type: str,
        runner: str,
        runner_ref: JsonDict,
        params: JsonDict,
        heartbeat_timeout_seconds: int | None,
    ) -> RunContext:
        now = datetime.now(UTC)
        ctx = RunContext(
            run_id=uuid4(),
            domain=domain,
            job_name=job_name,
            subject_key=subject_key,
            effective_date=effective_date,
            run_type=run_type,
            status="started",
            runner=runner,
            params=params,
            summary={},
            started_at=now,
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
            last_heartbeat_at=now if heartbeat_timeout_seconds else None,
            stale_after=(
                now + timedelta(seconds=heartbeat_timeout_seconds)
                if heartbeat_timeout_seconds
                else None
            ),
        )
        self.runs[ctx.run_id] = ctx
        return ctx

    def complete_run(self, run_id: UUID, summary: JsonDict | None) -> RunContext:
        ctx = replace(
            self.runs[run_id],
            status="succeeded",
            completed_at=datetime.now(UTC),
            summary=summary or {},
        )
        self.runs[run_id] = ctx
        return ctx

    def fail_run(
        self, run_id: UUID, error_message: str, summary: JsonDict | None
    ) -> RunContext:
        ctx = replace(
            self.runs[run_id],
            status="failed",
            completed_at=datetime.now(UTC),
            summary=summary or {},
        )
        self.runs[run_id] = ctx
        return ctx

    def heartbeat(self, run_id: UUID) -> RunContext:
        current = self.runs[run_id]
        now = datetime.now(UTC)
        ctx = replace(
            current,
            last_heartbeat_at=now,
            stale_after=(
                now + timedelta(seconds=current.heartbeat_timeout_seconds)
                if current.heartbeat_timeout_seconds
                else current.stale_after
            ),
        )
        self.runs[run_id] = ctx
        return ctx

    def get_run_context(self, run_id: UUID) -> RunContext | None:
        return self.runs.get(run_id)

    def find_latest_successful_run(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None,
        effective_date: date | None,
        before: datetime | None,
    ) -> RunContext | None:
        matches = self.find_successful_runs(
            domain=domain,
            job_name=job_name,
            subject_key=subject_key,
            after=None,
            before=before,
            limit=1000,
        )
        if effective_date is not None:
            matches = [run for run in matches if run.effective_date == effective_date]
        return matches[0] if matches else None

    def find_successful_runs(
        self,
        *,
        domain: str,
        job_name: str,
        subject_key: str | None,
        after: datetime | None,
        before: datetime | None,
        limit: int,
    ) -> list[RunContext]:
        runs = [
            run
            for run in self.runs.values()
            if run.status == "succeeded"
            and run.domain == domain
            and run.job_name == job_name
            and (subject_key is None or run.subject_key == subject_key)
            and (after is None or (run.completed_at and run.completed_at >= after))
            and (before is None or (run.completed_at and run.completed_at <= before))
        ]
        runs.sort(
            key=lambda run: (
                run.completed_at or datetime.min.replace(tzinfo=UTC),
                run.started_at or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        return runs[:limit]


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
        self.objects: dict[UUID, StoredObject] = {}

    def get_storage_root(self, root_name: str) -> StorageRoot | None:
        return self.roots.get(root_name)

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

    def insert_or_replace_object(self, **kwargs) -> StoredObject:
        for object_id, existing in list(self.objects.items()):
            if (
                existing.storage_root_id == kwargs["storage_root_id"]
                and existing.object_key == kwargs["object_key"]
                and existing.filename == kwargs["filename"]
            ):
                stored = replace(
                    existing,
                    run_id=kwargs["run_id"],
                    object_scope=kwargs["object_scope"],
                    domain=kwargs["domain"],
                    logical_name=kwargs["logical_name"],
                    content_type=kwargs["content_type"],
                    object_kind=kwargs["object_kind"],
                    size_bytes=kwargs["size_bytes"],
                    checksum_sha256=kwargs["checksum_sha256"],
                    expires_at=kwargs["expires_at"],
                    deleted_at=None,
                    purge_after=None,
                    delete_attempts=0,
                    last_delete_error=None,
                    metadata=kwargs["metadata"],
                    updated_at=datetime.now(UTC),
                )
                self.objects[object_id] = stored
                return stored
        return self.insert_object(**kwargs)

    def get_object(self, object_id: UUID) -> StoredObject | None:
        return self.objects.get(object_id)

    def find_objects_by_run_id(self, run_id: UUID) -> list[StoredObject]:
        return sorted(
            [
                obj
                for obj in self.objects.values()
                if obj.run_id == run_id and obj.deleted_at is None
            ],
            key=lambda obj: (obj.object_key, obj.filename),
        )

    def find_one(
        self,
        *,
        run_id: UUID | None,
        object_kind: str | None,
        filename: str | None,
        logical_name: str | None,
    ) -> StoredObject | None:
        for obj in sorted(
            self.objects.values(),
            key=lambda item: item.created_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        ):
            if obj.deleted_at is not None:
                continue
            if run_id is not None and obj.run_id != run_id:
                continue
            if object_kind is not None and obj.object_kind != object_kind:
                continue
            if filename is not None and obj.filename != filename:
                continue
            if logical_name is not None and obj.logical_name != logical_name:
                continue
            return obj
        return None

    def find_by_logical_name(
        self,
        *,
        domain: str,
        logical_name: str,
        object_scope: str | None,
    ) -> list[StoredObject]:
        return [
            obj
            for obj in self.objects.values()
            if obj.deleted_at is None
            and obj.domain == domain
            and obj.logical_name == logical_name
            and (object_scope is None or obj.object_scope == object_scope)
        ]

    def find_expired_objects(self, *, limit: int) -> list[StoredObject]:
        now = datetime.now(UTC)
        return [
            obj
            for obj in self.objects.values()
            if obj.deleted_at is None and obj.expires_at is not None and obj.expires_at <= now
        ][:limit]

    def mark_deleted(self, object_id: UUID, purge_after: datetime | None) -> None:
        obj = self.objects[object_id]
        self.objects[object_id] = replace(
            obj,
            deleted_at=datetime.now(UTC),
            purge_after=purge_after,
            updated_at=datetime.now(UTC),
        )

    def record_delete_error(self, object_id: UUID, error_message: str) -> None:
        obj = self.objects[object_id]
        self.objects[object_id] = replace(
            obj,
            delete_attempts=obj.delete_attempts + 1,
            last_delete_error=error_message,
            updated_at=datetime.now(UTC),
        )

    def find_deleted_objects_for_purge(self, *, limit: int) -> list[StoredObject]:
        now = datetime.now(UTC)
        return [
            obj
            for obj in self.objects.values()
            if obj.deleted_at is not None and obj.purge_after is not None and obj.purge_after <= now
        ][:limit]

    def find_deleted_objects_by_run_id(
        self, run_id: UUID, *, ignore_purge_after: bool
    ) -> list[StoredObject]:
        now = datetime.now(UTC)
        return [
            obj
            for obj in self.objects.values()
            if obj.run_id == run_id
            and obj.deleted_at is not None
            and (
                ignore_purge_after
                or (obj.purge_after is not None and obj.purge_after <= now)
            )
        ]

    def purge_metadata(self, object_id: UUID) -> None:
        self.objects.pop(object_id, None)
