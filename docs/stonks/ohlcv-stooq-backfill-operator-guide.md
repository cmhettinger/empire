# Stooq Historical Backfill Operator Guide

## Purpose And Boundaries

This runbook describes how to execute and verify Empire's one-shot Stooq US
daily-history backfill. The operator entry point is:

```text
bin/stonks-ohlcv-stooq-backfill
```

The workflow is intentionally CLI-only. It does not have an Airflow DAG, fetch
the archive from Stooq, automate Stooq's browser challenge, or schedule future
runs. Obtain `d_us_txt.zip` manually after completing any provider-required
interactive verification.

The import writes provider-native identities and current daily bars to
`stonks.provider_listing` and `stonks.ohlcv_daily`. It does not map or mutate
canonical issuers, securities, listings, exchanges, or symbol history. See the
[Stooq historical source contract](ohlcv-stooq-history-source-contract.md) for
the complete input format, value semantics, safety limits, and exclusions.

## Before Running

Run commands from the Empire repository root. Confirm that:

- PostgreSQL is running, Flyway migrations are current, and the configured
  Core `global` storage root is available.
- `deploy/env/local.env`, or the file supplied with `--env-file`, contains the
  working Empire database and object-storage configuration.
- The `empire-stonks-ohlcv` package dependencies are installed. If they are
  not, run `poetry install` inside `packages/empire-stonks-ohlcv`.
- The manually downloaded archive is a readable regular file named exactly
  `d_us_txt.zip`. The CLI never changes or deletes this operator-owned file.
- There is enough free space for the archive to be copied into Core storage.
  Every run that reaches acquisition creates a new raw object, including a
  safe rerun.
- The effective date is the date the archive was acquired, not the latest
  trading date contained in it. A parsed trading date cannot be later than the
  effective date.

The default environment expects the archive at:

```text
$EMPIRE_TEMP_DIR/d_us_txt.zip
```

The wrapper loads `deploy/env/local.env` automatically, so `$EMPIRE_TEMP_DIR`
does not need to be exported in the calling shell when an explicit path is
used.

Display the current command help with:

```bash
bin/stonks-ohlcv-stooq-backfill --help
```

## CLI Options

| Option | Required | Meaning |
|---|---:|---|
| `--input-path PATH` | Yes | Existing local file named `d_us_txt.zip`. |
| `--effective-date YYYY-MM-DD` | Yes | Operator-recorded archive acquisition date. |
| `--start-date YYYY-MM-DD` | No | Inclusive earliest trading date. |
| `--end-date YYYY-MM-DD` | No | Inclusive latest trading date. |
| `--market MARKET` | No | Exact `nasdaq`, `nyse`, or `nysemkt`; repeat to include multiple markets. Omit for all three. |
| `--ticker TICKER.US` | No | Exact uppercase Stooq ticker ending in `.US`; repeat to include multiple tickers. Omit for every ticker in the selected markets. |
| `--chunk-size ROWS` | No | Maximum bars per database transaction; default `50000`, maximum `100000`. |
| `--env-file PATH` | No | Environment file loaded by the wrapper; default `deploy/env/local.env`. |

Market and ticker filters are independent. Repeating `--market` broadens the
market set; repeating `--ticker` broadens the exact ticker set inside the
selected markets. Date bounds apply to every selected series. At least one
selected archive member and one eligible bar must remain after filtering.

## Run A Bounded Rehearsal

Before a broad import, use one known ticker and a short trading-date range.
This verifies archive discovery, Core storage, parsing, database writes, and
report generation while keeping the database change easy to inspect.

```bash
bin/stonks-ohlcv-stooq-backfill \
  --input-path tmp/d_us_txt.zip \
  --effective-date 2026-07-18 \
  --start-date 2025-04-07 \
  --end-date 2025-04-11 \
  --market nasdaq \
  --ticker AACB.US \
  --chunk-size 50000
```

Replace the dates and ticker with values appropriate for the archive being
used. Do not reuse the example effective date for a newly acquired archive.

