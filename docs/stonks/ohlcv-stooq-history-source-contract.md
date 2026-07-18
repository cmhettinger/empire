# Stooq Historical Backfill Source Contract

## Status And Scope

This document is the production input contract for the initial operator-run
Stooq historical backfill in `empire-stonks-ohlcv`. It defines the manually
supplied archive, supported US stock partitions, provider-native identity and
value interpretation, runtime inputs, filtering, safety bounds, progress, and
restart behavior implemented by Phase 7.

The workflow imports provider-native daily histories from one Stooq US text
bundle. It does not download from Stooq, automate CAPTCHA or JavaScript browser
verification, schedule a recurring job, or map Stooq series to canonical Empire
listings or exchanges.

The source identity is fixed by the shared provider conventions:

| Field | Value |
|-------|-------|
| Provider code | `STOOQ` |
| Source code | `stooq_history` |
| Parser version | `1.0.0` |
| Operator filename | `d_us_txt.zip` |
| Core filename | `raw.zip` |
| Content type | `application/zip` |

Changing the supported row interpretation requires a parser-version change.
Changing the local path or Stooq delivery filename without changing the logical
dataset does not create a new source code.

## Manual Acquisition Boundary

The operator obtains `d_us_txt.zip` from Stooq outside Empire after completing
any provider-required interactive verification. The operator is responsible for
following Stooq's terms and for recording the acquisition date. No API key,
cookie, CAPTCHA answer, browser state, authenticated URL, or download automation
is accepted by this workflow.

The normal local placement is:

```text
$EMPIRE_TEMP_DIR/d_us_txt.zip
```

`EMPIRE_TEMP_DIR` is loaded by the runtime from `deploy/env/local.env`. The
package receives a resolved input path; it does not load that file or assume the
repository path. A CLI input-path override may select the same supported bundle
from another local directory.

The input must be an existing readable regular ZIP file named
`d_us_txt.zip`. It remains operator-owned: acquisition copies it into Empire
Core and never modifies, moves, or deletes the source file. This is important
during development, when a failed attempt may need to be rerun.

The workflow creates one Core run before it copies the archive. Core stores one
short-lived raw object in the `global` storage root beneath the active run:

```text
stonks/ohlcv/stooq/runs/YYYY/MM/DD/<run_id>/stooq_history/raw.zip
```

The object uses `object_kind=stonks_ohlcv_raw_source`,
`logical_name=stooq_history`, parser version `1.0.0`, and safe
`request_scope=us_stocks` metadata. Its normal expiration is controlled by
`EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS`. Core's size and SHA-256 fields are the
authoritative content identity used by `provider_source_snapshot`.

Selected ZIP members are streamed from the stored archive. They are not
materialized as thousands of separate Core objects or left as untracked files
inside the object store. A parser may use a bounded runtime-owned temporary
buffer when necessary, but it must not extract the complete archive to disk or
load the complete archive into memory.

## Run Date And Trading-Date Bounds

Every run requires an explicit effective date in `YYYY-MM-DD` form. For this
historical source it means the operator-recorded archive acquisition date. It
does not mean the latest trading date in the archive and is never inferred from
the archive filename, filesystem modification time, or row order. The effective
date supplies the Core run and object-path partition.

Optional inclusive trading-date filters limit parsed bars:

```text
start_date <= trading_date <= end_date
```

Either bound may be omitted. With no bounds, all supported dates in the selected
series are eligible. When both are present, `start_date` must not be later than
`end_date`. Rows outside the bounds are counted as filtered, not rejected. An
explicitly bounded run that selects no bars fails preflight instead of silently
reporting success.

The archive may contain dates far earlier than the acquisition date. The
workflow does not impose an arbitrary earliest market date, infer exchange
calendars, or require every weekday. Parsed dates must still be valid calendar
dates and may not be later than the run's archive acquisition date.

## Supported Archive Layout

The archive root and directory names are part of the source contract:

```text
data/
  daily/
    us/
      nasdaq stocks/
        [1/ | 2/ | 3/] <ticker>.us.txt
      nyse stocks/
        [1/ | 2/ | 3/] <ticker>.us.txt
      nysemkt stocks/
        <ticker>.us.txt
```

