"""Weather imagery download client."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from empire_weather.config import WeatherImageryProductConfig
from empire_weather.exceptions import WeatherProviderError


@dataclass(frozen=True)
class WeatherImageDownload:
    """Downloaded bytes for one configured image product."""

    product: WeatherImageryProductConfig
    data: bytes
    content_type: str


class WeatherImageryProvider:
    """Download configured weather image assets."""

    def __init__(self, *, session: requests.Session | None = None, timeout_seconds: float = 30.0):
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def download(self, product: WeatherImageryProductConfig) -> WeatherImageDownload:
        try:
            response = self.session.get(product.url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise WeatherProviderError(f"Failed to download imagery product {product.name}: {exc}") from exc

        return WeatherImageDownload(
            product=product,
            data=response.content,
            content_type=product.content_type,
        )
