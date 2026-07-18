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
- Optional provider-native listing facts and identifiers supplied with a
  provider series, stored as JSON metadata.
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
- Sector, industry, fundamentals, or broad descriptive enrichment exposed by a
  provider. Optional provider-native listing facts and identifiers, such as a
  FIGI, may be retained on the provider listing as JSON metadata.
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
prove listing validity dates or current activity. The operator-controlled
`status` column enables or disables imports for the provider series; it does
not claim that the real-world instrument or canonical listing is active or
inactive.

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

The initial daily-bar table deliberately stores one OHLC series, optional
volume, and five derived values used by downstream analysis. It has no
adjusted-close, adjustment, currency, or arbitrary bar-metadata columns.
Optional JSON metadata belongs to the provider listing rather than an
individual bar. Consumers must use the provider source contract when
interpreting values; the database does not claim that different providers use
comparable adjustment bases.

Provider-native listing facts and identifiers useful for interpreting or later
reconciling the series, such as FIGI values, may be stored in the listing's JSON
metadata. Sector, industry, fundamentals, and unrelated provider enrichment
remain outside the OHLCV package even when the same provider exposes them.

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
status               VARCHAR(32)  NOT NULL  default 'ACTIVE'
metadata             JSONB        NULL
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

`status` is constrained to `ACTIVE` or `INACTIVE`. It is owned by operators and
is never accepted from or overwritten by provider input. `ACTIVE` allows daily
bars for the series to be imported. `INACTIVE` causes the transactional import
boundary to skip that series' bars, and the lower-level daily-bar writer rejects
direct writes to it. The listing may still be resolved and its descriptive
fields or provider metadata refreshed while inactive.

`metadata` is an optional JSON object for provider-native listing facts and
identifiers that do not justify first-class columns, such as FIGI values. It is
not a general store for fundamentals, sector/industry enrichment, credentials,
request details, or raw provider payloads.

The unique lookup index also supports provider-scoped series scans because
`provider_code` is its leading column. A separate partial index on
`(provider_code, last_seen DESC)` where `last_seen IS NOT NULL` supports
provider-scoped freshness and stale-series reporting. No indexes are added for
the optional name or instrument type without a demonstrated query.

The table intentionally omits currency and adjustment columns. `UNKNOWN`
already exists in `stonks.instrument_type`, so providers can be imported
without inferring a type.

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
to be null or non-negative. All numeric values reject PostgreSQL `NaN`. Prices
are not otherwise constrained to be non-negative so the database does not
silently impose a market-domain rule on provider-native values.

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
and trading date. Persistence operates on validated provider-listing and bar
records; validation must reject invalid records before they reach the writer.

### Input identity and ordering

Each writer call must contain at most one provider-listing record for an exact
`(provider_code, market, ticker)` identity and at most one bar for an exact
`(provider_listing_id, trading_date)` identity. The caller may supply records in
any order. Duplicate keys reaching persistence are an error and roll back the
writer call; the writer never uses first-wins or last-wins behavior.

Values are converted to their database scales before comparison. Derived values
are calculated from those stored-scale OHLC values, not from higher-precision
temporary inputs. This makes rerun comparisons and database formula checks
deterministic.

### Transaction and concurrency boundary

One accepted import batch or bounded historical chunk resolves its provider
listings and writes bars, derived values, and listing coverage dates for active
series in one database transaction. Bars parsed for inactive series are
intentionally omitted before reaching daily-bar persistence. Repository helpers
share the caller's cursor and do not commit independently. Any SQL, constraint,
or duplicate-key error rolls back the whole writer call and is raised to the
import service; persistence errors are not converted into rejected-row counts.

After resolving provider-listing IDs, the writer locks affected
`provider_listing` rows in deterministic ID order. This serializes bar and
derived-value changes for the same provider series while allowing different
series to be written concurrently. The implementation must not depend on input
order for lock order or derived calculations. Listing identities are also
resolved or inserted in deterministic `(provider_code, market, ticker)` order
so concurrent batches do not acquire uniqueness conflicts in caller order.

### Provider-listing resolution and updates

A missing provider series is inserted with its exact provider, market, and
ticker values. A uniqueness conflict resolves the existing row; it does not
create an alternate case or normalized identity.

For an existing series:

- A non-null incoming `name` replaces a distinct stored name; null does not
  erase a stored name.
- A non-`UNKNOWN` incoming `instrument_type_code` replaces a distinct stored
  value. `UNKNOWN` never downgrades a known type.
- Non-null incoming `metadata` replaces distinct stored metadata. Null does not
  erase stored metadata; an explicit empty object clears it to `{}`.
- Incoming provider records never set or change `status`. A manually assigned
  `INACTIVE` status remains in place across provider-listing upserts.
- `first_seen` becomes the least accepted trading date ever written for the
  series and `last_seen` becomes the greatest. They are initialized together
  by the first accepted bar and change only when accepted coverage expands.
- `updated_at` changes only when name, instrument type, metadata, or coverage
  actually changes. Resolving an identical series does not touch the row.

The listing writer reports one mutually exclusive result for each unique series
processed: `inserted`, `updated`, or `unchanged`. A newly inserted listing is
counted only as inserted even when its initial coverage dates are populated in
the same transaction.

### Daily-bar insert, correction, and unchanged behavior

The provider payload of a daily bar is `open`, `high`, `low`, `close`, and
nullable `volume`. The five derived columns are writer-owned and are never
accepted as provider inputs.

- If the `(provider_listing_id, trading_date)` key is absent, the writer inserts
  the stored-scale provider values and calculated derived values.
- If all five stored provider values compare equal with `IS NOT DISTINCT FROM`,
  the input bar is unchanged. It is not rewritten and its timestamps are not
  touched merely because it was seen again.
- If any stored provider value differs, the row is a provider correction. The
  writer replaces the current provider values, recalculates its derived values,
  and changes `updated_at`.

The write is therefore an update-only-when-distinct upsert, not an unconditional
`ON CONFLICT DO UPDATE`. No append-only bar revision row is created. Exceptional
manual database corrections remain an operator responsibility.

### Derived-value recalculation

The writer stages the full batch and calculates against the logical final series
that results when staged provider values overlay stored values. This avoids
input-order-dependent calculations while still supplying required derived
values when a new row is inserted. The recalculation set contains every accepted
input bar plus the immediately following stored bar for each inserted or
corrected date, if one exists in the logical final series. The set is
de-duplicated, so adjacent or overlapping inputs recalculate each affected row
once.

Calculations use the greatest stored trading date less than the target date as
the predecessor. They follow the formulas and eight-decimal rounding contract
defined for `ohlcv_daily`. This handles, without special ordering assumptions:

- Appending a newest bar.
- Inserting a new earliest bar.
- Filling a historical gap between two stored bars.
- Correcting one bar or several adjacent bars in the same batch.

An existing row is updated for derived maintenance only when at least one
derived value is distinct. Such an update changes `updated_at`. A no-op
recalculation does not touch the row.

### Returned counts

Daily-bar persistence returns these disjoint counts:

```text
inserted
updated
unchanged
derived_updated
```

`inserted`, `updated`, and `unchanged` classify accepted unique provider-input
bars and therefore sum to the accepted input count. `derived_updated` counts
existing rows changed only to repair or refresh derived values, including a
following bar not present in the input. An inserted or provider-corrected input
bar is never also counted as `derived_updated`. If an unchanged input row needs
a derived-only repair, it remains `unchanged` for input classification and also
increments `derived_updated` once.

Provider-listing counts are reported separately and are not added to bar
counts. The import/validation layer adds `rejected` and `warning` counts to the
combined result; persistence does not guess those outcomes. A failed writer
call returns no success counts because its transaction is rolled back.

Bars belonging to an inactive provider listing never reach the daily-bar
writer, so they do not appear in its accepted-input counts. The provider
listing itself is still reported as inserted, updated, or unchanged according
to normal listing-upsert behavior.

This is an intentional early-stage current-state tradeoff. A future requirement
for provider revision history must be designed separately rather than inferred
from Core run records.

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

### Acquisition-to-import failure boundary

Provider work uses this ordered durability boundary:

1. `run_provider_import()` starts and commits the Core run.
2. The acquisition collaborator downloads and stores each raw source through
   Core. Core object writes are independently durable before acquisition
   returns.
3. The parsing collaborator fully parses the acquired objects in memory. No
   source snapshot, provider listing, or daily bar is written while parsing.
4. One database transaction registers every acquired source snapshot, resolves
   every provider listing, and writes daily bars only for listings whose stored
   status is `ACTIVE`. The boundary commits once only after all writes succeed
   and otherwise rolls the transaction back.
5. The run wrapper records the compact success summary after that commit.

The failure contract is deliberately forward-only:

| Failed stage | Durable state after failure | Retry behavior |
|--------------|-----------------------------|----------------|
| Acquisition | The Core run and any raw objects already stored by the collaborator remain; no OHLCV transaction has begun. | Retry may reacquire or reuse retained content. |
| Parsing | All acquired Core raw objects remain; no source snapshot, listing, or bar from the attempt exists. | Retry may parse the retained content again. |
| Persistence or commit | Core raw objects remain; source-snapshot, membership, listing, and bar changes from the transaction are rolled back together. | Retry repeats the same content-identity and current-state upserts. |
| Core completion after database commit | Raw objects and all database writes remain even if the run cannot be marked successful. | Retry is safe because snapshot, listing, and bar writes are idempotent. |

No failure path deletes raw evidence or attempts compensating database writes.
`OHLCVWorkflowError` exposes only the allowlisted stage names `acquisition`,
`parsing`, and `persistence`; the original exception remains its in-process
cause. Core receives the fixed run error message and the safe stage only, never
provider, parser, database, credential, URL, or payload details.

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

### Object-store contract

The object-store key prefix is configured by:

```text
EMPIRE_STORAGE_KEY_STONKS_OHLCV
```

with default:

```text
stonks/ohlcv
```

The runtime normalizes the prefix by removing surrounding `/` characters. The
result must be a non-empty relative key; empty path segments and `.` or `..`
segments are invalid. OHLCV uses the existing Core `global` storage root, a
required active `RunContext`, `object_scope = run`, and `domain = stonks`.
Package code does not import `empire-stonks-securities`, but follows its
Core-owned object fields and run/date partitioning conventions.

#### Run object keys

Raw objects use this exact key shape:

```text
<storage_key>/<provider>/runs/YYYY/MM/DD/<run_id>/<source_code>
```

The path components have these meanings:

- `<storage_key>` is the normalized configured prefix.
- `<provider>` is the lowercase form of the uppercase database provider code.
- `YYYY/MM/DD` comes from the run's explicit effective date, not wall-clock
  storage time. Provider runners must always supply that date.
- `<run_id>` is the canonical lowercase UUID text from the active Core run.
- `<source_code>` is the stable lowercase provider-prefixed feed identifier.

Provider and source path values must match
`[a-z0-9]+(?:[_-][a-z0-9]+)*`; path separators, whitespace, and dot segments
are rejected. Exact source codes and parser versions remain owned by the
provider source-contract tasks. Including the run ID makes every attempt
distinct, while all objects from one run remain predictable from its effective
date and provider.

Health and historical-backfill reports use these keys and filenames:

```text
<storage_key>/<provider>/runs/YYYY/MM/DD/<run_id>/run-reports/health
    health.json
<storage_key>/<provider>/runs/YYYY/MM/DD/<run_id>/run-reports/backfill
    backfill.json
```

#### Raw filenames

A source adapter declares a fixed lowercase format suffix as part of its source
contract. One-payload sources use `raw.<format_suffix>`. A multipart source uses
`raw-<part_key>.<format_suffix>`, where `<part_key>` is a stable, path-safe
provider file or request-part identity. Examples include `raw.json`,
`raw.csv.gz`, and `raw-2026-q1.zip`.

`<part_key>` uses the same safe-token rule as provider and source path values.
`<format_suffix>` must match `[a-z0-9]+(?:\.[a-z0-9]+)*` and is fixed by the
source contract rather than inferred from untrusted response data.

The suffix and optional part key must be derived from the source contract and
request scope. Response timestamps, random values, URL query strings,
`Content-Disposition`, and unsanitized provider basenames must not determine the
stored filename. A run may contain only one object for an exact
`(source_code, filename)` pair; adapters split distinct payloads with distinct
stable part keys. Metadata stays in `core.stored_object.metadata`; OHLCV does
not create a metadata sidecar object.

#### Core object fields

The initial object fields are:

| Artifact | `object_kind` | `logical_name` | `content_type` |
|----------|---------------|----------------|----------------|
| Raw provider payload | `stonks_ohlcv_raw_source` | `<source_code>` | Actual allowlisted media type |
| Provider health report | `stonks_ohlcv_health_report` | `stonks-ohlcv-<provider>-health` | `application/json` |
| Historical backfill report | `stonks_ohlcv_backfill_report` | `stonks-ohlcv-<provider>-backfill` | `application/json` |

The raw object's required metadata is a small secret-safe allowlist:

```json
{
  "schema_version": 1,
  "provider_code": "EODDATA",
  "source_code": "eoddata_example",
  "effective_date": "YYYY-MM-DD",
  "acquired_at": "UTC RFC 3339 timestamp",
  "retention_days": 7
}
```

Once assigned by the provider source contract, `parser_version` is also stored.
Safe scalar provider facts such as a provider file date, ETag, or last-modified
value may be added only when the provider adapter explicitly defines them.
Core's first-class `filename`, `content_type`, `size_bytes`, and
`checksum_sha256` columns remain authoritative and are not duplicated in
metadata.

Report metadata uses the same `schema_version`, `provider_code`, and
`effective_date`, plus `report_name` and a UTC RFC 3339 `generated_at`. Counts,
failures, warnings, source semantics, and backfill bounds belong in the report
payload rather than object metadata.

Credentials, authentication headers, cookies, signed or query-bearing URLs,
raw request headers, full configuration dictionaries, and local temporary paths
are forbidden from object keys, filenames, logical names, metadata, and report
payloads. A provider may record a source endpoint only after reducing it to an
explicitly safe, credential-free identifier.

#### Expiration

Immediately before storing a raw object, the helper captures one UTC storage
timestamp and sets:

```text
expires_at = storage_timestamp
             + EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS
```

The configured default is seven days. Expiration is based on storage time, not
the effective date, so an old historical import still receives the full
inspection window. Core cleanup and purge own physical deletion. Health and
backfill reports have `expires_at = NULL` by default because they are run-level
operational records; only raw provider payloads use the short retention setting.

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

The EODData nightly source contract uses:

```text
EMPIRE_STONKS_OHLCV_EODDATA_API_KEY=<required secret>
EMPIRE_STONKS_OHLCV_EODDATA_BASE_URL=https://api.eoddata.com
EMPIRE_STONKS_OHLCV_EODDATA_EXCHANGES=NYSE,NASDAQ,AMEX
```

The initial workflow requires those three exchanges exactly once and requests
them in the configured order. The base URL must be an HTTPS URL without user
information, query, or fragment. Acquisition sends the API key only as the
provider's `apiKey` query parameter and never exposes a query-bearing URL in an
operational artifact. Exact request, response, filename, delivery, duplicate,
and native-value rules are defined in
`docs/stonks/ohlcv-eoddata-source-contract.md`.

Stooq and Yahoo do not have a required secret in the approved architecture.
If the selected source contract later requires one, it must follow the provider
prefix, be documented in the provider task, and receive the same redaction
tests. Source URLs, request bounds, and other provider-specific non-secret
suffixes are finalized with the provider source contracts rather than guessed
here.

## Provider Adapter Boundary

EODData, Stooq, and Yahoo share package-owned dataclasses for provider listings,
daily bars, source metadata, and import results.

The minimal adapter boundary is two callables:

```python
AcquireProviderObjects = Callable[
    [RunContext],
    tuple[AcquiredObject, ...],
]

ParseProviderObjects = Callable[
    [tuple[AcquiredObject, ...]],
    ParsedProviderOutput,
]
```

`AcquireProviderObjects` completes provider-specific retrieval and Core raw
storage, then returns a non-empty tuple of durable `AcquiredObject` references.
`ParseProviderObjects` reads those references using provider-owned mechanisms
and returns one immutable `ParsedProviderOutput` containing:

- A non-empty tuple of `ProviderSourceMetadata(source_code, parser_version)`.
- A tuple of shared `ParsedListingBatch` records, which may be empty for a
  structurally valid source containing no accepted series.

Each source code appears once in the metadata and the metadata source-code set
must exactly match the acquired objects' source-code set. Every parsed listing
must use the provider code of the active import. The boundary carries no URLs,
credentials, headers, retry policy, remote request model, or provider-specific
record types. A shared `ProviderListing` may carry an optional validated JSON
object containing provider-native listing facts and identifiers. Exact
source-code and parser-version values are assigned by the provider source-code
convention and source-contract tasks.

Adapters may satisfy these aliases with functions, bound methods, or other
callables. They do not inherit a shared base class and are not registered in a
provider factory. The transactional import boundary consumes the source
metadata to register each source snapshot and consumes only shared listing/bar
batches for persistence.

### Source and parser identifiers

Production adapters use these exact initial identities:

