"""Completely remove one run and its stored objects."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID

from empire_core import EmpireDatabase, ObjectStore


@dataclass(frozen=True)
class RunRow:
    run_id: UUID
    domain: str
    job_name: str
    status: str


def main() -> int:
    run_id = UUID(_required_env("EMPIRE_NUKE_RUN_RUN_ID"))
    dry_run = _env_bool("EMPIRE_NUKE_RUN_DRY_RUN")

    with EmpireDatabase.connect_from_env() as conn:
        run = _get_run(conn, run_id)
        if run is None:
            print(f"==> Run not found: {run_id}")
            return 0

        object_store = ObjectStore.from_connection(conn)
        active_objects = object_store.find_objects_by_run_id(run_id)
        deleted_objects = object_store.find_deleted_objects_by_run_id(
            run_id,
            ignore_purge_after=True,
        )

        print(
            "==> Run "
            f"{run.run_id} domain={run.domain} job_name={run.job_name} status={run.status}"
        )
        print(f"==> Active objects: {len(active_objects)}")
        for stored in active_objects:
            print(
                "    active "
                f"{stored.storage_root_name}:{stored.object_key}/{stored.filename} "
                f"object_id={stored.object_id}"
            )

        print(f"==> Deleted metadata rows: {len(deleted_objects)}")
        for stored in deleted_objects:
            print(
                "    deleted "
                f"{stored.storage_root_name}:{stored.object_key}/{stored.filename} "
                f"object_id={stored.object_id}"
            )

        if dry_run:
            print("==> Dry run only; no files or database rows changed.")
            return 0

        deleted_count = object_store.delete_objects_by_run_id(run_id)
        remaining_active = object_store.find_objects_by_run_id(run_id)
        if remaining_active:
            print(
                "ERROR: Some active objects could not be deleted. "
                "Run row was not removed."
            )
            return 1

        purged_count = object_store.purge_deleted_objects_by_run_id(
            run_id,
            ignore_purge_after=True,
        )
        _delete_run(conn, run_id)

        print(f"==> Deleted {deleted_count} active objects.")
        print(f"==> Purged {purged_count} deleted metadata rows.")
        print(f"==> Deleted run row {run_id}.")

    return 0


def _get_run(conn, run_id: UUID) -> RunRow | None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT run_id, domain, job_name, status
            FROM core.core_run
            WHERE run_id = %s
            """,
            (run_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return RunRow(
            run_id=row[0],
            domain=row[1],
            job_name=row[2],
            status=row[3],
        )


def _delete_run(conn, run_id: UUID) -> None:
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM core.core_run WHERE run_id = %s", (run_id,))
    conn.commit()


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _env_bool(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
