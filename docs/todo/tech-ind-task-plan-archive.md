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

## Phase 2: Implement The Database Contract

Goal: create the smallest durable schema supporting fast current-state reads
and the proven incremental strategy.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| S2.1 | [x] | Finalize payload/view columns | Translate the design-contract baseline into exact PostgreSQL names, types, generated expressions, nullability, copied OHLCV, view projection, metadata, and comments; both payload slots share the exact 90-column profile and every column has one formula owner. | P0.3-P0.9, B1.2 |
| S2.2 | [x] | Finalize auxiliary state schemas | Based on B1.2, explicitly reject or design minimal recurrence state, and translate P0.9's two slots, publication lifecycle, membership, and published view without generic markers or mixed visibility. | B1.2, P0.9, S2.1 |
| S2.3 | [x] | Finalize keys and constraints | Define PK/source FK, benchmark/Core/publication FKs, delete actions, version checks, basic bounds, streak/relative row shape, and Python-owned validation boundary. | S2.1-S2.2 |
| S2.4 | [x] | Design initial indexes | Use representative latest-date scans, listing history, backfill, rankings, and correction queries to select minimal indexes with `EXPLAIN` evidence. | P0.8, S2.1-S2.3 |
| S2.5 | [x] | Add Flyway migration | Create both payload slots, publication/membership state, the `ohlcv_daily_tech_indicators` published view, any proven recurrence state, comments, constraints, and indexes; migrate and validate successfully. | S2.1-S2.4 |
| S2.6 | [x] | Add schema contract tests | Add rollback-only SQL tests for keys, cascades, generated formulas, warm-up nulls, bounds, benchmark/publication dependencies, duplicates, and valid rows. | S2.5 |
| S2.7 | [x] | Add OHLCV regression | Prove no provider-identity, provider-isolation, source-cleanup, or existing-writer regression. | S2.5-S2.6 |
| S2.8 | [x] | Add database documentation group | Add technical tables to Stonks docs, regenerate schema/ERD/diagrams, and verify no stale artifacts. | S2.5-S2.7 |

Done: 2026-08-09 — froze the shared ordered 90-column slot/view DDL,
source-compatible copied types, all 23 `DOUBLE PRECISION` stored expressions,
65-column writer boundary, metadata/default ownership, and SQL comment contract
in `docs/stonks/tech-indicators-payload-schema-v1.md`; linked the design
handoff. A rolled-back PostgreSQL temporary table compiled all expressions and
matched nine representative generated values; pytest passed 85 tests; Poetry
lock/public imports passed; independent profile/model/schema audits passed (90
= 9 + 5 + 53 + 23, 65 writable fields, identical explicit view projection,
23 generated owners, 90 comment mappings); `make db-validate` validated 38
migrations; local-link, forbidden-field, and `git diff --check` scans passed.

Done: 2026-08-09 — rejected V1 recurrence state and froze exact publication
and membership columns, five unit kinds, three publication methods, six
statuses, normalized scope/benchmark/count/report/resume facts,
`PRESENT`/`REMOVE` per-listing slot
membership, cleanup-safe evidence, and explicit 90-column A/B view SQL in
`docs/stonks/tech-indicators-publication-schema-v1.md`; linked the payload,
publication, and design contracts. Rolled-back PostgreSQL compilation and
visibility fixtures passed; schema/view/lifecycle audits matched 41
publication columns, 16 membership columns, and 90 columns per view arm;
pytest (85), Poetry lock/public imports, `make db-validate` (38 migrations),
local-link, forbidden-marker, whitespace, and `git diff --check` checks passed.

Done: 2026-08-09 — froze payload, publication, and membership PKs/FKs/delete
actions, version/source/streak/bounds/SPX/count/cursor/lifecycle checks, the
one-active-membership integrity index, transition/cross-relation triggers, the
existing single-credential grant boundary, and Python-owned exhaustive
validation in `docs/stonks/tech-indicators-constraints-v1.md`; linked the
payload, publication, and design contracts. Rolled-back PostgreSQL compilation,
constraint/delete-action/lifecycle fixtures, and Core/report cleanup passed;
pytest (85), Poetry lock/public imports, `make db-validate` (38 migrations),
contract/link/whitespace, and `git diff --check` checks passed.

Done: 2026-08-09 — froze exactly one date-leading B-tree per payload slot and
no auxiliary or feature-specific access indexes in
`docs/stonks/tech-indicators-indexes-v1.md`; primary keys retain listing
history, backfill/resume, and correction ownership. Five-run read-only
PostgreSQL 18.4 plans over 20,684,494 live OHLCV rows proved 16,238-row paged
history, a 21,276-row latest slice/rank, 50,000-row backfill, and 50,000-row
drift paths with no temporary I/O; the rank quicksort used 2,264 kB at 4 MB
`work_mem`. Rolled-back index DDL/catalog checks, pytest (85), Poetry
lock/public imports, `make db-validate` (38 migrations), contract, local-link,
whitespace, fixture-residue, and `git diff --check` checks passed.

Done: 2026-08-09 — added and applied
`db/flyway/sql/V2026.08.09.0001__stonks_create_tech_indicators.sql` with both
90-column/23-generated-column payload slots, 41-column publication and
16-column membership state, exact constraints/delete actions, lifecycle
triggers, three designed secondary/integrity indexes, comments, and the
explicit non-updatable 90-column A/B published view; no recurrence state or
extra grants/indexes were added. Catalog audits found zero slot/view signature
drift, complete comments, 13 intended FKs, 35 checks, seven total indexes, and
both triggers. A rolled-back A/B publish/deactivate/retire fixture passed with
generated-value and visibility assertions; Flyway migrated and validated 39
migrations, pytest passed 85 tests, Poetry lock/public imports and migration-
source/whitespace/fixture-residue/`git diff --check` audits passed.

