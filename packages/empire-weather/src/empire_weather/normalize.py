"""Normalize provider weather payloads into the Empire weather schema."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from empire_weather.config import WeatherCollectionConfig, WeatherLocationConfig
from empire_weather.models import ProviderLocationData


SCHEMA_VERSION = 1


def normalize_weather_payload(
    *,
    config: WeatherCollectionConfig,
    provider_data: list[ProviderLocationData],
    generated_at: datetime,
    run_id: str | None,
) -> dict[str, Any]:
    """Build one date-oriented normalized payload for all locations."""

    by_location: dict[str, dict[str, ProviderLocationData]] = {}
    for item in provider_data:
        by_location.setdefault(item.location_key, {})[item.provider] = item

    locations: dict[str, Any] = {}
    for location in config.enabled_locations:
        location_data = by_location.get(location.key, {})
        openweather = location_data.get("openweather")
        nws = location_data.get("nws")
        accuweather = location_data.get("accuweather")
        locations[location.key] = _normalize_location(
            location=location,
            units=config.units,
            openweather=openweather.data if openweather else {},
            nws=nws.data if nws else {},
            accuweather=accuweather.data if accuweather else {},
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "source": "empire-weather",
        "run_id": run_id,
        "generated_at": _iso(generated_at),
        "config": {
            "name": config.name,
            "version": config.version,
            "units": config.units,
            "store_raw_responses": config.store_raw_responses,
        },
        "providers": {
            "openweather": {"role": "structured_weather"},
            "nws": {"role": "authoritative_us_alerts_and_forecasts"},
            "accuweather": {"role": "personal_use_health_activity_page_indexes"},
        },
        "locations": locations,
        "assets": [],
    }


def _normalize_location(
    *,
    location: WeatherLocationConfig,
    units: str,
    openweather: dict[str, Any],
    nws: dict[str, Any],
    accuweather: dict[str, Any],
) -> dict[str, Any]:
    onecall = _as_dict(openweather.get("onecall"))
    current = _as_dict(onecall.get("current"))
    air_quality = _as_dict(openweather.get("air_quality"))
    health_activities = _as_dict(accuweather.get("health_activities"))
    timezone = onecall.get("timezone")
    dates: dict[str, Any] = {}

    if current:
        current_date = _date_from_timestamp(current.get("dt"), timezone_offset=onecall.get("timezone_offset"))
        dates.setdefault(current_date, _empty_date())["current_conditions"] = {
            "source": "openweather",
            "observed_at": _dt_from_timestamp(current.get("dt")),
            "temperature": _measurement(current.get("temp"), _temperature_unit(units)),
            "feels_like": _measurement(current.get("feels_like"), _temperature_unit(units)),
            "humidity": _measurement(current.get("humidity"), "percent"),
            "dew_point": _measurement(current.get("dew_point"), _temperature_unit(units)),
            "wind_speed": _measurement(current.get("wind_speed"), _speed_unit(units)),
            "wind_gust": _measurement(current.get("wind_gust"), _speed_unit(units)),
            "wind_direction": _measurement(current.get("wind_deg"), "degrees"),
            "barometric_pressure": _measurement(current.get("pressure"), "hPa"),
            "visibility": _measurement(current.get("visibility"), "meters"),
            "cloud_cover": _measurement(current.get("clouds"), "percent"),
            "uv_index": _measurement(current.get("uvi"), "index"),
            "weather": _weather_items(current.get("weather")),
        }
        dates[current_date]["astronomy"] = {
            "source": "openweather",
            "sunrise": _dt_from_timestamp(current.get("sunrise")),
            "sunset": _dt_from_timestamp(current.get("sunset")),
        }

    for item in _as_list(onecall.get("hourly")):
        if not isinstance(item, dict):
            continue
        item_date = _date_from_timestamp(item.get("dt"), timezone_offset=onecall.get("timezone_offset"))
        dates.setdefault(item_date, _empty_date())["hourly_forecasts"].append(
            {
                "source": "openweather",
                "forecast_at": _dt_from_timestamp(item.get("dt")),
                "temperature": _measurement(item.get("temp"), _temperature_unit(units)),
                "feels_like": _measurement(item.get("feels_like"), _temperature_unit(units)),
                "humidity": _measurement(item.get("humidity"), "percent"),
                "dew_point": _measurement(item.get("dew_point"), _temperature_unit(units)),
                "wind_speed": _measurement(item.get("wind_speed"), _speed_unit(units)),
                "wind_gust": _measurement(item.get("wind_gust"), _speed_unit(units)),
                "wind_direction": _measurement(item.get("wind_deg"), "degrees"),
                "precipitation_probability": _measurement(item.get("pop"), "ratio"),
                "rainfall": _measurement(_nested(item, "rain", "1h"), _precip_unit(units)),
                "snowfall": _measurement(_nested(item, "snow", "1h"), _precip_unit(units)),
                "weather": _weather_items(item.get("weather")),
            }
        )

    for item in _as_list(onecall.get("minutely")):
        if not isinstance(item, dict):
            continue
        item_date = _date_from_timestamp(item.get("dt"), timezone_offset=onecall.get("timezone_offset"))
        dates.setdefault(item_date, _empty_date())["minutely_forecasts"].append(
            _short_interval_forecast(item, interval_minutes=1, units=units)
        )

    for item in _as_list(onecall.get("quarter_hourly")):
        if not isinstance(item, dict):
            continue
        item_date = _date_from_timestamp(item.get("dt"), timezone_offset=onecall.get("timezone_offset"))
        dates.setdefault(item_date, _empty_date())["quarter_hourly_forecasts"].append(
            _short_interval_forecast(item, interval_minutes=15, units=units)
        )

    for item in _as_list(onecall.get("daily")):
        if not isinstance(item, dict):
            continue
        item_date = _date_from_timestamp(item.get("dt"), timezone_offset=onecall.get("timezone_offset"))
        dates.setdefault(item_date, _empty_date())["daily_forecasts"].append(
            {
                "source": "openweather",
                "forecast_date": item_date,
                "summary": item.get("summary"),
                "temperature": {
                    "day": _measurement(_nested(item, "temp", "day"), _temperature_unit(units)),
                    "min": _measurement(_nested(item, "temp", "min"), _temperature_unit(units)),
                    "max": _measurement(_nested(item, "temp", "max"), _temperature_unit(units)),
                    "night": _measurement(_nested(item, "temp", "night"), _temperature_unit(units)),
                },
                "feels_like": {
                    "day": _measurement(_nested(item, "feels_like", "day"), _temperature_unit(units)),
                    "night": _measurement(_nested(item, "feels_like", "night"), _temperature_unit(units)),
                },
                "humidity": _measurement(item.get("humidity"), "percent"),
                "wind_speed": _measurement(item.get("wind_speed"), _speed_unit(units)),
                "wind_gust": _measurement(item.get("wind_gust"), _speed_unit(units)),
                "wind_direction": _measurement(item.get("wind_deg"), "degrees"),
                "precipitation_probability": _measurement(item.get("pop"), "ratio"),
                "rainfall": _measurement(item.get("rain"), _precip_unit(units)),
                "snowfall": _measurement(item.get("snow"), _precip_unit(units)),
                "uv_index": _measurement(item.get("uvi"), "index"),
                "weather": _weather_items(item.get("weather")),
                "astronomy": {
                    "sunrise": _dt_from_timestamp(item.get("sunrise")),
                    "sunset": _dt_from_timestamp(item.get("sunset")),
                    "moonrise": _dt_from_timestamp(item.get("moonrise")),
                    "moonset": _dt_from_timestamp(item.get("moonset")),
                    "moon_phase": _measurement(item.get("moon_phase"), "fraction"),
                },
            }
        )

    alerts = _normalize_nws_alerts(nws.get("alerts"))
    alerts.extend(_normalize_openweather_alerts(onecall.get("alert_details")))
    for alert in alerts:
        date_key = (alert.get("effective") or alert.get("sent") or "")[:10] or "undated"
        dates.setdefault(date_key, _empty_date())["alerts"].append(alert)

    for item in _normalize_nws_periods(nws.get("forecast")):
        dates.setdefault(item["forecast_date"], _empty_date())["daily_forecasts"].append(item)
    for item in _normalize_nws_periods(nws.get("forecast_hourly")):
        dates.setdefault(item["forecast_date"], _empty_date())["hourly_forecasts"].append(item)

    discussion = _normalize_forecast_discussion(nws.get("forecast_discussion"))
    if discussion:
        date_key = (discussion.get("issued_at") or "")[:10] or "undated"
        dates.setdefault(date_key, _empty_date())["forecast_discussions"].append(discussion)

    air_quality_items = _normalize_air_quality(air_quality)
    for item in air_quality_items:
        date_key = (item.get("observed_at") or "")[:10] or "undated"
        dates.setdefault(date_key, _empty_date())["air_quality"].append(item)

    if health_activities:
        fetched_date = (health_activities.get("fetched_at") or "")[:10] or "undated"
        dates.setdefault(fetched_date, _empty_date())["health_activities"] = _normalize_health_activities(
            health_activities
        )

    return {
        "key": location.key,
        "name": location.name,
        "county": location.county,
        "state": location.state,
        "latitude": location.lat,
        "longitude": location.lon,
        "timezone": timezone,
        "nws_grid": {
            "gridId": location.nws.grid_id,
            "gridX": location.nws.grid_x,
            "gridY": location.nws.grid_y,
        },
        "provenance": {
            "current_conditions": "openweather",
            "minutely_forecasts": "openweather",
            "quarter_hourly_forecasts": "openweather",
            "hourly_forecasts": ["openweather", "nws"],
            "daily_forecasts": ["openweather", "nws"],
            "astronomy": "openweather",
            "alerts": ["nws", "openweather"],
            "forecast_discussions": "nws",
            "air_quality": "openweather",
            "health_activities": "accuweather",
        },
        "dates": dict(sorted(dates.items())),
    }


def _empty_date() -> dict[str, Any]:
    return {
        "current_conditions": None,
        "minutely_forecasts": [],
        "quarter_hourly_forecasts": [],
        "hourly_forecasts": [],
        "daily_forecasts": [],
        "astronomy": None,
        "alerts": [],
        "forecast_discussions": [],
        "air_quality": [],
        "assets": [],
    }


def _normalize_nws_alerts(payload: Any) -> list[dict[str, Any]]:
    alerts = []
    for feature in _as_list(_as_dict(payload).get("features")):
        props = _as_dict(feature.get("properties")) if isinstance(feature, dict) else {}
        if not props:
            continue
        alerts.append(
            {
                "source": "nws",
                "id": props.get("id"),
                "event": props.get("event"),
                "headline": props.get("headline"),
                "severity": props.get("severity"),
                "certainty": props.get("certainty"),
                "urgency": props.get("urgency"),
                "status": props.get("status"),
                "message_type": props.get("messageType"),
                "sent": props.get("sent"),
                "effective": props.get("effective"),
                "expires": props.get("expires"),
                "ends": props.get("ends"),
                "area_description": props.get("areaDesc"),
                "description": props.get("description"),
                "instruction": props.get("instruction"),
            }
        )
    return alerts


def _normalize_openweather_alerts(payload: Any) -> list[dict[str, Any]]:
    alerts = []
    for item in _as_list(payload):
        if not isinstance(item, dict):
            continue
        alerts.append(
            {
                "source": "openweather",
                "id": item.get("id"),
                "event": item.get("event"),
                "sender_name": item.get("sender_name"),
                "effective": _dt_from_timestamp(item.get("start")),
                "expires": _dt_from_timestamp(item.get("end")),
                "description": item.get("description"),
            }
        )
    return alerts


def _normalize_nws_periods(payload: Any) -> list[dict[str, Any]]:
    periods = _as_list(_nested(_as_dict(payload), "properties", "periods"))
    normalized = []
    for period in periods:
        if not isinstance(period, dict):
            continue
        start_time = period.get("startTime")
        normalized.append(
            {
                "source": "nws",
                "forecast_date": str(start_time)[:10] if start_time else "undated",
                "name": period.get("name"),
                "start_time": start_time,
                "end_time": period.get("endTime"),
                "is_daytime": period.get("isDaytime"),
                "temperature": _measurement(period.get("temperature"), period.get("temperatureUnit")),
                "precipitation_probability": _measurement(
                    _nested(period, "probabilityOfPrecipitation", "value"),
                    "percent",
                ),
                "dew_point": _measurement(_nested(period, "dewpoint", "value"), _nested(period, "dewpoint", "unitCode")),
                "relative_humidity": _measurement(
                    _nested(period, "relativeHumidity", "value"),
                    "percent",
                ),
                "wind_speed": period.get("windSpeed"),
                "wind_direction": period.get("windDirection"),
                "short_forecast": period.get("shortForecast"),
                "detailed_forecast": period.get("detailedForecast"),
            }
        )
    return normalized


def _normalize_forecast_discussion(payload: Any) -> dict[str, Any] | None:
    payload_dict = _as_dict(payload)
    if payload_dict.get("productText"):
        return _forecast_discussion_from_props(payload_dict, product=payload_dict)

    products = _as_list(payload_dict.get("@graph"))
    if not products:
        products = _as_list(payload_dict.get("features"))
    if not products:
        return None
    product = _as_dict(products[0])
    props = _as_dict(product.get("properties")) or product
    return _forecast_discussion_from_props(props, product=product)


def _forecast_discussion_from_props(
    props: dict[str, Any],
    *,
    product: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": "nws",
        "id": props.get("id") or product.get("id"),
        "issued_at": props.get("issuanceTime") or props.get("issued") or props.get("updateTime"),
        "office": props.get("issuingOffice") or props.get("office"),
        "product_name": props.get("productName") or props.get("name"),
        "text": props.get("productText") or props.get("text"),
    }


def _normalize_air_quality(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for item in _as_list(payload.get("list")):
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "source": "openweather",
                "observed_at": _dt_from_timestamp(item.get("dt")),
                "aqi": _measurement(_nested(item, "main", "aqi"), "index"),
                "components": {
                    key: _measurement(value, "micrograms_per_cubic_meter")
                    for key, value in _as_dict(item.get("components")).items()
                },
            }
        )
    return items


def _normalize_health_activities(payload: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for group_name, items in _as_dict(payload.get("groups")).items():
        groups[group_name] = [
            {
                "name": _as_dict(item).get("name"),
                "key": _as_dict(item).get("key"),
                "level": _as_dict(item).get("level"),
            }
            for item in _as_list(items)
            if isinstance(item, dict)
        ]
    return {
        "source": "accuweather",
        "source_url": payload.get("source_url"),
        "fetched_at": payload.get("fetched_at"),
        "personal_use_note": payload.get("personal_use_note"),
        "groups": groups,
    }


def _short_interval_forecast(
    item: dict[str, Any],
    *,
    interval_minutes: int,
    units: str,
) -> dict[str, Any]:
    return {
        "source": "openweather",
        "interval_minutes": interval_minutes,
        "forecast_at": _dt_from_timestamp(item.get("dt")),
        "temperature": _measurement(item.get("temp"), _temperature_unit(units)),
        "feels_like": _measurement(item.get("feels_like"), _temperature_unit(units)),
        "humidity": _measurement(item.get("humidity"), "percent"),
        "dew_point": _measurement(item.get("dew_point"), _temperature_unit(units)),
        "wind_speed": _measurement(item.get("wind_speed"), _speed_unit(units)),
        "wind_gust": _measurement(item.get("wind_gust"), _speed_unit(units)),
        "wind_direction": _measurement(item.get("wind_deg"), "degrees"),
        "precipitation": _measurement(item.get("precipitation"), "millimeters_per_hour"),
        "precipitation_probability": _measurement(item.get("pop"), "ratio"),
        "rainfall": _measurement(_nested(item, "rain", "1h"), _precip_unit(units)),
        "snowfall": _measurement(_nested(item, "snow", "1h"), _precip_unit(units)),
        "weather": _weather_items(item.get("weather")),
    }


def _measurement(value: Any, unit: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"value": value, "unit": unit}


def _weather_items(value: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            "main": item.get("main"),
            "description": item.get("description"),
            "icon": item.get("icon"),
        }
        for item in _as_list(value)
        if isinstance(item, dict)
    ]


def _date_from_timestamp(value: Any, *, timezone_offset: Any = None) -> str:
    if value is None:
        return "undated"
    try:
        timestamp = int(value)
        offset = int(timezone_offset or 0)
    except (TypeError, ValueError):
        return "undated"
    return datetime.fromtimestamp(timestamp + offset, tz=UTC).date().isoformat()


def _dt_from_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError):
        return None


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _temperature_unit(units: str) -> str:
    return "fahrenheit" if units == "imperial" else "celsius" if units == "metric" else "kelvin"


def _speed_unit(units: str) -> str:
    return "miles_per_hour" if units == "imperial" else "meters_per_second"


def _precip_unit(units: str) -> str:
    return "inches" if units == "imperial" else "millimeters"
