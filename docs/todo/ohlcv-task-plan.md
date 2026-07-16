# OHLCV Package Action Plan

This document tracks the implementation roadmap for provider-native daily
OHLCV ingestion in Empire Stonks.

The first implementation is intentionally narrow. It downloads provider source
data, retains the raw objects briefly through Empire Core, parses provider-native
listing series and daily bars, and stores current provider-native values in the
`stonks` schema. It does not reconcile those series to canonical issuers,
securities, listings, or exchanges.

The initial providers are:

- EODData
- Stooq
- Yahoo Finance

The implementation should establish one complete provider path before expanding
the same small set of package contracts to the other providers.

## Starting A Task In A New Codex Chat

For a new implementation chat, copy the prompt below and replace `<TASK_ID>`
with the task to complete, such as `B1.1` or `E6.3`. The prompt tells Codex to
read the repository instructions and current documentation, honor completed
prerequisites and prior `Done:` notes, keep the work within the named task,
validate the implementation, and update this checklist when finished.

```text
Complete task <TASK_ID> from docs/todo/ohlcv-task-plan.md.

Before making changes, read AGENTS.md, docs/todo/ohlcv-plan.md, the full
docs/todo/ohlcv-task-plan.md, and docs/todo/ohlcv-task-plan-archive.md. Inspect
the current repository state and the Done: notes for completed prerequisite
tasks; do not assume the plan is newer than the live code.

Implement the named task completely and keep the work scoped to that task and
its necessary integration points. Follow the existing Empire architecture,
package, database, environment, Core, and Airflow conventions. Preserve
unrelated user changes and do not begin later tasks unless they are inseparable
from completing this one; if so, explain why.

Run formatting, linting, focused tests, import checks, and database or Airflow
validation appropriate to the files changed. Fix failures caused by the work.
When the task is complete, mark its checkbox [x] in
docs/todo/ohlcv-task-plan.md and add a terse dated Done: note listing the key
files changed and exact verification results. Summarize the implementation,
non-obvious decisions, and any remaining risks. If the task cannot be completed,
leave it unchecked and report the concrete blocker instead of weakening the
completion criteria.
```

## Package Boundary

`empire-stonks-ohlcv` owns:

- Provider-specific source acquisition and parsing for OHLCV inputs.
- Shared provider-listing and daily-bar dataclasses.
- Provider-native listing-series persistence.
- Provider-native daily OHLCV persistence.
- Idempotent current-state upserts.
- Empire Core run tracking and short-lived raw-object storage integration.
- Durable source-content identity through `stonks.provider_source_snapshot`.
- Daily and historical-import runners.
- OHLCV validation, freshness, coverage, and operational reports.
- Thin CLI entrypoints called by operators and Airflow.

`empire-stonks-ohlcv` does not own:

- Canonical issuer, security, listing, exchange, or symbol-history mutation.
- Provider-to-canonical listing mappings.
- Ticker-reuse detection or reconstruction of real-world identity changes.
- Cross-provider price normalization or provider-consensus values.
- Corporate-action normalization or adjustment reconstruction.
- Sector, industry, fundamentals, descriptive enrichment, or other non-OHLCV
  metadata that a provider may expose.
- An authoritative canonical OHLCV series.

The future `empire-stonks-ohlcv-bridge` package is deferred until the OHLCV
package is stable and the security master is further along. No bridge package,
mapping table, mapping status, or `listing_id` dependency is part of phases
0-10 below.

## Initial Data Contract

A `provider_listing` is a provider-native market/symbol series. It is not a
claim that the ticker has represented one real-world listing for all time.
Initial ingestion may identify a series by the provider, provider-native market
text, and provider-native ticker. If a provider reuses a ticker and the reuse is
not detectable from its input, ingestion may continue writing the same provider
series. A future temporal bridge can map different date ranges of that series to
different canonical listings.

`ohlcv_daily` stores values as supplied by each provider. The package does not
normalize price adjustment bases or reconcile disagreements across providers.
Provider-native adjustment semantics must be documented in provider source
contracts and operational reports so consumers do not assume unlike series are
comparable. They are not stored as columns on each listing or bar.

The initial database shape is deliberately limited to:

```text
stonks.provider_listing
stonks.ohlcv_daily
```

