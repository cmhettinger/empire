# OHLCV Operator Runbook

## Purpose And Safety Boundary

This runbook covers normal operation of Empire's provider-native daily OHLCV
workflows:

- EODData calendar-planned daily ingestion.
- Yahoo historical backfill.
- Yahoo eligibility-driven daily ingestion and recent-session reconciliation.
- Historical Stooq import from an operator-supplied archive.
- The manual EODData and Yahoo Airflow DAGs used for local development.
- Safe inspection, reruns, and failure recovery.

Run commands from the Empire repository root. These workflows mutate only the
provider-native OHLCV, Core run/object, and Stonks source-snapshot records they
own. They do not resolve canonical issuers, securities, listings, or exchanges.

The current EODData API key is the only OHLCV provider secret. Never print,
paste, or store it in a command argument, shell history, URL, log, report, Core
record, Airflow configuration payload, issue description, or support message.
In particular:

- Do not run `set -x` around an OHLCV command.
- Do not use `env`, `printenv`, `export -p`, or an unfiltered Compose rendering
  as a configuration check.
- Do not query or copy complete Core `params`, `summary`, or object `metadata`
  values when a bounded field list answers the question.
- Do not log provider response bodies or query-bearing URLs.
- Do not use `SELECT *` for operational evidence.

The package and wrappers intentionally emit secret-safe summaries. Preserve
those summaries and their Core run IDs; do not replace them with environment
dumps.

## Local Setup

### Database And Package

Start and migrate the local database, then validate the migration state:

```bash
make db-up
make db-migrate
make db-validate
```

Install the package environment when needed:

```bash
cd packages/empire-stonks-ohlcv
poetry install
cd ../..
```

The Core `global` storage root must exist and be writable by the CLI or Airflow
runtime. Raw objects, source snapshots, and reports cannot be registered if the
database or configured storage root is unavailable.

### Runtime Configuration And Secrets

Local wrappers load `deploy/env/local.env` through `bin/env-load`. Reusable
package code reads only `os.environ` and never opens that file itself. Keep the
active file local and use `deploy/env/local.example.env` only as the non-secret
key/default reference.

Set a real value locally for:

```text
EMPIRE_STONKS_OHLCV_EODDATA_API_KEY=<secret>
```

Yahoo and the supported historical Stooq path require no provider credential.
They still require the shared Empire database, Core storage, temporary
directory, retention, timeout, and retry configuration.

Confirm that the active file is ignored without displaying its contents:

```bash
git check-ignore deploy/env/local.env
```

Inspect the effective OHLCV settings through the credential-free command:

```bash
bin/stonks-ohlcv-config
```

The output reports `eoddata_configured=true` or `false`; it never returns the
API key. Fix configuration in the local environment file, not in package code,
DAG source, or a committed script.

## Choose A Workflow

| Need | Operator entry point | Scope |
|---|---|---|
| Import one EODData provider date | `bin/stonks-ohlcv-eoddata-daily` | Package planner selects due `NYSE`, `NASDAQ`, and `AMEX` exchange partitions. |
| Seed or repair Yahoo history | `bin/stonks-ohlcv-yahoo-backfill` | All active reviewed seeds by default; exact Empire-ticker and resume bounds are available. |
| Keep Yahoo current | `bin/stonks-ohlcv-yahoo-daily` | Eligible missing sessions plus recent-session reconciliation. |
| Import Stooq US stock history | `bin/stonks-ohlcv-stooq-backfill` | Operator-supplied `d_us_txt.zip`; exact date, market, ticker, and chunk bounds are available. |
| Trigger a provider DAG | Airflow UI or deployment API | Manual EODData or Yahoo; no Stooq DAG exists. |

Every CLI accepts `--env-file PATH`; omit it to use
`deploy/env/local.env`. Use each command's `--help` output as the exact option
contract.

## Manual EODData Daily Run

The effective date is the provider Quote List/session date, not the wall-clock
date on which a late rerun happens:

```bash
bin/stonks-ohlcv-eoddata-daily \
  --effective-date 2026-08-01
```

The package resolves the reviewed exchange policies and decides which exchange
partitions are due. A pre-eligibility, holiday, inactive, or already-complete
scope can complete successfully as a no-op with durable reports. A recent
completed session may still be requested for reconciliation so provider
corrections can converge.

Inspect these compact result fields first:

- `run_id`, `status`, `effective_date`, and `report_outcome`.
- `planned_exchange_count` and `ineligible_exchange_count`.
- `expected_session_count`, `eligible_session_count`, and
  `missing_session_count`.
- `retry_count` and `corrected_current_rows`.
- `listing_counts`, `bar_counts`, row-rejection totals, and inactive skips.
- JSON, run PDF, and daily-market PDF object IDs.

Do not treat zero inserted bars as a failure by itself. Check the plan counts
and report: a healthy idempotent or ineligible run can legitimately write no
bars.

## Yahoo Historical Backfill

Start with a bounded ticker and date range before selecting the full active
seed universe. `--end-date-exclusive` is exclusive:

```bash
bin/stonks-ohlcv-yahoo-backfill \
  --effective-date 2026-08-01 \
  --start-date 2026-07-01 \
  --end-date-exclusive 2026-08-02 \
  --ticker SPX
```

Omitting `--ticker` selects every active reviewed Yahoo seed. Omitting
`--start-date` uses
`EMPIRE_STONKS_OHLCV_YAHOO_BACKFILL_START_DATE`; omitting the exclusive end
uses the day after the effective date. The acquisition layer splits the range
by `EMPIRE_STONKS_OHLCV_YAHOO_BACKFILL_CHUNK_DAYS` and applies configured serial
pacing, jitter, retries, and failure cooldown.

For a safe inclusive restart in stable Empire-ticker order:

```bash
bin/stonks-ohlcv-yahoo-backfill \
  --effective-date 2026-08-01 \
  --start-date 1965-01-01 \
  --end-date-exclusive 2026-08-02 \
  --resume-from SPX
```

When `--ticker` is also supplied, the resume ticker must be in that selected
set. A resume marker is not a mutable checkpoint: it includes that ticker
again, and current-state upserts make the replay safe.

Progress is JSON on stderr; successful stdout is one compact JSON result.
Review selected/enumerated listing counts, request chunks, stored/missing/failed
acquisition counts, parse failures, imported/missing/failed chunks, source
snapshot count, bar counts, report IDs, and report outcome.

## Yahoo Daily Run

Run a bounded diagnostic for one stable Empire ticker when investigating a
specific policy or series:

```bash
bin/stonks-ohlcv-yahoo-daily \
  --effective-date 2026-08-01 \
  --start-date 2026-07-25 \
  --end-date 2026-08-01 \
  --ticker SPX
```

Omitting dates uses the configured inclusive daily lookback ending on the
effective date. Omitting tickers selects all active Yahoo seeds. The daily
runner executes two distinct phases:

1. `daily_ingestion` requests eligible expected sessions that are absent from
   current storage, plus due observed-only polls.
2. `reconciliation` re-pulls the configured recent expected/stored sessions to
   detect late values and provider corrections.

Sessions acquired successfully in the ingestion phase are not requested again
by reconciliation in the same Core run. Failed acquisition work remains
eligible for the reconciliation retry and later runs.

Review the compact `ingestion` and `reconciliation` sections separately. A
nonzero `corrected_reconciliation_bars` value is expected evidence of current-
state correction, not bar revision history. Use the JSON report for bounded
field-level OHLCV differences and adjusted-close diagnostics.

## Historical Stooq Import

Empire does not download the Stooq archive, automate provider enrollment,
solve CAPTCHA, drive browser verification, or create a historical-import DAG.
Complete any required interactive provider steps manually and obtain the
documented `d_us_txt.zip` archive yourself. Do not add cookies, browser state,
credentials, or a provider URL to the CLI arguments or Core metadata.

Run a short one-ticker rehearsal before widening the scope:

```bash
bin/stonks-ohlcv-stooq-backfill \
  --input-path tmp/d_us_txt.zip \
  --effective-date 2026-08-01 \
  --start-date 2026-07-28 \
  --end-date 2026-08-01 \
  --market nasdaq \
  --ticker AACB.US \
  --chunk-size 50000
```

The effective date is the archive acquisition date. The optional start/end
dates are inclusive trading-date filters. Markets are exact lowercase
`nasdaq`, `nyse`, or `nysemkt`; tickers are exact uppercase `.US` identities.
The command copies rather than moves the operator-owned archive into Core and
streams the stored copy in independently committed chunks.

Use the dedicated
[Stooq historical backfill guide](ohlcv-stooq-backfill-operator-guide.md) for
archive acquisition checks, broad-run sizing, progress fields, complete SQL
verification, and partial-chunk recovery. The
[source contract](ohlcv-stooq-history-source-contract.md) is authoritative for
the supported ZIP members and native-value limitations.

## Airflow DAG Operation

Bring up Airflow and confirm discovery with the repository targets:

```bash
make airflow-up
make airflow-dags
```

Both DAGs disable catchup and allow one active run. EODData is enabled at its
bounded weekday cadence. V10.10 keeps Yahoo external-trigger-only with
`schedule=None` and paused between operator runs. Temporarily unpause it for a
manual trigger, then pause it again. Use the Airflow UI or the deployment's
authenticated API; do not put provider credentials in `dag_run.conf`.

### EODData DAG

The DAG ID is `stonks_ohlcv_eoddata_daily_scrape`. It currently has
`schedule=None` for manual local-development operation. An empty configuration
uses the New York date at Airflow's `data_interval_end`. A bounded manual rerun
may provide:

```json
{
  "effective_date": "2026-08-01"
}
```

The task delegates once to `run_eoddata_daily()` and logs and returns only the
compact result. V10.8 selected 20:15 and 23:15 ET each weekday as the reviewed
production cadence, but P13.4-P13.5 must implement deployment-aware profiles
before that cadence is restored. The local profile remains manual.

### Yahoo DAG

The DAG ID is `stonks_ohlcv_yahoo_daily_scrape`. An empty configuration uses
the New York interval date, the configured lookback, and the full active seed
universe. Optional bounds use ISO dates and exact uppercase Empire tickers:

```json
{
  "effective_date": "2026-08-01",
  "start_date": "2026-07-25",
  "end_date": "2026-08-01",
  "tickers": ["SPX", "VIX"]
}
```

The task delegates once to `run_yahoo_daily()`. V10.10 deliberately approved
no automatic cadence: the selected Yahoo endpoint has no published quota or
availability contract, and the operator chose explicit control after the
bounded Y8 validation. Keep the DAG paused between manual runs. If a temporary
schedule is ever tested, rollback means restoring `schedule=None` and pausing
the DAG.

There is no Stooq backfill or Stooq daily DAG. Do not repurpose either provider
DAG to run Stooq work.

## Interpret Eligibility And Reconciliation

### Calendar-Backed Policies

Calendar-backed policies use reviewed exchange schedules, including holidays,
early closes, time zones, and daylight-saving transitions. A session is
eligible only after its exact close/cutoff plus the configured availability
delay. Interpret the fields as follows:

- `expected`: real calendar labels in the requested window.
- `eligible`: expected labels whose availability time has passed.
- `ineligible`: expected labels that exist but are not yet available.
- `missing`: eligible labels with no accepted current bar.
- `stored`: current provider rows; a stored recent row may still be reconciled.

Do not manufacture a bar for a holiday, weekend, or missing provider response.
A missing eligible session remains retryable until a valid bar is stored.

### Observed-Only Policies

Publisher-calculated and other unsupported-calendar policies are observed-only.
A due poll is permission to ask the provider for bounded data; it is not proof
that a session or missing bar exists. Reports must show unresolved polls or
observations without an authoritative missing count or coverage percentage.

### Provider Corrections

Reconciliation overlays provider values on the current series. Equal stored-
scale OHLCV is unchanged. Distinct provider values update the current row and
may update the following row's `change` or `changepct`. No append-only revision
row is created. Yahoo adjusted close remains diagnostic and never replaces the
stored native close.

## Interpret Reports

Completed runs store reports under:

```text
<storage_key>/<provider>/runs/YYYY/MM/DD/<run_id>/reports/
```

| Workflow | Report files |
|---|---|
| EODData daily | `report.json`, `report.pdf`, `daily-market-report.pdf` |
| Yahoo backfill or daily | `report.json`, `report.pdf` |
| Stooq historical | `report.json`, `report.pdf` |

JSON is authoritative for complete structured counts and bounded issue samples.
PDF is the human-readable companion. Reports do not expire; raw provider
objects normally expire after
`EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS`.

Interpret outcome separately from Core execution status:

- `PASS`: the workflow completed without report warnings or hard failures.
- `WARN`: useful work completed, but bounded row exclusions, provider no-data,
  retries/failures isolated to some Yahoo chunks, inactive skips, calendar
  policy errors, or similar non-systemic findings require review.
- `FAIL`: the report describes an incomplete or integrity-failed attempt. Check
  the Core run's safe failed stage and whether partial reports were stored.

For EODData, review per-exchange planning, source acquisition, row-rejection,
write, coverage, freshness, and reconciliation sections. The market PDF is an
equity-focused analytical view, not the authoritative run-status record.

For Yahoo daily, keep `daily_ingestion` and `reconciliation` separate. Review
calendar-backed missing sessions, observed-only polls, acquisition/import
failures, corrections, field differences, and native-versus-adjusted close
diagnostics. For backfill, review exact scope, chunk outcomes, snapshot count,
and persisted in-scope coverage.

For Stooq, review complete versus partial status, parser position, chunk
commits, date/market/ticker scope, inactive skips, and native-semantics notes.

## Inspect Runs And Objects Safely

Open the repository-managed PostgreSQL shell:

```bash
make db-psql
```

Disable the pager and set only the run ID copied from CLI stdout, progress, or
the Airflow task result:

```psql
\pset pager off
\set run_id '00000000-0000-0000-0000-000000000000'
```

### Find Recent OHLCV Runs

```sql
SELECT
    run_id,
    job_name,
    subject_key,
    effective_date,
    run_type,
    status,
    started_at,
    completed_at,
    summary->>'failed_stage' AS failed_stage,
    summary->>'report_outcome' AS report_outcome,
    error_message
FROM core.core_run
WHERE domain = 'stonks'
  AND job_name IN (
      'stonks_ohlcv_eoddata_daily',
      'stonks_ohlcv_stooq_backfill',
      'stonks_ohlcv_yahoo_backfill',
      'stonks_ohlcv_yahoo_daily'
  )
ORDER BY started_at DESC
LIMIT 20;
```

The stored error is intentionally fixed and terse. Use `failed_stage`, report
outcome, and bounded workflow counts; do not expect provider payload or
exception text in Core.

### List A Run's Objects

```sql
SELECT
    object.object_id,
    object.object_kind,
    object.logical_name,
    object.filename,
    object.content_type,
    object.size_bytes,
    object.checksum_sha256,
    object.expires_at,
    object.deleted_at,
    root.root_name,
    root.base_uri,
    object.object_key
FROM core.stored_object AS object
JOIN core.storage_root AS root USING (storage_root_id)
WHERE object.run_id = :'run_id'::uuid
ORDER BY object.created_at, object.object_id;
```

Raw objects use `object_kind=stonks_ohlcv_raw_source` and normally have an
expiration. Provider JSON/PDF reports have no expiration. A failed acquisition
may legitimately retain only the raw objects stored before the failure.

For a filesystem storage root, the physical file is:

```text
<base_uri>/<object_key>/<filename>
```

Inspect only the exact object selected by run ID. Verify size and checksum
before reading content:

```bash
shasum -a 256 /exact/object/path
```

For EODData or Yahoo JSON, prefer structural checks such as `jq type` or a
bounded record count; do not `cat` the payload into a terminal or ticket. For a
Stooq ZIP, use `unzip -t` and a bounded `unzip -l` listing rather than extracting
the full archive. Never copy a raw payload into a committed fixture without the
fixture provenance and sanitization process.

### Verify Source-Snapshot Lineage

```sql
SELECT
    snapshot.source_snapshot_id,
    snapshot.provider_code,
    snapshot.source_code,
    snapshot.parser_version,
    snapshot.content_sha256,
    link.object_id
FROM stonks.provider_source_snapshot_object AS link
JOIN stonks.provider_source_snapshot AS snapshot
  USING (source_snapshot_id)
JOIN core.stored_object AS object
  USING (object_id)
WHERE object.run_id = :'run_id'::uuid
ORDER BY snapshot.source_code, link.object_id;
```

Identical content in a later run should resolve the same source snapshot while
linking a new raw object. After normal Core cleanup/purge, the membership row may
disappear while the source snapshot remains.

### Verify Provider-Native Coverage

Set an exact provider, market, and ticker; values are case-sensitive:

```psql
\set provider 'YAHOO'
\set market 'XIDX'
\set ticker 'SPX'
```

```sql
SELECT
    listing.provider_listing_id,
    listing.status,
    listing.session_policy_code,
    listing.first_seen,
    listing.last_seen,
    count(daily.trading_date) AS stored_bars,
    min(daily.trading_date) AS first_bar,
    max(daily.trading_date) AS last_bar
FROM stonks.provider_listing AS listing
LEFT JOIN stonks.ohlcv_daily AS daily
  USING (provider_listing_id)
WHERE listing.provider_code = :'provider'
  AND listing.market = :'market'
  AND listing.ticker = :'ticker'
GROUP BY
    listing.provider_listing_id,
    listing.status,
    listing.session_policy_code,
    listing.first_seen,
    listing.last_seen;
```

OHLCV rows have no run ID. The run report states what one execution attempted;
this query verifies the resulting current provider-series state.

Exit with `\q`.

## Reruns And Failure Recovery

Start recovery by preserving the run ID, safe CLI progress/output, exact scope,
effective date, and input checksum where applicable. Do not delete raw evidence,
source snapshots, provider listings, or bars to make a retry look clean.

| Failed stage | Durable state | Recovery |
|---|---|---|
| Preflight/configuration | No Core run or provider work may exist. | Correct the local environment or arguments and rerun the same bounded scope. |
| Acquisition | Core run plus any already stored raw objects remain; no uncommitted database work is fabricated. | Resolve connectivity/rate/provider availability and start a new run with the same scope. |
| Parsing | Acquired raw objects remain; affected persistence has not been accepted. | Inspect structure/checksum safely, fix a package/parser defect if proven, then rerun retained-equivalent content in a new run. |
| EODData persistence | The scoped snapshot/listing/bar transaction rolls back together. | Rerun the same effective date; current-state and content-identity upserts are idempotent. |
| Yahoo chunk persistence | Successful request chunks remain committed; the failed chunk is isolated. | Rerun the exact scope or a narrower ticker/range; equal prior chunks become unchanged. |
| Stooq chunk persistence | Earlier chunks remain committed; the failed chunk rolls back and later chunks do not leapfrog it. | Rerun the exact archive/scope/chunk size; completed rows become unchanged and processing continues. |
| Reporting or Core completion | Imported data and raw objects may already be durable even when the run fails to close cleanly. | Inspect current state and objects, then rerun; do not compensate or manually rewrite Core summaries. |

CLI failures expose only one fixed message. Find the run through the latest Core
query or the last stderr progress event. Airflow failures propagate to the task;
use its compact logged run ID and the same Core queries. A rerun always creates a
new Core run and new raw/report objects, while identical provider content may
reuse a source snapshot and equal bars remain unchanged.

Do not manually mark an `INACTIVE` provider listing active merely to suppress a
warning. Status is operator-owned policy and provider imports deliberately
respect it. Do not edit derived daily values directly; historical insertion or
provider correction recalculation belongs to the shared writer.

Raw cleanup is owned by Empire Core. Do not manually remove physical files or
delete `core.stored_object` rows. V10.6 separately verifies the cleanup lifecycle;
this runbook does not authorize an ad hoc cleanup experiment on production
evidence.

## Reference Contracts

- [Package README](../../packages/empire-stonks-ohlcv/README.md)
- [Validation and report contract](ohlcv-validation-report-contract.md)
- [Market-session contract](ohlcv-market-session-contract.md)
- [EODData source contract](ohlcv-eoddata-source-contract.md)
- [Yahoo source contract](ohlcv-yahoo-source-contract.md)
- [Stooq historical source contract](ohlcv-stooq-history-source-contract.md)
- [Stooq historical backfill guide](ohlcv-stooq-backfill-operator-guide.md)
