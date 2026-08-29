# Technical Indicators Operator Runbook

## Purpose And Safety Boundary

This runbook covers the package-owned technical-indicator operator commands:

- Runtime, dependency, database, storage, and SPX identity readiness.
- Bounded daily calculation, dry runs, corrections, and healthy no-ops.
- Staged historical backfill, partial progress, and exact resume.
- Explicit rebuilds.
- Read-only coverage, freshness, drift, and source-readiness inspection.
- Report interpretation, publication recovery, and safe SQL inspection.

Run commands from the Empire repository root. These workflows read
provider-native `stonks.ohlcv_daily` rows and mutate only technical-indicator,
publication, Core run, and report state they own. They do not ingest or repair
OHLCV, alter provider listings, resolve canonical securities, select model
targets, or make investment recommendations.

Treat command output as operational evidence. The wrappers and package commands
intentionally hide exception, connection, and environment details. Never replace
their bounded output with `env`, `printenv`, `export -p`, shell tracing, complete
Core JSON, or `SELECT *`. Do not copy feature payloads, OHLCV values, database
credentials, or object-store configuration into logs, tickets, or reports.

## Local Setup And Preflight

Start, migrate, and validate the local database with repository workflows:

```bash
make db-up
make db-migrate
make db-validate
```

Install the package environment when needed:

```bash
cd packages/empire-stonks-tech-indicators
poetry install
cd ../..
```

Local wrappers load `deploy/env/local.env` through `bin/env-load`. Reusable
package code reads only `os.environ`; it never opens an environment file or
assumes a repository path. Keep the active file uncommitted and use
`deploy/env/local.example.env` only as the non-secret setting reference.

Confirm that the active file is ignored without displaying it:

```bash
git check-ignore deploy/env/local.env
```

The Core `global` storage root must exist and be writable. Every substantive
daily or backfill attempt stores durable JSON and PDF reports, including dry
runs, healthy no-ops, and partial backfills.

Run the read-only preflight before operator work:

```bash
bin/stonks-tech-indicators-config
```

A successful compact result has `ready=true` and bounded facts for:

- The validated non-secret technical-indicator configuration.
- Supported Python, Empire package, NumPy, TA-Lib Python, and TA-Lib C versions.
- Required package dependencies.
- PostgreSQL, ten required relations and privileges, and the `global` report
  storage root.
- Exactly one active reviewed `YAHOO/XIDX/SPX` benchmark identity.

This command proves runtime and infrastructure readiness only. It does not
prove that a requested effective date has complete OHLCV source evidence or a
ready technical-indicator publication.

On a classified preflight failure, stdout contains `ready=false` and one
`failure_stage`: `runtime`, `dependency`, `database`, or `benchmark`. Stderr
contains only the fixed safe failure. A missing or malformed environment may
produce only the fixed stderr failure. Correct the named layer and rerun; do not
print configuration or connection details to diagnose it.

## Choose A Command And Scope

| Need | Operator entry point | Mutation and scope |
|---|---|---|
| Validate the runtime | `bin/stonks-tech-indicators-config` | Read-only; no date-level publication claim. |
| Refresh one effective date | `bin/stonks-tech-indicators-daily` | One exact effective date; optional provider/market or exact-listing scope. |
| Build historical coverage | `bin/stonks-tech-indicators-backfill` | Required inclusive dates; bounded staged batches and exact resume. |
| Inspect operational facts | `bin/stonks-tech-indicators-inspect` | Read-only repeatable-read snapshot; bounded counts and samples. |

Every wrapper accepts `--env-file PATH`; omit it to use
`deploy/env/local.env`. Use each command's `--help` output as the exact option
contract.

Scope values are provider-native and case-sensitive. Provider codes are exact
uppercase identifiers. Markets retain their exact stored spelling. Exact
listing UUIDs use canonical lowercase text.

Provider and market selectors may be combined and repeated. An exact
`--provider-listing-id` scope is a separate mode and cannot be mixed with
provider or market filters. An omitted selector means the active eligible
universe; it is not permission to run an unreviewed broad backfill.

Inactive listings are excluded by default. Backfill and inspection allow
`--include-inactive` only with exact listing IDs. This opt-in does not make an
ineligible provider series eligible and does not extend inactive coverage
implicitly.

## Inspect Before Writing

Use the read-only inspection for the same date and scope you intend to run:

```bash
bin/stonks-tech-indicators-inspect \
  --effective-date 2026-08-24 \
  --provider-code EODDATA \
  --market NASDAQ \
  --sample-limit 10
```

Optional `--start-date` and `--end-date` are inclusive, must be supplied
together, and must contain the effective date. Inspection executes in one
`REPEATABLE READ READ ONLY` snapshot and does not acquire the writer lock,
create Core state, recover a publication, or mutate payloads.

Review these sections:

- `coverage`: complete count-only source, payload, version, feature-null, and
  benchmark facts.
- `coverage_listing_facts`: source/published key mismatch counts plus bounded
  listing samples.
- `freshness`: last source and published dates plus missing-publication counts.
- `drift`: equivalent/drifted listing counts, reason counts, earliest required
  recalculation date, and bounded samples.
- `spx_readiness`: exact-date upstream provider and benchmark evidence.

The disclosure is intentional: inspection returns no feature values, ranks,
screening thresholds, targets, or recommendations. Prefer it to ad hoc payload
queries.

## Daily Runs, Dry Runs, And No-Ops

The effective date is the exact source-readiness and publication horizon, not
merely the wall-clock date on which the command is executed.

Start with a dry run over the intended scope:

```bash
bin/stonks-tech-indicators-daily \
  --effective-date 2026-08-24 \
  --provider-code EODDATA \
  --market NASDAQ \
  --dry-run
```

A dry run acquires the global writer lock, resolves readiness and scope,
calculates and validates the work, and stores reports, but rolls back feature
and publication state. It does not reserve a future publication or make model
inputs ready.

Run the same scope without `--dry-run` to publish:

```bash
bin/stonks-tech-indicators-daily \
  --effective-date 2026-08-24 \
  --provider-code EODDATA \
  --market NASDAQ
```

Successful stdout is one compact JSON object. Preserve its `run_id`, optional
`publication_id`, JSON/PDF report object IDs, and `outcome`.

- `PASS` or `WARN` means a complete publication succeeded.
- `NO_OP` means the lock was acquired and the existing compatible publication
  was proven ready; reports and a successful Core run still exist, while
  `publication_id` is null.
- Zero writes alone does not prove a no-op. Confirm the outcome and report
  publication/readiness facts.

Use `--force` only when intentionally requesting a rebuild of the resolved
daily scope. It never bypasses source readiness, scope validation, benchmark
identity, report validation, transaction bounds, or the writer lock. Rehearse
with `--dry-run --force` first.

### Manual Airflow Daily Run

The `stonks_tech_indicators_daily_refresh` DAG is initially manual-only, with
no catchup and one active run. Trigger it with a JSON configuration containing
the required exact effective date:

```json
{
  "effective_date": "2026-08-24"
}
```

The optional fields mirror the daily command: `provider_codes`, `markets`, and
`provider_listing_ids` are JSON arrays; `calculation_version` is exact text;
and `dry_run` and `force` are JSON booleans. Exact listing IDs cannot be mixed
with provider or market filters. Use a bounded dry-run scope first when
rehearsing a correction:

```json
{
  "effective_date": "2026-08-24",
  "provider_codes": ["EODDATA"],
  "markets": ["NASDAQ"],
  "dry_run": true
}
```

The DAG never derives the business date from its logical date. Automatic
source-completion dispatch and the coordinator preflight are not enabled in
A11.3; until they are verified, manual runs still fail closed through the
package's same-date readiness decision.

## Publication Readiness

Calculation completion and publication readiness are different facts. A row in
the published view or a `PUBLISHED` database status alone is insufficient.
Readiness is exact to the requested listing/date scope, effective date,
`TECH_INDICATORS_V1`, current source keys and copied OHLCV, and the reviewed SPX
contract.

The package fails closed unless one read-only snapshot proves:

- Every requested listing has one active complete membership.
- Published coverage matches current source keys and row counts.
- Calculation versions are compatible.
- Copied source values and history counts have not drifted.
- Supported subjects use the current reviewed SPX identity with complete
  exact-date source/alignment evidence.
- No building, prepared, failed, removed, stale, or incomplete candidate is
  substituted for the requested publication.

Use `stonks-tech-indicators-inspect` for operational readiness facts. Model
consumers must use the package-owned readiness/model-input query in one
transaction; they must not infer readiness from a bare query of
`stonks.ohlcv_daily_tech_indicators` or reuse an old readiness token.

## Historical Backfill

Begin with one exact listing and a short inclusive range:

```bash
bin/stonks-tech-indicators-backfill \
  --effective-date 2026-08-24 \
  --start-date 2026-07-01 \
  --end-date 2026-08-23 \
  --provider-listing-id 00000000-0000-4000-8000-000000000000 \
  --dry-run
```

