
## Phase 0: Scope And Conventions

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| P0.1 | [x] | Lock identity lifecycle wording | Package docs or this plan clearly state that identity lifecycle starts with only `PROVISIONAL` and `CONFIRMED`; descriptive enrichment is separate. | Current plan |

Done: 2026-07-01. Updated `packages/empire-stonks-securities/README.md` and `docs/todo/stonks-securities-provisional-status.md` so lifecycle wording is locked to `PROVISIONAL` -> `CONFIRMED` only, with descriptive enrichment documented as separate evidence/classification data. Verification: `rg -n "ENRICHED|PROVISIONAL|CONFIRMED|identity lifecycle" docs/todo/stonks-securities-provisional-status.md packages/empire-stonks-securities/README.md docs/todo/reconciliation-plan.md`.
| P0.2 | [x] | Name the consolidated SEC refresh DAG | Decide the final DAG id for the consolidated daily SEC refresh, the legacy DAG retirement approach, and whether old DAG ids remain as temporary compatibility wrappers. | P0.1 |

Done: 2026-07-01. Chose `stonks_securities_sec_daily_scrape` as the consolidated daily SEC scrape DAG id, with the future DAG file expected at `dags/stonks/stonks_securities_sec_daily_scrape.py`. In Empire DAG naming, `scrape` means the scheduled internet-facing workflow that pulls provider data and processes it through the package-owned daily chain; it can contain subtasks for source collection, verification, observations, issuer/security/listing upserts, validation, conflict reporting, and daily summary reporting. Legacy per-stage DAG ids should remain unchanged only while D1.3-D1.7 introduce and verify the consolidated DAG. Do not add compatibility wrapper DAGs for old stage ids; stage-level wrappers would make partial-entry semantics ambiguous and could duplicate downstream work. D1.8 should retire the old trigger-chain DAG files and clean up Airflow metadata/operator docs after the consolidated DAG is proven. Verification: `rg -n "P0\\.2|stonks_securities_sec_daily_scrape|compatibility wrapper|D1\\.8" docs/todo/reconciliation-plan.md`.
| P0.3 | [x] | Name reconciliation outputs | Decide report name, object kind, logical name, object-store path, and CLI command naming for reconciliation dry-run/apply outputs. | P0.1 |

Done: 2026-07-01. Chose the reconciliation report and CLI naming contract in the `Reconciliation Output Naming` section below. Dry-run and apply produce distinct JSON report artifacts under the existing run-report object-store layout, and the CLI entrypoint is `stonks-securities-reconcile` with dry-run as the default and `--apply` as the explicit mutating mode. Verification: `rg -n "Reconciliation Output Naming|stonks_securities_reconciliation_dry_run|stonks_securities_reconciliation_apply|stonks-securities-reconcile|P0\\.3" docs/todo/reconciliation-plan.md docs/todo/stonks-securities-provisional-status.md`.

## Reconciliation Output Naming

Use the existing stonks securities run-report convention for reconciliation
artifacts. Reconciliation reports are JSON first; PDF rendering can be added
later as a sibling artifact only after the JSON contract is stable.

Dry-run output:

- Report name: `stonks_securities_reconciliation_dry_run`
- Object kind: `stonks_securities_reconciliation_dry_run_report`
- Logical name: `stonks_securities_reconciliation_dry_run`
- Object-store key: `stonks/securities/runs/YYYY/MM/DD/run-reports/reconciliation/dry-run`
- Filename: `stonks_securities_reconciliation_dry_run_YYYYMMDDTHHMMSSZ.json`

Apply output:

- Report name: `stonks_securities_reconciliation_apply`
- Object kind: `stonks_securities_reconciliation_apply_report`
- Logical name: `stonks_securities_reconciliation_apply`
- Object-store key: `stonks/securities/runs/YYYY/MM/DD/run-reports/reconciliation/apply`
- Filename: `stonks_securities_reconciliation_apply_YYYYMMDDTHHMMSSZ.json`

The report payload should include a top-level `mode` field with either
`dry_run` or `apply`, even though the object kinds are already mode-specific.
That keeps operator output self-describing when a report is copied outside the
object store.

CLI naming:

- Entrypoint: `stonks-securities-reconcile`
- Default mode: dry-run
- Apply mode: `stonks-securities-reconcile --apply`
- Expected context flags: `--source-run-id`, `--logical-date`, `--output`, and
  `--write-object-store`, matching the existing package pattern of reusable
  logic with a thin CLI wrapper.
  
