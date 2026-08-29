# Technical Indicators Airflow Coordination V1

## Status And Scope

A11.1 selects the V1 Airflow coordination mechanism for daily technical
indicators. This contract decides how completed EODData and Yahoo/SPX work wakes
the technical-indicator workflow and how the workflow joins those prerequisites
for one effective date. It does not implement the source signals, DAG, trigger
wiring, or production enablement owned by A11.2-A11.8.

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
  ID, source DAG ID, and source DAG-run ID as small secret-safe provenance.
  A11.2 freezes the exact payload shape.
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

A11.6 must prove these behaviors under repeated and overlapping source runs.

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
- No task in A11.1 enables scheduling or changes either source DAG. A11.8 owns
  the production cadence, pause behavior, backlog handling, and rollback
  decision after the Airflow vertical is proven.

## Implementation Handoff

- A11.2 adds the minimal secret-safe source completion values required for
  deterministic dispatch and same-date evidence.
- A11.3 adds the manual/event-woken coordinator DAG and validated scope inputs.
- A11.4 freezes its import, schedule, task-shape, date, logging, and delegation
  tests.
- A11.5 adds asynchronous trigger tasks to both source DAGs and the coordinator
  preflight join.
- A11.6 proves repeated-run coalescence, idempotency, and lock behavior.
- A11.7 verifies the complete Airflow/Core/report vertical.
- A11.8 alone decides whether and how automatic dispatch is enabled in normal
  operation.
