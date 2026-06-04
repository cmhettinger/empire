from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta

import pytest

from empire_core import ObjectStore, RunService
from empire_core.exceptions import ValidationError

from tests.fakes import InMemoryObjectRepository, InMemoryRunRepository


def _run_context():
    return RunService(InMemoryRunRepository()).start_run(
        domain="weather",
        job_name="weather_refresh",
        subject_key="ashburn-va",
        effective_date=date(2026, 5, 23),
        run_type="airflow",
        runner="airflow",
    )


def test_put_and_get_bytes(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))
    ctx = _run_context()
    data = b'{"temp": 72}'

    stored = store.put_bytes(
        run_context=ctx,
        storage_root="test_root",
        object_key=f"weather/ashburn-va/{ctx.run_id}/raw",
        filename="forecast.json",
        data=data,
        content_type="application/json",
        object_kind="raw_payload",
        metadata={"provider": "openweather"},
    )

    assert stored.run_id == ctx.run_id
    assert stored.domain == "weather"
    assert stored.size_bytes == len(data)
    assert stored.checksum_sha256 == hashlib.sha256(data).hexdigest()
    assert store.get_bytes(stored.object_id) == data


def test_put_file_moves_source_by_default(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path / "store")))
    ctx = _run_context()
    source = tmp_path / "download" / "movie.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video bytes")

    stored = store.put_file(
        run_context=ctx,
        storage_root="test_root",
        object_key="media/youtube/example",
        filename="movie.mp4",
        source_path=source,
        content_type="video/mp4",
        object_kind="media_asset",
    )

    assert not source.exists()
    assert stored.size_bytes == len(b"video bytes")
    assert stored.checksum_sha256 == hashlib.sha256(b"video bytes").hexdigest()
    assert store.get_bytes(stored.object_id) == b"video bytes"


def test_put_file_can_copy_source(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path / "store")))
    source = tmp_path / "download" / "movie.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video bytes")

    stored = store.put_file(
        run_context=None,
        storage_root="test_root",
        object_key="manual/media",
        filename="movie.mp4",
        source_path=source,
        move=False,
    )

    assert source.exists()
    assert stored.object_scope == "manual"
    assert store.get_bytes(stored.object_id) == b"video bytes"


def test_put_file_requires_existing_file(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))

    with pytest.raises(ValidationError):
        store.put_file(
            run_context=None,
            storage_root="test_root",
            object_key="manual/media",
            filename="movie.mp4",
            source_path=tmp_path / "missing.mp4",
        )


def test_multiple_objects_per_run(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))
    ctx = _run_context()

    first = store.put_bytes(
        run_context=ctx,
        storage_root="test_root",
        object_key="runs/raw",
        filename="forecast.json",
        data=b"one",
        object_kind="raw_payload",
    )
    second = store.put_bytes(
        run_context=ctx,
        storage_root="test_root",
        object_key="runs/normalized",
        filename="forecast.json",
        data=b"two",
        object_kind="normalized_payload",
    )

    objects = store.find_objects_by_run_id(ctx.run_id)
    assert {obj.object_id for obj in objects} == {first.object_id, second.object_id}


def test_reference_object_without_run(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))

    stored = store.put_bytes(
        run_context=None,
        object_scope="reference",
        domain="weather",
        logical_name="openweather-icon-10d",
        storage_root="test_root",
        object_key="reference/weather/icons/openweather",
        filename="10d.png",
        data=b"png",
        content_type="image/png",
        object_kind="weather_icon",
    )

    assert stored.run_id is None
    assert stored.object_scope == "reference"
    assert store.find_by_logical_name(
        domain="weather",
        logical_name="openweather-icon-10d",
        object_scope="reference",
    ) == [stored]


def test_put_bytes_can_overwrite_reference_object_path(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))

    first = store.put_bytes(
        run_context=None,
        object_scope="reference",
        domain="weather",
        logical_name="weather-config",
        storage_root="test_root",
        object_key="weather",
        filename="config.yml",
        data=b"version: 1",
        content_type="text/yaml",
        object_kind="weather_config",
    )
    second = store.put_bytes(
        run_context=None,
        object_scope="reference",
        domain="weather",
        logical_name="weather-config",
        storage_root="test_root",
        object_key="weather",
        filename="config.yml",
        data=b"version: 2",
        content_type="text/yaml",
        object_kind="weather_config",
        overwrite=True,
    )

    assert second.object_id == first.object_id
    assert second.size_bytes == len(b"version: 2")
    assert store.get_bytes(second.object_id) == b"version: 2"
    assert store.find_by_logical_name(
        domain="weather",
        logical_name="weather-config",
        object_scope="reference",
    ) == [second]


