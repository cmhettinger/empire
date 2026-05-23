"""Initialize storage_root rows from environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from empire_core import EmpireDatabase

ROOT_PREFIX = "EMPIRE_STORAGE_ROOT_"
ROOT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class StorageRootSpec:
    root_name: str
    base_uri: str


def main() -> int:
    create_dirs = _env_bool("EMPIRE_INIT_STORAGE_ROOTS_CREATE_DIRS")
    dry_run = _env_bool("EMPIRE_INIT_STORAGE_ROOTS_DRY_RUN")
    roots = _load_storage_roots()

    if not roots:
        raise SystemExit(f"No {ROOT_PREFIX}* environment variables found.")

    print("==> Storage roots")
    for root in roots:
        print(f"    {root.root_name}: {root.base_uri}")

    if dry_run:
        print("==> Dry run only; no directories or database rows changed.")
        return 0

    if create_dirs:
        for root in roots:
            path = Path(root.base_uri).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            print(f"==> Ensured directory exists: {path}")

    with EmpireDatabase.connect_from_env() as conn:
        for root in roots:
            row = _upsert_storage_root(conn, root)
            print(
                "==> Upserted storage root "
                f"{row['root_name']} ({row['storage_root_id']}): {row['base_uri']}"
            )

    return 0


def _load_storage_roots() -> list[StorageRootSpec]:
    roots: list[StorageRootSpec] = []
    for key, value in sorted(os.environ.items()):
        if not key.startswith(ROOT_PREFIX):
            continue
        if not value.strip():
            continue

        suffix = key.removeprefix(ROOT_PREFIX).lower()
        if not ROOT_NAME_PATTERN.match(suffix):
            raise ValueError(
                f"Invalid storage root name from {key}: {suffix!r}. "
                "Use letters, numbers, and underscores."
            )

        roots.append(StorageRootSpec(root_name=suffix, base_uri=value.strip()))
    return roots


def _upsert_storage_root(conn, root: StorageRootSpec) -> dict[str, object]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO core.storage_root (
                root_name,
                backend_type,
                base_uri,
                is_active,
                config
            )
            VALUES (
                %s,
                'filesystem',
                %s,
                true,
                '{}'::jsonb
            )
            ON CONFLICT (root_name)
            DO UPDATE SET
                backend_type = EXCLUDED.backend_type,
                base_uri = EXCLUDED.base_uri,
                is_active = true,
                updated_at = now()
            RETURNING storage_root_id, root_name, backend_type, base_uri, is_active
            """,
            (root.root_name, root.base_uri),
        )
        row = cursor.fetchone()
        conn.commit()
        columns = [column.name for column in cursor.description]
        return dict(zip(columns, row))


def _env_bool(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
