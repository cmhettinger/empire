# TODO / Roadmap

This document tracks upcoming work for the *empire* project.

It is intentionally split into:

* **Short-term tactical items** — small, focused tasks currently in flight
* **Long-term domains** — larger areas of future work and exploration

## Short-Term Tactical Tasks

| Priority | Task |
| :--- | :--- |
| Medium | finish empire-weather data collection |
| Medium | finish empire-youtube jellyfin docker and prod yml |
| Low | move dags/utils/util_daily_*.py to dags/utils/objectstore/util_daily_*.py |
| Low | new dag util_daily_stats (generate human readable and json - save in db or objectstore) |
| Low | does airflow keep task runs forever?  what if i only want to keep a few run |
| Low | empire branding (logo and colors)

## Long-Term Domain Tasks

| Domain | Task | Notes
| :--- | :--- | :--- |
| scrape | stonks | integrate into monorepo (sec edgar, fred) |
| scrape | hurricane data | noaa hurrican center |
| scrape | headlines | google news, yahoo, others |
| scrape | astronomy | planet rise/fall, stars, iss, etc. |
| scrape | comics | find online classic strip images |
| scrape | sports | schedule and box scores |
| pacakge | empire-report | pdf report package (or html) |
| package | calendar | calendar api to be used by other packages |
| report | 401k | stonks data combined with actual positions |
| report | stonks | generate multiple stonks reports |
| report | weather | convert weather.json to report |
| report | astronomy | convert astronomy.json to report |
| scrape | gas prices | gas buddy |
| ai gen | weather audio | convert weather.json into a script and use text-to-speeech to render |
| ai gen | comics | generate comic book panels |
| ai gen | writing | books, screenplays, poetry, haiku based off of yml |
| ai gen | podcast | based on ai collections (gen 5 min video on daily weather and highlights) |