| Provider | Purpose | `source_code` | `parser_version` |
|----------|---------|---------------|------------------|
| `EODDATA` | Provider symbol-list discovery | `eoddata_symbol_list` | `1.0.0` |
| `EODDATA` | Nightly daily OHLCV | `eoddata_daily` | `1.0.0` |
| `STOOQ` | Nightly daily OHLCV, including native series discovery | `stooq_daily` | `1.0.0` |
| `STOOQ` | Operator-supplied historical files | `stooq_history` | `1.0.0` |
| `YAHOO` | Controlled-symbol daily OHLCV | `yahoo_daily` | `1.0.0` |

Provider codes are the existing uppercase database identifiers. Source codes
are lowercase, provider-prefixed logical feed identifiers. They do not contain
an exchange, ticker, effective date, schedule, endpoint version, filename, or
file partition. For example, every supported Stooq historical partition uses
`stooq_history`; its stable part key and raw filename distinguish the concrete
file inside a run.

A source code remains stable when a URL, host, authentication mechanism, or
delivery filename changes without changing the logical provider feed. A
genuinely different provider dataset receives a new source code rather than
reusing an existing identity. Provider source-contract tasks select the remote
endpoint and format but must use these identifiers unless the implemented feed
is demonstrably a different logical dataset.

Parser versions use numeric `MAJOR.MINOR.PATCH` text and are versioned
independently for each source constant. A parser version changes whenever code
can change accepted or rejected records, provider-native field interpretation,
or shared listing/bar output for the same bytes. Package releases, run dates,
and fixture revisions do not by themselves change it. The current source
snapshot upsert preserves the parser version from the first registration of a
provider/source/checksum identity; a later reparse does not rewrite that
first-seen fact.

Stooq does not need a separate listing-discovery identity because its supported
daily and historical OHLCV records introduce their own provider-native series.
Yahoo likewise imports an explicitly controlled symbol set and has no broad
listing-discovery or historical-file workflow in the initial plan. Adding
identifiers for those unimplemented workflows would not authorize them.

### EODData selected nightly contract

The authoritative EODData production contract is
`docs/stonks/ohlcv-eoddata-source-contract.md`. One run uses an explicit US
exchange effective date and makes six exchange-partitioned requests in this
order:

```text
Symbol/List/NYSE
Symbol/List/NASDAQ
Symbol/List/AMEX
Quote/List/NYSE?DateStamp=YYYY-MM-DD
Quote/List/NASDAQ?DateStamp=YYYY-MM-DD
Quote/List/AMEX?DateStamp=YYYY-MM-DD
```

The API key is also sent on every request but is omitted above deliberately.
Each response is a separate short-lived Core JSON object. Exchange partitions
use `raw-nyse.json`, `raw-nasdaq.json`, and `raw-amex.json` under each of the
two established source-code keys.

Symbol List supplies the exact provider ticker plus best-effort name, type, and
currency. Type and currency remain listing JSON metadata;
`instrument_type_code` stays `UNKNOWN`. Quote-like Symbol List fields are
ignored. Quote List alone supplies daily OHLCV, and each accepted quote must
match the request exchange, daily interval, explicit effective date, and an
accepted same-exchange Symbol List identity.

Compatible duplicate symbol rows coalesce only when each selected descriptive
field has at most one distinct usable value. Conflicting symbol identities and
conflicting duplicate bars are rejected and reported rather than resolved by
input order. Exactly equal duplicate bars may collapse with a warning. Missing
quotes for discovered symbols are normal; quotes without an accepted listing
are rejected; absent symbols never cause automatic deletion or inactivation.

EODData says end-of-day data may receive corrections until 7 p.m. market time,
so the initial Airflow schedule should run no earlier than 8 p.m.
`America/New_York`. The selected provider material does not establish the OHLC
or volume adjustment basis. Reports must label both as unspecified and must not
use listing currency metadata to infer or convert bar currency.

### Provider fixture policy

Provider parser fixtures live under
`packages/empire-stonks-ohlcv/tests/fixtures/<provider>/<source_code>/` and are
governed by the package fixture README and manifest schema. A raw fixture is
committed only after repository format evidence or its provider source contract
documents the endpoint or file, syntax, native identity fields, and observed
OHLCV fields. This prevents a synthetic guess from silently becoming the parser
contract.

