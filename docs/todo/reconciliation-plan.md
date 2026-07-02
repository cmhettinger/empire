# Security Identity Reconciliation Action Plan

This document tracks the implementation roadmap for promoting provisional
security identities into stronger, long-lived security-master records.

The original provisional-status note described reconciliation as separate from
the daily SEC ingestion pipeline. That remains correct operationally: the daily
SEC DAG should keep collecting observations and upserting bootstrap entities,
while promotion, merge, and classification decisions should run as their own
explicit workflow.

That does not mean the first step is a new package. Most of the near-term
functionality belongs in `empire-stonks-securities` because that package already
owns SEC source observations, provider evidence, issuer/security/listing upserts,
validation, conflict reporting, and the security-master tables it writes. A new
`empire-stonks-reconciliation` package should only be introduced after the
single-provider SEC reconciliation contracts are stable and there is a real
cross-provider orchestration problem to solve.

## Package Boundary

Keep in `empire-stonks-securities`:

- SEC-derived evidence extraction and normalization.
- Security lifecycle columns and audit tables in the `stonks` schema.
- Deterministic promotion from SEC-backed provisional securities.
- Duplicate candidate detection for SEC-created provisional records.
- Classification upgrades that can be justified from SEC-owned evidence.
- Reconciliation JSON/PDF reports for SEC security-master health.
- Thin CLI and Airflow wrappers for SEC reconciliation runs.

Defer to a future `empire-stonks-reconciliation` package:

- Cross-provider policy that combines SEC evidence with future providers.
- Provider consensus scoring across SEC, FIGI, CUSIP/ISIN, market-data vendors,
  filings-derived identifiers, and other enrichment sources.
- Global merge/split orchestration when candidates span provider-owned evidence
  modules.
- Manual review workflow shared across providers or domains.

The maintainable path is to build reusable reconciliation primitives in
`empire-stonks-securities` first, with names and data contracts that can later be
called by a cross-provider package rather than moved wholesale.

Identity lifecycle should stay narrow. Start with `PROVISIONAL` and `CONFIRMED`;
do not use `ENRICHED` as a lifecycle state. Descriptive enrichment such as
sector, industry, category, asset class, or other supplemental attributes should
be tracked through separate classification/enrichment tables or evidence, not
through `security.identity_status`.

Airflow should expose pipeline-level workflows, not one DAG per internal
function. The existing SEC daily chain remains responsible for source
collection, verification, observations, and canonical issuer/security/listing
upserts, but the current many-DAG chain should be consolidated into one daily
SEC refresh DAG with internal tasks or task groups. The new reconciliation DAG
should then run after that daily refresh DAG or manually, calling package-owned
sequencing for evidence collection, confidence evaluation, dry-run reporting,
optional safe promotion, and final report writing. Dry-run should be the default
mode until the apply workflow is proven.

---

## How To Use This Checklist

Each task is intended to fit in one focused work session. A task is complete
only when the code/doc changes are made, the listed verification passes, and the
status checkbox is updated.

Default working pattern: use one Codex chat per task ID, such as `P0.1`,
`D1.1`, or `S2.1`. Start the chat by naming the task ID and asking Codex to
read this document, complete that task, run the listed verification, and update
the checkbox plus `Done:` note. Adjacent tiny tasks may be combined when they
are naturally coupled, but large tasks should be split in this document rather
than stretched across a long chat. New chats should start by reading the prior
task's `Done:` note and the current live repo state.

Status format:

- `[ ]` Not started
- `[~]` In progress
- `[x]` Complete

When completing a task, add a short `Done:` note under the task with the date,
the key files changed, and the verification command/result. Keep the notes terse
so this remains useful as a working reference.

