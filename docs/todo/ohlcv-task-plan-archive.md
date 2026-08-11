# OHLCV Package Action Plan Archive

This document contains fully completed phases moved from the active
[OHLCV package action plan](ohlcv-task-plan.md). Task IDs and their `Done:`
notes remain here as the historical record and may still be referenced by active
task dependencies.

---

## Phase 0: Scope And Conventions

Goal: turn the agreed architecture into exact, testable package rules before
implementation begins.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| P0.1 | [x] | Record initial scope | Update the OHLCV architecture documentation to say the first build contains only `empire-stonks-ohlcv`, `provider_listing`, and `ohlcv_daily`; the bridge and canonical mappings are explicitly deferred. | — |
| P0.2 | [x] | Define provider-series identity | Document that `provider_listing` represents a provider/market/ticker series, not guaranteed real-world continuity. State that ticker-reuse detection is deferred and future temporal mappings may split one series by date. | P0.1 |
| P0.3 | [x] | Define provider-native value policy | Document that OHLCV values and adjustment semantics are stored as supplied by each provider, without cross-provider normalization. Identify the metadata required to describe known source semantics. | P0.1 |
| P0.4 | [x] | Define retention and correction policy | Document approximately seven-day raw-object retention, durable source-snapshot identity, current-state idempotent upserts, no bar-revision history, and operator-managed exceptional corrections. | P0.1 |
| P0.5 | [x] | Define naming and runtime conventions | Record package/import names, database table names, Core run domain/job/subject conventions, object-store key prefix, object kinds, report logical names, and `EMPIRE_STONKS_OHLCV_*` environment variable names, including provider-specific secret names. | P0.1-P0.4 |

Done: 2026-07-13 — replaced the generated architecture draft with the approved
initial `empire-stonks-ohlcv` scope and explicitly deferred bridge/canonical
mapping work in `docs/todo/ohlcv-plan.md`; verified with `git diff --check`.

Done: 2026-07-13 — defined `provider_listing` as provider/market/ticker series
identity, documented undetectable ticker reuse, and reserved temporal identity
interpretation for the future bridge in `docs/todo/ohlcv-plan.md`; verified with
`git diff --check`.

Done: 2026-07-13 — documented provider-native value storage, adjustment
metadata expectations, and the prohibition on cross-provider normalization in
`docs/todo/ohlcv-plan.md`; verified with `git diff --check`.

Done: 2026-07-13 — documented seven-day raw retention, durable source-snapshot
lineage, current-state upserts, overwrite-on-provider-correction behavior, and
the absence of bar revision history in `docs/todo/ohlcv-plan.md`; verified with
`git diff --check`.

Done: 2026-07-13 — defined package/import/table names, Core run and DAG names,
subject-key conventions, object paths/kinds/logical names, `deploy/env/local.env`
runtime ownership, common environment variables, provider prefixes, and initial
EODData secret names in `docs/todo/ohlcv-plan.md`; verified with
`git diff --check`.

## Phase 1: Package And Runtime Skeleton

Goal: create a minimal reusable package that imports and tests independently
before provider or database logic is added.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| B1.1 | [x] | Scaffold Poetry package | Create `packages/empire-stonks-ohlcv` with version `0.1.0`, `src/empire_stonks_ohlcv`, tests, README, and the minimum initial dependency on `empire-core`. Package import works. | P0.5 |
| B1.2 | [x] | Add package exceptions and exports | Add a small exception hierarchy and stable top-level exports without exposing provider internals or creating a generic framework. Import tests pass. | B1.1 |
| B1.3 | [x] | Add environment-driven config skeleton | Add typed configuration that reads only `os.environ`. Local runtimes load `deploy/env/local.env`; the package does not load `.env` files or assume repository paths. Unit tests cover defaults, required values, and provider-specific credentials. | B1.1 |
| B1.4 | [x] | Add secret-safe config behavior | Prove config representations, errors, logs, Core run parameters, object metadata, reports, and serialized results do not expose provider credentials or tokens. Targeted tests pass. | B1.3 |
| B1.5 | [x] | Install package in Airflow image | Add the package to `deploy/docker/airflow/Dockerfile` in dependency-safe order. The Airflow image build reaches package installation successfully. | B1.1 |
| B1.6 | [x] | Add local environment settings | Add documented non-secret defaults/placeholders to `deploy/env/local.example.env` and the active local values to `deploy/env/local.env` as appropriate. Provider secrets stay local and are not committed. | B1.3-B1.4 |
| B1.7 | [x] | Pass OHLCV settings to Airflow | Pass the required `EMPIRE_STONKS_OHLCV_*` values from `deploy/env/local.env` through Airflow Compose without embedding credentials in DAG files or images. | B1.5-B1.6 |
| B1.8 | [x] | Add package CLI wrapper convention | Add the first `bin/stonks-ohlcv-*` wrapper and package script skeleton using the existing `bin/env-load` pattern so local commands receive `deploy/env/local.env`. Help/import smoke tests pass. | B1.1-B1.4, B1.6 |

Done: 2026-07-14 — added `packages/empire-stonks-ohlcv/{pyproject.toml,
poetry.lock,README.md,src/empire_stonks_ohlcv/__init__.py,tests/test_package.py}`;
`poetry check --lock` passed (deprecation warnings only), `poetry run pytest -q`
passed (1 test), isolated package/Core imports and `compileall` passed,
`poetry run python -m pip check` found no broken requirements, and
`poetry build` built the sdist/wheel.

Done: 2026-07-14 — added the shared exception hierarchy and explicit public
exports in `src/empire_stonks_ohlcv/{exceptions.py,__init__.py}` with import and
inheritance coverage in `tests/test_exceptions.py`; `poetry run pytest -q`
passed (3 tests), isolated public imports, `compileall`, `poetry check --lock`
(deprecation warnings only), `poetry run python -m pip check`, and
`git diff --check` passed.

Done: 2026-07-14 — added immutable common/EODData environment config in
`src/empire_stonks_ohlcv/config.py`, public exports, README defaults, and
`tests/test_config.py`; `poetry run pytest -q` passed (17 tests), isolated
config imports, `compileall`, `poetry check --lock` (deprecation warnings only),
`poetry run python -m pip check`, and `git diff --check` passed.

Done: 2026-07-14 — hardened credential representation/error handling and added
the explicit safe operational payload in `src/empire_stonks_ohlcv/config.py`,
README guidance, and `tests/test_secret_safety.py`; `poetry run pytest -q`
passed (22 tests), isolated safe-config import, `compileall`,
`poetry check --lock` (deprecation warnings only),
`poetry run python -m pip check`, and `git diff --check` passed.

Done: 2026-07-14 — installed `packages/empire-stonks-ohlcv` immediately after
`empire-core` in `deploy/docker/airflow/Dockerfile`; `make airflow-build`
completed all 19 image steps and installed `empire-stonks-ohlcv==0.1.0`, and a
one-off `empire-airflow:3.2.1` container imported both OHLCV and Core
successfully (`0.1.0 empire_stonks_ohlcv empire_core`).

Done: 2026-07-14 — completed the OHLCV defaults/placeholders in tracked
`deploy/env/local.example.env` and ignored `deploy/env/local.env` while
preserving the API-key-only EODData credential; both files loaded through
`bin/env-load` and `OHLCVConfig.from_env()`, Compose config validation passed,
`poetry run pytest -q` passed (20 tests), and local ignore/tracking checks plus
`git diff --check` passed.

Done: 2026-07-14 — passed the storage key, common OHLCV settings, and EODData
API key/source settings through the shared Airflow environment in
`deploy/compose/airflow.yml`; Compose config validation and `make airflow-build`
passed, rendered config verified 7 variables across all 6 Airflow services, and
a one-off container loaded the API-key config with a secret-safe summary; image
metadata inspection confirmed no OHLCV settings were embedded in the image.

Done: 2026-07-14 — added `bin/stonks-ohlcv-config`, the package
`scripts.config` module/Poetry entrypoint, README usage, and secret-safe CLI
coverage; Bash syntax, wrapper/module help and example-env smoke tests passed,
`poetry run pytest -q` passed (21 tests), and Poetry check/install/build,
`pip check`, `compileall`, import, and `git diff --check` passed.

## Phase 2: Database Design And Migration

Goal: finalize and implement the smallest durable schema for provider-native
series and daily bars.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| S2.1 | [x] | Design `provider_listing` columns | Document exact columns, types, exact case-sensitive provider-native market and ticker handling, provider-series lookup key, optional name and default-`UNKNOWN` instrument type, first/last-seen semantics, deliberate metadata omissions, timestamps, constraints, and indexes. The design does not claim canonical identity. | P0.2-P0.4 |
| S2.2 | [x] | Design `ohlcv_daily` columns | Document exact price/volume and persisted derived-value types, nullability, composite key, OHLC and derived-value invariants, deliberate adjusted-value and per-row provenance omissions, timestamps, and indexes for listing/date and freshness queries. | P0.3-P0.4, S2.1 |
| S2.3 | [x] | Define idempotent write behavior | Specify insert, unchanged-row skip, provider-correction update, first/last-seen update, prior-close-derived recalculation for the immediately following bar, transaction, and returned-count behavior before repository code is written. | S2.1-S2.2 |
| S2.4 | [x] | Add provider seed migration | Add idempotent `stonks.provider` rows for `EODDATA`, `STOOQ`, and `YAHOO` using the existing provider-table conventions. DB validation passes. | P0.5 |
| S2.5 | [x] | Add OHLCV table migration | Create `stonks.provider_listing` and `stonks.ohlcv_daily` in one ordered Flyway migration or clearly ordered migrations, with the designed provider, instrument-type, and owning-series FKs and no per-row Core/source-snapshot FKs. | S2.1-S2.4 |
| S2.6 | [x] | Validate schema and regenerate DB docs | Run repo DB validation and regenerate the Stonks ERD/docs. Generated relations show the intended provider, instrument-type, listing-series, and daily-bar relationships with no canonical `listing_id`, Core run, or source-snapshot FK. | S2.5 |
| S2.7 | [x] | Add schema contract tests | Add focused tests or validation SQL proving primary keys, exact case-sensitive unique lookup behavior, reference FKs, OHLC and row-local derived-value checks, and update/delete semantics behave as designed. | S2.5 |

Done: 2026-07-15 — finalized the minimal `stonks.provider_listing` contract in
`docs/todo/ohlcv-plan.md` and revised `docs/todo/ohlcv-db-roughcut.txt`: exact
case-sensitive `(provider_code, market, ticker)` identity, default `UNKNOWN`
instrument type, coverage-date semantics, constraints, timestamps, and focused
indexes, with status/currency/adjustment/JSON metadata deliberately omitted;
verified with `git diff --check` and focused documentation consistency searches.

Done: 2026-07-15 — finalized the minimal `stonks.ohlcv_daily` contract in
`docs/todo/ohlcv-plan.md` and revised `docs/todo/ohlcv-db-roughcut.txt`:
`NUMERIC` OHLCV and persisted derived-value types, composite key, structural
and row-local formula checks, prior-close semantics, timestamps, and one
cross-series freshness index, with adjusted values and per-row snapshot/run
provenance deliberately omitted; retained the five daily conveniences on the
bar while deferring rolling/cross-series/versioned technical indicators to a
future design; verified with `git diff --check` and focused documentation
consistency searches.

Done: 2026-07-15 — defined the idempotent persistence contract in
`docs/todo/ohlcv-plan.md`: unique validated inputs, stored-scale comparisons,
one transaction per batch/chunk, deterministic per-series locking, conservative
listing metadata updates, update-only-when-distinct bars, final-state derived
recalculation, timestamp rules, and disjoint input versus derived-maintenance
counts; verified with `git diff --check`, balanced Markdown fences, and focused
contract consistency searches.

Done: 2026-07-15 — added
`db/flyway/sql/V2026.07.15.0001__stonks_seed_ohlcv_providers.sql` with
idempotent active `DATA_SOURCE` upserts for `EODDATA`, `STOOQ`, and `YAHOO`;
`make db-migrate` applied migration 2026.07.15.0001, `make db-validate`
successfully validated all 30 migrations, and a PostgreSQL query returned the
three intended active provider rows.

Done: 2026-07-15 — added
`db/flyway/sql/V2026.07.15.0002__stonks_create_ohlcv_tables.sql` with the
designed provider-listing identity, coverage/default checks, current daily
OHLCV and persisted derived columns, numeric/formula checks, focused indexes,
provider/instrument FKs, and cascading bar ownership FK; `make db-migrate`
applied migration 2026.07.15.0002 and `make db-validate` validated all 31
migrations. PostgreSQL catalog inspection confirmed 24 columns, 12 checks, the
three intended FKs/delete actions, five PK/unique/reporting indexes, and no
canonical listing, Core run, source-snapshot, or source-object columns.