The effective date identifies the Core execution and benchmark evidence date.
The start and end dates identify the inclusive historical publication unit.
Replace the example UUID with an exact ID obtained through bounded inspection.

Backfill writes complete current listing images into inactive slots in
1,000-10,000-row transactions, then flips membership only after the whole unit
is prepared and revalidated. Committed partial batches remain invisible to the
published view.

Provider, market, unfiltered, more-than-100-listing, or more-than-1,000,000-row
scopes require `--confirm-broad-scope`, including dry runs. Confirmation is an
acknowledgement, not a bypass. Review the dry-run reports before removing
`--dry-run`.

`--batch-size` defaults to 5,000. Use `--batch-limit` to stop deliberately after
a bounded number of newly committed batches. Progress is compact aggregate JSON
on stderr after each committed transaction; stdout is one terminal compact
result.

A `status=partial`, `outcome=PARTIAL` result is intentionally unpublished and
may exit zero because the requested bounded stop completed correctly. Preserve
all three fields from `resume_cursor`:

```text
provider_listing_id
trading_date
batch_number
```

Resume with the identical immutable listing/date/version/rebuild scope and the
exact cursor:

```bash
bin/stonks-tech-indicators-backfill \
  --effective-date 2026-08-24 \
  --start-date 2026-07-01 \
  --end-date 2026-08-23 \
  --provider-listing-id 00000000-0000-4000-8000-000000000000 \
  --resume-provider-listing-id 00000000-0000-4000-8000-000000000000 \
  --resume-trading-date 2026-07-31 \
  --resume-batch-number 1
```

The cursor is exclusive deterministic progress, not TA-Lib recurrence state.
The package revalidates the committed prefix and scope hash before continuing.
Do not edit, advance, combine, or transplant cursor fields. Resume cannot be
combined with `--dry-run` or `--batch-limit`.

## Rebuilds And Source Corrections

Technical rows are current calculated state, not revision history. The package
never repairs `ohlcv_daily` or `provider_listing`. Provider-source corrections
must first converge through the owning OHLCV workflow described in the
[OHLCV operator runbook](ohlcv-operator-runbook.md).

After source convergence, inspection reports deterministic drift such as
`TAIL_APPEND`, `MISSING_TECH_ROW`, `SOURCE_COPY_DRIFT`,
`HISTORY_COUNT_DRIFT`, `VERSION_DRIFT`, or benchmark-driven drift. A normal
daily run recalculates the conservative affected suffix through its safe
horizon. Recursive indicators make an isolated-row repair unsafe.

Use an explicit staged rebuild for a reviewed historical or version-wide unit:

```bash
bin/stonks-tech-indicators-backfill \
  --effective-date 2026-08-24 \
  --start-date 2025-01-01 \
  --end-date 2026-08-23 \
  --provider-listing-id 00000000-0000-4000-8000-000000000000 \
  --rebuild \
  --confirm-rebuild \
  --dry-run
```

Both `--rebuild` and `--confirm-rebuild` are required. Preserve those flags and
the exact immutable scope when resuming a partial rebuild. Remove `--dry-run`
only after reviewing counts, coverage, benchmark evidence, estimated batches,
and report warnings.

Never update or delete technical payload rows, publication membership, resume
cursors, Core summaries, or source OHLCV manually to force readiness. A missing
technical row is itself a suffix-rebuild signal. SPX corrections propagate to
all supported subjects with affected published coverage; the package does not
guess a proxy benchmark or null old SPX fields to publish partial work.

## Benchmark Failure

The benchmark contract requires exactly one reviewed, active
`YAHOO/XIDX/SPX` provider listing with the expected `EQUITY_INDEX` identity and
Yahoo request symbol, plus sufficient exact-date source evidence for the run.

Diagnose in this order:

1. Run `bin/stonks-tech-indicators-config`. A `failure_stage=benchmark` means
   identity is absent, duplicated, inactive, or materially drifted.
2. Run `bin/stonks-tech-indicators-inspect` for the exact intended effective
   date. Review `spx_readiness` to distinguish identity from missing upstream
   Yahoo/SPX or provider-date evidence.
3. Use the OHLCV operator workflow to restore the reviewed upstream source
   state. Do not create a replacement technical benchmark, change the
   configured identity, or substitute another index.
4. Rerun config and inspection, then repeat the same bounded technical scope.

If benchmark identity becomes unhealthy, supported-subject work fails before
publication. The prior complete publication may remain visible, but it is not
ready for current source state. After source health returns, benchmark-driven
recalculation must complete before readiness can pass.