---

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
| D1.2 | [ ] | Add a package-level daily refresh orchestrator shape | Add or identify package functions that can run each stage with explicit `source_run_id`/run context, without depending on cross-DAG conf handoff. | D1.1 |
| D1.3 | [ ] | Create consolidated DAG skeleton | Add the consolidated SEC refresh DAG with task groups or tasks in the intended order, initially calling the existing stage functions without deleting legacy DAGs. DAG import smoke test passes. | D1.2 |
| D1.4 | [ ] | Wire scrape and verify stages | Consolidated DAG can collect SEC sources and run verification with the same run id and report path behavior as the old chain. Targeted tests pass. | D1.3 |
| D1.5 | [ ] | Wire observation and entity stages | Consolidated DAG can run observations, issuers, securities, and listings in order with the same idempotent behavior as the old chain. Targeted tests pass. | D1.4 |
| D1.6 | [ ] | Wire validation, conflicts, and summary stages | Consolidated DAG can write validation, conflict, and daily summary reports with the same durable run-report behavior as the old chain. Targeted tests pass. | D1.5 |
| D1.7 | [ ] | Add consolidated DAG regression tests | Add DAG import, task-order, and run-context smoke tests for the consolidated DAG. Keep package-local tests runnable from the repo root. | D1.6 |
| D1.8 | [ ] | Retire old trigger-chain DAGs | Remove or disable the old per-stage trigger DAGs after the consolidated DAG is verified. Update docs and tests so there is one normal SEC daily refresh entrypoint. | D1.7 |

Done: 2026-07-02. Added the `D1.1 Current SEC Daily Chain Inventory` section below with current DAG order, trigger conf payloads, run-id/report handoff, durable outputs, and task ids to preserve. Verification: `rg -n "D1\\.1|Current SEC Daily Chain Inventory|trigger_stonks_securities_daily_verify|stonks_securities_daily_summary" docs/todo/reconciliation-plan.md`.

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
- Keep the legacy DAG ids unchanged until D1.8 retires them after consolidated
  DAG regression tests pass.

## Phase 2: Lifecycle And Audit Schema

Goal: add the minimal database contract needed to distinguish provisional from
confirmed identities and record explainable reconciliation decisions.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| S2.1 | [ ] | Design lifecycle migration | Draft the Flyway migration shape for `stonks.security.identity_status`, default/backfill behavior, constraints, indexes, and any minimal promotion metadata. | P0.1 |
| S2.2 | [ ] | Implement lifecycle migration | Add the migration and validate it with `make db-validate` or the repo-standard DB validation target. | S2.1 |
| S2.3 | [ ] | Update package queries/models for lifecycle | Update security query/upsert/report code so existing rows are treated as `PROVISIONAL` and no existing ingestion path silently confirms identities. Package tests pass. | S2.2 |
| S2.4 | [ ] | Design reconciliation audit tables | Draft immutable audit/evaluation table shapes for decision type, rule version, confidence, explanation, run id, previous/new state, and linked evidence/security/listing ids. | S2.2 |
| S2.5 | [ ] | Implement reconciliation audit migration | Add audit/evaluation tables and validate schema. Include indexes needed for security-level history and run-level reporting. | S2.4 |
| S2.6 | [ ] | Add audit write helpers | Add small package helpers for inserting evaluation and applied-decision rows. Unit tests cover immutability expectations and required fields. | S2.5 |

## Phase 3: Evidence Collection

Goal: create deterministic, stored evidence summaries that can later drive
confidence and promotion decisions.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| E3.1 | [ ] | Define first evidence types | Document the first evidence types, such as issuer match, stable ticker/exchange observation, source snapshot continuity, and SEC series/class evidence placeholder. | S2.6 |
| E3.2 | [ ] | Design evidence storage changes | Decide whether existing `provider_evidence` is enough or whether a new security-level reconciliation evidence table is needed. Document the chosen shape before implementing. | E3.1 |
| E3.3 | [ ] | Implement evidence storage migration | Add the selected storage changes and validate schema. Preserve `provider_observation` and `provider_evidence` as the source trail. | E3.2 |
| E3.4 | [ ] | Build evidence collector query layer | Add package queries that select provisional securities and their supporting SEC observations, source snapshots, issuer identifiers, security identifiers, and listings. Unit tests cover ordering and idempotent selection. | E3.3 |
| E3.5 | [ ] | Build evidence collector writer | Write derived evidence idempotently with stable keys or conflict handling. Unit tests prove reruns do not duplicate evidence. | E3.4 |
| E3.6 | [ ] | Add evidence collection summary | Return counts for scanned securities, evidence inserted/skipped, missing evidence, and warnings. Summary is JSON-ready for reports and CLI output. | E3.5 |

## Phase 4: Confidence And Promotion Dry Run