Done: 2026-07-15 — added the `ohlcv` Stonks documentation group in
`tools/docs/db/schemas/stonks/groups/ohlcv.txt`, documented it in
`docs/db/tools-docs.md`, and generated focused Mermaid and pg-diagram outputs
under `docs/db/stonks/generated`; `make db-validate` validated all 31
migrations, and the Stonks schema, full/grouped Mermaid, and full/grouped
pg-diagram generators completed. Visual inspection confirmed the provider and
instrument-type references into `provider_listing` and its one-to-many
`ohlcv_daily` relation, with no canonical/Core/source-snapshot relationship.

Done: 2026-07-15 — added the transactional schema contract suite in
`db/tests/stonks/ohlcv_schema_contract.sql` and the `db-test-ohlcv-schema` Make
target in `tools/make/db.mk`; the suite passed 21 expected constraint failures
plus valid insert, correction, and cascade paths, rolled back all fixtures, and
`make db-validate` successfully validated all 31 migrations.

## Phase 3: Shared Models And Persistence

Goal: build provider-neutral package primitives for parsed records and database
writes without introducing provider-specific schema branches.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| M3.1 | [x] | Add provider-listing dataclass | Add a typed immutable record for provider code, native market, native ticker, optional name, and instrument type defaulting to `UNKNOWN`. Validation tests cover required identity fields. | B1.2, S2.1 |
| M3.2 | [x] | Add daily-bar dataclass | Add a typed immutable daily-bar record using `date` and `Decimal`, with optional volume and validation matching the source-field database invariants. Persisted derived values are writer-calculated rather than provider inputs. Unit tests cover valid and invalid bars. | B1.2, S2.2 |
| M3.3 | [x] | Add provider batch/result models | Add small JSON-ready result dataclasses for acquired objects, parsed listing/bar batches, inserted/updated/unchanged and derived-maintenance counts, failures, and warnings. | M3.1-M3.2 |
| M3.4 | [x] | Implement provider-listing writer | Add focused transactional SQL that resolves or inserts provider series idempotently and updates observational metadata without mutating canonical tables. Unit tests cover reruns and different providers/markets. | S2.3, M3.1 |
| M3.5 | [x] | Implement daily-bar writer | Add batched transactional current-state upserts returning inserted, updated, unchanged, and derived-updated counts. Tests cover reruns, provider corrections, following-bar derived-value recalculation, null optional fields, and constraint failures. | S2.3, M3.2-M3.4 |
| M3.6 | [x] | Add daily-bar query helpers | Add only the read queries needed for incremental cutoffs, per-series date ranges, freshness, coverage, and reporting. Ordering and empty-state tests pass. | M3.5 |
| M3.7 | [x] | Prove provider isolation | Tests prove identical market/ticker/date values from EODData, Stooq, and Yahoo remain distinct through their provider-listing IDs and cannot overwrite one another. | M3.4-M3.6 |

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

Done: 2026-07-16 — added the caller-transaction-owned daily-bar writer and
resolved-listing input record in
`packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/{daily_bars.py,__init__.py}`
with scale, duplicate-input, and rollback-only PostgreSQL coverage in
`tests/{test_daily_bars.py,test_daily_bars_integration.py,test_exceptions.py}`;
focused unit tests passed (4), PostgreSQL integration passed (2), full package
tests passed (131), Flyway validated 31 migrations, and the OHLCV schema
contract passed. Poetry lock check, `compileall`, import smoke test, `pip
check`, package sdist/wheel build, 88-column scan, and `git diff --check`
passed (no project formatter/linter is configured).

Done: 2026-07-16 — added public read-only incremental-cutoff, per-series
date-range, provider-freshness, and ordered provider-coverage helpers in
`packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/{queries.py,__init__.py}`
with JSON/export, ordering, and empty-state coverage in
`tests/{test_queries.py,test_queries_integration.py,test_exceptions.py}`;
focused unit tests passed (5), PostgreSQL integration passed (1), full package
tests passed (137), Flyway validated 31 migrations, and the OHLCV schema
contract passed. `poetry check`, `compileall`, import smoke test, and `git diff
--check` passed (no project formatter/linter is configured).

Done: 2026-07-16 — added rollback-only PostgreSQL provider-isolation coverage
in `packages/empire-stonks-ohlcv/tests/test_provider_isolation_integration.py`;
identical EODData, Stooq, and Yahoo native market/ticker/date inputs resolved
to distinct IDs, and an EODData correction left the Stooq/Yahoo bars and
provider-scoped coverage unchanged. Focused PostgreSQL integration passed (1),
full package tests passed (138), Flyway validated 31 migrations, and the OHLCV
schema contract passed. `poetry check`, `compileall`, import smoke test,
test-file 88-column scan, and `git diff --check` passed (no project
formatter/linter is configured).

## Phase 4: Core Run, Object-Store, And Source-Snapshot Integration

Goal: retain raw inputs briefly while preserving durable content identity and
run-level operational provenance.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| C4.1 | [x] | Define OHLCV object paths and kinds | Document deterministic storage keys for provider/date/run/source, raw filenames, object kinds, logical names, metadata, and approximately seven-day expiration. | P0.4-P0.5, B1.3 |
| C4.2 | [x] | Add raw-object storage helper | Add package-owned helpers that store downloaded bytes/files through `ObjectStore` with the active `RunContext`, checksum, provider metadata, and expiration. Tests use an in-memory/fake object repository. | C4.1 |
| C4.3 | [x] | Add source-snapshot persistence | Add focused Stonks persistence that upserts `provider_source_snapshot` by provider/source/checksum and links each current stored object through `provider_source_snapshot_object`. Do not duplicate these tables. | C4.2, S2.5 |
| C4.4 | [x] | Prove cleanup-safe lineage | Tests or database verification prove raw object purge removes snapshot-object membership while the source snapshot and OHLCV rows remain valid. | C4.3 |
| C4.5 | [x] | Add package run wrapper | Add a reusable runner that starts, completes, fails, and summarizes `core.core_run` records around provider acquisition/import work. Tests cover success and failure paths. | B1.3, M3.3, C4.2 |
| C4.6 | [x] | Add acquisition-to-import transaction boundary | Define and implement failure behavior between completed raw download, snapshot registration, parsing, and database writes so partial failures are reportable and safely rerunnable. | C4.3-C4.5, M3.5 |

Done: 2026-07-16 — defined the Core-compatible OHLCV raw/report key,
filename, kind, logical-name, metadata, secret-safety, and expiration contract
in `docs/todo/ohlcv-plan.md`; focused config/secret tests passed (17), Poetry
lock check and config import passed, the full package suite passed (133 passed,
5 skipped), the contract/fence scans found 8 required markers and 60 balanced
fences, and `git diff --check` passed.

Done: 2026-07-16 — added public Core-backed raw byte/file storage, deterministic
key/filename builders, metadata and run validation, retention, and fake-repository
coverage in `packages/empire-stonks-ohlcv/{src/empire_stonks_ohlcv/object_store.py,
tests/test_object_store.py,README.md}` plus exports; focused tests passed (10),
the full suite passed (143 passed, 5 skipped), and Poetry lock check, compileall,
pip check, import smoke test, sdist/wheel build, 88-column scan, and
`git diff --check` passed (no formatter/linter is configured).

Done: 2026-07-16 — added caller-transaction-owned source identity and object
membership persistence in `packages/empire-stonks-ohlcv/src/
empire_stonks_ohlcv/source_snapshots.py`, public exports/README guidance, and
focused fake-cursor/PostgreSQL tests; unit tests passed (8), PostgreSQL
integration passed (1), the DB-backed full suite passed (157), Flyway validated
31 migrations, and Poetry lock check, compileall, pip check, import smoke test,
88-column scan, and `git diff --check` passed (no formatter/linter is configured).

Done: 2026-07-16 — added rollback-only PostgreSQL purge-lifecycle coverage in
`packages/empire-stonks-ohlcv/tests/test_cleanup_safe_lineage_integration.py`;
documented the verified behavior in the package README; the focused lifecycle
test passed (1), the DB-backed full suite passed (158), Flyway validated 31
migrations, and Poetry lock check, compileall, pip check, 88-column scan, and
`git diff --check` passed (no formatter/linter is configured).

Done: 2026-07-16 — added the injected, secret-safe Core lifecycle wrapper and
compact run result/summary contract in
`packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/runner.py`, public
exports/README guidance, and success, failure, validation, and PostgreSQL
coverage; focused unit tests passed (5), PostgreSQL integration passed (1), the
DB-backed full suite passed (164), Flyway validated 31 migrations, and Poetry
lock check, compileall, pip check, import smoke test, 88-column scan, and
`git diff --check` passed (no formatter/linter is configured).

Done: 2026-07-16 — added the public acquisition/parse/transaction boundary,
allowlisted stage-safe workflow failures, and Core failure-stage summaries in
`packages/empire-stonks-ohlcv/{src/empire_stonks_ohlcv/{import_boundary.py,
exceptions.py,runner.py},tests/test_import_boundary*.py,README.md}` and updated
`docs/todo/ohlcv-plan.md`; focused unit tests passed (14), focused PostgreSQL
integration passed (1), the DB-backed full suite passed (172), Flyway validated
31 migrations, and the OHLCV schema contract, Poetry lock check, compileall,
pip check, import smoke test, package build, 88-column scan, and
`git diff --check` passed (no formatter/linter is configured).

## Phase 5: Provider Contract And Fixtures

Goal: establish the small shared boundary used by all three providers while
allowing their acquisition and parsing details to differ.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| A5.1 | [x] | Define provider output contract | Define the minimal provider interface or callable contract that yields shared listing and daily-bar batches plus source metadata. Do not require unrelated metadata or identical remote APIs. | M3.1-M3.3, C4.6 |
| A5.2 | [x] | Define source-code conventions | Assign stable provider/source/parser-version identifiers for listing discovery, nightly daily data, and historical files so source snapshots remain interpretable. | C4.3, A5.1 |
| A5.3 | [x] | Add provider fixture policy | Add small committed fixtures derived from documented provider formats, sanitized of credentials and limited to records needed for parser and edge-case tests. | A5.1-A5.2 |
| A5.4 | [x] | Add shared parser contract tests | Add reusable assertions for provider code, exact market/ticker preservation, date/Decimal parsing, optional volume, rejected invalid rows, and deterministic output. | A5.3 |
| A5.5 | [x] | Add provider runner seam | Make package runners accept provider acquisition/parser collaborators so tests do not require network access and Airflow remains a thin caller. | C4.5-C4.6, A5.1 |

Done: 2026-07-16 — added the public callable aliases and immutable parsed-output
and source-metadata records in `packages/empire-stonks-ohlcv/src/
empire_stonks_ohlcv/{provider_contract.py,results.py,import_boundary.py,
__init__.py}`, documented the minimal adapter boundary, and updated focused
tests; the database-backed package suite passed (186), Flyway validated all 31
migrations, and Poetry lock, compileall, pip check, public import, package build,
88-column changed-Python-file scan, and `git diff --check` passed (no
formatter/linter is configured).

Done: 2026-07-16 — added immutable production source/parser constants in
`packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/
source_conventions.py`, public exports/tests, and exact identifier, partition,
and parser-version rules in the architecture plan and package README; the
database-backed package suite passed (189), Flyway validated all 31 migrations,
and focused tests (51), Poetry lock, compileall, pip check, public import,
package build, changed-Python-file 88-column scan, and `git diff --check` passed
(no formatter/linter is configured).

Done: 2026-07-16 — added the provider fixture policy, manifest schema, and
automated hygiene enforcement in `packages/empire-stonks-ohlcv/{README.md,
tests/fixtures/{README.md,manifest.schema.json},tests/test_fixture_policy.py}`
and documented it in `docs/todo/ohlcv-plan.md`; a bounded EODData NASDAQ probe
returned HTTP 200/1,103,147 bytes/5,013 rows, and added the 443-byte sanitized
fixture, SHA-256 manifest, and evidence note under `tests/fixtures/eoddata` and
`docs/stonks/ohlcv-eoddata-daily-format.md`. The database-backed package suite
passed (192), focused policy tests passed (3), and JSON validation, Poetry lock,
compileall, pip check, package build, changed-Python-file 88-column scan, and
`git diff --check` passed (no formatter/linter is configured).

Done: 2026-07-16 — added the reusable bytes-adapter parser assertions and
test-only reference suite in `packages/empire-stonks-ohlcv/tests/
{parser_contract.py,test_parser_contract.py}` and documented the test seam in
`docs/todo/ohlcv-plan.md` and the package README; the database-backed package
suite passed (193), the focused contract test passed (1), and Poetry lock,
compileall, pip check, helper import, package build, changed-Python-file
88-column scan, and `git diff --check` passed (no formatter/linter is
configured).

