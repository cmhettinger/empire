from __future__ import annotations

import pytest

from empire_weather.config import WeatherCollectionConfig
from empire_weather.exceptions import WeatherConfigError


CONFIG = {
    "weather": {
        "name": "daily_weather",
        "version": 1,
        "units": "imperial",
        "locations": [
            {
                "key": "ashburn_va",
                "name": "Ashburn",
                "county": "Loudoun",
                "state": "Virginia",
                "lat": 39.0277,
                "lon": -77.4714,
                "nws": {"gridId": "LWX", "gridX": 80, "gridY": 76},
            }
        ],
        "providers": {
            "openweather": {"api_key": "test-key"},
            "nws": {"user_agent": "empire-weather-test"},
        },
    }
}


def test_config_from_mapping():
    config = WeatherCollectionConfig.from_mapping(CONFIG)

    assert config.name == "daily_weather"
    assert config.version == 1
    assert config.units == "imperial"
    assert config.store_raw_responses is True
    assert config.retention_days == 7
    assert config.locations[0].key == "ashburn_va"
    assert config.locations[0].nws.grid_id == "LWX"
    assert config.providers.openweather.api_key == "test-key"
    assert config.providers.openweather.collect_minutely is True
    assert config.providers.openweather.collect_quarter_hourly is True
    assert config.providers.openweather.collect_alert_details is True


def test_openweather_key_can_come_from_env(monkeypatch):
    monkeypatch.setenv("EMPIRE_WEATHER_OPENWEATHER_API_KEY", "env-key")
    config_data = dict(CONFIG)
    weather = dict(CONFIG["weather"])
    weather["providers"] = {"openweather": {}, "nws": {}}
    config_data["weather"] = weather

    config = WeatherCollectionConfig.from_mapping(config_data)

    assert config.providers.openweather.api_key == "env-key"


def test_location_keys_must_be_unique():
    config_data = {
        "weather": {
            **CONFIG["weather"],
            "locations": CONFIG["weather"]["locations"] * 2,
        }
    }

    with pytest.raises(WeatherConfigError, match="unique"):
        WeatherCollectionConfig.from_mapping(config_data)
