# Tech-Indicators Report Schema V1

Status: frozen implementation contract for R8.1 and R8.3 as of 2026-08-22.

This document defines the machine-readable facts shared by the daily and
backfill `report.json` artifacts for `empire-stonks-tech-indicators`. It extends
the [daily technical-indicators design contract](technical-indicators-design-contract.md),
the [performance and release gates](tech-indicators-performance-release-gates-v1.md),
the [publication contract](tech-indicators-publication-contract-v1.md), and the
[concurrency contract](tech-indicators-concurrency-contract-v1.md).

R8.2 owns the aggregate queries that supply these facts. R8.3 owns typed report
models, validation, and deterministic serialization. R8.4 owns Core storage.
R8.5-R8.8 own the PDF presentation and paired-artifact checks. This task does
not implement those later concerns.

## Identity And Compatibility

The root is a JSON object with integer `schema_version: 1`. Unknown root or
section keys are rejected by the V1 serializer. Consumers must reject an
unsupported schema version rather than infer a compatible shape.

The two report identities are:

| Workflow | `report_id` | Core job | Logical JSON name |
|---|---|---|---|
| Daily | `stonks.tech-indicators.daily` | `stonks_tech_indicators_daily` | `tech_indicators_daily_report` |
| Backfill | `stonks.tech-indicators.backfill` | `stonks_tech_indicators_backfill` | `tech_indicators_backfill_report` |

Both use Core domain `stonks`, filename `report.json`, object kind
`stonks_tech_indicators_report`, media type `application/json`, and the frozen
run-scoped reports path. Reports are durable and have no expiration date.

`generated_at` and every other timestamp are timezone-aware UTC RFC 3339 text
with a `Z` suffix. UUIDs use lowercase canonical text. Dates use ISO
`YYYY-MM-DD`. Durations are finite non-negative JSON numbers in seconds.
Counts are non-negative JSON integers; booleans are JSON booleans. A missing
concept is represented by an explicit JSON null where this contract marks the
field nullable, never by an omitted key, empty text, `NaN`, or infinity.

## Root Shape

The exact V1 root members are:

```text
schema_version
report_id
workflow_kind
outcome
generated_at
identity
scope
versions
lock
source_readiness
publication
counts
writes
coverage
backfill
performance
warnings
failures
diagnostic_samples
native_value_semantics
```

Deterministic JSON uses UTF-8, sorted object keys, compact separators, and one
trailing newline. Array ordering is defined below. The serialized artifact must
not exceed P0.8's 2 MiB limit.

### Root outcome

`workflow_kind` is `DAILY` or `BACKFILL`. `outcome` is exactly one of:

| Value | Meaning |
|---|---|
| `PASS` | Complete successful work with no retained warning or failure. |
| `WARN` | Complete successful work with one or more retained warnings. |
| `NO_OP` | Ready, lock-protected success with no eligible feature mutation. |
| `PARTIAL` | Safely resumable backfill progress remains unpublished. |
| `FAIL` | The workflow failed; no incomplete candidate became published. |

`PARTIAL` is valid only for `BACKFILL`. It is not success, readiness, or a
published unit. `NO_OP` is not lock contention: it requires lock acquisition,
source/readiness evaluation, Core lifecycle, and durable reports. A contended
invocation creates no Core run or report and therefore has no V1 report
document.

## `identity`

```text
run_id                         UUID
core_domain                    constant "stonks"
core_job_name                  frozen daily/backfill job name
core_subject_key               non-empty secret-safe text
effective_date                 date
publication_id                 UUID or null
existing_readiness_token       lowercase SHA-256 hex or null
json_object_id                 always null inside report.json
pdf_object_id                  always null inside report.json
```

The report cannot contain its own not-yet-created Core object ID. JSON and PDF
object IDs belong in Core summaries, publication state, and storage metadata,
not recursively inside either artifact. `publication_id` is null for no-op and
dry-run facts. `existing_readiness_token` is populated only by a healthy no-op
that reuses a compatible published snapshot; it is descriptive evidence and
cannot be supplied to a later model-input transaction.