Files may be directly inside a selected market directory or inside any of its
existing numeric shard directories. Discovery is recursive below each selected
directory and deterministic by full member path. The implementation must not
assume that all future bundles have the same shard count.

Exactly these provider markets are supported:

| Archive directory | Stored `provider_listing.market` | Informational venue |
|-------------------|----------------------------------|---------------------|
| `nasdaq stocks` | `nasdaq` | Nasdaq / XNAS |
| `nyse stocks` | `nyse` | NYSE / XNYS |
| `nysemkt stocks` | `nysemkt` | NYSE American / XASE / AMEX |

The stored lowercase market values are exact Stooq folder identities. The
informational venue column is explanatory only; ingestion does not resolve or
write a canonical exchange or `listing_id`.

An optional market filter accepts a non-empty subset of the three exact stored
market values. The default is all three. An optional ticker filter accepts exact
provider ticker values such as `AACB.US`; it does not accept globs, regular
expressions, case folding, or suffix inference. Filters affect discovery and
progress totals but never change stored identity.

Directories containing `etfs` and every directory outside the three selected
stock partitions are ignored. Their contents do not create listings, bars,
warnings, or absent-series decisions.

## Member And Row Format

Each selected member has a lowercase `.txt` filename but contains CSV text. The
observed header is:

```text
<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>
```

The selected fields map as follows:

| Shared field | Stooq field | Rule |
|--------------|--------------|------|
| listing provider | — | Constant `STOOQ` |
| listing market | archive directory | Exact value from the table above |
| listing ticker | `<TICKER>` | Required exact text, including `.US` |
| listing name | — | `None` |
| instrument type | archive category | `UNKNOWN`; `stocks` is not mapped to a canonical type |
| bar date | `<DATE>` | Required calendar date in `YYYYMMDD` form |
| open | `<OPEN>` | Required finite decimal |
| high | `<HIGH>` | Required finite decimal |
| low | `<LOW>` | Required finite decimal |
| close | `<CLOSE>` | Required finite decimal |
| volume | `<VOL>` | Required finite non-negative decimal; zero is valid |

`<PER>` must be `D`. `<TIME>` and `<OPENINT>` are retained only as structural
input columns and are not persisted. A member must use one ticker throughout,
and that exact uppercase ticker must equal the member basename converted to
uppercase. Two selected members must not claim the same exact
`(market, ticker)` identity.

Prices and volume are parsed directly to `Decimal` without a binary-float round
trip. Volume must not be coerced to an integer: the supplied archive contains
fractional historical volume, including values such as
`593562.95523744`. The shared OHLC invariants apply before persistence.

Rows are expected in ascending date order within a member, but correctness must
not depend on archive or member order. Exact duplicate rows for one
`(market, ticker, date)` may collapse with a warning. Conflicting duplicates are
rejected and reported; first-wins and last-wins behavior are prohibited.

An invalid row is rejected with a deterministic reason and contributes to
bounded issue samples; it is never silently dropped. An unreadable ZIP,
duplicate or unsafe member path, missing selected directory, invalid selected
member header, inconsistent member ticker, or truncated member is a hard source
failure because continuing would make archive coverage unknowable.

## Provider-Native Value Semantics

The selected Stooq bundle does not provide authoritative adjustment or currency
metadata in each row. Empire therefore stores OHLC and volume exactly as
supplied, subject only to declared database scale and validation, and labels all
of these semantics as unspecified:

- Whether historical OHLC values are split-adjusted or dividend-adjusted.
- Whether volume is adjusted and why some historical values are fractional.
- Bar currency.
- Corporate-action interpretation.

Empire does not reconstruct adjustments, round volume to shares, convert
currency, merge Stooq values with another provider, or infer meaning from a
ticker suffix. Reports must repeat these native-semantics limitations.

## Observed Archive Volume And Preflight

The operator-supplied archive inspected for this contract on 2026-07-18 has:

| Measure | Observed value |
|---------|----------------|
| ZIP size | 537,380,289 bytes |
| ZIP entries, including directories | 13,179 |
| Total uncompressed bytes | 1,858,787,027 |
| Selected Nasdaq stock files | 4,724 |
| Selected NYSE stock files | 4,551 |
| Selected NYSE MKT stock files | 323 |
| Selected stock files | 9,598 |
| Selected uncompressed bytes | 1,361,884,825 |
| SHA-256 | `faf932285b47ae216461345e7bac7a1085d210cbddd2f02f8a575ab47ff50435` |

