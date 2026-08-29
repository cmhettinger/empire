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

## Phase 8: Build JSON And Professional PDF Reports

Goal: make every run operationally inspectable before production runners.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| R8.1 | [x] | Define report schema V1 | Define secret-safe JSON for identity, scope, versions, source/publication readiness, lock outcome, provider/market/listing counts, writes, warm-up/null/benchmark coverage, warnings, timing, throughput, and bounded samples. | P0.2, P0.8-P0.10, W7.7 |
| R8.2 | [x] | Add summary queries | Implement provider/market/type/date/version quality and coverage aggregations without serializing feature payloads; plans meet P0.8. | W7.7-W7.9, R8.1 |
| R8.3 | [x] | Build JSON report | Produce deterministic versioned JSON for success, warning, no-op, resumed/partial backfill, and failure. | R8.1-R8.2 |
| R8.4 | [x] | Store JSON report | Store durable `report.json` through Core with approved kind, logical name, metadata, retention, and run relationship. | R8.3 |
| R8.5 | [x] | Design professional PDF | Define Empire cover/disclaimer, status, scope, coverage, formula/library versions, benchmark health, quality, performance, warnings, and methodology without recommendations. | R8.1-R8.3 |
| R8.6 | [x] | Implement PDF renderer | Use reusable `empire-reports` components, bounded tables/charts, deterministic pagination, and accessible labels. | R8.5 |
| R8.7 | [x] | Visually verify PDF | Render success, warning, no-op, and large-scope reports; inspect every page for clipping, overflow, sparse layouts, charts, and branding. | R8.6 |
| R8.8 | [x] | Store PDF report | Store durable `report.pdf` with matching Core lineage/metadata and prove JSON/PDF facts agree. | R8.4, R8.7 |

Done: 2026-08-22 — froze the shared daily/backfill JSON fact shape, outcomes,
readiness/lock/publication semantics, count equations, coverage/null reasons,
performance denominators, 100-sample ceiling, disclosures, and Core metadata
allowlist in `docs/stonks/tech-indicators-report-schema-v1.md`; linked the
design contract and package README. Contract marker/count/schema checks,
documentation links, package pytest (514 passed, 3 skipped), Poetry lock/build,
`pip check`, compileall, public import, Flyway validation (39 migrations),
whitespace,
and `git diff --check` passed.

Done: 2026-08-22 — added count-only active/candidate summaries in
`reporting_queries.py`, PostgreSQL/unit coverage, README guidance, and the
repeatable R8.2 probe/evidence. Verified `519 passed, 3 skipped`; query
integration `9 passed`; wheel/sdist build and public import; 1,000,000-row
five-run plans at `481.562 ms` median / `495.921 ms` maximum with zero temp I/O
(`9.91 s` / `10.21 s` linear P0.8 full-scope projections).

Done: 2026-08-22 — added immutable schema-V1 models, fixed vocabularies,
R8.2 fact adapters, cross-section validation, and bounded deterministic JSON in
`reports.py`, with public API/contract/README updates. Verified focused
`18 passed`; full package `530 passed, 3 skipped`; wheel/sdist build, public
import, wheel contents, and `git diff --check`.

Done: 2026-08-22 — added Core-backed durable JSON storage in
`report_storage.py`, exact run/date keys, logical names, metadata allowlist,
active-run validation, Core dependency, public API, docs, and tests. Verified
focused `11 passed`; full package `541 passed, 16 skipped`; Poetry lock/check,
`pip check`, wheel/sdist dependency/content and public import, compilation,
88-column scan, and `git diff --check`.

Done: 2026-08-22 — froze the Empire PDF presentation, accessibility, fixed
section order, ten-family/76-feature quality rollup, benchmark/performance
language, bounded diagnostics, compaction, and methodology in
`docs/stonks/tech-indicators-pdf-design-v1.md`; linked the report/design
contracts and package README. Verified contract mapping (76 unique fields, 10
families, 5 outcomes), links (4 files), tech report/storage tests (`22 passed`),
shared PDF/branding/contracts tests (`10 passed`), and `git diff --check`.