Goal: evaluate identities without mutating canonical state. Dry-run reporting is
the safety rail before any automatic promotion exists.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| C4.1 | [ ] | Define first confidence rules | Document explicit versioned rules for what can make a security promotion candidate and what blocks promotion. Avoid a generic rules engine. | E3.6 |
| C4.2 | [ ] | Implement confidence evaluator | Add package code that turns stored evidence into confidence results with rule id, score/level, explanation, evidence ids, and refusal reasons. Unit tests cover deterministic output. | C4.1 |
| C4.3 | [ ] | Implement promotion candidate evaluator | Add dry-run evaluation for provisional securities without mutating identity state. Unit tests cover candidate and blocked cases. | C4.2 |
| C4.4 | [ ] | Write evaluation audit rows in dry-run mode | Store evaluation results with run context while leaving `security.identity_status` unchanged. Tests prove dry-run does not promote. | C4.3 |
| C4.5 | [ ] | Add dry-run JSON report builder | Produce a report payload with lifecycle counts, candidates, blocked securities, missing evidence classes, duplicate candidates, warnings, and failures. | C4.4 |
| C4.6 | [ ] | Store dry-run report artifact | Persist the dry-run JSON report under the agreed object-store run-report path with the agreed object kind/logical name. Tests cover report path and metadata. | C4.5 |

## Phase 5: Safe Apply Mode

Goal: allow explicit, high-confidence promotion from `PROVISIONAL` to
`CONFIRMED` while preserving identity and audit history.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| A5.1 | [ ] | Define apply-mode guardrails | Document which candidates can be auto-promoted, which must remain blocked, and which conditions require manual review or future provider evidence. | C4.6 |
| A5.2 | [ ] | Implement one-way promotion helper | Add package helper that changes `identity_status` from `PROVISIONAL` to `CONFIRMED`, writes audit rows, and rejects downgrades or unsupported transitions. Unit tests pass. | A5.1 |
| A5.3 | [ ] | Implement apply-mode runner | Add explicit apply mode that promotes only safe candidates and returns applied/skipped/blocked counts. Dry-run remains the default path. | A5.2 |
| A5.4 | [ ] | Add apply-mode report content | Include applied promotions, skipped candidates, blockers, and audit references in reconciliation reports. | A5.3 |
| A5.5 | [ ] | Prove idempotent apply behavior | Tests prove applying the same safe candidate twice does not duplicate audit/evidence rows or change confirmed identities incorrectly. | A5.4 |

## Phase 6: Duplicate Candidate Detection

Goal: surface possible duplicate provisional identities as recommendations, not
automatic merges.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| M6.1 | [ ] | Define duplicate candidate rules | Document first duplicate candidate rules for same issuer/ticker, ticker/exchange continuity, source-snapshot evidence, and known blockers. | C4.6 |
| M6.2 | [ ] | Implement duplicate candidate queries | Add package query logic for duplicate provisional candidates. Unit tests cover expected candidate grouping. | M6.1 |
| M6.3 | [ ] | Add duplicate candidates to dry-run report | Reconciliation dry-run report includes candidate groups, supporting evidence, and why automatic merge is not performed. | M6.2 |
| M6.4 | [ ] | Add validation/conflict integration | Existing validation/conflict or daily-health reports include duplicate candidate counts without changing canonical identities. | M6.3 |

## Phase 7: CLI, Reconciliation DAG, And Operator Docs

Goal: expose the package workflow through a thin CLI and one Airflow
reconciliation DAG.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| O7.1 | [ ] | Add reconcile CLI skeleton | Add `stonks-securities-reconcile` with dry-run default, apply flag, source-run/report context options, and JSON output. CLI imports and help text work. | C4.6 |
| O7.2 | [ ] | Wire CLI dry-run mode | CLI runs evidence collection, confidence evaluation, dry-run auditing, and report writing. Targeted CLI tests pass. | O7.1 |
| O7.3 | [ ] | Wire CLI apply mode | CLI apply mode requires an explicit flag and runs safe promotions plus apply report content. Targeted CLI tests pass. | A5.5 |
| O7.4 | [ ] | Add reconciliation DAG skeleton | Add one thin reconciliation DAG that can run after the consolidated SEC refresh DAG or manually. DAG import smoke test passes. | D1.8, O7.2 |
| O7.5 | [ ] | Wire reconciliation DAG run context | DAG passes source run/report context explicitly and calls package-owned sequencing. Tests cover context handoff. | O7.4 |
| O7.6 | [ ] | Update operator docs | Document consolidated SEC refresh, reconciliation dry-run/apply, report interpretation, and exact local verification/rebuild commands. | O7.5 |

