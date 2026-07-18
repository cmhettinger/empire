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
active checklist focused. Phases 0-6 are currently archived there;
their task IDs remain valid dependencies for active work.

## Phase 7: Historical Stooq Import

Goal: provide a safe operator-run historical import from an operator-supplied
Stooq source file, with its own progress and coverage reporting, without adding
canonical identity assumptions or automating Stooq's browser-verification
challenge. Stooq currently requires an API key obtained through an interactive
CAPTCHA, and its download pages may require JavaScript to verify the browser.
Automated Stooq daily access is therefore deferred to Phase 10 and may in fact
never be built.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| H7.1 | [x] | Define historical import inputs and bounds | Document supported operator-supplied Stooq historical source files, manual acquisition boundary, environment settings, date bounds, symbol/market filters, expected volume, restart behavior, and explicit exclusions. The package does not automate CAPTCHA or browser verification. | E6.13, A5.1-A5.2 |
| H7.2 | [x] | Add streaming/chunked historical parser | Parse historical input without loading the entire dataset into memory. Tests prove the documented Stooq format, stable chunk boundaries, and equivalent results across chunk sizes. | H7.1, A5.3-A5.4 |
| H7.3 | [x] | Add chunked database writer | Write provider listings and bars in bounded transactions with cumulative inserted/updated/unchanged/derived-updated/failure counts. A failed chunk can be rerun safely. | H7.2, M3.4-M3.5 |
| H7.4 | [x] | Add historical import run tracking | Start one Core run with explicit non-secret parameters and progress summaries; retain the operator-supplied input through the normal source-snapshot and raw-object policy. Failure leaves enough context for an operator rerun. | H7.3, C4.3-C4.6 |
| H7.5 | [x] | Add historical import report | Build and store a Stooq backfill report with input bounds, chunk progress, write counts, resulting coverage, failures, warnings, and native-semantics notes. Tests cover partial and successful runs. | H7.4, E6.7-E6.8 |
| H7.6 | [x] | Add historical Stooq CLI | Add `stonks-ohlcv-stooq-backfill` using `bin/env-load`, with an explicit local input path plus date/filter/chunk options and a secret-safe JSON summary. It does not download from Stooq or mutate canonical tables. | H7.5, B1.8 |
| H7.7 | [x] | Add historical fixture vertical test | Import a multi-symbol, multi-date fixture twice, store its report, and prove stable provider-listing IDs, unchanged second-run counts, correct date ranges, and bounded transactions. | H7.6 |
| H7.8 | [x] | Run bounded development backfill | Manually obtain a source file, run a deliberately small local/dev date-and-symbol range using `deploy/env/local.env`, inspect performance/counts/reporting, and record the acquisition date, command, and result before any broad import. | H7.7 |

Done: 2026-07-18 — added
`docs/stonks/ohlcv-stooq-history-source-contract.md` with the manual
`d_us_txt.zip`/Core boundary, exact US stock layout and identities, date and
market/ticker filters, decimal OHLCV semantics, observed 9,598-file/1.36 GB
selected volume, streaming/progress/restart rules, and explicit exclusions;
aligned the architecture and package README. The supplied 537,380,289-byte ZIP
passed integrity validation; focused source/fixture policy tests passed (6), and
counts, representative rows, SHA-256, documentation links/consistency, Markdown
fences, and `git diff --check` passed.

Done: 2026-07-18 — added the public one-shot streaming parser and typed scope,
discovery, chunk, per-market count, and summary records in
`empire_stonks_ohlcv/stooq_history.py`; added a manifested Stooq member fixture,
shared parser-contract coverage, deterministic recursive discovery, exact
market/ticker/date filtering, decimal/fractional-volume parsing, bounded ZIP and
issue handling, duplicate/rejection accounting, stable chunk-boundary tests,
and public exports/README guidance. Focused tests passed (20); the full package
suite passed (340, 12 environment-dependent skips). A bounded live-archive
smoke test selected `AACB.US`, emitted five bars as `[2, 2, 1]`, filtered 218,
and rejected zero. Poetry lock/check/build, compileall, pip check, public import,
88-column scan, secret-pattern scan, and `git diff --check` passed.

Done: 2026-07-18 — added `StooqHistoryChunkWriter` with one independent commit
per sequential parser chunk, distinct listing resolution across split batches,
inactive-series skipping, shared daily-bar upserts, rollback-safe failures, and
bounded typed per-chunk/cumulative JSON-ready counts. Failed chunk numbers stay
retryable while later chunks cannot leapfrog them. Unit tests cover commits,
aggregation, inactive bars, safe failure details, rollback accounting, retry,
ordering, and connection validation. The PostgreSQL integration test proved
earlier commits survive a failed chunk, failed writes leave no residue,
derived-only repair is counted, retry succeeds, and a full replay is unchanged.
Focused tests passed (10, 1 environment skip), the full package suite passed
(346, 13 environment skips), and the live database integration test passed.
Poetry check, compileall, pip check, public import, 88-column scan, and
`git diff --check` passed.

Done: 2026-07-18 — added the public CLI-oriented
`run_stooq_history_backfill()` lifecycle with one heartbeat-enabled Core run,
explicit safe scope/chunk/storage parameters, non-moving raw ZIP retention,
streaming from Core's validated `raw.zip` path, checksum source-snapshot
registration, sequential chunk persistence, and JSON-ready success/failure
summaries. Parser progress is now typed and emitted after discovery, every 100
completed members, and every chunk commit; partial failures retain acquired
object identity, exact rerun scope, parse position, cumulative write/failure
counts, and last committed chunk without exception details. Added reusable Core
`ObjectStore.get_path()` for bounded filesystem-backed streaming. Unit tests
cover success sequencing, raw-copy ownership, safe parameters/progress,
heartbeats, failure recovery context, pre-run validation, and 100-file progress.
PostgreSQL integration proved the Core run, raw object, snapshot membership,
listing/bar writes, heartbeat, and stored summary. Core tests passed (29); the
OHLCV suite passed (350, 14 environment skips); live H7.3/H7.4 database tests
passed (2). Poetry checks, dependency checks, compileall, public import,
88-column scan, and `git diff --check` passed.

Done: 2026-07-18 — added the public Stooq historical JSON report builder,
deterministic serializer, scoped coverage query, typed market/series coverage
records, and durable Core report storage. Reports capture exact input bounds,
archive/snapshot identity, complete or partial parser state, chunk/write counts,
elapsed time, last committed chunk, persisted versus requested-date coverage,
bounded series and issue samples, safe failures/warnings, and native adjustment,
volume, currency, corporate-action, and canonical-identity notes. The H7.4
runner now stores PASS/WARN reports before successful completion and
best-effort partial FAIL reports before failed Core runs close; summaries and
successful return values include report identity/outcome. Coverage aggregation
is provider/market/ticker scoped, with only the bounded sample set receiving
series-level aggregation. Unit tests cover complete, warning, partial failure,
coverage SQL bounds, deterministic JSON, durable storage, and runner wiring.
PostgreSQL integration proved both complete and failed-chunk partial reports,
durable object contents, safe Core summaries, and partial database coverage.
The OHLCV suite passed (353, 15 environment skips); both live H7.5 database
paths passed. Poetry checks, dependency checks, compileall, public import,
88-column scan, and `git diff --check` passed.

Done: 2026-07-18 — added the package and executable
`stonks-ohlcv-stooq-backfill` operator entry points with `bin/env-load`, a
required existing local `d_us_txt.zip`, explicit acquisition date, optional
inclusive trading-date bounds, repeatable exact market/ticker filters, and a
bounded chunk option. The initial 50,000-bar default follows the supplied prior
implementation's row batch and is capped at 100,000 pending H7.8 performance
validation. Arguments and scope are rejected before database connection;
package progress is emitted as secret-safe JSON lines on stderr while stdout is
reserved for one final JSON result. Runtime failures expose only a fixed safe
message. No downloader, browser automation, DAG, or canonical-table path was
added. CLI tests passed (16); the full package suite passed (369, 15
environment-dependent skips). Wrapper syntax/help, Poetry check, dependency
check, compileall, public CLI import, 88-column changed-file scan, and
`git diff --check` passed.

Done: 2026-07-18 — added manifested NYSE and NYSE MKT historical members and a
PostgreSQL vertical test that builds one bounded three-market ZIP from those
members plus the existing Nasdaq fixture. The test imports the same six-bar,
three-symbol, multi-date scope twice through the complete package runner. It
proves distinct Core runs/raw objects/reports reuse one checksum snapshot,
provider-listing UUIDs and per-series date ranges remain stable, and the second
run records three unchanged listings and six unchanged bars with no inserts,
updates, or derived repairs. Instrumentation proves six two-row bar writes and,
per run, exactly one snapshot commit plus three independently committed chunks.
Both stored PASS reports reproduce the exact scope, write outcomes, and market
coverage. Fixture-policy tests passed (3); the live H7.7 PostgreSQL test passed
(1). The full package suite passed (369, 16 environment-dependent skips).
Poetry check, dependency check, compileall, changed-file line-length scan, and
`git diff --check` passed.

Done: 2026-07-18 — completed the bounded development rehearsal with the real
operator-supplied archive and the real CLI. The archive was acquired and
inspected on 2026-07-18; it was 537,380,289 bytes with SHA-256
`faf932285b47ae216461345e7bac7a1085d210cbddd2f02f8a575ab47ff50435`.
The wrapper loaded its default `deploy/env/local.env` and the exact command was:

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

The CLI succeeded as Core run
`1c948ab4-e075-4b75-be96-4fce8f2c2afb`. Archive acquisition progress arrived
at 0.274 seconds, selected-member discovery at 0.358 seconds, the database run
completed in 0.406 seconds, and CLI wall time was 0.75 seconds. The parser
discovered and completed one file, read 223 rows, date-filtered 218, accepted
five, and rejected none. One actual five-row transaction completed under the
50,000-row configured maximum; it inserted one provider listing and five bars
with no updates, unchanged rows, derived repairs, inactive skips, failed
chunks, duplicates, or warnings. This validates the initial default on the
bounded path but is not a 50,000-row capacity benchmark; a broad run must still
be monitored through its per-chunk progress.

The stored source snapshot is
`9b045178-22e7-4e43-aa45-94a21b71990d`, backed by raw object
`576ff9c8-ebf1-4d8d-99f0-c30b4088aa66`. Durable PASS report
`a33a34ce-8775-420a-8ee3-5cb73fc3105d` records complete status, zero warnings
and hard failures, one active `nasdaq/AACB.US` series, five persisted/scoped
bars, exact coverage from 2025-04-07 through 2025-04-11, and
`canonical_identity_mutation=false`. Database inspection matched all five
provider OHLCV rows and the report's listing UUID
`7f83335f-6368-4c0e-95bf-7ad6e39b33ab`. The retained raw object remains under
the normal expiration policy; the report and source snapshot remain durable.

Follow-up: 2026-07-18 — added a professional Stooq historical backfill PDF
companion after Phase 7 completion, matching the shared Empire letter-format
branding used by the EODData daily report. The package renderer converts both
complete and partial schema-version-2 Stooq JSON reports into an executive
summary, exact run scope, coverage, parser/write results, lineage,
warning/failure, and native-semantics sections. The runner now stores durable
`report.json` and `report.pdf` objects, and exposes both IDs in Core summaries
and successful CLI output. JSON remains authoritative for the complete bounded
sample. Unit tests cover rendering, metadata, Core storage, success wiring, and
partial reports; PostgreSQL tests cover successful, failed-chunk, and replay
storage. The real H7.8 JSON report was rendered to
`output/pdf/stooq-history-backfill-report.pdf` and all four pages passed visual
inspection after Poppler rendering.

## Phase 8: Yahoo Daily End-To-End Vertical Slice

Goal: add Yahoo acquisition, persistence, reporting, and the intentionally
selected scheduling mode while keeping non-OHLCV Yahoo data out of the package.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| Y8.1 | [ ] | Document Yahoo source and config contract | Record the chosen OHLCV endpoint/source, `EMPIRE_STONKS_OHLCV_YAHOO_*` settings, request inputs, market/ticker fields, native daily/adjusted semantics, rate/error behavior, and explicit exclusion of enrichment. Runtime values come from `deploy/env/local.env`. | H7.8, A5.1-A5.2 |
| Y8.2 | [ ] | Implement Yahoo acquisition | Acquire Yahoo OHLCV responses with injected HTTP dependencies, timeouts, bounded retries, provider-appropriate request pacing, Core raw storage, and secret-safe errors/metadata. | Y8.1, C4.2, A5.5 |
| Y8.3 | [ ] | Implement Yahoo parser | Parse Yahoo fixtures into the selected provider-native OHLCV series without adding adjusted-close or provider-specific columns to the shared tables. | Y8.1-Y8.2, A5.3-A5.4 |
| Y8.4 | [ ] | Implement Yahoo import service | Compose validation, snapshot registration, provider-series resolution, bar writes, and import summaries. Rerun tests pass. | Y8.2-Y8.3, E6.5-E6.6 |
| Y8.5 | [ ] | Build and store Yahoo report | Reuse the shared report contract for Yahoo-scoped import health, freshness, coverage, stale series, gap warnings, failures, and native adjustment notes. | Y8.4, E6.7-E6.8 |
| Y8.6 | [ ] | Add Yahoo CLI | Add an operator CLI and `bin` wrapper using `bin/env-load`; it runs controlled Yahoo import plus reporting and emits a secret-safe summary. | Y8.5, B1.8 |
| Y8.7 | [ ] | Add Yahoo daily runner | Add package-owned Yahoo sequencing with configured request bounds, Core run lifecycle, and reporting. Tests cover success, failure, and reruns. | Y8.5-Y8.6 |
| Y8.8 | [ ] | Decide and implement Yahoo DAG mode | Record whether Yahoo is scheduled, manual-only, or limited to selected symbols based on the implemented source constraints. Add the matching thin DAG and tests only when operationally justified. | Y8.7, B1.5-B1.7 |
| Y8.9 | [ ] | Verify Yahoo vertical workflow | Verify enabled DAG discovery and run the full Yahoo fixture path through reporting. Confirm lineage, secret safety, rerun behavior, and coexistence with overlapping EODData and historical Stooq data. | Y8.8, M3.7 |