Done: 2026-08-09 — added the rollback-only
`db/tests/stonks/tech_indicators_schema_contract.sql` suite and
`make db-test-tech-indicators-schema` target. The suite passed with 64 exact
expected failures plus valid A/B rows, all 23 generated formulas, warm-up
nulls, catalog shape, keys, duplicates, bounds, benchmark/Core/publication
dependencies, lifecycle/view visibility, and delete/cascade assertions; it
left zero fixture residue. The existing OHLCV contract suite passed; pytest
passed 85 tests; Poetry lock/public import, Flyway validation (39 migrations),
whitespace, transaction-boundary, and `git diff --check` audits passed.

Done: 2026-08-09 — added rollback-only PostgreSQL compatibility coverage in
`test_tech_indicators_ohlcv_regression_integration.py` under
`packages/empire-stonks-ohlcv/tests`. Two tests prove exact
case-sensitive provider identity, three-provider source/payload isolation,
existing listing and daily-bar insert/unchanged/gap/correction/derived-repair
writes with technical children, and source-row/provider cleanup cascades that
leave unrelated providers intact. The focused regression passed 7 tests and
the full database-enabled OHLCV suite passed 608; both schema contracts,
Poetry lock/compile/public imports, Flyway validation (39 migrations),
88-column/fixture-residue/`git diff --check` audits passed.

Done: 2026-08-09 — added the nine-table `tech-indicators` Stonks database
documentation group and inventory entry; regenerated canonical schema SQL,
full/grouped Mermaid ERDs, and full/grouped pg-diagram SVG/PNG artifacts.
Hardened the pg-diagram SQL filter to remove complete dollar-quoted functions
before statement parsing. Inventory audits matched 12 definitions, 24 grouped
Mermaid files, and 48 grouped images with no stale or empty artifacts; all 26
PNG and 26 SVG files had valid signatures, and both new diagrams passed visual
inspection. Flyway validated 39 migrations, both OHLCV and technical-indicator
schema contracts passed (the latter with 64 expected failures), and filter
compilation and `git diff --check` passed.

---

## Phase 3: Build Input, Scope, And Readiness Services

Goal: provide deterministic chronological inputs and explicit source readiness
without coupling calculations to source runners or Airflow.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| I3.1 | [x] | Add eligible-listing queries | Implement provider/market/type/status/date selection from P0.6; cover active, inactive, insufficient-history, and explicit selections. | P0.6, B1.6, S2.5 |
| I3.2 | [x] | Add chronological bar reader | Stream/page exact OHLCV in listing/date order without whole-universe memory load; cover null volume, gaps, negative-capable values, and ordering. | I3.1 |
| I3.3 | [x] | Add SPX resolver | Resolve exactly one reviewed active `YAHOO/XIDX/SPX` and fail closed on missing, duplicate, inactive, or metadata drift. | P0.5, I3.1 |
| I3.4 | [x] | Add benchmark bar reader | Load exact-date SPX history for ratio, relative return, beta, and correlation without forward fill. | I3.2-I3.3 |
| I3.5 | [x] | Add state-comparison queries | Detect missing rows, copied-source drift, version drift, and earliest changed dates needed by recalculation. | P0.7, S2.5, I3.2 |
| I3.6 | [x] | Add source-readiness decision | Decide effective-date readiness from OHLCV/SPX coverage and successful source evidence where required, not wall-clock ordering alone. | P0.5-P0.7, I3.3-I3.5 |
| I3.7 | [x] | Verify large-read behavior | Exercise query plans, paging, transaction ownership, cancellation, and memory bounds at representative size. | P0.8, I3.1-I3.6 |

Done: 2026-08-09 — added public caller-transaction-owned P0.6 selection and
scoped coverage in `empire_stonks_tech_indicators/queries.py`, with active,
explicit inactive, exact provider/market/type predicates, inclusive dates, and
zero/short-history coverage plus unit/PostgreSQL tests and README handoff.
Package pytest passed 96 tests with 1 expected Core-runtime skip; the focused
rollback-only PostgreSQL test passed 1 test. Wheel/sdist build, Poetry lock,
compilation, public import, `pip check`, 88-column scan, `git diff --check`, and
Flyway validation of 39 migrations passed.

Done: 2026-08-09 — added public keyset-paged chronological OHLCV reads in
`empire_stonks_tech_indicators/queries.py`, reusing I3.1 selection and the
configured 1,000-50,000 page bounds while preserving exact `Decimal` values,
null/zero volume, negative prices, calendar gaps, and deterministic provider/
listing/date order without transaction mutation. Package pytest passed 102
tests with 1 expected Core-runtime skip; the focused rollback-only PostgreSQL
suite passed 2 tests, including the I3.2 reader, and the 1,002-row unit fixture
crossed two pages. Wheel/sdist build, Poetry lock, compilation, public import,
`pip check`, changed-Python 88-column scan, `git diff --check`, and Flyway
validation of 39 migrations passed.

Done: 2026-08-09 — added public fail-closed SPX resolution in
`empire_stonks_tech_indicators/queries.py`, using injected frozen benchmark
configuration for an exact bounded `YAHOO/XIDX/SPX` lookup and separately
validating one row, active status, `EQUITY_INDEX`, object metadata, exact
`YahooTicker=^GSPC`, and the generated UUID through `ResolvedBenchmark`.
Package pytest passed 112 tests with 1 expected Core-runtime skip; the focused
rollback-only PostgreSQL suite passed 3 tests, including live SPX success and
inactive/type/metadata drift. Wheel/sdist build, Poetry lock, compilation,
public import, `pip check`, changed-Python 88-column scan, `git diff --check`,
and Flyway validation of 39 migrations passed.