Done: 2026-08-22 — added the typed professional renderer in `report_pdf.py`,
ten-family chart/table rollups, bounded exceptions/diagnostics, fixed outcome
and methodology language, public API/dependency wiring, and reusable page/byte
bounds plus long-title fitting in `empire-reports`. Verified tech package `550
passed, 16 skipped`; reports package `21 passed`; wheel/sdist build, dependency
metadata/content, public import, compileall, Poetry lock/check, `pip check`, and
`git diff --check`; rendered and inspected an 11-page, 174,224-byte PASS PDF
with nine numbered/headered body pages.

Done: 2026-08-22 — rendered PASS, WARN, NO_OP, FAIL, resumed PARTIAL backfill,
and 100-sample maximum fixtures; recorded R8.7 evidence and a maximum-sample
regression. Poppler/pypdf verified six Letter PDFs, 68/68 visually inspected
pages, 11/11/11/11/12/12 pages, 174,224/174,285/174,207/174,257/175,387/
177,374 bytes, all 56 body headers/footers/page numbers, fixed section/status/
resume text, repeated diagnostic headers, and the 25-page/5-MiB bounds; focused
PDF tests passed 10, report/PDF/exception tests passed 28, full tech package
passed 551 with 16 environment-gated skips, full reports package passed 21,
and `git diff --check` passed.

Done: 2026-08-22 — added Core-backed durable PDF storage in
`report_storage.py` with frozen daily/backfill logical names, object kind,
media type, filename, shared active-run/key/metadata validation, and no
expiration; added public API, README, valid-artifact, and immutable paired-fact
coverage. Verified storage tests `14 passed`; report/storage/PDF/API tests `42
passed`; full tech package `554 passed, 16 skipped`; reports package `21
passed`; an 11-page stored PDF with Poppler/pypdf; Poetry lock/check, build,
`pip check`, compileall, public import, wheel contents, 88-column scan, and
`git diff --check`.

---

## Phase 9: Implement Daily And Backfill Runners

Goal: own complete Core-tracked workflows in the package while callers provide
runtime services and explicit scope.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| J9.1 | [x] | Add Core lifecycle | Start, heartbeat, succeed, fail, and summarize jobs with stable identity and no source/feature payloads in Core metadata. | P0.2, B1.6 |
| J9.2 | [x] | Define daily scope | Add effective date, provider/market/listing filters, readiness, version, dry-run, and force semantics; reject ambiguity. | P0.7, I3.6, W7.5 |
| J9.9 | [x] | Add package-owned writer lock | Implement P0.10's single PostgreSQL transaction advisory lock on a dedicated connection; all mutating scopes share it, contention returns immediately without workflow state, heartbeats detect loss, terminal publication uses the lock connection, and every terminal path releases it. | P0.10, J9.1-J9.2 |
| J9.3 | [x] | Implement daily runner | Sequence lock acquisition, readiness, planning, calculation, validation, atomic publication, summaries, JSON/PDF storage, and Core completion. | W7.8, W7.10, R8.8, J9.1-J9.2, J9.9 |
| J9.4 | [x] | Implement healthy no-op | No eligible new/corrected/version work succeeds with explicit readiness and durable reports but no writes. | J9.3 |
| J9.5 | [x] | Define backfill scope | Add provider/market/listing/date ranges, batches, resume cursor, version, rebuild, and confirmation for broad scopes. | P0.7-P0.8, W7.5 |
| J9.6 | [x] | Implement resumable backfill | Process deterministic inactive-slot batches with independent commits, unpublished partial progress, heartbeats, reports, exact resume, and no duplicate work; flip membership only for a complete P0.9 unit. | W7.9-W7.10, R8.8, J9.1, J9.5, J9.9 |
| J9.7 | [x] | Add failure safety | Validation, DB, cancellation, report, and benchmark failures mark Core correctly, preserve only safely resumable unpublished chunks, roll back active work, never advance publication readiness, release locks, and expose safe errors. | J9.3-J9.6, J9.9 |
| J9.8 | [x] | Add vertical runner integration | Run append, no-op, correction, version rebuild, and resumed backfill through PostgreSQL, Core, JSON, and PDF with zero fixture residue. | J9.3-J9.7 |