Every payload has a `<payload_file>.fixture.json` sidecar recording its
production provider/source/parser identity, repository format reference, provenance,
sanitization, exact byte size and SHA-256, and the minimal parser cases it
covers. Payloads are at most 64 KiB, contain only fields and records required by
those cases, and preserve provider syntax that affects parsing. Credentials,
authentication material, cookies, signed or query-bearing URLs, account data,
request headers, and local paths are prohibited.

Committed parser tests never call live providers. Acquisition uses injected
transport collaborators, while parsers read fixed fixture bytes. Compressed
payloads are allowed only when compression belongs to the documented source
contract. Full provider downloads and large historical samples are not test
fixtures; volume and chunk-boundary tests generate deterministic local data.

No raw provider fixture is committed before its source format is evidenced. The
initial EODData NASDAQ daily fixture is constructed from the bounded live-format
evidence in `docs/stonks/ohlcv-eoddata-daily-format.md` and is interpreted by
the production contract in
`docs/stonks/ohlcv-eoddata-source-contract.md`. Stooq and Yahoo fixtures remain
deferred until H7.1 and Y8.1 provide equivalent format evidence. Stooq daily
fixtures remain deferred until the T10.1 automation gate documents a sustainable
daily source.

### Shared parser test contract

Provider parser tests adapt their parser entrypoint to the test-only
`Callable[[bytes], ParsedProviderOutput]` alias and call the reusable assertions
in `tests/parser_contract.py`. This is a test seam only; production adapters do
not need an identical bytes-based API.

Each provider contract suite supplies exact expected shared records for its
committed fixtures. The assertions call every valid case twice and require:

- The expected uppercase provider code on every listing.
- Exact provider-native market and ticker text, including case and punctuation.
- Stable JSON-ready provider-listing metadata when the source contract exposes
  supported listing facts or identifiers.
- `date` trading dates and `Decimal` OHLCV values rather than floats.
- At least one populated-volume case. A source declaring optional volume also
  supplies a `volume=None` case; a required-volume source must never emit one.
- Stable listing, bar, source-metadata, batch ordering, and JSON-ready output.

Every suite also supplies at least one structurally invalid row or payload. It
must raise `OHLCVParseError` with the same non-empty safe message on repeated
calls; silently normalizing, accepting, or dropping that invalid input fails
the contract. This parser-level rule does not define the later validation
policy or import-level rejected-row counts, which remain owned by E6.4-E6.5.

### Provider runner seam

`run_provider_pipeline()` composes the Core lifecycle and transactional import
boundary while leaving provider work injected:

```python
run_provider_pipeline(
    run_service=run_service,
    connection=connection,
    config=config,
    provider_code=provider_code,
    job_name=job_name,
    effective_date=effective_date,
    run_type=run_type,
    runner=runner,
    acquire=acquire_provider_objects,
    parse=parse_provider_objects,
)
```

The acquisition and parser values use the A5.1 callable aliases. The seam
validates the connection protocol and both collaborators before starting Core,
then delegates run start/completion/failure to `run_provider_import()` and the
ordered acquisition/parse/transaction work to `execute_import_boundary()`.
Provider exceptions retain the existing secret-safe workflow-stage behavior.

The caller owns the injected database connection; the seam does not create,
commit outside the import/Core boundaries, or close it. Tests use fake
collaborators and need no network. Provider-specific daily runners added by the
vertical slices bind real acquisition/parser implementations. A CLI or Airflow
task remains responsible only for runtime context/configuration, connection
scope, calling the package runner, and returning its compact JSON-ready result.
No provider registry, downloader base class, Airflow dependency, or environment
file loading is introduced.

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

The production severity, scoped-count, bounded-issue, freshness, stale-series,
weekday-gap, inactive-series, and JSON report meanings are finalized in
[`docs/stonks/ohlcv-validation-report-contract.md`](../stonks/ohlcv-validation-report-contract.md).

The shared report contract should cover:

- Acquisition and parse status.
- Accepted, rejected, inserted, updated, unchanged, and derived-maintenance
  counts.
- Per-provider market/series coverage.
- Minimum and maximum trading dates.
- Latest-bar age and stale-series candidates.
- Weekday-shaped gap warnings.
- Bounded samples of failures and warnings.
- Provider-native adjustment/interpretation notes.

Reports should exclude intentionally inactive provider listings from ordinary
freshness, stale-series, and gap warnings or present them in a clearly separate
inactive-series section. A manual import disablement must not be reported as an
unexpected provider-health failure.

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
