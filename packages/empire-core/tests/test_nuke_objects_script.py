from __future__ import annotations

from pathlib import Path

import pytest

from empire_core.scripts import nuke_objects


def test_select_roots_from_target():
    assert nuke_objects._select_roots("global") == ["global"]
    assert nuke_objects._select_roots("jellyfin") == ["jellyfin"]
    assert nuke_objects._select_roots("both") == ["global", "jellyfin"]


def test_load_root_paths_reads_expected_env(monkeypatch, tmp_path):
    global_root = tmp_path / "global"
    monkeypatch.setenv("EMPIRE_STORAGE_ROOT_GLOBAL", str(global_root))

    paths = nuke_objects._load_root_paths(["global"])

    assert paths == {"global": global_root.resolve()}


def test_filesystem_stats_counts_nested_contents(tmp_path):
    root = tmp_path / "store"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "one.txt").write_bytes(b"123")
    (root / "two.txt").write_bytes(b"12345")

    stats = nuke_objects._load_filesystem_stats(root)

    assert stats.files == 2
    assert stats.dirs == 2
    assert stats.bytes == 8


def test_empty_directory_removes_contents_but_keeps_root(tmp_path):
    root = tmp_path / "store"
    nested = root / "a"
    nested.mkdir(parents=True)
    (nested / "one.txt").write_text("hello")
    (root / "two.txt").write_text("world")

    nuke_objects._empty_directory(root)

    assert root.exists()
    assert list(root.iterdir()) == []


def test_validate_plans_rejects_db_path_mismatch(tmp_path):
    path = tmp_path / "env-root"
    path.mkdir()
    db_path = tmp_path / "db-root"
    db_path.mkdir()
    plan = nuke_objects.RootPlan(
        root_name="global",
        env_name="EMPIRE_STORAGE_ROOT_GLOBAL",
        path=path,
        storage_root_id=1,
        db_base_uri=str(db_path),
        db_total_rows=0,
        db_active_rows=0,
        db_deleted_rows=0,
        db_size_bytes=0,
        fs_files=0,
        fs_dirs=0,
        fs_bytes=0,
    )

    with pytest.raises(ValueError, match="environment path does not match"):
        nuke_objects._validate_plans([plan])


def test_confirm_requires_exact_phrase(monkeypatch, tmp_path):
    plan = nuke_objects.RootPlan(
        root_name="global",
        env_name="EMPIRE_STORAGE_ROOT_GLOBAL",
        path=Path(tmp_path),
        storage_root_id=1,
        db_base_uri=str(tmp_path),
        db_total_rows=0,
        db_active_rows=0,
        db_deleted_rows=0,
        db_size_bytes=0,
        fs_files=0,
        fs_dirs=0,
        fs_bytes=0,
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "nuke global")

    assert nuke_objects._confirm([plan]) is True
