from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from empire_core import ObjectStore, RunService
from empire_core.object_store.models import StorageRoot, StoredObject

from empire_youtube.downloader import (
    MOVIE_FILENAME,
    YouTubeDownloadEntry,
    YouTubeDownloadError,
    cleanup_entry_sidecars,
    download_entry_to_object_store,
    find_download_entry,
    iter_download_entries,
)

from test_runner import InMemoryRunRepository


def test_iter_and_find_download_entries():
    plan = {
        "entries": [
            {
                "video_id": "abc123",
                "title": "Example",
                "object_key": "media/youtube/Channel/Example [abc123]",
                "source_url": "https://www.youtube.com/watch?v=abc123",
                "movie_filename": "movie.mp4",
            }
        ]
    }

    entries = iter_download_entries(plan)

    assert entries[0].video_id == "abc123"
    assert find_download_entry(plan, video_id="abc123") == entries[0]
    with pytest.raises(RuntimeError, match="not found"):
        find_download_entry(plan, video_id="missing")


def test_download_entry_to_object_store(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPIRE_YOUTUBE_DAYS_TO_KEEP", "14")
    run_repo = InMemoryRunRepository()
    object_repo = MultiRootObjectRepository(str(tmp_path))
    run_service = RunService(run_repo)
    object_store = ObjectStore(object_repo)
    ctx = run_service.start_run(
        domain="youtube",
        job_name="youtube_download",
        subject_key="abc123",
        effective_date=date(2026, 5, 30),
        run_type="manual",
        runner="pytest",
    )

    result = download_entry_to_object_store(
        entry=_entry(),
        object_store=object_store,
        run_context=ctx,
        temp_dir=tmp_path / "tmp",
        downloader=FakeDownloader(),
    )

    assert result.status == "downloaded"
    assert result.filename == MOVIE_FILENAME
    stored = object_repo.objects[UUID(result.object_id)]
    assert stored.expires_at is not None
    assert stored.expires_at - datetime.now(UTC) <= timedelta(days=14, seconds=1)
    assert stored.expires_at - datetime.now(UTC) > timedelta(days=13, hours=23)
    assert not (
        tmp_path / "tmp" / "youtube" / "downloads" / str(ctx.run_id) / "abc123"
    ).exists()
    assert object_store.get_bytes(UUID(result.object_id)) == b"video"


def test_download_entry_skips_existing_movie(tmp_path):
    run_repo = InMemoryRunRepository()
    object_repo = MultiRootObjectRepository(str(tmp_path))
    run_service = RunService(run_repo)
    object_store = ObjectStore(object_repo)
    ctx = run_service.start_run(
        domain="youtube",
        job_name="youtube_download",
        subject_key="abc123",
        effective_date=date(2026, 5, 30),
        run_type="manual",
        runner="pytest",
    )
    object_store.put_bytes(
        run_context=ctx,
        storage_root="jellyfin",
        object_key=_entry().object_key,
        filename=MOVIE_FILENAME,
        data=b"existing",
        object_kind="youtube_media_asset",
    )

    result = download_entry_to_object_store(
        entry=_entry(),
        object_store=object_store,
        run_context=ctx,
        temp_dir=tmp_path / "tmp",
        downloader=FailingDownloader(),
    )

    assert result.status == "skipped"
    assert result.skipped is True


def test_cleanup_on_failure_deletes_entry_sidecars(tmp_path):
    run_repo = InMemoryRunRepository()
    object_repo = MultiRootObjectRepository(str(tmp_path))
    run_service = RunService(run_repo)
    object_store = ObjectStore(object_repo)
    ctx = run_service.start_run(
        domain="youtube",
        job_name="youtube_download",
        subject_key="abc123",
        effective_date=date(2026, 5, 30),
        run_type="manual",
        runner="pytest",
    )
    for filename in ("empire.json", "movie.nfo"):
        object_store.put_bytes(
            run_context=ctx,
            storage_root="jellyfin",
            object_key=_entry().object_key,
            filename=filename,
            data=b"sidecar",
        )

    with pytest.raises(YouTubeDownloadError) as exc:
        download_entry_to_object_store(
            entry=_entry(),
            object_store=object_store,
            run_context=ctx,
            temp_dir=tmp_path / "tmp",
            downloader=FailingDownloader(),
            cleanup_on_failure=True,
        )

    assert exc.value.result.status == "failed"
    assert exc.value.result.cleanup_count == 2


def test_cleanup_entry_sidecars(tmp_path):
    run_repo = InMemoryRunRepository()
    object_repo = MultiRootObjectRepository(str(tmp_path))
    object_store = ObjectStore(object_repo)
    ctx = RunService(run_repo).start_run(
        domain="youtube",
        job_name="youtube_download",
        subject_key="abc123",
        effective_date=date(2026, 5, 30),
        run_type="manual",
        runner="pytest",
    )
    object_store.put_bytes(
        run_context=ctx,
        storage_root="jellyfin",
        object_key=_entry().object_key,
        filename="empire.json",
        data=b"sidecar",
    )

    assert cleanup_entry_sidecars(
        object_store=object_store,
        storage_root="jellyfin",
        entry=_entry(),
    ) == 1


def _entry() -> YouTubeDownloadEntry:
    return YouTubeDownloadEntry(
        video_id="abc123",
        title="Example",
        object_key="media/youtube/Channel/Example [abc123]",
        source_url="https://www.youtube.com/watch?v=abc123",
    )


class FakeDownloader:
    def download(self, *, url, output_template):
        assert url == "https://www.youtube.com/watch?v=abc123"
        output_template.parent.mkdir(parents=True, exist_ok=True)
        (output_template.parent / MOVIE_FILENAME).write_bytes(b"video")


class FailingDownloader:
    def download(self, *, url, output_template):
        raise RuntimeError("download failed")


class MultiRootObjectRepository:
    def __init__(self, base_uri: str):
        self.roots = {
            "global": StorageRoot(
                storage_root_id=1,
                root_name="global",
                backend_type="filesystem",
                base_uri=base_uri,
            ),
            "jellyfin": StorageRoot(
                storage_root_id=2,
                root_name="jellyfin",
                backend_type="filesystem",
                base_uri=base_uri,
            ),
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
        root = next(
            root
            for root in self.roots.values()
            if root.storage_root_id == storage_root_id
        )
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

    def find_one(self, *, run_id, object_kind, filename, logical_name):
        return None

    def find_objects_by_run_id(self, run_id):
        return [
            obj
            for obj in self.objects.values()
            if obj.run_id == run_id and obj.deleted_at is None
        ]

    def mark_deleted(self, object_id, purge_after):
        self.objects[object_id] = replace(
            self.objects[object_id],
            deleted_at=datetime.now(UTC),
            purge_after=purge_after,
        )

    def record_delete_error(self, object_id, error_message):
        return None
