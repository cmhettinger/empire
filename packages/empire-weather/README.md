# empire-weather

Reusable weather data collection package for Empire.

The initial implementation collects structured weather data from OpenWeather and
the National Weather Service, normalizes it into one run-level JSON payload, and
stores payloads and raw provider responses in the Empire object store.

OpenWeather collection defaults to One Call API 4.0. The provider fetches the
4.0 current, 1-minute timeline, 15-minute timeline, 1-hour timeline, 1-day
timeline, and alert-detail endpoints, then normalizes those responses into the
stable Empire weather payload. Air quality still comes from the OpenWeather 2.5
air pollution endpoint when that endpoint is enabled for the configured API key.

Configuration is environment-driven and package configuration is stored as a
well-known object in the `config` storage root under:

```text
weather/config.yml
```

Run artifacts are stored under:

```text
${EMPIRE_STORAGE_KEY_WEATHER}/runs/YYYY/MM/DD/<run_id>/
```

When `weather.imagery.enabled` is true, enabled imagery products from the config
are downloaded during object-store-backed runs and stored under:

```text
${EMPIRE_STORAGE_KEY_WEATHER}/runs/YYYY/MM/DD/<run_id>/images/
```

## Current Collection Coverage

The consolidated `weather.json` payload is one Empire run-level weather snapshot
for all configured locations. The initial config covers:

- Ashburn, Virginia
- Savannah, Georgia

For each location, the normalized payload currently includes:

- Current weather conditions: temperature, feels-like temperature, humidity, dew
  point, wind speed and direction, pressure, visibility, cloud cover, UV index,
  and weather description.
- Minute-by-minute short-term forecast data for the next hour.
- 15-minute forecast slices for near-term conditions.
- Hourly forecast data from OpenWeather and NWS.
- Daily forecast data, including high/low style temperature values,
  precipitation probability, rain and snow values when available, wind, UV
  index, sunrise, sunset, moonrise, moonset, and moon phase.
- Air quality data from OpenWeather, including AQI and pollutant components,
  when the configured API key has access to the Air Pollution API.
- NWS weather alerts, watches, and warnings when active.
- OpenWeather alert details when OpenWeather returns alert IDs.
- NWS forecast discussion text from the relevant forecast office.
- Configured weather imagery, stored as run objects under `images/` and
  referenced from the top-level `images` array in `weather.json`.
- Source provenance for major sections so downstream reporting can show whether
  data came from OpenWeather or NWS.
- Raw provider responses stored as object-store artifacts for debugging and
  auditability.

The normalized payload is organized by actual calendar date rather than labels
such as `today` or `tomorrow`.

## Not Collected Yet

The original weather wishlist also included several data and asset types that
are not part of the first implementation yet:

- Radar loops and dynamic map products beyond configured static image URLs.
- Air quality graphics beyond configured static image URLs.
- Air quality forecast/history beyond the current Air Pollution API snapshot.
- Pollen graphics.
- Other weather-related screenshots or image assets.
- Pollen and allergy data.
- Dedicated historical backfill beyond what the OpenWeather 4.0 timeline
  endpoints return during a normal run.
- Report-ready visual summaries; those belong in a later reporting package.

## Getting Started

Install the package environment once:

```bash
cd packages/empire-weather
poetry install
cd ../..
```

Publish the default weather config to the Empire object store:

```bash
bin/weather-put-config
```

Run this again after changing `object-store/config/weather/config.yml`; the collector
loads weather config from the object store by default.

That command reads:

```text
object-store/config/weather/config.yml
```

and stores it as:

```text
config:weather/config.yml
```

Run collection from the stored config:

```bash
bin/weather-collect
```

For a local debug payload without writing a run to the object store:

```bash
bin/weather-collect --config-file object-store/config/weather/config.yml --output-file /tmp/weather.json
```