Done: 2026-08-23 — added immutable aggregate-only Core start/heartbeat/succeed/
fail handling in `core_lifecycle.py`, public API/README guidance, and unit plus
cleanup-safe PostgreSQL coverage. Focused lifecycle/API pytest passed 21; full
package pytest passed 584. Poetry lock/dependency/compile checks, 88-column
scan, wheel/sdist build and source/wheel imports, Flyway validation of 39
migrations, zero Core fixture residue, and `git diff --check` passed.

Done: 2026-08-23 — added canonical exact-date daily request/resolution in
`daily_scope.py`, same-resolution I3.6 readiness, P0.10 hash/scoped Core
identity, W7.5 force IDs, R8.1 report projection, public API/README guidance,
and focused/unit/PostgreSQL coverage. Focused pytest passed 80; full package
pytest passed 584 with 17 skips; rollback-only PostgreSQL pytest passed 9.
Poetry check, `pip check`, compileall, 88-column scan, wheel/sdist build and
isolated wheel import, Flyway validation of 39 migrations, and
`git diff --check` passed.

Done: 2026-08-23 — added the single-use package-owned P0.10 transaction lock
in `writer_lock.py`, including fixed-key nonblocking acquisition, bounded
contention/exit-75 facts, dedicated-connection heartbeat/loss, terminal-cursor
commit, rollback/context cleanup, safe errors, public API/README guidance, and
unit plus live concurrency coverage. Focused pytest passed 69; full package
pytest passed 606 with 20 skips; PostgreSQL lock/publication/query integration
passed 17 with zero workflow-state drift. Poetry check, `pip check`,
compileall, 88-column scan, wheel/sdist build and isolated wheel import,
Flyway validation of 39 migrations, and `git diff --check` passed.

Done: 2026-08-23 — added `daily_runner.py` and `daily_publication.py` for the
non-empty daily/dry-run vertical, rollback-only exact candidate summaries,
durable JSON/PDF evidence, Core completion, and lock-transaction publication;
added API/README guidance and unit/PostgreSQL vertical coverage. Full package
pytest passed 615 with 23 skips; focused PostgreSQL passed 12, including dry
and atomic published JSON/PDF verticals with zero residue. Poetry check/
compile, 88-column scan, sdist/wheel build and isolated imports, Flyway
validation of 39 migrations, and `git diff --check` passed.

Done: 2026-08-23 — added the published-readiness-backed healthy no-op branch
in `daily_runner.py`, durable `NO_OP` JSON/PDF and Core evidence, second-token
drift protection, dry-zero semantics, README guidance, and live zero-write
coverage in `test_daily_noop_integration.py`. Full package pytest passed 616
with 24 skips; focused PostgreSQL passed 13 with zero fixture residue. Poetry
check, compileall, 88-column scan, sdist/wheel build and isolated imports,
Flyway validation of 39 migrations, and `git diff --check` passed.

Done: 2026-08-24 — added `backfill_scope.py` with bounded inclusive selection,
P0.10 identity, batch/resume controls, rebuild/inactive semantics, exact source-
cursor validation, and 100-listing/1,000,000-row broad confirmation; added
public API/README guidance and unit/live query coverage. Focused pytest passed
63; full package pytest passed 657 with 24 skips; read-only PostgreSQL query
integration passed 9. Poetry check/lock, `pip check`, compileall, 88-column
scan, sdist/wheel build and isolated imports, Flyway validation of 39
migrations, and `git diff --check` passed.

