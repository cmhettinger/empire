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

EODData acquisition uses this runtime credential:

```text
EMPIRE_STONKS_OHLCV_EODDATA_API_KEY
```

Stooq and Yahoo do not require credentials in the current package contract.

Credentials are excluded from config and credential representations. Use
`OHLCVConfig.to_safe_dict()` when placing configuration details in Core run
parameters, object metadata, reports, logs, or serialized results. Pass the
credential object itself only to provider authentication code.

## Raw object storage

`store_raw_bytes()` and `store_raw_file()` persist acquired provider payloads
through Empire Core under the active `stonks` `RunContext`. They build the
provider/effective-date/run/source key and stable raw filename, apply the
configured raw retention window, attach only allowlisted provider metadata, and
return an `AcquiredObject` containing Core's computed size and SHA-256.

The file helper moves its staged source by default, matching the existing
`empire-stonks-securities` acquisition convention; callers can request a copy
when they still own the staged file. Source-snapshot registration is a separate
persistence step and is not performed by these storage helpers.

## CLI

Local commands use `bin/env-load` to load `deploy/env/local.env` before calling
package-owned command modules. The initial configuration check prints only the
secret-safe configuration summary:

```bash
bin/stonks-ohlcv-config
bin/stonks-ohlcv-config --env-file deploy/env/local.example.env
```

The same command is exposed as the package script `stonks-ohlcv-config` for
installed runtimes; environment loading remains the caller's responsibility.

## Development

Install the package environment and run its tests from this directory:

```bash
poetry install
poetry run pytest
```

## Status

Shared models, provider-native persistence/query helpers, and Core raw-object
storage are implemented. Provider contracts, source-snapshot registration,
provider import CLIs, and Airflow entrypoints are added in later tasks.
