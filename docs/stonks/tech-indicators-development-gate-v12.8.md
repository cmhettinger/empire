# Technical-Indicator Development Gate (V12.8)

Date: 2026-08-29

Phase 13 decision: **READY**.

Empire may begin Phase 13 at P13.1 using the reviewed V1 development candidate
and the capacity assumptions below. This decision authorizes staged production
planning, procurement, host preparation, deployment design, and the ordered
Phase 13 gates only. It does not authorize a broad source import, a technical-
indicator backfill, publication, production source cadence, or release of the
technical coordinator. Normal production operation remains an explicit P13.14
go/no-go decision.

## Reviewed Candidate

| Identity | Reviewed value |
|---|---|
| Git commit | `eedc9d264241e4e6e8b326e21142d31b85c17cf7` (`V12.7`) |
| Branch state at review | `main`, equal to `origin/main`, clean working tree |
| Package | `empire-stonks-tech-indicators` 0.1.0 |
| Calculation version | `TECH_INDICATORS_V1` |
| Report schema | 1 |
| Python contract | `>=3.11,<4.0`; reviewed runtime 3.14.6 |
| Calculation runtime | NumPy 2.4.6; TA-Lib Python/C 0.7.1 |
| Database runtime | PostgreSQL 18.4; Flyway 12.6.1 |
| Orchestration runtime | Airflow 3.2.1 |

The reviewed hash is the complete development candidate through V12.7. This
V12.8 decision record follows that hash. It is not the eventual production
deployment hash: P13.4-P13.5 intentionally add the reviewed deployment-aware
scheduling profile, and P13.6 must record and deploy the exact later commit.

The committed package lock is format 2.1 with content hash
`52eeffe6587fd118fb267efc46f15bf042211d533a668dbf83eacb87e75b58d2`.
The full package, migration, configuration, wrapper, Compose/Airflow, report-
asset, universe, and rollback inventory is in the
[V12.7 release-candidate audit](tech-indicators-release-candidate-audit-v12.7.md).

## Development Evidence

| Gate | Evidence | Result |
|---|---|---|
| Documentation and operation | V12.1 package README and V12.2 operator runbook cover ownership, formulas, source caveats, configuration, schema, reports, CLIs, Airflow, bounded execution, recovery, and rollback | Pass |
| Package and integration regression | V12.3 passed the then-current full technical package plus standalone Core/report, schema, CLI, distribution, and Airflow checks; subsequent V12.5 and V12.7 runs passed all 789 current package tests | Pass |
| Database and generated documentation | V12.4 validated 39 migrations, four rollback-only Stonks SQL contracts, 641 database-enabled OHLCV tests, and all generated schema/ERD artifacts without substantive drift | Pass |
| Correctness and isolation | [V12.5](tech-indicators-correctness-isolation-audit-v12.5.md) passed independent formulas, pinned TA-Lib, an 850-row/76-feature stored-versus-fresh audit, incremental equivalence, provider/version isolation, publication visibility, SPX completeness, writer locking, and recovery | Pass |
| Representative performance | [V12.6](tech-indicators-performance-evidence-v12.6.md) passed calculation, million-row pilot, persistence, transaction, query, report, memory, storage, WAL, publication, and lock gates without evidence-driven tuning | Pass |
| Release candidate | [V12.7](tech-indicators-release-candidate-audit-v12.7.md) passed package/lock/build, migration, environment, wrapper, deployment, asset, universe, rollback, and production-prerequisite review with no unresolved development blocker | Pass |
| Final state recheck | Lock and dependency checks, Flyway validation, live configuration preflight, Airflow inventory/import health, repository links/fences, and diff hygiene | Pass |

The V12.5 audit used deterministic and rollback-only generated data and only
bounded aggregate facts from the development database. The V12.6 performance
gate used generated workloads and disposable scratch schemas. Neither evidence
set ran a broad source or technical backfill or changed live cadence.

## Supported V1 Universe

Calculation is limited to these exact provider-native identities:

| Provider | Eligible identity | SPX-relative subject support |
|---|---|---|
| EODData | `NYSE`, `NASDAQ`, or `AMEX`, with metadata type resolving to `EQUITY` | Yes |
| Stooq | `nasdaq`, `nyse`, or `nysemkt` U.S. stock partition | Yes |
| Yahoo | Exact `XIDX/SPX`, `EQUITY_INDEX`, `YahooTicker=^GSPC` benchmark | No; benchmark only |

At review, the bounded eligible development inventory contained 22,261 active
listings and 20,584,282 source rows across those seven provider/market cohorts.
These counts are planning inputs, not permission for one unbounded run. Phase
13 must stage and stop between Yahoo SPX and each EODData/Stooq market cohort.

Provider-native source semantics remain unchanged: EODData and Stooq
adjustment, volume, and currency bases are not normalized or upgraded by this
package; Yahoo SPX uses native unadjusted Chart OHLC. V1 does not merge
providers, convert currency, reconstruct corporate actions, or retain source-
bar or technical revision history. Reports and downstream consumers must keep
those disclosures attached to the data.

## Production Capacity Assumptions

These are mandatory planning and rollout assumptions, not a selected HPE bill
of materials. P13.1 must translate them into a whole-host configuration with
operating-system, PostgreSQL, Airflow, Docker, monitoring, NAS, backup, growth,
and failure headroom.

| Dimension | V12.8 assumption or hard gate |
|---|---|
| Initial calculation scope | 22,261 active eligible listings and 20,584,282 source rows; recalculate before every production cohort |
| Writer concurrency | One global PostgreSQL advisory-locked writer; capacity and schedules must not assume parallel technical writers |
| Read/write shape | 10,000-row source pages, 5,000-row default writes, 10,000-row configurable write maximum, and 25,000-row hard transaction ceiling |
| Transaction duration | Target at most 30 seconds; representative hard maximum 60 seconds |
| Process memory | Full rebuild and million-row pilot gate at most 2 GiB RSS; ordinary daily at most 1 GiB; reports and one 20,000-row listing at most 512 MiB |
| Throughput and duration | At least 250 evaluated-and-persisted rows/second after startup; full initial universe under 24 hours; ordinary append/correction of at most 25,000 rows under five minutes |
| Measured pilot | 1,000,000 rows at 1,035.40 rows/second and 412.469 MiB peak RSS; production hardware must re-prove rather than extrapolate this as guaranteed throughput |
| Technical storage | 935.5264 measured bytes per row; two populated initial payload slots project to 35.869 GiB |
| Free-space gate | At least 87,765,975,184 bytes available before a full generation, equal to twice the projected additional footprint plus 10 GiB; backups, source growth, WAL retention, and other Empire data require separate added capacity |
| Database baseline | PostgreSQL 18.4 evidence used 128 MiB `shared_buffers`, 4 MiB `work_mem`, and 64 MiB `maintenance_work_mem`; any production tuning must repeat the plans and memory gates |
| Query latency | Latest slice 250 ms median/1 s max; rank 500 ms/2 s; full coverage summary 10 s/30 s; required indexes and no prohibited spill/full-scan shape |
| Reports | Daily render under 30 seconds, backfill render under 60 seconds, each at most 512 MiB RSS; JSON at most 2 MiB, PDF at most 5 MiB and 25 pages |
| Network and NAS | No development-host throughput claim; P13.3 must prove mount identity, boot/reconnect, sustained throughput, free-space reporting, and safe failure before Core storage initialization |

The 2-GiB process gate is not a whole-server memory recommendation. P13.1 must
add simultaneous PostgreSQL, Airflow, Redis, container, filesystem-cache,
monitoring, backup, and operating-system needs. Likewise, the free-space gate
is a minimum pre-generation safety check, not total NAS sizing or a retention
policy.

## Known Risks And Required Owners