Done: 2026-07-16 — added and publicly exported `run_provider_pipeline()` in
`packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/{runner.py,__init__.py}`
with injected acquisition/parser and caller-owned connection seams, focused
coverage in `tests/{test_provider_runner_seam.py,test_exceptions.py}`, and
architecture/README guidance; focused tests passed (14), the database-backed
package suite passed (198), and Flyway validated all 31 migrations. Poetry lock,
compileall, pip check, import, package build, changed-Python-file 88-column scan,
and `git diff --check` passed (no formatter/linter is configured).

## Phase 6: EODData End-To-End Vertical Slice

Goal: complete the first provider from environment configuration and the
ordered nightly symbol-list plus daily-quote workflow through validation,
stored listings and bars, reporting, and its Airflow DAG before starting the
next provider. Each run covers NYSE, NASDAQ, and AMEX and keeps all provider
values provider-native.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| E6.1 | [x] | Document EODData source, duplicate, and config contract | Specify `Symbol/List/{exchangeCode}` for listing discovery followed by `Quote/List/{exchangeCode}` for daily bars across NYSE, NASDAQ, and AMEX; finalize `EMPIRE_STONKS_OHLCV_EODDATA_*` settings, API-key authentication, explicit effective-date behavior, JSON formats, delivery timing, native price semantics, and six stable exchange-partitioned raw filenames. Map symbol `name` best-effort and preserve available `type`/`currency` only as metadata while keeping `instrument_type_code='UNKNOWN'`. Define deterministic handling and reporting for duplicate symbol identities, duplicate bars, missing descriptive fields, quote/listing mismatches, empty responses, and symbols without a quote; never infer canonical identity or automatically inactivate absent symbols. Secrets come from `deploy/env/local.env` at runtime. | A5.1-A5.2, B1.6-B1.7 |
| E6.2 | [x] | Implement EODData six-request acquisition | Acquire and store the three Symbol List payloads before the three Quote List payloads using deterministic exchange order, the two established source codes, stable exchange part keys, timeouts, bounded retries, clear errors, injected HTTP/object-storage dependencies, and Core raw-object storage. Tests cover all six successful objects, partial failure with retained raw evidence, retryable and non-retryable responses, invalid/empty content according to E6.1, and secret-safe errors/metadata. | E6.1, C4.2, A5.5 |
| E6.3 | [x] | Implement EODData Symbol List parser | Parse exchange-scoped Symbol List fixtures into one shared `ProviderListing` per exact `(EODDATA, exchange, code)` identity. Ignore quote-like fields in this endpoint, keep `instrument_type_code='UNKNOWN'`, retain `name`, `type`, and `currency` only on a best-effort basis, and implement the documented deterministic duplicate policy without arbitrary first/last-wins behavior. Focused and shared parser-contract tests cover all three exchanges, missing optional fields, compatible duplicates, and conflicting duplicates. | E6.1-E6.2, A5.3-A5.4 |
| E6.4 | [x] | Implement EODData Quote List parser and reconciliation | Parse exchange-scoped daily Quote List fixtures, require the requested exchange, daily interval, and effective trading date, and reconcile each accepted quote to the same-exchange Symbol List identity without synthesizing a canonical or unlisted series. Produce one unique shared listing batch per provider identity with its bar, while preserving symbol-list metadata. Tests cover symbols without quotes, quotes without listings, duplicate/conflicting quotes, exchange/date/interval mismatches, deterministic ordering, and NYSE/NASDAQ/AMEX ticker overlap. | E6.1-E6.3, A5.3-A5.4 |
| E6.5 | [x] | Define shared validation, issue, count, and report contract | Define structural OHLC checks, null/volume handling, hard failures versus row rejections and warnings, bounded issue samples, and separate listing-feed, quote-feed, listing-write, and bar-write counts by source and market. Define freshness, coverage, stale-series, and weekday-shaped gap metrics, and state that gaps are not exchange-calendar authoritative. Extend the shared result boundary only as much as required to carry deterministic accepted/rejected/warning results from parsing and validation into persistence and reporting. | E6.4, P0.3, S2.2, M3.3, M3.6 |
| E6.6 | [x] | Implement atomic EODData import service | Validate the reconciled output, register source-snapshot membership for all six acquired objects, upsert every discovered provider listing, resolve active listing IDs, and then upsert accepted daily bars in one database transaction. Return the separate E6.5 parse/validation and persistence counts, including derived maintenance. Tests prove rollback across all snapshot/listing/bar writes on failure, inactive-listing behavior, duplicate-policy outcomes, corrections, and an unchanged idempotent rerun. | E6.2-E6.5, M3.4-M3.5, C4.3-C4.6 |
| E6.7 | [x] | Implement EODData health queries | Add the first deterministic health queries for the shared report contract, parameterized by provider and exercised for EODData across NYSE, NASDAQ, and AMEX. Include active/inactive handling and validate existing indexes against representative fixture volume before adding any new index. | E6.5-E6.6 |
| E6.8 | [x] | Build and store EODData report | Produce a common Empire-style JSON report with per-source and per-market acquisition, parse, validation, listing-write, and bar-write counts; duplicate and cross-feed mismatch outcomes; freshness, coverage, stale series, gap warnings, bounded failures/warnings, and native-semantics notes. Store it under the active Core run; tests cover provider/market scoping, paths, metadata, and secret safety. | E6.6-E6.7, C4.2, C4.5 |
| E6.9 | [x] | Add EODData daily runner | Add package-owned sequencing for the ordered Symbol List and Quote List acquisition, parsing/reconciliation, atomic snapshot/listing/bar persistence, reporting, and Core run completion/failure. Support an explicit effective date and return only a compact secret-safe result. Tests cover success, acquisition/parse/persistence/report failures, partial raw evidence, and rerun behavior. | E6.8, B1.8 |
| E6.10 | [x] | Add EODData CLI | Add an operator CLI and `bin` wrapper that receives `deploy/env/local.env` through `bin/env-load`, supports an explicit effective date, calls the package daily runner, and emits its secret-safe JSON summary without duplicating sequencing. | E6.9, B1.8 |
| E6.11 | [x] | Add EODData manual DAG | Add one thin manual-only DAG that obtains Airflow context/config from the Compose environment, derives or receives the intended effective date, calls the package daily runner, and returns only small secret-safe summaries/object IDs. DAG tests cover manual scheduling, catchup, overlap, context, effective date, and imports. | E6.9-E6.10, B1.5-B1.7 |
| E6.12 | [x] | Verify EODData Airflow discovery | Rebuild/restart the Airflow image as required and verify the EODData DAG appears with its intended schedule/tags and imports without credentials in the DAG source. | E6.11 |
| E6.13 | [x] | Run EODData six-object fixture vertical test | Run the full three-exchange Symbol List plus Quote List fixture path through the DAG-callable package runner and stored report. Confirm one Core run, six raw objects and snapshot memberships, atomic listing-before-bar persistence, separate listing/bar counts, duplicate and mismatch reporting, market isolation, and the durable run/object/snapshot/report chain; then prove a rerun is unchanged. | E6.11-E6.12, S2.6 |

Done: 2026-07-17 — added the production EODData source contract in
`docs/stonks/ohlcv-eoddata-source-contract.md`, aligned the architecture,
format-evidence note, package README, and tracked/active local exchange order,
and finalized the two-source/six-object, effective-date, delivery, metadata,
duplicate, reconciliation, and unspecified-adjustment rules. Focused package
tests passed (20), combined Airflow Compose config validation passed, supplied
JSON samples validated as arrays with 2 compatible symbol duplicate groups and
0 duplicate quote groups, and consistency scans plus `git diff --check` passed.

Done: 2026-07-17 — added environment-validated EODData source settings and
public six-request acquisition/transport contracts in
`packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/{config.py,eoddata.py,
object_store.py,__init__.py}`, with deterministic Symbol-before-Quote Core
storage, bounded transport/429/5xx retries, JSON-array and empty-feed rules,
partial raw-evidence retention, safe market metadata, and secret-free errors.
Focused tests passed (49), the full package suite passed (216 passed, 9
skipped), and Poetry lock, compileall, pip check, public import, package build,
88-column scan, and `git diff --check` passed.

Done: 2026-07-17 — added the public exchange-scoped EODData Symbol List parser
and result in `empire_stonks_ohlcv/eoddata_symbols.py`, sanitized manifested
NYSE/NASDAQ/AMEX fixtures, listing-only shared parser-contract support, focused
duplicate/metadata/structural tests, public exports, and README guidance.
Compatible duplicates collapse independent of row order; conflicting identities
are rejected with deterministic bounded safe issues. Focused tests passed (24),
the full package suite passed (231 passed, 9 skipped), and compileall, pip check,
public import, package build, 88-column changed-code scan, and `git diff --check`
passed.

Done: 2026-07-17 — added the public EODData Quote List parser/reconciler and
result in `empire_stonks_ohlcv/eoddata_quotes.py`, manifested NYSE duplicate and
AMEX overlap fixtures, three-exchange shared parser-contract coverage, public
exports, and README guidance. Scope mismatches hard-fail; invalid/conflicting or
unmatched quote groups are rejected with bounded deterministic issues; accepted
Symbol List metadata and no-quote listings are preserved in shared batches.
Focused tests passed (44), the full package suite passed (248 passed, 9 skipped),
and compileall, pip check, public import, package build, 88-column changed-code
scan, and `git diff --check` passed.

Done: 2026-07-17 — finalized the shared validation/count/report contract in
`docs/stonks/ohlcv-validation-report-contract.md`; added public bounded issue,
source/market feed, source/market write, and validated-output records in
`empire_stonks_ohlcv/validation.py`; and adapted reconciled EODData results to
carry feed grains, typed row rejections, and deterministic hard-failure/warning
summaries. The contract
defines OHLC/null/volume severity, 100-sample bounds, active/inactive coverage,
calendar/weekday freshness, stale candidates, non-calendar-authoritative gaps,
and the versioned stored-report shape. Focused tests passed (82), the full suite
passed (268 passed, 9 skipped), and compileall, pip check, public import, package
build, 88-column scan, and `git diff --check` passed.

Done: 2026-07-17 — added public `import_eoddata_daily()` and compact
`EODDataImportResult` in `empire_stonks_ohlcv/eoddata_import.py`, with complete
six-object/three-market preflight validation, deterministic snapshot/listing/bar
ordering, one commit boundary, active-listing bar resolution, inactive-bar skip
counts, and source/market feed/write outcomes including derived maintenance.
Unit coverage passed (50, with the separately run DB test skipped); the focused
rollback-only PostgreSQL integration passed (1), and the full configured suite
passed (288) with no skips, proving rollback after snapshot/listing/bar writes,
insert, unchanged rerun, correction, inactive behavior, and duplicate outcomes.
Poetry check/build, compileall, pip check, public import, 88-column scan, and
`git diff --check` passed.

Done: 2026-07-17 — added public provider-parameterized market coverage,
ordered active/inactive series health, and bounded active-series weekday-gap
queries in `empire_stonks_ohlcv/health.py`, with complete gap totals and explicit
non-calendar-authoritative semantics. Unit tests cover deterministic ordering,
empty states, status separation, bounds, validation, and JSON-ready results.
The rolled-back PostgreSQL integration exercised EODData across NYSE, NASDAQ,
and AMEX at 4,500 listings and 139,200 bars, verified 150 known active-series
gap candidates while excluding inactive-series gaps, and confirmed the existing
provider-listing and `pk_ohlcv_daily` access paths; no new index was added.
The full configured package suite passed (299) with no skips, and Poetry check,
compileall, pip check, public import, package build, 88-column scan, and
`git diff --check` passed.

Done: 2026-07-17 — added the schema-version-2 EODData report builder,
deterministic JSON serializer, Core run path, and durable report storage in
`empire_stonks_ohlcv/reporting.py`. The report preserves six-object acquisition,
feed/duplicate/cross-feed/write counts at source and NYSE/NASDAQ/AMEX grains;
adds active coverage/freshness, bounded stale/no-data/gap candidates, separate
inactive counts, bounded issues, outcome, and native-semantics notes; and stores
only safe metadata without expiration. Exact typed cross-feed outcomes now flow
from reconciliation through import, and weekday-gap queries accept an optional
exact market scope. Focused report/contract tests and the rolled-back 4,500-
listing/139,200-bar PostgreSQL test passed; the full configured suite passed
(304) with no skips. Poetry check/build, compileall, pip check, public import,
88-column scan, secret-key scan, and `git diff --check` passed.

