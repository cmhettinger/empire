"""Exceptions for empire-weather."""

from __future__ import annotations


class WeatherError(Exception):
    """Base exception for weather collection failures."""


class WeatherConfigError(WeatherError):
    """Raised when weather configuration is missing or invalid."""


class WeatherProviderError(WeatherError):
    """Raised when a weather provider request or response fails."""
