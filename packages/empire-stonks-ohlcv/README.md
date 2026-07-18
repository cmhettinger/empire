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

EODData nightly acquisition uses:

```text
EMPIRE_STONKS_OHLCV_EODDATA_API_KEY=<required secret>
EMPIRE_STONKS_OHLCV_EODDATA_BASE_URL=https://api.eoddata.com
EMPIRE_STONKS_OHLCV_EODDATA_EXCHANGES=NYSE,NASDAQ,AMEX
EMPIRE_STONKS_OHLCV_EODDATA_REQUEST_DELAY_SECONDS=2
```

The initial source contract makes Symbol List requests for all three exchanges
before their effective-date Quote List requests. It stores six exchange-scoped
JSON objects and keeps EODData name/type/currency data best-effort on provider
listings while leaving `instrument_type_code` as `UNKNOWN`. See
[`docs/stonks/ohlcv-eoddata-source-contract.md`](../../docs/stonks/ohlcv-eoddata-source-contract.md)
for request, duplicate, reconciliation, delivery, and provider-native value
semantics.

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

The EODData endpoints and formats are selected in its source contract. Their
acquisition, parsing, reporting, and runner implementations remain later Phase
6 tasks. Stooq and Yahoo endpoints remain later provider-contract tasks.

Production source metadata is exposed as immutable constants:

| Provider workflow | Source code | Parser version |
|-------------------|-------------|----------------|
| EODData symbol discovery | `eoddata_symbol_list` | `1.0.0` |
| EODData nightly daily | `eoddata_daily` | `1.0.0` |
| Stooq nightly daily | `stooq_daily` | `1.0.0` |
| Stooq historical files | `stooq_history` | `1.0.0` |
| Yahoo controlled-symbol daily | `yahoo_daily` | `1.0.0` |

Source codes identify logical feeds, not endpoints, dates, symbols, or file
partitions. Parser versions use source-specific `MAJOR.MINOR.PATCH` values and
change when parsing or interpretation can change shared output. Stooq daily and
historical records discover their own series; Yahoo has no initial broad symbol
discovery or historical-file source. EODData's concrete endpoints are selected
in its source contract; Stooq and Yahoo endpoints remain owned by their later
provider source-contract tasks.

## Provider fixtures

Parser fixtures follow [the package fixture policy](tests/fixtures/README.md).
Each small raw payload is paired with a manifest that records its documented
format reference, production source/parser identity, provenance, sanitization,
size, checksum, and intended cases. Policy tests reject unmanifested,
oversized, drifted, unsafe, or unknown-source payloads.

Provider payloads are added only after repository evidence or a source-contract
task documents the real format. Tests never acquire live fixture data.

Provider parser tests reuse `tests/parser_contract.py`. They adapt their parser
to a bytes-in callable and provide exact valid and invalid cases, declaring
whether a bar source permits absent volume or is listing-only. The assertions
verify provider and native identity, optional/required volume behavior,
`date`/`Decimal` types, deterministic ordered output, and deterministic
`OHLCVParseError` rejection. This test seam does not impose one production
parser signature.

## Provider runner seam

`run_provider_pipeline()` accepts an existing `RunService`, caller-owned
database connection, and injected A5.1 acquisition/parser callables. It composes
the Core lifecycle with `execute_import_boundary()` and returns the same compact
`OHLCVRunResult`. Invalid collaborators are rejected before a Core run starts;
workflow failures retain the secret-safe acquisition/parsing/persistence stage.

The package seam performs no network access by itself and does not load an
environment file, create a provider registry, or depend on Airflow. Future
provider runners bind their concrete collaborators; CLI and Airflow callers
only establish runtime scope and call the package.

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

Run the EODData daily workflow with an explicit provider date:

```bash
bin/stonks-ohlcv-eoddata-daily --effective-date 2026-07-15
bin/stonks-ohlcv-eoddata-daily \
  --effective-date 2026-07-15 \
  --env-file deploy/env/local.example.env
```