The package reuses these existing tables rather than creating equivalents:

```text
stonks.provider
stonks.instrument_type
stonks.provider_source_snapshot
stonks.provider_source_snapshot_object
core.core_run
core.stored_object
```

Raw provider objects should normally expire after approximately seven days.
Their durable checksum/source/parser identity remains in
`stonks.provider_source_snapshot` after Core removes the physical object and its
membership link. Database OHLCV rows remain the long-lived parsed output.

The initial package stores current provider values. An idempotent rerun skips
unchanged rows and a later provider correction may update the existing daily
row. It does not add an append-only bar-revision table. Exceptional manual
database corrections remain an operator responsibility during this phase.

Airflow is orchestration only. Provider acquisition, parsing, persistence,
validation, reporting, and sequencing belong in the package.

Runtime configuration follows the existing Empire boundary. Local shells,
`bin` wrappers, Docker Compose, and Airflow load values from
`deploy/env/local.env`; reusable package code reads only `os.environ`. The
package must not load `.env` files, depend on the repository path, or copy
provider credentials into Core run parameters, object metadata, logs, reports,
or Airflow task payloads.

---

## How To Use This Checklist

Each task is intended to fit in one focused work session. A task is complete
only when the code/doc changes are made, the listed verification passes, and the
status checkbox is updated.

Default working pattern: use one Codex chat per task ID, such as `P0.1`,
`S2.1`, or `E6.1`. Start the chat by naming the task ID and asking Codex to read
this document, complete that task, run the listed verification, and update the
checkbox plus `Done:` note. Adjacent tiny tasks may be combined when they are
naturally coupled, but large tasks should be split in this document rather than
stretched across a long chat. New chats should start by reading the prior task's
`Done:` note in this plan or its archive and the current live repository state.

Status format:

- `[ ]` Not started
- `[~]` In progress
- `[x]` Complete

When completing a task, add a short `Done:` note under the task with the date,
the key files changed, and the verification command/result. Keep the notes terse
so this remains useful as a working reference.

---

## Completed Phase Archive

Fully completed phases and their `Done:` notes are moved to the
[OHLCV package action plan archive](ohlcv-task-plan-archive.md) to keep this
active checklist focused. Phases 0-2 are currently archived there;
their task IDs remain valid dependencies for active work.

## Phase 3: Shared Models And Persistence

Goal: build provider-neutral package primitives for parsed records and database
writes without introducing provider-specific schema branches.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| M3.1 | [x] | Add provider-listing dataclass | Add a typed immutable record for provider code, native market, native ticker, optional name, and instrument type defaulting to `UNKNOWN`. Validation tests cover required identity fields. | B1.2, S2.1 |
| M3.2 | [x] | Add daily-bar dataclass | Add a typed immutable daily-bar record using `date` and `Decimal`, with optional volume and validation matching the source-field database invariants. Persisted derived values are writer-calculated rather than provider inputs. Unit tests cover valid and invalid bars. | B1.2, S2.2 |
| M3.3 | [x] | Add provider batch/result models | Add small JSON-ready result dataclasses for acquired objects, parsed listing/bar batches, inserted/updated/unchanged and derived-maintenance counts, failures, and warnings. | M3.1-M3.2 |
| M3.4 | [x] | Implement provider-listing writer | Add focused transactional SQL that resolves or inserts provider series idempotently and updates observational metadata without mutating canonical tables. Unit tests cover reruns and different providers/markets. | S2.3, M3.1 |
| M3.5 | [ ] | Implement daily-bar writer | Add batched transactional current-state upserts returning inserted, updated, unchanged, and derived-updated counts. Tests cover reruns, provider corrections, following-bar derived-value recalculation, null optional fields, and constraint failures. | S2.3, M3.2-M3.4 |
| M3.6 | [ ] | Add daily-bar query helpers | Add only the read queries needed for incremental cutoffs, per-series date ranges, freshness, coverage, and reporting. Ordering and empty-state tests pass. | M3.5 |
| M3.7 | [ ] | Prove provider isolation | Tests prove identical market/ticker/date values from EODData, Stooq, and Yahoo remain distinct through their provider-listing IDs and cannot overwrite one another. | M3.4-M3.6 |

