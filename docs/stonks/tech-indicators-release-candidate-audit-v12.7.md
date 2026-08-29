# Technical-Indicator Release-Candidate Audit (V12.7)

Date: 2026-08-29

Decision: pass. The V1 development release candidate has no unresolved code or
documentation blocker. This audit does not close the development gate, enable
Airflow cadence, authorize a broad source or technical-indicator backfill, or
replace the explicit V12.8 ready/not-ready decision.

The audited working tree was based on commit
`b58eff17e1b2b880ad7e9217d5ed5a90d1cdd75c`. V12.8 owns the final reviewed
commit because this evidence and its plan integration necessarily follow that
base commit.

## Candidate Matrix

| Surface | Audited release state | Result |
|---|---|---|
| Package and calculation profile | `empire-stonks-tech-indicators` 0.1.0; `TECH_INDICATORS_V1`; report schema 1; Python `>=3.11,<4.0` | Pass |
| Calculation runtime | NumPy 2.4.6 and TA-Lib Python/C 0.7.1 in the package lock, local environment, Airflow requirements, and deployed Airflow image | Pass |
| Empire dependencies | `empire-core` 0.1.0 and `empire-reports` 0.1.0; local `pip check` and Airflow `pip check` reported no broken requirements | Pass |
| Distribution | Package-local `poetry build` produced the 0.1.0 wheel and source distribution; wheel metadata contained the exact runtime pins and four console entry points | Pass |
| Database | Flyway 12.6.1 validated 39 migrations against PostgreSQL 18.4; the technical-indicator schema contract passed all 64 expected rejection cases and rolled back | Pass |
| Configuration | The package defaults, all 10 committed example settings, and all 10 Airflow Compose defaults match exactly | Pass |
| Operator entry points | Four executable wrappers passed shell syntax and help smokes; the live read-only config preflight returned `ready=true` | Pass |
| Compose and Airflow | Compose configuration resolved; Airflow 3.2.1 had zero DAG import errors, exact installed dependencies, and four installed technical-indicator commands | Pass |
| Reports and assets | JSON/PDF/storage tests passed; all six required fonts registered without fallback and both required 512h black logo lockups exist among 109 tracked branding assets | Pass |
| Source universes | Package SQL, subject policy, README, source contracts, and bounded live aggregates agree on the seven exact provider-native cohorts | Pass |
| Recovery and rollback | Cadence pause, atomic failure isolation, staged resume, source correction, calculation-version withdrawal, lock recovery, and ambiguous-response recovery are explicit in the operator runbook and tested | Pass |

The committed lock file uses lock format 2.1, declares Python
`>=3.11,<4.0`, and has content hash
`52eeffe6587fd118fb267efc46f15bf042211d533a668dbf83eacb87e75b58d2`.
Its file SHA-256 was
`4056f78a393f55c2c01d55ea553d86252b0432528be4ebc5c762121868690395`.
The Airflow image remains based on `apache/airflow:3.2.1`, installs binary
NumPy/TA-Lib first, then installs Core, reports, OHLCV, and technical indicators
in dependency order.

Poetry 2.4.1 on the audited host has a tool-level path-resolution defect when
`poetry --directory` receives a relative src-layout package path: wheel assembly
looks under `src/src`. The documented package-local `poetry build` command and
the Airflow image build path are unaffected and both succeeded. No package
metadata workaround was added for this host-tooling defect.

## Migration And Configuration Boundaries

The technical-indicator schema is owned by the single forward migration
`V2026.08.09.0001__stonks_create_tech_indicators.sql`, whose SHA-256 was
`cd9af004ce2b4b2752aa043db3f9bcafd2cf4cbda2fe27d448038028a60e3df6`.
Empire does not rewrite or reverse an applied versioned migration. A schema
problem requires a reviewed forward migration; a production disaster requires
the P13.7 backup/restore procedure. Application or calculation rollback must
use the package-owned publication paths and must never manually flip slots,
restore stale payload rows, or edit Flyway history.

The active local preflight resolved package 0.1.0, Python 3.14.6, NumPy 2.4.6,
TA-Lib Python/C 0.7.1, PostgreSQL 18.4, ten required relations, the writable
`global` storage root, and exactly one active `YAHOO/XIDX/SPX` benchmark. The
exact-listing inspection proved that benchmark has 15,497 source rows from
1965-01-04 through 2026-08-03 and correctly remains an unsupported technical
subject with no published technical rows. Its current-date source evidence was
not ready; this is expected development data state, not a release defect.

## Airflow Rollout State

The live Airflow metadata and source definitions agree:

- `stonks_tech_indicators_daily_refresh` uses `schedule=None`, `catchup=False`,
  and `max_active_runs=1`, and remains paused.
- EODData retains the reviewed weekday source schedule and is unpaused.
- Yahoo uses `schedule=None` and remains paused/manual-only.
- Both source DAGs dispatch exact completion evidence to the technical
  coordinator; 53 focused OHLCV completion and DAG tests passed.
- Airflow reported no import errors. Its installed technical package and
  calculation runtime exactly match the package candidate.

The coordinator must remain paused until P13.14. P13.4-P13.5 own the future
deployment-aware local/production source scheduling profile; V12.7 does not
preempt that design or enable production cadence.

## Supported Provider-Native Universe

The frozen calculation universe is exact and case-sensitive:

| Provider | Exact eligible identity | Active listings | Source rows |
|---|---|---:|---:|
| EODData | `AMEX`, metadata type `EQUITY` | 4,322 | 32,938 |
| EODData | `NASDAQ`, metadata type `EQUITY` | 5,364 | 38,085 |
| EODData | `NYSE`, metadata type `EQUITY` | 3,012 | 22,026 |
| Stooq | `nasdaq` | 4,704 | 9,082,078 |
| Stooq | `nyse` | 4,537 | 10,558,875 |
| Stooq | `nysemkt` | 321 | 834,783 |
| Yahoo | `XIDX/SPX`, `EQUITY_INDEX`, `YahooTicker=^GSPC` | 1 | 15,497 |
| **Total** | **Seven cohorts** | **22,261** | **20,584,282** |

These are bounded read-only development aggregates. They do not authorize
processing the full universe. SPX-relative features remain supported only for
the EODData and Stooq cash-equity cohorts; SPX supplies the benchmark and is not
itself an SPX-relative subject.

## Recovery And Rollback Audit

The operator runbook provides the release-candidate recovery boundary:

- Pause only the technical coordinator to stop new technical work; inventory
  queued and running wakes because pausing does not terminate active work.
- Preserve the prior complete publication after any pre-commit failure. Resume
  staged work only from an exact durable cursor.
- Inspect Core, reports, publication, and readiness before retrying an
  ambiguous response after a possible commit.
- Converge source corrections through the owning OHLCV workflow, then run the
  exact bounded technical correction or rebuild.
- Withdraw a calculation version through a fresh validated staged publication
  under reviewed code. Never flip A/B membership or reactivate stale rows.
- Let PostgreSQL transaction advisory locks release on transaction or
  connection termination. Never delete a lock row or routinely terminate its
  backend.

The correctness/isolation and database-backed integration suites exercise
these visibility, contention, failure, retry, correction, resume, and version
boundaries. Production backup restore, service reboot, and NAS failure recovery
remain P13.7 gates because they cannot be proven on this development host.

## Production-Only Operational Risks

The following risks are explicitly deferred and are not development-release
blockers. Each has a Phase 13 owner and must pass before P13.14 can enable
normal operation:

| Risk requiring production hardware or deployment state | Required gate |
|---|---|
| HPE CPU, memory, storage-growth, expansion, warranty, and purchase sizing against the V12.6 measurements | P13.1 |
| Server firmware, OS patch level, Docker/Compose versions, time sync, administrative access, firewall, power/restart behavior, and monitoring | P13.2 |
| NAS identity, least-privilege mounts, boot/reconnect behavior, throughput, free space, and mount-failure protection before storage-root initialization | P13.3 |
| Production scheduling profile, exact source cadence, timezone/DST behavior, parse-time validation, pause, and rollback while local source DAGs remain manual | P13.4-P13.5 |
| Exact reviewed deployment commit, production secrets, database endpoints, storage roots, image build, Flyway application, and Airflow initialization | P13.6 |
| PostgreSQL/PgBouncer/storage preflights, backups and restore, container restart and host reboot recovery, and production observability | P13.7 |
| Provider access, pacing, full historical source quality, staged cohort capacity, production calculation/report performance, and initial publication storage/WAL growth | P13.8-P13.10 |
| Exact scheduled-run semantics, queued-wake behavior, three consecutive ready dates, unchanged rerun, resource use, provider pressure, and stop conditions | P13.11-P13.13 |

The current development database has no published full-universe technical
image. Consequently a production-scale healthy no-op, full populated-universe
summary, live source-to-technical latency, backup volume, and real NAS behavior
cannot be evaluated until P13.10 builds the initial production coverage. The
V12.6 bounded performance gate remains the capacity input, not a production
claim.

## Exact Verification

From the repository root unless a package directory is stated:

```bash
make db-validate
make db-test-tech-indicators-schema
```

Results: 39 Flyway migrations validated; the schema contract passed with 64
expected failures and rolled back.

```bash
cd packages/empire-stonks-tech-indicators
poetry check --lock
poetry build
poetry run python -m pip check
poetry run pytest -q
```

Results: lock check passed; wheel and source distribution built; `pip check`
reported no broken requirements; 761 non-database tests passed with 28
database tests skipped when the environment was intentionally absent.

With `deploy/env/local.env` loaded, the 27 cleanup-safe database integration
tests passed together in 13.79 seconds and the long vertical integration test
passed independently in 15.65 seconds. Combined with the non-database run, all
789 collected package tests passed. The report JSON/PDF/storage subset passed
35 tests in 1.48 seconds, and the OHLCV completion/EODData/Yahoo DAG subset
passed 53 tests in 0.91 seconds.

```bash
bin/stonks-tech-indicators-config
bin/stonks-tech-indicators-{config,daily,backfill,inspect} --help
make airflow-dags
docker compose --env-file deploy/env/local.env -f deploy/compose/empire.yml \
  exec -T airflow-api airflow dags list-import-errors --output json
docker compose --env-file deploy/env/local.env -f deploy/compose/empire.yml \
  exec -T airflow-api python -m pip check
```

Results: preflight `ready=true`; four local wrapper and four installed Airflow
entry-point help smokes passed; the technical DAG was paused; import errors
were `[]`; and Airflow dependencies were consistent. Compose configuration,
ten-setting parity, wheel metadata/entry points, six exact fonts, two exact
logos, bounded seven-cohort database aggregates, and exact SPX inspection also
passed. No source or technical backfill, publication, remediation, migration,
cadence change, or durable data write ran.