The wrapper sources `bin/env-load`, defaults to `deploy/env/local.env`, and
suppresses environment-loader status output so successful stdout is exactly one
compact JSON object. The installed `stonks-ohlcv-eoddata-daily` package command
expects its runtime environment to be loaded already. Invalid dates are rejected
before opening a database connection; runtime failures print only a fixed safe
message and return nonzero.

## EODData acquisition

`acquire_eoddata_objects()` performs the package-owned EODData acquisition
stage. It requests NYSE, NASDAQ, and AMEX Symbol List payloads first, followed
by the three effective-date Quote List payloads, and stores every validated
JSON array immediately through Core. The returned tuple contains six
`AcquiredObject` references in that deterministic order.

The function accepts an injected `EODDataHTTPTransport` and sleep callable for
tests. Its default transport uses the Python standard library, keeps the API
key separate from the base URL until the request is sent, applies the common
timeout, spaces consecutive requests by the configured EODData delay, and
retries transport failures, HTTP 429, and HTTP 5xx responses up to the
configured bound. Safe numeric `Retry-After` values are honored with a
60-second cap; otherwise bounded exponential backoff starts at two seconds.

HTTP failures, malformed/non-array JSON, non-JSON media types, and empty Symbol
List payloads stop acquisition with a source/exchange-specific but secret-safe
error. Empty Quote List arrays remain valid. Successful objects from earlier
partitions remain durable when a later request fails, while response bodies,
query-bearing URLs, and transport exception details are excluded from surfaced
errors and Core metadata.

## EODData Symbol List parsing

`parse_eoddata_symbol_list()` parses one trusted NYSE, NASDAQ, or AMEX Symbol
List payload. It preserves the exact provider code as the ticker, always emits
the shared `UNKNOWN` instrument type, retains usable `name`, `type`, and
`currency` values, and ignores all quote-like fields in this discovery feed.

Compatible duplicate codes collapse without choosing an input row. Conflicting
descriptive values reject the whole exchange/code identity, and the provider-
specific result returns deterministic duplicate counts plus a bounded safe
issue sample. `to_parsed_provider_output()` adapts accepted listings to the
shared listing-batch boundary with no bars; Quote List reconciliation owns bars
in the next stage.

## EODData Quote List parsing

`parse_eoddata_quote_list()` requires one trusted exchange partition, an
explicit effective date, and that exchange's accepted Symbol List result. It
hard-fails exchange, daily-interval, and date scope mismatches, parses JSON
numbers directly to `Decimal`, and reconciles quotes only to exact accepted
same-exchange ticker identities.

Compatible quote duplicates collapse to one bar. Conflicting duplicates,
invalid OHLCV groups, and quotes without an accepted listing are rejected with
deterministic counts and bounded safe issue samples. The reconciled shared
output retains every accepted Symbol List listing and its metadata, including
listings without a quote, and attaches at most one daily bar to each batch.

## Validation and report contract

The shared validation boundary is documented in
[`docs/stonks/ohlcv-validation-report-contract.md`](../../docs/stonks/ohlcv-validation-report-contract.md).
`ProviderValidationResult` carries accepted shared batches alongside one
`FeedOutcomeCounts` per source and market, typed `RowRejectionSummary` buckets,
and separate bounded hard-failure and warning summaries.
`SourceMarketWriteCounts` preserves listing and bar write
outcomes at their distinct source/market grains for later import reports.

Issue totals remain complete while safe samples are capped at 100. The report
contract also defines active/inactive coverage, calendar and weekday freshness,
stale candidates, and weekday-shaped gap warnings as non-calendar-authoritative
operational heuristics.

## EODData atomic import

`import_eoddata_daily()` accepts the six acquired Core object references and
one `ProviderValidationResult` for each of NYSE, NASDAQ, and AMEX. It validates
the complete run shape before opening a transaction, then registers all six
source snapshots, upserts every accepted Symbol List listing, resolves active
listing IDs, and writes accepted Quote List bars in one commit boundary.

Work is ordered by production source and configured market order. Inactive
listings are still resolved and may receive metadata updates, but their bars are
excluded from the daily-bar writer and reported through `skipped_inactive`.
`EODDataImportResult` retains source/market feed and write counts, exact
market/source/reason rejection buckets, aggregate listing/bar persistence
counts, bounded validation issues, and snapshot lineage without returning full
bar payloads.