Done: 2026-07-17 — added public `run_eoddata_daily()` and compact
`EODDataDailyRunResult` in `empire_stonks_ohlcv/eoddata_runner.py`. The runner
starts one Core run, acquires Symbol List then Quote List partitions, parses and
reconciles NYSE/NASDAQ/AMEX in configured order, invokes the atomic import,
builds/stores the detailed report, and completes with IDs and aggregate safe
counts only. Acquisition, parsing, persistence, and reporting failures store
only a safe stage and fixed message before re-raising; partial raw evidence and
already committed data remain durable. Tests cover success/order, all four
failure stages, preflight without a run, partial evidence, real six-object parse
composition, secret safety, and same-date reruns with distinct Core run IDs and
unchanged counts. The full configured suite passed (314) with no skips.
Poetry check/build, compileall, pip check, public import, 88-column scan,
secret-key scan, and `git diff --check` passed.

Done: 2026-07-17 — added the `stonks-ohlcv-eoddata-daily` package command and
executable `bin/stonks-ohlcv-eoddata-daily` wrapper. The wrapper extracts only
`--env-file`, sources `bin/env-load` with `deploy/env/local.env` by default, and
delegates an explicit `--effective-date YYYY-MM-DD` to the command module. The
module loads environment-only configuration, constructs Core database/run/
object services, calls `run_eoddata_daily()` once, and prints one sorted compact
JSON result; it contains no provider sequencing. Invalid dates stop before the
database opens, and runtime failures emit only a fixed non-secret message with a
nonzero exit. CLI, wrapper syntax/help/executable-mode, entrypoint, delegation,
failure, and secret-safety tests passed; the full configured suite passed (321)
with no skips.
Poetry install/check/build, installed command help, compileall, pip check,
88-column scan, shell syntax, secret-key scan, and `git diff --check` passed.

Done: 2026-07-17 — added the thin manual-only Airflow DAG
`stonks_ohlcv_eoddata_daily_scrape`, with `schedule=None`, catchup disabled, and
one active run. Manual runs may provide a strict
`dag_run.conf.effective_date` override; otherwise the DAG derives the provider
effective date from the New York date at `data_interval_end`. Its single task
loads Compose-provided environment configuration, constructs Core services,
calls `run_eoddata_daily()` once, and returns/logs only compact safe IDs and
counts.
DAG tests cover imports, manual scheduling, overlap, date derivation/override,
invalid context input, service delegation, runner identity, and the returned
payload. The full configured suite passed (330) with no skips. Poetry
check/build, compileall, pip check, public import, Compose config validation,
88-column scan, credential-source scan, and `git diff --check` passed.

Done: 2026-07-17 — rebuilt the Airflow image and recreated the API,
scheduler, DAG processor, triggerer, and worker after confirming the previous
image contained an older `empire-stonks-ohlcv` installation without the public
`run_eoddata_daily` export. The recreated image imports the export from
`empire_stonks_ohlcv.eoddata_runner`; Airflow reports no DAG import errors and
discovers `stonks_ohlcv_eoddata_daily_scrape` paused with `schedule=None`,
catchup disabled, one active run, the `stonks`/`ohlcv`/`eoddata`/`manual` tags,
and the single `run_eoddata_daily` task.

Follow-up: the first live manual run retained its NYSE Symbol List object but
then received HTTP 429 for NASDAQ because the new client sent consecutive
partitions without the two-second pacing used by the proven legacy client.
Acquisition now spaces all six requests with the environment-configurable
`EMPIRE_STONKS_OHLCV_EODDATA_REQUEST_DELAY_SECONDS` (default `2`) and uses a
two-second bounded exponential retry base when `Retry-After` is absent. Tests
cover pacing, provider-directed delay, fallback retry timing, retained partial
evidence, and secret safety. The configured suite passed (333) with no skips;
the Airflow image was rebuilt/recreated and verified with the new settings.

The next live rerun acquired all six objects and committed the import, then
exposed PostgreSQL's `sum(bigint) -> numeric` behavior in report health counts:
`active_bar_count` and `inactive_bar_count` arrived as Python `Decimal` values.
The shared health-query boundary now normalizes all aggregate counts to its
declared integer contract before reporting. Unit coverage uses Decimal-shaped
database rows, PostgreSQL integration verifies integer/JSON-ready results, and
integration fixtures no longer assume an empty live EODData provider scope or
one fixed query-plan choice. The configured suite passed (333) with no skips;
the rebuilt Airflow worker JSON-serialized the live NYSE/NASDAQ/AMEX health
results successfully and Airflow reported no import errors.

The following live manual rerun completed one Core run and stored all six raw
objects plus the report. Its idempotent persistence result was 13,601 unchanged
listings and 12,161 unchanged bars. The technical run succeeded, while the
original stored quality outcome was `FAIL`: 464 structurally invalid OHLC
groups (1
NYSE, 4 NASDAQ, 459 AMEX) and 3 conflicting duplicate groups (2 NASDAQ, 1
AMEX) were rejected; no quote lacked a same-market Symbol List identity. Raw
samples show the dominant AMEX defect is zero-volume data whose close lies
outside the provider-supplied open/high/low range. Validation remains strict.
The report contract was subsequently corrected so these safely excluded rows
produce `WARN`, not `FAIL`: rejection buckets now retain exact market, source,
reason, rejected-identity count, rejected-row count, and bounded samples. Only
partition/run-integrity problems are hard failures; aborting acquisition or
parsing failures also record safe market/source scope when known. The DAG
remains manual pending further operational review.

Done: 2026-07-17 — revised the EODData quality boundary after the first live
run. Safe row/group exclusions now flow through typed market/source/reason
rejection summaries and produce `WARN`; `FAIL` is reserved for hard
partition/run-integrity findings. Reports use schema version 2, retain grouped
identity and raw-row totals per market, and expose market-specific hard-failure
sections. Compact runner/Core summaries include rejection totals, while
aborting acquisition and parsing failures retain safe market/source scope when
known. The configured PostgreSQL suite passed (335). Replaying the retained six
live objects produced `WARN`, zero hard failures, 467 rejected identities, and
470 rejected rows: NYSE 1/1, NASDAQ 6/8, and AMEX 460/461. The rebuilt Airflow
worker loaded the schema-version-2 package and the manual DAG had no import
errors.

Done: 2026-07-17 — corrected backdated report health after a 2026-07-16 run
followed an already imported 2026-07-17 run. The shared market, series, and
weekday-gap queries now accept an inclusive `as_of_date`; report coverage,
freshness, bar counts, and gaps exclude later stored bars without hiding
listings that have no in-scope data. The redundant current-state
`future_last_trading_date` report failure was removed because parser/import
preflight already requires accepted bars to match the effective date. The
configured PostgreSQL suite passed (336). Replaying the retained six objects
produced `WARN`, zero hard failures, 8 rejected identities, 11 rejected rows,
12,665 in-scope bars, and `current` freshness for all three markets.

Done: 2026-07-17 — added a configured PostgreSQL/Core vertical integration
test that drives generated NYSE, NASDAQ, and AMEX Symbol List and Quote List
fixtures through the public DAG-callable EODData runner. Each invocation proves
one Core run, six raw objects, six snapshot memberships, a stored report,
listing-before-bar write order, separate per-market listing/bar counts,
market-isolated overlapping tickers, and exact duplicate/mismatch rejection
buckets. The first import inserted five listings and three bars; an identical
second run created a new durable run/object/report chain while all five listings
and three bars were unchanged. The full configured suite passed (337) with no
skips; Poetry lock/check/build, compileall, pip check, public import,
88-column scan, and `git diff --check` passed.

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
storage.

## Phase 8: Yahoo Daily End-To-End Vertical Slice

Goal: seed the deliberately bounded Yahoo benchmark universe, backfill its
provider-native daily bars, and keep every eligible completed market session
current without using Yahoo for ordinary equities already covered by EODData.
Calendar-aware eligibility, retries, and reconciliation belong in the package;
Airflow only invokes that logic.

### Initial Yahoo Seed Universe

Y8.4 must seed the following 93 provider listings. `Empire code` is the stable
`provider_listing.ticker` inside the provider-scoped `XIDX` market. `Yahoo
ticker` is the exact acquisition symbol stored as metadata key `YahooTicker`;
it is not a second relational ticker column and is never stored in `market`.
The migration should preserve this reviewed starting universe while allowing a
later migration to add, correct, deactivate, or remove individual listings.

