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
