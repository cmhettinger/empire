# Technical Indicators Package Action Plan

This document tracks the implementation roadmap for provider-native daily
technical indicators in Empire Stonks.

The first implementation creates a reusable `empire-stonks-technicals` package
that reads `stonks.ohlcv_daily`, calculates versioned daily analytical
features, and stores current state in `stonks.ohlcv_daily_technicals`. It does
not put calculation logic in the OHLCV package, DAGs, reports, or strategies.

The rollout proves one manageable, testable layer at a time: contracts,
runtime dependencies, schema, inputs, calculation families, persistence,
reports, runners, CLIs, Airflow coordination, and bounded release.

## Starting A Task In A New Codex Chat

Copy this prompt and replace `<TASK_ID>` with the task to complete.

```text
Complete task <TASK_ID> from docs/todo/tech-ind-task-plan.md.

Before changing code, read AGENTS.md, the full active plan and archive, and the
full docs/stonks/technical-indicators-design-contract.md. Also read the OHLCV
plans/source contracts required by the task. Inspect the live repository and
completed prerequisite Done: notes; do not assume the plan is newer than the
implementation.

Implement only the named task and necessary integration points. Follow Empire
package, database, Core, reporting, environment, CLI, and Airflow conventions.
Run the focused formatting, tests, imports, DB validation, report rendering,
CLI smoke, or Airflow validation appropriate to the task. Fix failures caused
by the work. Mark the task [x] and add a terse dated Done: note with key files
and exact verification. If blocked, leave it unchecked and report the blocker
instead of weakening completion criteria.
```

## Package Boundary

`empire-stonks-technicals` owns chronological OHLCV reads, benchmark
resolution, TA-Lib/NumPy calculation adapters, versioned formulas, numerical
validation, affected-range planning, current-state persistence, daily and
backfill runners, feature/coverage queries, JSON/PDF run reports, and thin CLI
entrypoints.

It does not own provider ingestion, OHLCV mutation, canonical identity,
corporate-action normalization, strategy thresholds, target selection,
portfolio/backtest execution, point-in-time sector mappings, intraday
indicators, or Airflow business logic. `empire-stonks-ohlcv` stays upstream and
must not import technicals.

## Required Design Baseline

The agreed table shape, feature inventory, formula direction, generated-versus
Python ownership, validation split, SPX identity, index philosophy, operational
surfaces, deferred indicators, and narrowly scoped open decisions are preserved
in the
[daily technical indicators design contract](../stonks/technical-indicators-design-contract.md).

Implementation tasks refine and prove that baseline. They must not restart the
indicator-selection or table-design discussion without new evidence and an
explicit contract update.

```text
empire-stonks-ohlcv -> stonks.ohlcv_daily
    -> empire-stonks-technicals -> stonks.ohlcv_daily_technicals
    -> reports / screens / future backtests
```

## Initial Persistence And Calculation Contract

`stonks.ohlcv_daily_technicals` has one current row per
`(provider_listing_id, trading_date)` with an owning FK to `ohlcv_daily`. Rows
remain provider-native. The read-optimized table copies OHLCV so ordinary
screens need no source join, stores historical/cross-series outputs calculated
in Python, and may use `STORED` generated columns for cheap same-row formulas.

Analytical values normally use `DOUBLE PRECISION`; copied source values remain
exact `NUMERIC`. Percentage fields store ratios (`0.05` means 5 percent).
Python, as the only normal writer, strictly validates finite values, formulas,
warm-up nullability, and benchmark semantics. PostgreSQL retains keys, FKs,
basic bounds, and row-shape invariants rather than an exhaustive float check.

The table stores current calculated state, not revision history. Unchanged
reruns are idempotent. Source, SPX, and calculation-version changes trigger
tested affected-range recalculation. A calculation-state table is allowed only
if the recursive-equivalence prototype proves it necessary.

Lookbacks count chronological observations, never future rows. TA-Lib warm-up
and unstable periods are versioned; non-finite output becomes null, never zero.
Subject/SPX observations align by exact date without forward fill. Adjustment
semantics remain provider-native and are disclosed. Backtest consumers still
own point-in-time universes, survivorship, execution timing, slippage, and
transaction costs.

## Version-1 Feature Families