For a durable shell log, keep stdout and stderr separate. Stdout contains only
the final JSON result on success; stderr contains JSON progress events or the
fixed safe error message.

```bash
RESULT_FILE="/tmp/stooq-backfill-result.json"
PROGRESS_FILE="/tmp/stooq-backfill-progress.jsonl"

bin/stonks-ohlcv-stooq-backfill \
  --input-path tmp/d_us_txt.zip \
  --effective-date 2026-07-18 \
  --start-date 2025-04-07 \
  --end-date 2025-04-11 \
  --market nasdaq \
  --ticker AACB.US \
  --chunk-size 50000 \
  >"$RESULT_FILE" \
  2> >(tee "$PROGRESS_FILE" >&2)

jq . "$RESULT_FILE"
```

Each progress line has `event=stooq_history_progress` and includes the Core run
ID, current stage, elapsed time, parser position, and cumulative write counts.
Normal stages are `acquisition`, `parsing`, and `persistence`. A broad import
should continue to emit heartbeats and make progress at file or chunk
boundaries.

## Run The Intended Backfill

Remove only the filters that are intentionally outside the import scope. For
example, the complete supported US stock scope with no trading-date bounds is:

```bash
bin/stonks-ohlcv-stooq-backfill \
  --input-path tmp/d_us_txt.zip \
  --effective-date 2026-07-18 \
  --chunk-size 50000
```

Omitting `--market` selects `nasdaq`, `nyse`, and `nysemkt`. Omitting
`--ticker` selects every stock ticker in those markets. Omitting both date
bounds selects every supported date in the archive. Stooq ETFs and other
partitions are always excluded.

The inspected 2026-07-18 archive contained 9,598 selected stock files and about
1.36 GB of selected uncompressed data. That is planning evidence, not a fixed
requirement for later archives. Monitor the JSON progress stream during the
broad run rather than assuming the rehearsal runtime predicts it.

## Success, Failure, And Reruns

A successful command exits zero and prints one compact, secret-safe JSON object
to stdout. Important fields include:

- `run_id` and `status`
- exact `scope` and `chunk_size`
- raw `acquired_object` identity, size, and SHA-256
- durable `source_snapshot` identity
- `parse_summary` and `write_summary`
- `report_object_id`, `pdf_report_object_id`, and `report_outcome`

`report_outcome` is `PASS` when there are no report warnings and `WARN` when the
run succeeds with rejected records, collapsed exact duplicates, or skipped
inactive-series bars.

A failed command exits nonzero and prints only:

```text
ERROR: Stooq historical backfill failed.
```

Use the progress log's run ID and the Core queries below for the safe failure
stage and last committed chunk. The underlying exception is deliberately not
printed or stored in Core.

Do not delete already written rows after a failure. Start a new command with
the same archive, effective date, date bounds, market/ticker filters, and chunk
size. Each completed chunk from the failed run remains committed; the failed
chunk is rolled back. On rerun, unchanged listings and bars are classified as
`unchanged`, and processing safely continues through the full input. The rerun
creates a new Core run, raw object, and report pair while reusing the same
source-snapshot identity when the archive SHA-256 is unchanged.

## What A Run Produces

Every current successful run produces:

1. A `core.core_run` row for job `stonks_ohlcv_stooq_backfill`.
2. A run-scoped Core raw object named `raw.zip`, with
   `object_kind=stonks_ohlcv_raw_source`. It is a copy of the operator archive
   and normally expires after `EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS`.
3. A checksum-addressed `stonks.provider_source_snapshot` and a link from the
   raw object to that source identity.
4. Upserted `stonks.provider_listing` rows identified by exact
   `(STOOQ, market, ticker)` values.
5. Current `stonks.ohlcv_daily` rows identified by provider listing and trading
   date. A same-key rerun can insert, update, repair derived fields, or leave a
   row unchanged.
6. A durable structured JSON report named `report.json`, with
   `object_kind=stonks_ohlcv_provider_report`.
7. A durable human-readable PDF report named `report.pdf`, with
   `object_kind=stonks_ohlcv_provider_pdf_report`.