The subject key is `all_series` for the unfiltered universe. A scoped subject
key follows J9's later normalization contract and cannot contain selectors,
credentials, or an unbounded listing list.

## `scope`

```text
scope_schema_version           integer 1
scope_hash                     lowercase SHA-256 hex
effective_date                 date or null
start_date                     date or null
end_date                       date or null
provider_codes                 sorted unique string array
markets                        sorted unique string array
instrument_type_codes          sorted unique string array
requested_listing_count        integer
resolved_listing_count         integer
include_inactive               boolean
dry_run                        boolean
force                          boolean
rebuild                        boolean
```

Daily scope has `effective_date` populated and both range dates null. Backfill
scope has inclusive `start_date` and `end_date` populated and its execution
`effective_date` in `identity`; its scoped `effective_date` is null. Selector
arrays contain safe normalized input selectors, not a complete resolved UUID
set. Empty arrays mean no filter for that dimension. Resolved listing UUIDs
are represented only by their count and bounded diagnostics.

`scope_hash` is the P0.10 canonical resolved-scope hash, not a hash of this
display object. Later J9 tasks may advance the canonical scope schema; doing so
requires a report-schema revision if the displayed fields change.

## `versions`

```text
calculation_version            constant "TECH_INDICATORS_V1"
benchmark_contract_version     constant "TECH_INDICATORS_SPX_V1"
package_version                semantic-version text
python_version                 text
numpy_version                  constant "2.4.6"
talib_python_version           constant "0.7.1"
talib_c_version                constant "0.7.1"
postgresql_version             text or null
```

Versions identify accepted calculations and the measured runtime. They do not
include dependency inventories, image digests, filesystem paths, hostnames, or
environment values. `postgresql_version` may be null when failure occurred
before a safe server-version query.

## `lock`

```text
name                           constant "empire:stonks:tech-indicators:writer:v1"
key                            integer 7681980501239933110
outcome                        "ACQUIRED" or "LOST"
heartbeat_count                integer
heartbeat_failure_count        integer 0 or 1
held_through_report            constant true
```

An `ACQUIRED` report does not claim that the lock has already been released:
P0.10 requires it to remain held through report/Core completion and terminal
publication. `LOST` requires `outcome: FAIL`, exactly one heartbeat failure,
and unpublished candidate state. Backend PIDs, lock-owner facts, SQL, wait
events, connection details, and lock timestamps are prohibited. `CONTENDED`
is deliberately absent because contention must return before workflow state or
report creation.

## `source_readiness`

```text
decision                       "READY", "NOT_READY", or "NOT_APPLICABLE"
effective_date                 date or null
reason_counts[]
  code                         uppercase reason code
  count                        integer
provider_evidence[]
  provider_code                string
  evidence_kind                "CORE_AND_COVERAGE" or "COVERAGE_ONLY"
  required                     boolean
  ready                        boolean
  successful_run_count         integer
  latest_successful_run_id     UUID or null
  source_listing_count         integer
  source_row_count             integer
  effective_date_row_count     integer
benchmark
  required                     boolean
  ready                        boolean
  provider_listing_id          UUID or null
  provider_code                constant "YAHOO"
  market                       constant "XIDX"
  ticker                       constant "SPX"
  effective_date_bar_present   boolean
```

Reason counts are sorted by code. Provider evidence is sorted by provider code
and contains only successful same-date Core identity and aggregate coverage.
It never embeds Core parameters, summaries, object metadata, raw source facts,
or exception text. EODData and Yahoo use `CORE_AND_COVERAGE`; Stooq uses
`COVERAGE_ONLY`. The benchmark UUID is populated only after exact reviewed
resolution. `READY` requires no reasons and all required provider and benchmark
evidence to be ready. Daily readiness uses its effective date. Backfill
readiness may use null effective date and the requested coverage range. A
failure before readiness evaluation uses `NOT_APPLICABLE`, null effective date,
no provider evidence, and a non-ready benchmark shape; it never implies that
sources were healthy.

