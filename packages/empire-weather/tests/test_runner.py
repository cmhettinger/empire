from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from empire_core import ObjectStore, RunService

from empire_weather.collector import WeatherCollector
from empire_weather.config import WeatherCollectionConfig
from empire_weather.models import RawProviderResponse, WeatherCollectionResult
from empire_weather.providers.imagery import WeatherImageDownload
from empire_weather.runner import DEFAULT_OUTPUT_FILENAME, run_weather_collection_to_object_store

from fakes import InMemoryObjectRepository, InMemoryRunRepository
from test_config import CONFIG


def test_run_weather_collection_to_object_store(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPIRE_STORAGE_KEY_WEATHER", "/weather/")
    run_repo = InMemoryRunRepository()
    object_repo = InMemoryObjectRepository(str(tmp_path))
    run_service = RunService(run_repo)
    object_store = ObjectStore(object_repo)
    config = WeatherCollectionConfig.from_mapping(CONFIG)
    generated_at = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)

    result = run_weather_collection_to_object_store(
        config=config,
        collector=FakeCollector(config),
        run_service=run_service,
        object_store=object_store,
        run_type="manual",
        runner="pytest",
        generated_at=generated_at,
    )

    run_id = result.run_context.run_id
    stored = result.stored_object
    assert run_repo.runs[run_id].status == "succeeded"
    assert stored.object_key == f"weather/runs/2026/05/30/{run_id}"
    assert stored.filename == DEFAULT_OUTPUT_FILENAME
    assert stored.expires_at == generated_at + timedelta(days=7)
    assert stored.metadata["location_count"] == 1
    assert result.raw_object_count == 2
    assert result.image_object_count == 0

    payload = json.loads(object_store.get_bytes(stored.object_id))
    assert payload["run_id"] == str(run_id)
    assert payload["locations"]["ashburn_va"]["name"] == "Ashburn"

    raw_objects = [
        obj
        for obj in object_repo.objects.values()
        if obj.object_kind == "raw_provider_response"
    ]
    assert len(raw_objects) == 2
    raw_by_provider = {obj.metadata["provider"]: obj for obj in raw_objects}
    assert raw_by_provider["openweather"].object_key.endswith("/raw/ashburn_va/openweather/onecall")
    assert raw_by_provider["openweather"].expires_at == generated_at + timedelta(days=7)
    assert raw_by_provider["accuweather"].object_key.endswith(
        "/raw/ashburn_va/accuweather/health_activities"
    )
    assert raw_by_provider["accuweather"].content_type == "text/html"


def test_run_weather_collection_stores_enabled_imagery(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPIRE_STORAGE_KEY_WEATHER", "/weather/")
    run_repo = InMemoryRunRepository()
    object_repo = InMemoryObjectRepository(str(tmp_path))
    run_service = RunService(run_repo)
    object_store = ObjectStore(object_repo)
    config = WeatherCollectionConfig.from_mapping(
        {
            "weather": {
                **CONFIG["weather"],
                "imagery": {
                    "enabled": True,
                    "retention_days": 3,
                    "continue_on_error": True,
                    "products": {
                        "satellite_geocolor_conus": {
                            "enabled": True,
                            "provider": "goes_star",
                            "output_file": "satellite_geocolor_conus.jpg",
                            "content_type": "image/jpeg",
                            "url": "https://example.test/satellite.jpg",
                        },
                        "disabled_product": {
                            "enabled": False,
                            "provider": "wpc",
                            "output_file": "disabled.png",
                            "content_type": "image/png",
                            "url": "https://example.test/disabled.png",
                        },
                    },
                },
            }
        }
    )
    generated_at = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
    downloader = FakeImageryDownloader()

    result = run_weather_collection_to_object_store(
        config=config,
        collector=FakeCollector(config),
        run_service=run_service,
        object_store=object_store,
        run_type="manual",
        runner="pytest",
        generated_at=generated_at,
        imagery_downloader=downloader,
    )

    assert downloader.product_names == ["satellite_geocolor_conus"]
    image_objects = [
        obj
        for obj in object_repo.objects.values()
        if obj.object_kind == "weather_image"
    ]
    assert len(image_objects) == 1
    image_object = image_objects[0]
    assert image_object.object_key == f"weather/runs/2026/05/30/{result.run_context.run_id}/images"
    assert image_object.filename == "satellite_geocolor_conus.jpg"
    assert image_object.content_type == "image/jpeg"
    assert image_object.expires_at == generated_at + timedelta(days=3)
    assert image_object.metadata["name"] == "satellite_geocolor_conus"
    assert image_object.metadata["source_url"] == "https://example.test/satellite.jpg"

    payload = json.loads(object_store.get_bytes(result.stored_object.object_id))
    assert payload["images"] == [
        {
            "name": "satellite_geocolor_conus",
            "output_file": "satellite_geocolor_conus.jpg",
            "content_type": "image/jpeg",
            "object_id": str(image_object.object_id),
        }
    ]
    assert object_store.get_bytes(image_object.object_id) == b"fake-image-bytes"
    assert result.stored_object.metadata["image_count"] == 1
    assert result.image_object_count == 1
    assert run_repo.runs[result.run_context.run_id].summary["image_object_count"] == 1


def test_run_failure_marks_run_failed(tmp_path):
    run_repo = InMemoryRunRepository()
    run_service = RunService(run_repo)
    object_store = ObjectStore(InMemoryObjectRepository(str(tmp_path)))
    config = WeatherCollectionConfig.from_mapping(CONFIG)

    with pytest.raises(RuntimeError, match="boom"):
        run_weather_collection_to_object_store(
            config=config,
            collector=FailingCollector(config=config),
            run_service=run_service,
            object_store=object_store,
            run_type="manual",
            runner="pytest",
            generated_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        )

    run = next(iter(run_repo.runs.values()))
    assert run.status == "failed"
    assert run.summary == {"failed_step": "weather_collection_to_object_store"}


class FakeCollector(WeatherCollector):
    def __init__(self, config):
        self.config = config

    def collect(self, *, generated_at=None, run_id=None):
        return WeatherCollectionResult(
            payload={
                "schema_version": 1,
                "source": "empire-weather",
                "run_id": run_id,
                "generated_at": generated_at.isoformat(),
                "locations": {"ashburn_va": {"name": "Ashburn"}},
            },
            raw_responses=[
                RawProviderResponse(
                    provider="openweather",
                    location_key="ashburn_va",
                    endpoint="onecall",
                    filename="onecall.json",
                    payload={"ok": True},
                ),
                RawProviderResponse(
                    provider="accuweather",
                    location_key="ashburn_va",
                    endpoint="health_activities",
                    filename="health_activities.html",
                    payload="<html>Tree Pollen High</html>",
                    content_type="text/html",
                ),
            ],
        )


class FailingCollector(WeatherCollector):
    def collect(self, *, generated_at=None, run_id=None):
        raise RuntimeError("boom")


class FakeImageryDownloader:
    def __init__(self):
        self.product_names = []

    def download(self, product):
        self.product_names.append(product.name)
        return WeatherImageDownload(
            product=product,
            data=b"fake-image-bytes",
            content_type=product.content_type,
        )