## Phase 9: Documentation, Verification, And Incremental Rollout

Goal: verify the package without scheduled Stooq acquisition and move from
fixture workflows to normal provider operation one proven path at a time.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| V9.1 | [ ] | Complete package README | Document scope, provider-native semantics, `deploy/env/local.env` runtime loading, `os.environ` package boundary, secret handling, CLIs, raw retention, source snapshots, tables, enabled DAGs/reports, the manual Stooq backfill boundary, and deferred bridge/enrichment work. | Y8.9, H7.8 |
| V9.2 | [ ] | Add operator runbook | Document local secret/config setup, manual runs, each enabled provider DAG, historical Stooq file acquisition/import, report interpretation, raw-object inspection, reruns, and failure recovery without printing credentials. | V9.1 |
| V9.3 | [ ] | Run formatting and full package tests | Configured formatting/linting and the full `empire-stonks-ohlcv` test suite pass from the repository root. | V9.2 |
| V9.4 | [ ] | Run DB validation and regenerate docs | Repo-standard DB validation and Stonks schema documentation generation pass with no drift. | V9.2 |
| V9.5 | [ ] | Verify package, CLI, and DAG imports | Package, all CLI modules, and all enabled provider DAGs import cleanly in their actual runtime environments. | V9.3-V9.4 |
| V9.6 | [ ] | Verify raw-object cleanup | Expire and clean a test raw object and prove stored-object/membership rows are removed while source snapshot, provider listing, bars, and report remain queryable. | V9.4-V9.5 |
| V9.7 | [ ] | Run combined fixture regression | Run EODData, operator-supplied historical Stooq, and Yahoo fixture paths through provider reports and prove reruns, provider isolation, secret safety, and report scoping. | V9.3-V9.6 |
| V9.8 | [ ] | Run and enable bounded EODData | Run a bounded live EODData import, inspect lineage/bars/report, then enable its nightly DAG only after results are healthy. Record the decision. | V9.7, E6.13 |
| V9.9 | [ ] | Run bounded historical Stooq import | Run the defined limited historical import and verify performance, counts, rerun behavior, cleanup, and report visibility before expanding scope. | V9.8, H7.8 |
| V9.10 | [ ] | Run and enable selected Yahoo mode | Run a bounded live Yahoo import, inspect lineage/native semantics/reporting, and enable only the scheduling mode selected in Y8.8. Record the decision. | V9.9, Y8.9 |
| V9.11 | [ ] | Audit derived daily-bar consistency | Recompute expected `change` and `changepct` from each provider listing's nearest preceding stored bar and compare them with every `ohlcv_daily` row, covering first rows, zero predecessor closes, gaps, corrections, and out-of-order imports. Report bounded discrepancy counts and samples by provider and market. If discrepancies exist, identify the cause and add a tested, bounded, idempotent repair command or workflow; if none exist, record the evidence and do not add a scheduled mutation task. | V9.10, H7.8 |

## Phase 10: Stooq Daily End-To-End Vertical Slice

Goal: revisit Stooq daily acquisition only after the rest of the package is
operational, and add unattended ingestion only if Stooq provides a stable,
authorized machine-download path that does not depend on browser-challenge
automation.

