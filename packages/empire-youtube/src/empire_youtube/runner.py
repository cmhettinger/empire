"""Empire run-context and object-store runners for YouTube workflows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime

from empire_core import ObjectStore, RunContext, RunService, StoredObject
from empire_core.object_store.storage import FilesystemStorageBackend

from empire_youtube.config import YouTubeScraperConfig
from empire_youtube.models import YouTubeScrapeResult
from empire_youtube.processor import YouTubeLibraryPlan, YouTubeScrapeProcessor
from empire_youtube.scraper import YouTubeScraper


DEFAULT_DOMAIN = "youtube"
DEFAULT_SUBJECT_KEY = "daily"
DEFAULT_STORAGE_ROOT = "global"
DEFAULT_STORAGE_KEY = "youtube"
DEFAULT_OUTPUT_FILENAME = "youtube-scraper.json"
DEFAULT_OUTPUT_CONTENT_TYPE = "application/json"
DEFAULT_OUTPUT_OBJECT_KIND = "normalized_payload"
DEFAULT_PROCESSOR_JOB_NAME = "youtube_process"
DEFAULT_LIBRARY_STORAGE_ROOT = "jellyfin"
DEFAULT_LIBRARY_STORAGE_KEY = "media/youtube"
DEFAULT_LIBRARY_PLAN_STORAGE_ROOT = "global"
DEFAULT_LIBRARY_PLAN_STORAGE_KEY = "scraper/youtube"
DEFAULT_LIBRARY_PLAN_FILENAME = "youtube-library-plan.json"
DEFAULT_LIBRARY_PLAN_OBJECT_KIND = "jellyfin_library_plan"


@dataclass(frozen=True)
class YouTubeScrapeRunResult:
    """Result of an Empire-backed YouTube scrape run."""

    run_context: RunContext
    scrape_result: YouTubeScrapeResult
    stored_object: StoredObject


@dataclass(frozen=True)
class YouTubeProcessRunResult:
    """Result of an Empire-backed YouTube processing run."""

    run_context: RunContext
    library_plan: YouTubeLibraryPlan
    stored_object: StoredObject
    sidecar_object_count: int
    skipped_sidecar_count: int


def run_youtube_scraper_to_object_store(
    *,
    config: YouTubeScraperConfig,
    scraper: YouTubeScraper,
    run_service: RunService,
    object_store: ObjectStore,
    run_type: str,
    runner: str,
    runner_ref: dict | None = None,
    effective_date: date | None = None,
    generated_at: datetime | None = None,
    storage_root: str | None = None,
    storage_key_prefix: str | None = None,
) -> YouTubeScrapeRunResult:
    """Run the scraper and store normalized JSON in the Empire object store."""

    generated_at = generated_at or datetime.now(UTC)
    effective_date = effective_date or generated_at.date()
    resolved_storage_root = storage_root or os.environ.get(
        "EMPIRE_STORAGE_ROOT_NAME_YOUTUBE",
        DEFAULT_STORAGE_ROOT,
    )
    resolved_storage_key = storage_key_prefix or os.environ.get(
        "EMPIRE_STORAGE_KEY_YOUTUBE",
        DEFAULT_STORAGE_KEY,
    )

    ctx = run_service.start_run(
        domain=DEFAULT_DOMAIN,
        job_name=config.name,
        subject_key=DEFAULT_SUBJECT_KEY,
        effective_date=effective_date,
        run_type=run_type,
        runner=runner,
        runner_ref=runner_ref or {},
        params={
            "config_name": config.name,
            "config_version": config.version,
            "lookback_hours": config.lookback_hours,
            "max_results_per_query": config.max_results_per_query,
        },
    )

    try:
        scrape_result = scraper.scrape(
            generated_at=generated_at,
            run_id=str(ctx.run_id),
        )
        data = scrape_result.to_json().encode("utf-8")
        object_key = _daily_output_key(
            storage_key_prefix=resolved_storage_key,
            effective_date=effective_date,
            run_id=str(ctx.run_id),
        )
        stored = object_store.put_bytes(
            run_context=ctx,
            storage_root=resolved_storage_root,
            object_key=object_key,
            filename=DEFAULT_OUTPUT_FILENAME,
            data=data,
            content_type=DEFAULT_OUTPUT_CONTENT_TYPE,
            object_kind=DEFAULT_OUTPUT_OBJECT_KIND,
            metadata={
                "config_name": config.name,
                "config_version": config.version,
                "schema_version": scrape_result.schema_version,
                "video_count": len(scrape_result.videos),
                "window_hours": scrape_result.window_hours,
            },
        )
        run_service.complete_run(
            ctx.run_id,
            summary={
                "stored_object_id": str(stored.object_id),
                "video_count": len(scrape_result.videos),
                "object_key": object_key,
                "filename": DEFAULT_OUTPUT_FILENAME,
            },
        )
        return YouTubeScrapeRunResult(
            run_context=ctx,
            scrape_result=scrape_result,
            stored_object=stored,
        )
    except Exception as exc:
        _rollback_if_possible(object_store)
        run_service.fail_run(
            ctx.run_id,
            error_message=str(exc),
            summary={"failed_step": "youtube_scrape_to_object_store"},
        )
        raise


def _daily_output_key(
    *,
    storage_key_prefix: str,
    effective_date: date,
    run_id: str,
) -> str:
    prefix = storage_key_prefix.strip("/")
    return (
        f"{prefix}/daily/"
        f"{effective_date:%Y}/{effective_date:%m}/{effective_date:%d}/"
        f"{run_id}"
    )


def run_youtube_processor_to_object_store(
    *,
    scrape_payload: dict,
    processor: YouTubeScrapeProcessor,
    run_service: RunService,
    object_store: ObjectStore,
    run_type: str,
    runner: str,
    runner_ref: dict | None = None,
    source: dict | None = None,
    effective_date: date | None = None,
    generated_at: datetime | None = None,
    storage_root: str | None = None,
    storage_key_prefix: str | None = None,
    plan_storage_root: str | None = None,
    plan_storage_key_prefix: str | None = None,
) -> YouTubeProcessRunResult:
    """Process scraper JSON and store a Jellyfin library plan."""

    generated_at = generated_at or datetime.now(UTC)
    effective_date = effective_date or generated_at.date()
    resolved_storage_root = storage_root or os.environ.get(
        "EMPIRE_STORAGE_ROOT_NAME_YOUTUBE_LIBRARY",
        DEFAULT_LIBRARY_STORAGE_ROOT,
    )
    resolved_storage_key = storage_key_prefix or os.environ.get(
        "EMPIRE_STORAGE_KEY_YOUTUBE_LIBRARY",
        DEFAULT_LIBRARY_STORAGE_KEY,
    )
    resolved_plan_storage_root = plan_storage_root or os.environ.get(
        "EMPIRE_STORAGE_ROOT_NAME_YOUTUBE_LIBRARY_PLAN",
        DEFAULT_LIBRARY_PLAN_STORAGE_ROOT,
    )
    resolved_plan_storage_key = plan_storage_key_prefix or os.environ.get(
        "EMPIRE_STORAGE_KEY_YOUTUBE_LIBRARY_PLAN",
        DEFAULT_LIBRARY_PLAN_STORAGE_KEY,
    )

    videos = scrape_payload.get("videos")
    video_count = len(videos) if isinstance(videos, list) else 0
    ctx = run_service.start_run(
        domain=DEFAULT_DOMAIN,
        job_name=DEFAULT_PROCESSOR_JOB_NAME,
        subject_key=DEFAULT_SUBJECT_KEY,
        effective_date=effective_date,
        run_type=run_type,
        runner=runner,
        runner_ref=runner_ref or {},
        params={
            "source": source or {},
            "source_run_id": scrape_payload.get("run_id"),
            "source_schema_version": scrape_payload.get("schema_version"),
            "source_video_count": video_count,
        },
    )

    try:
        library_plan = processor.process(scrape_payload)
        stored_sidecars: list[StoredObject] = []
        skipped_sidecar_count = 0
        for entry in library_plan.entries:
            for planned_file in entry.files:
                if _object_file_exists(
                    object_store=object_store,
                    storage_root=resolved_storage_root,
                    object_key=entry.object_key,
                    filename=planned_file.filename,
                ):
                    skipped_sidecar_count += 1
                    continue
                stored_sidecars.append(
                    object_store.put_bytes(
                        run_context=ctx,
                        storage_root=resolved_storage_root,
                        object_key=entry.object_key,
                        filename=planned_file.filename,
                        data=planned_file.data,
                        content_type=planned_file.content_type,
                        object_kind=planned_file.object_kind,
                        metadata=planned_file.metadata,
                    )
                )
        data = library_plan.to_json().encode("utf-8")
        object_key = _daily_output_key(
            storage_key_prefix=resolved_plan_storage_key,
            effective_date=effective_date,
            run_id=str(ctx.run_id),
        )
        stored = object_store.put_bytes(
            run_context=ctx,
            storage_root=resolved_plan_storage_root,
            object_key=object_key,
            filename=DEFAULT_LIBRARY_PLAN_FILENAME,
            data=data,
            content_type=DEFAULT_OUTPUT_CONTENT_TYPE,
            object_kind=DEFAULT_LIBRARY_PLAN_OBJECT_KIND,
            metadata={
                "schema_version": library_plan.schema_version,
                "source_schema_version": library_plan.source_schema_version,
                "source_run_id": library_plan.source_run_id,
                "source_video_count": library_plan.source_video_count,
                "plan_entry_count": len(library_plan.entries),
                "sidecar_object_count": len(stored_sidecars),
                "skipped_sidecar_count": skipped_sidecar_count,
            },
        )
        run_service.complete_run(
            ctx.run_id,
            summary={
                "stored_object_id": str(stored.object_id),
                "source_video_count": library_plan.source_video_count,
                "plan_entry_count": len(library_plan.entries),
                "sidecar_object_count": len(stored_sidecars),
                "skipped_sidecar_count": skipped_sidecar_count,
                "object_key": object_key,
                "filename": DEFAULT_LIBRARY_PLAN_FILENAME,
            },
        )
        return YouTubeProcessRunResult(
            run_context=ctx,
            library_plan=library_plan,
            stored_object=stored,
            sidecar_object_count=len(stored_sidecars),
            skipped_sidecar_count=skipped_sidecar_count,
        )
    except Exception as exc:
        run_service.fail_run(
            ctx.run_id,
            error_message=str(exc),
            summary={"failed_step": "youtube_process_to_object_store"},
        )
        raise


def _object_file_exists(
    *,
    object_store: ObjectStore,
    storage_root: str,
    object_key: str,
    filename: str,
) -> bool:
    root = object_store.repository.get_storage_root(storage_root)
    if root is None or root.backend_type != "filesystem":
        return False
    if _stored_object_metadata_exists(
        object_store=object_store,
        storage_root_id=root.storage_root_id,
        object_key=object_key,
        filename=filename,
    ):
        return True
    return FilesystemStorageBackend(root.base_uri).exists(object_key, filename)


def _stored_object_metadata_exists(
    *,
    object_store: ObjectStore,
    storage_root_id: int,
    object_key: str,
    filename: str,
) -> bool:
    repository = object_store.repository
    objects = getattr(repository, "objects", None)
    if isinstance(objects, dict):
        return any(
            obj.storage_root_id == storage_root_id
            and obj.object_key == object_key
            and obj.filename == filename
            and obj.deleted_at is None
            for obj in objects.values()
        )

    connection = getattr(repository, "connection", None)
    if connection is None:
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM core.stored_object
            WHERE storage_root_id = %s
              AND object_key = %s
              AND filename = %s
              AND deleted_at IS NULL
            LIMIT 1
            """,
            (storage_root_id, object_key, filename),
        )
        return cursor.fetchone() is not None


def _rollback_if_possible(object_store: ObjectStore) -> None:
    connection = getattr(object_store.repository, "connection", None)
    if connection is not None:
        connection.rollback()
