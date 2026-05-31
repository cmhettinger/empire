from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from empire_core import ObjectStore, RunService

from empire_weather.collector import WeatherCollector
from empire_weather.config import WeatherCollectionConfig
from empire_weather.models import RawProviderResponse, WeatherCollectionResult
from empire_weather.runner import DEFAULT_OUTPUT_FILENAME, run_weather_collection_to_object_store

from fakes import InMemoryObjectRepository, InMemoryRunRepository
from test_config import CONFIG


def test_run_weather_collection_to_object_store(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPIRE_STORAGE_KEY_WEATHER", "/scraper/weather/")
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
    assert stored.object_key == f"scraper/weather/runs/2026/05/30/{run_id}"
    assert stored.filename == DEFAULT_OUTPUT_FILENAME
    assert stored.expires_at == generated_at + timedelta(days=7)
    assert stored.metadata["location_count"] == 1
    assert result.raw_object_count == 1

    payload = json.loads(object_store.get_bytes(stored.object_id))
    assert payload["run_id"] == str(run_id)
    assert payload["locations"]["ashburn_va"]["name"] == "Ashburn"

    raw_objects = [
        obj
        for obj in object_repo.objects.values()
        if obj.object_kind == "raw_provider_response"
    ]
    assert len(raw_objects) == 1
    assert raw_objects[0].object_key.endswith("/raw/ashburn_va/openweather/onecall")
    assert raw_objects[0].expires_at == generated_at + timedelta(days=7)


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
                )
            ],
        )


class FailingCollector(WeatherCollector):
    def collect(self, *, generated_at=None, run_id=None):
        raise RuntimeError("boom")
