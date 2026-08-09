# Technical Indicators Package Action Plan Archive

This document contains fully completed phases moved from the active
[technical indicators package action plan](tech-ind-task-plan.md). Task IDs and
their `Done:` notes remain here as the historical record and may still be
referenced by active task dependencies.

When every task in a phase is complete, move its heading, goal, table, and all
associated `Done:` notes here without changing IDs, wording, dates, order, or
verification results. Do not archive partially completed phases.

---

## Phase 0: Freeze Scope And Calculation Contracts

Goal: turn the agreed feature set into exact, testable contracts before schema
or calculation code is committed.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| P0.1 | [x] | Ratify the design contract | Audit the existing design contract against live OHLCV/Core/reporting conventions, resolve contradictions without reopening settled scope, and mark it as the authoritative V1 baseline. | — |
| P0.2 | [x] | Freeze naming conventions | Select package/import, table/state-table, calculation version, Core jobs, storage keys, object kinds, report IDs, CLI names, and DAG ID. | P0.1 |
| P0.3 | [x] | Freeze feature profile V1 | Convert the contract inventory into the exact persisted/generated/query-time profile, resolving only its named open units, nullability, and ownership decisions. | P0.1 |
| P0.4 | [x] | Freeze formula semantics | Turn the contract formulas into executable specifications and resolve its named volatility, z-score, TA-Lib warm-up, tolerance, and denominator decisions. | P0.3 |
| P0.5 | [x] | Define SPX contract | Define `YAHOO/XIDX/SPX` resolution, eligible subjects, exact alignment, relative return, beta/correlation, complete windows, and unavailable behavior. | P0.3-P0.4 |
| P0.6 | [x] | Define source-value policy | Audit EODData, Stooq, and Yahoo adjustment/corporate-action semantics and select initially eligible provider listings without claiming normalization. | P0.1, OHLCV V10.11 |
| P0.7 | [x] | Define recalculation semantics | Specify daily append, missing row, source correction, SPX correction, version change, inactive listing, and deletion behavior with full/incremental equivalence. | P0.4-P0.6 |
| P0.8 | [x] | Set performance and release gates | Record representative sizes, daily/backfill timing and memory targets, transaction/staging bounds, query-plan expectations, report bounds, and live rollout criteria. | P0.3-P0.7 |
| P0.9 | [x] | Define atomic publication semantics | Freeze the publication unit and readiness predicate for daily, correction, version rebuild, and backfill work; choose transaction or staged-generation behavior so consumers fail closed on partial, mixed-version, or incomplete-benchmark state. | P0.5, P0.7-P0.8 |
| P0.10 | [x] | Define concurrency contract | Freeze the database-backed lock identity, scope normalization/overlap rules across job kinds and versions, acquisition lifetime, contention result, timeout, release, and recovery behavior shared by package, CLI, and Airflow runners. Any jobs able to write the same current rows must conflict. | P0.7-P0.9 |

Done: 2026-08-09 — ratified
`docs/stonks/technical-indicators-design-contract.md` against the live OHLCV
schema/package, completed source contracts, Core lifecycle/object services,
`empire-reports`, wrappers, and DAGs; froze cleanup-safe non-owning Core run
lineage while preserving task-owned open decisions. `make db-validate`
validated 38 migrations; focused contract marker/link checks and
`git diff --check` passed.

Done: 2026-08-09 — froze the `tech-indicators` naming contract in
`docs/stonks/technical-indicators-design-contract.md` and aligned future task
references in this plan for the distribution/import, main and conditional
state tables, `TECH_INDICATORS_V1`, Core jobs, environment/storage names,
report artifacts/IDs, four CLIs, and Airflow DAG/task. Identifier syntax,
length, uniqueness, and forbidden-legacy-name scans passed; `make db-validate`
validated 38 migrations, and `git diff --check` passed.

Done: 2026-08-09 — froze the exact 90-column V1 persisted, Python-computed,
PostgreSQL-generated, and query-time profile in
`docs/stonks/tech-indicators-feature-profile-v1.md`; linked its field
ownership, units, and logical nullability from the design contract. Independent
`python3` design/profile set comparison passed (`9 + 5 + 53 + 23 = 90`, no
duplicates or inventory drift); P0.2/P0.3/P0.4 status, forbidden alternate
identifier `rg` checks, and `git diff --check` passed.

Done: 2026-08-09 — froze executable V1 observation, formula, denominator,
sample-volatility, prior-reference z-score, TA-Lib warm-up, and numerical-
tolerance semantics in `docs/stonks/tech-indicators-formula-spec-v1.md`, with
design/profile links and P0.5 SPX boundaries. `python3` coverage and statistical
fixture assertions passed (42 non-SPX Python fields, 23 generated fields, 11
SPX fields deferred; no missing formulas; sample SD `5.916079783099616`,
excluded-current z-score `1.7748239349298849`); local-link, P0.3/P0.4/P0.5
status, alternate-identifier `rg`, and `git diff --check` checks passed.