## Phase 1: Consolidate The Existing SEC Daily Chain

Goal: replace the current many-DAG trigger chain with one daily SEC refresh DAG
that contains internal tasks or task groups for the existing stages. This is
orchestration cleanup, not a rewrite of package business logic.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| D1.1 | [x] | Inventory current DAG chain behavior | Document the existing scrape -> verify -> observations -> issuers -> securities -> listings -> validation -> conflicts -> summary order, conf payload, run id handoff, report outputs, and task ids that should survive. | P0.2 |
| D1.2 | [x] | Add a package-level daily refresh orchestrator shape | Add or identify package functions that can run each stage with explicit `source_run_id`/run context, without depending on cross-DAG conf handoff. | D1.1 |
| D1.3 | [x] | Create consolidated DAG skeleton | Add the consolidated SEC refresh DAG with task groups or tasks in the intended order, initially calling the existing stage functions without deleting legacy DAGs. DAG import smoke test passes. | D1.2 |
| D1.4 | [x] | Wire scrape and verify stages | Consolidated DAG can collect SEC sources and run verification with the same run id and report path behavior as the old chain. Targeted tests pass. | D1.3 |
| D1.5 | [x] | Wire observation and entity stages | Consolidated DAG can run observations, issuers, securities, and listings in order with the same idempotent behavior as the old chain. Targeted tests pass. | D1.4 |
| D1.6 | [x] | Wire validation, conflicts, and summary stages | Consolidated DAG can write validation, conflict, and daily summary reports with the same durable run-report behavior as the old chain. Targeted tests pass. | D1.5 |
| D1.7 | [x] | Add consolidated DAG regression tests | Add DAG import, task-order, and run-context smoke tests for the consolidated DAG. Keep package-local tests runnable from the repo root. | D1.6 |
| D1.8 | [x] | Retire old trigger-chain DAGs | Remove or disable the old per-stage trigger DAGs after the consolidated DAG is verified. Update docs and tests so there is one normal SEC daily refresh entrypoint. | D1.7 |

Done: 2026-07-02. Added the `D1.1 Current SEC Daily Chain Inventory` section below with current DAG order, trigger conf payloads, run-id/report handoff, durable outputs, and task ids to preserve. Verification: `rg -n "D1\\.1|Current SEC Daily Chain Inventory|trigger_stonks_securities_daily_verify|stonks_securities_daily_summary" docs/todo/reconciliation-plan.md`.

Done: 2026-07-02. Added package-owned daily refresh stage wrappers in `empire_stonks_securities.daily_refresh`, exported explicit `DailyRefreshRunContext`/stage result helpers, and covered source-run context plus report object-id handoff in `tests/test_daily_refresh.py`. The future consolidated DAG can now call package functions directly instead of relying on cross-DAG `dag_run.conf` templating. Verification: `packages/empire-stonks-securities/.venv/bin/python -m pytest packages/empire-stonks-securities/tests` (`159 passed`).

Done: 2026-07-02. Added the consolidated SEC refresh DAG skeleton at `dags/stonks/stonks_securities_sec_daily_scrape.py`, preserving the existing stage task ids/order while calling package-owned daily refresh stage functions and leaving legacy DAGs in place. Verification: rebuilt/recreated the Airflow image, then ran `docker compose --env-file deploy/env/local.env -f deploy/compose/empire.yml exec airflow-api python -c "import sys; sys.path.insert(0, '/opt/airflow/dags'); import stonks.stonks_securities_sec_daily_scrape as dag_module; print(dag_module.stonks_securities_sec_daily_scrape_dag.dag_id)"` (`stonks_securities_sec_daily_scrape`).

Done: 2026-07-02. Added focused daily-refresh tests proving the consolidated scrape stage preserves the legacy daily scrape run contract and the verify stage uses the same source run id while writing the existing verify run-report artifact. Files changed: `packages/empire-stonks-securities/tests/test_daily_refresh.py`, `docs/todo/reconciliation-plan.md`. Verification: `packages/empire-stonks-securities/.venv/bin/python -m pytest packages/empire-stonks-securities/tests/test_daily_refresh.py` (`5 passed`).

Done: 2026-07-02. Added focused daily-refresh tests proving the consolidated observation, issuer, security, and listing stage wrappers run in order with the same explicit source run id and package-owned idempotent upsert functions as the old chain. Files changed: `packages/empire-stonks-securities/tests/test_daily_refresh.py`, `docs/todo/reconciliation-plan.md`. Verification: `packages/empire-stonks-securities/.venv/bin/python -m pytest packages/empire-stonks-securities/tests/test_daily_refresh.py` (`6 passed`).

