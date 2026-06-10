# TODO / empire-weather

This document tracks upcoming work for the *empire-weather* package.

## Empire Weather Remaining Work

The first `empire-weather` implementation now collects structured weather data
from OpenWeather One Call API 4.0, OpenWeather Air Pollution API, and NWS. The
remaining weather work is mostly asset collection, provider hardening, and
coverage expansion.

| Priority | Task | Possible Sources | Notes |
| :--- | :--- | :--- | :--- |
| Low | Generate report-ready weather graphics | Future reporting package | Keep `empire-weather` as acquisition layer; reporting package can render charts, briefings, PDFs, and dashboards later. |