Done: 2026-08-09 — added public immutable `BenchmarkHistory` and
`load_spx_benchmark_history()` in
`empire_stonks_tech_indicators/queries.py`, resolving reviewed SPX then reusing
bounded source pages to retain strictly chronological exact-date OHLCV with
binary exact lookup and no synthetic, nearest-date, or forward-filled values.
Package pytest passed 120 tests with 1 expected Core-runtime skip; the focused
rollback-only PostgreSQL suite passed 4 tests, including a live stored SPX gap.
Wheel/sdist build, Poetry check/lock, compilation, public import, `pip check`,
changed-Python 88-column scan, `git diff --check`, and Flyway validation of 39
migrations passed.

Done: 2026-08-09 — added public paged `ListingStateComparison` and
`iter_state_comparison_pages()` in `empire_stonks_tech_indicators/state.py`,
using one set-based published-view comparison to distinguish tail appends from
historical missing rows and detect exact null-safe OHLCV-copy, chronological-
count, and requested-version drift with conservative earliest dates. Package
pytest passed 133 tests with 1 expected Core-runtime skip; the focused
rollback-only PostgreSQL suite passed 5 tests, including valid A-slot drift and
equivalent rerun fixtures. Wheel/sdist build, Poetry check/lock, compilation,
public import, `pip check`, changed-Python 88-column scan, `git diff --check`,
and Flyway validation of 39 migrations passed.

Done: 2026-08-09 — added public `SourceReadinessDecision` and
`decide_source_readiness()` in
`empire_stonks_tech_indicators/readiness.py`, combining exact eligible-scope
OHLCV/SPX coverage with healthy benchmark resolution and effective-date-
matched successful EODData/Yahoo Core evidence rather than task timing; Stooq
remains coverage-driven. Package pytest passed 141 tests with 1 expected Core-
runtime skip; the focused rollback-only PostgreSQL suite passed 6 tests,
including live ready 2026-08-03 and same-listing wrong-date failure. Wheel/
sdist build, Poetry check/lock, compilation, public import, `pip check`, wheel-
content and changed-Python 88-column scans, `git diff --check`, and Flyway
validation of 39 migrations passed.

Done: 2026-08-09 — added the read-only I3.7 live probe and evidence in
`tools/tech-indicators/large-read-smoke.py` and
`docs/stonks/tech-indicators-large-read-evidence-i3.7.md`, and corrected
`queries.py` source paging to primary-key `(provider_listing_id, trading_date)`
order. Against 20,684,494 OHLCV rows and 22,261 eligible listings, the
16,238-row public read paged 10,000/6,238 and the full scope filled a 10,000-row
page at 103.83 MiB RSS; five-run 50,000-row source/drift plans had 7.57/8.03 ms
and 6.77/7.15 ms median/max, no temp I/O,
and cancellation plus caller rollback recovery passed. Package pytest passed
141 tests with 1 expected skip; rollback-only PostgreSQL passed 6 tests;
Poetry check/build, compilation, `pip check`, `git diff --check`, and Flyway
validation of 39 migrations passed.

---

## Phase 4: Implement Deterministic Core Features

Goal: calculate non-TA-Lib features as pure, independently tested operations.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| C4.1 | [x] | Normalize calculation arrays | Convert ordered source values to contiguous arrays with null masks and no silent reorder, zero fill, or look-ahead. | B1.6, I3.2 |
| C4.2 | [x] | Calculate returns | Implement 1/2/3/5/10/20/63/126/252-observation returns with agreed zero-denominator and warm-up behavior. | P0.4, C4.1 |
| C4.3 | [x] | Calculate bar structure | Implement gap, intraday return, range, close location, dollar volume, and copied source values; cover zero range and null volume. | P0.4, C4.1 |
| C4.4 | [x] | Calculate range relationships | Implement 20/50/252 highs and 20/50 lows without forward leakage. | P0.4, C4.1 |
| C4.5 | [x] | Calculate volume and liquidity | Implement 20/60 average volume and 20 average dollar volume with missing-volume and complete-window rules. | P0.4, C4.1, C4.3 |
| C4.6 | [x] | Calculate streak state | Implement up/down streaks with unchanged close resetting both; prove append/rebuild equivalence. | P0.4, C4.1 |
| C4.7 | [x] | Calculate return statistics | Implement 20/60 return volatility and defined 1d/3d 20-observation z-scores with zero-variance behavior. | P0.4, C4.1-C4.2 |
| C4.8 | [x] | Add core golden fixtures | Compare independent formulas, trustworthy legacy examples, gaps, discontinuities, short histories, and randomized invariants. | C4.2-C4.7 |

Done: 2026-08-11 — added public lazy-loaded `CalculationArrays` and
`normalize_source_bars()` in `empire_stonks_tech_indicators/arrays.py` with
strict single-listing/date-order checks, exact attached source bars, read-only
contiguous `float64` OHLCV, explicit nullable-volume masks, and finite-
conversion failure; documented and tested gaps, prefix independence, negative/
zero values, missing volume, tampering, mixed/reversed input, and overflow.
Package pytest passed 155 tests with 1 expected Core-runtime skip; Poetry lock,
`pip check`, wheel/sdist build, compileall, NumPy 2.4.6/TA-Lib 0.7.1 runtime
smoke, public/cold imports, and `git diff --check` passed.

Done: 2026-08-11 — added public lazy-loaded `MaskedFloatArray`,
`ReturnArrays`, and `calculate_returns()` in
`empire_stonks_tech_indicators/{arrays,returns}.py` for all nine V1 observation
lags with exact warm-up masks, exact-zero prior-close nulls, negative/tiny
nonzero denominator support, finite-output failure, and read-only contiguous
arrays. Tests cover every first-valid index, gaps, zero recovery, unchanged and
negative closes, tiny denominators, prefix independence, masks, dtypes, and
overflow. Package pytest passed 172 tests with 1 expected Core-runtime skip;
Poetry lock, `pip check`, wheel/sdist build, wheel-content inspection,
compileall, NumPy
2.4.6/TA-Lib 0.7.1 runtime smoke, public/cold imports, and `git diff --check`
passed.

