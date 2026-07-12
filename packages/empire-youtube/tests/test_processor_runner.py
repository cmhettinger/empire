from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from empire_core import ObjectStore, RunService

from empire_youtube.processor import ThumbnailAsset, YouTubeScrapeProcessor
from empire_youtube.runner import (
    DEFAULT_LIBRARY_PLAN_FILENAME,
    run_youtube_processor_to_object_store,
)

from test_runner import InMemoryObjectRepository, InMemoryRunRepository


def test_run_youtube_processor_to_object_store(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPIRE_STORAGE_KEY_YOUTUBE", "/youtube/")
    monkeypatch.delenv("EMPIRE_STORAGE_KEY_YOUTUBE_LIBRARY", raising=False)
    monkeypatch.setenv("EMPIRE_YOUTUBE_DAYS_TO_KEEP", "7")
    run_repo = InMemoryRunRepository()
    object_repo = InMemoryObjectRepository(str(tmp_path))
    object_repo.roots["jellyfin"] = object_repo.roots["global"]
    run_service = RunService(run_repo)
    object_store = ObjectStore(object_repo)
    generated_at = datetime(2026, 5, 23, 22, 0, tzinfo=UTC)

    result = run_youtube_processor_to_object_store(
        scrape_payload={
            "source": "youtube",
            "schema_version": 1,
            "run_id": "scrape-run",
            "videos": [
                {
                    "video_id": "abc123",
                    "url": "https://www.youtube.com/watch?v=abc123",
                    "title": "Example Video",
                    "channel": {"channel_name": "Example Channel"},
                    "published_at": "2026-05-23T12:00:00Z",
                    "thumbnails": {"maxres": {"url": "https://example.test/max.jpg"}},
                }
            ],
        },
        processor=YouTubeScrapeProcessor(thumbnail_fetcher=FakeThumbnailFetcher()),
        run_service=run_service,
        object_store=object_store,
        run_type="manual",
        runner="pytest",
        generated_at=generated_at,
        source={"type": "file", "path": "/tmp/youtube-scraper.json"},
    )

    run_id = result.run_context.run_id
    stored = result.stored_object
    assert run_repo.runs[run_id].status == "succeeded"
    assert stored.object_key == f"youtube/2026/05/23/{run_id}"
    assert stored.storage_root_name == "global"
    assert stored.filename == DEFAULT_LIBRARY_PLAN_FILENAME
    assert stored.object_kind == "jellyfin_library_plan"
    assert stored.content_type == "application/json"
    assert stored.expires_at is not None
    assert stored.expires_at - datetime.now(UTC) <= timedelta(days=7, seconds=1)
    assert stored.expires_at - datetime.now(UTC) > timedelta(days=6, hours=23)
    assert result.sidecar_object_count == 3
    assert result.skipped_sidecar_count == 0
    assert stored.metadata == {
        "schema_version": 1,
        "source_schema_version": 1,
        "source_run_id": "scrape-run",
        "source_video_count": 1,
        "plan_entry_count": 1,
        "sidecar_object_count": 3,
        "skipped_sidecar_count": 0,
    }

    payload = json.loads(object_store.get_bytes(stored.object_id))
    assert payload["source_video_count"] == 1
    assert payload["entries"][0]["object_key"] == (
        "media/youtube/Example Channel/"
        "2026-05-23 - Example Video [abc123]"
    )
    stored_objects = [
        item
        for item in object_repo.objects.values()
        if item.run_id == run_id
    ]
    assert {item.filename for item in stored_objects} == {
        "empire.json",
        "movie.nfo",
        "fanart.jpg",
        DEFAULT_LIBRARY_PLAN_FILENAME,
    }
    assert all(item.expires_at == stored.expires_at for item in stored_objects)
    assert run_repo.runs[run_id].summary == {
        "stored_object_id": str(stored.object_id),
        "source_video_count": 1,
        "plan_entry_count": 1,
        "sidecar_object_count": 3,
        "skipped_sidecar_count": 0,
        "object_key": f"youtube/2026/05/23/{run_id}",
        "filename": DEFAULT_LIBRARY_PLAN_FILENAME,
    }


def test_processor_reuses_the_supplied_workflow_run_context(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPIRE_STORAGE_KEY_YOUTUBE", "youtube")
    run_repo = InMemoryRunRepository()
    object_repo = InMemoryObjectRepository(str(tmp_path))
    object_repo.roots["jellyfin"] = object_repo.roots["global"]
    run_service = RunService(run_repo)
    workflow_context = run_service.start_run(
        domain="youtube",
        job_name="daily_youtube_scraper",
        subject_key="daily",
        effective_date=datetime(2026, 5, 23, tzinfo=UTC).date(),
        run_type="manual",
        runner="pytest",
    )

    result = run_youtube_processor_to_object_store(
        scrape_payload={
            "source": "youtube",
            "schema_version": 1,
            "run_id": str(workflow_context.run_id),
            "videos": [],
        },
        processor=YouTubeScrapeProcessor(thumbnail_fetcher=FakeThumbnailFetcher()),
        run_service=run_service,
        object_store=ObjectStore(object_repo),
        run_type="manual",
        runner="pytest",
        run_context=workflow_context,
        complete_run=False,
        generated_at=datetime(2026, 5, 23, 22, 0, tzinfo=UTC),
    )

    assert result.run_context.run_id == workflow_context.run_id
    assert list(run_repo.runs) == [workflow_context.run_id]
    assert result.stored_object.object_key == f"youtube/2026/05/23/{workflow_context.run_id}"
    assert run_repo.runs[workflow_context.run_id].status == "started"


def test_run_youtube_processor_skips_existing_sidecars(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPIRE_STORAGE_KEY_YOUTUBE", "/youtube/")
    monkeypatch.delenv("EMPIRE_STORAGE_KEY_YOUTUBE_LIBRARY", raising=False)
    run_repo = InMemoryRunRepository()
    object_repo = InMemoryObjectRepository(str(tmp_path))
    object_repo.roots["jellyfin"] = object_repo.roots["global"]
    run_service = RunService(run_repo)
    object_store = ObjectStore(object_repo)
    generated_at = datetime(2026, 5, 23, 22, 0, tzinfo=UTC)
    payload = {
        "source": "youtube",
        "schema_version": 1,
        "run_id": "scrape-run",
        "videos": [
            {
                "video_id": "abc123",
                "url": "https://www.youtube.com/watch?v=abc123",
                "title": "Example Video",
                "channel": {"channel_name": "Example Channel"},
                "published_at": "2026-05-23T12:00:00Z",
                "thumbnails": {"maxres": {"url": "https://example.test/max.jpg"}},
            }
        ],
    }

    run_youtube_processor_to_object_store(
        scrape_payload=payload,
        processor=YouTubeScrapeProcessor(thumbnail_fetcher=FakeThumbnailFetcher()),
        run_service=run_service,
        object_store=object_store,
        run_type="manual",
        runner="pytest",
        generated_at=generated_at,
    )
    second = run_youtube_processor_to_object_store(
        scrape_payload=payload,
        processor=YouTubeScrapeProcessor(thumbnail_fetcher=FakeThumbnailFetcher()),
        run_service=run_service,
        object_store=object_store,
        run_type="manual",
        runner="pytest",
        generated_at=generated_at,
    )

    second_run = run_repo.runs[second.run_context.run_id]
    assert second.sidecar_object_count == 0
    assert second.skipped_sidecar_count == 3
    assert second_run.summary["sidecar_object_count"] == 0
    assert second_run.summary["skipped_sidecar_count"] == 3
    assert second.stored_object.filename == DEFAULT_LIBRARY_PLAN_FILENAME


def test_run_youtube_processor_skips_existing_sidecar_metadata_without_file(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("EMPIRE_STORAGE_KEY_YOUTUBE", "/youtube/")
    monkeypatch.delenv("EMPIRE_STORAGE_KEY_YOUTUBE_LIBRARY", raising=False)
    run_repo = InMemoryRunRepository()
    object_repo = InMemoryObjectRepository(str(tmp_path))
    object_repo.roots["jellyfin"] = object_repo.roots["global"]
    run_service = RunService(run_repo)
    object_store = ObjectStore(object_repo)
    generated_at = datetime(2026, 5, 23, 22, 0, tzinfo=UTC)
    payload = {
        "source": "youtube",
        "schema_version": 1,
        "run_id": "scrape-run",
        "videos": [
            {
                "video_id": "abc123",
                "url": "https://www.youtube.com/watch?v=abc123",
                "title": "Example Video",
                "channel": {"channel_name": "Example Channel"},
                "published_at": "2026-05-23T12:00:00Z",
            }
        ],
    }
    object_store.put_bytes(
        run_context=RunService(run_repo).start_run(
            domain="youtube",
            job_name="existing",
            subject_key="daily",
            effective_date=generated_at.date(),
            run_type="manual",
            runner="pytest",
        ),
        storage_root="jellyfin",
        object_key="media/youtube/Example Channel/2026-05-23 - Example Video [abc123]",
        filename="empire.json",
        data=b"{}",
    )
    existing_file = (
        tmp_path
        / "media"
        / "youtube"
        / "Example Channel"
        / "2026-05-23 - Example Video [abc123]"
        / "empire.json"
    )
    existing_file.unlink()

    result = run_youtube_processor_to_object_store(
        scrape_payload=payload,
        processor=YouTubeScrapeProcessor(thumbnail_fetcher=FakeThumbnailFetcher()),
        run_service=run_service,
        object_store=object_store,
        run_type="manual",
        runner="pytest",
        generated_at=generated_at,
    )

    assert result.sidecar_object_count == 1
    assert result.skipped_sidecar_count == 1


class FakeThumbnailFetcher:
    def fetch(self, url: str) -> ThumbnailAsset:
        assert url == "https://example.test/max.jpg"
        return ThumbnailAsset(data=b"jpg", content_type="image/jpeg")
