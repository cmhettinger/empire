from __future__ import annotations

from datetime import UTC, datetime

from empire_weather.config import NWSConfig, OpenWeatherConfig, WeatherCollectionConfig
from empire_weather.providers import NWSProvider, OpenWeatherProvider

from test_config import CONFIG


def test_openweather_provider_collects_onecall_4_timelines_and_air_quality():
    config = WeatherCollectionConfig.from_mapping(CONFIG)
    session = FakeSession(
        {
            "/data/4.0/onecall/current": {
                "timezone": "America/New_York",
                "timezone_offset": -14400,
                "data": [{"dt": 1780142400, "temp": 72, "alerts": ["alert-1"]}],
            },
            "/data/4.0/onecall/timeline/1min": {
                "timezone": "America/New_York",
                "timezone_offset": -14400,
                "data": [{"dt": 1780142460, "precipitation": 0.1}],
            },
            "/data/4.0/onecall/timeline/15min": {
                "timezone": "America/New_York",
                "timezone_offset": -14400,
                "data": [{"dt": 1780143300, "temp": 73}],
            },
            "/data/4.0/onecall/timeline/1h": {
                "timezone": "America/New_York",
                "timezone_offset": -14400,
                "data": [{"dt": 1780146000, "temp": 74}],
            },
            "/data/4.0/onecall/timeline/1day": {
                "timezone": "America/New_York",
                "timezone_offset": -14400,
                "data": [{"dt": 1780142400, "temp": {"day": 75}}],
            },
            "/data/4.0/onecall/alert/alert-1": {
                "id": "alert-1",
                "event": "Heat Advisory",
            },
            "/data/2.5/air_pollution": {"list": []},
        }
    )
    provider = OpenWeatherProvider(
        OpenWeatherConfig(api_key="key", base_url="https://example.test"),
        session=session,
    )

    result = provider.collect_location(
        config.locations[0],
        collected_at=datetime(2026, 5, 30, tzinfo=UTC),
        store_raw=True,
    )

    assert result.data["onecall"]["current"]["temp"] == 72
    assert result.data["onecall"]["minutely"][0]["precipitation"] == 0.1
    assert result.data["onecall"]["quarter_hourly"][0]["temp"] == 73
    assert result.data["onecall"]["hourly"][0]["temp"] == 74
    assert result.data["onecall"]["daily"][0]["temp"]["day"] == 75
    assert result.data["onecall"]["alert_details"][0]["event"] == "Heat Advisory"
    assert result.raw_responses[0].filename == "current.json"
    assert session.requests[0]["params"]["units"] == "imperial"
    assert [request["path"] for request in session.requests[:5]] == [
        "/data/4.0/onecall/current",
        "/data/4.0/onecall/timeline/1min",
        "/data/4.0/onecall/timeline/15min",
        "/data/4.0/onecall/timeline/1h",
        "/data/4.0/onecall/timeline/1day",
    ]


def test_nws_provider_fetches_latest_forecast_discussion():
    config = WeatherCollectionConfig.from_mapping(CONFIG)
    session = FakeSession(
        {
            "/gridpoints/LWX/80,76/forecast": {"properties": {"periods": []}},
            "/gridpoints/LWX/80,76/forecast/hourly": {"properties": {"periods": []}},
            "/alerts/active": {"features": []},
            "/products/types/AFD/locations/LWX": {
                "@graph": [{"id": "https://api.weather.gov/products/AFD123"}]
            },
            "/products/AFD123": {
                "id": "AFD123",
                "productText": "Area forecast discussion text",
            },
        }
    )
    provider = NWSProvider(
        NWSConfig(base_url="https://api.weather.test", user_agent="test-agent"),
        session=session,
    )

    result = provider.collect_location(
        config.locations[0],
        collected_at=datetime(2026, 5, 30, tzinfo=UTC),
        store_raw=True,
    )

    assert result.data["forecast_discussion"]["productText"] == "Area forecast discussion text"
    assert [raw.endpoint for raw in result.raw_responses][-1] == "forecast_discussion"
    assert session.requests[-1]["headers"]["User-Agent"] == "test-agent"


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def get(self, url, **kwargs):
        path = "/" + url.split("/", 3)[3]
        self.requests.append({"url": url, "path": path, **kwargs})
        return FakeResponse(self.responses[path])


class FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload
