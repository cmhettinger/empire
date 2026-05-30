"""Immediately remove local object-store files and metadata for dev roots."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from empire_core import EmpireDatabase
from empire_core.db.postgres import row_to_dict

TARGETS = {
    "global": "EMPIRE_STORAGE_ROOT_GLOBAL",
    "jellyfin": "EMPIRE_STORAGE_ROOT_JELLYFIN",
}


@dataclass(frozen=True)
class RootPlan:
    root_name: str
    env_name: str
    path: Path
    storage_root_id: int | None
    db_base_uri: str | None
    db_total_rows: int
    db_active_rows: int
    db_deleted_rows: int
    db_size_bytes: int
    fs_files: int
    fs_dirs: int
    fs_bytes: int


@dataclass(frozen=True)
class FilesystemStats:
    files: int
    dirs: int
    bytes: int


@dataclass(frozen=True)
class DbStats:
    storage_root_id: int | None
    base_uri: str | None
    total_rows: int
    active_rows: int
    deleted_rows: int
    size_bytes: int


def main() -> int:
    try:
        return _main()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _main() -> int:
    dry_run = _env_bool("EMPIRE_NUKE_OBJECTS_DRY_RUN")
    yes = _env_bool("EMPIRE_NUKE_OBJECTS_YES")
    target = os.environ.get("EMPIRE_NUKE_OBJECTS_TARGET", "").strip().lower()

    root_names = _select_roots(target)
    root_paths = _load_root_paths(root_names)

    with EmpireDatabase.connect_from_env() as conn:
        plans = [
            _build_plan(conn, root_name, root_paths[root_name])
            for root_name in root_names
        ]
        _print_plan(plans)
        _validate_plans(plans)

        if dry_run:
            print("==> Dry run only; no files or database rows changed.")
            return 0

        if not yes and not _confirm(plans):
            print("==> Aborted; no files or database rows changed.")
            return 1

        for plan in plans:
            _empty_directory(plan.path)
            if plan.storage_root_id is not None:
                _delete_stored_object_rows(conn, plan.storage_root_id)
            print(f"==> Nuked {plan.root_name}: {plan.path}")

        conn.commit()

    print("==> Object-store nuke complete.")
    return 0


def _select_roots(target: str) -> list[str]:
    if target:
        if target == "both":
            return list(TARGETS)
        if target in TARGETS:
            return [target]
        raise ValueError("--target must be one of: global, jellyfin, both")

    print("Select object-store root to nuke:")
    print("  1) global   EMPIRE_STORAGE_ROOT_GLOBAL")
    print("  2) jellyfin EMPIRE_STORAGE_ROOT_JELLYFIN")
    print("  3) both")
    choice = input("Choice [1/2/3]: ").strip().lower()
    if choice in {"1", "global", "g"}:
        return ["global"]
    if choice in {"2", "jellyfin", "j"}:
        return ["jellyfin"]
    if choice in {"3", "both", "b"}:
        return list(TARGETS)
    raise ValueError("Invalid choice; expected 1, 2, or 3")


def _load_root_paths(root_names: list[str]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for root_name in root_names:
        env_name = TARGETS[root_name]
        raw_path = os.environ.get(env_name)
        if not raw_path:
            raise ValueError(f"Missing required environment variable: {env_name}")
        paths[root_name] = Path(raw_path).expanduser().resolve()
    return paths


def _build_plan(conn: Any, root_name: str, path: Path) -> RootPlan:
    db_stats = _load_db_stats(conn, root_name)
    fs_stats = _load_filesystem_stats(path)
    return RootPlan(
        root_name=root_name,
        env_name=TARGETS[root_name],
        path=path,
        storage_root_id=db_stats.storage_root_id,
        db_base_uri=db_stats.base_uri,
        db_total_rows=db_stats.total_rows,
        db_active_rows=db_stats.active_rows,
        db_deleted_rows=db_stats.deleted_rows,
        db_size_bytes=db_stats.size_bytes,
        fs_files=fs_stats.files,
        fs_dirs=fs_stats.dirs,
        fs_bytes=fs_stats.bytes,
    )


def _load_db_stats(conn: Any, root_name: str) -> DbStats:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                r.storage_root_id,
                r.base_uri,
                count(o.object_id) AS total_rows,
                count(o.object_id) FILTER (WHERE o.deleted_at IS NULL) AS active_rows,
                count(o.object_id) FILTER (WHERE o.deleted_at IS NOT NULL) AS deleted_rows,
                coalesce(sum(o.size_bytes), 0) AS size_bytes
            FROM core.storage_root r
            LEFT JOIN core.stored_object o
                ON o.storage_root_id = r.storage_root_id
            WHERE r.root_name = %s
            GROUP BY r.storage_root_id, r.base_uri
            """,
            (root_name,),
        )
        row = cursor.fetchone()
        if row is None:
            return DbStats(
                storage_root_id=None,
                base_uri=None,
                total_rows=0,
                active_rows=0,
                deleted_rows=0,
                size_bytes=0,
            )
        data = row_to_dict(cursor, row)
        return DbStats(
            storage_root_id=data["storage_root_id"],
            base_uri=data["base_uri"],
            total_rows=data["total_rows"],
            active_rows=data["active_rows"],
            deleted_rows=data["deleted_rows"],
            size_bytes=data["size_bytes"],
        )