Done: 2026-08-24 — added `backfill_runner.py` and
`backfill_publication.py` for independently committed inactive-slot batches,
exact out-of-range active-row copies, durable cursor/prefix validation,
unpublished `PARTIAL` JSON/PDF and Core evidence, complete-listing membership,
and one terminal P0.9 flip; added
public API/README guidance and cleanup-safe PostgreSQL resume coverage. Full
package pytest passed 659 with 25 skips; focused backfill/daily/publication
PostgreSQL pytest passed 9 with zero J9.6 fixture residue. Poetry check,
`pip check`, compileall, 88-column scan, sdist/wheel build and source/wheel
imports, Flyway validation of 39 migrations, and `git diff --check` passed.

Done: 2026-08-24 — added shared fail-closed runner cleanup in
`failure_safety.py`, Core post-success correction, terminal candidate recovery,
cursor-proven failed-Core resume classification, safe outward errors, and
failure-injection coverage. Full package pytest passed 666 with 25 skips;
focused PostgreSQL publication/daily/backfill pytest passed 8 with zero fixture
residue. Poetry check, `pip check`, compileall, changed-file 88-column scan,
package build, source/wheel imports, Flyway validation of 39 migrations, and
`git diff --check` passed.

Done: 2026-08-24 — added the cleanup-safe append/no-op/correction/version-
rebuild/partial-resume PostgreSQL vertical in
`test_runner_vertical_integration.py` and corrected benchmark-only no-op report
facts in `daily_runner.py`. The vertical passed with seven matching Core and
JSON/PDF outcomes; all PostgreSQL integrations passed 26 with zero J9.8/SPX
fixture residue; full package pytest passed 666 with 26 skips. Poetry check,
`pip check`, compileall, changed-file 88-column scan, package build,
source/wheel imports, Flyway validation of 39 migrations, and
`git diff --check` passed.

---

## Phase 10: Add Package Commands And `bin/` Wrappers

Goal: expose safe operator workflows before Airflow coordination.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| O10.1 | [x] | Add config command | Add a secret-safe package command and `bin/stonks-tech-indicators-config` using `bin/env-load`; validate runtime, dependency, benchmark, and DB readiness. | B1.5-B1.8, I3.6 |
| O10.2 | [x] | Add daily command | Add package command and `bin/stonks-tech-indicators-daily` with effective date/scope/version/dry-run options and compact JSON stdout. | J9.3-J9.4 |
| O10.3 | [x] | Add backfill command | Add package command and `bin/stonks-tech-indicators-backfill` with bounded scope, resume, rebuild protection, progress, and compact JSON stdout. | J9.5-J9.7 |
| O10.4 | [x] | Add inspect command | Add read-only `bin/stonks-tech-indicators-inspect` for coverage, freshness, drift, SPX readiness, and bounded samples without target recommendations. | W7.7, R8.2 |
| O10.5 | [x] | Add CLI validation | Cover help, invalid scopes, missing config, benchmark failure, lock contention, dry run, no-op, success, resume, exit codes, and safe stdout/stderr. | O10.1-O10.4 |
| O10.6 | [x] | Add operator documentation | Document setup, reports, scopes, publication readiness, lock contention/recovery, backfill/resume, rebuild, corrections, benchmark failure, and safe SQL inspection. | O10.1-O10.5 |
| O10.7 | [x] | Verify installed commands | Build/install and prove package scripts/wrappers work in Poetry and Airflow with environment loading owned by runtime. | O10.1-O10.6 |