## Provider health queries

The public health helpers are provider-parameterized and return deterministic
inputs for the stored report builder:

- `select_provider_market_health()` separates active and inactive listing and
  bar coverage by market, including active first/last stored dates.
- `select_provider_series_health()` returns ordered coverage and freshness
  inputs for every active and inactive provider-native series.
- `select_provider_weekday_gaps()` counts active-series weekday-shaped gaps and
  returns at most 100 deterministic samples. These are operational candidates,
  not exchange-calendar-authoritative missing sessions.

The queries are read-only and do not calculate report presentation or accept an
EODData-specific exchange branch. PostgreSQL integration coverage exercises the
same provider-scoped API for EODData across NYSE, NASDAQ, and AMEX using 4,500
listings and 139,200 daily bars. Existing provider-listing and daily-bar primary
and identity indexes provide the required access paths, so E6.7 adds no schema
index.

## EODData stored report

`build_eoddata_report()` combines one `EODDataImportResult` with provider-
scoped database health queries. Its schema-version-2 JSON keeps acquisition,
feed, duplicate, cross-feed reconciliation, listing-write, and bar-write
outcomes at their source/market grains. It adds active coverage and freshness,
bounded stale/no-data and weekday-gap candidates, a separate inactive-series
summary, bounded warnings, market-specific hard failures, market/source/reason
row rejections, and the required provider-native value semantics. Safe row
rejections produce `WARN`; only partition/run-integrity failures produce
`FAIL`.

`store_eoddata_report()` writes deterministic JSON as a durable Core run object
under `<storage_key>/eoddata/runs/YYYY/MM/DD/<run_id>/reports/report.json`.
The object has no expiration and its metadata contains only schema version,
provider, effective/generated dates, and outcome. Runtime credentials are not
accepted by the report builder and are never serialized from `OHLCVConfig`.

## EODData daily runner

`run_eoddata_daily()` owns the provider's nightly package sequence under one
Core run: acquire the three Symbol List objects followed by three Quote List
objects, read and parse/reconcile them in NYSE/NASDAQ/AMEX order, execute the
atomic import, build and store the detailed report, and complete the Core run.
Callers provide the connection, Core services, explicit effective date, and
runtime identity; the package neither loads environment files nor depends on
Airflow.

The returned `EODDataDailyRunResult` contains only the run/report IDs, status,
effective date, aggregate write/issue and rejected-row counts, inactive skip
count, and report outcome. Core params and summaries use
`OHLCVConfig.to_safe_dict()` and never
contain credentials, source payloads, issue text, or full report contents.
Acquisition and parsing failures also record the safe market and source code
when the failed partition is known; all runtime failures record a safe stage
while the original exception is re-raised. Previously stored raw
objects and successfully committed import data are not deleted on later-stage
failure, making a new Core run for the same effective date safe to retry.

## EODData manual DAG

Airflow DAG `stonks_ohlcv_eoddata_daily_scrape` is manual-only
(`schedule=None`). It disables catchup and permits one active run so EODData
acquisitions cannot overlap. The task reads runtime settings from the
Compose-provided process environment and delegates the complete workflow to
`run_eoddata_daily()`.

For a manual run or rerun, pass an explicit provider date with DAG run
configuration such as `{"effective_date": "2026-07-15"}`. If omitted, the DAG
uses the New York date at `data_interval_end`. The task returns only the
runner's compact secret-safe summary; detailed diagnostics remain in the stored
report.

## Development

Install the package environment and run its tests from this directory:

```bash
poetry install
poetry run pytest
```

## Status

Shared models, provider-native persistence/query helpers, Core raw-object
storage, source-snapshot registration, run lifecycle, the transactional import
boundary, EODData six-request acquisition, and EODData Symbol List parsing are
implemented along with EODData Quote List parsing/reconciliation, atomic import,
shared provider health queries, the stored EODData report, and the scheduled
EODData Airflow entrypoint. Later provider parsers are added in later tasks.