Done: 2026-08-11 — added public lazy-loaded `BarStructureArrays` and
`calculate_bar_structure()` in
`empire_stonks_tech_indicators/bar_structure.py`, retaining exact source bars,
calculating Python-owned gap plus four PostgreSQL-generated-column reference
series, and preserving exact-zero/null and finite-output rules without changing
writer ownership. Tests cover first-row warm-up, calendar gaps, zero
denominators/range/volume, null volume, negative prices, `abs(close)` dollar
volume, recovery, copied `Decimal` values, prefix equivalence, masks, overflow,
and ownership. Package pytest passed 181 tests with 1 expected Core-runtime
skip; Poetry lock, `pip check`, wheel/sdist build, wheel-content inspection,
compileall, NumPy 2.4.6/TA-Lib 0.7.1 runtime smoke, public/cold imports, and
`git diff --check` passed.

Done: 2026-08-11 — added public lazy-loaded `RangeRelationshipArrays` and
`calculate_range_relationships()` in
`empire_stonks_tech_indicators/range_relationships.py` for complete trailing
`hh_20`, `hh_50`, `hh_252`, `ll_20`, and `ll_50` observation windows using
current-bar-inclusive NumPy extrema and explicit read-only null masks. Tests
compare every eligible value with independent Python extrema and cover each
warm-up boundary, negative values, calendar gaps, short history, current-bar
participation, future-extreme prefix isolation, dtypes, masks, and invalid
inputs. Package pytest passed 192 tests with 1 expected Core-runtime skip;
Poetry lock, `pip check`, wheel/sdist build, wheel-content inspection,
compileall, NumPy 2.4.6/TA-Lib 0.7.1 runtime smoke, public/cold imports, and
`git diff --check` passed.

Done: 2026-08-11 — added public lazy-loaded `VolumeLiquidityArrays` and
`calculate_volume_liquidity()` in
`empire_stonks_tech_indicators/volume_liquidity.py` for complete
20/60-observation volume averages and the 20-observation nominal dollar-volume
average, consuming C4.3's exactly aligned dollar-volume reference. Tests compare
all windows with independent averages and cover warm-up, calendar gaps, null
window/recovery, zero and fractional-capable volume, negative closes, short
history, prefix isolation, source mismatch/tampering, masks, dtypes, overflow,
and invalid inputs. Package pytest passed 203 tests with 1 expected Core-runtime
skip; Poetry lock, `pip check`, wheel/sdist build, wheel-content inspection,
compileall, NumPy 2.4.6/TA-Lib 0.7.1 runtime smoke, public/cold imports, and
`git diff --check` passed.

Done: 2026-08-11 — added public lazy-loaded `StreakArrays` and
`calculate_streaks()` in `empire_stonks_tech_indicators/streaks.py` with
non-null read-only `int64` up/down counts, zero initialization, strict close
direction, and unchanged-close reset semantics over the complete source prefix.
Tests cover positive/negative/unchanged transitions, calendar gaps, long
streaks, mutual exclusivity, dtypes, immutability, repeated full-prefix append
runs, and independent append-state equivalence at every split. Package pytest
passed 211 tests with 1 expected Core-runtime skip; Poetry lock, `pip check`,
wheel/sdist build, wheel-content inspection, compileall, NumPy 2.4.6/TA-Lib
0.7.1 runtime smoke, public/cold imports, and `git diff --check` passed.

Done: 2026-08-11 — added public lazy-loaded `ReturnStatisticArrays` and
`calculate_return_statistics()` in
`empire_stonks_tech_indicators/return_statistics.py` for nonannualized
20/60-return sample volatility and current-excluded, prior-20-reference 1d/3d
return z-scores, with complete-window masks, exact-zero-variance nulls,
finite-output failure, and exact normalized-source/return alignment. Tests use
independent sample estimators and cover every warm-up, calendar gaps, null
window recovery, constant returns, prefix isolation, tampering, dtypes, masks,
overflow, and invalid inputs. Focused pytest passed 36 tests; package pytest
passed 223 tests with 1 expected Core-runtime skip. Poetry lock, `pip check`,
wheel/sdist build and content inspection, compileall, NumPy 2.4.6/TA-Lib 0.7.1
runtime smoke, public/cold imports, and `git diff --check` passed.

Done: 2026-08-11 — added `tests/fixtures/core_features_v1.json` and
`tests/test_core_golden.py` as the combined C4.2-C4.7 regression gate. The
committed goldens preserve the legacy Stonks engine's 260-bar overlap for
`hh_20`, `ll_20`, and `volume_avg_20` plus an unadjusted discontinuity/calendar
gap; an independent standard-library scalar oracle checks every core value and
null mask across four short histories and 840 seeded randomized bars under the
frozen tolerance, with whole-family future-prefix isolation. Focused pytest
passed 9 tests; package pytest passed 232 tests with 1 expected Core-runtime
skip. Poetry lock, `pip check`, wheel/sdist build and content inspection,
compileall, NumPy 2.4.6/TA-Lib 0.7.1 runtime smoke, and `git diff --check`
passed.

---

## Phase 5: Implement TA-Lib Feature Families

