"""AccuWeather personal health/activity page collector."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import requests

from empire_weather.config import AccuWeatherConfig, WeatherLocationConfig
from empire_weather.exceptions import WeatherProviderError
from empire_weather.models import ProviderLocationData, RawProviderResponse


HEALTH_ACTIVITY_GROUPS = {
    "allergies": (
        "Tree Pollen",
        "Ragweed Pollen",
        "Mold",
        "Grass Pollen",
        "Dust & Dander",
    ),
    "health": (
        "Arthritis",
        "Sinus Pressure",
        "Common Cold",
        "Flu",
        "Migraine",
        "Asthma",
    ),
    "outdoor_activities": (
        "Fishing",
        "Running",
        "Golf",
        "Biking & Cycling",
        "Beach & Pool",
        "Stargazing",
        "Hiking",
    ),
    "travel_and_commute": (
        "Air Travel",
        "Driving",
    ),
    "home_and_garden": (
        "Lawn Mowing",
        "Composting",
        "Outdoor Entertaining",
    ),
    "pests": (
        "Mosquitos",
        "Indoor Pests",
        "Outdoor Pests",
    ),
}

INDEX_LEVELS = (
    "Very High",
    "Very Low",
    "Excellent",
    "Moderate",
    "Extreme",
    "Ideal",
    "Great",
    "Poor",
    "Fair",
    "Good",
    "High",
    "Low",
)


class AccuWeatherHealthActivitiesProvider:
    """Collect personal-use health/activity categories from AccuWeather pages."""

    provider_name = "accuweather"

    def __init__(self, config: AccuWeatherConfig, *, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()

    def collect_location(
        self,
        location: WeatherLocationConfig,
        *,
        collected_at,
        store_raw: bool,
    ) -> ProviderLocationData:
        raw_responses: list[RawProviderResponse] = []
        if not location.accuweather_health_activities_url:
            return ProviderLocationData(
                provider=self.provider_name,
                location_key=location.key,
                collected_at=collected_at,
                data={},
                raw_responses=[],
            )

        url = urljoin(self.config.base_url, location.accuweather_health_activities_url)
        html = self._get_html(url, endpoint_name="health_activities")
        items = parse_health_activity_indexes(html)
        data: dict[str, Any] = {
            "health_activities": {
                "source": "accuweather",
                "source_url": url,
                "fetched_at": collected_at.isoformat(),
                "personal_use_note": (
                    "Collected from the public AccuWeather Health & Activities page "
                    "for a personal Empire daily weather digest."
                ),
                "groups": items,
            }
        }
        if store_raw:
            raw_responses.append(
                RawProviderResponse(
                    provider=self.provider_name,
                    location_key=location.key,
                    endpoint="health_activities",
                    filename="health_activities.html",
                    payload=html,
                    content_type="text/html",
                )
            )
        return ProviderLocationData(
            provider=self.provider_name,
            location_key=location.key,
            collected_at=collected_at,
            data=data,
            raw_responses=raw_responses,
        )

    def _get_html(self, url: str, *, endpoint_name: str) -> str:
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": self.config.user_agent,
        }
        try:
            response = self.session.get(url, headers=headers, timeout=self.config.timeout_seconds)
        except requests.RequestException as exc:
            raise WeatherProviderError(f"AccuWeather {endpoint_name} request failed: {exc}") from exc
        if response.status_code >= 400:
            raise WeatherProviderError(
                f"AccuWeather {endpoint_name} request failed: "
                f"status={response.status_code} body={response.text[:500]}"
            )
        return response.text


def parse_health_activity_indexes(html: str) -> dict[str, list[dict[str, str]]]:
    """Extract known health/activity index labels from visible page text."""

    parser = _TextParser()
    parser.feed(html)
    text = " ".join(parser.parts)
    parsed: dict[str, list[dict[str, str]]] = {}
    for group, labels in HEALTH_ACTIVITY_GROUPS.items():
        group_items = []
        for label in labels:
            level = _find_level(text, label)
            if level:
                group_items.append(
                    {
                        "name": label,
                        "key": _key(label),
                        "level": level,
                    }
                )
        parsed[group] = group_items
    return parsed


def _find_level(text: str, label: str) -> str | None:
    start = 0
    while True:
        start = text.find(label, start)
        if start < 0:
            return None
        tail = text[start + len(label) : start + len(label) + 40].strip()
        for level in INDEX_LEVELS:
            if tail.startswith(level):
                return level
        start += len(label)
    return None


def _key(label: str) -> str:
    normalized = []
    for char in label.lower():
        normalized.append(char if char.isalnum() else "_")
    return "_".join(part for part in "".join(normalized).split("_") if part)


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self.parts.append(cleaned)
