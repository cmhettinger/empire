# empire-stonks-ohlcv

Reusable provider-native daily OHLCV ingestion utilities for Empire stonks.

This package will own source acquisition and parsing, provider-native listing
series and daily-bar persistence, Empire Core run and raw-object integration,
and provider-scoped validation and reporting. Airflow and other runtimes should
call package-owned functions rather than embedding ingestion logic directly.

The package stores values as supplied by each provider. It does not normalize
values across providers, map provider series to canonical securities or
listings, or construct an authoritative OHLCV history.

## Development

Install the package environment and run its tests from this directory:

```bash
poetry install
poetry run pytest
```

## Status

This is the initial package scaffold. Provider contracts, configuration,
database persistence, Core integration, CLIs, and Airflow entrypoints are added
in later implementation tasks.
