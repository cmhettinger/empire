"""National Weather Service provider client."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from empire_weather.config import NWSConfig, WeatherLocationConfig
from empire_weather.exceptions import WeatherProviderError
from empire_weather.models import ProviderLocationData, RawProviderResponse


class NWSProvider:
    """Collect authoritative U.S. weather data from the National Weather Service."""

    provider_name = "nws"

    def __init__(self, config: NWSConfig, *, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()

    def collect_location(
        self,
        location: WeatherLocationConfig,
        *,
        collected_at: datetime,
        store_raw: bool,
    ) -> ProviderLocationData:
        grid = location.nws
        raw_responses: list[RawProviderResponse] = []
        data: dict[str, Any] = {}

        endpoints = {
            "forecast": f"/gridpoints/{grid.grid_id}/{grid.grid_x},{grid.grid_y}/forecast",
            "forecast_hourly": f"/gridpoints/{grid.grid_id}/{grid.grid_x},{grid.grid_y}/forecast/hourly",
            "alerts": "/alerts/active",
        }
        params_by_endpoint: dict[str, dict[str, Any]] = {
            "forecast": {},
            "forecast_hourly": {},
            "alerts": {"point": f"{location.lat},{location.lon}"},
        }
        if self.config.collect_forecast_discussion:
            endpoints["forecast_discussion_index"] = f"/products/types/AFD/locations/{grid.grid_id}"
            params_by_endpoint["forecast_discussion_index"] = {}

        for endpoint_name, path in endpoints.items():
            payload = self._get_json(
                path,
                params=params_by_endpoint[endpoint_name],
                endpoint_name=endpoint_name,
            )
            data[endpoint_name] = payload
            if store_raw:
                raw_responses.append(
                    RawProviderResponse(
                        provider=self.provider_name,
                        location_key=location.key,
                        endpoint=endpoint_name,
                        filename=f"{endpoint_name}.json",
                        payload=payload,
                    )
                )

        discussion_index = data.get("forecast_discussion_index")
        discussion_id = _latest_product_id(discussion_index)
        if discussion_id:
            discussion = self._get_json(
                f"/products/{discussion_id}",
                params={},
                endpoint_name="forecast_discussion",
            )
            data["forecast_discussion"] = discussion
            if store_raw:
                raw_responses.append(
                    RawProviderResponse(
                        provider=self.provider_name,
                        location_key=location.key,
                        endpoint="forecast_discussion",
                        filename="forecast_discussion.json",
                        payload=discussion,
                    )
                )

        return ProviderLocationData(
            provider=self.provider_name,
            location_key=location.key,
            collected_at=collected_at,
            data=data,
            raw_responses=raw_responses,
        )

    def _get_json(self, path: str, *, params: dict[str, Any], endpoint_name: str) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}{path}"
        headers = {
            "Accept": "application/geo+json, application/json",
            "User-Agent": self.config.user_agent,
        }
        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise WeatherProviderError(f"NWS {endpoint_name} request failed: {exc}") from exc
        if response.status_code >= 400:
            raise WeatherProviderError(
                f"NWS {endpoint_name} request failed: "
                f"status={response.status_code} body={response.text[:500]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise WeatherProviderError(f"NWS {endpoint_name} returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise WeatherProviderError(f"NWS {endpoint_name} returned non-object JSON.")
        return payload


def _latest_product_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    products = payload.get("@graph")
    if not isinstance(products, list) or not products:
        return None
    first = products[0]
    if not isinstance(first, dict):
        return None
    product_id = first.get("id")
    return str(product_id).rsplit("/", 1)[-1] if product_id else None
