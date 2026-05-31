"""Weather collection data models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class RawProviderResponse:
    """A raw provider response captured during collection."""

    provider: str
    location_key: str
    endpoint: str
    filename: str
    payload: JsonDict


@dataclass(frozen=True)
class WeatherCollectionResult:
    """Normalized weather payload plus optional raw responses."""

    payload: JsonDict
    raw_responses: list[RawProviderResponse] = field(default_factory=list)

    @property
    def location_count(self) -> int:
        locations = self.payload.get("locations", {})
        return len(locations) if isinstance(locations, dict) else 0

    @property
    def schema_version(self) -> int:
        return int(self.payload.get("schema_version", 1))

    def to_json(self) -> str:
        return json.dumps(self.payload, indent=2, sort_keys=True)


@dataclass(frozen=True)
class ProviderLocationData:
    """Provider-specific data for one location."""

    provider: str
    location_key: str
    collected_at: datetime
    data: JsonDict
    raw_responses: list[RawProviderResponse] = field(default_factory=list)