def _load_filesystem_stats(path: Path) -> FilesystemStats:
    if not path.exists():
        return FilesystemStats(files=0, dirs=0, bytes=0)
    if not path.is_dir():
        raise ValueError(f"Storage root is not a directory: {path}")

    file_count = 0
    dir_count = 0
    byte_count = 0
    for child in path.rglob("*"):
        if child.is_symlink():
            file_count += 1
            try:
                byte_count += child.lstat().st_size
            except FileNotFoundError:
                pass
        elif child.is_file():
            file_count += 1
            try:
                byte_count += child.stat().st_size
            except FileNotFoundError:
                pass
        elif child.is_dir():
            dir_count += 1
    return FilesystemStats(files=file_count, dirs=dir_count, bytes=byte_count)


def _print_plan(plans: list[RootPlan]) -> None:
    print("==> Object-store nuke plan")
    for plan in plans:
        print(f"    {plan.root_name} ({plan.env_name})")
        print(f"      path: {plan.path}")
        print(
            "      filesystem: "
            f"{plan.fs_files} files, {plan.fs_dirs} dirs, {_format_bytes(plan.fs_bytes)}"
        )
        print(
            "      database: "
            f"{plan.db_total_rows} stored_object rows "
            f"({plan.db_active_rows} active, {plan.db_deleted_rows} deleted), "
            f"{_format_bytes(plan.db_size_bytes)} recorded"
        )
        if plan.db_base_uri is None:
            print("      database storage_root: missing")
        else:
            print(f"      database storage_root: {plan.db_base_uri}")


def _validate_plans(plans: list[RootPlan]) -> None:
    for plan in plans:
        if plan.path == Path(plan.path.anchor):
            raise ValueError(f"Refusing to nuke filesystem root: {plan.path}")
        if plan.path == Path.home().resolve():
            raise ValueError(f"Refusing to nuke home directory: {plan.path}")
        if not plan.path.exists():
            raise ValueError(f"Storage root directory does not exist: {plan.path}")
        if plan.db_base_uri is None:
            print(
                "WARNING: "
                f"No core.storage_root row found for {plan.root_name}; only files will be removed."
            )
            continue
        db_path = Path(plan.db_base_uri).expanduser().resolve()
        if db_path != plan.path:
            raise ValueError(
                "Refusing to nuke because environment path does not match "
                f"core.storage_root for {plan.root_name}: "
                f"{plan.path} != {db_path}"
            )


def _confirm(plans: list[RootPlan]) -> bool:
    selected = ", ".join(plan.root_name for plan in plans)
    answer = input(
        f"Type 'nuke {selected}' to permanently remove these files and rows: "
    )
    return answer == f"nuke {selected}"


def _empty_directory(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def _delete_stored_object_rows(conn: Any, storage_root_id: int) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM core.stored_object WHERE storage_root_id = %s",
            (storage_root_id,),
        )


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def _env_bool(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