Done: 2026-07-16 — added and publicly exported immutable `ProviderListing` in
`packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/{models.py,__init__.py}`
with identity/default/immutability coverage in `tests/{test_models.py,
test_exceptions.py}`; focused tests passed (20), full package tests passed (41),
and Poetry lock check, `compileall`, isolated import smoke test, `pip check`,
package sdist/wheel build, 88-column scan, and `git diff --check` passed (no
project formatter/linter is configured).

Done: 2026-07-16 — added and publicly exported immutable `DailyBar` in
`packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/{models.py,__init__.py}`
with source-only fields and date/Decimal/OHLCV invariant coverage in
`tests/{test_models.py,test_exceptions.py}`; focused tests passed (73), full
package tests passed (94), and Poetry lock check, `compileall`, isolated import
smoke test, `pip check`, package sdist/wheel build, 88-column scan, and
`git diff --check` passed (no project formatter/linter is configured).

Done: 2026-07-16 — added public JSON-ready acquisition, parsed-batch,
persistence-count, issue, and provider-import records in
`packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/{results.py,models.py,
__init__.py}` with coverage in `tests/{test_results.py,test_exceptions.py}`;
focused tests passed (26), full package tests passed (120), and Poetry lock
check, `compileall`, isolated import/JSON smoke test, `pip check`, package
sdist/wheel build, 88-column scan, and `git diff --check` passed (no project
formatter/linter is configured).

Done: 2026-07-16 — added the caller-transaction-owned provider-listing writer
and resolved-ID results in
`packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/{listings.py,__init__.py}`
with fake-cursor and rollback-only PostgreSQL coverage in
`tests/{test_provider_listings.py,test_provider_listings_integration.py,
test_exceptions.py}`; focused unit tests passed (6), PostgreSQL integration
passed (1), full package tests passed (127), Flyway validated 31 migrations,
and the OHLCV schema contract passed. Poetry lock check, `compileall`, import
smoke test, `pip check`, package sdist/wheel build, 88-column scan, and
`git diff --check` passed (no project formatter/linter is configured).

## Phase 4: Core Run, Object-Store, And Source-Snapshot Integration

Goal: retain raw inputs briefly while preserving durable content identity and
run-level operational provenance.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| C4.1 | [ ] | Define OHLCV object paths and kinds | Document deterministic storage keys for provider/date/run/source, raw filenames, object kinds, logical names, metadata, and approximately seven-day expiration. | P0.4-P0.5, B1.3 |
| C4.2 | [ ] | Add raw-object storage helper | Add package-owned helpers that store downloaded bytes/files through `ObjectStore` with the active `RunContext`, checksum, provider metadata, and expiration. Tests use an in-memory/fake object repository. | C4.1 |
| C4.3 | [ ] | Add source-snapshot persistence | Add focused Stonks persistence that upserts `provider_source_snapshot` by provider/source/checksum and links each current stored object through `provider_source_snapshot_object`. Do not duplicate these tables. | C4.2, S2.5 |
| C4.4 | [ ] | Prove cleanup-safe lineage | Tests or database verification prove raw object purge removes snapshot-object membership while the source snapshot and OHLCV rows remain valid. | C4.3 |
| C4.5 | [ ] | Add package run wrapper | Add a reusable runner that starts, completes, fails, and summarizes `core.core_run` records around provider acquisition/import work. Tests cover success and failure paths. | B1.3, M3.3, C4.2 |
| C4.6 | [ ] | Add acquisition-to-import transaction boundary | Define and implement failure behavior between completed raw download, snapshot registration, parsing, and database writes so partial failures are reportable and safely rerunnable. | C4.3-C4.5, M3.5 |

## Phase 5: Provider Contract And Fixtures

Goal: establish the small shared boundary used by all three providers while
allowing their acquisition and parsing details to differ.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| A5.1 | [ ] | Define provider output contract | Define the minimal provider interface or callable contract that yields shared listing and daily-bar batches plus source metadata. Do not require unrelated metadata or identical remote APIs. | M3.1-M3.3, C4.6 |
| A5.2 | [ ] | Define source-code conventions | Assign stable provider/source/parser-version identifiers for listing discovery, nightly daily data, and historical files so source snapshots remain interpretable. | C4.3, A5.1 |
| A5.3 | [ ] | Add provider fixture policy | Add small committed fixtures derived from documented provider formats, sanitized of credentials and limited to records needed for parser and edge-case tests. | A5.1-A5.2 |
| A5.4 | [ ] | Add shared parser contract tests | Add reusable assertions for provider code, exact market/ticker preservation, date/Decimal parsing, optional volume, rejected invalid rows, and deterministic output. | A5.3 |
| A5.5 | [ ] | Add provider runner seam | Make package runners accept provider acquisition/parser collaborators so tests do not require network access and Airflow remains a thin caller. | C4.5-C4.6, A5.1 |