- Source and state: OHLCV, dollar volume, observation count, up/down streaks.
- Returns: 1/2/3/5/10/20/63/126/252 observations.
- Bar structure: gap, intraday return, range percentage, close location.
- Trend: SMA 20/50/200; EMA 12/20/26/50; price/average distances;
  cross-distances; 20-observation SMA 50/200 changes.
- Range: 20/50/252 highs, 20/50 lows, and close distances.
- Momentum/volatility: RSI 14, ATR 14/percentage, 20/60 return volatility,
  1d/3d 20-observation z-scores.
- Bollinger: 20-observation price deviation, `%b`, and BandWidth; redundant
  upper/lower bands are not stored.
- Directional movement: +DI 14, -DI 14, and ADX 14.
- MACD: 12/26/9 line, signal, histogram, and normalized line/histogram.
- Volume: 20/60 average volume, 20 average dollar volume, relative volume 20.
- SPX: price ratio and 20/50 trend, 20/63/126/252 relative returns, and
  60/252 beta and correlation using `YAHOO/XIDX/SPX`.

Strategy booleans, thresholds, sector-relative features, and the remaining
TA-Lib catalog are deferred until a concrete consumer justifies them.

## Run, Report, And Runtime Contract

Every substantive daily/backfill run creates durable `report.json` and
professional Empire-branded `report.pdf`. They cover run scope, versions,
source readiness, feature/benchmark coverage, writes, warm-up/null state,
performance, warnings, and bounded diagnostics without recommendations or
full feature payloads.

Reusable code reads only `os.environ` and receives injected database/Core
services. Runtimes own environment loading. Airflow is orchestration only.

## How To Use This Checklist

Status values are `[ ]` not started, `[~]` in progress, and `[x]` complete.
Add a dated `Done:` note below the phase when completing a task. Move only fully
completed phases to the
[technical indicators action plan archive](tech-ind-task-plan-archive.md).

## Completed Phase Archive

No phases are archived yet. Completed phases and their `Done:` notes will move
to the archive while preserving their task IDs as valid dependencies.

---

## Phase 0: Freeze Scope And Calculation Contracts

Goal: turn the agreed feature set into exact, testable contracts before schema
or calculation code is committed.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| P0.1 | [ ] | Ratify the design contract | Audit the existing design contract against live OHLCV/Core/reporting conventions, resolve contradictions without reopening settled scope, and mark it as the authoritative V1 baseline. | — |
| P0.2 | [ ] | Freeze naming conventions | Select package/import, table/state-table, calculation version, Core jobs, storage keys, object kinds, report IDs, CLI names, and DAG ID. | P0.1 |
| P0.3 | [ ] | Freeze feature profile V1 | Convert the contract inventory into the exact persisted/generated/query-time profile, resolving only its named open units, nullability, and ownership decisions. | P0.1 |
| P0.4 | [ ] | Freeze formula semantics | Turn the contract formulas into executable specifications and resolve its named volatility, z-score, TA-Lib warm-up, tolerance, and denominator decisions. | P0.3 |
| P0.5 | [ ] | Define SPX contract | Define `YAHOO/XIDX/SPX` resolution, eligible subjects, exact alignment, relative return, beta/correlation, complete windows, and unavailable behavior. | P0.3-P0.4 |
| P0.6 | [ ] | Define source-value policy | Audit EODData, Stooq, and Yahoo adjustment/corporate-action semantics and select initially eligible provider listings without claiming normalization. | P0.1, OHLCV V10.11 |
| P0.7 | [ ] | Define recalculation semantics | Specify daily append, missing row, source correction, SPX correction, version change, inactive listing, and deletion behavior with full/incremental equivalence. | P0.4-P0.6 |
| P0.8 | [ ] | Set performance and release gates | Record representative sizes, daily/backfill timing and memory targets, query-plan expectations, report bounds, and live rollout criteria. | P0.3-P0.7 |

---

## Phase 1: Prove Dependencies And Scaffold The Package