Goal: expose reviewed TA-Lib calculations through stable Empire contracts with
explicit warm-up and version semantics.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| T5.1 | [x] | Add TA-Lib adapter | Accept normalized arrays, record library/version, convert non-finite warm-up output to null masks, and hide TA-Lib types. | B1.1-B1.2, C4.1 |
| T5.2 | [x] | Calculate SMA and EMA | Implement SMA 20/50/200 and EMA 12/20/26/50 with agreed initialization and full/incremental equivalence. | P0.4, T5.1 |
| T5.3 | [x] | Calculate average changes | Implement 20-observation SMA 50/200 changes and inputs for generated price/average distances. | C4.2, T5.2 |
| T5.4 | [x] | Calculate RSI and ATR | Implement Wilder RSI 14 and ATR 14 with independent references and correction replay. | P0.4, T5.1 |
| T5.5 | [x] | Calculate Bollinger state | Implement price standard deviation, `%b`, and BandWidth for the fixed 20/2 contract; do not store redundant bands. | P0.4, T5.1-T5.2 |
| T5.6 | [x] | Calculate ADX and DMI | Implement +DI 14, -DI 14, and ADX 14 with Wilder smoothing and unstable-period policy. | P0.4, T5.1, T5.4 |
| T5.7 | [x] | Calculate MACD | Implement 12/26/9 line, signal, histogram, and normalized values with fixed scale and zero handling. | P0.4, T5.1-T5.2 |
| T5.8 | [x] | Add combined TA-Lib regression | Compare pinned-library fixtures, edge cases, trustworthy legacy examples, and an independent reference per family. | T5.2-T5.7 |

Done: 2026-08-11 — added public lazy-loaded `TALibAdapter` and
`TALibRuntimeInfo` in `empire_stonks_tech_indicators/talib_adapter.py` for the
exact NumPy 2.4.6/TA-Lib Python and C 0.7.1 runtime, normalized-array-only
inputs, default/zero global-setting enforcement, explicit reviewed calls, and
Empire-owned warm-up masks with hard post-lookback non-finite failure. Focused
pytest passed 27 tests; package pytest passed 251 tests with 1 expected
Core-runtime skip. Poetry lock, `pip check`, wheel/sdist build and content
inspection, compileall, pinned runtime smoke, cold lazy-import, 88-column, and
`git diff --check` checks passed.

Done: 2026-08-11 — added public lazy-loaded `MovingAverageArrays` and
`calculate_moving_averages()` in
`empire_stonks_tech_indicators/moving_averages.py` for exact TA-Lib SMA
20/50/200 and EMA 12/20/26/50 calls from the complete source prefix, preserving
the frozen SMA seed, EMA recursion, and null boundaries without adding T5.3
distances or changes. Independent scalar references plus append and correction
suffix composition passed in 44 focused tests; package pytest passed 268 tests
with 1 expected Core-runtime skip. Poetry lock, `pip check`, wheel/sdist build
and content inspection, compileall, pinned runtime smoke, cold lazy-import,
88-column, and `git diff --check` checks passed.

Done: 2026-08-11 — added public lazy-loaded `MovingAverageTrendArrays` and
`calculate_moving_average_trends()` in
`empire_stonks_tech_indicators/moving_average_trends.py` for the persisted
20-observation SMA 50/200 changes and eight PostgreSQL-generated close/average
and SMA-spread reference series, with exact-zero/null rules and strict
normalized-source/moving-average alignment. Independent formulas, all first-
valid boundaries, short/zero/negative-capable histories, prefix isolation,
tampering, and overflow passed in 61 focused tests; package pytest passed 285
tests with 1 expected Core-runtime skip. Poetry lock, `pip check`, wheel/sdist
build and content inspection, compileall, pinned runtime smoke, cold lazy-
import, 88-column, and `git diff --check` checks passed.

Done: 2026-08-11 — added public lazy-loaded `RsiAtrArrays` and
`calculate_rsi_atr()` in `empire_stonks_tech_indicators/rsi_atr.py` for exact
TA-Lib Wilder RSI 14 and ATR 14 calls from the complete source prefix, leaving
generated `atr_pct_14` ownership unchanged. Independent gain/loss and true-
range scalar recurrences, warm-up seeds, flat/rising/falling zero guards,
calendar gaps, discontinuities, append isolation, and full-prefix correction
suffix composition passed in 37 focused tests; package pytest passed 295 tests
with 1 expected Core-runtime skip. Poetry lock, `pip check`, wheel/sdist build
and content inspection, compileall, pinned runtime smoke, cold lazy-import,
88-column, and `git diff --check` checks passed.

Done: 2026-08-11 — added public lazy-loaded `BollingerStateArrays` and
`calculate_bollinger_state()` in
`empire_stonks_tech_indicators/bollinger.py` for TA-Lib population
`STDDEV(20, 1.0)` plus PostgreSQL-generated fixed-20/2 `%b` and BandWidth
references, with strict SMA-20 alignment and no retained upper/lower bands.
Independent population/band formulas, warm-up, flat positive/negative/zero
middle and width rules, prefix isolation, ownership, and tampering passed in 54
focused tests; package pytest passed 305 tests with 1 expected Core-runtime
skip. Poetry lock, `pip check`, wheel/sdist build and content inspection,
compileall, pinned runtime smoke, cold lazy-import, 88-column, and
`git diff --check` checks passed.

Done: 2026-08-11 — added public lazy-loaded `DirectionalMovementArrays` and
`calculate_directional_movement()` in
`empire_stonks_tech_indicators/directional_movement.py` for exact TA-Lib
Wilder +DI 14, -DI 14, and ADX 14 calls from the complete source prefix with
zero unstable-period enforcement. An independent DM/TR/DI/DX/ADX recurrence,
14/27 warm-up boundaries, negative-capable gaps, tied/up/down/zero movement,
append isolation, correction suffix composition, and unstable-period failure
passed in 48 focused tests; package pytest passed 316 tests with 1 expected
Core-runtime skip. Poetry lock, `pip check`, wheel/sdist build and content
inspection, compileall, pinned runtime smoke, cold lazy-import, 88-column, and
`git diff --check` checks passed.

