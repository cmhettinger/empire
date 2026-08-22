# Technical Indicators Package Action Plan

This document tracks the implementation roadmap for provider-native daily
technical indicators in Empire Stonks.

The first implementation creates a reusable
`empire-stonks-tech-indicators` package
that reads `stonks.ohlcv_daily`, calculates versioned daily analytical
features, and stores current state in
`stonks.ohlcv_daily_tech_indicators`. It does not put calculation logic in the
OHLCV package, DAGs, reports, or strategies.

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

`empire-stonks-tech-indicators` owns chronological OHLCV reads, benchmark
resolution, TA-Lib/NumPy calculation adapters, versioned formulas, numerical
validation, affected-range planning, current-state persistence, daily and
backfill runners, feature/coverage queries, JSON/PDF run reports, and thin CLI
entrypoints.

It does not own provider ingestion, OHLCV mutation, canonical identity,
corporate-action normalization, strategy thresholds, target selection,
portfolio/backtest execution, point-in-time sector mappings, intraday
indicators, or Airflow business logic. `empire-stonks-ohlcv` stays upstream and
must not import `empire_stonks_tech_indicators`.

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
    -> empire-stonks-tech-indicators -> stonks.ohlcv_daily_tech_indicators
    -> reports / screens / future backtests
```

## Initial Persistence And Calculation Contract

`stonks.ohlcv_daily_tech_indicators` has one current row per
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

Model consumers see only complete publication units with one calculation
version and complete benchmark semantics. The package owns database-backed
scope locking across daily, backfill, CLI, and Airflow entry points; Airflow
scheduler limits are not the concurrency boundary.

Lookbacks count chronological observations, never future rows. TA-Lib warm-up
and unstable periods are versioned; expected pre-lookback non-finite output
becomes null, while post-lookback non-finite output fails calculation.
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

Phases 0-7 are archived there with task IDs P0.1-P0.10, B1.1-B1.8,
S2.1-S2.8, I3.1-I3.7, C4.1-C4.8, T5.1-T5.8, X6.1-X6.8, and W7.1-W7.10,
together with their `Done:` notes.

---

## Phase 8: Build JSON And Professional PDF Reports

Goal: make every run operationally inspectable before production runners.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| R8.1 | [x] | Define report schema V1 | Define secret-safe JSON for identity, scope, versions, source/publication readiness, lock outcome, provider/market/listing counts, writes, warm-up/null/benchmark coverage, warnings, timing, throughput, and bounded samples. | P0.2, P0.8-P0.10, W7.7 |
| R8.2 | [ ] | Add summary queries | Implement provider/market/type/date/version quality and coverage aggregations without serializing feature payloads; plans meet P0.8. | W7.7-W7.9, R8.1 |
| R8.3 | [ ] | Build JSON report | Produce deterministic versioned JSON for success, warning, no-op, resumed/partial backfill, and failure. | R8.1-R8.2 |
| R8.4 | [ ] | Store JSON report | Store durable `report.json` through Core with approved kind, logical name, metadata, retention, and run relationship. | R8.3 |
| R8.5 | [ ] | Design professional PDF | Define Empire cover/disclaimer, status, scope, coverage, formula/library versions, benchmark health, quality, performance, warnings, and methodology without recommendations. | R8.1-R8.3 |
| R8.6 | [ ] | Implement PDF renderer | Use reusable `empire-reports` components, bounded tables/charts, deterministic pagination, and accessible labels. | R8.5 |
| R8.7 | [ ] | Visually verify PDF | Render success, warning, no-op, and large-scope reports; inspect every page for clipping, overflow, sparse layouts, charts, and branding. | R8.6 |
| R8.8 | [ ] | Store PDF report | Store durable `report.pdf` with matching Core lineage/metadata and prove JSON/PDF facts agree. | R8.4, R8.7 |

Done: 2026-08-22 — froze the shared daily/backfill JSON fact shape, outcomes,
readiness/lock/publication semantics, count equations, coverage/null reasons,
performance denominators, 100-sample ceiling, disclosures, and Core metadata
allowlist in `docs/stonks/tech-indicators-report-schema-v1.md`; linked the
design contract and package README. Contract marker/count/schema checks,
documentation links, package pytest (514 passed, 3 skipped), Poetry lock/build,
`pip check`, compileall, public import, Flyway validation (39 migrations),
whitespace,
and `git diff --check` passed.

---

## Phase 9: Implement Daily And Backfill Runners

Goal: own complete Core-tracked workflows in the package while callers provide
runtime services and explicit scope.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| J9.1 | [ ] | Add Core lifecycle | Start, heartbeat, succeed, fail, and summarize jobs with stable identity and no source/feature payloads in Core metadata. | P0.2, B1.6 |
| J9.2 | [ ] | Define daily scope | Add effective date, provider/market/listing filters, readiness, version, dry-run, and force semantics; reject ambiguity. | P0.7, I3.6, W7.5 |
| J9.9 | [ ] | Add package-owned writer lock | Implement P0.10's single PostgreSQL transaction advisory lock on a dedicated connection; all mutating scopes share it, contention returns immediately without workflow state, heartbeats detect loss, terminal publication uses the lock connection, and every terminal path releases it. | P0.10, J9.1-J9.2 |
| J9.3 | [ ] | Implement daily runner | Sequence lock acquisition, readiness, planning, calculation, validation, atomic publication, summaries, JSON/PDF storage, and Core completion. | W7.8, W7.10, R8.8, J9.1-J9.2, J9.9 |
| J9.4 | [ ] | Implement healthy no-op | No eligible new/corrected/version work succeeds with explicit readiness and durable reports but no writes. | J9.3 |
| J9.5 | [ ] | Define backfill scope | Add provider/market/listing/date ranges, batches, resume cursor, version, rebuild, and confirmation for broad scopes. | P0.7-P0.8, W7.5 |
| J9.6 | [ ] | Implement resumable backfill | Process deterministic inactive-slot batches with independent commits, unpublished partial progress, heartbeats, reports, exact resume, and no duplicate work; flip membership only for a complete P0.9 unit. | W7.9-W7.10, R8.8, J9.1, J9.5, J9.9 |
| J9.7 | [ ] | Add failure safety | Validation, DB, cancellation, report, and benchmark failures mark Core correctly, preserve only safely resumable unpublished chunks, roll back active work, never advance publication readiness, release locks, and expose safe errors. | J9.3-J9.6, J9.9 |
| J9.8 | [ ] | Add vertical runner integration | Run append, no-op, correction, version rebuild, and resumed backfill through PostgreSQL, Core, JSON, and PDF with zero fixture residue. | J9.3-J9.7 |

---

## Phase 10: Add Package Commands And `bin/` Wrappers

Goal: expose safe operator workflows before Airflow coordination.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| O10.1 | [ ] | Add config command | Add a secret-safe package command and `bin/stonks-tech-indicators-config` using `bin/env-load`; validate runtime, dependency, benchmark, and DB readiness. | B1.5-B1.8, I3.6 |
| O10.2 | [ ] | Add daily command | Add package command and `bin/stonks-tech-indicators-daily` with effective date/scope/version/dry-run options and compact JSON stdout. | J9.3-J9.4 |
| O10.3 | [ ] | Add backfill command | Add package command and `bin/stonks-tech-indicators-backfill` with bounded scope, resume, rebuild protection, progress, and compact JSON stdout. | J9.5-J9.7 |
| O10.4 | [ ] | Add inspect command | Add read-only `bin/stonks-tech-indicators-inspect` for coverage, freshness, drift, SPX readiness, and bounded samples without target recommendations. | W7.7, R8.2 |
| O10.5 | [ ] | Add CLI validation | Cover help, invalid scopes, missing config, benchmark failure, lock contention, dry run, no-op, success, resume, exit codes, and safe stdout/stderr. | O10.1-O10.4 |
| O10.6 | [ ] | Add operator documentation | Document setup, reports, scopes, publication readiness, lock contention/recovery, backfill/resume, rebuild, corrections, benchmark failure, and safe SQL inspection. | O10.1-O10.5 |
| O10.7 | [ ] | Verify installed commands | Build/install and prove package scripts/wrappers work in Poetry and Airflow with environment loading owned by runtime. | O10.1-O10.6 |

---

## Phase 11: Add Thin Airflow Coordination

Goal: refresh tech indicators only after required EODData and Yahoo/SPX inputs
are ready for the same effective date, without moving package logic into DAGs.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| A11.1 | [ ] | Select coordination mechanism | Evaluate Airflow 3 assets/events, coordinator DAG, and trigger/wait patterns against scheduled EODData and manual Yahoo. Select a date-scoped prerequisite join that does not rely on timing alone. | I3.6, J9.3, OHLCV V10.8-V10.10 |
| A11.2 | [ ] | Define source completion signals | Add/reuse minimal date-scoped source outputs/assets so EODData and Yahoo success is unambiguous, rerun-safe, and contains no credentials/raw data. | A11.1 |
| A11.3 | [ ] | Add manual tech-indicators DAG | Add thin `stonks_tech_indicators_daily_refresh` wiring runtime services and validated effective-date/scope overrides to the package runner; begin `schedule=None`, no catchup, one active run. | O10.7, A11.1 |
| A11.4 | [ ] | Add DAG contract tests | Cover import, tags, schedule, task shape, date handling, overrides, runner identity, logging, and absence of calculation SQL/business logic. | A11.3 |
| A11.5 | [ ] | Wire prerequisites | Implement the selected EODData plus Yahoo/SPX join so automatic refresh occurs only after both inputs succeed or readiness is explicitly proven for the same date. | A11.2-A11.4 |
| A11.6 | [ ] | Handle repeated source runs | Prove EODData's multiple daily runs and Yahoo/manual reconciliation coalesce or safely trigger idempotent refresh through the package-owned scope lock, without concurrent duplicate work or partial publication. | A11.5, J9.4, J9.9 |
| A11.7 | [ ] | Verify Airflow vertical | Rebuild Airflow, verify zero import errors, run source fixture completions through tech indicators, and inspect Core plus JSON/PDF objects. | A11.4-A11.6 |
| A11.8 | [ ] | Decide production cadence | From bounded evidence, choose event-driven, scheduled, or manual-only operation and document pause/rollback before enabling it. | A11.7 |

---

## Phase 12: Verify, Backfill, And Roll Out Incrementally

Goal: prove correctness and performance from fixtures through bounded live
operation before normal refresh begins.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| V12.1 | [ ] | Complete package README | Document ownership, profile, formulas, source caveats, config, tables, validation, versions, reports, CLIs, DAGs, and deferred work. | O10.6, A11.8 |
| V12.2 | [ ] | Complete operator runbook | Document daily operation, atomic publication, lock diagnosis/recovery, backfill, resume/rebuild, reports, SPX readiness, corrections, version rollout, Airflow recovery, and rollback. | V12.1 |
| V12.3 | [ ] | Run formatting and full tests | Formatting/linting, package, schema, PostgreSQL/Core, report, CLI, and DAG suites pass from repository root. | V12.2 |
| V12.4 | [ ] | Validate DB and regenerate docs | Flyway, Stonks contracts, OHLCV regressions, and all DB documentation generation pass without drift. | V12.2 |
| V12.5 | [ ] | Run correctness and isolation audit | Compare stored features with fresh rebuilds, pinned TA-Lib, independent formulas, and incremental outputs across providers, gaps, short history, corrections, and SPX alignment; concurrently exercise publication visibility, version isolation, benchmark completeness, the global writer lock, and failure recovery. | W7.6, W7.10, J9.8-J9.9, V12.3-V12.4 |
| V12.6 | [ ] | Run performance gate | Measure rebuild, append, source/SPX correction, upsert, atomic publication/staging, lock acquisition/contention, latest-date scan/rank, report, and memory against P0.8; tune only from evidence. | W7.9-W7.10, V12.3-V12.5 |
| V12.7 | [ ] | Run bounded backfill | Backfill a representative cohort and verify counts, warm-up/null coverage, generated/SPX values, resume, reports, and no source mutation. | V12.5-V12.6 |
| V12.8 | [ ] | Expand backfill in stages | Expand by provider/market cohorts with checkpoints and stop criteria; audit adjustment warnings, inactive listings, performance, and reports. | V12.7 |
| V12.9 | [ ] | Run bounded live daily | Execute live source prerequisites then technical refresh; inspect atomic readiness/publication, idempotency, corrections, lock behavior, Core, JSON/PDF, and Airflow. | A11.8, V12.7 |
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