Goal: establish an independently importable package and prove TA-Lib works in
every runtime before building around it.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| B1.1 | [ ] | Prove TA-Lib runtime support | Pin a reviewed TA-Lib/NumPy combination and prove local Poetry and Airflow-image installation/import. Record wheel/native-library behavior, license, Python compatibility, and rollback. | P0.4, P0.8 |
| B1.2 | [ ] | Prototype recursive equivalence | Compare full-series output with append and historical-correction suffix strategies for EMA, RSI, ATR, ADX, and MACD. Decide whether exact updates require state, bounded replay, or full replay. | B1.1, P0.7 |
| B1.3 | [ ] | Scaffold Poetry package | Create `packages/empire-stonks-technicals` version `0.1.0` with `src/` layout, README, tests, minimum dependencies, isolated import, lock, and build. | B1.1 |
| B1.4 | [ ] | Add exceptions and exports | Add a small public exception hierarchy and explicit API without exposing TA-Lib or persistence internals. | B1.3 |
| B1.5 | [ ] | Add environment config | Add environment-only typed config for version, benchmark, batches, storage key, and limits; package code never loads `.env`. | P0.2, B1.3 |
| B1.6 | [ ] | Add typed base models | Add immutable source-bar, feature-row, scope, benchmark, issue, count, summary, and run-result models with bounded JSON-ready forms. | P0.3-P0.7, B1.4 |
| B1.7 | [ ] | Install in Airflow image | Install in dependency-safe order and prove technicals, TA-Lib, NumPy, Core, and OHLCV imports coexist in the built image. | B1.1, B1.3 |
| B1.8 | [ ] | Add runtime settings plumbing | Add non-secret example/local settings and Compose passthrough without embedding configuration in images or DAGs. | B1.5, B1.7 |

---

## Phase 2: Implement The Database Contract

Goal: create the smallest durable schema supporting fast current-state reads
and the proven incremental strategy.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| S2.1 | [ ] | Finalize main-table columns | Translate the design-contract baseline into exact PostgreSQL names, types, generated expressions, nullability, copied OHLCV, metadata, and comments; every column has one formula owner. | P0.3-P0.7, B1.2 |
| S2.2 | [ ] | Decide recurrence-state schema | Based on B1.2, explicitly reject or design minimal calculation-state storage. Do not add generic state without demonstrated need. | B1.2, S2.1 |
| S2.3 | [ ] | Finalize keys and constraints | Define PK/source FK, benchmark/Core FKs, delete actions, version checks, basic bounds, streak/relative row shape, and Python-owned validation boundary. | S2.1-S2.2 |
| S2.4 | [ ] | Design initial indexes | Use representative latest-date scans, listing history, backfill, rankings, and correction queries to select minimal indexes with `EXPLAIN` evidence. | P0.8, S2.1-S2.3 |
| S2.5 | [ ] | Add Flyway migration | Create `ohlcv_daily_technicals`, any proven state table, comments, constraints, and indexes; migrate and validate successfully. | S2.1-S2.4 |
| S2.6 | [ ] | Add schema contract tests | Add rollback-only SQL tests for keys, cascades, generated formulas, warm-up nulls, bounds, benchmark dependencies, duplicates, and valid rows. | S2.5 |
| S2.7 | [ ] | Add OHLCV regression | Prove no provider-identity, provider-isolation, source-cleanup, or existing-writer regression. | S2.5-S2.6 |
| S2.8 | [ ] | Add database documentation group | Add technical tables to Stonks docs, regenerate schema/ERD/diagrams, and verify no stale artifacts. | S2.5-S2.7 |

---

## Phase 3: Build Input, Scope, And Readiness Services

Goal: provide deterministic chronological inputs and explicit source readiness
without coupling calculations to source runners or Airflow.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| I3.1 | [ ] | Add eligible-listing queries | Implement provider/market/type/status/date selection from P0.6; cover active, inactive, insufficient-history, and explicit selections. | P0.6, B1.6, S2.5 |
| I3.2 | [ ] | Add chronological bar reader | Stream/page exact OHLCV in listing/date order without whole-universe memory load; cover null volume, gaps, negative-capable values, and ordering. | I3.1 |
| I3.3 | [ ] | Add SPX resolver | Resolve exactly one reviewed active `YAHOO/XIDX/SPX` and fail closed on missing, duplicate, inactive, or metadata drift. | P0.5, I3.1 |
| I3.4 | [ ] | Add benchmark bar reader | Load exact-date SPX history for ratio, relative return, beta, and correlation without forward fill. | I3.2-I3.3 |
| I3.5 | [ ] | Add state-comparison queries | Detect missing rows, copied-source drift, version drift, and earliest changed dates needed by recalculation. | P0.7, S2.5, I3.2 |
| I3.6 | [ ] | Add source-readiness decision | Decide effective-date readiness from OHLCV/SPX coverage and successful source evidence where required, not wall-clock ordering alone. | P0.5-P0.7, I3.3-I3.5 |
| I3.7 | [ ] | Verify large-read behavior | Exercise query plans, paging, transaction ownership, cancellation, and memory bounds at representative size. | P0.8, I3.1-I3.6 |