Done: 2026-08-11 — added public lazy-loaded `MacdArrays` and
`calculate_macd()` in `empire_stonks_tech_indicators/macd.py` for one exact
TA-Lib MACD 12/26/9 call plus PostgreSQL-generated line/EMA-26 and
histogram/close normalized references, preserving the shared observation-33
mask and exact-zero denominator nulls without reconstructing the line from
stored EMAs. Fixed-call, scale, warm-up, flat positive/negative/zero, prefix,
correction suffix, ownership, and tampering checks passed in 56 focused tests;
package pytest passed 328 tests with 1 expected Core-runtime skip. Poetry lock,
`pip check`, wheel/sdist build and content inspection, compileall, runtime
smoke, cold lazy-import, 88-column, and `git diff --check` checks passed.

Done: 2026-08-11 — added
`tests/{test_talib_golden.py,fixtures/talib_features_v1.json}` as the combined
T5.2-T5.7 regression gate for all 30 raw and generated-reference outputs. The
committed NumPy 2.4.6/TA-Lib 0.7.1 goldens preserve the trustworthy seven-field
legacy 260-bar overlap and a provider-native discontinuity; independent
standard-library SMA/EMA, Wilder RSI/ATR/DMI/ADX, population-deviation, MACD,
and generated-expression references cover seeded gaps, negative/tiny values,
and flat positive/negative/zero histories. Focused pytest passed 104 tests;
package pytest passed 336 tests with 1 expected Core-runtime skip. Poetry lock,
`pip check`, wheel/sdist build and content inspection, compileall, pinned
runtime smoke, cold lazy-import, 88-column, and `git diff --check` checks
passed.

---

## Phase 6: Implement SPX-Relative Features

Goal: add exact-date cross-provider market comparison without implying a
canonical identity mapping.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| X6.1 | [x] | Build aligned returns | Align subject/SPX one-day returns by exact date, preserve gaps, and expose aligned counts. | P0.5, I3.4, C4.2 |
| X6.2 | [x] | Calculate SPX price ratio | Implement `rel_spx` and 20/50 ratio-trend distances with denominator and warm-up rules. | P0.5, X6.1, T5.2 |
| X6.3 | [x] | Calculate relative returns | Implement compounded SPX-relative returns for 20/63/126/252 aligned observations. | P0.5, X6.1 |
| X6.4 | [x] | Calculate rolling beta | Implement 60/252 sample-covariance beta; null incomplete windows and zero SPX variance. | P0.5, X6.1 |
| X6.5 | [x] | Calculate rolling correlation | Implement 60/252 Pearson correlation with complete windows and bounded tolerance. | P0.5, X6.1 |
| X6.6 | [x] | Enforce eligible subjects | Populate SPX features only for approved subjects; leave unsupported global/index/futures/commodity/currency series null with bounded reasons. | P0.5-P0.6, X6.2-X6.5 |
| X6.7 | [x] | Test benchmark corrections | Prove inserted, changed, missing, or deleted SPX bars recalculate required subject dates without unrelated mutation. | P0.7, X6.2-X6.6 |
| X6.8 | [x] | Add SPX golden regression | Compare ratio, relative returns, beta, and correlation against independent aligned fixtures covering gaps and low variance. | X6.2-X6.7 |

Done: 2026-08-19 — added public lazy-loaded `AlignedReturnArrays` and
`calculate_aligned_returns()` in `empire_stonks_tech_indicators/spx_alignment.py`
for compact exact-date subject/SPX closes, common-endpoint one-observation
returns, native-subject aligned-close counts, and trailing valid-pair counts
without fill. Focused pytest passed 17 tests; package pytest passed 346 tests
with 1 expected Core-runtime skip. Poetry lock/dependency checks, compileall,
pinned runtime smoke, wheel/sdist build and wheel-content inspection, public
import, changed-Python 88-column scan, and `git diff --check` passed.

Done: 2026-08-19 — added public lazy-loaded `SpxPriceRatioArrays` and
`calculate_spx_price_ratios()` in
`empire_stonks_tech_indicators/spx_price_ratio.py` for subject-row `rel_spx`
and complete current-inclusive 20/50-aligned-observation ratio trends, with
exact-zero SPX/mean denominators, null-window recovery, and no date filling.
Focused pytest passed 27 tests; package pytest passed 356 tests with 1 expected
Core-runtime skip. Poetry lock/dependency checks, compileall, pinned runtime
smoke, wheel/sdist build and wheel-content inspection, public import,
changed-Python 88-column scan, and `git diff --check` passed.

Done: 2026-08-19 — added public lazy-loaded `SpxRelativeReturnArrays` and
`calculate_spx_relative_returns()` in
`empire_stonks_tech_indicators/spx_relative_returns.py` for chronological
compounding over complete 20/63/126/252 aligned-return pairs, subject-row
output, exact-zero SPX gross denominators, invalid-window recovery, and
non-finite product failure. Focused pytest passed 30 tests; package pytest
passed 369 tests with 1 expected Core-runtime skip. Poetry lock/dependency
checks, compileall, pinned runtime smoke, wheel/sdist build and wheel-content
inspection, public import, changed-Python 88-column scan, and `git diff --check`
passed.

Done: 2026-08-19 — added public lazy-loaded `SpxBetaArrays` and
`calculate_spx_beta()` in `empire_stonks_tech_indicators/spx_beta.py` for
complete 60/252 aligned-return windows using sample covariance and sample SPX
variance, with subject-row output, exact-zero variance nulls, invalid-window
recovery, unbounded finite beta, and non-finite statistic failure. Focused
pytest passed 29 tests; package pytest passed 381 tests with 1 expected
Core-runtime skip. Poetry lock/dependency checks, compileall, pinned runtime
smoke, wheel/sdist build and wheel-content inspection, public import,
changed-Python 88-column scan, and `git diff --check` passed.

