from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from empire_core.object_store.models import StorageRoot, StoredObject
from empire_core.run_context.models import RunContext


class InMemoryRunRepository:
    def __init__(self):
        self.runs: dict[UUID, RunContext] = {}

    def start_run(
        self,
        *,
        domain,
        job_name,
        subject_key,
        effective_date,
        run_type,
        runner,
        runner_ref,
        params,
        heartbeat_timeout_seconds,
    ):
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
            started_at=datetime.now(UTC),
        )
        self.runs[ctx.run_id] = ctx
        return ctx

    def complete_run(self, run_id, summary):
        ctx = replace(
            self.runs[run_id],
            status="succeeded",
            completed_at=datetime.now(UTC),
            summary=summary or {},
        )
        self.runs[run_id] = ctx
        return ctx

    def fail_run(self, run_id, error_message, summary):
        ctx = replace(
            self.runs[run_id],
            status="failed",
            completed_at=datetime.now(UTC),
            summary=summary or {},
        )
        self.runs[run_id] = ctx
        return ctx


class InMemoryObjectRepository:
    def __init__(self, base_uri: str):
        self.roots = {
            "global": StorageRoot(
                storage_root_id=1,
                root_name="global",
                backend_type="filesystem",
                base_uri=base_uri,
            ),
            "config": StorageRoot(
                storage_root_id=2,
                root_name="config",
                backend_type="filesystem",
                base_uri=base_uri,
            )
        }
        self.objects: dict[UUID, StoredObject] = {}

    def get_storage_root(self, root_name):
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
        root = self.roots["global"]
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

    def find_objects_by_run_id(self, run_id):
        return [
            obj
            for obj in self.objects.values()
            if obj.run_id == run_id and obj.deleted_at is None
        ]

    def find_by_logical_name(self, *, domain, logical_name, object_scope):
        return [
            obj
            for obj in self.objects.values()
            if obj.deleted_at is None
            and obj.domain == domain
            and obj.logical_name == logical_name
            and (object_scope is None or obj.object_scope == object_scope)
        ]
