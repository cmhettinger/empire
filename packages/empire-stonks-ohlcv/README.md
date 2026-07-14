# empire-stonks-ohlcv

Reusable provider-native daily OHLCV ingestion utilities for Empire stonks.

This package will own source acquisition and parsing, provider-native listing
series and daily-bar persistence, Empire Core run and raw-object integration,
and provider-scoped validation and reporting. Airflow and other runtimes should
call package-owned functions rather than embedding ingestion logic directly.

The package stores values as supplied by each provider. It does not normalize
values across providers, map provider series to canonical securities or
listings, or construct an authoritative OHLCV history.

## Configuration

Package configuration is read only from the process environment. Runtime
wrappers, Docker Compose, and Airflow are responsible for loading environment
files; this package does not load `.env` files or assume a repository path.

Common settings and defaults are:

```text
EMPIRE_STORAGE_KEY_STONKS_OHLCV=stonks/ohlcv
EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS=7
EMPIRE_STONKS_OHLCV_HTTP_TIMEOUT_SECONDS=30
EMPIRE_STONKS_OHLCV_MAX_RETRIES=3
```

EODData acquisition requires both of these runtime credentials:

```text
EMPIRE_STONKS_OHLCV_EODDATA_USERNAME
EMPIRE_STONKS_OHLCV_EODDATA_PASSWORD
```

Stooq and Yahoo do not require credentials in the current package contract.

Credentials are excluded from config and credential representations. Use
`OHLCVConfig.to_safe_dict()` when placing configuration details in Core run
parameters, object metadata, reports, logs, or serialized results. Pass the
credential object itself only to provider authentication code.

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