## `publication`

```text
method                         "IN_PLACE", "STAGED", or "NONE"
report_phase                   "PREPARED_CANDIDATE", "EXISTING_PUBLICATION",
                               "UNPUBLISHED_PARTIAL", "DRY_RUN", or "FAILED"
candidate_status               publication status or null
readiness_at_report            "READY" or "NOT_READY"
readiness_reason_counts[]
  code                         bounded P0.9 reason code
  count                        integer
publication_listing_count      integer
publication_source_row_count   integer
publication_payload_row_count  integer
benchmark_provider_listing_id  UUID or null
benchmark_contract_version     string or null
resume_cursor                  object or null
```

The report records facts at report-generation time and must not claim a
terminal commit that has not happened. A publishing run rendered before P0.9
finalization uses `PREPARED_CANDIDATE` and `NOT_READY`; finalization owns the
later durable `PUBLISHED` state. A healthy no-op uses `EXISTING_PUBLICATION`
and `READY`. A partial backfill uses `UNPUBLISHED_PARTIAL` and `NOT_READY`.
Failure uses `FAILED` and `NOT_READY`.
Dry run uses `DRY_RUN`, `NONE`, and `NOT_READY`; it may report planning and
calculation evidence but cannot create publication state or readiness.

`candidate_status`, when populated, uses the database lifecycle vocabulary
`BUILDING`, `PREPARED`, `PUBLISHED`, `FAILED`, or `ABANDONED`; reports never
invent a parallel state machine. Readiness reason codes are the bounded P0.9
vocabulary. `resume_cursor` uses the backfill cursor shape below and is null
for daily, no-op, non-resumable failure, and complete work.

## `counts`

```text
eligible_listing_count         integer
selected_listing_count         integer
source_listing_count           integer
source_row_count               integer
evaluated_row_count            integer
payload_row_count              integer
published_listing_count        integer
published_row_count            integer
providers[]
markets[]
instrument_types[]
```

Each aggregation row has this exact shape:

```text
code                           provider, market, or instrument-type code
listing_count                  integer
source_row_count               integer
evaluated_row_count            integer
payload_row_count              integer
published_row_count            integer
```

Provider, market, and instrument-type arrays are sorted by exact `code`.
Complete counts are never sampled. Grains remain separate and are not added
together as if one represented another. R8.2 must obtain them with set-based
aggregations and no serialized feature payload.

## `writes`

```text
inserted                       integer
updated                        integer
deleted                        integer
equivalent                     integer
copied_equivalent              integer
unchanged                      integer
failed                         integer
batch_count                    integer
committed_batch_count          integer
rolled_back_batch_count        integer
```

These are mutually explicit operational outcomes. `equivalent` is a
recalculated candidate that preserved the stored payload; `copied_equivalent`
is an exact slot copy and is not recalculation; `unchanged` is inspected input
requiring neither operation. A rolled-back batch contributes no successful
write outcome. `failed` counts attempted logical rows only when that exact
count is known; otherwise it is zero and the failure section carries the
workflow-level failure.

For `NO_OP`, every write and batch count is zero. For `PARTIAL`, committed
inactive-slot batches may be nonzero but `published_row_count` does not advance.

## `coverage`

```text
date
  source_first_date            date or null
  source_last_date             date or null
  payload_first_date           date or null
  payload_last_date            date or null
  effective_date_source_rows   integer
  effective_date_payload_rows  integer
  effective_date_published_rows integer
versions[]
  calculation_version          string
  listing_count                integer
  row_count                    integer
features[]
  feature_name                 V1 analytical field name
  eligible_row_count           integer
  populated_count              integer
  null_count                   integer
  warmup_null_count            integer
  dependency_null_count        integer
  unsupported_null_count       integer
  unexpected_null_count        integer
benchmark
  supported_listing_count      integer
  unsupported_listing_count    integer
  benchmark_linked_row_count   integer
  benchmark_unlinked_row_count integer
  aligned_row_count            integer
  effective_date_aligned_count integer
  complete_20_count            integer
  complete_50_count            integer
  complete_60_count            integer
  complete_63_count            integer
  complete_126_count           integer
  complete_252_count           integer
```

