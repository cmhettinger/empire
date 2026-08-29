# Technical Indicators Package Action Plan

This document tracks the implementation roadmap for provider-native daily
technical indicators in Empire Stonks.

The first implementation creates a reusable
`empire-stonks-tech-indicators` package
that reads `stonks.ohlcv_daily`, calculates versioned daily analytical
features, and stores current state in
`stonks.ohlcv_daily_tech_indicators`. It does not put calculation logic in the
OHLCV package, DAGs, reports, or strategies.

The delivery proves one manageable, testable layer at a time: contracts,
runtime dependencies, schema, inputs, calculation families, persistence,
reports, runners, CLIs, Airflow coordination, development closeout, and a
separate production buildout.

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

Phases 0-12 are archived there with task IDs P0.1-P0.10, B1.1-B1.8,
S2.1-S2.8, I3.1-I3.7, C4.1-C4.8, T5.1-T5.8, X6.1-X6.8, W7.1-W7.10,
R8.1-R8.8, J9.1-J9.9, O10.1-O10.7, A11.1-A11.8, and V12.1-V12.8,
together with their `Done:` notes.

---

## Phase 13: Build Out Production And Start Daily Operation

Goal: provision the new home-lab production host, establish durable network and
NAS-backed operation, add deployment-aware Airflow cadence, seed production
history, build initial technical coverage, and start automated daily EODData,
Yahoo, and technical-indicator workflows while local development stays manual.

Phase 13 starts only after V12.8 records a ready decision. Broad imports and
backfills run on the new production host, not on the development laptop. Each
long-running step must have a reviewed scope, capacity check, durable report,
checkpoint or resume path, stop criteria, and post-run coverage audit.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| P13.1 | [ ] | Size and procure the HPE host | Convert the V12.8 CPU, memory, storage-growth, database, container, and network assumptions into a reviewed HPE server configuration; record the selected hardware, expansion headroom, warranty/support, expected delivery, and purchase decision. | V12.8 |
| P13.2 | [ ] | Establish the host baseline | Install and patch the reviewed server OS, firmware, Docker/Compose runtime, time synchronization, administrative access, firewall, power/restart behavior, and monitoring prerequisites; record versions and the recovery path. | P13.1 |
| P13.3 | [ ] | Connect production networking and NAS storage | Assign the stable host identity and network configuration, create the production NAS shares and Empire storage layout, mount them with least-privilege ownership, and prove boot-time mount, reconnect, throughput, free-space, and failure behavior. Do not initialize Empire storage roots until the expected mounts are present. | P13.2 |
| P13.4 | [ ] | Design deployment-aware Airflow cadence | Evaluate one shared DAG definition with a small validated deployment profile and environment-supplied schedules against separate local/prod DAG files. Prefer shared task logic and one DAG ID per workflow: local resolves EODData and Yahoo to `schedule=None`, production resolves explicit reviewed schedules, and the technical coordinator stays event-driven with `schedule=None`. Define parse-time validation, timezone/DST behavior, tags and observability, pause/rollback, configuration ownership, and safe behavior for missing or invalid settings. Duplicate DAG files are allowed only if Airflow import/serialization evidence shows the shared design is unsafe or materially harder to operate. | V12.8, A11.8 |
| P13.5 | [ ] | Implement and verify scheduling profiles | Implement the selected cadence configuration without duplicating package business logic. Add committed non-secret defaults/templates and deployment wiring; update the Yahoo provider-access decision and rollout contracts for a conservative production cadence. Tests must parse the same DAG code under local and production profiles, prove local source DAGs are manual, prove production EODData and Yahoo schedules are exact, prove catchup/overlap protections and source-triggered technical dispatch remain intact, and prove rollback to manual operation requires configuration plus the documented Airflow refresh/restart rather than a code fork. | P13.4 |
| P13.6 | [ ] | Deploy the reviewed Empire release | Clone the repository on the server, check out the exact commit reviewed after P13.5, create the uncommitted production environment and secrets from the committed template, configure the production Airflow profile, database, and NAS-backed storage roots, build the required images, run Flyway, initialize Core storage roots, and initialize Airflow using repository workflows. | V12.8, P13.3, P13.5 |
| P13.7 | [ ] | Prove production infrastructure readiness | Run database, PgBouncer, storage, package, CLI, report, and Airflow preflights; verify expected DAGs and import health, exact production schedules, local-versus-production profile isolation, backups and restore procedure, service restart/reboot recovery, observability, and initial paused states before source loading. | P13.6 |
| P13.8 | [ ] | Run the weekend Stooq starter import | Manually acquire and record the approved Stooq archive and provenance, run the production Stooq historical import for the reviewed U.S. stock partitions with checkpoints and stop criteria, resume safely as needed, and audit counts, coverage, warnings, performance, Core lineage, JSON/PDF reports, and absence of canonical/source crossover. | P13.7 |
| P13.9 | [ ] | Backfill the Yahoo benchmark universe | Run the bounded seeded Yahoo index, yield, volatility, currency, commodity, and continuous-futures backfill with provider-safe pacing and resume; verify SPX identity/history, calendar coverage, native semantics, request volume, lineage, and JSON/PDF reports. | P13.7 |
| P13.10 | [ ] | Build initial production technical coverage | After the Stooq and Yahoo source audits pass, backfill technical indicators in staged provider/market cohorts. Verify counts, warm-up/null and generated/SPX coverage, publication isolation, resume, adjustment warnings, inactive-listing handling, production performance, reports, and no OHLCV mutation. | P13.8-P13.9 |
| P13.11 | [ ] | Rehearse the automated production daily path | With normal automation still paused, temporarily exercise the production schedules or their exact scheduled-run semantics for bounded same-date EODData and Yahoo prerequisites followed by source-triggered technical refresh. Inspect effective-date derivation, readiness, atomic publication, idempotency, correction behavior, locking, Core lineage, reports, Airflow dispatch, and rollback; confirm the local profile remains manual. | P13.10, A11.8 |
| P13.12 | [ ] | Start the first Monday automated daily cycle | Enable the reviewed production EODData and Yahoo schedules while leaving local development manual. Release the technical coordinator only under the reviewed readiness and backlog procedure, then record same-date source completion, automatic dispatch, technical freshness, resource use, and recovery evidence. | P13.11 |
| P13.13 | [ ] | Observe bounded production operation | Verify at least three consecutive ready effective dates and one unchanged rerun within release targets; audit scheduled-run timing, queued wakes, warnings, source and benchmark coverage, provider request pressure, resource use, reports, backups, and stop conditions before normal activation. | P13.12 |
| P13.14 | [ ] | Close the production rollout gate | Record the deployed commit, local and production cadence profiles, calculation version, supported universes, coverage, production performance, provider-access evidence, risks, recovery, and explicit go/no-go. On a go decision, leave the reviewed production source schedules and technical coordinator enabled while retaining `schedule=None` for the corresponding local-development source DAGs. | P13.13 |

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