| Empire code | Yahoo ticker | Name | Instrument type |
|-------------|--------------|------|-----------------|
| SPX | ^GSPC | S&P 500 Index | EQUITY_INDEX |
| DJI | ^DJI | Dow Jones Industrial Average | EQUITY_INDEX |
| DJT | ^DJT | Dow Jones Transportation Average | EQUITY_INDEX |
| DJU | ^DJU | Dow Jones Utility Average | EQUITY_INDEX |
| NDX | ^NDX | Nasdaq-100 Index | EQUITY_INDEX |
| IXIC | ^IXIC | Nasdaq Composite Index | EQUITY_INDEX |
| NYA | ^NYA | NYSE Composite Index | EQUITY_INDEX |
| RUT | ^RUT | Russell 2000 Index | EQUITY_INDEX |
| RUA | ^RUA | Russell 3000 Index | EQUITY_INDEX |
| W5000 | ^W5000 | Wilshire 5000 Total Market Index | EQUITY_INDEX |
| OEX | ^OEX | S&P 100 Index | EQUITY_INDEX |
| SP400 | ^SP400 | S&P MidCap 400 Index | EQUITY_INDEX |
| SP600 | ^SP600 | S&P SmallCap 600 Index | EQUITY_INDEX |
| SOX | ^SOX | PHLX Semiconductor Index | EQUITY_INDEX |
| NYFANG | ^NYFANG | NYSE FANG+ Index | EQUITY_INDEX |
| VIX | ^VIX | CBOE Volatility Index | VOLATILITY_INDEX |
| VXN | ^VXN | CBOE Nasdaq-100 Volatility Index | VOLATILITY_INDEX |
| RVX | ^RVX | CBOE Russell 2000 Volatility Index | VOLATILITY_INDEX |
| VVIX | ^VVIX | CBOE VIX Volatility Index | VOLATILITY_INDEX |
| SKEW | ^SKEW | CBOE SKEW Index | VOLATILITY_INDEX |
| MOVE | ^MOVE | ICE BofA MOVE Bond Volatility Index | VOLATILITY_INDEX |
| UST5Y | ^FVX | U.S. Treasury 5-Year Yield Index | YIELD_INDEX |
| UST10Y | ^TNX | U.S. Treasury 10-Year Yield Index | YIELD_INDEX |
| UST30Y | ^TYX | U.S. Treasury 30-Year Yield Index | YIELD_INDEX |
| FTSE | ^FTSE | FTSE 100 Index | EQUITY_INDEX |
| DAX | ^GDAXI | DAX 40 Index | EQUITY_INDEX |
| CAC | ^FCHI | CAC 40 Index | EQUITY_INDEX |
| STOXX50E | ^STOXX50E | EURO STOXX 50 Index | EQUITY_INDEX |
| STOXX600 | ^STOXX | STOXX Europe 600 Index | EQUITY_INDEX |
| IBEX | ^IBEX | IBEX 35 Index | EQUITY_INDEX |
| AEX | ^AEX | AEX Netherlands Index | EQUITY_INDEX |
| SMI | ^SSMI | Swiss Market Index | EQUITY_INDEX |
| FTSEMIB | FTSEMIB.MI | FTSE MIB Index | EQUITY_INDEX |
| OMXSTO30 | ^OMX | OMX Stockholm 30 Index | EQUITY_INDEX |
| BEL20 | ^BFX | BEL 20 Index | EQUITY_INDEX |
| PSI20 | PSI20.LS | PSI 20 Index | EQUITY_INDEX |
| ISEQ | ^ISEQ | ISEQ Overall Index | EQUITY_INDEX |
| N225 | ^N225 | Nikkei 225 Index | EQUITY_INDEX |
| HSI | ^HSI | Hang Seng Index | EQUITY_INDEX |
| HSCEI | ^HSCE | Hang Seng China Enterprises Index | EQUITY_INDEX |
| KOSPI | ^KS11 | KOSPI Composite Index | EQUITY_INDEX |
| SHCOMP | 000001.SS | Shanghai Composite Index | EQUITY_INDEX |
| CSI300 | 000300.SS | CSI 300 Index | EQUITY_INDEX |
| SZCOMPONENT | 399001.SZ | Shenzhen Component Index | EQUITY_INDEX |
| TWSE | ^TWII | Taiwan Weighted Index | EQUITY_INDEX |
| STI | ^STI | Straits Times Index | EQUITY_INDEX |
| SET | ^SET | Stock Exchange of Thailand SET Index | EQUITY_INDEX |
| JCI | ^JKSE | Jakarta Composite Index | EQUITY_INDEX |
| KLCI | ^KLSE | FTSE Bursa Malaysia KLCI Index | EQUITY_INDEX |
| PSEI | PSEI.PS | Philippine Stock Exchange PSEi Index | EQUITY_INDEX |
| NIFTY50 | ^NSEI | Nifty 50 Index | EQUITY_INDEX |
| SENSEX | ^BSESN | BSE Sensex Index | EQUITY_INDEX |
| ASX200 | ^AXJO | S&P/ASX 200 Index | EQUITY_INDEX |
| TSXCOMP | ^GSPTSE | S&P/TSX Composite Index | EQUITY_INDEX |
| BOVESPA | ^BVSP | Bovespa Index | EQUITY_INDEX |
| MEXIPC | ^MXX | S&P/BMV IPC Index | EQUITY_INDEX |
| MERVAL | ^MERV | S&P MERVAL Index | EQUITY_INDEX |
| IPSA | ^IPSA | S&P IPSA Index | EQUITY_INDEX |
| JTOPI | ^JA0R.JO | FTSE/JSE Top 40 Index | EQUITY_INDEX |
| XU100 | XU100.IS | BIST 100 Index | EQUITY_INDEX |
| TA125 | ^TA125.TA | TA-125 Index | EQUITY_INDEX |
| TASI | ^TASI.SR | Tadawul All Share Index | EQUITY_INDEX |
| MSCIWORLD | ^990100-USD-STRD | MSCI World Index | EQUITY_INDEX |
| MSCIEM | ^891800-USD-STRD | MSCI Emerging Markets Index | EQUITY_INDEX |
| MSCIACWI | ^892400-USD-STRD | MSCI All Country World Index | EQUITY_INDEX |
| GSCI | ^SPGSCI | S&P GSCI Commodity Index | COMMODITY_INDEX |
| BCOM | ^BCOM | Bloomberg Commodity Index | COMMODITY_INDEX |
| DXY | DX-Y.NYB | ICE U.S. Dollar Index | CURRENCY_INDEX |
| ES | ES=F | E-mini S&P 500 Futures | CONTINUOUS_FUTURE_EQUITY |
| NQ | NQ=F | E-mini Nasdaq-100 Futures | CONTINUOUS_FUTURE_EQUITY |
| YM | YM=F | E-mini Dow Jones Industrial Average Futures | CONTINUOUS_FUTURE_EQUITY |
| RTY | RTY=F | E-mini Russell 2000 Futures | CONTINUOUS_FUTURE_EQUITY |
| WTI | CL=F | WTI Crude Oil Futures | CONTINUOUS_FUTURE_COMMODITY |
| BRENT | BZ=F | Brent Crude Oil Futures | CONTINUOUS_FUTURE_COMMODITY |
| NATGAS | NG=F | Henry Hub Natural Gas Futures | CONTINUOUS_FUTURE_COMMODITY |
| HEATOIL | HO=F | New York Harbor ULSD Heating Oil Futures | CONTINUOUS_FUTURE_COMMODITY |
| RBOB | RB=F | RBOB Gasoline Futures | CONTINUOUS_FUTURE_COMMODITY |
| GOLD | GC=F | Gold Futures | CONTINUOUS_FUTURE_COMMODITY |
| SILVER | SI=F | Silver Futures | CONTINUOUS_FUTURE_COMMODITY |
| COPPER | HG=F | Copper Futures | CONTINUOUS_FUTURE_COMMODITY |
| PLATINUM | PL=F | Platinum Futures | CONTINUOUS_FUTURE_COMMODITY |
| PALLADIUM | PA=F | Palladium Futures | CONTINUOUS_FUTURE_COMMODITY |
| CORN | ZC=F | Corn Futures | CONTINUOUS_FUTURE_COMMODITY |
| WHEAT | ZW=F | Chicago SRW Wheat Futures | CONTINUOUS_FUTURE_COMMODITY |
| SOYBEANS | ZS=F | Soybean Futures | CONTINUOUS_FUTURE_COMMODITY |
| SOYMEAL | ZM=F | Soybean Meal Futures | CONTINUOUS_FUTURE_COMMODITY |
| SOYOIL | ZL=F | Soybean Oil Futures | CONTINUOUS_FUTURE_COMMODITY |
| COFFEE | KC=F | Coffee C Futures | CONTINUOUS_FUTURE_COMMODITY |
| SUGAR | SB=F | Sugar No. 11 Futures | CONTINUOUS_FUTURE_COMMODITY |
| COCOA | CC=F | Cocoa Futures | CONTINUOUS_FUTURE_COMMODITY |
| COTTON | CT=F | Cotton No. 2 Futures | CONTINUOUS_FUTURE_COMMODITY |
| LIVECATTLE | LE=F | Live Cattle Futures | CONTINUOUS_FUTURE_COMMODITY |
| LEANHOGS | HE=F | Lean Hogs Futures | CONTINUOUS_FUTURE_COMMODITY |

Y8.13.2 retained these 93 rows as the starting-universe audit trail, corrected
the active `JTOPI` and `SET` request symbols to `^J200.JO` and `^SET.BK`, and
marked `IPSA`, `MSCIEM`, and `RVX` inactive with a documented
`metadata.YahooSeedReview` disposition. The controlled active universe is now
90 listings. Y8.13.3 subsequently retained the historical bars and exact
mappings for `BCOM`, `CSI300`, `MOVE`, `PSEI`, `TASI`, and `W5000`, but marked
the listings inactive with an `UNAVAILABLE_STALE_HISTORY` disposition after
Yahoo returned only empty OHLC placeholders beyond July 16/17 and no exact
continuous alternative was found. Y8.13.4's targeted retry then proved that
corrected `SET` (`^SET.BK`) also stopped after July 17, so it is retained with
the same inactive disposition. The controlled active universe is now 83
listings.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| Y8.1 | [x] | Document the Yahoo source and bounded-universe contract | Record the chosen daily OHLCV endpoint, `EMPIRE_STONKS_OHLCV_YAHOO_*` settings, request/range limits, ticker and provider-date semantics, time zones, native adjusted-close and volume behavior, rate/error behavior, and Core raw retention. Explicitly limit Yahoo to the seeded indexes, yield and volatility indexes, currency and commodity indexes, and continuous futures; exclude ordinary equities and non-OHLCV enrichment. Runtime values come from `deploy/env/local.env`. | H7.8, A5.1-A5.2 |
| Y8.2 | [x] | Design the shared market-session eligibility contract | Define the smallest reusable representation for each provider listing's calendar, local session/time zone, post-close delay, and session-date rule. Cover exchange-traded cash indexes, publisher-calculated indexes, DXY, and Yahoo `=F` provider daily-settlement series. Define `eligible_at`, missing-session detection, no synthetic weekend/holiday bars, retry behavior, and a configurable 5-7-session reconciliation window. Record why the selected market-calendar library is justified and how unsupported calendars or provider-date ambiguity fail safely. | Y8.1, M3.7 |
| Y8.3 | [x] | Add Yahoo instrument taxonomy migration | Add an idempotent Flyway migration for `YIELD_INDEX`, `EQUITY_INDEX`, `COMMODITY_INDEX`, `CURRENCY_INDEX`, `CONTINUOUS_FUTURE_COMMODITY`, and `CONTINUOUS_FUTURE_EQUITY`, using existing `INDEX` and `DERIVATIVE` classes and the reference-data upsert convention. Database validation and generated Stonks schema docs pass. | Y8.2 |
| Y8.4 | [x] | Add Stonks session-policy table and seed Yahoo provider listings | Implement the Y8.2 persistence design inside the existing `stonks` PostgreSQL schema and seed the complete reviewed Yahoo catalog into `stonks.provider_listing` under the existing `YAHOO` provider. Store the Empire code as `provider_listing.ticker`, store the exact acquisition symbol as metadata key `YahooTicker`, add no Yahoo-specific relational ticker column, and never overload `market`. Attach an instrument type and explicit session policy to every row. The migration is deterministic/idempotent, rejects missing provider/type/calendar references, contains no ordinary equities, and has assertions/tests for representative cash indexes, global indexes, yields, volatility, DXY, equity-index futures, and commodity futures. | Y8.2-Y8.3 |
| Y8.5 | [x] | Implement calendar and eligibility services | Add package-owned services that resolve expected sessions from the configured market calendar, honor local holidays and early closes, calculate `eligible_at = session_close + availability_delay`, and return only eligible missing sessions. Implement an explicit provider-daily-settlement cutoff for Yahoo continuous futures and safe handling for publisher indexes without an exchange calendar. Tests cross UTC/date boundaries, DST, holidays, early closes, disjoint country holidays, reruns, and unknown calendars. | Y8.4 |
| Y8.6 | [x] | Implement Yahoo acquisition | Acquire bounded historical ranges for selected seeded Yahoo listings with injected HTTP dependencies, timeouts, bounded retries, request pacing, and chunking where the source requires it. Store every response through Core with durable snapshot identity and secret-safe errors/metadata. Tests cover rate limiting, empty/malformed/error payloads, partial symbol failures, and request-boundary dates. | Y8.1, Y8.4-Y8.5, C4.2, A5.5 |
| Y8.7 | [x] | Implement Yahoo parser | Parse Yahoo fixtures into shared provider-listing and daily-bar records with correct provider session dates, nullable volume where valid, deterministic duplicate handling, and documented adjusted-close treatment consistent with the shared table contract. Do not silently substitute adjusted close for native close or add Yahoo-only columns. | Y8.1, Y8.6, A5.3-A5.4 |
| Y8.8 | [x] | Implement Yahoo import service | Compose validation, snapshot registration, seeded provider-listing resolution, daily-bar upserts, and per-listing import summaries. Do not create unseeded Yahoo listings during normal import. Unchanged reruns skip writes, later provider corrections update current rows, and one listing failure does not discard successful listings. | Y8.6-Y8.7, E6.5-E6.6 |
| Y8.9 | [x] | Add Yahoo historical backfill runner and CLI | Add a package-owned backfill runner, operator CLI, and `bin` wrapper using `bin/env-load`. It enumerates all active seeded Yahoo listings, accepts explicit bounded date/range controls and safe resume/retry behavior, imports available history in source-safe chunks, records Core lifecycle/lineage, and emits a secret-safe machine-readable summary and report. Tests cover full enumeration, partial restart, unchanged rerun, correction, and partial failure. | Y8.8, B1.8 |
| Y8.10 | [x] | Implement Yahoo daily completeness planning | For each active seeded Yahoo listing, determine completed expected sessions, calculate eligibility, compare them with stored `ohlcv_daily` rows, and produce a bounded pull plan containing only eligible missing sessions. A rerun before eligibility or after completion is a no-op; a failed/missing session remains retryable on a later run. Tests prove one record per real market session across U.S., European, Asian, and futures examples. | Y8.5, Y8.8-Y8.9 |
| Y8.11 | [x] | Add recent-session reconciliation | Add a daily reconciliation pass that re-pulls the configured recent 5-7 expected sessions, compares provider OHLC, close/adjustment semantics, and volume with current rows, and applies idempotent corrections through the normal upsert path. Surface corrected-row counts and field-level differences in run results/reports without adding a bar-revision table. Tests cover late bars, changed values, null volume, provider-date corrections, and unchanged history. | Y8.7-Y8.10 |
| Y8.12 | [x] | Build and store Yahoo reports | Reuse the shared report contract for Yahoo-scoped backfill and daily health, expected-session coverage, ineligible versus missing sessions, stale listings, retries/failures, reconciliation corrections, calendar-policy errors, and native adjustment notes. Reports distinguish initial ingestion from reconciliation and remain queryable after raw-object cleanup. | Y8.9-Y8.11, E6.7-E6.8 |
| Y8.13 | [x] | Add Yahoo daily runner and CLI | Add package-owned sequencing and an operator CLI/`bin` wrapper that run eligibility planning, eligible missing-session ingestion, recent-session reconciliation, Core lifecycle, and reporting with configured request bounds. Tests cover no-op, success, partial failure, retry, correction, and idempotent rerun. | Y8.10-Y8.12, B1.8 |
| Y8.13.1 | [x] | Separate Yahoo response time zone from session-policy time zone | Review the parser's assumption that Yahoo `exchangeTimezoneName` must equal the listing's eligibility-policy time zone. Model and validate provider response/session-date interpretation separately from exchange calendar or cutoff eligibility without weakening symbol, date, or calendar checks. Preserve the intended policies for `SKEW`, `VVIX`, `VXN`, `UST5Y`, `UST10Y`, and `UST30Y`, and prove their stored fixtures parse into the correct provider dates across DST boundaries. | Y8.7, Y8.11-Y8.13 |
| Y8.13.2 | [x] | Correct Yahoo empty-history classification and remediate unusable seed mappings | Treat a structurally valid Chart result with metadata/indicators but `timestamp=null` as an explicit no-history/no-data outcome rather than a generic malformed-chart failure when safe. Review current Yahoo availability and exact `metadata.YahooTicker` values for `IPSA`, `JTOPI`, `MSCIEM`, `SET`, and the HTTP-404 `RVX`; correct mappings through an idempotent Flyway migration when a valid replacement exists, otherwise explicitly deactivate or document the unsupported seed instead of allowing permanent daily warnings. Tests distinguish malformed payloads, empty history, provider errors, symbol mismatch, and unavailable/deactivated seeds. | Y8.4, Y8.6-Y8.8, Y8.13 |
| Y8.13.3 | [x] | Investigate and classify stale Yahoo series | Determine why `BCOM`, `CSI300`, `MOVE`, `PSEI`, and `W5000` stopped at 2026-07-17 and `TASI` stopped at 2026-07-16 while peer series reached 2026-07-30. Check current Yahoo symbol availability, response contents, provider-date behavior, and session-policy expectations. Correct ticker/policy metadata or deactivate genuinely discontinued/unavailable seeds through Flyway; do not suppress real eligible-session gaps or manufacture bars. Add report/planner tests for the selected disposition. | Y8.10, Y8.12-Y8.13 |
| Y8.13.4 | [x] | Run targeted Yahoo remediation verification | Retry only the affected tickers after Y8.13.1-Y8.13.3, not the healthy 82-listing universe. Verify correct acquisition classifications, provider dates, session eligibility, database coverage, reconciliation behavior, reports, and rerun idempotency. Record any intentionally unsupported/deactivated listings and require no unexplained persistent warnings before proceeding to the DAG. | Y8.13.1-Y8.13.3 |
| Y8.14 | [x] | Add the initially manual Yahoo DAG | Add `dags/stonks/stonks_ohlcv_yahoo_daily_scrape.py` as a thin manually triggered DAG that invokes the daily runner. Keep schedule selection out of the DAG's business logic; document the intended eventual multi-run cadence (for example 06:00, 10:00, 13:00, 18:00, and 23:00 America/New_York, or hourly if live request volume permits) and leave automatic enablement to the rollout gate. DAG tests prove importability, manual schedule state, parameter forwarding, no-op success, and failure propagation. | Y8.13.4, B1.5-B1.7 |
| Y8.14.1 | [x] | Add professional Yahoo PDF reports | Render and durably store a branded human-readable `report.pdf` beside `report.json` for every successful Yahoo backfill and daily run. Cover executive status, run scope, acquisition and persistence, provider-series coverage, daily health and reconciliation, native-value semantics, and bounded warning samples. Return both object IDs through Core, CLI, and Airflow summaries and prove both report modes render and persist valid PDFs. | Y8.12-Y8.14, E6.7-E6.8 |
| Y8.15 | [x] | Verify the Yahoo vertical workflow | Run the complete fixture path from seeded listings through backfill, eligibility-based daily ingestion, reconciliation, stored reports, and raw-object cleanup. Verify lineage, secret safety, request bounds, calendar behavior, provider isolation, reruns, corrections, and coexistence with EODData and historical Stooq data. Verify the manual DAG is discovered in its Airflow runtime. | Y8.14.1, M3.7 |