## Reports And Exit Behavior

Every substantive daily or backfill attempt stores under the configured storage
key (default `stonks/tech-indicators`):

```text
<storage_key>/runs/YYYY/MM/DD/<run_id>/reports/report.json
<storage_key>/runs/YYYY/MM/DD/<run_id>/reports/report.pdf
```

JSON is authoritative for complete structured facts and bounded diagnostics;
PDF is the branded human-readable companion. Neither contains target selection
or a dump of feature rows. Review:

- Identity, exact scope hash/dates, calculation/runtime versions, and source
  readiness.
- Lock outcome and publication method, phase, readiness, and reason counts.
- Selected/source/evaluated/payload/published counts and write outcomes.
- Date, version, null-reason, and SPX-alignment coverage.
- Backfill batch counts, remaining work, and exact cursors.
- Timing, throughput, warnings, failures, and native-value disclosures.

Report outcomes mean:

| Outcome | Operator interpretation |
|---|---|
| `PASS` | Complete successful work with no retained warning or failure. |
| `WARN` | Complete successful work with bounded warnings requiring review. |
| `NO_OP` | Lock-protected proof that no feature mutation was needed. |
| `PARTIAL` | Resumable backfill progress exists but remains unpublished. |
| `FAIL` | No incomplete candidate became published. |

CLI exit behavior is stable:

- `0`: successful command result, including a deliberate partial backfill.
- `2`: invalid command-line arguments or unsafe scope combination; parsing
  stops before database access.
- `75`: immediate writer-lock contention; compact safe JSON is on stderr and
  no workflow state was created.
- `1`: other configuration or runtime failure; stderr contains only a fixed
  safe message, with a bounded readiness-stage object where supported.

Daily, inspection, and terminal backfill results reserve stdout for one compact
JSON object. Backfill progress and contention use stderr. Keep the streams
separate when capturing automation evidence.

## Writer-Lock Contention And Recovery

Every writer—including dry run, no-op, daily, correction, backfill, resume, and
rebuild—uses one nonblocking PostgreSQL transaction advisory lock. Disjoint
providers, listings, dates, and versions still conflict. Config and inspection
remain lock-free.

On contention, do not immediately loop. The invocation created no Core run,
publication, report, payload, or resume state. Preserve the safe stderr result,
identify the current owner through the bounded SQL below, wait for that run to
reach a terminal state, inspect its report/publication, and then make one fresh
attempt with the same scope.

There is no stale lock row to delete. PostgreSQL releases the lock on commit,
rollback, connection loss, backend termination, or database restart. If the
owner loses its lock connection, it fails closed and must not silently
reacquire. Already committed inactive-slot batches remain unpublished and an
exact later invocation may validate and resume them.

Do not call advisory unlock functions, terminate a backend, edit membership,
or mark a Core/publication row complete as routine recovery. An apparently
hung owner requires review of its Core heartbeat and operational context;
backend termination is an exceptional cancellation requiring explicit
authorization.

Crash recovery preserves atomic visibility:

| Observed state | Visible publication | Normal recovery |
|---|---|---|
| Crash before `PREPARED` | Prior complete publication | Rerun the exact bounded scope; resume only from a returned durable cursor. |
| `PREPARED` before Core success | Prior complete publication | Reacquire through a fresh command and let package validation resume or fail the candidate. |
| Core success before terminal commit | Prior complete publication | Fresh invocation revalidates and publishes or marks the candidate/Core failed. |
| Terminal commit before response | Complete new publication | Inspect the already-published state; do not manufacture a new completion. |

## Safe SQL Inspection

Prefer the inspect command. Use SQL only for bounded lifecycle, object, and
aggregate evidence. Open the repository-managed shell:

```bash
make db-psql
```

Disable the pager and set an exact run ID copied from safe CLI output:

```psql
\pset pager off
\set run_id '00000000-0000-0000-0000-000000000000'
```

### Find Recent Technical-Indicator Runs

```sql
SELECT
    run_id,
    job_name,
    subject_key,
    effective_date,
    run_type,
    status,
    started_at,
    last_heartbeat_at,
    completed_at,
    summary->>'outcome' AS outcome,
    error_message
FROM core.core_run
WHERE domain = 'stonks'
  AND job_name IN (
      'stonks_tech_indicators_daily',
      'stonks_tech_indicators_backfill'
  )
ORDER BY started_at DESC
LIMIT 20;
```