Done: 2026-08-19 — added public lazy-loaded `SpxCorrelationArrays` and
`calculate_spx_correlation()` in
`empire_stonks_tech_indicators/spx_correlation.py` for complete 60/252
aligned-return Pearson windows, with subject-row output, exact-zero variance
nulls, invalid-window recovery, non-finite failure, and the contract's `1e-12`
boundary-only canonicalization. Focused pytest passed 35 tests; package pytest
passed 399 tests with 1 expected Core-runtime skip. Poetry lock/dependency
checks, compileall, pinned runtime smoke, wheel/sdist build and wheel-content
inspection, isolated public import, changed-Python 88-column scan, and
`git diff --check` passed.

Done: 2026-08-19 — added public lazy-loaded `SpxFeatureArrays`,
`calculate_spx_features()`, and `is_spx_supported_subject()` in
`empire_stonks_tech_indicators/spx_features.py` to compose all 11 SPX fields
only for exact P0.5 EODData/Stooq subject markets. Unsupported Yahoo/global/
index/futures/commodity/currency identities receive a null benchmark, 11
read-only null arrays, and one row-counted `SUBJECT_UNSUPPORTED` reason without
benchmark calculation. Focused pytest passed 92 tests; package pytest passed
421 tests with 1 expected Core-runtime skip. Poetry lock/dependency checks,
compileall, pinned runtime smoke, wheel/sdist build and wheel-content inspection,
isolated public import, changed-Python 88-column scan, and `git diff --check`
passed.

Done: 2026-08-19 — added `tests/test_spx_corrections.py` full-prefix
regressions for inserted and changed SPX bars, missing current dates, and
first/middle/final deletions across all 11 SPX fields. Exact pre-correction
prefixes remain unchanged, conservative suffix replacement equals a fresh
rebuild, unsupported subjects and nonoverlapping supported coverage remain
identical, and source rows are not mutated; W7.5 retains work-range planning.
Focused pytest passed 93 tests; package pytest passed 429 tests with 1 expected
Core-runtime skip. Poetry lock/dependency checks, compileall, pinned runtime
smoke, wheel/sdist build and wheel-content inspection, isolated public import,
changed-Python 88-column scan, and `git diff --check` passed.

Done: 2026-08-19 — added
`tests/{test_spx_golden.py,fixtures/spx_features_v1.json}` as the combined
X6.2-X6.7 regression gate for all 11 SPX outputs. Committed exact-date-gap and
low-nonzero-variance cases are anchored by snapshots, while independent
standard-library scalar alignment, ratio, compounding, sample covariance/
variance, beta, and Pearson formulas compare every value and null mask under
the frozen tolerance. Focused pytest passed 104 tests; package pytest passed
433 tests with 1 expected Core-runtime skip. Fixture JSON validation, Poetry
lock/dependency checks, compileall, pinned runtime smoke, wheel/sdist build and
wheel-content inspection, isolated public import, changed-Python 88-column
scan, and `git diff --check` passed.

---

## Phase 7: Validate And Persist Current Feature State

Goal: write complete validated rows efficiently and idempotently while
preserving caller transaction ownership.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| W7.1 | [x] | Add strict row validation | Validate finite values, copied source, bounds, warm-up nulls, dependencies, benchmark, observation counts, and generated inputs before SQL. | C4.8, T5.8, X6.8 |
| W7.2 | [x] | Assemble complete rows | Merge core, TA-Lib, and SPX outputs without positional drift; every V1 field is intentionally populated or null. | W7.1 |
| W7.3 | [x] | Implement slot bulk upsert | Write bounded active/inactive-slot batches, omit generated columns, preserve copied-equivalent rows, count inserted/updated/unchanged, and avoid no-change updates. | S2.5, W7.2 |
| W7.4 | [x] | Persist optional recurrence state | If S2.2 approved state, write it atomically and prevent advancement without its feature row; otherwise record no writer is needed. | S2.2, W7.3 |
| W7.5 | [x] | Implement affected-range planner | Convert missing rows, source/SPX corrections, and version drift into deterministic work ranges with required prefix and suffix propagation. | I3.5, X6.7, W7.3-W7.4 |
| W7.6 | [x] | Prove rebuild equivalence | Compare full rebuild, append, resume, source correction, SPX correction, and version rebuild within approved tolerance. | B1.2, W7.3-W7.5 |
| W7.7 | [x] | Add published feature queries | Add view-backed date/listing coverage, freshness, version, benchmark, ranking, readiness-token, and one-snapshot model-input reads without strategy thresholds. | S2.4, W7.3 |
| W7.8 | [x] | Add PostgreSQL integration | Cover slot/view visibility, rollback, generated values, idempotency, correction propagation, provider/benchmark isolation, and repeated runs. | W7.3-W7.7 |
| W7.9 | [x] | Benchmark persistence | Measure batches, upserts, index cost, memory, and latest-date latency; adjust only with evidence against P0.8. | P0.8, W7.8 |
| W7.10 | [x] | Implement atomic publication | Implement P0.9's bounded in-place finalizer, inactive-slot build/membership flip, recovery, and fail-closed readiness/model-input queries; prove readers never observe partial dates, mixed versions, incomplete benchmark output, or failed/cancelled work. | P0.9, S2.5, W7.3-W7.6 |

Done: 2026-08-22 — added public full-prefix pre-SQL row validation in
`empire_stonks_tech_indicators/validation.py`, lazy export/README guidance,
and focused coverage in `tests/test_validation.py`. Focused pytest passed 14;
package pytest passed 447 with 1 expected Core-runtime skip. Poetry lock,
`pip check`, compileall, pinned runtime smoke, wheel/sdist build and isolated
lazy wheel import, 88-column/whitespace/`git diff --check`, Flyway validation
of 39 migrations, and the technical schema contract with 64 expected failures
passed.