## Phase 6: EODData End-To-End Vertical Slice

Goal: complete the first provider from environment configuration and
acquisition through validation, stored bars, reporting, and its nightly Airflow
DAG before starting the next provider.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| E6.1 | [ ] | Document EODData source and config contract | Record the chosen nightly source, `EMPIRE_STONKS_OHLCV_EODDATA_*` settings, authentication requirements, file/response format, market/ticker fields, native value semantics, and expected delivery timing. Secrets come from `deploy/env/local.env` at runtime. | A5.1-A5.2, B1.6-B1.7 |
| E6.2 | [ ] | Implement EODData acquisition | Download or receive the chosen nightly source with timeouts, bounded retries, clear errors, injected HTTP/file dependencies, and Core raw-object storage. Unit tests cover success, common failures, and secret-safe errors/metadata. | E6.1, C4.2, A5.5 |
| E6.3 | [ ] | Implement EODData parser | Parse fixtures into shared provider-listing and daily-bar records while preserving provider-native market, ticker, and value semantics. Shared parser-contract tests pass. | E6.1-E6.2, A5.3-A5.4 |
| E6.4 | [ ] | Define shared validation and report contract | Define structural OHLC checks, null/volume handling, hard failures versus warnings, provider/run import counts, freshness, coverage, stale-series, and weekday-shaped gap metrics. State that gaps are not exchange-calendar authoritative. | P0.3, S2.2, M3.6 |
| E6.5 | [ ] | Implement EODData import service | Validate parsed records, register the source snapshot, resolve provider listings, upsert daily bars, and return accepted/rejected/inserted/updated/unchanged plus derived-maintenance counts. Idempotent rerun tests pass. | E6.2-E6.4, M3.4-M3.5, C4.3-C4.6 |
| E6.6 | [ ] | Implement EODData health queries | Add the first deterministic health queries for the shared report contract, scoped to EODData provider series. Validate indexes against representative fixture volume. | E6.4-E6.5 |
| E6.7 | [ ] | Build and store EODData report | Produce a common Empire-style JSON report with EODData run/import counts, freshness, coverage, stale series, gap warnings, failures, and native-semantics notes; store it under the active Core run. Tests cover paths and metadata. | E6.5-E6.6, C4.2, C4.5 |
| E6.8 | [ ] | Add EODData CLI | Add an operator CLI and `bin` wrapper that receives `deploy/env/local.env` through `bin/env-load`, supports an explicit effective date, runs import plus reporting, and emits a secret-safe JSON summary. | E6.7, B1.8 |
| E6.9 | [ ] | Add EODData daily runner | Add package-owned sequencing for nightly EODData acquisition, snapshot registration, validation, persistence, reporting, and Core run completion/failure. Tests cover success, failure, and rerun behavior. | E6.7-E6.8 |
| E6.10 | [ ] | Add EODData nightly DAG | Add one thin scheduled DAG that obtains Airflow context/config from the Compose environment, calls the package runner, and returns only small secret-safe summaries/object IDs. DAG tests cover schedule, catchup, overlap, context, and imports. | E6.9, B1.5-B1.7 |
| E6.11 | [ ] | Verify EODData Airflow discovery | Rebuild/restart the Airflow image as required and verify the EODData DAG appears with its intended schedule/tags and imports without credentials in the DAG source. | E6.10 |
| E6.12 | [ ] | Run EODData fixture vertical test | Run the full EODData fixture path through the DAG-callable package runner and report. Confirm the operational run/object/snapshot/report chain and the separately persisted provider listing/bars, then prove a rerun is unchanged. | E6.10-E6.11, S2.6 |

## Phase 7: Stooq Daily End-To-End Vertical Slice