---

## Phase 4: Implement Deterministic Core Features

Goal: calculate non-TA-Lib features as pure, independently tested operations.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| C4.1 | [ ] | Normalize calculation arrays | Convert ordered source values to contiguous arrays with null masks and no silent reorder, zero fill, or look-ahead. | B1.6, I3.2 |
| C4.2 | [ ] | Calculate returns | Implement 1/2/3/5/10/20/63/126/252-observation returns with agreed zero-denominator and warm-up behavior. | P0.4, C4.1 |
| C4.3 | [ ] | Calculate bar structure | Implement gap, intraday return, range, close location, dollar volume, and copied source values; cover zero range and null volume. | P0.4, C4.1 |
| C4.4 | [ ] | Calculate range relationships | Implement 20/50/252 highs and 20/50 lows without forward leakage. | P0.4, C4.1 |
| C4.5 | [ ] | Calculate volume and liquidity | Implement 20/60 average volume and 20 average dollar volume with missing-volume and complete-window rules. | P0.4, C4.1, C4.3 |
| C4.6 | [ ] | Calculate streak state | Implement up/down streaks with unchanged close resetting both; prove append/rebuild equivalence. | P0.4, C4.1 |
| C4.7 | [ ] | Calculate return statistics | Implement 20/60 return volatility and defined 1d/3d 20-observation z-scores with zero-variance behavior. | P0.4, C4.1-C4.2 |
| C4.8 | [ ] | Add core golden fixtures | Compare independent formulas, trustworthy legacy examples, gaps, discontinuities, short histories, and randomized invariants. | C4.2-C4.7 |

---

## Phase 5: Implement TA-Lib Feature Families

Goal: expose reviewed TA-Lib calculations through stable Empire contracts with
explicit warm-up and version semantics.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| T5.1 | [ ] | Add TA-Lib adapter | Accept normalized arrays, record library/version, convert non-finite warm-up output to null masks, and hide TA-Lib types. | B1.1-B1.2, C4.1 |
| T5.2 | [ ] | Calculate SMA and EMA | Implement SMA 20/50/200 and EMA 12/20/26/50 with agreed initialization and full/incremental equivalence. | P0.4, T5.1 |
| T5.3 | [ ] | Calculate average changes | Implement 20-observation SMA 50/200 changes and inputs for generated price/average distances. | C4.2, T5.2 |
| T5.4 | [ ] | Calculate RSI and ATR | Implement Wilder RSI 14 and ATR 14 with independent references and correction replay. | P0.4, T5.1 |
| T5.5 | [ ] | Calculate Bollinger state | Implement price standard deviation, `%b`, and BandWidth for the fixed 20/2 contract; do not store redundant bands. | P0.4, T5.1-T5.2 |
| T5.6 | [ ] | Calculate ADX and DMI | Implement +DI 14, -DI 14, and ADX 14 with Wilder smoothing and unstable-period policy. | P0.4, T5.1, T5.4 |
| T5.7 | [ ] | Calculate MACD | Implement 12/26/9 line, signal, histogram, and normalized values with fixed scale and zero handling. | P0.4, T5.1-T5.2 |
| T5.8 | [ ] | Add combined TA-Lib regression | Compare pinned-library fixtures, edge cases, trustworthy legacy examples, and an independent reference per family. | T5.2-T5.7 |

---

## Phase 6: Implement SPX-Relative Features