Done: 2026-08-25 — added package-owned runtime/dependency/database/SPX checks
in `config_readiness.py`, the installed `scripts.config` command,
`bin/stonks-tech-indicators-config`, focused tests, and README guidance. Full
package pytest passed 674 with 26 environment-gated skips; Poetry check/install,
`pip check`, compileall, build, Bash/help smokes, and `git diff --check` passed;
`make db-validate` validated 39 migrations, and the live wrapper returned ready
for Python 3.14.6, NumPy 2.4.6, TA-Lib/C 0.7.1, PostgreSQL 18.4, ten required
relations/privileges, active `global` storage, and reviewed `YAHOO/XIDX/SPX`.

Done: 2026-08-25 — added the installed `scripts.daily` command,
`bin/stonks-tech-indicators-daily`, focused CLI tests, and README guidance for
effective-date, provider/market/listing, version, dry-run, force, compact-success,
and exit-75 contention behavior. Full package pytest passed 684 with 26
environment-gated skips; focused cleanup-safe PostgreSQL/Core runner pytest
passed 3; Poetry check/install, `pip check`, compileall, build and wheel
entry-point inspection, Bash/package/wrapper help smokes, `make db-validate`
(39 migrations), and `git diff --check` passed.

Done: 2026-08-25 — added the installed `scripts.backfill` command,
`bin/stonks-tech-indicators-backfill`, post-batch aggregate JSON progress,
bounded scope/batch controls, exact resume cursors, broad-scope/rebuild
confirmation, focused tests, and README guidance. Full package pytest passed
706 with 26 environment-gated skips; focused cleanup-safe PostgreSQL/Core
partial/resume pytest passed 2; Poetry check/install, `pip check`, compileall,
build and wheel entry-point inspection, Bash/package/wrapper help smokes,
`make db-validate` (39 migrations), and `git diff --check` passed.

Done: 2026-08-25 — added `inspection.py`, the installed `scripts.inspect`
command, `bin/stonks-tech-indicators-inspect`, bounded CLI/service/PostgreSQL
tests, and README guidance for read-only coverage, freshness, drift, and
SPX/source-readiness facts without feature values or recommendations. Full
package pytest passed 724 with 27 environment-gated skips; focused unit/query
pytest passed 93 and read-only PostgreSQL pytest passed 10; Poetry check/install,
`pip check`, compileall, build/wheel inspection, Bash/package/wrapper and bounded
live-wrapper smokes, `make db-validate` (39 migrations), and `git diff --check`
passed.

Done: 2026-08-25 — completed config/daily/backfill/inspect CLI validation in
the four `tests/test_*_cli.py` suites, adding explicit secret-safe pre-connect
missing-config coverage and daily `NO_OP` success output. Focused CLI pytest
passed 55; cleanup-safe PostgreSQL dry-run/success/no-op/resume/lock/inspection
pytest passed 8; full package pytest passed 728 with 27 environment-gated skips;
four wrapper Bash/help smokes, Poetry check, `make db-validate` (39 migrations),
and `git diff --check` passed.

Done: 2026-08-25 — added
`docs/stonks/tech-indicators-operator-runbook.md` and linked it from the package
README, covering setup, bounded scopes, publication/readiness, reports,
contention/recovery, backfill/resume, rebuild/corrections, benchmark failure,
and safe SQL. Focused CLI pytest passed 55; four wrapper Bash/help smokes, live
config and bounded inspect, six live read-only SQL checks, and 35 report/render
pytest passed; 21/21 documentation links, balanced fences, Poetry check,
`make db-validate` (39 migrations), and `git diff --check` passed.

Done: 2026-08-25 — verified package 0.1.0 build/install and all four console
scripts plus wrappers in Poetry and the fresh Airflow 3.2.1 image. Poetry and
wrapper live readiness passed on Python 3.14.6; the Compose-owned Airflow
runtime supplied 10/10 settings, passed `pip check`, all four help smokes, and
live readiness on Python 3.13.13 without package-owned environment loading.
Wheel/sdist build and four-entry-point inspection, full package pytest (728
passed, 27 environment-gated skips), compileall, `make db-validate` (39
migrations), archive checks, and `git diff --check` passed.