Done: 2026-08-09 — froze exact `YAHOO/XIDX/SPX` resolution, EODData/Stooq
cash-equity support, common-date aligned returns, ratio/relative-return windows,
sample beta/correlation, counts, bounds, and unavailable/readiness behavior in
`docs/stonks/tech-indicators-spx-contract-v1.md`; linked the feature, formula,
and design contracts. `python3` contract fixtures passed (11/11 SPX fields,
live seed identity, intersection `[1, 4]`, 20-pair relative return
`0.21779997158616426`, beta `2.0`, correlation `1.0`); local-link,
P0.4/P0.5/P0.6 status, alternate-identifier `rg`, and `git diff --check` checks
passed.

Done: 2026-08-09 — froze exact EODData Equity, Stooq U.S. stock, and Yahoo
SPX-only source-value eligibility plus native adjustment, volume, currency,
corporate-action, correction, and comparability limits in
`docs/stonks/tech-indicators-source-value-policy-v1.md`; linked the feature,
SPX, and design contracts. Exact-predicate fixtures, live OHLCV report-label
and Yahoo seed checks, local-link/status scans, and `git diff --check` passed.

Done: 2026-08-09 — froze full-series equivalence, conservative suffix
invalidation, append/missing/source/SPX/version drift, inactive maintenance,
eligibility cleanup, safe horizons, and deletion behavior in
`docs/stonks/tech-indicators-recalculation-contract-v1.md`; linked the formula,
feature, SPX, source-value, and design contracts. Deterministic affected-range
fixtures, OHLCV FK/writer marker checks, local-link/status/stale-boundary scans,
and `git diff --check` passed.

Done: 2026-08-09 — froze measured live-size envelopes, daily/no-op/backfill
timing and RSS targets, read/write/transaction/staging/disk bounds, query-plan
and latency expectations, JSON/PDF limits, and nine staged rollout gates in
`docs/stonks/tech-indicators-performance-release-gates-v1.md`; linked the
recalculation and design contracts. Read-only PostgreSQL sizing/report evidence,
contract threshold fixtures, local-link/status/stale-boundary scans, and
`git diff --check` passed.

Done: 2026-08-09 — froze bounded in-place daily publication, two physical
payload slots, inactive-slot backfill/version builds, per-listing atomic
membership, terminal Core/report-aware finalization, crash recovery, and
one-snapshot fail-closed readiness in
`docs/stonks/tech-indicators-publication-contract-v1.md`; amended the frozen
naming/90-column relation handoff and linked dependent contracts. Publication
state/slot/readiness fixtures, live Core commit and PostgreSQL MVCC marker
checks, local-link/status/stale-boundary scans, and `git diff --check` passed.

Done: 2026-08-09 — froze one capability-wide, nonblocking PostgreSQL
transaction advisory lock, exact key derivation, dedicated PgBouncer-compatible
lock transaction, global overlap, canonical scope identity, zero-state
contention, terminal release, lock-loss, and recovery behavior in
`docs/stonks/tech-indicators-concurrency-contract-v1.md`; linked publication,
recalculation, performance, and design handoffs. Hash/scope fixtures, live
two-session advisory-lock/release checks, PgBouncer/Core marker scans, local
links/status/stale-boundary scans, and `git diff --check` passed.

---

## Phase 1: Prove Dependencies And Scaffold The Package

Goal: establish an independently importable package and prove TA-Lib works in
every runtime before building around it.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| B1.1 | [x] | Prove TA-Lib runtime support | Pin a reviewed TA-Lib/NumPy combination and prove local Poetry and Airflow-image installation/import. Record wheel/native-library behavior, license, Python compatibility, and rollback. | P0.4, P0.8 |
| B1.2 | [x] | Prototype recursive equivalence | Compare full-series output with append and historical-correction suffix strategies for EMA, RSI, ATR, ADX, and MACD. Decide whether exact updates require state, bounded replay, or full replay. | B1.1, P0.7 |
| B1.3 | [x] | Scaffold Poetry package | Create `packages/empire-stonks-tech-indicators` version `0.1.0` with `src/` layout, README, tests, minimum dependencies, isolated import, lock, and build. | B1.1 |
| B1.4 | [x] | Add exceptions and exports | Add a small public exception hierarchy and explicit API without exposing TA-Lib or persistence internals. | B1.3 |
| B1.5 | [x] | Add environment config | Add environment-only typed config for version, benchmark, batches, storage key, and limits; package code never loads `.env`. | P0.2, B1.3 |
| B1.6 | [x] | Add typed base models | Add immutable source-bar, feature-row, scope, benchmark, issue, count, summary, and run-result models with bounded JSON-ready forms. | P0.3-P0.7, B1.4 |
| B1.7 | [x] | Install in Airflow image | Install in dependency-safe order and prove tech-indicators, TA-Lib, NumPy, Core, and OHLCV imports coexist in the built image. | B1.1, B1.3 |
| B1.8 | [x] | Add runtime settings plumbing | Add non-secret example/local settings and Compose passthrough without embedding configuration in images or DAGs. | B1.5, B1.7 |