Version rows sort by calculation version. Feature rows include all 76
analytical fields (53 Python-computed plus 23 generated) exactly once in the
feature-profile order; identity, lifecycle, and copied OHLCV fields are not
feature coverage. For every feature row:

```text
populated_count + null_count = eligible_row_count
warmup_null_count + dependency_null_count + unsupported_null_count
    + unexpected_null_count = null_count
```

One null row has exactly one report reason under the precedence
`UNSUPPORTED`, `WARMUP`, `DEPENDENCY`, then `UNEXPECTED`; it is not counted in
multiple buckets. Expected zero-denominator, zero-variance, missing-volume,
or exact-date-alignment nulls are `dependency_null_count`. Unsupported SPX
subject fields use `unsupported_null_count`. Any `unexpected_null_count > 0`
requires `outcome: FAIL`.

Coverage contains counts only. It never contains a feature value, OHLCV value,
rank, threshold, target, or recommendation.

## `backfill`

```text
applicable                     boolean
batch_size                     integer or null
planned_batch_count            integer or null
completed_batch_count          integer
last_completed_cursor          cursor or null
resumed_from_cursor            cursor or null
remaining_listing_count        integer
remaining_row_count            integer
```

A cursor has only:

```text
provider_listing_id            UUID
trading_date                   date or null
batch_number                   positive integer
```

Daily reports use `applicable: false`, null batch size/count/cursors, and zero
completed/remaining counts. Backfill cursors are deterministic progress facts,
not recurrence state or a replacement for the normalized scope hash. `PASS` or
`WARN` backfills have zero remaining counts. `PARTIAL` requires a last-completed
cursor or zero completed batches, and at least one remaining listing or row.

## `performance`

```text
started_at                     UTC timestamp
finished_at                    UTC timestamp
elapsed_seconds                number
peak_rss_bytes                 integer or null
phases[]
  phase                        uppercase phase code
  elapsed_seconds              number
throughput
  evaluated_rows               integer
  persisted_rows               integer
  elapsed_seconds              number
  evaluated_rows_per_second    number or null
  persisted_rows_per_second    number or null
database
  read_page_count              integer
  write_batch_count            integer
  largest_read_page_rows       integer
  largest_write_batch_rows     integer
  longest_write_transaction_seconds number or null
```

Phase rows sort by this frozen R8.3 order and contain no overlapping
double-counted duration:

```text
LOCK
SCOPE_RESOLUTION
SOURCE_READINESS
PLANNING
SOURCE_READ
CALCULATION
VALIDATION
PERSISTENCE
PUBLICATION_PREPARATION
SUMMARY_QUERIES
REPORT_FACTS
```

Throughput denominators are explicit. A rate is null when elapsed time is
zero; it is never infinity. `persisted_rows` is
`inserted + updated` and excludes equivalent, copied, unchanged, and deleted
rows. Peak RSS may be null when the runtime cannot measure it safely.

Timing is operational evidence, not a source of publication truth. Hostnames,
process IDs, container IDs, filesystem paths, query plans, and SQL are
prohibited.

## `warnings`, `failures`, And `diagnostic_samples`

Warnings and failures share this aggregate shape:

```text
code                           uppercase bounded code
count                          positive integer
message                        fixed secret-safe text, at most 500 characters
sample_ids                     sorted diagnostic sample IDs
```

Warning and failure rows sort by code. `PASS` and `NO_OP` have no warnings or
failures. `WARN` has warnings and no failures. `FAIL` has at least one failure.
`PARTIAL` has at least one warning or failure explaining why work stopped.

