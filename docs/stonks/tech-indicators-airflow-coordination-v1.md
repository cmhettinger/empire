# Technical Indicators Airflow Coordination V1

## Status And Scope

A11.1 selects the V1 Airflow coordination mechanism for daily technical
indicators. A11.2 freezes its source completion signals, A11.3 implements the
initially manual coordinator DAG, A11.4 freezes its DAG contract tests, A11.5
wires both sources to the package-owned same-date preflight join, and A11.6
proves repeated-run and overlap behavior. This
contract decides how successful EODData and Yahoo/SPX completions wake the
technical-indicator workflow and how it joins those prerequisites for one
effective date. The full Airflow vertical and final production cadence decision
remain owned by A11.7-A11.8.

The deployed runtime is Apache Airflow 3.2.1 with
`apache-airflow-providers-standard` 1.12.3. The live source DAGs are intentionally
unlike:

- `stonks_ohlcv_eoddata_daily_scrape` runs at 20:15 and 23:15
  `America/New_York` on weekdays, with package-owned eligibility and
  reconciliation deciding whether work is due.
- `stonks_ohlcv_yahoo_daily_scrape` has `schedule=None` and stays manual under
  the V10.10 rollout decision.
- Both accept an explicit effective-date override, so an Airflow logical date or
  data interval is not the business-date join key.

The package already owns the authoritative I3.6 predicate in
`decide_source_readiness()`. Airflow coordination must wake and invoke that
predicate; it must not replace it with scheduler state.

## Selected Mechanism

Use the named `stonks_tech_indicators_daily_refresh` DAG as a manual and
event-woken coordinator with `schedule=None`, `catchup=False`, and
`max_active_runs=1` initially.

After a source runner task succeeds, each EODData and Yahoo DAG asynchronously
dispatches the coordinator through `TriggerDagRunOperator`:

```text
EODData success --\
                  +--> tech coordinator wake --> same-date DB readiness
Yahoo success ----/                              --> package daily runner
```

The dispatch contract is:

- Dispatch only downstream of successful package-runner completion. A failed
  or cancelled source task emits no successful wake.
- Pass the explicit source `effective_date`, source provider, source Core run
  ID, source DAG ID, and source DAG-run ID as small secret-safe provenance,
  using the exact A11.2 payload below.
- Give each source completion a deterministic coordinator run ID derived from
  its source identity and Core run ID. Set `skip_when_already_exists=True` so a
  retry of the same dispatch does not create another wake.
- Use `wait_for_completion=False`. Source acquisition must not occupy a worker
  or change its data result while waiting for technical calculation.
- Do not reset an existing coordinator run and do not infer the effective date
  from the trigger's logical date or data interval.

The coordinator validates its explicit effective date and performs a read-only
I3.6 preflight before invoking `run_tech_indicators_daily()` for the unfiltered
V1 daily scope. A not-ready wake ends as a bounded, successful orchestration
no-op: it creates no technical Core run, report, publication, or payload state.
The later source completion creates another independent wake. A ready preflight
calls the normal package runner, which reacquires and rechecks readiness after
the package-owned writer lock; the preflight is an optimization, never the
authority for publication.

Manual invocations use the same coordinator task graph and package runner. They
may provide the bounded A11.3 scope overrides, but no override bypasses source
readiness, the writer lock, validation, or atomic publication.

## Manual Coordinator Contract

`dags/stonks/stonks_tech_indicators_daily_refresh.py` contains the ordered tasks
`check_source_readiness` and `run_tech_indicators_daily`. The DAG has
`schedule=None`, `catchup=False`, and `max_active_runs=1`, and uses
`America/New_York` only for its fixed start-date identity. It never derives the
business effective date from wall time, logical date, or data interval.

Every run requires `dag_run.conf.effective_date` as canonical `YYYY-MM-DD`.
Optional scope keys are `provider_codes`, `markets`, `provider_listing_ids`,
`calculation_version`, `dry_run`, and `force`. Selectors must be JSON arrays;
provider codes are uppercase, markets are trimmed provider-native text, and
listing IDs are canonical lowercase UUID strings. Listing-ID scope cannot be
combined with provider or market filters. Booleans must be JSON booleans, and
the package scope enforces the frozen calculation version and all remaining
normalization and compatibility rules.

The DAG accepts and validates the exact A11.2 coordination provenance keys.
Its package-owned preflight uses a repeatable-read, read-only transaction and
returns only the bounded readiness decision. When ready, the runner task loads
the Compose-owned environment, uses independent work, Core, and object-store
connections plus the normal lock connection factory, and delegates to
`run_tech_indicators_daily()` with `run_type="airflow"` and
`runner="airflow"`. It returns and logs only the runner's compact secret-safe
result.

## Frozen Source Completion Signal

