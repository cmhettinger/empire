# OHLCV Architecture Plan

## Status

This document defines the approved initial architecture for provider-native
daily OHLCV ingestion in Empire Stonks.

The active implementation target is `empire-stonks-ohlcv`. The future
`empire-stonks-ohlcv-bridge` package is explicitly deferred until:

- Provider-native OHLCV ingestion is stable.
- The security master and reconciliation contracts are further along.
- A concrete consumer requires provider-to-canonical listing mappings.

The implementation checklist is maintained in
`docs/todo/ohlcv-task-plan.md`.

## Initial Goal

Build a simple reusable package that:

- Downloads daily or historical source data from EODData, Stooq, and Yahoo.
- Stores raw provider objects briefly through Empire Core.
- Parses provider-native market/symbol series and daily bars.
- Stores current provider-native OHLCV values in PostgreSQL.
- Runs idempotently through CLIs and thin Airflow DAGs.
- Reports import health, freshness, coverage, stale series, and gap warnings.
- Preserves provider-native series identity for a future bridge.

The package does not need canonical issuer, security, listing, or exchange
resolution before importing data.

## Active Package Boundary

### `empire-stonks-ohlcv` owns

- Provider-specific OHLCV source acquisition and parsing.
- Shared provider-listing and daily-bar dataclasses.
- Provider-native listing-series persistence.
- Provider-native daily OHLCV persistence.
- Current-state idempotent upserts.
- Core run tracking and short-lived raw-object integration.
- Durable source-content identity through existing Stonks source snapshots.
- Provider-specific daily and historical-import runners.
- Provider-scoped validation and operational reports.
- Thin CLI entrypoints called by operators and Airflow.

### `empire-stonks-ohlcv` does not own

- Canonical issuer, security, listing, exchange, or symbol-history mutation.
- Provider-to-canonical listing mappings.
- Ticker-reuse detection or real-world identity reconstruction.
- Cross-provider price or adjustment normalization.
- Corporate-action normalization.
- A canonical or authoritative OHLCV series.
- Sector, industry, fundamentals, descriptive enrichment, or other non-OHLCV
  metadata exposed by a provider.
- Intraday or extended-hours data in the first implementation.
- Append-only provider bar revision history.

Airflow orchestrates package-owned functions. Provider acquisition, parsing,
persistence, validation, reporting, and sequencing do not belong in DAG files.

## Dependency Direction

The initial Python dependency shape is:

```text
empire-stonks-ohlcv
        |
        v
   empire-core
```

`empire-stonks-ohlcv` does not import `empire-stonks-securities`. It may use
existing shared tables in the `stonks` schema, including:

```text
stonks.provider
stonks.instrument_type
stonks.provider_source_snapshot
stonks.provider_source_snapshot_object
```

The security-master package does not depend on OHLCV. Neither package depends
on the future bridge.

## Provider-Series Identity

A `provider_listing` identifies a provider-native market/symbol series. It does
not assert that the series represents one real-world listing for its entire
history.

The initial provider-series lookup is based on:

```text
provider_code
market
ticker
```

`market` and `ticker` preserve the provider values exactly, including case.
Lookup and uniqueness are case-sensitive. Leading or trailing whitespace and
empty values are invalid; provider adapters must reject them rather than
silently normalizing them. A provider changing only the case of either value
therefore creates a different provider series.

Ticker reuse cannot be reliably detected from raw OHLCV inputs and is not an
initial ingestion responsibility. If a provider reuses a market/ticker tuple
without exposing an identity break, the same provider series may contain both
date ranges. A future bridge can map non-overlapping periods of one provider
series to different canonical listings.

Similarly, if a provider changes its ticker representation, multiple provider
series may later map to different periods of one canonical listing. OHLCV
ingestion does not infer that relationship.

`first_seen` and `last_seen` are the minimum and maximum accepted trading dates
observed for the provider series. They are coverage metadata only and do not
prove listing validity dates or current activity. The initial table has no
status column.

## Provider-Native Value Policy

Daily values are stored as supplied by each provider.

The initial package does not:

- Convert one provider's raw prices to another provider's adjustment basis.
- Reconstruct splits or dividends.
- Reconcile price or volume disagreements.
- Merge provider rows into a consensus value.

Shared daily-bar dataclasses provide a common shape, but they do not imply that
values from different providers are directly comparable.

Where a provider exposes the information, its source contract and operational
report should document:

- The provider-native market and ticker.
- Whether OHLC fields are documented as raw or adjusted.
- Whether adjusted close is separately supplied.
- Whether volume is adjusted, unadjusted, absent, or unspecified.
- The provider source/feed code.
- The parser version.