R8.3 freezes these aggregate codes and messages. The serializer derives the
message from the code; callers cannot provide free-form aggregate text.

| Code | Message |
|---|---|
| `BACKFILL_INCOMPLETE` | Backfill work remains safely resumable and unpublished. |
| `BENCHMARK_COVERAGE_WARNING` | Benchmark coverage requires operator review. |
| `CALCULATION_FAILED` | Technical-indicator calculation failed validation. |
| `CANCELLED` | The workflow was cancelled before publication. |
| `CORE_LIFECYCLE_FAILED` | The Core run lifecycle did not complete safely. |
| `LOCK_LOST` | The package-owned writer lock was lost during the workflow. |
| `PERSISTENCE_FAILED` | Technical-indicator persistence failed safely. |
| `PUBLICATION_NOT_READY` | The candidate publication is not ready. |
| `REPORT_VALIDATION_FAILED` | Report facts failed schema validation. |
| `SOURCE_COVERAGE_WARNING` | Source coverage requires operator review. |
| `SOURCE_NOT_READY` | Required source evidence is not ready. |
| `UNEXPECTED_NULL` | A required post-warm-up feature value is null. |
| `VALIDATION_FAILED` | Technical-indicator output validation failed. |
| `WRITE_RECONCILIATION_FAILED` | Write outcome counts did not reconcile. |

Readiness-only diagnostic samples additionally use their fixed reason-code
messages: `BENCHMARK_MISMATCH`, `BENCHMARK_UNAVAILABLE`,
`COVERAGE_INCOMPLETE`, `EODDATA_SOURCE_EVIDENCE_MISSING`,
`NO_ACTIVE_PUBLICATION`, `NO_ELIGIBLE_LISTINGS`, `SCOPE_MISMATCH`,
`SOURCE_DRIFT`, `SPX_COVERAGE_INCOMPLETE`, `VERSION_MISMATCH`, and
`YAHOO_SOURCE_EVIDENCE_MISSING`.

The root `diagnostic_samples` array contains at most 100 entries across the
entire JSON report. Every sample is referenced by at least one warning,
failure, readiness reason, or coverage anomaly and has:

```text
sample_id                      zero-padded stable text such as "S001"
code                           uppercase bounded code
provider_listing_id            UUID or null
provider_code                  string or null
market                         string or null
ticker                         string or null
trading_date                   date or null
field_name                     V1 field name or null
message                        fixed secret-safe text, at most 500 characters
```

Samples sort by provider code, market, ticker, canonical listing UUID, date,
field, code, then message before receiving IDs. Truncation is explicit through
the aggregate `count` exceeding its `sample_ids` length. A sample may identify
a field but never contain its value, source OHLCV, formula inputs, SQL value,
raw exception, or full payload row.

## `native_value_semantics`

```text
provider_native_grain          constant true
canonical_identity            constant false
cross_provider_normalized      constant false
corporate_actions_normalized   constant false
percentages_are_ratios         constant true
benchmark_alignment            constant "EXACT_DATE_NO_FILL"
notes[]                        ordered fixed disclosure codes
```

`notes` contains these codes, in this exact order when the corresponding
provider or feature family is present:

```text
EODDATA_OHLC_ADJUSTMENT_UNSPECIFIED
EODDATA_VOLUME_BASIS_UNSPECIFIED
EODDATA_LISTING_CURRENCY_NOT_BAR_CURRENCY
STOOQ_OHLC_ADJUSTMENT_UNSPECIFIED
STOOQ_VOLUME_BASIS_UNSPECIFIED_FRACTIONAL_ALLOWED
STOOQ_CURRENCY_UNSPECIFIED
STOOQ_CORPORATE_ACTIONS_UNSPECIFIED
YAHOO_NATIVE_UNADJUSTED_OHLC
YAHOO_ADJUSTED_CLOSE_NOT_PERSISTED
YAHOO_VOLUME_NULLABLE
CORPORATE_ACTIONS_NOT_NORMALIZED
NOMINAL_DOLLAR_VOLUME_NOT_USD
CROSS_PROVIDER_VALUES_NOT_NORMALIZED
```