---

## Phase 11: Add Thin Airflow Coordination

Goal: refresh tech indicators only after required EODData and Yahoo/SPX inputs
are ready for the same effective date, without moving package logic into DAGs.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| A11.1 | [x] | Select coordination mechanism | Evaluate Airflow 3 assets/events, coordinator DAG, and trigger/wait patterns against scheduled EODData and manual Yahoo. Select a date-scoped prerequisite join that does not rely on timing alone. | I3.6, J9.3, OHLCV V10.8-V10.10 |
| A11.2 | [x] | Define source completion signals | Add/reuse minimal date-scoped source outputs/assets so EODData and Yahoo success is unambiguous, rerun-safe, and contains no credentials/raw data. | A11.1 |
| A11.3 | [x] | Add manual tech-indicators DAG | Add thin `stonks_tech_indicators_daily_refresh` wiring runtime services and validated effective-date/scope overrides to the package runner; begin `schedule=None`, no catchup, one active run. | O10.7, A11.1 |
| A11.4 | [x] | Add DAG contract tests | Cover import, tags, schedule, task shape, date handling, overrides, runner identity, logging, and absence of calculation SQL/business logic. | A11.3 |
| A11.5 | [x] | Wire prerequisites | Implement the selected EODData plus Yahoo/SPX join so automatic refresh occurs only after both inputs succeed or readiness is explicitly proven for the same date. | A11.2-A11.4 |
| A11.6 | [x] | Handle repeated source runs | Prove EODData's multiple daily runs and Yahoo/manual reconciliation coalesce or safely trigger idempotent refresh through the package-owned scope lock, without concurrent duplicate work or partial publication. | A11.5, J9.4, J9.9 |
| A11.7 | [x] | Verify Airflow vertical | Rebuild Airflow, verify zero import errors, run source fixture completions through tech indicators, and inspect Core plus JSON/PDF objects. | A11.4-A11.6 |
| A11.8 | [x] | Decide production cadence | From bounded evidence, choose event-driven, scheduled, or manual-only operation and document pause/rollback before enabling it. | A11.7 |

Done: 2026-08-29 — selected asynchronous EODData/Yahoo source-success
dispatch to the manual/event-woken coordinator, with I3.6's same-effective-date
Core/OHLCV/SPX readiness predicate as the authoritative join, in
`docs/stonks/tech-indicators-airflow-coordination-v1.md`; rejected
unpartitioned assets, unavailable Airflow 3.2.1 runtime partition assignment,
scheduled polling, and logical-date sensors. Documentation marker/link checks,
the Airflow 3.2.1/provider 1.12.3 API probe, focused source-DAG pytest (20
passed), focused readiness pytest (9 passed), non-table/non-URL prose
88-column scan, and `git diff --check` passed.

Done: 2026-08-29 — added the immutable, JSON-safe EODData/Yahoo completion
signal and deterministic Airflow trigger configuration in
`empire_stonks_ohlcv.tech_indicators_completion`; qualifying daily results now
expose it without credentials, raw data, or report/object payloads, with exact
eligibility and rerun contracts documented in the OHLCV README and A11
coordination/design contracts. Focused pytest passed (76), full OHLCV pytest
passed (597 passed, 33 skipped), `poetry check --lock`, `pip check`, package
build, compile/import smoke, both daily CLI `--help` smokes, prose line scan,
and `git diff --check` passed.

Done: 2026-08-29 — added the one-task, manual-only
`dags/stonks/stonks_tech_indicators_daily_refresh.py` DAG with required exact
effective date, validated daily scope/version/dry-run/force overrides,
independent work/Core/object-store connections, the normal lock factory, and
direct package-runner delegation; documented its operator and coordination
contract without enabling source triggers or preflight wiring. Full package
pytest passed (728 passed, 27 skipped); Poetry lock and dependency checks,
compileall, live Airflow 3.2.1 import/task-shape and scope smokes, zero Airflow
import errors, changed-file prose/code line scan, absence-of-SQL scan, and
`git diff --check` passed.

