"""Empire run-context and object-store runner for weather collection."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from empire_core import ObjectStore, RunContext, RunService, StoredObject

from empire_weather.collector import WeatherCollector
from empire_weather.config import WeatherCollectionConfig, WeatherImageryProductConfig
from empire_weather.exceptions import WeatherProviderError
from empire_weather.models import WeatherCollectionResult
from empire_weather.providers.imagery import WeatherImageDownload, WeatherImageryProvider


DEFAULT_DOMAIN = "weather"
DEFAULT_SUBJECT_KEY = "all_locations"
DEFAULT_STORAGE_ROOT = "global"
DEFAULT_STORAGE_KEY = "weather"
DEFAULT_OUTPUT_FILENAME = "weather.json"
DEFAULT_OUTPUT_CONTENT_TYPE = "application/json"
DEFAULT_OUTPUT_OBJECT_KIND = "normalized_payload"
DEFAULT_RAW_CONTENT_TYPE = "application/json"
DEFAULT_RAW_OBJECT_KIND = "raw_provider_response"
DEFAULT_IMAGE_OBJECT_KIND = "weather_image"


logger = logging.getLogger(__name__)


class WeatherImageryDownloader(Protocol):
    """Downloader interface for weather image products."""

    def download(self, product: WeatherImageryProductConfig) -> WeatherImageDownload:
        ...


@dataclass(frozen=True)
class WeatherCollectionRunResult:
    """Result of an Empire-backed weather collection run."""

    run_context: RunContext
    collection_result: WeatherCollectionResult
    stored_object: StoredObject
    raw_object_count: int
    image_object_count: int


def run_weather_collection_to_object_store(
    *,
    config: WeatherCollectionConfig,
    collector: WeatherCollector,
    run_service: RunService,
    object_store: ObjectStore,
    run_type: str,
    runner: str,
    runner_ref: dict | None = None,
    effective_date: date | None = None,
    generated_at: datetime | None = None,
    storage_root: str | None = None,
    storage_key_prefix: str | None = None,
    imagery_downloader: WeatherImageryDownloader | None = None,
) -> WeatherCollectionRunResult:
    """Run weather collection and store normalized JSON and raw responses."""

    generated_at = generated_at or datetime.now(UTC)
    effective_date = effective_date or generated_at.date()
    resolved_storage_root = storage_root or DEFAULT_STORAGE_ROOT
    resolved_storage_key = storage_key_prefix or os.environ.get(
        "EMPIRE_STORAGE_KEY_WEATHER",
        DEFAULT_STORAGE_KEY,
    )
    expires_at = generated_at + timedelta(days=config.retention_days)
    image_expires_at = generated_at + timedelta(days=config.imagery.retention_days)

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
            "location_count": len(config.enabled_locations),
            "units": config.units,
            "store_raw_responses": config.store_raw_responses,
        },
    )

    try:
        collection_result = collector.collect(
            generated_at=generated_at,
            run_id=str(ctx.run_id),
        )
        object_key = _run_output_key(
            storage_key_prefix=resolved_storage_key,
            effective_date=effective_date,
            run_id=str(ctx.run_id),
        )
        images = _download_and_store_images(
            config=config,
            downloader=imagery_downloader or WeatherImageryProvider(),
            object_store=object_store,
            run_context=ctx,
            storage_root=resolved_storage_root,
            object_key=object_key,
            expires_at=image_expires_at,
        )
        collection_result.payload["images"] = images
        stored = object_store.put_bytes(
            run_context=ctx,
            storage_root=resolved_storage_root,
            object_key=object_key,
            filename=DEFAULT_OUTPUT_FILENAME,
            data=collection_result.to_json().encode("utf-8"),
            content_type=DEFAULT_OUTPUT_CONTENT_TYPE,
            object_kind=DEFAULT_OUTPUT_OBJECT_KIND,
            expires_at=expires_at,
            metadata={
                "config_name": config.name,
                "config_version": config.version,
                "schema_version": collection_result.schema_version,
                "location_count": collection_result.location_count,
                "raw_response_count": len(collection_result.raw_responses),
                "image_count": len(images),
            },
        )
        raw_count = 0
        for raw in collection_result.raw_responses:
            raw_key = f"{object_key}/raw/{raw.location_key}/{raw.provider}/{raw.endpoint}"
            raw_data = (
                raw.payload.encode("utf-8")
                if isinstance(raw.payload, str)
                else json.dumps(raw.payload, indent=2, sort_keys=True).encode("utf-8")
            )
            object_store.put_bytes(
                run_context=ctx,
                storage_root=resolved_storage_root,
                object_key=raw_key,
                filename=raw.filename,
                data=raw_data,
                content_type=raw.content_type,
                object_kind=DEFAULT_RAW_OBJECT_KIND,
                expires_at=expires_at,
                metadata={
                    "location_key": raw.location_key,
                    "provider": raw.provider,
                    "endpoint": raw.endpoint,
                },
            )
            raw_count += 1

        run_service.complete_run(
            ctx.run_id,
            summary={
                "stored_object_id": str(stored.object_id),
                "location_count": collection_result.location_count,
                "raw_object_count": raw_count,
                "image_object_count": len(images),
                "object_key": object_key,
                "filename": DEFAULT_OUTPUT_FILENAME,
            },
        )
        return WeatherCollectionRunResult(
            run_context=ctx,
            collection_result=collection_result,
            stored_object=stored,
            raw_object_count=raw_count,
            image_object_count=len(images),
        )
    except Exception as exc:
        _rollback_if_possible(object_store)
        run_service.fail_run(
            ctx.run_id,
            error_message=str(exc),
            summary={"failed_step": "weather_collection_to_object_store"},
        )
        raise


def _run_output_key(
    *,
    storage_key_prefix: str,
    effective_date: date,
    run_id: str,
) -> str:
    prefix = storage_key_prefix.strip("/")
    return f"{prefix}/runs/{effective_date:%Y}/{effective_date:%m}/{effective_date:%d}/{run_id}"


def _download_and_store_images(
    *,
    config: WeatherCollectionConfig,
    downloader: WeatherImageryDownloader,
    object_store: ObjectStore,
    run_context: RunContext,
    storage_root: str,
    object_key: str,
    expires_at: datetime,
) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for product in config.imagery.enabled_products:
        try:
            downloaded = downloader.download(product)
            stored = object_store.put_bytes(
                run_context=run_context,
                storage_root=storage_root,
                object_key=f"{object_key}/images",
                filename=product.output_file,
                data=downloaded.data,
                content_type=downloaded.content_type,
                object_kind=DEFAULT_IMAGE_OBJECT_KIND,
                expires_at=expires_at,
                metadata={
                    "name": product.name,
                    "provider": product.provider,
                    "source_url": product.url,
                },
            )
        except WeatherProviderError as exc:
            if not config.imagery.continue_on_error:
                raise
            logger.warning("Skipping weather imagery product %s after download failure: %s", product.name, exc)
            continue

        images.append(
            {
                "name": product.name,
                "output_file": product.output_file,
                "content_type": product.content_type,
                "object_id": str(stored.object_id),
            }
        )
    return images


def _rollback_if_possible(object_store: ObjectStore) -> None:
    repository = getattr(object_store, "repository", None)
    rollback = getattr(repository, "rollback", None)
    if callable(rollback):
        rollback()