Done: 2026-08-22 — added public single-pass complete-row assembly in
`empire_stonks_tech_indicators/assembly.py`, shared immutable calculation-state
validation, lazy export/README guidance, and `tests/test_assembly.py`. Focused
assembly/validation/API pytest passed 30; package pytest passed 456 with 1
expected Core-runtime skip. Poetry lock, `pip check`, compileall, pinned
runtime smoke, wheel/sdist build and isolated lazy wheel import,
88-column/whitespace/`git diff --check`, Flyway validation of 39 migrations,
and the technical schema contract with 64 expected failures passed.

Done: 2026-08-22 — added bounded A/B-slot `MERGE` upserts and exact
copied-equivalent slot transfers in
`empire_stonks_tech_indicators/persistence.py`, public API/README integration,
and focused unit/PostgreSQL coverage. Focused pytest passed 16; package pytest
passed 472 with 2 expected Core-runtime skips; the rollback-only PostgreSQL
integration passed 1. Poetry lock, `pip check`, compileall, pinned runtime
smoke, wheel/sdist build and isolated wheel import,
88-column/whitespace/`git diff --check`, Flyway validation of 39 migrations,
and the technical schema contract with 64 expected failures passed.

Done: 2026-08-22 — recorded the ratified B1.2/S2.2 V1 no-recurrence-state
decision in the package README; no state model, table, configuration, or writer
is required or added. The 20,000-row typical/high-offset equivalence prototype
passed with full-prefix output equivalent and bounded replay rejected across
EMA/RSI/ATR/ADX/MACD. Package pytest passed 472 with 2 expected Core-runtime
skips; Flyway validated 39 migrations, the schema contract passed with 64
expected failures and an absent state relation, repository scans found no
state writer/schema, and `git diff --check` passed.

Done: 2026-08-22 — added public deterministic affected-range planning in
`empire_stonks_tech_indicators/affected_ranges.py`, shared lightweight SPX
subject policy, README/API integration, and `tests/test_affected_ranges.py`.
The planner collapses local/SPX/version/explicit reasons per listing, separates
full-prefix calculation from suffix writes, expands unsafe narrowed horizons,
and caps benchmark-only inactive maintenance. Focused pytest passed 24; package
pytest passed 496 with 2 expected Core-runtime skips. Poetry lock, `pip check`,
compileall, pinned runtime smoke, wheel/sdist build and isolated lazy planner
import, changed-Python 88-column/whitespace/`git diff --check`, Flyway
validation of 39 migrations, and the schema contract with 64 expected failures
passed.

Done: 2026-08-22 — added complete 65-column rebuild-equivalence coverage in
`tests/test_rebuild_equivalence.py` plus README guidance for full rebuild,
append, replay-safe resume, source/SPX correction, and version rebuild. Focused
pytest passed 6; planner/assembly/persistence integration pytest passed 55;
package pytest passed 502 with 2 expected Core-runtime skips. Poetry lock,
`pip check`, compileall, pinned runtime smoke, wheel/sdist build, isolated lazy
wheel import, changed-Python 88-column/`git diff --check`, Flyway validation of
39 migrations, and the schema contract with 64 expected failures passed.

Done: 2026-08-22 — added public published-view coverage, threshold-free
freshness/ranking, and fail-closed one-snapshot model-input reads in
`empire_stonks_tech_indicators/published_queries.py`, with API/README and unit/
PostgreSQL coverage. Focused pytest passed 67; package pytest passed 514 with 2
expected Core-runtime skips; rollback-only PostgreSQL query integration passed
8. Poetry lock, `pip check`, compileall, calculation-lazy runtime/wheel import,
wheel/sdist build, changed-Python 88-column/`git diff --check`, Flyway validation
of 39 migrations, and the schema contract with 64 expected failures passed.

Done: 2026-08-22 — added the rollback-only Phase 7 PostgreSQL vertical in
`tests/test_persistence_integration.py`, covering mixed A/B publication,
generated values, rollback, subject/SPX correction suffixes, provider/benchmark
isolation, and repeat-write convergence. Phase 7 PostgreSQL pytest passed 10;
package pytest passed 514 with 2 expected Core-runtime skips; focused OHLCV
regression passed 2. Poetry lock, `pip check`, compileall, wheel/sdist build,
88-column/`git diff --check`, Flyway validation of 39 migrations, and the schema
contract with 64 expected failures passed.

Done: 2026-08-22 — added the disposable logged-schema benchmark in
`tools/tech-indicators/persistence-benchmark.py`, canonical W7.9 evidence, and
README guidance. The 100-listing/1,000,000-row pilot sustained 1,049.65
calculated/validated/persisted rows/s with 400.73 MiB peak RSS and a 0.636 s
maximum 5,000-row transaction; two slots project to 35.87 GiB. Five-run
history/slice/rank/coverage plans passed, the 25,000-row rank used 2,526 KiB
with no temp I/O, and no index or write-batch change was justified. Package
pytest passed 514 with 2 expected Core-runtime skips; PostgreSQL integration
passed 10 and OHLCV regression passed 2. Poetry lock, `pip check`, compileall,
wheel/sdist build, harness smoke/zero-residue checks, 88-column/
`git diff --check`, Flyway validation of 39 migrations, and the schema contract
with 64 expected failures passed.

Done: 2026-08-22 — added lock-transaction-owned atomic finalization and
recovery in `empire_stonks_tech_indicators/publication.py`, public API/README
integration, and `tests/test_publication_integration.py`. Focused PostgreSQL
pytest passed 5, including staged/in-place flips, partial-date/mixed-version/
benchmark/cancelled rejection, idempotent recovery, and three-connection MVCC;
the Phase 7 PostgreSQL suite passed 15 with zero fixture residue. Package pytest
passed 514 with 3 expected integration/Core-runtime skips; focused OHLCV
regression passed 2. Poetry lock, `pip check`, compileall, wheel/sdist build and
isolated wheel import, changed-Python 88-column/`git diff --check`, Flyway
validation of 39 migrations, and the schema contract with 64 expected failures
passed.

---
