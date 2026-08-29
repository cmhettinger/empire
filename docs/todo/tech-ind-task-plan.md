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

Phases 0-11 are archived there with task IDs P0.1-P0.10, B1.1-B1.8,
S2.1-S2.8, I3.1-I3.7, C4.1-C4.8, T5.1-T5.8, X6.1-X6.8, W7.1-W7.10,
R8.1-R8.8, J9.1-J9.9, O10.1-O10.7, and A11.1-A11.8, together with their
`Done:` notes.

---

## Phase 12: Complete Verification And Close Development

Goal: finish the code and documentation, prove correctness and representative
performance, and produce a release candidate that is ready to deploy to the
new production host.

Phase 12 is a development-closeout phase. It may use fixtures, generated
datasets, PostgreSQL integration environments, and deliberately bounded
existing development data. It must not run a broad Stooq or Yahoo source
backfill, a broad technical-indicator backfill, or a normal live-production
cadence on the development laptop. Those operations belong to Phase 13.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| V12.1 | [x] | Complete package README | Document ownership, profile, formulas, source caveats, config, tables, validation, versions, reports, CLIs, DAGs, and deferred work. | O10.6, A11.8 |
| V12.2 | [x] | Complete operator runbook | Document daily operation, atomic publication, lock diagnosis/recovery, backfill, resume/rebuild, reports, SPX readiness, corrections, version rollout, Airflow recovery, and rollback. | V12.1 |
| V12.3 | [x] | Run formatting and full tests | Formatting/linting, package, schema, PostgreSQL/Core, report, CLI, and DAG suites pass from repository root. | V12.2 |
| V12.4 | [x] | Validate DB and regenerate docs | Flyway, Stonks contracts, OHLCV regressions, and all DB documentation generation pass without drift. | V12.2 |
| V12.5 | [x] | Run correctness and isolation audit | Using deterministic fixtures, generated datasets, PostgreSQL integration tests, and only deliberately bounded existing development data, compare stored features with fresh calculations, pinned TA-Lib, independent formulas, and incremental outputs across providers, gaps, short history, corrections, and SPX alignment; concurrently exercise publication visibility, version isolation, benchmark completeness, the global writer lock, and failure recovery. | W7.6, W7.10, J9.8-J9.9, V12.3-V12.4 |
| V12.6 | [x] | Run representative performance gate | Measure rebuild, append, source/SPX correction, upsert, atomic publication/staging, lock acquisition/contention, latest-date scan/rank, report, and memory against P0.8 using generated or already-available bounded data; tune only from evidence and defer production-scale confirmation to Phase 13. | W7.9-W7.10, V12.3-V12.5 |
| V12.7 | [x] | Audit the release candidate | Verify package versions and locks, migrations, environment templates, wrappers, Compose/Airflow definitions, report assets, supported provider universes, rollback paths, and production-host prerequisites. Resolve every code or documentation blocker; record any operational risk that can only be evaluated on production hardware. | V12.1-V12.6, A11.8 |
| V12.8 | [x] | Close the development gate | Record the reviewed commit, calculation version, test and performance evidence, supported universes, known risks, recovery procedures, production capacity assumptions, and an explicit ready/not-ready decision for Phase 13. Do not enable production cadence or perform broad source or indicator backfills. | V12.7 |

Done: 2026-08-29 — completed
`packages/empire-stonks-tech-indicators/README.md` against the live V1 package,
schema, reports, four CLIs, and event-driven paused Airflow coordinator. Focused
pytest passed 148 tests; Poetry lock and `pip check`, wheel/sdist build,
distribution import/version, four wrapper help smokes, 20 local links, required
section/fence validation, and `git diff --check` passed.

Done: 2026-08-29 — completed
`docs/stonks/tech-indicators-operator-runbook.md` with daily operation, atomic
publication, Airflow/lock recovery, staged backfill/resume, correction and
version rollout/rollback procedures. Focused pytest passed 186 tests including
CLI, report/PDF, writer-lock, runner, scope, and DAG coverage; Poetry lock and
`pip check`, four wrapper help smokes, 13 required sections, 48 balanced fences,
13 local links, and `git diff --check` passed.

Done: 2026-08-29 — full technical-indicators pytest passed 788 tests against
live PostgreSQL; standalone Core and reports pytest passed 32 and 21 tests.
The rollback-only schema contract passed 64 expected failures. Poetry lock,
`pip check`, compileall, wheel/sdist build, distribution import/version, four
CLI help smokes, deployed Airflow DAG listing with zero import errors, and
`git diff --check` passed; the repository configures no formatter or linter.

Done: 2026-08-29 — Flyway validated 39 migrations; all four rollback-only
Stonks SQL contracts passed, including 64 technical-indicator expected
failures. Full database-enabled OHLCV pytest passed 641 tests, including both
technical-child regressions. `make docs-db` generated both schemas, 12 Stonks
groups, and both SchemaSpy sites; 88 tracked artifacts, 24 grouped Mermaid
files, 48 grouped images, and all 28 PNG/28 SVG signatures passed. Schema,
ERD, and image outputs had zero drift; only both tool-owned generation
timestamps advanced. `git diff --check` passed.

Done: 2026-08-29 — added the rollback-only 850-row/76-feature PostgreSQL audit
in `test_correctness_audit_integration.py` and recorded the V12.5 matrix in
`docs/stonks/tech-indicators-correctness-isolation-audit-v12.5.md`. Focused
formula/equivalence pytest passed 107 tests, focused PostgreSQL isolation and
recovery pytest passed 27, and full package pytest passed 789. Bounded
repeatable-read development aggregates, Poetry check, compileall, line-length
scan, and `git diff --check` passed; no backfill, cadence, or durable data write
ran.

Done: 2026-08-29 — added the deterministic 20,000-observation calculation
probe and recorded the V12.6 gate in
`docs/stonks/tech-indicators-performance-evidence-v12.6.md`. Rebuild, append,
source/SPX correction, the 1,000,000-row pilot, 25,000-row upserts/scan/rank,
summary projection, publication, lock, vertical/no-op, report, RSS, storage,
WAL, and disk gates passed; pilot throughput was 1,035.40 rows/s at 412.47 MiB
RSS and 35.87 GiB projected slots. Full pytest passed 789; Poetry check,
compileall, zero scratch residue, line scan, and `git diff --check` passed. No
tuning, broad backfill, publication, or cadence ran; production confirmation
remains Phase 13.

Done: 2026-08-29 — recorded the passing V12.7 release-candidate audit in
`docs/stonks/tech-indicators-release-candidate-audit-v12.7.md`. Flyway validated
39 migrations; the schema contract passed 64 expected failures; all 789 package
tests passed across database-partitioned runs; 35 report and 53 OHLCV/Airflow
integration tests passed. Lock/build, `pip check`, config preflight, 8 CLI help
smokes, Compose/Airflow import/runtime, 10-setting parity, assets, seven exact
provider cohorts, rollback, production risks, and `git diff --check` passed; no
backfill, publication, migration, remediation, or cadence change ran.

Done: 2026-08-29 — recorded the V12.8 READY decision for staged Phase 13 entry
in `docs/stonks/tech-indicators-development-gate-v12.8.md` against reviewed
commit `eedc9d264241e4e6e8b326e21142d31b85c17cf7` and `TECH_INDICATORS_V1`.
Lock and local/Airflow dependency checks, 39-migration Flyway validation,
`ready=true` config preflight, paused technical DAG, zero Airflow import errors,
links/fences, completion assertions, and `git diff --check` passed; no backfill,
publication, migration, remediation, activation, or cadence change ran.

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