T10.1 is a decision gate. A documented manual-only or defer decision completes
this phase without starting T10.2-T10.10; those implementation tasks remain
deferred until the source conditions change. A go decision continues through
T10.10.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| T10.1 | [ ] | Gate Stooq daily automation | Document current Stooq API-key enrollment, terms and rate expectations, secret handling, CSV format, and browser-verification behavior. Manually enroll if appropriate, then prove whether a key-authenticated endpoint works from a clean non-browser HTTP client without cookies or challenge circumvention. Record a go, manual-only, or defer decision. | V9.11, H7.1 |
| T10.2 | [ ] | Implement Stooq daily acquisition when approved | If T10.1 approves unattended use, acquire the selected daily source through the documented interface and store it through the Core object/snapshot flow. Tests cover success, retryable failure, challenge/error content, and secret-safe diagnostics. Do not add headless-browser, CAPTCHA-solving, or challenge-bypass code. | T10.1, C4.2, A5.5 |
| T10.3 | [ ] | Implement Stooq daily parser | Parse documented Stooq daily fixtures into shared records without EODData-specific persistence branches. Shared parser-contract tests pass. Reuse historical parsing only where the evidenced formats genuinely match. | T10.1-T10.2, H7.2, A5.3-A5.4 |
| T10.4 | [ ] | Implement Stooq daily import service | Compose validation, snapshot registration, provider-listing writes, bar upserts, and import summaries. Reruns are idempotent. | T10.2-T10.3, E6.5-E6.6 |
| T10.5 | [ ] | Build and store Stooq daily report | Reuse the shared health/report contract for Stooq-scoped freshness, coverage, stale series, gap warnings, failures, and native-semantics notes. Tests prove provider scoping and stored report paths. | T10.4, H7.5 |
| T10.6 | [ ] | Add Stooq daily CLI | Add an operator CLI and `bin` wrapper using `bin/env-load`; it runs Stooq daily import plus reporting and emits a secret-safe JSON summary. | T10.5, B1.8 |
| T10.7 | [ ] | Add Stooq daily runner | Add package-owned Stooq sequencing with Core run lifecycle and reporting. Tests cover success, failure, challenge responses, and reruns. | T10.5-T10.6 |
| T10.8 | [ ] | Decide and implement Stooq DAG mode | Select scheduled, manual-only, or limited-symbol operation based on the approved interface and implemented source constraints. Add a thin scheduled DAG only when operationally justified; never add a browser-dependent DAG. Tests cover whichever go-path mode is selected. | T10.7, B1.5-B1.7 |
| T10.9 | [ ] | Verify Stooq daily vertical workflow | Verify any enabled DAG discovery and run the full Stooq daily fixture path through reporting. Confirm lineage, report rows, secret safety, rerun behavior, and isolation from EODData, Yahoo, and historical Stooq imports. | T10.8, M3.7 |
| T10.10 | [ ] | Run bounded Stooq daily and finalize docs | Run a bounded live import and enable any selected DAG only after healthy results. Update the README and runbook with the decision and exact operational boundary. | T10.9 |

---

## Future Bridge Gate

Do not start the bridge merely because provider-native OHLCV exists. Begin
bridge planning only when both the OHLCV contracts and the relevant canonical
security-master contracts are stable enough to support temporal mappings.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| X11.1 | [ ] | Confirm bridge readiness | Record the concrete consumers and stable OHLCV/security-master contracts that require provider-to-canonical mapping. | V9.11, completed T10.1 gate decision, plus future securities readiness |
| X11.2 | [ ] | Review provider-series identity evidence | Evaluate what market, ticker, date-range, identifier, and provider metadata is actually available after live ingestion. Do not assume ticker reuse can be detected automatically. | X11.1 |
| X11.3 | [ ] | Design temporal mapping storage | Design mappings that can attach different date ranges of one provider series to different canonical listings and multiple provider series to one listing. Preserve candidate/decision evidence and ambiguity. | X11.2 |
| X11.4 | [ ] | Decide bridge package creation | Create `empire-stonks-ohlcv-bridge` only when implemented mapping or canonical-series logic justifies a separate Python package. | X11.3 |
| X11.5 | [ ] | Design authoritative-series policy | Define explicit provider selection, fallback, validation, gap-fill, adjustment-compatibility, and provenance rules before storing or exposing one canonical OHLCV history. | X11.3-X11.4 |

---

## Expected End State After Phases 0-10

When phases 0-10 are complete, Empire should have a reusable
`empire-stonks-ohlcv` package with:

- Provider-neutral listing and daily-bar dataclasses.
- Provider-specific EODData and Yahoo daily acquisition/parsing modules, a
  Stooq historical-file parser, and Stooq daily acquisition only if T10.1
  approves a sustainable machine-download path.
- Provider-native daily histories stored independently in
  `stonks.ohlcv_daily`.
- Idempotent current-state imports and update counts.
- Durable provider-source content identity after short-lived raw objects expire.
- One controlled historical Stooq import path.
- Thin Airflow DAGs for the provider modes that are operationally enabled;
  Stooq daily may remain manual-only or deferred if its automation gate fails.
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