Goal: add Stooq acquisition, persistence, provider-scoped reporting, and its
nightly DAG using the proven EODData contracts without changing the schema.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| T7.1 | [ ] | Document Stooq daily source and config contract | Record the chosen daily source, `EMPIRE_STONKS_OHLCV_STOOQ_*` settings, file/response format, market/ticker fields, native value semantics, and source availability expectations. Runtime values come from `deploy/env/local.env`. | E6.12, A5.1-A5.2 |
| T7.2 | [ ] | Implement Stooq daily acquisition | Acquire the chosen daily source and store it through the same Core object/snapshot flow. Tests cover success, retryable failure, invalid content, and secret-safe diagnostics. | T7.1, C4.2, A5.5 |
| T7.3 | [ ] | Implement Stooq daily parser | Parse Stooq fixtures into shared records without EODData-specific persistence branches. Shared parser-contract tests pass. | T7.1-T7.2, A5.3-A5.4 |
| T7.4 | [ ] | Implement Stooq daily import service | Compose validation, snapshot registration, provider-listing writes, bar upserts, and import summaries. Reruns are idempotent. | T7.2-T7.3, E6.4-E6.5 |
| T7.5 | [ ] | Build and store Stooq report | Reuse the shared health/report contract for Stooq-scoped freshness, coverage, stale series, gap warnings, failures, and native-semantics notes. Tests prove provider scoping and stored report paths. | T7.4, E6.6-E6.7 |
| T7.6 | [ ] | Add Stooq daily CLI | Add an operator CLI and `bin` wrapper using `bin/env-load`; it runs Stooq daily import plus reporting and emits a secret-safe JSON summary. | T7.5, B1.8 |
| T7.7 | [ ] | Add Stooq daily runner | Add package-owned nightly Stooq sequencing with Core run lifecycle and reporting. Tests cover success, failure, and reruns. | T7.5-T7.6 |
| T7.8 | [ ] | Add Stooq nightly DAG | Add one thin scheduled DAG calling the Stooq runner. Tests cover schedule, catchup, overlap, context, small task payloads, and import safety. | T7.7, B1.5-B1.7 |
| T7.9 | [ ] | Verify Stooq vertical workflow | Verify Airflow discovery and run the full Stooq fixture path through reporting. Confirm all lineage and report rows, then prove EODData and Stooq overlapping histories remain isolated. | T7.8, M3.7 |

## Phase 8: Historical Stooq Import

Goal: provide a safe operator-run historical import with its own progress and
coverage reporting, without adding canonical identity assumptions.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| H8.1 | [ ] | Define historical import inputs and bounds | Document supported Stooq historical source files, environment settings, date bounds, symbol/market filters, expected volume, restart behavior, and explicit exclusions. | T7.9 |
| H8.2 | [ ] | Add streaming/chunked historical parser | Parse historical input without loading the entire dataset into memory. Tests prove stable chunk boundaries and equivalent results across chunk sizes. | H8.1, T7.3 |
| H8.3 | [ ] | Add chunked database writer | Write provider listings and bars in bounded transactions with cumulative inserted/updated/unchanged/derived-updated/failure counts. A failed chunk can be rerun safely. | H8.2, M3.4-M3.5 |
| H8.4 | [ ] | Add historical import run tracking | Start one Core run with explicit non-secret parameters and progress summaries; retain source snapshots and raw input according to the same retention policy. Failure leaves enough context for an operator rerun. | H8.3, C4.3-C4.6 |
| H8.5 | [ ] | Add historical import report | Build and store a Stooq backfill report with input bounds, chunk progress, write counts, resulting coverage, failures, and warnings. Tests cover partial and successful runs. | H8.4, T7.5 |
| H8.6 | [ ] | Add historical Stooq CLI | Add `stonks-ohlcv-stooq-backfill` using `bin/env-load`, with explicit input/date/filter/chunk options and a secret-safe JSON summary. It does not mutate canonical tables. | H8.5, B1.8 |
| H8.7 | [ ] | Add historical fixture vertical test | Import a multi-symbol, multi-date fixture twice, store its report, and prove stable provider-listing IDs, unchanged second-run counts, correct date ranges, and bounded transactions. | H8.6 |
| H8.8 | [ ] | Run bounded development backfill | Run a deliberately small local/dev date-and-symbol range using `deploy/env/local.env`, inspect performance/counts/reporting, and record the command/result before any broad import. | H8.7 |

