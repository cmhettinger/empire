# TODO / Roadmap

This document tracks upcoming work for the *stonks* project.

It is intentionally split into:

* **Short-term tactical items** — small, focused tasks currently in flight
* **Long-term domains** — larger areas of future work and exploration

## Empire Weather Remaining Work

The first `empire-weather` implementation now collects structured weather data
from OpenWeather One Call API 4.0, OpenWeather Air Pollution API, and NWS. The
remaining weather work is mostly asset collection, provider hardening, and
coverage expansion.

| Priority | Task | Possible Sources | Notes |
| :--- | :--- | :--- | :--- |
| High | Add weather asset manifest support | Empire object store | Link stored images/assets back into `weather.json` with provider, location, date, asset type, object path/id, content type, and provenance. |
| High | Collect NOAA/NWS radar imagery | NWS radar services, NOAA nowCOAST | Prefer NOAA/NWS first because products are generally public domain and intended for reuse. Start with location-centered radar image assets. |
| High | Collect NOAA satellite imagery | NOAA nowCOAST, GOES imagery services | Store current regional satellite images per configured location. |
| Medium | Collect NOAA/nowCOAST precipitation maps | NOAA nowCOAST, NWS/NOAA map services | Use this before custom OpenWeather map composition if it provides useful finished products. |
| Medium | Collect NOAA/nowCOAST temperature or weather-analysis maps | NOAA nowCOAST, NWS/NOAA map services | Determine whether NOAA sources provide useful finished local/regional map products. |
| Medium | Add OpenWeather Maps 1.0 tile collector | OpenWeather Weather Maps 1.0 | Key access is confirmed. Raw tiles are weather overlays only, so this needs base-map composition before it is report-friendly. |
| Medium | Composite OpenWeather maps over a base map | OpenWeather Maps 1.0, OpenStreetMap, Census TIGER/Line | Fetch matching weather and base-map tiles, stitch them, add labels/markers, and store finished PNGs. |
| Medium | Expand air quality collection | OpenWeather Air Pollution API | Current AQ snapshot works. Add forecast/history if available and normalize by date. |
| Medium | Add pollen/allergy provider | Ambee, Tomorrow.io, Open-Meteo if useful for U.S. locations | Not available from current NWS/OpenWeather coverage in a useful way. Needs provider decision. |
| Low | Add historical weather backfill mode | OpenWeather One Call API 4.0 timelines/history | Separate from daily collection; should write date-oriented payloads using explicit backfill parameters. |
| Low | Add provider capability probes | OpenWeather, NOAA/NWS/nowCOAST | Small CLI/debug probes for map, air quality, radar, and satellite access before enabling permanent collection. |
| Low | Generate report-ready weather graphics | Future reporting package | Keep `empire-weather` as acquisition layer; reporting package can render charts, briefings, PDFs, and dashboards later. |

## Short-Term Tactical Tasks

| Priority | Task |
| :--- | :--- |
| Medium | finish empire-weather in airflow |

## Long-Term Domain Tasks

| Domain | Task | Notes
| :--- | :--- | :--- |
| scrape | weather | openweather and nws |
| scrape | stonks | integrate monorepo |
| scrape | hurricane data | noaa hurrican center |
| scrape | headlines | google news, yahoo, others |
| scrape | comics | find online classic strip images |
| scrape | sports | schedule and box scores |
| server | jellyfin | procure hp mini |
| report | 401k | stonks data combined with actual positions |
| scrape | gas prices | gas buddy |
| ai gen | comics | generate comic book panels |
| ai gen | writing | books, poetry, haiku based off of yml |
| ai gen | podcast | based on ai collections |