Goal: add exact-date cross-provider market comparison without implying a
canonical identity mapping.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| X6.1 | [ ] | Build aligned returns | Align subject/SPX one-day returns by exact date, preserve gaps, and expose aligned counts. | P0.5, I3.4, C4.2 |
| X6.2 | [ ] | Calculate SPX price ratio | Implement `rel_spx` and 20/50 ratio-trend distances with denominator and warm-up rules. | P0.5, X6.1, T5.2 |
| X6.3 | [ ] | Calculate relative returns | Implement compounded SPX-relative returns for 20/63/126/252 aligned observations. | P0.5, X6.1 |
| X6.4 | [ ] | Calculate rolling beta | Implement 60/252 sample-covariance beta; null incomplete windows and zero SPX variance. | P0.5, X6.1 |
| X6.5 | [ ] | Calculate rolling correlation | Implement 60/252 Pearson correlation with complete windows and bounded tolerance. | P0.5, X6.1 |
| X6.6 | [ ] | Enforce eligible subjects | Populate SPX features only for approved subjects; leave unsupported global/index/futures/commodity/currency series null with bounded reasons. | P0.5-P0.6, X6.2-X6.5 |
| X6.7 | [ ] | Test benchmark corrections | Prove inserted, changed, missing, or deleted SPX bars recalculate required subject dates without unrelated mutation. | P0.7, X6.2-X6.6 |
| X6.8 | [ ] | Add SPX golden regression | Compare ratio, relative returns, beta, and correlation against independent aligned fixtures covering gaps and low variance. | X6.2-X6.7 |

---

## Phase 7: Validate And Persist Current Feature State

Goal: write complete validated rows efficiently and idempotently while
preserving caller transaction ownership.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| W7.1 | [ ] | Add strict row validation | Validate finite values, copied source, bounds, warm-up nulls, dependencies, benchmark, observation counts, and generated inputs before SQL. | C4.8, T5.8, X6.8 |
| W7.2 | [ ] | Assemble complete rows | Merge core, TA-Lib, and SPX outputs without positional drift; every V1 field is intentionally populated or null. | W7.1 |
| W7.3 | [ ] | Implement bulk upsert | Write bounded batches, omit generated columns, count inserted/updated/unchanged, and avoid no-change updates. | S2.5, W7.2 |
| W7.4 | [ ] | Persist optional recurrence state | If S2.2 approved state, write it atomically and prevent advancement without its feature row; otherwise record no writer is needed. | S2.2, W7.3 |
| W7.5 | [ ] | Implement affected-range planner | Convert missing rows, source/SPX corrections, and version drift into deterministic work ranges with required prefix and suffix propagation. | I3.5, X6.7, W7.3-W7.4 |
| W7.6 | [ ] | Prove rebuild equivalence | Compare full rebuild, append, resume, source correction, SPX correction, and version rebuild within approved tolerance. | B1.2, W7.3-W7.5 |
| W7.7 | [ ] | Add feature queries | Add date/listing coverage, freshness, version, benchmark, ranking, and model-input reads without strategy thresholds. | S2.4, W7.3 |
| W7.8 | [ ] | Add PostgreSQL integration | Cover rollback, generated values, idempotency, correction propagation, provider/benchmark isolation, and repeated runs. | W7.3-W7.7 |
| W7.9 | [ ] | Benchmark persistence | Measure batches, upserts, index cost, memory, and latest-date latency; adjust only with evidence against P0.8. | P0.8, W7.8 |

---

## Phase 8: Build JSON And Professional PDF Reports

Goal: make every run operationally inspectable before production runners.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| R8.1 | [ ] | Define report schema V1 | Define secret-safe JSON for identity, scope, versions, readiness, provider/market/listing counts, writes, warm-up/null/benchmark coverage, warnings, timing, throughput, and bounded samples. | P0.2, P0.8, W7.7 |
| R8.2 | [ ] | Add summary queries | Implement provider/market/type/date/version quality and coverage aggregations without serializing feature payloads; plans meet P0.8. | W7.7-W7.9, R8.1 |
| R8.3 | [ ] | Build JSON report | Produce deterministic versioned JSON for success, warning, no-op, resumed/partial backfill, and failure. | R8.1-R8.2 |
| R8.4 | [ ] | Store JSON report | Store durable `report.json` through Core with approved kind, logical name, metadata, retention, and run relationship. | R8.3 |
| R8.5 | [ ] | Design professional PDF | Define Empire cover/disclaimer, status, scope, coverage, formula/library versions, benchmark health, quality, performance, warnings, and methodology without recommendations. | R8.1-R8.3 |
| R8.6 | [ ] | Implement PDF renderer | Use reusable `empire-reports` components, bounded tables/charts, deterministic pagination, and accessible labels. | R8.5 |
| R8.7 | [ ] | Visually verify PDF | Render success, warning, no-op, and large-scope reports; inspect every page for clipping, overflow, sparse layouts, charts, and branding. | R8.6 |
| R8.8 | [ ] | Store PDF report | Store durable `report.pdf` with matching Core lineage/metadata and prove JSON/PDF facts agree. | R8.4, R8.7 |