## Phase 9: Yahoo Daily End-To-End Vertical Slice

Goal: add Yahoo acquisition, persistence, reporting, and the intentionally
selected scheduling mode while keeping non-OHLCV Yahoo data out of the package.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| Y9.1 | [ ] | Document Yahoo source and config contract | Record the chosen OHLCV endpoint/source, `EMPIRE_STONKS_OHLCV_YAHOO_*` settings, request inputs, market/ticker fields, native daily/adjusted semantics, rate/error behavior, and explicit exclusion of enrichment. Runtime values come from `deploy/env/local.env`. | T7.9, A5.1-A5.2 |
| Y9.2 | [ ] | Implement Yahoo acquisition | Acquire Yahoo OHLCV responses with injected HTTP dependencies, timeouts, bounded retries, provider-appropriate request pacing, Core raw storage, and secret-safe errors/metadata. | Y9.1, C4.2, A5.5 |
| Y9.3 | [ ] | Implement Yahoo parser | Parse Yahoo fixtures into the selected provider-native OHLCV series without adding adjusted-close or provider-specific columns to the shared tables. | Y9.1-Y9.2, A5.3-A5.4 |
| Y9.4 | [ ] | Implement Yahoo import service | Compose validation, snapshot registration, provider-series resolution, bar writes, and import summaries. Rerun tests pass. | Y9.2-Y9.3, E6.4-E6.5 |
| Y9.5 | [ ] | Build and store Yahoo report | Reuse the shared report contract for Yahoo-scoped import health, freshness, coverage, stale series, gap warnings, failures, and native adjustment notes. | Y9.4, E6.6-E6.7 |
| Y9.6 | [ ] | Add Yahoo CLI | Add an operator CLI and `bin` wrapper using `bin/env-load`; it runs controlled Yahoo import plus reporting and emits a secret-safe summary. | Y9.5, B1.8 |
| Y9.7 | [ ] | Add Yahoo daily runner | Add package-owned Yahoo sequencing with configured request bounds, Core run lifecycle, and reporting. Tests cover success, failure, and reruns. | Y9.5-Y9.6 |
| Y9.8 | [ ] | Decide and implement Yahoo DAG mode | Record whether Yahoo is scheduled, manual-only, or limited to selected symbols based on the implemented source constraints. Add the matching thin DAG and tests only when operationally justified. | Y9.7, B1.5-B1.7 |
| Y9.9 | [ ] | Verify Yahoo vertical workflow | Verify enabled DAG discovery and run the full Yahoo fixture path through reporting. Confirm lineage, secret safety, rerun behavior, and coexistence with overlapping EODData/Stooq histories. | Y9.8, M3.7 |

## Phase 10: Documentation, Verification, And Incremental Rollout

Goal: verify the complete package and move from fixture workflows to normal
provider operation one proven vertical slice at a time.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| V10.1 | [ ] | Complete package README | Document scope, provider-native semantics, `deploy/env/local.env` runtime loading, `os.environ` package boundary, secret handling, CLIs, raw retention, source snapshots, tables, DAGs/reports, and deferred bridge/enrichment work. | Y9.9, H8.8 |
| V10.2 | [ ] | Add operator runbook | Document local secret/config setup, manual runs, each provider DAG, historical Stooq import, report interpretation, raw-object inspection, reruns, and failure recovery without printing credentials. | V10.1 |
| V10.3 | [ ] | Run formatting and full package tests | Configured formatting/linting and the full `empire-stonks-ohlcv` test suite pass from the repository root. | V10.2 |
| V10.4 | [ ] | Run DB validation and regenerate docs | Repo-standard DB validation and Stonks schema documentation generation pass with no drift. | V10.2 |
| V10.5 | [ ] | Verify package, CLI, and DAG imports | Package, all CLI modules, and all enabled provider DAGs import cleanly in their actual runtime environments. | V10.3-V10.4 |
| V10.6 | [ ] | Verify raw-object cleanup | Expire and clean a test raw object and prove stored-object/membership rows are removed while source snapshot, provider listing, bars, and report remain queryable. | V10.4-V10.5 |
| V10.7 | [ ] | Run combined fixture regression | Run all three vertical slices from fixture acquisition through provider reports and prove reruns, provider isolation, secret safety, and report scoping. | V10.3-V10.6 |
| V10.8 | [ ] | Run and enable bounded EODData | Run a bounded live EODData import, inspect lineage/bars/report, then enable its nightly DAG only after results are healthy. Record the decision. | V10.7, E6.12 |
| V10.9 | [ ] | Run and enable bounded Stooq daily | Run a bounded live Stooq daily import, inspect its report and overlap with EODData, then enable its nightly DAG only after results are healthy. | V10.8, T7.9 |
| V10.10 | [ ] | Run bounded historical Stooq import | Run the defined limited historical import and verify performance, counts, rerun behavior, cleanup, and report visibility before expanding scope. | V10.9, H8.8 |
| V10.11 | [ ] | Run and enable selected Yahoo mode | Run a bounded live Yahoo import, inspect lineage/native semantics/reporting, and enable only the scheduling mode selected in Y9.8. Record the decision. | V10.10, Y9.9 |

