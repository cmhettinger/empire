"""Clean active objects associated with one run ID."""

from __future__ import annotations

import os
from uuid import UUID

from empire_core import EmpireDatabase, ObjectStore


def main() -> int:
    run_id = UUID(_required_env("EMPIRE_CLEANUP_RUN_OBJECTS_RUN_ID"))
    dry_run = _env_bool("EMPIRE_CLEANUP_RUN_OBJECTS_DRY_RUN")

    with EmpireDatabase.connect_from_env() as conn:
        object_store = ObjectStore.from_connection(conn)
        objects = object_store.find_objects_by_run_id(run_id)

        if not objects:
            print(f"==> No active objects found for run {run_id}.")
            return 0

        print(f"==> Run {run_id} active_objects={len(objects)}")
        for stored in objects:
            print(
                "    "
                f"{stored.storage_root_name}:{stored.object_key}/{stored.filename} "
                f"object_id={stored.object_id}"
            )

        if dry_run:
            print(f"==> Dry run only; {len(objects)} active objects would be deleted.")
            return 0

        deleted_count = object_store.delete_objects_by_run_id(run_id)
        print(f"==> Deleted {deleted_count} active objects.")
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