Done: 2026-07-29 — selected bounded single-symbol Yahoo Chart `1d` JSON for
both seeded-universe backfill and daily/reconciliation in
`docs/stonks/ohlcv-yahoo-source-contract.md`; added validated, secret-safe
Yahoo settings in `packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/config.py`
and the OHLCV sections of `deploy/env/local{,.example}.env`; aligned the
architecture/package docs and config/secret tests. Focused tests passed (47),
the full package suite passed (397 passed, 17 skipped), and `poetry check`,
`compileall`, example-environment config smoke, environment-key parity,
88-column changed-Python scan, and `git diff --check` passed.

Done: 2026-07-29 — designed the shared provider-listing session policy in
`docs/stonks/ohlcv-market-session-contract.md`: selected
`pandas_market_calendars`, defined the normalized policy/FK handoff for Y8.4,
calendar-close and local-cutoff eligibility, three provider-date rules,
authoritative versus observed-only completeness, safe retry/reconciliation,
no-synthetic-bar invariants, and fail-closed behavior for unsupported or
ambiguous mappings. Documentation validation and `git diff --check` passed.

Done: 2026-07-29 — added idempotent migration
`V2026.07.29.0001__stonks_add_yahoo_instrument_taxonomy.sql` with the six
reviewed Yahoo index and continuous-future types under the existing `INDEX`
and `DERIVATIVE` classes. Flyway applied and validated all 33 migrations; a
direct second execution succeeded and retained exactly six active rows with
the expected classes. The transactional OHLCV schema contract passed, and
canonical Core/Stonks schema plus all Stonks ERD groups regenerated without
structural diffs. `git diff --check` passed.

Done: 2026-07-30 — added
`V2026.07.30.0001__stonks_add_ohlcv_session_policies_and_yahoo_listings.sql`
inside the existing `stonks` schema with the normalized session-policy table,
nullable provider-listing FK, policy-shape constraints, Yahoo metadata
constraint, and unique `YahooTicker` expression index. Seeded 49 reviewed
policies and all 93 active `YAHOO`/`XIDX` listings with the Empire code as
`provider_listing.ticker`, the exact request symbol in `metadata.YahooTicker`,
and an explicit instrument type and policy. Calendar-backed policy names were
resolved and year schedules exercised with `pandas_market_calendars` 5.4.0;
unsupported or provider-calculated cases use explicit observed-only policies.
Flyway applied and validated all 34 migrations, direct migration replay
succeeded, both OHLCV schema and Yahoo seed SQL contracts passed, the full
package suite passed (397 passed, 17 skipped), and canonical Stonks
schema/Mermaid/pg-diagram documentation regenerated. `git diff --check`
passed.

Done: 2026-07-30 — added immutable session-policy, calendar-schedule,
expected-session, and observed-poll values plus the package-owned
`MarketSessionService`. The narrow `pandas_market_calendars` adapter resolves
authoritative closes and fails closed for unknown calendars or unreviewed
warnings. Eligibility supports exact close delays, provider-local cutoffs,
Yahoo daily-settlement labels, eligible-missing selection, and explicit
observed-only polling without synthetic sessions. Tests cover normal and early
closes, DST, UTC-date crossings, disjoint U.S./European/Asian holidays,
idempotent reruns, futures ambiguity, unsafe calendars/time zones/warnings, and
ambiguous or nonexistent local times. The full package suite passed (420
passed, 17 skipped).

Done: 2026-07-30 — implemented bounded, serial Yahoo Chart acquisition for
caller-selected seeded listings with immutable target/request/outcome values,
exact percent-encoded request paths, guarded inclusive/exclusive Unix bounds,
and deterministic backfill chunking. Added injected transport, sleep, random,
and clock seams; conservative pacing, jitter, `Retry-After`, exponential
retry, and failure cooldown; ambiguity checks for provider-listing and
`YahooTicker` identity; and partial-failure results. Every HTTP 200 body is
stored through Core before safe Chart-envelope classification, while non-200
and transport failures expose no body or URL content. Tests cover 408/425/429
and 5xx retries, pre-Unix-epoch boundaries, chunk edges, empty/malformed/error
payloads, symbol mismatch, missing daily data, empty backfills, raw-storage
failure, and successful listings around a failed symbol. The full package
suite passed (446 passed, 17 skipped).

Done: 2026-07-30 — implemented deterministic Yahoo Chart parsing against the
exact seeded Empire ticker, `metadata.YahooTicker`, acquisition range,
session policy, response IANA time zone, and caller-planned calendar labels.
The parser validates the Chart envelope and positional arrays, converts JSON
numeric text directly to `Decimal`, preserves null and zero volume, derives
provider-local and daily-settlement dates without UTC truncation, and emits
shared `ProviderListing`/`DailyBar` output without enrichment. Adjusted close
is retained only in parse diagnostics and never replaces native close.
Unplanned and invalid rows receive bounded safe issues; equal duplicates
collapse and conflicting duplicates reject the date independent of input
order. Added a policy-compliant constructed Yahoo fixture plus generated tests
for futures UTC-date crossing, observed-only bounds, structural failures,
timezone and symbol mismatches, invalid OHLCV/timestamps/adjusted close, and
array alignment. The full package suite passed (466 passed, 17 skipped).

Done: 2026-07-30 — implemented `import_yahoo_ranges()` as a package-owned,
seed-only Yahoo persistence service. Each acquired request chunk resolves and
locks its durable provider-listing UUID, fails closed on inactive or changed
seed identity, registers valid stored bodies as provider snapshots, and writes
matching parsed bars through the shared current-state upsert without calling
the provider-listing writer. Independent chunk transactions preserve successful
listings across acquisition, seed-resolution, and persistence failures, while
ordered per-listing summaries retain only bounded safe diagnostics and counts.
Unit and PostgreSQL integration coverage proves no unseeded listing creation,
snapshot lineage, partial-failure isolation, unchanged reruns, later provider
corrections, and inactive-listing protection. The full database-enabled package
suite passed (493 passed); `poetry check --lock`, public import and `compileall`
smokes, the 88-column changed-Python scan, and `git diff --check` passed.

Done: 2026-07-30 — added reusable active Yahoo seed/session-policy
enumeration, explicit `YahooBackfillScope` date and ticker controls, inclusive
Empire-ticker resume, and `run_yahoo_backfill()` package sequencing. The runner
acquires the complete selected universe with existing serial pacing and
source-bounded chunking, heartbeats and emits safe progress per acquisition,
parses stored bodies against each seed policy, and independently imports every
chunk through Y8.8. Successful chunks remain committed across partial
provider/parse/persistence failures; same-range retries are unchanged and later
provider corrections update current rows. Core runs retain safe params and
summaries plus a durable schema-versioned JSON execution report. Added the
`stonks-ohlcv-yahoo-backfill` Poetry command and executable `bin` wrapper with
configured/default date bounds, repeated ticker selection, inclusive resume,
JSON stderr progress, and compact JSON stdout. Unit and PostgreSQL vertical
coverage proves full enumeration, scoped inclusive restart, unchanged rerun,
provider correction, mixed partial failure, durable report lineage, and
secret-safe failure handling. The full database-enabled package suite passed
(510 passed); `poetry check --lock`, public import and `compileall` smokes,
shell syntax/help validation, the 88-column changed-Python scan, and
`git diff --check` passed.

Done: 2026-07-31 — added package-owned Yahoo daily completeness planning over
the active seeded listing/session-policy catalog and exact bounded
`ohlcv_daily` date reads. Calendar-backed plans retain expected, eligible,
ineligible, and missing distinctions and emit tightly bounded daily Chart
pulls justified only by eligible absent session labels; completed and
pre-eligibility reruns are no-ops, while unstored work remains stateless and
retryable. Explicit observed-only policies emit due polling candidates without
claiming authoritative gaps. Distinct policies are resolved once per plan,
stored sessions split request ranges, configured source bounds are enforced,
and calendar-policy failures remain isolated with secret-safe reasons. Unit
coverage exercises deterministic retries, no-ops, bounds, observed-only
semantics, failure isolation, and real U.S., European, Asian, and futures
calendars; PostgreSQL coverage proves exact seed enumeration/date comparison,
completion no-op behavior, and retry planning. A read-only smoke over the seven
live sample series found no policy failures or earlier in-window gaps and
planned only the not-yet-stored 2026-07-31 work, correctly labeling DXY as an
observed poll rather than an authoritative missing session. The full
database-enabled package suite passed (521 passed); `poetry check --lock`,
public import, `compileall`, the 88-column changed-Python scan, and
`git diff --check` passed.

Done: 2026-07-31 — added bounded recent-session reconciliation planning over
Y8.10 completeness results. Calendar-backed listings re-pull the latest
configured eligible expected labels whether stored or missing; observed-only
listings use recent stored provider dates plus a due poll without manufacturing
expected sessions. Added reusable database-scale daily-bar comparison and
reconciliation-aware Yahoo imports that classify inserted, unchanged, and
corrected rows before applying the normal current-state upsert. Results retain
ordered old/new OHLCV field differences, including null-volume transitions,
and require comparison totals to agree with persistence counts. Current raw
adjusted close is compared with native close and explicitly remains
non-persisted; valid newly returned provider dates are surfaced as inserts
without heuristically deleting another stored date. Unit coverage proves
recent-N selection, ineligible exclusion, source-bound splitting, normalized
field comparison, and observed-only behavior. PostgreSQL coverage proves
stored-plus-missing planning, a late/corrected provider-date insert, OHLC and
null-volume correction, adjusted-close diagnostics, normal upsert persistence,
and an unchanged idempotent rerun. A read-only smoke over the seven populated
sample series produced one bounded pull per listing with no policy failures:
seven recent sessions for each calendar-backed listing and seven recent stored
dates plus one due poll for observed-only DXY. The full database-enabled
package suite passed (527 passed); `poetry check --lock`, public import,
`compileall`, the 88-column changed-Python scan, and `git diff --check` passed.