The JSON and PDF reports have the same `PASS`, `WARN`, or `FAIL` outcome and do
not have a retention expiration. A failure after raw acquisition receives a
best-effort partial `FAIL` report pair. If reporting itself fails, Core still
records the run failure even though one or both reports may be absent.

Older Stooq runs created before PDF persistence was added can legitimately have
only `raw.zip` and `report.json`. A successful run made with the current CLI
should have all three objects.

## Verify With `psql`

The examples below use the local Docker Compose PostgreSQL container. If the
database is reached another way, open an equivalent `psql` session and use the
same SQL.

```bash
docker exec -it empire-postgres psql -U empire -d empire
```

Disable the pager and define the run and rehearsal scope once. Copy the run ID
from the successful stdout JSON or the first progress event.

```psql
\pset pager off
\set run_id '00000000-0000-0000-0000-000000000000'
\set market 'nasdaq'
\set ticker 'AACB.US'
\set start_date '2025-04-07'
\set end_date '2025-04-11'
```

Keep the single quotes in the `\set` commands. The queries use psql's
`:'variable'` form to quote values safely.

### Find A Run ID

If the final stdout file was lost, list the most recent Stooq attempts:

```sql
SELECT
    run_id,
    status,
    effective_date,
    started_at,
    completed_at,
    summary->>'failed_stage' AS failed_stage,
    summary->>'report_outcome' AS report_outcome
FROM core.core_run
WHERE domain = 'stonks'
  AND job_name = 'stonks_ohlcv_stooq_backfill'
ORDER BY started_at DESC
LIMIT 10;
```

### Verify Run Completion And Scope

```sql
SELECT
    run_id,
    status,
    run_type,
    runner,
    effective_date,
    params->'scope' AS requested_scope,
    params->>'chunk_size' AS chunk_size,
    summary->>'elapsed_seconds' AS elapsed_seconds,
    summary->>'report_outcome' AS report_outcome,
    error_message,
    started_at,
    completed_at
FROM core.core_run
WHERE run_id = :'run_id'::uuid;
```

For success, expect `status=succeeded`, `run_type=cli`, the exact requested
scope, `report_outcome=PASS` or `WARN`, a null `error_message`, and non-null
completion time.

### Verify Parse And Write Counts

```sql
SELECT
    summary->'parse_summary'->>'files_discovered' AS files_discovered,
    summary->'parse_summary'->>'files_completed' AS files_completed,
    summary->'parse_summary'->>'input_rows' AS input_rows,
    summary->'parse_summary'->>'date_filtered_rows' AS date_filtered_rows,
    summary->'parse_summary'->>'accepted_records' AS accepted_records,
    summary->'parse_summary'->>'rejected_records' AS rejected_records,
    summary->'parse_summary'->>'duplicate_rows_collapsed'
        AS duplicate_rows_collapsed,
    summary->'write_summary'->>'chunks_completed' AS chunks_completed,
    summary->'write_summary'->>'chunks_failed' AS chunks_failed,
    summary->'write_summary'->'listing_counts' AS listing_counts,
    summary->'write_summary'->'bar_counts' AS bar_counts,
    summary->'write_summary'->>'skipped_inactive_bars'
        AS skipped_inactive_bars
FROM core.core_run
WHERE run_id = :'run_id'::uuid;
```

For a clean first import, expect zero rejected records, zero collapsed
duplicates, zero failed chunks, and accepted records accounted for by inserted,
updated, or unchanged bar counts plus any inactive-series skips. On an
idempotent rerun, a large or complete `unchanged` count is expected.

### Verify Raw, JSON, And PDF Objects

```sql
SELECT
    object.object_id,
    object.object_kind,
    object.logical_name,
    object.filename,
    object.size_bytes,
    object.checksum_sha256,
    object.metadata->>'outcome' AS outcome,
    object.expires_at,
    object.deleted_at,
    root.root_name,
    root.base_uri || '/' || object.object_key || '/' || object.filename
        AS storage_location
FROM core.stored_object AS object
JOIN core.storage_root AS root USING (storage_root_id)
WHERE object.run_id = :'run_id'::uuid
ORDER BY object.created_at;
```