def test_run_object_requires_run_context(tmp_path):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))

    with pytest.raises(ValidationError):
        store.put_bytes(
            run_context=None,
            object_scope="run",
            storage_root="test_root",
            object_key="runs/raw",
            filename="forecast.json",
            data=b"{}",
        )


@pytest.mark.parametrize(
    ("object_key", "filename"),
    [
        ("../escape", "x.txt"),
        ("/absolute", "x.txt"),
        ("safe", "../x.txt"),
    ],
)
def test_path_traversal_rejection(tmp_path, object_key, filename):
    store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))

    with pytest.raises(ValidationError):
        store.put_bytes(
            run_context=None,
            storage_root="test_root",
            object_key=object_key,
            filename=filename,
            data=b"x",
        )


def test_expired_object_deletion_marks_deleted(tmp_path):
    repo = InMemoryObjectRepository(str(tmp_path))
    store = ObjectStore(repo, tombstone_days=30)
    stored = store.put_bytes(
        run_context=None,
        storage_root="test_root",
        object_key="manual/tmp",
        filename="old.txt",
        data=b"old",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    deleted_count = store.delete_expired_objects()

    deleted = repo.objects[stored.object_id]
    assert deleted_count == 1
    assert deleted.deleted_at is not None
    assert deleted.purge_after is not None
    assert not (tmp_path / "manual" / "tmp" / "old.txt").exists()


def test_delete_object_marks_deleted_and_removes_file(tmp_path):
    repo = InMemoryObjectRepository(str(tmp_path))
    store = ObjectStore(repo)
    stored = store.put_bytes(
        run_context=None,
        storage_root="test_root",
        object_key="manual/tmp",
        filename="delete-me.txt",
        data=b"delete me",
    )

    deleted = store.delete_object(stored.object_id)

    assert deleted is True
    assert repo.objects[stored.object_id].deleted_at is not None
    assert store.delete_object(stored.object_id) is False
    assert not (tmp_path / "manual" / "tmp" / "delete-me.txt").exists()
    assert not (tmp_path / "manual").exists()


def test_delete_objects_by_run_id_marks_deleted_and_removes_files(tmp_path):
    repo = InMemoryObjectRepository(str(tmp_path))
    store = ObjectStore(repo)
    ctx = _run_context()
    first = store.put_bytes(
        run_context=ctx,
        storage_root="test_root",
        object_key="runs/delete",
        filename="first.txt",
        data=b"first",
    )
    second = store.put_bytes(
        run_context=ctx,
        storage_root="test_root",
        object_key="runs/delete",
        filename="second.txt",
        data=b"second",
    )

    deleted_count = store.delete_objects_by_run_id(ctx.run_id)

    assert deleted_count == 2
    assert repo.objects[first.object_id].deleted_at is not None
    assert repo.objects[second.object_id].deleted_at is not None
    assert store.find_objects_by_run_id(ctx.run_id) == []
    assert not (tmp_path / "runs" / "delete" / "first.txt").exists()
    assert not (tmp_path / "runs" / "delete" / "second.txt").exists()
    assert not (tmp_path / "runs").exists()


def test_purge_deleted_objects_by_run_id_respects_purge_after(tmp_path):
    repo = InMemoryObjectRepository(str(tmp_path))
    store = ObjectStore(repo, tombstone_days=30)
    ctx = _run_context()
    stored = store.put_bytes(
        run_context=ctx,
        storage_root="test_root",
        object_key="runs/purge",
        filename="future.txt",
        data=b"future",
    )
    store.delete_object(stored.object_id)

    purged_count = store.purge_deleted_objects_by_run_id(ctx.run_id)

    assert purged_count == 0
    assert stored.object_id in repo.objects


def test_purge_deleted_objects_by_run_id_can_ignore_purge_after(tmp_path):
    repo = InMemoryObjectRepository(str(tmp_path))
    store = ObjectStore(repo, tombstone_days=30)
    ctx = _run_context()
    first = store.put_bytes(
        run_context=ctx,
        storage_root="test_root",
        object_key="runs/purge",
        filename="first.txt",
        data=b"first",
    )
    second = store.put_bytes(
        run_context=ctx,
        storage_root="test_root",
        object_key="runs/purge",
        filename="second.txt",
        data=b"second",
    )
    store.delete_objects_by_run_id(ctx.run_id)

    purged_count = store.purge_deleted_objects_by_run_id(
        ctx.run_id,
        ignore_purge_after=True,
    )

    assert purged_count == 2
    assert first.object_id not in repo.objects
    assert second.object_id not in repo.objects