Done: 2026-08-29 — added
`packages/empire-stonks-tech-indicators/tests/test_daily_refresh_dag.py` with
25 contract cases covering import, tags/manual schedule, task shape, required
exact date, normalized and invalid scope overrides, reserved A11.2 provenance,
separate runtime services, lock-factory and Airflow runner identity, compact
secret-safe logging, failure cleanup, and absence of SQL/calculation logic.
Focused pytest passed (25); full package pytest passed (753 passed, 27 skipped);
Poetry lock/dependency checks, compileall, live Airflow 3.2.1 contract import,
zero Airflow import errors, changed-file line scan, and `git diff --check`
passed.

Done: 2026-08-29 — wired qualifying EODData and Yahoo/SPX results through
strict package-owned dispatch construction to asynchronous, deterministic
`TriggerDagRunOperator` wakes; added the coordinator's repeatable-read,
read-only package preflight so not-ready dates skip before Core/report work and
ready dates retain the locked authoritative runner recheck. Key files:
`tech_indicators_completion.py`, `daily_preflight.py`, and the three Stonks
DAGs. Full pytest passed for tech indicators (760 passed, 27 skipped) and OHLCV
(606 passed, 33 skipped); both Poetry lock, `pip check`, and compileall checks,
`make airflow-build`, fresh Airflow 3.2.1 image DAG graph/operator assertions,
fresh-image `pip check`, and `git diff --check` passed.

Done: 2026-08-29 — proved repeated-source behavior in
`test_tech_indicators_completion.py`, `test_daily_refresh_dag.py`, and the live
`test_daily_noop_integration.py`: exact source retries retain one trigger ID,
new same-date Core runs create distinct wakes into one scope, real overlap
returns zero-state contention, and later healthy EODData/Yahoo evidence
converges to `NO_OP` without a second publication or payload timestamp change.
Focused unit pytest passed 108; cleanup-safe PostgreSQL lock/publication pytest
passed 9 with zero fixture residue; full tech-indicators pytest passed 761 with
27 skipped and full OHLCV pytest passed 608 with 33 skipped. Both Poetry lock,
dependency, and compileall checks, `make db-validate` (39 migrations), fresh
Airflow 3.2.1 DAG assertions, and `git diff --check` passed.

Done: 2026-08-29 — added the cleanup-safe
`tools/tech-indicators/airflow-vertical.py` probe and recorded the deployed
vertical in `tech-indicators-airflow-vertical-evidence-a11.7.md`: fresh Airflow
3.2.1/provider 1.12.3 build and recreation, zero import errors, two successful
source-provenance DAG runs, one 15,498-row `PASS` publication, one zero-write
`NO_OP`, and four checksum-valid schema-V1 JSON/12-page PDF objects. Fresh-image
`pip check`, exact DAG/task states, JSON/PDF inspection, paused-state restore,
six zero database residue counts, zero report-file residue, probe compile/help,
focused coordinator/source pytest (28 and 53 passed), changed-prose line scan,
and `git diff --check` passed.

Done: 2026-08-29 — selected event-driven source-completion operation with
`schedule=None`, kept normal technical refresh paused until the P13.14 go
decision, and froze activation, queued-wake, pause, and data-preserving rollback
in `tech-indicators-airflow-rollout-v1.md`; retagged the coordinator
`event-driven` and restored Yahoo's required manual-only paused state. Focused
coordinator/source pytest passed 28 and 53; compileall and Poetry lock check
passed; live Airflow proved the exact two-task DAG contract, zero import errors,
EODData unpaused, Yahoo/coordinator paused, and zero queued/running runs for all
three DAGs; changed-prose scan and `git diff --check` passed.

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