Done: 2026-07-03. Added focused daily-refresh tests proving the consolidated validation, conflict, and daily summary stage wrappers write the existing durable run-report artifacts, preserve source-run context, and pass verify/validation/conflict report object ids into the summary stage. Files changed: `packages/empire-stonks-securities/tests/test_daily_refresh.py`, `docs/todo/reconciliation-plan.md`. Verification: `packages/empire-stonks-securities/.venv/bin/python -m pytest packages/empire-stonks-securities/tests/test_daily_refresh.py` (`7 passed`).

Done: 2026-07-03. Added package-local consolidated DAG regression tests covering import/config, preserved stage order, TaskFlow handoff shape, and Airflow run-context adaptation. Files changed: `packages/empire-stonks-securities/tests/test_sec_daily_scrape_dag.py`, `docs/todo/reconciliation-plan.md`. Verification: `packages/empire-stonks-securities/.venv/bin/python -m pytest packages/empire-stonks-securities/tests` (`165 passed`).

Done: 2026-07-03. Retired the old stonks securities per-stage trigger-chain DAG files and removed the now-unused trigger-conf helper/test surface, leaving `dags/stonks/stonks_securities_sec_daily_scrape.py` as the only normal SEC daily refresh DAG entrypoint. Updated `packages/empire-stonks-securities/README.md` and added a regression assertion that only the consolidated stonks securities DAG file exists. Verification: `packages/empire-stonks-securities/.venv/bin/python -m pytest packages/empire-stonks-securities/tests` (`154 passed`).

## D1.1 Current SEC Daily Chain Inventory

This inventory captures the current multi-DAG SEC daily chain before it is
collapsed into `stonks_securities_sec_daily_scrape`.

### Current Order

The existing stage order is:

1. `stonks_securities_daily_scrape`
2. `stonks_securities_daily_verify`
3. `stonks_securities_daily_observations`
4. `stonks_securities_daily_issuers`
5. `stonks_securities_daily_securities`
6. `stonks_securities_daily_listings`
7. `stonks_securities_daily_validation`
8. `stonks_securities_daily_conflicts`
9. `stonks_securities_daily_refresh_summary`

All existing DAGs are unscheduled manual DAGs with `catchup=False` and
`max_active_runs=1`. The consolidated DAG should keep that conservative
single-active-run behavior unless scheduling is changed deliberately later.

### Stage Behavior And Task IDs

Task ids that should survive in the consolidated DAG, either as exact task ids
or as the terminal names inside task groups:

| Stage | Current DAG id | Current task id | Package function or behavior | Downstream trigger task |
|-------|----------------|-----------------|------------------------------|-------------------------|
| Scrape | `stonks_securities_daily_scrape` | `collect_sec_sources` | Loads config by logical name, creates an Empire run through `RunService`, downloads `DEFAULT_DAILY_SOURCE_KEYS`, and writes SEC source files plus metadata to object storage. | `trigger_stonks_securities_daily_verify` |
| Verify | `stonks_securities_daily_verify` | `verify_sec_sources` | Runs `verify_stonks_securities_daily_sources`, builds `stonks_securities_verify`, and writes the verify JSON report. | `trigger_stonks_securities_daily_observations` |
| Observations | `stonks_securities_daily_observations` | `write_sec_observations` | Runs `run_stonks_securities_daily_observation_writer` for the source run. | `trigger_stonks_securities_daily_issuers` |
| Issuers | `stonks_securities_daily_issuers` | `upsert_sec_issuers` | Runs `upsert_sec_issuers_from_provider_observations` for the source run. | `trigger_stonks_securities_daily_securities` |
| Securities | `stonks_securities_daily_securities` | `upsert_sec_securities` | Runs `upsert_sec_securities_from_provider_observations` for the source run. | `trigger_stonks_securities_daily_listings` |
| Listings | `stonks_securities_daily_listings` | `upsert_sec_listings` | Runs `upsert_sec_listings_from_provider_observations` for the source run. | `trigger_stonks_securities_daily_validation` |
| Validation | `stonks_securities_daily_validation` | `generate_validation_report` | Runs `generate_phase_2a_validation_report` and writes the validation JSON report. | `trigger_stonks_securities_daily_conflicts` |
| Conflicts | `stonks_securities_daily_conflicts` | `generate_conflict_report` | Runs `generate_phase_2a_conflict_report` and writes the conflict JSON report. | `trigger_stonks_securities_daily_refresh_summary` |
| Summary | `stonks_securities_daily_refresh_summary` | `generate_daily_refresh_summary` | Runs `generate_daily_refresh_summary_report`, writes the summary JSON report, and renders/writes the summary PDF report. | None |