The OHLCV package owns the immutable
`TechIndicatorsSourceCompletionSignal`; source DAGs do not construct ad hoc
dictionaries. A qualifying source runner result exposes it under
`tech_indicators_completion_signal`. Its exact JSON-safe output is:

```json
{
  "schema_version": 1,
  "signal_type": "stonks_ohlcv_daily_completion",
  "provider_code": "EODDATA",
  "source_code": "eoddata_daily",
  "job_name": "stonks_ohlcv_eoddata_daily",
  "effective_date": "2026-08-28",
  "source_run_id": "10000000-0000-4000-8000-000000000001",
  "report_outcome": "WARN",
  "trigger_run_id": "source__eoddata__10000000-0000-4000-8000-000000000001"
}
```

The Yahoo identity is `YAHOO`, `yahoo_daily`, and
`stonks_ohlcv_yahoo_daily`; its trigger prefix is `source__yahoo__`. The source
Core run UUID makes the trigger ID deterministic for one completed run and
distinct for a later reconciliation run.

Eligibility deliberately mirrors the source half of I3.6:

- EODData emits only for a succeeded result with `PASS` or `WARN`, zero
  failures, and zero missing sessions.
- Yahoo emits only for a succeeded `PASS` or `WARN` result whose ticker scope
  is empty (the full eligible universe) or explicitly contains `SPX`.
- A result that does not meet those rules serializes the nested signal as
  `null`; failed source tasks return no successful result at all.

The trigger configuration derived from the signal has exactly these fields:

```text
coordination_schema_version
effective_date
source_provider_code
source_code
source_job_name
source_core_run_id
source_dag_id
source_dag_run_id
```

It accepts only the two frozen source identities and a bounded Airflow-safe
source DAG-run ID. Neither output carries credentials, configuration, report or
raw-object IDs, raw data, row counts, issue text, or diagnostics. The signal is
still only a wake hint; the coordinator must execute the database readiness
join below.

## Authoritative Date-Scoped Join

One coordinator wake may run technical indicators for date `D` only when the
existing package decision for the exact resolved scope and `D` is ready. For
the normal unfiltered V1 daily scope, that proves all of the following from one
database snapshot:

1. The eligible provider-listing scope is non-empty and the reviewed active
   `YAHOO/XIDX/SPX` identity resolves without drift.
2. A succeeded, completed `stonks_ohlcv_eoddata_daily` Core run has
   `effective_date=D`, safe EODData identity, zero failures, zero missing
   sessions, and a `PASS` or `WARN` report outcome.
3. A succeeded, completed `stonks_ohlcv_yahoo_daily` Core run has
   `effective_date=D`, safe Yahoo source identity, a scope containing `SPX` or
   the full active Yahoo universe, and a `PASS` or `WARN` report outcome.
4. When a supported EODData or Stooq subject has a bar on `D`, SPX has an exact
   bar on `D`; there is no forward fill, nearest-date match, or holiday
   fabrication.

The source Core run IDs returned by the readiness decision become calculation
and report evidence. Airflow task success, event order, wall-clock delay, DAG
logical date, and XCom presence are not substitutes for these checks.

This deliberately permits `WARN` source reports only where the source
contracts already classify bounded row exclusions as a successful import.
EODData must still report zero unresolved missing sessions, and Yahoo/SPX must
still satisfy exact scope and bar coverage.

## Repeated Runs And Concurrency

Both source DAGs dispatch because either may complete second. The first wake may
find the join incomplete and stop without durable technical workflow state; the
second then observes both successful same-date prerequisites and can run.

Repeated EODData reconciliation, a Yahoo rerun, or a retried source completion
may create later coordinator wakes for the same date. This is intentional:

- The source-specific deterministic trigger ID coalesces retry of one exact
  source completion.
- `max_active_runs=1` bounds coordinator overlap inside Airflow.
- The capability-wide PostgreSQL advisory lock remains the only concurrency
  authority across Airflow, CLI, daily, backfill, correction, and rebuild
  writers.
- A later same-date wake converges through the package's idempotent no-op or
  affected-range path rather than relying on Airflow deduplication for data
  correctness.

A11.6 proves these behaviors at the package and database boundaries:

- Replaying one serialized source completion under a different Airflow source
  run retains the exact trigger-run ID because the source Core run is unchanged.
- New EODData and Yahoo Core runs for the same date receive distinct wake IDs,
  while both provenance shapes resolve the same package daily scope.
- A real contending daily runner returns the fixed bounded `CONTENDED` result
  before creating Core, report, publication, or payload state.
- After the held lock is released, the first ready run publishes atomically.
  Later healthy same-date source evidence is selected by readiness, but
  unchanged OHLCV converges to a reported `NO_OP` with no second publication or
  payload timestamp change.