Done: 2026-08-09 — pinned wheel-only TA-Lib 0.7.1/C 0.7.1 and NumPy
2.4.6 in `deploy/docker/airflow/airflow-requirements.txt`; added
`docs/stonks/tech-indicators-runtime-contract-v1.md` and
`tools/tech-indicators/runtime-smoke.py`. A clean CPython 3.14.6 Poetry env
passed lock, exact-version calculation smoke, native-link/license inspection,
and `pip check`; `make airflow-build` completed 19 steps, and final CPython
3.13.13 Airflow one-offs passed the same smoke, Airflow/Core/OHLCV coexistence
imports, and `pip check`. Compilation, local-link, and `git diff --check`
passed.

Done: 2026-08-09 — added
`tools/tech-indicators/recursive-equivalence.py` and froze full-prefix
calculation with affected-suffix writes and no V1 recurrence-state table in
`docs/stonks/tech-indicators-recursive-equivalence-v1.md`; aligned the formula,
recalculation, and design contracts. Exact NumPy 2.4.6/TA-Lib 0.7.1 runs on
local CPython 3.14.6 and Airflow CPython 3.13.13 proved full-prefix append and
two correction cases equivalent, exposed bounded-restart mismatches across
EMA/RSI/ATR/ADX/MACD, and rejected EMA-derived MACD. Both 20,000-row fixture
runs passed the 120-second/512-MiB gates (0.031s/51.2 MiB local;
0.033s/119.9 MiB Airflow); compile, help, invalid-input, local-link, and diff
checks passed.

Done: 2026-08-09 — scaffolded
`packages/empire-stonks-tech-indicators` 0.1.0 with Poetry lock, `src/` import
boundary, README, and package test; runtime metadata contains only exact NumPy
2.4.6 and TA-Lib 0.7.1 pins. `poetry check --lock`, pytest (1 passed), package
and isolated wheel imports, both `pip check` runs, wheel/sdist build and content
inspection, local-link validation, compilation, and `git diff --check` passed.

Done: 2026-08-09 — added the public base plus configuration, calculation,
validation, persistence, and workflow exceptions in
`empire_stonks_tech_indicators/exceptions.py`, with exact package-root exports
and README guidance. Pytest passed 8 tests; cold Poetry and isolated-wheel
imports exposed only the declared API and loaded no NumPy, TA-Lib, psycopg, or
persistence implementation, while build, compilation, lock, dependency,
local-link, and diff checks passed.

Done: 2026-08-09 — added immutable `BenchmarkConfig` and
`TechIndicatorsConfig` with exact V1 calculation/benchmark identity,
environment-only storage, bounded read/write batches, diagnostic limits, safe
serialization, and a non-configurable 25,000-row transaction ceiling; exported
both types and documented variables without adding B1.8 runtime plumbing.
Pytest passed 37 tests; Poetry and dependency checks, `.env`/dotenv isolation,
inclusive-bound and drift failures, compilation, wheel/sdist build, isolated
wheel import, local links, and `git diff --check` passed.

Done: 2026-08-09 — added immutable source-bar, exact 65-column package-write
feature-row, normalized scope, resolved SPX benchmark, bounded issue/reason and
feature-count ledgers, summary, and compact run-result models in
`empire_stonks_tech_indicators/models.py`; exported and documented the API
without adding generated/database-owned fields or unbounded row collections.
Pytest passed 85 tests; an independent P0.3 audit matched all 53 Python fields,
and Poetry/dependency checks, JSON/non-finite validation, compilation,
wheel/sdist build, dependency-free isolated-wheel import, local links, dotenv
scan, and `git diff --check` passed.

Done: 2026-08-09 — installed `empire-stonks-tech-indicators` after the pinned
binary calculation runtime and OHLCV package in
`deploy/docker/airflow/Dockerfile`; amended the runtime contract and README.
`make airflow-build` completed 21 steps, and final CPython 3.13.13/Airflow
3.2.1 one-offs proved technical-indicators 0.1.0, Core 0.1.0, reports 0.1.0,
OHLCV 0.1.0, NumPy 2.4.6, and TA-Lib/C 0.7.1 coexist; the 65-column model,
calculation smoke, `pip check`, bundled-native `ldd`, Airflow CLI, local-link,
and `git diff --check` checks passed.

Done: 2026-08-09 — added all ten non-secret V1 settings to tracked
`deploy/env/local.example.env`, the ignored active `deploy/env/local.env`, and
the shared Airflow environment in `deploy/compose/airflow.yml`; updated the
runtime contract and README. Both environment files loaded the exact safe
config, Compose rendered all ten values across all six Airflow services from
each file, the image contained no embedded settings, and pytest (85), Poetry
lock, `pip check`, configuration-isolation scans, and `git diff --check`
passed.

---
