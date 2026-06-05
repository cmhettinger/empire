"""Empire run-context and object-store runner for weather collection."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from empire_core import ObjectStore, RunContext, RunService, StoredObject

from empire_weather.collector import WeatherCollector
from empire_weather.config import WeatherCollectionConfig
from empire_weather.models import WeatherCollectionResult


DEFAULT_DOMAIN = "weather"
DEFAULT_SUBJECT_KEY = "all_locations"
DEFAULT_STORAGE_ROOT = "global"
DEFAULT_STORAGE_KEY = "weather"
DEFAULT_OUTPUT_FILENAME = "weather.json"
DEFAULT_OUTPUT_CONTENT_TYPE = "application/json"
DEFAULT_OUTPUT_OBJECT_KIND = "normalized_payload"
DEFAULT_RAW_CONTENT_TYPE = "application/json"
DEFAULT_RAW_OBJECT_KIND = "raw_provider_response"


@dataclass(frozen=True)
class WeatherCollectionRunResult:
    """Result of an Empire-backed weather collection run."""

    run_context: RunContext
    collection_result: WeatherCollectionResult
    stored_object: StoredObject
    raw_object_count: int


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
                "object_key": object_key,
                "filename": DEFAULT_OUTPUT_FILENAME,
            },
        )
        return WeatherCollectionRunResult(
            run_context=ctx,
            collection_result=collection_result,
            stored_object=stored,
            raw_object_count=raw_count,
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


def _rollback_if_possible(object_store: ObjectStore) -> None:
    repository = getattr(object_store, "repository", None)
    rollback = getattr(repository, "rollback", None)
    if callable(rollback):
        rollback()