## Phase 8: Final Verification And Cleanup

Goal: make the implementation reliable enough to become the normal workflow.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| V8.1 | [ ] | Run full package test suite | `packages/empire-stonks-securities/.venv/bin/python -m pytest packages/empire-stonks-securities/tests` passes from the repo root. | O7.6 |
| V8.2 | [ ] | Run DB validation | Repo-standard DB validation passes after all migrations. | O7.6 |
| V8.3 | [ ] | Verify Airflow imports | Consolidated SEC refresh DAG and reconciliation DAG import cleanly in the Airflow environment or existing DAG smoke-test harness. | O7.6 |
| V8.4 | [ ] | Verify local end-to-end dry run | Local/dev run proves SEC refresh then reconciliation dry-run produces expected reports without applying promotions. | V8.1, V8.2, V8.3 |
| V8.5 | [ ] | Decide apply-mode rollout | Decide whether apply mode remains manual-only, becomes scheduled after dry-run, or needs more evidence/provider work before use. Record the decision here. | V8.4 |

---

## Future Cross-Provider Package Gate

Do not start this package until the SEC-owned reconciliation workflow above has
stable schema contracts, CLI/report interfaces, and at least one additional
provider or identifier source needs to participate.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| X9.1 | [ ] | Confirm package need | Proceed only when reconciliation must combine SEC evidence with at least one non-SEC provider or shared manual-review workflow. Record the specific provider boundary that justifies a new package. | V8.5 |
| X9.2 | [ ] | Create cross-provider package | Create `empire-stonks-reconciliation` with standard Poetry/src layout, environment-driven config, thin CLI, tests, and no direct Airflow business logic. Depend on provider packages instead of duplicating their internals. | X9.1 |
| X9.3 | [ ] | Define provider evidence adapters | Expose small adapter interfaces that call provider-owned packages for evidence summaries, candidate decisions, and report payloads. Keep provider parsing and provider-specific SQL in provider packages. | X9.2 |
| X9.4 | [ ] | Add cross-provider confidence policy | Combine SEC lifecycle evidence with future CUSIP/ISIN/FIGI/vendor evidence using explicit, versioned policy. Store explanations and source evidence links for every score. | X9.3 plus future provider package |
| X9.5 | [ ] | Add cross-provider merge orchestration | Coordinate duplicate detection and merge recommendations across provider evidence. Start with recommendations and audit records; require a separate apply workflow for destructive identity changes. | X9.4 |
| X9.6 | [ ] | Add shared manual review queue | Build a provider-agnostic review workflow for ambiguous identities, conflicting identifiers, and low-confidence merges. Manual review augments automated decisions and writes auditable outcomes. | X9.5 |
| X9.7 | [ ] | Add global reconciliation reports | Produce portfolio-wide reconciliation reports and metrics across providers: lifecycle distribution, promotion throughput, conflicts, merge candidates, manual-review backlog, and stale evidence. | X9.4-X9.6 |
| X9.8 | [ ] | Add cross-provider orchestration DAG | Add a thin DAG that invokes the cross-provider package after provider-specific refreshes complete. Keep provider-specific collection and normalization in their existing packages. | X9.7 |

---

## Expected End State After Phases 0-8

When phases 0-8 are complete, `empire-stonks-securities` should be a stable SEC
security-master package with two normal workflows:

- One consolidated SEC daily refresh DAG that collects SEC source files, verifies
  them, writes observations, updates canonical issuer/security/listing tables,
  runs validation/conflict checks, and writes the daily summary.
- One reconciliation DAG/CLI workflow that evaluates provisional security
  identities, writes explainable dry-run reports, and can explicitly apply only
  high-confidence `PROVISIONAL` -> `CONFIRMED` promotions.

At that point, the package should be ready to begin backfill design and build,
but not necessarily ready to run broad historical backfill directly into
canonical identity tables without a backfill-specific design. The important
difference is that backfill work can be designed against stable lifecycle,
evidence, audit, report, and reconciliation contracts rather than inventing
those contracts during the backfill.

The database should contain, at a high level:

- Authoritative SEC source snapshot identity: which downloaded SEC source files
  represent the same provider content, independent of a single Airflow run or
  object-store retention cycle.
- Authoritative provider observations: parsed SEC rows with source lineage,
  source snapshot links, raw keys, observation timestamps, and summary payloads.
- Canonical issuers derived from SEC evidence, including CIK-backed issuer
  identity and issuer identifiers where SEC evidence supports them.
- Canonical listings for current SEC-observed ticker/exchange relationships,
  including listing symbol history and active-listing guards.
- Canonical securities that are explicitly lifecycle-scoped: newly bootstrapped
  SEC securities remain `PROVISIONAL`; only deterministic, auditable
  reconciliation can mark a security `CONFIRMED`.
- Provider and reconciliation evidence explaining why issuers, securities, and
  listings exist, and which observations support or block promotion.
- Immutable reconciliation evaluation/audit history showing dry-run decisions,
  applied promotions, rule versions, confidence, explanations, and linked
  evidence.
- Durable validation, conflict, daily summary, and reconciliation reports stored
  under predictable run-report paths.

What should be considered done and authoritative:

- The SEC current-state ingestion pipeline is reliable and idempotent.
- SEC source content identity and observation lineage are durable.
- CIK-backed issuer identity and SEC-observed current listing facts are
  authoritative to the level supported by the SEC source files.
- Security identity status is explicit; `PROVISIONAL` is not treated as
  permanent truth.
- `CONFIRMED` security identity is authoritative only when backed by stored
  reconciliation evidence and audit rows.

What should still be considered not done:

- Historical backfill ingestion and historical lifecycle reconstruction.
- Automatic merge/split execution for duplicate or successor identities.
- Cross-provider reconciliation across FIGI, CUSIP/ISIN, vendor datasets, or
  other future sources.
- Descriptive enrichment such as sector, industry, fund categories, asset class,
  fundamentals, or analytics-ready classifications unless separately built.
- Broad hydration that silently overwrites identity facts; hydration should
  write additive evidence until reconciliation rules promote or reject it.

Backfill readiness after this plan:

- Ready to design and build backfill against stable contracts.
- Ready to run read-only backfill experiments and additive evidence collection.
- Not automatically ready to mutate confirmed identity history at scale until
  the backfill design defines source priority, temporal rules, conflict handling,
  and review/reporting expectations.

## OHLCV Readiness Guidance

Do not block all OHLCV work on perfect historical security-master coverage.
Daily current OHLCV and historical OHLCV backfill have different readiness
thresholds.

Daily current OHLCV can begin after the early reconciliation foundations are in
place:

- The consolidated SEC daily refresh DAG is stable.
- `security.identity_status` exists and distinguishes `PROVISIONAL` from
  `CONFIRMED`.
- Evidence and audit basics exist.
- Reconciliation dry-run reporting exists.
- Duplicate provisional candidate detection exists at least as warnings.
- Consumers have a clear policy that OHLCV may attach to `listing_id`, but must
  respect listing quality and security identity status.

At that point, daily OHLCV should be added as an additive provider pipeline for
current active listings. It should preserve immutable provider observations and
attach normalized bars cautiously, so later identity/backfill improvements can
change interpretation without destroying raw price facts.

Preferred high-level storage shape:

```text
ohlcv_provider_observation
  provider
  observed_symbol
  observed_exchange / venue
  price_date
  open/high/low/close/volume
  raw provider metadata

ohlcv_bar
  listing_id nullable or confidence-scoped
  provider_observation_id
  price_date
  normalized open/high/low/close/volume
  adjustment status
```

Historical OHLCV backfill should wait for a separate security/listing backfill
design. Historical bars are where ticker reuse, exchange changes, delistings,
splits, symbol changes, and successor identities become material. The system
does not need full historical execution before historical OHLCV work starts, but
it does need temporal identity rules and conflict handling before historical
bars mutate normalized canonical facts at scale.

Practical readiness summary:

- Daily current OHLCV: begin after phases 0-6 are complete and reports show
  current listings are stable enough for cautious attachment.
- Historical OHLCV backfill: begin after the security/listing backfill design
  defines temporal identity, source priority, adjustment, and conflict rules.
- Never treat OHLCV ingestion as a reason to silently promote, merge, split, or
  overwrite security identity. It should write additive observations first and
  let reconciliation decide identity meaning.