These values are format evidence and planning volume, not invariants for future
downloads. Before Core storage or database writes, acquisition must inspect the
central directory and verify at least:

- The archive is a valid, non-encrypted ZIP.
- Member paths are relative, normalized, unique, and cannot escape the archive
  root; symlinks and other special-file entries are rejected.
- All three selected market directories exist and each contains at least one
  `.txt` member.
- Selected members have nonzero declared size and the complete selected totals
  fit the implementation's documented bounded-resource limits.
- Requested market and ticker filters resolve to at least one selected member.

The inspected archive passes `unzip -tq`. Later implementation tests use small
sanitized fixtures and generated volume data; this full archive is local
operator input and must not be committed as a repository fixture.

The initial parser enforces these deliberately generous safety ceilings:

| Resource | Maximum |
|----------|---------|
| ZIP file size | 4 GiB |
| ZIP central-directory entries | 100,000 |
| Selected stock members | 50,000 |
| Total selected uncompressed bytes | 20 GiB |
| One selected member's uncompressed bytes | 256 MiB |

These limits are package constants, not environment settings. Raising one
requires new representative evidence and tests; a caller cannot disable them.

## Progress And Resource Bounds

The implementation first discovers the selected member set and calculates total
selected files and declared uncompressed bytes. Processing then streams one
member at a time and sends bounded bar chunks to the database writer. It must
not build a list of every bar or one transaction covering the complete archive.

Operational progress includes, at minimum:

- Core run ID and effective date.
- Selected markets, ticker-filter count, and inclusive date bounds.
- Files discovered, files completed, and current member.
- Rows seen, date-filtered, accepted, rejected, and written.
- Chunk number and cumulative inserted, updated, unchanged,
  `derived_updated`, and failure counts.
- Elapsed time and the most recent committed member or chunk boundary.

The runner emits a progress update at least every 100 completed ticker files and
at every chunk commit. Issue details remain bounded by the shared validation and
report contract. The parser requires an explicit positive chunk size. The H7.6
CLI defaults to 50,000 bars, matching the supplied prior implementation's
bounded row batch, and rejects values above 100,000. The H7.8 bounded
development run retained this initial operating value after a real-archive CLI
run completed one actual five-row transaction. That result validates the
bounded path, not 50,000-row capacity; any broad import must still be monitored
through per-chunk progress. These CLI bounds do not weaken the
one-transaction-per-chunk contract.

The package runner uses Core job `stonks_ohlcv_stooq_backfill`, subject
`us_stocks`, and a 900-second heartbeat timeout. Run parameters contain only the
fixed provider/source/parser identities, operator-file mode and filename, exact
date/market/ticker scope, chunk size, storage key, and raw retention period; the
local input path, browser state, and authentication state are not stored. Each
progress payload combines elapsed time, current bounded parser counts, and the
cumulative writer summary. A failing progress observer is non-fatal; Core
heartbeat failures remain run failures.

## Restart And Idempotency

A failed execution is not resumed inside the failed Core run. The operator
starts a new run with the same archive effective date, input checksum, filters,
date bounds, and chunk configuration. The new run stores its own raw object and
report chain while resolving the same durable `stooq_history` source snapshot
identity by checksum.

Every successfully committed chunk remains durable. The failed chunk rolls back
as a unit. A rerun starts discovery from the beginning; current-state listing
and bar upserts classify previously committed content as unchanged and safely
continue through the remainder. No checkpoint table, staging schema, manual row
deletion, or compensating write is required.

The package writer accepts chunks in strict numeric order, deduplicates listing
identities repeated by a parser boundary, and uses one caller connection commit
per chunk. Its bounded summary retains only cumulative completed/failed chunk,
listing, bar, derived-only update, and inactive-skip counts; it does not retain
every chunk result in memory. Validation failures occur before a transaction.
Persistence failures are rolled back and raised as a secret-safe
`OHLCVWorkflowError` scoped to `stooq_history`.