The initial database deliberately stores one OHLC series, optional volume, and
five derived values used by downstream analysis. It has no adjusted-close,
adjustment, currency, or arbitrary metadata columns. Consumers must use the
provider source contract when interpreting values; the database does not claim
that different providers use comparable adjustment bases.

Sector, industry, fundamentals, and unrelated provider metadata are outside the
OHLCV package even when the same provider exposes them.

## Initial Database Shape

The first implementation adds only:

```text
stonks.provider_listing
stonks.ohlcv_daily
```

It also registers these rows in the existing `stonks.provider` table:

```text
EODDATA
STOOQ
YAHOO
```

### `provider_listing`

`provider_listing` stores the durable UUID used by Empire to own one
provider-native market/symbol series.

The exact columns are:

```text
provider_listing_id  UUID         NOT NULL  PK, default gen_random_uuid()
provider_code        VARCHAR(32)  NOT NULL  FK -> stonks.provider
market               TEXT         NOT NULL
ticker               TEXT         NOT NULL
name                 TEXT         NULL
instrument_type_code VARCHAR(32)  NOT NULL  FK -> stonks.instrument_type,
                                             default 'UNKNOWN'
first_seen           DATE         NULL
last_seen            DATE         NULL
created_at           TIMESTAMPTZ  NOT NULL  default now()
updated_at           TIMESTAMPTZ  NOT NULL  default now()
```

The provider-series lookup key and unique constraint are:

```text
(provider_code, market, ticker)
```

The key uses exact case-sensitive `TEXT` equality. `market` and `ticker` must
both be non-empty and equal to their `btrim` result. `first_seen` and
`last_seen` must either both be null or both be non-null with
`last_seen >= first_seen`. The provider and instrument-type FKs use the default
`NO ACTION` delete behavior so referenced rows cannot be removed while provider
series use them. `name` is descriptive only and has no uniqueness or non-blank
constraint. `updated_at` is maintained by the writer when stored values change;
the initial migration does not add a general timestamp trigger.

The unique lookup index also supports provider-scoped series scans because
`provider_code` is its leading column. A separate partial index on
`(provider_code, last_seen DESC)` where `last_seen IS NOT NULL` supports
provider-scoped freshness and stale-series reporting. No indexes are added for
the optional name or instrument type without a demonstrated query.

The table intentionally omits status, currency, adjustment, and JSON metadata
columns. `UNKNOWN` already exists in `stonks.instrument_type`, so providers can
be imported without inferring a type.

It must not contain `listing_id` or another canonical-identity FK.

### `ohlcv_daily`

`ohlcv_daily` stores one current provider-native daily bar for a
`provider_listing` and trading date.

The intended natural primary key is:

```text
(provider_listing_id, trading_date)
```

The exact columns are:

```text
provider_listing_id UUID           NOT NULL  PK, FK -> provider_listing
trading_date        DATE           NOT NULL  PK
open                NUMERIC(30,10) NOT NULL
high                NUMERIC(30,10) NOT NULL
low                 NUMERIC(30,10) NOT NULL
close               NUMERIC(30,10) NOT NULL
volume              NUMERIC(30,8)  NULL
change              NUMERIC(30,8)  NULL
changepct           NUMERIC(30,8)  NULL
typ                 NUMERIC(30,8)  NOT NULL
hl_range            NUMERIC(30,8)  NOT NULL
oc_range            NUMERIC(30,8)  NOT NULL
created_at           TIMESTAMPTZ    NOT NULL  default now()
updated_at           TIMESTAMPTZ    NOT NULL  default now()
```

The provider-listing FK uses `ON DELETE CASCADE` because a daily bar has no
meaning without its owning provider series. The composite primary key supports
listing/date range scans and per-listing latest-date lookups in either scan
direction, so a duplicate `(provider_listing_id, trading_date DESC)` index is
not added. An additional `(trading_date DESC, provider_listing_id)` index
supports cross-series freshness and coverage queries.

All four OHLC values are required. Checks require `high >= low`, `high` to be
at least `open` and `close`, `low` to be at most `open` and `close`, and volume
to be null or non-negative. Prices are not constrained to be non-negative so
the database does not silently impose a market-domain rule on provider-native
values.

The five derived columns are persisted and rounded to their declared scale:

```text
change    = close - previous_close
changepct = change / previous_close
typ       = (high + low + close) / 3
hl_range  = high - low
oc_range  = close - open
```

`previous_close` is the close from the greatest stored `trading_date` less than
the current date for the same provider listing; it need not be the previous
calendar or weekday date. `change` and `changepct` are null when no previous bar
exists. `changepct` is also null when `previous_close` is zero, and it stores the
ratio rather than percentage points. A check requires `changepct` to be null
whenever `change` is null. Checks also require the stored `typ`, `hl_range`, and
`oc_range` values to equal their formulas after rounding to eight decimal
places. Cross-row `change` and `changepct` correctness remains the writer's
responsibility because a row check cannot inspect the preceding bar.

