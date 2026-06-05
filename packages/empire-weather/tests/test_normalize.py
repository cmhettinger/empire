from __future__ import annotations

from datetime import UTC, datetime

from empire_weather.config import WeatherCollectionConfig
from empire_weather.models import ProviderLocationData
from empire_weather.normalize import normalize_weather_payload

from test_config import CONFIG


def test_normalized_payload_is_date_oriented():
    config = WeatherCollectionConfig.from_mapping(CONFIG)
    generated_at = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
    provider_data = [
        ProviderLocationData(
            provider="openweather",
            location_key="ashburn_va",
            collected_at=generated_at,
            data={
                "onecall": {
                    "timezone": "America/New_York",
                    "timezone_offset": -14400,
                    "current": {
                        "dt": 1780142400,
                        "temp": 72.5,
                        "feels_like": 73.1,
                        "humidity": 60,
                        "dew_point": 58.0,
                        "wind_speed": 7.0,
                        "wind_deg": 230,
                        "pressure": 1012,
                        "visibility": 10000,
                        "clouds": 20,
                        "uvi": 6.2,
                        "sunrise": 1780120800,
                        "sunset": 1780173600,
                        "weather": [{"id": 800, "main": "Clear", "description": "clear sky"}],
                    },
                    "hourly": [{"dt": 1780146000, "temp": 74, "pop": 0.1}],
                    "minutely": [{"dt": 1780142460, "precipitation": 0.1}],
                    "quarter_hourly": [{"dt": 1780143300, "temp": 73, "pop": 0.2}],
                    "daily": [
                        {
                            "dt": 1780142400,
                            "summary": "Warm",
                            "temp": {"day": 75, "min": 61, "max": 80, "night": 66},
                            "feels_like": {"day": 76, "night": 66},
                            "humidity": 55,
                            "sunrise": 1780120800,
                            "sunset": 1780173600,
                            "moon_phase": 0.5,
                        },
                        {
                            "dt": 1780228800,
                            "summary": "Warm again",
                            "temp": {"day": 76, "min": 62, "max": 81, "night": 67},
                            "feels_like": {"day": 77, "night": 67},
                            "humidity": 56,
                        }
                    ],
                    "alert_details": [
                        {
                            "id": "ow-alert-1",
                            "event": "Heat Advisory",
                            "start": 1780142400,
                            "end": 1780153200,
                            "description": "Hot conditions expected.",
                        }
                    ],
                },
                "air_quality": {
                    "list": [
                        {
                            "dt": 1780142400,
                            "main": {"aqi": 2},
                            "components": {"pm2_5": 4.2},
                        }
                    ]
                },
            },
        ),
        ProviderLocationData(
            provider="nws",
            location_key="ashburn_va",
            collected_at=generated_at,
            data={
                "alerts": {
                    "features": [
                        {
                            "properties": {
                                "id": "alert-1",
                                "event": "Severe Thunderstorm Watch",
                                "effective": "2026-05-30T15:00:00-04:00",
                            }
                        }
                    ]
                },
                "forecast": {
                    "properties": {
                        "periods": [
                            {
                                "name": "Today",
                                "startTime": "2026-05-30T06:00:00-04:00",
                                "temperature": 80,
                                "temperatureUnit": "F",
                                "shortForecast": "Sunny",
                            }
                        ]
                    }
                },
                "forecast_discussion": {
                    "id": "afd-1",
                    "issuanceTime": "2026-05-30T09:30:00Z",
                    "issuingOffice": "LWX",
                    "productName": "Area Forecast Discussion",
                    "productText": "Forecast discussion text.",
                },
            },
        ),
        ProviderLocationData(
            provider="accuweather",
            location_key="ashburn_va",
            collected_at=generated_at,
            data={
                "health_activities": {
                    "source": "accuweather",
                    "source_url": "https://www.accuweather.com/en/us/ashburn/20147/health-activities/2160760",
                    "fetched_at": generated_at.isoformat(),
                    "personal_use_note": (
                        "Collected from the public AccuWeather Health & Activities page for a personal "
                        "Empire daily weather digest."
                    ),
                    "groups": {
                        "allergies": [
                            {"name": "Tree Pollen", "key": "tree_pollen", "level": "High"},
                            {"name": "Dust & Dander", "key": "dust_dander", "level": "Very High"},
                        ],
                        "pests": [{"name": "Mosquitos", "key": "mosquitos", "level": "Extreme"}],
                    },
                }
            },
        ),
    ]

    payload = normalize_weather_payload(
        config=config,
        provider_data=provider_data,
        generated_at=generated_at,
        run_id="run-1",
    )

    location = payload["locations"]["ashburn_va"]
    assert "2026-05-30" in location["dates"]
    day = location["dates"]["2026-05-30"]
    next_day = location["dates"]["2026-05-31"]
    assert day["current_conditions"]["source"] == "openweather"
    assert day["minutely_forecasts"][0]["precipitation"] == {
        "value": 0.1,
        "unit": "millimeters_per_hour",
    }
    assert day["quarter_hourly_forecasts"][0]["temperature"] == {
        "value": 73,
        "unit": "fahrenheit",
    }
    assert day["current_conditions"]["temperature"] == {
        "value": 72.5,
        "unit": "fahrenheit",
    }
    assert day["alerts"][0]["source"] == "nws"
    assert day["alerts"][1]["source"] == "openweather"
    assert day["forecast_discussions"][0]["text"] == "Forecast discussion text."
    assert day["air_quality"][0]["aqi"] == {"value": 2, "unit": "index"}
    assert day["health_activities"]["source"] == "accuweather"
    assert day["health_activities"]["groups"]["allergies"][1] == {
        "name": "Dust & Dander",
        "key": "dust_dander",
        "level": "Very High",
    }
    assert "health_activities" not in next_day
    assert location["provenance"]["alerts"] == ["nws", "openweather"]
    assert location["provenance"]["health_activities"] == "accuweather"
