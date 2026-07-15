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