Stored errors are intentionally fixed and terse. Do not select complete
`params` or `summary` documents when these allowlisted fields answer the
question.

### Inspect One Run's Publication

```sql
SELECT
    publication_id,
    publication_kind,
    status,
    publication_method,
    calculation_version,
    effective_date,
    requested_start_date,
    requested_end_date,
    expected_listing_count,
    expected_source_row_count,
    expected_payload_row_count,
    completed_batch_count,
    staged_payload_row_count,
    resume_provider_listing_id,
    resume_trading_date,
    json_report_object_id,
    pdf_report_object_id,
    prepared_at,
    published_at,
    failed_at,
    abandoned_at
FROM stonks.tech_indicators_publication
WHERE run_id = :'run_id'::uuid
ORDER BY created_at, publication_id;
```

Aggregate membership without dumping listing IDs:

```sql
SELECT
    publication.status,
    membership.action,
    membership.target_slot,
    membership.is_active,
    membership.calculation_version,
    count(*) AS listing_count,
    sum(membership.source_row_count) AS source_rows,
    sum(membership.payload_row_count) AS payload_rows
FROM stonks.tech_indicators_publication AS publication
JOIN stonks.tech_indicators_publication_listing AS membership
  USING (publication_id)
WHERE publication.run_id = :'run_id'::uuid
GROUP BY
    publication.status,
    membership.action,
    membership.target_slot,
    membership.is_active,
    membership.calculation_version
ORDER BY membership.is_active DESC, membership.target_slot;
```

`BUILDING` and `PREPARED` are not ready. An inactive partial membership is not
visible through the published view.

### List One Run's Reports

```sql
SELECT
    object.object_id,
    object.object_kind,
    object.logical_name,
    object.filename,
    object.content_type,
    object.size_bytes,
    object.checksum_sha256,
    root.root_name,
    root.base_uri,
    object.object_key
FROM core.stored_object AS object
JOIN core.storage_root AS root USING (storage_root_id)
WHERE object.run_id = :'run_id'::uuid
  AND object.object_kind IN (
      'stonks_tech_indicators_report',
      'stonks_tech_indicators_pdf_report'
  )
ORDER BY object.created_at, object.object_id;
```

For a filesystem root, the physical artifact is
`<base_uri>/<object_key>/<filename>`. Verify the exact file's checksum before
opening it. Do not recursively list the storage root.

### Inspect Published Coverage Without Values

```sql
SELECT
    listing.provider_code,
    listing.market,
    indicator.calculation_version,
    count(DISTINCT indicator.provider_listing_id) AS listing_count,
    count(*) AS published_rows,
    min(indicator.trading_date) AS first_date,
    max(indicator.trading_date) AS last_date
FROM stonks.ohlcv_daily_tech_indicators AS indicator
JOIN stonks.provider_listing AS listing USING (provider_listing_id)
GROUP BY
    listing.provider_code,
    listing.market,
    indicator.calculation_version
ORDER BY listing.provider_code, listing.market;
```

This is a coverage observation, not a readiness proof. Do not select feature or
copied OHLCV columns for routine operational inspection.

### Inspect The Exact Writer Lock

The frozen signed 64-bit key `7681980501239933110` maps to PostgreSQL advisory
lock parts `classid=1788600464` and `objid=2749507766`:

```sql
SELECT
    lock.pid,
    lock.granted,
    activity.application_name,
    activity.state,
    activity.xact_start,
    activity.query_start
FROM pg_locks AS lock
LEFT JOIN pg_stat_activity AS activity USING (pid)
WHERE lock.locktype = 'advisory'
  AND lock.classid = 1788600464::oid
  AND lock.objid = 2749507766::oid
ORDER BY lock.granted DESC, lock.pid;
```

This deliberately omits query text, connection details, and backend control.
An empty result means no current lock owner; it does not prove that an existing
candidate is complete or safe to publish.

Exit `psql` with `\q`.

## Reference Contracts

- [Package README](../../packages/empire-stonks-tech-indicators/README.md)
- [Technical-indicators design contract](technical-indicators-design-contract.md)
- [Source-value policy](tech-indicators-source-value-policy-v1.md)
- [Recalculation contract](tech-indicators-recalculation-contract-v1.md)
- [Publication contract](tech-indicators-publication-contract-v1.md)
- [Concurrency contract](tech-indicators-concurrency-contract-v1.md)
- [Report schema](tech-indicators-report-schema-v1.md)
- [PDF design](tech-indicators-pdf-design-v1.md)
- [OHLCV operator runbook](ohlcv-operator-runbook.md)
