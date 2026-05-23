"""Purge deleted object metadata associated with one run ID."""

from __future__ import annotations

import os
from uuid import UUID

from empire_core import EmpireDatabase, ObjectStore


def main() -> int:
    run_id = UUID(_required_env("EMPIRE_PURGE_RUN_OBJECTS_RUN_ID"))
    dry_run = _env_bool("EMPIRE_PURGE_RUN_OBJECTS_DRY_RUN")
    ignore_purge_after = _env_bool("EMPIRE_PURGE_RUN_OBJECTS_IGNORE_PURGE_AFTER")

    with EmpireDatabase.connect_from_env() as conn:
        object_store = ObjectStore.from_connection(conn)
        active_objects = object_store.find_objects_by_run_id(run_id)
        if active_objects:
            print(
                "==> Active objects still exist for this run. "
                "Run run-objects-cleanup first."
            )
            for stored in active_objects:
                print(
                    "    active "
                    f"{stored.storage_root_name}:{stored.object_key}/{stored.filename} "
                    f"object_id={stored.object_id}"
                )
            return 1

        deleted_objects = object_store.find_deleted_objects_by_run_id(
            run_id,
            ignore_purge_after=ignore_purge_after,
        )

        if not deleted_objects:
            if ignore_purge_after:
                print(f"==> No deleted objects found for run {run_id}.")
            else:
                print(f"==> No deleted objects are eligible for purge for run {run_id}.")
            return 0

        print(f"==> Run {run_id} purgeable_deleted_objects={len(deleted_objects)}")
        for stored in deleted_objects:
            print(
                "    "
                f"{stored.storage_root_name}:{stored.object_key}/{stored.filename} "
                f"object_id={stored.object_id} purge_after={stored.purge_after}"
            )

        if dry_run:
            print(
                f"==> Dry run only; {len(deleted_objects)} deleted metadata rows "
                "would be purged."
            )
            return 0

        purged_count = object_store.purge_deleted_objects_by_run_id(
            run_id,
            ignore_purge_after=ignore_purge_after,
        )
        print(f"==> Purged {purged_count} deleted metadata rows.")
        print("==> Run row remains in core.core_run as lineage/history.")

    return 0


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
