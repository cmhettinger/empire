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

`upsert_provider_source_snapshot()` performs that caller-transaction-owned
step. It verifies the `AcquiredObject` against the current Core raw-object row,
upserts the existing Stonks source identity by provider, source code, and Core
checksum, and idempotently links every concrete stored object carrying that
content. It reuses `stonks.provider_source_snapshot` and
`stonks.provider_source_snapshot_object`; it does not create package-specific
lineage tables or commit independently.

Core metadata purge is lineage-safe: deleting an expired raw
`core.stored_object` cascades only its
`provider_source_snapshot_object` membership and clears the snapshot's nullable
first-seen object reference. The durable source snapshot, provider listing, and
OHLCV bars remain independent and queryable.

## Core run lifecycle

`run_provider_import()` starts the approved provider job through Core, passes
the active `RunContext` to package-owned work, and completes or fails the run.
Successful Core summaries contain only provider and import counts; acquired
object details and issue text remain outside the run record. Failures store a
fixed secret-safe message and compact failure summary before re-raising the
original exception to the caller.

The wrapper accepts injected work and `RunService` collaborators for reusable
CLI, Airflow, and test use. It owns run lifecycle only.

## Acquisition-to-import boundary

`execute_import_boundary()` composes injected acquisition and parsing work with
the shared persistence helpers. Acquisition finishes first, and Core raw-object
writes remain independently committed. Parsing then completes in memory before
the boundary opens one caller connection transaction for every source-snapshot,
provider-listing, and daily-bar write. That transaction commits once on success
and rolls back in full on any persistence or commit error.

Failures raise `OHLCVWorkflowError` with only one allowlisted stage:
`acquisition`, `parsing`, or `persistence`. `run_provider_import()` records that
stage in its otherwise detail-free failure summary and re-raises the exception;
provider exception text is retained only as the Python cause and is never sent
to Core. The boundary does not delete already stored raw inputs or compensate
successful database commits. Content-identity and current-state upserts make an
identical retry safe after parsing, persistence, or later Core completion
failure.

The boundary accepts injected acquisition and parsing callables. Provider
acquisition returns stored `AcquiredObject` references; parsing returns a
`ParsedProviderOutput` containing only shared listing/bar batches and the
`ProviderSourceMetadata` source-code/parser-version pairs needed for snapshot
registration. Source metadata must exactly cover the acquired source codes,
and parsed listings must match the active provider. Provider adapters may use
functions or bound methods and do not share a downloader base class, registry,
remote request model, or arbitrary metadata contract.

Concrete source identifiers, provider implementations, and provider runners
remain later tasks.

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

Shared models, provider-native persistence/query helpers, Core raw-object
storage, source-snapshot registration, run lifecycle, and the transactional
import boundary are implemented. Provider contracts, provider import CLIs, and
Airflow entrypoints are added in later tasks.