The consolidated DAG should remove the trigger tasks but preserve the semantic
handoff points above so logs, tests, and future operator docs remain legible.

### Conf Payload And Handoff Contract

The current chain passes state through `dag_run.conf` using
`empire_stonks_securities.dag_conf`.

Required key:

- `input_run_id`: the Empire run id created by `collect_sec_sources`.

Optional accumulated report keys:

- `verify_report_object_id`
- `validation_report_object_id`
- `conflict_report_object_id`

Current trigger behavior:

- Scrape to verify uses `scrape_to_verify_conf()`, which sets `input_run_id`
  from `collect_sec_sources` XCom field `run_id`.
- Verify to observations uses `verify_to_observations_conf()`, which carries
  `input_run_id` and sets `verify_report_object_id` from `verify_sec_sources`
  XCom field `object_id`.
- Observations, issuers, securities, and listings use `pass_through_conf()`,
  carrying `input_run_id` and the optional `verify_report_object_id`.
- Validation to conflicts uses `validation_to_conflicts_conf()`, carrying
  `input_run_id`, `verify_report_object_id`, and the validation report object
  id from `generate_validation_report`.
- Conflicts to summary uses `conflicts_to_summary_conf()`, carrying
  `input_run_id`, `verify_report_object_id`, `validation_report_object_id`,
  and the conflict report object id from `generate_conflict_report`.

The consolidated DAG should replace cross-DAG conf templating with explicit
in-DAG return values or a package-level daily refresh context object. It should
continue to treat the scrape run id as the source run id for all downstream
reads, writes, reports, and `RunService.get_run_context(input_run_id)` calls.

### Durable Outputs To Preserve

Scrape output:

- Empire run: domain `stonks`, job name `stonks_securities_daily_scrape`,
  subject key `sec_daily_sources`.
- Source keys: `sec_company_tickers_exchange` and `sec_company_tickers`.
- Object kinds: `sec_source_file` and `sec_source_file_metadata`.
- Object scope: run-scoped when written with the scrape run context.

Run-report outputs use the shared object-store layout:

```text
stonks/securities/runs/YYYY/MM/DD/run-reports/<report_type>
```

Current report contracts:

| Stage | Report name / logical name | Object kind | Report type | Filename pattern |
|-------|----------------------------|-------------|-------------|------------------|
| Verify | `stonks_securities_verify` | `stonks_securities_verify_report` | `verify` | `stonks_securities_verify_YYYYMMDDTHHMMSSZ.json` |
| Validation | `stonks_securities_validation` | `stonks_securities_validation_report` | `validation` | `stonks_securities_validation_YYYYMMDDTHHMMSSZ.json` |
| Conflicts | `stonks_securities_conflicts` | `stonks_securities_conflict_report` | `conflicts` | `stonks_securities_conflicts_YYYYMMDDTHHMMSSZ.json` |
| Summary JSON | `stonks_securities_daily_summary` | `stonks_securities_daily_summary_report` | `summary` | `stonks_securities_daily_summary_YYYYMMDDTHHMMSSZ.json` |
| Summary PDF | `stonks_securities_daily_summary_pdf` | `stonks_securities_daily_summary_pdf` | `summary` | `stonks_securities_daily_summary_YYYYMMDDTHHMMSSZ.pdf` |

The summary stage should continue to accept linked verify, validation, and
conflict report object ids when available. If an object id is absent, the
existing summary report logic can fall back to latest matching report objects,
but the consolidated DAG should pass the explicit object ids produced in the
same run.

### Consolidation Notes For D1.2-D1.7

- Keep Airflow thin: orchestration should call package functions and should not
  embed SEC business rules in the DAG file.
- Prefer one source-run context created by the scrape stage. Downstream stages
  should receive `source_run_id` explicitly rather than reading cross-DAG
  `dag_run.conf`.
- Preserve reporting `run_context` fields: `dag_id`, Airflow `run_id`,
  `source_run_id`, `logical_date`, and `environment="airflow"`.
- Preserve current stage order. Validation and conflict reports are inputs to
  the summary report, not replacements for it.
- D1.8 retired the legacy per-stage DAG ids after the consolidated DAG
  regression tests passed. The normal SEC daily refresh entrypoint is now
  `stonks_securities_sec_daily_scrape`.
