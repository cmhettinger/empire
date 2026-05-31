from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from empire_core import ObjectStore, RunService
from empire_core.object_store.models import StorageRoot, StoredObject
from empire_core.run_context.models import RunContext

from empire_youtube.config import YouTubeScraperConfig
from empire_youtube.models import NormalizedVideo, YouTubeScrapeResult
from empire_youtube.runner import (
    DEFAULT_OUTPUT_FILENAME,
    run_youtube_scraper_to_object_store,
)


def test_run_youtube_scraper_to_object_store(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPIRE_STORAGE_KEY_YOUTUBE", "youtube")
    monkeypatch.delenv("EMPIRE_YOUTUBE_DAYS_TO_KEEP", raising=False)
    run_repo = InMemoryRunRepository()
    object_repo = InMemoryObjectRepository(str(tmp_path))
    run_service = RunService(run_repo)
    object_store = ObjectStore(object_repo)
    config = _config()
    generated_at = datetime(2026, 5, 23, 22, 0, tzinfo=UTC)

    result = run_youtube_scraper_to_object_store(
        config=config,
        scraper=FakeScraper(config),
        run_service=run_service,
        object_store=object_store,
        run_type="manual",
        runner="pytest",
        generated_at=generated_at,
    )

    run_id = result.run_context.run_id
    stored = result.stored_object
    assert run_repo.runs[run_id].status == "succeeded"
    assert stored.object_key == f"youtube/daily/2026/05/23/{run_id}"
    assert stored.filename == DEFAULT_OUTPUT_FILENAME
    assert stored.object_kind == "normalized_payload"
    assert stored.content_type == "application/json"
    assert stored.expires_at is not None
    assert stored.expires_at - datetime.now(UTC) <= timedelta(days=10, seconds=1)
    assert stored.expires_at - datetime.now(UTC) > timedelta(days=9, hours=23)
    assert stored.metadata == {
        "config_name": "daily_youtube_scraper",
        "config_version": 1,
        "schema_version": 1,
        "video_count": 1,
        "window_hours": 26,
    }

    payload = json.loads(object_store.get_bytes(stored.object_id))
    assert payload["run_id"] == str(run_id)
    assert payload["videos"][0]["video_id"] == "abc123"
    assert run_repo.runs[run_id].summary == {
        "stored_object_id": str(stored.object_id),
        "video_count": 1,
        "object_key": f"youtube/daily/2026/05/23/{run_id}",
        "filename": DEFAULT_OUTPUT_FILENAME,
    }


def test_run_failure_marks_run_failed(tmp_path):
    run_repo = InMemoryRunRepository()
    run_service = RunService(run_repo)
    object_store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))

    with pytest.raises(RuntimeError, match="boom"):
        run_youtube_scraper_to_object_store(
            config=_config(),
            scraper=FailingScraper(),
            run_service=run_service,
            object_store=object_store,
            run_type="manual",
            runner="pytest",
            generated_at=datetime(2026, 5, 23, 22, 0, tzinfo=UTC),
        )

    run = next(iter(run_repo.runs.values()))
    assert run.status == "failed"
    assert run.summary == {"failed_step": "youtube_scrape_to_object_store"}


def _config():
    return YouTubeScraperConfig.from_mapping(
        {
            "youtube": {
                "name": "daily_youtube_scraper",
                "version": 1,
                "lookback_hours": 26,
                "max_results_per_query": 10,
                "followed_channels": [
                    {
                        "channel_name": "All-In Podcast",
                        "channel_id": "UCESLZhusAkFfsNsApnjF_Cg",
                    }
                ],
            }
        }
    )


class FakeScraper:
    def __init__(self, config):
        self.config = config

    def scrape(self, *, generated_at, run_id):
        return YouTubeScrapeResult(
            source="youtube",
            generated_at=generated_at,
            window_hours=self.config.lookback_hours,
            run_id=run_id,
            config_name=self.config.name,
            config_version=self.config.version,
            videos=[
                NormalizedVideo(
                    video_id="abc123",
                    url="https://www.youtube.com/watch?v=abc123",
                    title="Example",
                    description="Description",
                    channel_id="UC123",
                    channel_name="Example Channel",
                    published_at="2026-05-23T12:00:00Z",
                )
            ],
        )


class FailingScraper:
    def scrape(self, *, generated_at, run_id):
        raise RuntimeError("boom")


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