Done: 2026-07-31 — added shared-schema-version-2 Yahoo report builders and a
single durable Core storage boundary for historical backfill and daily health.
Backfill reports now identify initial ingestion, retain retry/failure and
post-import persisted range coverage, and aggregate large history scopes in
PostgreSQL without loading every date. Daily reports preserve distinct eligible
ingestion and recent reconciliation phases, calendar-authoritative expected,
eligible, ineligible, stored, and missing counts, latest-session staleness,
observed-only unresolved polls without false coverage claims, and bounded
calendar-policy errors. Reconciliation sections retain inserted/corrected/
unchanged totals, OHLCV field-difference counts, and native-versus-adjusted
close diagnostics while reaffirming that only native close is persisted.
Reports are deterministic, secret-safe, stored without expiration, and remain
readable after the same run's expiring raw objects are deleted and purged.
Unit and PostgreSQL coverage verifies report semantics, durable metadata,
backfill schema migration, retries/failures, corrections, adjustment notes,
and cleanup-safe report access. The full database-enabled package suite passed
(531 passed); `poetry check`, public import, `compileall`, the 88-column
changed-Python scan, and `git diff --check` passed.

Done: 2026-07-31 — added `run_yahoo_daily()` as the package-owned Core
lifecycle for calendar eligibility planning, eligible-missing ingestion,
recent-session reconciliation, post-import health reporting, and durable report
storage. Added explicit `YahooDailyScope` and compact secret-safe run results,
per-phase progress/heartbeat reporting, configured 30-day default lookback and
30-day maximum daily request range, exact ticker scoping, and safe systemic
failure summaries. Sessions freshly acquired during ingestion are omitted from
same-run reconciliation to avoid duplicate raw-object identities and redundant
provider calls; failed acquisitions remain eligible for the reconciliation
retry, and later runs retain the full recent-session correction pass. Added the
`stonks-ohlcv-yahoo-daily` Poetry command and executable `bin` wrapper using
`bin/env-load`, with optional bounded dates/tickers, JSON stderr progress, and
compact JSON stdout. Unit, CLI, and PostgreSQL vertical coverage proves no-op,
successful ingestion, mixed partial failure, same-run retry, later retry,
idempotent rerun, provider correction, report phase/correction visibility, and
final database values. The full database-enabled package suite passed (546
passed); `poetry check`, public import, `compileall`, shell syntax/help, the
88-column changed-Python scan, environment-key parity, and `git diff --check`
passed.

Done: 2026-08-01 — ran the Y8.13.1-Y8.13.3 remediation scope without touching
the healthy universe. Backfill run
`fcf7e037-34c2-4784-b2b4-60e0db9ba8ec` selected eight active listings, stored
and imported all eight requests, inserted 3,131 bars, had no missing, failed,
or parse-failed chunks, and stored PASS report
`4fc4b170-3d07-4e20-a404-5ddaccec1f06`. `JTOPI`, `SKEW`, `UST5Y`, `UST10Y`,
`UST30Y`, `VVIX`, and `VXN` cover 2025-01-02 through 2026-07-30 with the
expected provider symbols and provider dates. The retry also proved that
corrected `SET` (`^SET.BK`) returns a valid empty-history response for every
Bangkok session after its last complete bar on 2026-07-17; migration
`V2026.08.01.0003__stonks_deactivate_stale_yahoo_set.sql` therefore preserves
its 372 accepted bars and corrected-symbol audit trail while marking it
`UNAVAILABLE_STALE_HISTORY` and inactive.

The resulting inactive review set is `IPSA`, `MSCIEM`, and `RVX` as
`UNSUPPORTED`, plus `BCOM`, `CSI300`, `MOVE`, `PSEI`, `SET`, `TASI`, and
`W5000` as `UNAVAILABLE_STALE_HISTORY`; active enumeration is 83. Diagnostic
daily run `e9b43551-44f8-409c-a15b-ab339e1e5b12` explained its WARN entirely
as the newly confirmed SET gap and July 25-26 weekend probes from the explicit
observed-only Treasury-yield policy. After SET deactivation, bounded weekday
runs `f80a03f9-a4d3-49a1-9136-8fae7af05a13` and
`20ef2f87-5453-44bf-b687-b604a17a7262` each performed zero ingestion requests,
reconciled the same 21 bars unchanged across seven listings, had zero missing,
failed, retry, parse, correction, or calendar-policy counts, and stored PASS
reports `9daf78a4-fc28-4ecc-8dd0-3ae1c121c049` and
`c0988359-242d-4a1f-b265-1466e00ae79b`. This proves report persistence,
reconciliation, and idempotent rerun behavior with no unexplained warning.
Flyway validated all 37 migrations, the transactional Yahoo seed contract
passed, the focused remediation suite passed (21 tests), and the full
database-enabled package suite passed (561 tests).

Done: 2026-08-01 — added the thin
`dags/stonks/stonks_ohlcv_yahoo_daily_scrape.py` Airflow DAG around the
package-owned Yahoo daily runner. Local/development operation is deliberately
manual (`schedule=None`, `catchup=False`, `max_active_runs=1`); comments beside
the schedule record that production should use deployment-specific
America/New_York runs at 06:00, 10:00, 13:00, 18:00, and 23:00 only after the
Y8.15/V10.10 rollout gates. Manual JSON configuration can narrowly override
`effective_date`, `start_date`, `end_date`, and an exact uppercase `tickers`
array, while omitted values retain the configured package lookback and full
active universe. Airflow Compose now forwards the complete Yahoo OHLCV
environment contract to every runtime component. Ten focused DAG tests cover
manual metadata, the in-source production guidance, New York date handling,
default and overridden scope forwarding, invalid inputs, no-op success, and
failure propagation. The Compose model rendered successfully; the running
Airflow 3.2.1 processor discovered the DAG as paused and reported no import
errors; and the full database-enabled package suite passed (571 tests).

Done: 2026-08-01 — added a shared Empire-branded Yahoo PDF renderer for both
historical backfill and daily session-health models. Every successful Yahoo run
now renders and durably stores `reports/report.pdf` beside `report.json` using
the shared `stonks_ohlcv_provider_pdf_report` object kind and returns
`pdf_report_object_id` through the Core summary, CLI result, and Airflow task
payload. The bounded letter-format report covers executive status, run facts
and scope, per-phase acquisition/parser/persistence counts, provider-series
coverage, daily health and reconciliation evidence, and provider-native value
semantics; JSON remains authoritative for complete samples. Unit and
PostgreSQL vertical tests verify valid non-expiring PDF objects for both
workflows. Representative live PASS reports were rendered with Poppler and all
seven pages were visually inspected; a title-width collision and an orphaned
final table row found during review were corrected. The full database-enabled
package suite passed (572 tests), `poetry check`, public imports, compilation,
the changed-Python line-length scan, and `git diff --check` passed.

Done: 2026-08-01 — completed the Yahoo vertical release gate across seeded
listing selection, bounded acquisition, provider-date parsing, real-calendar
eligibility, missing-session planning, historical backfill, daily ingestion,
recent-session reconciliation, idempotent reruns, provider corrections,
secret-safe failures, durable JSON/PDF reports, cleanup-safe snapshot lineage,
and identical-symbol isolation across Yahoo, EODData, and Stooq. The focused
fixture and PostgreSQL gate passed 122 tests, and the full database-enabled
package suite passed 572 tests. The live database has all 93 reviewed Yahoo
listings, 83 active listings, no Yahoo listing missing a session policy or
`metadata.YahooTicker`, 108,561 Yahoo bars from 1965-01-04 through 2026-07-30,
and retained Yahoo source snapshots alongside existing EODData and historical
Stooq bars. Flyway validated all 37 migrations; `poetry check` and compilation
passed. The running Airflow 3.2.1 worker contains the current PDF-capable
package, the manual `stonks_ohlcv_yahoo_daily_scrape` DAG is discovered as
paused, and the DAG processor reports no import errors. No substantial defect
requiring a Y8.15.x remediation task was found.

## Phase 9: Calendar-Aware EODData Daily Scheduling

Goal: reuse the market-session eligibility capability proven by Yahoo so the
EODData provider requests each configured exchange only after its completed
session is expected to be available. Keep EODData's exchange-bulk source
contract and package-owned business logic intact.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| C9.1 | [x] | Define EODData exchange session policies | Map every configured EODData exchange to a supported market calendar, local session/time zone, and post-close availability delay using the shared Y8.2 contract. Document fallbacks and fail closed for an exchange without a valid policy rather than assuming U.S. Eastern time. | Y8.15 |
| C9.2 | [x] | Persist and resolve EODData policies | Add the minimal configuration or Flyway data required by the Y8.2 design and implement policy resolution for EODData's dynamically discovered provider listings. Tests cover all configured exchanges, holidays, early closes, DST, and unknown or inactive markets. | C9.1, Y8.5 |
| C9.3 | [x] | Add exchange-level eligibility and reconciliation planning | Before an exchange-bulk EODData request, determine whether its latest expected session is complete and eligible, whether rows are missing, and whether it falls in the configured recent-session reconciliation window. Skip ineligible/complete work while preserving bounded retry and correction behavior. Tests cover exchanges with different calendars on the same date and idempotent repeated runs. | C9.2, E6.10-E6.12 |
| C9.4 | [x] | Integrate calendar planning into the EODData runner and reports | Run only planned exchange work, preserve Core lifecycle and partial-exchange failure handling, and report expected-session coverage, ineligible exchanges, missing rows, retries, and corrected current rows. Existing CLI behavior remains compatible and secret safe. | C9.3, E6.7-E6.10 |
| C9.5 | [x] | Convert the EODData DAG to eligibility-driven multi-run operation | Keep the DAG thin and invoke it often enough to cover configured exchange closes; the package planner decides whether work is due. Initially retain a safe manual/disabled state until the rollout gate. DAG tests cover discovery, schedule configuration, no-op runs, and failure propagation. | C9.4, B1.5-B1.7 |
| C9.6 | [x] | Verify calendar-aware EODData end to end | Run multi-calendar fixtures through planning, acquisition, persistence, reconciliation, and reports. Prove there are no fabricated weekend/holiday rows, completed rows are skipped, missing rows retry, corrections converge, and Yahoo/EODData policies coexist without provider leakage. | C9.5, Y8.15 |

Done: 2026-08-01 — defined the complete NYSE/NASDAQ/AMEX policy mapping,
reviewed AMEX-to-XNYS fallback, 8-p.m. local eligibility, and fail-closed rules
in `docs/stonks/ohlcv-{market-session,eoddata-source}-contract.md` and aligned
`docs/todo/ohlcv-plan.md`; 68 focused tests passed, 3/3 exchange calendar
assertions passed across DST/holiday/early-close cases, and Poetry lock check,
compileall, public imports, and `git diff --check` passed.

Done: 2026-08-01 — added Flyway migration
`V2026.08.01.0004__stonks_add_eoddata_session_policies.sql`, package resolver
and first-discovery assignment in `empire_stonks_ohlcv/eoddata_policies.py`,
EODData import integration, and focused unit/PostgreSQL/SQL contract coverage;
all 13,672 live configured EODData listings resolved exact policies, the full
package suite passed 582 tests, Flyway validated 38 migrations, all three DB
contracts passed, and Poetry check/build, compileall, public imports, pip check,
88-column scan, and `git diff --check` passed.

Done: 2026-08-01 — added exchange eligibility, completeness, retry, and bounded
reconciliation planning in `empire_stonks_ohlcv/eoddata_planning.py`, wired its
configuration through package/env/Compose surfaces, and added unit/PostgreSQL
coverage plus source-contract docs; the full package suite passed 594 tests,
the focused PostgreSQL planner test passed, Flyway validated 38 migrations,
and Compose config, Poetry check/build, compileall, public imports, pip check,
88-column scan, and `git diff --check` passed.

Done: 2026-08-01 — integrated scoped calendar plans, no-op Core lifecycles,
retry/correction telemetry, and session coverage into `eoddata.py`,
`eoddata_import.py`, `eoddata_runner.py`, `reporting.py`, and the EODData PDF;
the full database-backed package suite passed 601 tests, 4 focused PostgreSQL
integration tests and 25 DAG/CLI/report tests passed, Flyway validated 38
migrations, and Compose config, Poetry check/build, compileall, workspace
imports, pip check, changed-file 88-column scan, and `git diff --check` passed.