The final report distinguishes a complete run from a partial failed run and
records the exact safe input scope and last committed boundary. The operator
must use the same scope when relying on idempotent restart behavior; changing
filters or bounds is a new import scope rather than a continuation.

The Core success/failure summary also records the restart context: archive
object ID/key/size/checksum, registered source-snapshot identity when available,
exact scope and chunk size, current
parse totals, cumulative write/failure counts, elapsed time, and last committed
chunk. Core stores only the shared safe failure message, never an underlying
database, filesystem, ZIP, or callback exception string.

## Historical Backfill Report

The runner stores one durable schema-version-2 JSON provider report beneath the
active run's shared `reports/report.json` path. It uses
`object_kind=stonks_ohlcv_provider_report` and
`logical_name=stooq_history_report`; unlike the raw ZIP, the report has no
retention expiration. The final Core summary records its object ID and outcome.

The report contains:

- Exact effective date, trading-date bounds, markets, ticker filter, chunk size,
  raw object identity/checksum, and registered source snapshot.
- Complete parser counts or the current partial parser position, cumulative
  writer counts, elapsed time, failed chunks, and last committed chunk.
- Resulting listing and bar coverage for only the selected Stooq markets and
  optional ticker identities. It distinguishes all persisted dates from bars
  inside the requested date bounds and keeps series samples bounded.
- Safe hard-failure stage, rejected/conflicting record counts, collapsed exact
  duplicates, inactive-series skips, and bounded parser issue samples.
- Explicit notes that adjustment basis, currency, volume basis, and corporate
  action interpretation are unspecified and canonical identity is untouched.

A complete report is `PASS` when it has no warnings and `WARN` otherwise. A run
that fails after the archive has been retained receives a best-effort partial
`FAIL` report before Core closes the run. Partial-report construction never
replaces or exposes the original safe workflow failure; if reporting itself is
unavailable, Core still closes the run with its H7.4 restart summary.

## Runtime Settings

The historical workflow uses existing runtime settings:

```text
EMPIRE_TEMP_DIR=<operator input and bounded temporary-work root>
EMPIRE_STORAGE_KEY_STONKS_OHLCV=stonks/ohlcv
EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS=7
```

Database, Core, and global object-store settings remain owned by their existing
runtime configuration. No Stooq credential, URL, browser, HTTP timeout, retry,
or download setting is part of Phase 7. Chunk size and CLI scope are explicit
operator inputs rather than hidden environment behavior.

Reusable package code reads only `os.environ` where environment configuration
is its responsibility. Local wrappers use `bin/env-load`; the package never
opens `deploy/env/local.env` or depends on the repository location.

The operator entry point is:

```bash
bin/stonks-ohlcv-stooq-backfill \
  --input-path "$EMPIRE_TEMP_DIR/d_us_txt.zip" \
  --effective-date 2026-07-18 \
  --start-date 2024-01-01 \
  --end-date 2026-07-17 \
  --market nasdaq \
  --ticker AACB.US \
  --chunk-size 50000
```

`--input-path` and `--effective-date` are required. Market and ticker options
are repeatable exact filters; omitting either selects its documented full
scope. Start/end dates are optional inclusive bounds. The CLI validates its
argument scope before connecting to the database, sends JSON progress records
to stderr, and reserves stdout for one secret-safe final JSON result. The local
path is passed to the runner but is not written to Core parameters, progress,
or final output. Runtime failures expose only a fixed message and nonzero exit.

## Explicit Exclusions

Phase 7 does not include:

- Stooq download, authentication, API-key enrollment, CAPTCHA solving, browser
  automation, or JavaScript-challenge bypass.
- A scheduled or manual Airflow DAG. Phase 7 exposes an operator CLI only.
- Stooq ETFs, world data, indices, intraday bars, or non-US partitions.
- Canonical issuer, security, listing, exchange, or symbol-history mapping.
- Ticker-reuse detection or automatic series splitting.
- Adjustment reconstruction, currency conversion, provider reconciliation, or
  an authoritative OHLCV series.
- Provider-driven listing inactivation or deletion when a ticker is absent.
- Append-only bar revisions, a staging schema, or a checkpoint table.
- One Core object per extracted member or retention of a full extracted tree.
- Committing the full source archive or a large historical sample as a test
  fixture.
