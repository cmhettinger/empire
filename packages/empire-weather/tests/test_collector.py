from __future__ import annotations

from datetime import UTC, datetime

import pytest

from empire_weather.collector import WeatherCollector
from empire_weather.config import WeatherCollectionConfig
from empire_weather.exceptions import WeatherProviderError
from empire_weather.models import ProviderLocationData

from test_config import CONFIG


def test_accuweather_provider_failure_is_optional(caplog):
    config = WeatherCollectionConfig.from_mapping(CONFIG)
    collector = WeatherCollector(
        config=config,
        openweather=FakeOpenWeatherProvider(),
        nws=FakeNWSProvider(),
        accuweather=FailingAccuWeatherProvider(),
    )

    result = collector.collect(
        generated_at=datetime(2026, 6, 7, 10, 46, tzinfo=UTC),
        run_id="test-run",
    )

    assert result.payload["run_id"] == "test-run"
    assert "ashburn_va" in result.payload["locations"]
    dates = result.payload["locations"]["ashburn_va"]["dates"]
    assert "health_activities" not in dates["2026-06-07"]
    assert "Skipping optional AccuWeather data for location ashburn_va" in caplog.text


class FakeOpenWeatherProvider:
    provider_name = "openweather"

    def collect_location(self, location, *, collected_at, store_raw):
        return ProviderLocationData(
            provider=self.provider_name,
            location_key=location.key,
            collected_at=collected_at,
            data={
                "onecall": {
                    "timezone": "America/New_York",
                    "timezone_offset": -14400,
                    "current": {
                        "dt": 1780829160,
                        "temp": 78,
                        "weather": [],
                    },
                },
                "air_quality": {"list": []},
            },
        )


class FakeNWSProvider:
    provider_name = "nws"

    def collect_location(self, location, *, collected_at, store_raw):
        return ProviderLocationData(
            provider=self.provider_name,
            location_key=location.key,
            collected_at=collected_at,
            data={
                "forecast": {"properties": {"periods": []}},
                "forecast_hourly": {"properties": {"periods": []}},
                "alerts": {"features": []},
            },
        )


class FailingAccuWeatherProvider:
    def collect_location(self, location, *, collected_at, store_raw):
        raise WeatherProviderError("AccuWeather health_activities request failed: status=403")