Disclosure codes, not free-form provider text, identify the reviewed EODData,
Stooq, and Yahoo adjustment/volume/currency limitations from the frozen source
policy. R8.3 exposes one fixed reviewed message for every code so renderers do
not accept free-form disclosure text. Reports must not imply USD liquidity,
adjusted comparability, canonical identity, investment advice, targets, or
recommendations.

## Secret-Safety And Boundedness

The following are prohibited everywhere in the report and its Core metadata:

- credentials, tokens, cookies, authenticated URLs, request headers, DSNs,
  passwords, environment dictionaries, or secret names and values;
- raw provider bodies, complete Core parameters or summaries, database-driver
  exceptions, stack traces, SQL, query plans, backend/process IDs, hostnames,
  filesystem paths, or Airflow context payloads;
- source bars, feature rows, feature values, complete listing UUID arrays,
  ranks, screening thresholds, target flags, strategies, or recommendations;
- uncontrolled exception text or arbitrary provider text.

The report retains complete aggregate counts, at most 100 total diagnostic
samples, and no other unbounded array. Selector, reason, phase, version,
feature, provider, market, and instrument-type arrays are bounded by frozen
vocabularies or the selected scope. R8.3 must reject non-finite numbers,
unknown keys, invalid enums, broken count equations, unsafe text, and sample
overflow before serialization.

Core object metadata for R8.4 is a smaller allowlist, not a copy of this root:

```text
schema_version
report_id
workflow_kind
outcome
effective_date
calculation_version
scope_hash
publication_id
generated_at
```

No metadata field contains selectors, diagnostics, Core summaries, or null
object IDs. JSON and PDF storage use the same metadata facts except object kind,
logical name, filename, content type, and size/checksum owned by Core.

## Cross-Section Invariants

R8.3 must enforce at least these V1 invariants before bytes are produced:

1. Report ID, workflow kind, Core job name, scope date shape, and backfill
   applicability agree.
2. `generated_at` is not earlier than `performance.finished_at`, and elapsed
   time agrees with the start/finish interval within one millisecond.
3. Source readiness `READY` has no reasons and all required evidence ready.
4. Lock loss, unexpected nulls, failed writes, or any failure requires `FAIL`.
5. No-op has existing readiness, zero writes/batches, no candidate publication,
   and no backfill progress.
6. Partial work is backfill-only, remains unpublished, and never advances the
   published counts or readiness token.
7. All root/provider/market/type/write/coverage counts reconcile at their
   declared grains without cross-grain addition.
8. Feature population/null equations hold for every analytical field.
9. Benchmark IDs and counts follow supported/unsupported P0.5 semantics.
10. Warning/failure counts are complete while all referenced samples exist and
    the global sample count is at most 100.
11. Report phase and readiness describe the snapshot at rendering; neither
    predicts a later terminal commit.
12. JSON/PDF facts used by both renderers come from one immutable validated
    report model.

## Handoff To Later Tasks

- R8.2 implements only the set-based provider/market/type/date/version,
  readiness, warm-up/null, and benchmark coverage queries needed here. It must
  not serialize features or add strategy-specific aggregation.
- R8.3 defines immutable report models, freezes phase/disclosure/reason
  vocabularies, validates every invariant above, and emits deterministic JSON
  for all five outcomes.
- R8.4 stores durable JSON through Core using the frozen names, path, metadata
  allowlist, and no expiration.
- R8.5-R8.7 design, render, and visually verify a professional PDF from the
  same immutable facts with P0.8's smaller PDF sample and page bounds.
- R8.8 stores the PDF and proves JSON, PDF, Core metadata, and publication facts
  agree without parsing feature payloads.