The cleanup-safe PostgreSQL proof also reruns the existing lock-release and
reader-publication visibility cases. This deliberately proves data safety
through the package boundary rather than treating Airflow run serialization as
the correctness mechanism.

## Alternatives Evaluated

### Airflow assets and events

Airflow marks an ordinary asset updated when its producer task succeeds, and
asset-event metadata can carry an effective date. An unpartitioned two-asset
`AND`, however, means both assets changed since the previous consumer run; it
does not prove that the two events describe the same effective date. Event
metadata would therefore move the date join into custom DAG logic after the
scheduler had already combined potentially unlike dates.

Airflow 3.2 introduced partitioned assets and
`PartitionedAssetTimetable`, which can express a same-partition join. They are
not selected for V1 because the source DAGs do not share a timetable-derived
partition: EODData runs twice per business date, Yahoo is manual, and either
may use an explicit backdated override. The deployed Airflow 3.2.1 SDK also has
no `PartitionedAtRuntime` API for assigning the source result's effective date
as a partition during the task. Requiring operators to coordinate both
`dag_run.conf.effective_date` and an Airflow partition key would create two
business-date inputs that can drift.

Assets may be reconsidered after a reviewed Airflow upgrade provides a tested
runtime-partition contract for both source DAGs. Until then, they may be useful
for observability but are not a prerequisite authority. See the official
[Airflow 3.2.1 asset definitions](https://airflow.apache.org/docs/apache-airflow/3.2.1/authoring-and-scheduling/assets.html)
and [3.2 asset-partition release notes](https://airflow.apache.org/docs/apache-airflow/3.2.0/release_notes.html).

### Scheduled polling coordinator

A separately scheduled coordinator was rejected. Choosing a poll time after
EODData still relies on timing, and manual Yahoo may finish before or after that
time or may intentionally refresh an older effective date. A scan for all
unprocessed date intersections would add new durable coordination state and
date-discovery logic that the source completion already provides.

### External task sensors and trigger-and-wait

`ExternalTaskSensor` waits for another DAG or task at a specific Airflow logical
date. The source DAGs' logical dates are not the explicit provider effective
date, particularly for manual and overridden runs. Waiting for manual Yahoo
would also need an arbitrary timeout and would tie up or defer an EODData-linked
workflow for an unbounded operator decision.

Direct trigger-and-wait has the same lifecycle coupling. Technical failure must
not rewrite or invalidate an already durable source success, and source reruns
must not wait for package lock contention. Asynchronous dispatch plus the
database readiness predicate preserves those boundaries. See Airflow's
[cross-DAG dependency guidance](https://airflow.apache.org/docs/apache-airflow-providers-standard/stable/sensors/external_task_sensor.html)
and [`TriggerDagRunOperator` contract](https://airflow.apache.org/docs/apache-airflow-providers-standard/stable/_api/airflow/providers/standard/operators/trigger_dagrun/index.html).

## Failure And Rollout Boundaries

- Failure to dispatch is visible as an Airflow orchestration failure and is
  retryable; it does not roll back the already committed source Core run or
  OHLCV rows.
- A not-ready coordinator wake is not a failed source run and does not create a
  failed technical Core run.
- Once invoked, technical runner failure propagates normally and must preserve
  J9.7 failure safety, report, lock-release, and publication rules.
- A11.5 adds dispatch to the existing source DAGs but does not change their
  schedules: EODData retains its reviewed two-run weekday cadence and Yahoo
  remains manual. A11.8 owns the final production cadence, pause behavior,
  backlog handling, and rollback decision after the Airflow vertical is proven.

## Implementation Handoff

- A11.2 added the package-owned minimal, secret-safe source completion signal
  and deterministic trigger configuration described above.
- A11.3 added the manual coordinator DAG, exact-date/scope validation, runtime
  service wiring, and package-runner delegation described above.
- A11.4 added contract tests for import, tags, manual scheduling, task shape,
  exact-date/scope validation, runtime delegation and identity, compact
  logging, failure cleanup, and the no-SQL/business-logic boundary.
- A11.5 added strict signal deserialization and dispatch construction,
  asynchronous trigger tasks to both source DAGs, and the coordinator's
  package-owned read-only preflight join.
- A11.6 added explicit source retry/new-run identity contracts and a live
  repeated-run proof covering zero-state contention, lock release, atomic first
  publication, latest same-date source evidence, and idempotent `NO_OP`.
- A11.7 verified the complete deployed Airflow/Core/report vertical with two
  bounded source-completion fixtures, one atomic `PASS` publication, one
  zero-write `NO_OP`, four checksum-valid JSON/PDF objects, and zero fixture
  residue. Exact evidence is recorded in
  `tech-indicators-airflow-vertical-evidence-a11.7.md`.
- A11.8 alone decides whether and how automatic dispatch is enabled in normal
  operation.