A current success should return three non-deleted objects: `raw.zip`,
`report.json`, and `report.pdf`. Only the raw object normally has `expires_at`.
The raw checksum should equal the SHA-256 in the CLI result and report. The two
report rows should share the run's `PASS` or `WARN` outcome.

### Verify Source Lineage

```sql
SELECT
    snapshot.source_snapshot_id,
    snapshot.provider_code,
    snapshot.source_code,
    snapshot.parser_version,
    snapshot.content_sha256,
    link.object_id AS raw_object_id
FROM stonks.provider_source_snapshot_object AS link
JOIN stonks.provider_source_snapshot AS snapshot
  USING (source_snapshot_id)
JOIN core.stored_object AS object
  USING (object_id)
WHERE object.run_id = :'run_id'::uuid;
```

Expect one row with `provider_code=STOOQ`,
`source_code=stooq_history`, parser version `1.0.0`, and the same checksum as
the raw object. Rerunning the identical archive creates a new raw object link
but resolves the same `source_snapshot_id`.

### Verify A Listing And Its Date Coverage

```sql
SELECT
    listing.provider_listing_id,
    listing.market,
    listing.ticker,
    listing.status,
    count(daily.trading_date) FILTER (
        WHERE daily.trading_date
              BETWEEN :'start_date'::date AND :'end_date'::date
    ) AS scoped_bars,
    min(daily.trading_date) AS first_persisted_bar,
    max(daily.trading_date) AS last_persisted_bar
FROM stonks.provider_listing AS listing
LEFT JOIN stonks.ohlcv_daily AS daily
  USING (provider_listing_id)
WHERE listing.provider_code = 'STOOQ'
  AND listing.market = :'market'
  AND listing.ticker = :'ticker'
GROUP BY
    listing.provider_listing_id,
    listing.market,
    listing.ticker,
    listing.status;
```

`scoped_bars` should match the number of persisted dates expected inside the
requested bounds. `first_persisted_bar` and `last_persisted_bar` describe all
currently stored dates for the provider series, including dates written by an
earlier run outside this run's bounds.

The OHLCV tables are current-state tables and do not contain a run ID on each
row. The Core summary and reports are therefore authoritative for what this run
attempted and classified; the listing query verifies the resulting current
state.

### Inspect The Persisted Bars

```sql
SELECT
    daily.trading_date,
    daily.open,
    daily.high,
    daily.low,
    daily.close,
    daily.volume,
    daily.change,
    daily.changepct,
    daily.typ,
    daily.hl_range,
    daily.oc_range
FROM stonks.ohlcv_daily AS daily
JOIN stonks.provider_listing AS listing
  USING (provider_listing_id)
WHERE listing.provider_code = 'STOOQ'
  AND listing.market = :'market'
  AND listing.ticker = :'ticker'
  AND daily.trading_date
      BETWEEN :'start_date'::date AND :'end_date'::date
ORDER BY daily.trading_date;
```

Check that `high` bounds open and close, `low` bounds open and close, volume is
non-negative, and the requested inclusive date range is respected. Fractional
Stooq volume is valid and must not be rounded to an integer.

### Diagnose A Failed Run Safely

```sql
SELECT
    run_id,
    status,
    summary->>'failed_stage' AS failed_stage,
    summary->'parse_progress' AS parse_progress,
    summary->'write_summary'->>'last_completed_chunk'
        AS last_completed_chunk,
    summary->'write_summary'->>'chunks_failed' AS chunks_failed,
    summary->>'report_object_id' AS partial_json_report_object_id,
    summary->>'pdf_report_object_id' AS partial_pdf_report_object_id,
    summary->>'report_outcome' AS report_outcome,
    error_message
FROM core.core_run
WHERE run_id = :'run_id'::uuid;
```

Expect `status=failed`, a safe `failed_stage`, and the fixed Core error message.
Non-null report IDs identify the best-effort partial `FAIL` reports. Preserve
the progress log and use the exact original scope for the rerun.

Exit `psql` with:

```psql
\q
```