Inserting or correcting a historical bar recalculates its derived values and
the `change` and `changepct` of the immediately following stored bar. Exact
transaction and returned-count behavior is finalized in S2.3. `updated_at` is
maintained by the writer only when a stored bar or its persisted derived values
change.

These five values remain on `ohlcv_daily` as frequently queried daily-bar
conveniences. A future technical-indicator table is not created or reserved in
the initial schema. If provider-native or canonical technicals are later
implemented, rolling, cross-series, parameterized, or calculation-versioned
indicators belong in a separately designed table at their actual grain; that
does not require moving these foundational daily values.

The table intentionally omits adjusted close, source snapshot, Core run, and
arbitrary metadata columns. Core runs, raw objects, and source snapshots remain
available for import operations and reports, but an individual bar is not
traceable to the run or source snapshot that supplied its current value. This
accepts less auditing and lower row/index storage overhead for the initial
current-state dataset.

A separate `provider_market`, `market_data_series`, canonical bar, or bar
revision table is not part of the initial schema.

## Current-State Upsert Policy

The initial package stores the current provider value for each provider series
and trading date.

- A first import inserts the bar.
- An identical rerun is unchanged and does not duplicate it.
- A later provider correction may update the existing row.
- A historical insert or correction also refreshes prior-close-derived values
  on the immediately following stored bar when necessary.
- The package returns inserted, updated, unchanged, rejected, and warning counts
  where applicable.
- No append-only bar revision history is created initially.
- Exceptional manual database corrections remain an operator responsibility.

This is an intentional early-stage tradeoff. A future requirement for provider
revision history must be designed separately rather than inferred from Core run
records.

## Core Run And Source Provenance

Empire Core owns execution and physical object metadata:

```text
core.core_run
core.stored_object
```

Existing Stonks tables own durable provider-source content identity:

```text
stonks.provider_source_snapshot
stonks.provider_source_snapshot_object
```

The ingestion flow is:

```text
provider source
    -> core.core_run
    -> core.stored_object with short expiration
    -> stonks.provider_source_snapshot

provider source
    -> provider_listing
    -> ohlcv_daily

core.core_run
    -> provider health report
```

Raw objects normally expire after approximately seven days. When Core cleanup
and purge remove a raw object, its `provider_source_snapshot_object` membership
row may be removed while the durable source snapshot and parsed database rows
remain. Source snapshots identify acquired provider content for operations and
reports but are intentionally not foreign-keyed from individual OHLCV rows.

Core runs likewise describe import execution but are not referenced from the
mutable OHLCV facts. Credentials must never be written into run parameters,
summaries, object metadata, logs, reports, or Airflow task payloads.

## Package And Runtime Conventions

### Package names

```text
Poetry distribution: empire-stonks-ohlcv
Python import:       empire_stonks_ohlcv
Initial version:     0.1.0
```

### Database names

```text
stonks.provider_listing
stonks.ohlcv_daily
```

Flyway migrations remain in the monorepo-level `db/flyway/sql` directory and
must run after the existing Core and Stonks reference/source-snapshot
migrations. No package-local migration runner is introduced.

### Core run names

All OHLCV runs use:

```text
domain = stonks
```

Initial job names are:

```text
stonks_ohlcv_eoddata_daily
stonks_ohlcv_stooq_daily
stonks_ohlcv_yahoo_daily
stonks_ohlcv_stooq_backfill
```

The default `subject_key` is `all_series`. Explicitly scoped imports may use a
stable provider-native scope such as `market:<market>` or `symbol:<symbol>`.
Secrets are never part of a subject key or run parameter.

### Airflow DAG names

Initial DAG IDs follow the package job names:

```text
stonks_ohlcv_eoddata_daily
stonks_ohlcv_stooq_daily
stonks_ohlcv_yahoo_daily
```

Yahoo scheduling may remain manual or symbol-limited if its implemented source
contract does not justify a full nightly schedule. Historical Stooq import is an
operator CLI, not a scheduled backfill DAG in the initial scope.

### Object-store names

The object-store key prefix is configured by:

```text
EMPIRE_STORAGE_KEY_STONKS_OHLCV
```

with default:

```text
stonks/ohlcv
```

Raw objects use a deterministic shape equivalent to:

```text
stonks/ohlcv/<provider>/runs/YYYY/MM/DD/<run_id>/<source_code>/
```

Provider reports use:

```text
stonks/ohlcv/<provider>/runs/YYYY/MM/DD/<run_id>/run-reports/health/
```

Initial object kinds are:

```text
stonks_ohlcv_raw_source
stonks_ohlcv_health_report
stonks_ohlcv_backfill_report
```

Health-report logical names use:

```text
stonks-ohlcv-<provider>-health
```

Source codes are stable lowercase feed identifiers prefixed by provider, for
example `eoddata_<feed>`, `stooq_<feed>`, and `yahoo_<feed>`. Exact feed suffixes
and parser versions are fixed in each provider's source-contract task.

## Environment And Secret Conventions

Reusable package code reads configuration from `os.environ`. It must not:

- Load `.env` files.
- Import `python-dotenv`.
- Assume the repository location of `deploy/env/local.env`.
- Read configuration directly from repository files.

Local shells and `bin` wrappers use the existing `bin/env-load` mechanism to
load:

```text
deploy/env/local.env
```

Docker Compose and Airflow receive the same values from the runtime environment.
Non-secret names/defaults are documented in `deploy/env/local.example.env`.
Real credentials remain in the active local environment and are not committed.

Common OHLCV variables are:

```text
EMPIRE_STORAGE_KEY_STONKS_OHLCV=stonks/ohlcv
EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS=7
EMPIRE_STONKS_OHLCV_HTTP_TIMEOUT_SECONDS=<seconds>
EMPIRE_STONKS_OHLCV_MAX_RETRIES=<count>
```

Provider-specific variables use these prefixes:

```text
EMPIRE_STONKS_OHLCV_EODDATA_*
EMPIRE_STONKS_OHLCV_STOOQ_*
EMPIRE_STONKS_OHLCV_YAHOO_*
```

The initial EODData credential name is:

```text
EMPIRE_STONKS_OHLCV_EODDATA_API_KEY
```

Stooq and Yahoo do not have a required secret in the approved architecture.
If the selected source contract later requires one, it must follow the provider
prefix, be documented in the provider task, and receive the same redaction
tests. Source URLs, request bounds, and other provider-specific non-secret
suffixes are finalized with the provider source contracts rather than guessed
here.

## Provider Adapter Boundary

EODData, Stooq, and Yahoo share package-owned dataclasses for provider listings,
daily bars, source metadata, and import results.

Their remote APIs and file layouts do not need a forced common downloader
interface. Provider-specific modules may acquire and parse differently as long
as they return the shared package records and use the same persistence, Core,
validation, and report contracts.

The first EODData vertical slice defines the smallest useful common contract.
Stooq and Yahoo reuse it without adding provider-specific database columns.
Avoid a registry, plugin system, generic provider factory, or unrelated metadata
framework unless later requirements justify one.

## Validation And Reporting Scope

Each provider vertical slice includes its own validation, stored health report,
runner, and Airflow DAG before work begins on the next provider.

The shared report contract should cover:

- Acquisition and parse status.
- Accepted, rejected, inserted, updated, and unchanged counts.
- Per-provider market/series coverage.
- Minimum and maximum trading dates.
- Latest-bar age and stale-series candidates.
- Weekday-shaped gap warnings.
- Bounded samples of failures and warnings.
- Provider-native adjustment/interpretation notes.

The initial schema has no authoritative exchange calendar. Reports must not
claim that a missing exchange holiday is definitively a missing bar.

## Deferred Bridge And Authoritative History

The future bridge will answer:

> Which canonical listing, if any, corresponds to this provider series for a
> particular effective period?

That work is deferred. The current package does not create:

```text
provider_listing_mapping
canonical_ohlcv
authoritative_ohlcv
```

Future temporal mappings must be able to:

- Map multiple provider series to one canonical listing.
- Map different date ranges of one provider series to different listings.
- Preserve unresolved and ambiguous provider series.
- Retain evidence and decision provenance.

Any future authoritative series must select provider rows explicitly and retain
their provider-listing and trading-date identity. If source-level lineage is a
requirement, that future design must add it explicitly because the initial bar
table does not retain a source-snapshot FK. It must not silently coalesce unlike
provider values.

## Known Initial Limitations

- Provider market text is not mapped to canonical exchange records.
- Provider ticker reuse may be undetected.
- Provider values are not normalized across adjustment bases.
- Provider corrections overwrite current rows without stored revision history.
- Individual bars do not retain source-snapshot or import-run provenance.
- Raw files expire after the operational inspection window.
- Gap reports are not exchange-calendar aware.
- No canonical listing relationship exists until bridge work begins.
- No sector, industry, fundamentals, or descriptive enrichment is collected.

These are accepted scope limits, not blockers for importing useful
provider-native daily and historical OHLCV data.