---

## Future Bridge Gate

Do not start the bridge merely because provider-native OHLCV exists. Begin
bridge planning only when both the OHLCV contracts and the relevant canonical
security-master contracts are stable enough to support temporal mappings.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| X11.1 | [ ] | Confirm bridge readiness | Record the concrete consumers and stable OHLCV/security-master contracts that require provider-to-canonical mapping. | V10.11 plus future securities readiness |
| X11.2 | [ ] | Review provider-series identity evidence | Evaluate what market, ticker, date-range, identifier, and provider metadata is actually available after live ingestion. Do not assume ticker reuse can be detected automatically. | X11.1 |
| X11.3 | [ ] | Design temporal mapping storage | Design mappings that can attach different date ranges of one provider series to different canonical listings and multiple provider series to one listing. Preserve candidate/decision evidence and ambiguity. | X11.2 |
| X11.4 | [ ] | Decide bridge package creation | Create `empire-stonks-ohlcv-bridge` only when implemented mapping or canonical-series logic justifies a separate Python package. | X11.3 |
| X11.5 | [ ] | Design authoritative-series policy | Define explicit provider selection, fallback, validation, gap-fill, adjustment-compatibility, and provenance rules before storing or exposing one canonical OHLCV history. | X11.3-X11.4 |

---

## Expected End State After Phases 0-10

When phases 0-10 are complete, Empire should have a reusable
`empire-stonks-ohlcv` package with:

- Provider-neutral listing and daily-bar dataclasses.
- Provider-specific EODData, Stooq, and Yahoo acquisition/parsing modules.
- Provider-native daily histories stored independently in
  `stonks.ohlcv_daily`.
- Idempotent current-state imports and update counts.
- Durable provider-source content identity after short-lived raw objects expire.
- One controlled historical Stooq import path.
- Thin nightly Airflow DAGs for the providers that are operationally enabled.
- JSON health reports for ingestion counts, freshness, stale series, coverage,
  and non-calendar-aware gap warnings.
- Tests proving provider isolation, rerun safety, cleanup-safe Core object and
  snapshot integration, and runtime imports.

What should be considered done and authoritative:

- Each stored row is the current value imported for one provider-native series
  and trading date.
- The provider, exact native market text, and exact native ticker are traceable
  from each row. Adjustment semantics remain in provider source contracts and
  reports; source snapshots and import runs are not linked per row.
- Reprocessing the same input does not duplicate provider listings or bars.
- Providers can disagree without overwriting one another.

What should still be considered not done:

- Proof that a provider market/ticker series represents one real-world listing
  throughout its history.
- Detection of ticker reuse, exchange transfers, or corporate successors from
  OHLCV input alone.
- Mapping provider listings to canonical `stonks.listing` rows.
- Cross-provider adjustment normalization, price consensus, or silent merging.
- A canonical or authoritative OHLCV history.
- Intraday bars, extended-hours variants, multiple stored series variants, or a
  market calendar.
- Sector, industry, fundamentals, Finviz enrichment, or other non-OHLCV data.
- Append-only provider bar revision history or a packaged manual-correction
  workflow.

This end state is sufficient to accumulate useful daily and historical
provider-native data now while preserving a clean path to temporal canonical
mapping later.
