# Tech-Indicators Concurrency Contract V1

Status: frozen implementation contract for P0.10 as of 2026-08-09.

This document freezes the V1 database-backed writer lock, contention outcome,
lifetime, loss, and recovery behavior. It extends the
[`tech-indicators-recalculation-contract-v1.md`](tech-indicators-recalculation-contract-v1.md),
[`tech-indicators-performance-release-gates-v1.md`](tech-indicators-performance-release-gates-v1.md),
and
[`tech-indicators-publication-contract-v1.md`](tech-indicators-publication-contract-v1.md).

J9.9 owns the reusable package implementation. CLI and Airflow tasks call that
package implementation and do not create separate locking rules.

## Selected V1 Mechanism

V1 deliberately serializes every tech-indicators workflow that can mutate
payload, publication, membership, recurrence, or cleanup state. It does not
attempt provider-, listing-, date-, job-kind-, or calculation-version-level
parallelism.

The package acquires one PostgreSQL transaction-level advisory lock:

```text
lock seed: empire:stonks:tech-indicators:writer:v1
algorithm: first eight bytes of SHA-256, interpreted as signed big-endian int64
lock key:  7681980501239933110
SQL:       SELECT pg_try_advisory_xact_lock(7681980501239933110::bigint)
```

The seed, algorithm, and resulting integer are frozen together. Runtime code
uses the integer constant and retains the seed beside it for review; it does
not call PostgreSQL `hashtext`, Python `hash`, or a locale-dependent function.
The lock is database-local and reserves this key for Empire's tech-indicators
writer only.

The nonblocking `pg_try_advisory_xact_lock` call is the only V1 acquisition
mode. There is no lock table, lease clock, fencing counter, retry loop,
scope-overlap graph, or manual stale-lock cleanup.

## Why The Lock Is Transaction-Level

Empire's live local and Airflow database endpoint uses PgBouncer transaction
pooling. A session-level advisory lock could remain attached to a pooled
PostgreSQL server session after the client transaction ends and must not be
used.

The package instead opens a dedicated lock connection, explicitly begins one
`READ COMMITTED` transaction, and acquires the transaction advisory lock. The
open transaction pins one PgBouncer server connection until terminal commit,
rollback, or connection loss. Calculation and staged payload batches use
separate caller-owned connections, so their commits do not release the lock.

The lock connection performs no payload or publication mutation before final
publication. For a publishing run, the P0.9 terminal revalidation and atomic
payload/membership/publication change execute on this same lock connection,
then `COMMIT` publishes the unit and releases the lock together. Code must not
transfer the lock between connections or release it immediately before the
terminal transaction.

Holding one pooled server connection for the run is an accepted V1 resource
cost. Only one tech-indicators writer can do so. J9.9 must prove the configured
database path permits a transaction to remain open for the longest supported
workflow and must emit the existing 30-second workflow heartbeat on the lock
connection with a trivial statement. A failed heartbeat means the lock is
lost; it is not silently reacquired.

## Conflict And Scope Rules

All of these workflow kinds acquire the same key and therefore conflict:

- daily append, recent correction, and healthy no-op;
- historical backfill, resume, and initial cohort load;
- calculation-version rebuild;
- subject or SPX correction;
- eligibility removal and inactive-payload cleanup;
- failed/prepared publication recovery; and
- dry-run planning through any mutating runner entry point.

Provider, market, listing, date, job kind, resume position, and calculation
version never partition the V1 lock. Two disjoint listing backfills conflict;
different versions conflict; a daily run conflicts with a backfill; and a
cleanup conflicts with calculation. This conservative rule is intentional and
prevents two jobs from choosing or changing the same inactive slot without an
overlap solver.

Read-only config checks, inspection, coverage queries, readiness/model-input
reads, and report viewing do not acquire the writer lock. They rely on P0.9's
published view and one-snapshot readiness contract and must not mutate or
recover state as a side effect.

## Scope Normalization

Scope is normalized for publication identity, Core subject facts, reporting,
resume validation, and idempotency, but not to calculate lock conflicts. The
global writer key is acquired before readiness, scope resolution, or planning.

After acquisition, a concrete scope is represented as canonical JSON with:

- schema version `1` and exact workflow kind;
- calculation version as validated uppercase text;
- resolved provider-listing UUIDs in lowercase canonical form, deduplicated
  and sorted by UUID text;
- daily effective date or inclusive start/end dates in ISO `YYYY-MM-DD` form;
- explicit inactive-listing opt-in and rebuild/dry-run booleans; and
- null rather than an omitted key where a field does not apply.

Provider/market/ticker selectors are safe input facts, not the resolved write
identity. Resolution must produce the concrete listing UUID set before a
publication is prepared. Canonical JSON uses UTF-8, sorted object keys, compact
separators, JSON booleans/null, and no timestamps, secrets, environment data,
or resume cursor. The normalized scope hash is lowercase SHA-256 hex of those
bytes. Later daily/backfill scope tasks may add validated fields by advancing
the scope schema version; they may not make lock conflicts narrower in V1.