---

## Phase 9: Implement Daily And Backfill Runners

Goal: own complete Core-tracked workflows in the package while callers provide
runtime services and explicit scope.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| J9.1 | [ ] | Add Core lifecycle | Start, heartbeat, succeed, fail, and summarize jobs with stable identity and no source/feature payloads in Core metadata. | P0.2, B1.6 |
| J9.2 | [ ] | Define daily scope | Add effective date, provider/market/listing filters, readiness, version, dry-run, and force semantics; reject ambiguity. | P0.7, I3.6, W7.5 |
| J9.3 | [ ] | Implement daily runner | Sequence readiness, planning, calculation, validation, persistence, summaries, JSON/PDF storage, and Core completion. | W7.8, R8.8, J9.1-J9.2 |
| J9.4 | [ ] | Implement healthy no-op | No eligible new/corrected/version work succeeds with explicit readiness and durable reports but no writes. | J9.3 |
| J9.5 | [ ] | Define backfill scope | Add provider/market/listing/date ranges, batches, resume cursor, version, rebuild, and confirmation for broad scopes. | P0.7-P0.8, W7.5 |
| J9.6 | [ ] | Implement resumable backfill | Process deterministic batches with independent commits, heartbeats, progress, partial/final reports, exact resume, and no duplicate work. | W7.9, R8.8, J9.1, J9.5 |
| J9.7 | [ ] | Add failure safety | Validation, DB, cancellation, report, and benchmark failures mark Core correctly, preserve committed chunks, roll back active work, and expose safe errors. | J9.3-J9.6 |
| J9.8 | [ ] | Add vertical runner integration | Run append, no-op, correction, version rebuild, and resumed backfill through PostgreSQL, Core, JSON, and PDF with zero fixture residue. | J9.3-J9.7 |

---

## Phase 10: Add Package Commands And `bin/` Wrappers

Goal: expose safe operator workflows before Airflow coordination.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| O10.1 | [ ] | Add config command | Add a secret-safe package command and `bin/stonks-technicals-config` using `bin/env-load`; validate runtime, dependency, benchmark, and DB readiness. | B1.5-B1.8, I3.6 |
| O10.2 | [ ] | Add daily command | Add package command and `bin/stonks-technicals-daily` with effective date/scope/version/dry-run options and compact JSON stdout. | J9.3-J9.4 |
| O10.3 | [ ] | Add backfill command | Add package command and `bin/stonks-technicals-backfill` with bounded scope, resume, rebuild protection, progress, and compact JSON stdout. | J9.5-J9.7 |
| O10.4 | [ ] | Add inspect command | Add a read-only command/wrapper for coverage, freshness, drift, SPX readiness, and bounded samples without target recommendations. | W7.7, R8.2 |
| O10.5 | [ ] | Add CLI validation | Cover help, invalid scopes, missing config, benchmark failure, dry run, no-op, success, resume, exit codes, and safe stdout/stderr. | O10.1-O10.4 |
| O10.6 | [ ] | Add operator documentation | Document setup, reports, scopes, backfill/resume, rebuild, corrections, benchmark failure, and safe SQL inspection. | O10.1-O10.5 |
| O10.7 | [ ] | Verify installed commands | Build/install and prove package scripts/wrappers work in Poetry and Airflow with environment loading owned by runtime. | O10.1-O10.6 |

---

## Phase 11: Add Thin Airflow Coordination