Done: 2026-08-01 — kept
`dags/stonks/stonks_ohlcv_eoddata_daily_scrape.py` manual while exposing
planner telemetry and documenting the gated production schedule
`15 20-23 * * 1-5` America/New_York; updated DAG tests, README, and source
contract. Forty focused DAG/runner/CLI tests and the full database-backed suite
of 602 tests passed; Compose config, Poetry check, compileall, imports, pip
check, changed-file 88-column scan, and `git diff --check` passed. The rebuilt
Airflow 3.2.1 runtime discovered the external-trigger-only DAG with one active
run, current worker imports, and no DAG import errors.

Done: 2026-08-01 — added the PostgreSQL/Core multi-calendar gate in
`tests/test_eoddata_calendar_vertical_integration.py` and made reconciliation
recency clock-relative in `eoddata_planning.py`. The gate proved XNYS/NASDAQ
calendar use, holiday/weekend no-ops without fabricated rows, retry of a
missing AMEX session, NYSE correction then unchanged convergence, completed
historical-session skipping, JSON/PDF/report lineage, and isolated EODData and
Yahoo policies. Twelve focused EODData/Yahoo/isolation integrations and the
full database-backed suite of 604 tests passed; Flyway validated 38 migrations,
and Compose config, Poetry check/build, compileall, imports, pip check,
changed-file 88-column scan, and `git diff --check` passed. The rebuilt Airflow
3.2.1 worker imported the final package and the manual DAG remained
external-trigger-only with no import errors.

## Phase 10: Documentation, Verification, And Incremental Rollout

Goal: verify the package without scheduled Stooq acquisition and move from
fixture workflows to normal provider operation one proven path at a time.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| V10.1 | [x] | Complete package README | Document scope, provider-native semantics, `deploy/env/local.env` runtime loading, `os.environ` package boundary, secret handling, CLIs, raw retention, source snapshots, tables, calendar/session policies, enabled DAGs/reports, the manual Stooq backfill boundary, and deferred bridge/enrichment work. | C9.6, Y8.15, H7.8 |
| V10.2 | [x] | Add operator runbook | Document local secret/config setup, manual runs, each enabled provider DAG, historical Stooq file acquisition/import, Yahoo backfill, eligibility and reconciliation interpretation, report interpretation, raw-object inspection, reruns, and failure recovery without printing credentials. | V10.1 |
| V10.3 | [x] | Run formatting and full package tests | Configured formatting/linting and the full `empire-stonks-ohlcv` test suite pass from the repository root. | V10.2 |
| V10.4 | [x] | Run DB validation and regenerate docs | Repo-standard DB validation and Stonks schema documentation generation pass with no drift. | V10.2 |
| V10.5 | [x] | Verify package, CLI, and DAG imports | Package, all CLI modules, and all enabled provider DAGs import cleanly in their actual runtime environments. | V10.3-V10.4 |
| V10.6 | [x] | Verify raw-object cleanup | Expire and clean a test raw object and prove stored-object/membership rows are removed while source snapshot, provider listing, bars, session policy, and report remain queryable. | V10.4-V10.5 |
| V10.7 | [x] | Run combined fixture regression | Run EODData, operator-supplied historical Stooq, and Yahoo fixture paths through provider reports and prove reruns, calendar isolation, provider isolation, secret safety, and report scoping. | V10.3-V10.6 |
| V10.8 | [x] | Run and enable bounded EODData | Run bounded live EODData imports across representative calendar windows, inspect eligibility, lineage, bars, reconciliation, and reports, then enable its multi-run DAG only after results are healthy. Record the cadence and decision. | V10.7, C9.6, E6.13 |
| V10.9 | [x] | Run bounded historical Stooq import | Run the defined limited historical import and verify performance, counts, rerun behavior, cleanup, and report visibility before expanding scope. | V10.8, H7.8 |
| V10.10 | [x] | Close the Yahoo rollout gate | Audit the completed bounded live Yahoo backfill and daily runs for the reviewed seed universe, including calendar assignments, lineage, native semantics, bars, reports, and recent-session reconciliation. Record request volume, then explicitly select scheduled or manual-only operation and document the rollback decision. | V10.9, Y8.15 |
| V10.11 | [x] | Audit derived daily-bar consistency | Recompute expected `change` and `changepct` from each provider listing's nearest preceding stored bar and compare them with every `ohlcv_daily` row, covering first rows, zero predecessor closes, market-session gaps, corrections, and out-of-order imports. Report bounded discrepancy counts and samples by provider and market. If discrepancies exist, identify the cause and add a tested, bounded, idempotent repair command or workflow; if none exist, record the evidence and do not add a scheduled mutation task. | V10.10, H7.8 |

Done: 2026-08-02 — completed
`packages/empire-stonks-ohlcv/README.md` and this checklist with current scope,
data/lineage, runtime/secret, CLI, DAG/report, session-policy, Stooq-manual, and
deferred-work contracts. Focused package tests passed 130; package, four runners,
and five CLI imports passed; five wrapper help smokes, 8/8 README links, nine
balanced fenced blocks, Compose config, `poetry check --lock`, package
sdist/wheel build, `pip check`, compilation, Flyway validation of 38 migrations,
the OHLCV schema contract, and `git diff --check` passed.

Done: 2026-08-02 — added `docs/stonks/ohlcv-operator-runbook.md`, linked it
from `packages/empire-stonks-ohlcv/README.md`, and updated this checklist with
secret-safe setup, CLI/DAG operation, Stooq acquisition, Yahoo backfill,
eligibility/reconciliation, report/raw inspection, rerun, and recovery steps.
Focused tests passed 163; five wrapper help smokes, package/four-runner/five-CLI
imports, 18/18 documentation links, 32 balanced fenced blocks, four live
read-only SQL checks, Compose config, `poetry check --lock`, Flyway validation
of 38 migrations, and `git diff --check` passed.

Done: 2026-08-02 — wrapped five overlong lines in `queries.py`,
`reports/eoddata_daily_market_pdf.py`, and
`tests/test_daily_market_reporting.py`; no formatter/linter is configured
beyond `.editorconfig`. From the repository root, the full database-enabled
suite passed 604 tests in 73.78 seconds with no skips. UTF-8/final-newline and
88-column scans, `poetry check --lock`, compilation, `pip check`, focused
imports, and `git diff --check` passed.

Done: 2026-08-02 — regenerated the Stonks schema, full/grouped Mermaid, and
full/grouped pg-diagram documentation; added the missing
`security-reconciliation` guide inventory entry and removed four stale
`source-evidence` diagram artifacts. Flyway validated 38 migrations; all 11
groups produced 22 Mermaid and 44 pg-diagram files with zero missing/extra
outputs and no canonical content drift. All 24 PNG signatures, 24 SVG XML
documents, 24 Mermaid fences, OHLCV schema/relationship markers, and
`git diff --check` passed.

Done: 2026-08-02 — verified the live `empire-stonks-ohlcv` package, five CLI
modules, and the EODData/Yahoo DAG modules without code changes. All 50 package
modules imported in both Poetry and the installed Airflow 3.2.1 worker; 5/5
CLI modules and wrappers imported, and both manual-only DAGs imported with the
intended IDs, `schedule=None`, disabled catchup, and one active run. Airflow
discovered both DAGs with zero import errors; 57 focused CLI/DAG tests passed.

Done: 2026-08-02 — upgraded
`tests/test_cleanup_safe_lineage_integration.py` to expire, clean, and purge an
isolated Core-backed raw object while proving its stored-object and membership
rows disappear and its source snapshot, provider listing, daily bar, attached
session policy, and non-expiring report remain queryable. Ten focused OHLCV
lineage tests and 20 Core object-store tests passed; Flyway validated 38
migrations, fixture residue was 0/0/0/0, and dependency, compilation, import,
88-column, and `git diff --check` checks passed.

Done: 2026-08-02 — ran the existing EODData calendar, operator-supplied Stooq
history, Yahoo daily, three-provider isolation, provider-report, and
secret-safety fixtures together without code changes. The combined regression
passed 29 tests in 27.02 seconds, covering unchanged/corrected reruns,
EODData/Yahoo calendar isolation, exact three-provider identity isolation,
provider/market/listing report scopes, and secret-safe operational surfaces.
Fixture run/object/listing/membership residue was 0/0/0/0; Flyway validated 38
migrations, and lock, compilation, dependency, import, and `git diff --check`
checks passed.

Done: 2026-08-02 — audited successful live EODData windows from 2026-07-14
through 2026-07-27, then ran one bounded 2026-07-31 import
`db82bc85-e36c-4a73-8eb3-48230352cc0c`: all 3/3 markets were eligible and
complete, 12,617 bars were inserted, failures were 0, 6 raw objects had 6
lineage memberships, and 3 durable JSON/PDF reports were valid. A read-only
rerun plan found 0 missing sessions and selected all markets only for recent
reconciliation. Because the live run recovered 13 request retries,
`dags/stonks/stonks_ohlcv_eoddata_daily_scrape.py`, its focused test, the
package README, EODData source contract, and operator runbook enable the
reduced `15 20,23 * * 1-5` New York cadence with a documented pause/restore
rollback. Focused DAG tests passed 10; lock, compilation, dependency, Compose,
and diff checks passed; Flyway validated 38 migrations. The rebuilt Airflow
runtime reported 0 import errors, exact cron/timezone/catchup/overlap settings,
DAG version 2 unpaused, and next creation at 2026-08-04 00:15:00+00:00.

Done: 2026-08-02 — audited the existing large Stooq run
`64b2752a-6e6e-48d0-9ea6-c5ac8cfa2fcd` instead of replaying the unavailable
537,380,289-byte archive. It completed 9,562/9,562 files and 410/410 chunks in
4:41:30.9, accepting 20,475,736 of 20,475,807 rows at 1,212.23 rows/second,
inserting 9,561 listings and 20,475,731 bars, and reusing the H7.8 snapshot plus
five unchanged rehearsal bars. Database totals matched the WARN report across
Nasdaq 4,704/9,082,078, NYSE 4,537/10,558,875, and NYSE MKT 321/834,783
listings/bars; 71 invalid rows and 36 empty files caused 107 warnings, with 0
hard failures or failed chunks. The expired raw ZIP was physically cleaned;
the checksum snapshot, all 9,562 listings and 20,475,736 bars, and valid durable
82,952-byte JSON plus five-page PDF reports remain visible. Updated the Stooq
operator guide, source contract, and this checklist with the passed gate. Forty
focused non-integration tests passed in 0.90 seconds; Poetry lock, compilation,
public import, dependency, Flyway validation of 38 migrations, and diff checks
passed.

Done: 2026-08-02 — closed the Yahoo rollout gate by reusing the completed Y8
evidence and the operator's explicit manual-only decision; no provider request
was made. The reviewed release sequence used 126 logical request chunks: 93 for
the full-universe backfill, 8 for remediation, 11 for the diagnostic daily run,
and 7 for each of two unchanged reconciliation reruns. The live catalog has 93
reviewed listings, 83 active, 10 inactive, 0 missing session policies or Yahoo
tickers, 108,561 bars from 1965-01-04 through 2026-07-30, 166 snapshots and
lineage links, and 11 durable JSON reports. The final two daily runs each had
0 ingestion requests, 7 reconciliation requests, 21 unchanged bars, and 0
missing, failed, retry, correction, or calendar-policy counts. Updated the
Yahoo DAG and focused test, package README, Yahoo source contract, operator
runbook, and this checklist: `schedule=None` is the approved cadence, the DAG
stays paused between manual runs, and rollback from temporary scheduling is to
restore `schedule=None` and pause it. Focused DAG tests passed 10; Poetry lock,
compilation, public imports, dependency and Compose checks, Flyway validation
of 38 migrations, and diff checks passed. Airflow reported 0 import errors,
manual metadata, `is_paused=True`, and no next run.

Done: 2026-08-02 — added
`docs/stonks/ohlcv-derived-value-audit.md` and completed a null-safe read-only
audit of all 20,671,779 live bars across seven provider/market partitions.
Nearest-predecessor `change` and `changepct` plus row-local `typ`, `hl_range`,
and `oc_range` each had 0 discrepancies. The audit included 22,863 first rows,
3 zero-close predecessors, 4,675,493 non-consecutive-date transitions, and
37,105 post-insert-updated rows; no discrepancy samples or repair workflow were
needed. Six focused database-backed writer tests passed in 0.39 seconds,
covering reverse-order input, gap insertion, correction, successor
recalculation, and unchanged reruns. Poetry lock, compilation, public import,
dependency and diff checks passed; Flyway validated 38 migrations.
