"""Empire run-context and object-store runner for YouTube scraping."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime

from empire_core import ObjectStore, RunContext, RunService, StoredObject

from empire_youtube.config import YouTubeScraperConfig
from empire_youtube.models import YouTubeScrapeResult
from empire_youtube.scraper import YouTubeScraper


DEFAULT_DOMAIN = "youtube"
DEFAULT_SUBJECT_KEY = "daily"
DEFAULT_STORAGE_ROOT = "global"
DEFAULT_STORAGE_KEY = "youtube"
DEFAULT_OUTPUT_FILENAME = "youtube-scraper.json"
DEFAULT_OUTPUT_CONTENT_TYPE = "application/json"
DEFAULT_OUTPUT_OBJECT_KIND = "normalized_payload"


@dataclass(frozen=True)
class YouTubeScrapeRunResult:
    """Result of an Empire-backed YouTube scrape run."""

    run_context: RunContext
    scrape_result: YouTubeScrapeResult
    stored_object: StoredObject


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
