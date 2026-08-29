# Technical Indicators Airflow Rollout V1

## Decision

A11.8 selects **event-driven source-completion operation** as the production
cadence for `stonks_tech_indicators_daily_refresh`. The coordinator keeps
`schedule=None`, `catchup=False`, and `max_active_runs=1`. Qualifying EODData
and Yahoo/SPX completions wake it asynchronously, and its package-owned
same-effective-date readiness check remains authoritative.

This decision does not enable normal refresh yet. The coordinator remains
paused until P13.14 records a go decision after the staged backfill and bounded
live-daily gates. This preserves the release contract that a successful
fixture vertical is necessary evidence, not production authorization.

The source cadences do not change:

- `stonks_ohlcv_eoddata_daily_scrape` remains scheduled and unpaused at its
  reviewed weekday cadence.
- `stonks_ohlcv_yahoo_daily_scrape` remains `schedule=None`, manual-only, and
  paused between operator runs under the V10.10 source decision.
- The technical coordinator remains `schedule=None` and paused until P13.14.

## Evidence And Alternatives

A11.6 proved deterministic retry coalescing, distinct later source wakes,
zero-state lock contention, atomic first publication, and unchanged-input
`NO_OP`. A11.7 then proved the deployed Airflow 3.2.1 vertical with two source
completion fixtures: two successful coordinator task graphs, one 15,498-row
publication, one zero-write `NO_OP`, four checksum-valid JSON/PDF objects, and
zero fixture residue.

That evidence supports source events as bounded wake hints. It does not support
an independent technical schedule: EODData runs twice on weekdays, while
Yahoo remains operator-driven and may complete or reconcile an older date.
Polling would guess at timing or require new durable date-discovery state.
Manual-only technical operation is also rejected as the target cadence because
the source dispatch, exact-date join, retry identity, lock, and idempotency path
have now been proven end to end. Keeping an extra operator trigger would add a
failure-prone step without improving readiness authority.

## Activation Gate

P13.14 may approve normal operation only after P13.8-P13.13 evidence satisfies
the frozen release gates, including at least three consecutive ready effective
dates and one unchanged rerun within the daily targets. Before activation:

1. Confirm zero Airflow import errors and the expected three DAG definitions.
2. Confirm EODData is unpaused, Yahoo is paused, and the coordinator is paused.
3. Inspect coordinator DAG runs and account for every queued or running wake.
4. Confirm the reviewed calculation version, source universes, database
   readiness, report storage, performance, risks, and recovery decision.
5. Record the P13.14 go decision before leaving the coordinator enabled for normal operation.

Use the repository Airflow views for the first checks:

```bash
make airflow-dags
make airflow-dag-runs DAG=stonks_tech_indicators_daily_refresh
docker compose --env-file deploy/env/local.env \
  -f deploy/compose/empire.yml exec airflow-api \
  airflow dags list-import-errors --output json
```

After a recorded go decision, enable only the coordinator:

```bash
docker compose --env-file deploy/env/local.env \
  -f deploy/compose/empire.yml exec airflow-api \
  airflow dags unpause stonks_tech_indicators_daily_refresh
make airflow-dags
```

Do not schedule or permanently unpause Yahoo as part of technical-indicator
activation.

## Normal Wake And Backlog Behavior

The coordinator has no clock cadence. Every run must carry one exact effective
date. An early EODData wake normally skips before technical Core, report, or
publication state when same-date Yahoo/SPX evidence is absent. A later
qualifying Yahoo completion wakes the same readiness path. A reconciliation
may create a later same-date wake; unchanged inputs converge to `NO_OP`.

`max_active_runs=1` bounds executing DAG runs, not the number of queued wakes.
Pausing the coordinator does not stop source DAGs from creating queued
coordinator runs. During a short technical hold, leave source ingestion on,
avoid optional Yahoo runs, and inspect the coordinator run list before resume.
On resume, exact-date readiness, deterministic source retry IDs, the global
writer lock, and idempotent publication make those wakes data-safe, while
Airflow drains them one at a time.

For a prolonged hold, do not blindly unpause a large backlog. Keep the
coordinator paused, record each queued run ID/effective date/source identity,
and decide explicitly whether to drain it or cancel the exact obsolete Airflow
run through the approved operator interface. Never delete Core runs,
publications, payloads, feature rows, source rows, advisory locks, or Airflow
metadata to clear a cadence backlog. Pausing EODData to suppress all new wakes
is a separate source-ingestion decision and is not part of technical rollback.

## Pause And Rollback

Pause immediately when import errors, repeated task failures, unexpected
warnings, readiness drift, lock anomalies, report mismatch, partial visibility,
performance/resource regression, or a V12 stop condition appears:

```bash
docker compose --env-file deploy/env/local.env \
  -f deploy/compose/empire.yml exec airflow-api \
  airflow dags pause stonks_tech_indicators_daily_refresh
make airflow-dags
make airflow-dag-runs DAG=stonks_tech_indicators_daily_refresh
```

Pausing prevents queued runs from starting; it does not terminate an already
running task. Let healthy work reach a terminal state and inspect its Core and
reports. Exceptional cancellation follows the operator runbook and requires an
exact target and explicit authorization; do not terminate PostgreSQL backends
or call advisory-unlock functions as routine recovery.

Cadence rollback is the same pause operation. Because the selected coordinator
has `schedule=None`, there is no cron expression or catchup state to restore.
Keep the source cadences unchanged, preserve the last complete publication,
and diagnose through the package inspection, Core, and report contracts. A
cadence rollback never rewrites or deletes technical or OHLCV data. Any later
data correction or rebuild is a separate, bounded package workflow under the
publication and recovery contracts.

## A11.8 Deployed-State Check

On 2026-08-29, the live metadata check found no queued or running runs for the
three participating DAGs and zero import errors. EODData was unpaused and the
technical coordinator was paused. Yahoo had drifted to unpaused; A11.8 restored
it to the required V10.10 paused state and verified the final states as:

```text
stonks_ohlcv_eoddata_daily_scrape     paused=false  active=0
stonks_ohlcv_yahoo_daily_scrape       paused=true   active=0
stonks_tech_indicators_daily_refresh  paused=true   active=0
```

The selected event-driven cadence is therefore documented and ready for the
later P13.14 decision, while normal technical refresh remains disabled.
