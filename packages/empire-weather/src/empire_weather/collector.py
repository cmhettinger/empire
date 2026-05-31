"""Weather collection orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

from empire_weather.config import WeatherCollectionConfig
from empire_weather.models import ProviderLocationData, WeatherCollectionResult
from empire_weather.normalize import normalize_weather_payload
from empire_weather.providers import NWSProvider, OpenWeatherProvider


class WeatherCollector:
    """Collect weather data from all configured providers and locations."""

    def __init__(
        self,
        *,
        config: WeatherCollectionConfig,
        openweather: OpenWeatherProvider | None = None,
        nws: NWSProvider | None = None,
    ):
        self.config = config
        self.openweather = openweather or OpenWeatherProvider(config.providers.openweather)
        self.nws = nws or NWSProvider(config.providers.nws)

    def collect(
        self,
        *,
        generated_at: datetime | None = None,
        run_id: str | None = None,
    ) -> WeatherCollectionResult:
        generated_at = generated_at or datetime.now(UTC)
        provider_data: list[ProviderLocationData] = []
        raw_responses = []
        for location in self.config.enabled_locations:
            openweather_data = self.openweather.collect_location(
                location,
                collected_at=generated_at,
                store_raw=self.config.store_raw_responses,
            )
            nws_data = self.nws.collect_location(
                location,
                collected_at=generated_at,
                store_raw=self.config.store_raw_responses,
            )
            provider_data.extend([openweather_data, nws_data])
            raw_responses.extend(openweather_data.raw_responses)
            raw_responses.extend(nws_data.raw_responses)

        payload = normalize_weather_payload(
            config=self.config,
            provider_data=provider_data,
            generated_at=generated_at,
            run_id=run_id,
        )
        return WeatherCollectionResult(payload=payload, raw_responses=raw_responses)