| Known risk | Containment and owner |
|---|---|
| No production hardware, NAS, network, backup, restore, reboot, or observability evidence exists yet | P13.1-P13.3 and P13.7 must prove them before data loading |
| No deployment-aware local/production source schedule exists | P13.4-P13.5 must implement and parse-test it; the future local profile must make both source DAGs manual while the technical coordinator remains event-driven |
| The production database has no initial technical publication, so full-universe no-op, summary, storage/WAL, and runtime behavior are unproven | P13.8-P13.10 must load sources and build isolated cohorts with stop conditions before any cadence rehearsal |
| Yahoo access, pacing, source completeness, and conservative cadence require production evidence | P13.5, P13.9, and P13.11 own the decision and bounded verification |
| Provider-native adjustment, volume, and currency semantics are deliberately not normalized, and current-state corrections have no revision history | Preserve source/run/report provenance and disclosures; stop on unexplained drift or crossover |
| The global writer lock serializes all providers, dates, dry runs, corrections, and backfills; paused Airflow wakes can queue | Keep `max_active_runs=1`, inventory every wake, stage cohorts, monitor heartbeat, and stop on unexplained backlog |
| V1 supports only `TECH_INDICATORS_V1`; version withdrawal cannot restore stale rows | Use a fresh validated staged publication under reviewed code; never flip slots manually |
| Applied Flyway migrations are forward-only compatibility boundaries | Correct with a reviewed forward migration; P13.7 must prove backup restore for disaster recovery |
| Poetry 2.4.1 misresolves relative `--directory` src-layout wheel builds on the reviewed development host | Use the documented package-local `poetry build`; the Airflow image build path is unaffected |

Any formula mismatch, source mutation, provider leakage, mixed or partial
publication, benchmark incompleteness, unrecoverable resume drift, lock
failure, report mismatch, capacity violation, or unexplained warning stops the
rollout and leaves cadence disabled.

## Recovery Procedures

The [operator runbook](tech-indicators-operator-runbook.md) is the canonical
recovery procedure. The Phase 13 handoff must preserve these boundaries:

1. Pause the technical coordinator, inventory queued/running exact-date wakes,
   and allow healthy active work to finish unless an exact exceptional
   cancellation is authorized.
2. Keep the prior complete publication visible after any pre-commit failure.
   Resume staged work only from a returned durable cursor.
3. After a possible commit with a failed response, inspect Core, publication,
   reports, and readiness before deciding whether any retry is needed.
4. Correct source data through the owning OHLCV workflow, inspect drift, and
   run only the exact bounded technical correction or staged rebuild.
5. Withdraw a calculation version through a new validated staged publication
   under reviewed code. Never edit membership or reactivate stale payloads.
6. Let PostgreSQL release transaction advisory locks normally. Do not delete a
   lock row, call advisory unlock, or terminate a backend as routine recovery.
7. Treat schema repair as a forward migration and infrastructure disaster as a
   tested backup restore, not an edit to Flyway history.

## Decision Conditions

V12.8 is complete and Phase 13 may start because all development gates through
V12.7 passed, the reviewed candidate is committed, no development blocker is
open, risks have explicit owners, and recovery/capacity boundaries are
preserved.

The decision becomes **NOT READY** and work stops at the current Phase 13 gate
if any assumption is invalidated or a required gate fails. Passing V12.8 never
skips a Phase 13 dependency. Production cadence remains disabled until P13.14
records a separate go decision after staged source loading, initial technical
coverage, exact-path rehearsal, and bounded live observation all pass.

## Final Verification

Against reviewed commit `eedc9d264241e4e6e8b326e21142d31b85c17cf7`:

```bash
cd packages/empire-stonks-tech-indicators
poetry check --lock
poetry run python -m pip check

cd ../..
make db-validate
bin/stonks-tech-indicators-config
make airflow-dags
docker compose --env-file deploy/env/local.env -f deploy/compose/empire.yml \
  exec -T airflow-api airflow dags list-import-errors --output json
docker compose --env-file deploy/env/local.env -f deploy/compose/empire.yml \
  exec -T airflow-api python -m pip check
```

Results: lock validation passed; local and Airflow dependency checks reported
no broken requirements; Flyway validated 39 migrations; configuration returned
`ready=true` for `TECH_INDICATORS_V1`; Airflow import errors were `[]`; and the
technical coordinator remained paused. V12.7 supplies the current 789-test,
schema, build, CLI, report, asset, universe, and deployment evidence.

No source or indicator backfill, publication, migration, remediation, service
activation, schedule change, or durable data write ran during V12.8.