An empty or no-op scope still retains the writer lock through its final
decision and report/Core completion. A resume request must match its prepared
publication's normalized scope hash, calculation version, and immutable source
facts; the cursor alone cannot redefine scope.

## Acquisition And Contention

The package attempts the lock before starting a Core run, creating a
publication row, rendering reports, or writing payload. Outcomes are bounded:

```text
ACQUIRED   continue the workflow
CONTENDED  stop immediately without workflow state
LOST       abort an already-started workflow and fail closed
```

Contention waits zero seconds: one nonblocking database call returns
`CONTENDED`. The package does not sleep or retry internally. Contention creates
no Core run, report object, publication, membership, payload, recurrence, or
resume record and is not a healthy no-op. This keeps an operator's accidental
second invocation from polluting operational or feature data.

The reusable contention exception/result contains only the outcome, frozen
lock name, and a safe message. It does not expose connection strings, backend
PIDs, SQL, scope UUID lists, or the current owner's Core parameters. The CLI
maps contention to compact stderr and temporary-failure exit code `75`.
Airflow may apply its own bounded task retry policy, but the package performs a
fresh single attempt on each invocation and never waits inside a worker.

## Lock Lifetime And Terminal Paths

The acquired lock is held from before all readiness/planning until exactly one
terminal path:

| Terminal path | Required lock-connection action |
|---|---|
| published unit | terminal P0.9 transaction commits, publishing and releasing together |
| healthy no-op | finish durable reports/Core success, then commit or roll back the otherwise empty lock transaction |
| dry run | return bounded results, then roll back the lock transaction |
| validation/calculation/report/Core failure | make candidate/Core failure durable on separate owned connections, then roll back the lock transaction |
| cancellation | roll back active work and the lock transaction in `finally` |
| process, network, or database-session loss | PostgreSQL rolls back and releases the transaction lock automatically |

The package holds the lock while it records failure facts that could affect
resume/recovery. After release, it performs no feature/publication/cleanup
write for that workflow. Connection close is a fallback, not the normal
release API. Code never calls `pg_advisory_unlock` for this transaction lock.

The lock handle owns its connection and transaction. It is single-use,
non-copyable, and not accepted as a generic query connection by calculation or
reporting services. Every exit path uses structured cleanup so cancellation,
`BaseException`, and ordinary errors cannot skip rollback/close.

## Loss And Recovery

A successful lock heartbeat proves only that the dedicated transaction is
still usable. If the lock connection closes, becomes aborted, or fails its
heartbeat, the runner stops scheduling work immediately. It must not continue
staging, finalize through another connection, or reacquire and pretend the
same execution remained exclusive.

Already committed inactive-slot batches stay unpublished under P0.9. The
runner safely fails the Core/publication state when it still can; otherwise a
later recovery run does so. The recovery run starts from a new invocation,
acquires the same global lock, inspects durable Core/publication/batch facts,
and either resumes the exact normalized candidate or abandons/fails it. It
never trusts the absence of an advisory lock as proof that a candidate is
complete.

PostgreSQL automatically releases the transaction lock on commit, rollback,
backend termination, database restart, or client-session loss, so there is no
stale lock to delete. An operator may inspect `pg_locks` and `pg_stat_activity`
with bounded safe tooling. Force-terminating the identified backend is an
exceptional cancellation that rolls back the lock transaction; operators do
not unlock arbitrary numeric keys or edit publication membership to recover.

## Airflow And CLI Boundary

Airflow retains `max_active_runs=1` as a secondary guard, initially with
`schedule=None`, but manual runs, CLI calls, reruns, and future trigger paths
all call the same package lock. Airflow pools or scheduler settings never
replace it.

CLI wrappers load the environment and construct the dedicated lock connection.
Reusable package code reads `os.environ` only through Empire configuration and
does not load `.env` files. The lock uses the same configured Empire database
endpoint as ordinary services; no direct-PostgreSQL bypass or second password
is introduced.

## Required Contract Tests

J9.9 and later integration tasks must cover at least:

1. exact frozen seed/key derivation and absence of Python/PostgreSQL runtime
   hashing;
2. two database connections proving exactly one acquisition succeeds;
3. daily/backfill, different-version, disjoint-listing, correction, cleanup,
   resume, no-op, and dry-run calls all conflicting on the same key;
4. read-only inspection/readiness proceeding while the writer lock is held;
5. immediate `CONTENDED`, exit code `75`, and zero Core/report/publication/
   payload state;
6. the dedicated transaction retaining the lock across commits on separate
   work connections through PgBouncer transaction pooling;
7. terminal publication on the lock connection with commit releasing both the
   data change and lock;
8. rollback, ordinary exception, cancellation, and connection loss releasing
   the lock;
9. lock-heartbeat failure stopping work without silent reacquisition;
10. recovery reacquiring the global lock and validating exact durable scope
    before resume or abandonment;
11. canonical scope JSON/hash equivalence under reordered or duplicate input
    selectors and inequality for material scope changes; and
12. secret-safe contention/report/Core/CLI/Airflow surfaces with no backend PID
    or connection detail leakage.
