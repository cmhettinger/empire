"""Weather collection orchestration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from empire_weather.config import WeatherCollectionConfig
from empire_weather.exceptions import WeatherProviderError
from empire_weather.models import ProviderLocationData, WeatherCollectionResult
from empire_weather.normalize import normalize_weather_payload
from empire_weather.providers import AccuWeatherHealthActivitiesProvider, NWSProvider, OpenWeatherProvider


logger = logging.getLogger(__name__)


class WeatherCollector:
    """Collect weather data from all configured providers and locations."""

    def __init__(
        self,
        *,
        config: WeatherCollectionConfig,
        openweather: OpenWeatherProvider | None = None,
        nws: NWSProvider | None = None,
        accuweather: AccuWeatherHealthActivitiesProvider | None = None,
    ):
        self.config = config
        self.openweather = openweather or OpenWeatherProvider(config.providers.openweather)
        self.nws = nws or NWSProvider(config.providers.nws)
        self.accuweather = accuweather or AccuWeatherHealthActivitiesProvider(config.providers.accuweather)

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
            if self.config.providers.accuweather.enabled:
                try:
                    accuweather_data = self.accuweather.collect_location(
                        location,
                        collected_at=generated_at,
                        store_raw=self.config.store_raw_responses,
                    )
                except WeatherProviderError as exc:
                    logger.warning(
                        "Skipping optional AccuWeather data for location %s: %s",
                        location.key,
                        exc,
                    )
                    continue
                provider_data.append(accuweather_data)
                raw_responses.extend(accuweather_data.raw_responses)

        payload = normalize_weather_payload(
            config=self.config,
            provider_data=provider_data,
            generated_at=generated_at,
            run_id=run_id,
        )
        return WeatherCollectionResult(payload=payload, raw_responses=raw_responses)