Goal: refresh technicals only after required EODData and Yahoo/SPX inputs are
ready for the same effective date, without moving package logic into DAGs.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| A11.1 | [ ] | Select coordination mechanism | Evaluate Airflow 3 assets/events, coordinator DAG, and trigger/wait patterns against scheduled EODData and manual Yahoo. Select a date-scoped prerequisite join that does not rely on timing alone. | I3.6, J9.3, OHLCV V10.8-V10.10 |
| A11.2 | [ ] | Define source completion signals | Add/reuse minimal date-scoped source outputs/assets so EODData and Yahoo success is unambiguous, rerun-safe, and contains no credentials/raw data. | A11.1 |
| A11.3 | [ ] | Add manual technicals DAG | Add thin `stonks_technicals_daily_refresh` wiring runtime services and validated effective-date/scope overrides to the package runner; begin `schedule=None`, no catchup, one active run. | O10.7, A11.1 |
| A11.4 | [ ] | Add DAG contract tests | Cover import, tags, schedule, task shape, date handling, overrides, runner identity, logging, and absence of calculation SQL/business logic. | A11.3 |
| A11.5 | [ ] | Wire prerequisites | Implement the selected EODData plus Yahoo/SPX join so automatic refresh occurs only after both inputs succeed or readiness is explicitly proven for the same date. | A11.2-A11.4 |
| A11.6 | [ ] | Handle repeated source runs | Prove EODData's multiple daily runs and Yahoo/manual reconciliation coalesce or safely trigger idempotent refresh without concurrent duplicate work. | A11.5, J9.4 |
| A11.7 | [ ] | Verify Airflow vertical | Rebuild Airflow, verify zero import errors, run source fixture completions through technicals, and inspect Core plus JSON/PDF objects. | A11.4-A11.6 |
| A11.8 | [ ] | Decide production cadence | From bounded evidence, choose event-driven, scheduled, or manual-only operation and document pause/rollback before enabling it. | A11.7 |

---

## Phase 12: Verify, Backfill, And Roll Out Incrementally

Goal: prove correctness and performance from fixtures through bounded live
operation before normal refresh begins.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| V12.1 | [ ] | Complete package README | Document ownership, profile, formulas, source caveats, config, tables, validation, versions, reports, CLIs, DAGs, and deferred work. | O10.6, A11.8 |
| V12.2 | [ ] | Complete operator runbook | Document daily operation, backfill, resume/rebuild, reports, SPX readiness, corrections, version rollout, Airflow recovery, and rollback. | V12.1 |
| V12.3 | [ ] | Run formatting and full tests | Formatting/linting, package, schema, PostgreSQL/Core, report, CLI, and DAG suites pass from repository root. | V12.2 |
| V12.4 | [ ] | Validate DB and regenerate docs | Flyway, Stonks contracts, OHLCV regressions, and all DB documentation generation pass without drift. | V12.2 |
| V12.5 | [ ] | Run numerical audit | Compare stored features with fresh rebuilds, pinned TA-Lib, independent formulas, and incremental outputs across providers, gaps, short history, corrections, and SPX alignment. | W7.6, J9.8, V12.3-V12.4 |
| V12.6 | [ ] | Run performance gate | Measure rebuild, append, source/SPX correction, upsert, latest-date scan/rank, report, and memory against P0.8; tune only from evidence. | W7.9, V12.3-V12.5 |
| V12.7 | [ ] | Run bounded backfill | Backfill a representative cohort and verify counts, warm-up/null coverage, generated/SPX values, resume, reports, and no source mutation. | V12.5-V12.6 |
| V12.8 | [ ] | Expand backfill in stages | Expand by provider/market cohorts with checkpoints and stop criteria; audit adjustment warnings, inactive listings, performance, and reports. | V12.7 |
| V12.9 | [ ] | Run bounded live daily | Execute live source prerequisites then technical refresh; inspect readiness, idempotency, corrections, Core, JSON/PDF, and Airflow. | A11.8, V12.7 |
| V12.10 | [ ] | Close rollout gate | Record cadence, calculation version, supported universes, coverage, performance, risks, recovery, and go/no-go; enable only after healthy evidence. | V12.8-V12.9 |

---

## Deferred Work

- Sector-relative returns until point-in-time mappings exist.
- Strategy target flags and threshold-specific indexes.
- Portfolio/backtest engines and execution/performance analytics.
- Cross-sectional ranks until the historical universe is explicit.
- Stochastic, Williams `%R`, CCI, MFI, OBV, Chaikin A/D, Aroon, Parabolic SAR,
  Ichimoku, Keltner, candlestick-pattern, and cycle/Hilbert families.
- Intraday indicators and true session VWAP.
- Canonical/cross-provider consensus technical histories.
- Append-only technical revision history.

New indicators require a concrete consumer, exact versioned formula,
incremental behavior, storage/query justification, and independent regression.
