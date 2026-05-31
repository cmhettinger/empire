"""OpenWeather provider client."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from empire_weather.config import OpenWeatherConfig, WeatherLocationConfig
from empire_weather.exceptions import WeatherProviderError
from empire_weather.models import ProviderLocationData, RawProviderResponse


class OpenWeatherProvider:
    """Collect structured weather data from OpenWeather."""

    provider_name = "openweather"

    def __init__(self, config: OpenWeatherConfig, *, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()

    def collect_location(
        self,
        location: WeatherLocationConfig,
        *,
        collected_at: datetime,
        store_raw: bool,
    ) -> ProviderLocationData:
        onecall, raw_responses = self._collect_onecall(location, store_raw=store_raw)

        air_quality: dict[str, Any] | None = None
        if self.config.collect_air_quality:
            air_quality = self._get_json(
                "/data/2.5/air_pollution",
                params={
                    "lat": location.lat,
                    "lon": location.lon,
                    "appid": self.config.api_key,
                },
                endpoint_name="air_pollution",
            )
            if store_raw:
                raw_responses.append(
                    RawProviderResponse(
                        provider=self.provider_name,
                        location_key=location.key,
                        endpoint="air_pollution",
                        filename="air_pollution.json",
                        payload=air_quality,
                    )
                )

        data: dict[str, Any] = {"onecall": onecall}
        if air_quality is not None:
            data["air_quality"] = air_quality
        return ProviderLocationData(
            provider=self.provider_name,
            location_key=location.key,
            collected_at=collected_at,
            data=data,
            raw_responses=raw_responses,
        )

    def _collect_onecall(
        self,
        location: WeatherLocationConfig,
        *,
        store_raw: bool,
    ) -> tuple[dict[str, Any], list[RawProviderResponse]]:
        current = self._get_json(
            "/data/4.0/onecall/current",
            params=self._location_params(location),
            endpoint_name="onecall_current",
        )
        minutely = (
            self._get_json(
                "/data/4.0/onecall/timeline/1min",
                params=self._location_params(location),
                endpoint_name="onecall_timeline_1min",
            )
            if self.config.collect_minutely
            else {}
        )
        quarter_hourly = (
            self._get_json(
                "/data/4.0/onecall/timeline/15min",
                params=self._location_params(location),
                endpoint_name="onecall_timeline_15min",
            )
            if self.config.collect_quarter_hourly
            else {}
        )
        hourly = self._get_json(
            "/data/4.0/onecall/timeline/1h",
            params=self._location_params(location),
            endpoint_name="onecall_timeline_1h",
        )
        daily = self._get_json(
            "/data/4.0/onecall/timeline/1day",
            params=self._location_params(location),
            endpoint_name="onecall_timeline_1day",
        )

        raw_responses = []
        if store_raw:
            raw_responses.append(_raw(location, "onecall_current", "current.json", current))
            if minutely:
                raw_responses.append(
                    _raw(location, "onecall_timeline_1min", "timeline_1min.json", minutely)
                )
            if quarter_hourly:
                raw_responses.append(
                    _raw(
                        location,
                        "onecall_timeline_15min",
                        "timeline_15min.json",
                        quarter_hourly,
                    )
                )
            raw_responses.append(_raw(location, "onecall_timeline_1h", "timeline_1h.json", hourly))
            raw_responses.append(
                _raw(location, "onecall_timeline_1day", "timeline_1day.json", daily)
            )

        alert_details: list[dict[str, Any]] = []
        if self.config.collect_alert_details:
            for alert_id in _alert_ids(current, minutely, quarter_hourly, hourly, daily):
                alert = self._get_json(
                    f"/data/4.0/onecall/alert/{alert_id}",
                    params={"appid": self.config.api_key},
                    endpoint_name="onecall_alert",
                )
                alert_details.append(alert)
                if store_raw:
                    safe_alert_id = str(alert_id).replace("/", "_")
                    raw_responses.append(
                        _raw(
                            location,
                            "onecall_alert",
                            f"alert_{safe_alert_id}.json",
                            alert,
                        )
                    )

        return _combined_onecall_4_payload(
            current=current,
            minutely=minutely,
            quarter_hourly=quarter_hourly,
            hourly=hourly,
            daily=daily,
            alert_details=alert_details,
        ), raw_responses

    def _location_params(self, location: WeatherLocationConfig) -> dict[str, Any]:
        return {
            "lat": location.lat,
            "lon": location.lon,
            "appid": self.config.api_key,
            "units": self.config.units,
        }

    def _get_json(self, path: str, *, params: dict[str, Any], endpoint_name: str) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}{path}"
        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise WeatherProviderError(f"OpenWeather {endpoint_name} request failed: {exc}") from exc
        if response.status_code >= 400:
            raise WeatherProviderError(
                f"OpenWeather {endpoint_name} request failed: "
                f"status={response.status_code} body={response.text[:500]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise WeatherProviderError(f"OpenWeather {endpoint_name} returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise WeatherProviderError(f"OpenWeather {endpoint_name} returned non-object JSON.")
        return payload


def _combined_onecall_4_payload(
    *,
    current: dict[str, Any],
    minutely: dict[str, Any],
    quarter_hourly: dict[str, Any],
    hourly: dict[str, Any],
    daily: dict[str, Any],
    alert_details: list[dict[str, Any]],
) -> dict[str, Any]:
    current_items = _data_items(current)
    return {
        "lat": current.get("lat", hourly.get("lat", daily.get("lat"))),
        "lon": current.get("lon", hourly.get("lon", daily.get("lon"))),
        "timezone": current.get("timezone", hourly.get("timezone", daily.get("timezone"))),
        "timezone_offset": current.get(
            "timezone_offset",
            hourly.get("timezone_offset", daily.get("timezone_offset")),
        ),
        "current": current_items[0] if current_items else {},
        "minutely": _data_items(minutely),
        "quarter_hourly": _data_items(quarter_hourly),
        "hourly": _data_items(hourly),
        "daily": _data_items(daily),
        "alert_details": alert_details,
        "source_api_version": "4.0",
    }


def _data_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("data")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _alert_ids(*payloads: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for payload in payloads:
        for item in _data_items(payload):
            alerts = item.get("alerts")
            if not isinstance(alerts, list):
                continue
            for alert_id in alerts:
                if not alert_id:
                    continue
                parsed = str(alert_id)
                if parsed not in seen:
                    ids.append(parsed)
                    seen.add(parsed)
    return ids


def _raw(
    location: WeatherLocationConfig,
    endpoint: str,
    filename: str,
    payload: dict[str, Any],
) -> RawProviderResponse:
    return RawProviderResponse(
        provider=OpenWeatherProvider.provider_name,
        location_key=location.key,
        endpoint=endpoint,
        filename=filename,
        payload=payload,
    )
