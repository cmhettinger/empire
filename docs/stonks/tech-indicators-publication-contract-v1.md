# Tech-Indicators Publication Contract V1

Status: frozen implementation contract for P0.9, amended by P0.10 on 2026-08-09.

This document freezes V1 atomic publication units, physical visibility,
readiness, failure, recovery, and rollback behavior. It extends the
[`tech-indicators-spx-contract-v1.md`](tech-indicators-spx-contract-v1.md),
[`tech-indicators-recalculation-contract-v1.md`](tech-indicators-recalculation-contract-v1.md),
and
[`tech-indicators-performance-release-gates-v1.md`](tech-indicators-performance-release-gates-v1.md).

Lock identity, lifetime, contention, and recovery are frozen in
[`tech-indicators-concurrency-contract-v1.md`](tech-indicators-concurrency-contract-v1.md).
S2.1-S2.3 own exact DDL types, constraints, indexes, grants, and view SQL
without changing this mechanism.

S2.2 freezes the auxiliary columns, lifecycle vocabulary, normalized
membership facts, recurrence-state rejection, benchmark-contract identity,
and slot-selecting view SQL in
[`tech-indicators-publication-schema-v1.md`](tech-indicators-publication-schema-v1.md).

## Selected Hybrid Mechanism

V1 uses two bounded physical payload slots and one published consumer view:

```text
stonks.ohlcv_daily_tech_indicators_a       physical 90-column payload table
stonks.ohlcv_daily_tech_indicators_b       physical 90-column payload table
stonks.tech_indicators_publication         publication lifecycle and scope
stonks.tech_indicators_publication_listing per-listing slot membership
stonks.ohlcv_daily_tech_indicators         published 90-column consumer view
```

The `a` and `b` tables have the exact P0.3 feature profile, including generated
columns, source ownership, benchmark lineage, and optional Core run lineage.
Each has primary key `(provider_listing_id, trading_date)`. The view exposes
the same 90 columns and at most one logical row per natural key. It is not a
normal write target.

For each provider listing, exactly one active publication membership may select
slot `A`, slot `B`, or logical removal. The view unions only rows from the
selected slot for active `PUBLISHED` memberships. A `BUILDING` or `PREPARED`
publication and every inactive slot row are invisible. Package writers operate
on slots; model/report/feature consumers use the view through readiness-aware
package queries.

This is not append-only technical revision history. Each listing has at most
two physical payload copies, inactive payload is replaced when that slot is
reused, and durable publication records retain bounded operational facts rather
than old feature values. The design provides one inactive build target without
unbounded generations or a multi-million-row commit.

## Publication Records And Membership

One `tech_indicators_publication` row owns a candidate unit. Its exact DDL is
deferred to S2.2-S2.3, but it must identify and constrain at least:

- publication UUID, kind, status, calculation version, normalized scope hash,
  effective/start/end dates, and creation/preparation/publication timestamps;
- Core run ID with cleanup-safe nullable lineage;
- resolved SPX provider-listing ID and benchmark-contract identity when the
  unit contains supported subjects;
- expected listing, source-row, payload-row, insert/update/delete/equivalent,
  and warning/failure counts;
- JSON/PDF report object IDs as cleanup-safe operational evidence; and
- source/readiness facts needed for final revalidation without storing feature
  payloads or complete listing lists in JSON.

Statuses follow this one-way state machine:

```text
BUILDING -> PREPARED -> PUBLISHED -> RETIRED
    |           |
    +----------> FAILED
    +----------> ABANDONED
```

`PUBLISHED` cannot transition to `FAILED` or `ABANDONED`. It may become
`RETIRED` only after no active listing membership references it. Cleanup of a
Core run or report object does not unpublish correct feature data.

`tech_indicators_publication_listing` is normalized membership, not an
unbounded JSON field. One row per `(publication_id, provider_listing_id)`
records:

- action `PRESENT` with target slot `A` or `B`, or action `REMOVE` with no slot;
- calculation version, source coverage bounds/count, payload count, resolved
  benchmark identity/null shape, and deterministic completion facts; and
- whether this is the one active membership for that provider listing.

A partial unique constraint permits at most one active membership per provider
listing. An active `PRESENT` membership must reference a `PUBLISHED`
publication and a complete target-slot image. An active `REMOVE` membership
suppresses older payload without pretending a null-valued feature row exists.
The finalizer changes old and new membership activity in the same transaction.

## Active And Inactive Slot Rules

The active slot is defined per provider listing, not globally. Different
listings may use different slots. This permits a bounded cohort or listing
rebuild without copying unrelated histories.

For an in-place unit, candidate changes remain in memory or transaction-local
staging until the terminal transaction updates the listing's currently active
slot. Readers see the prior committed rows before that commit and all new rows
after it. This path is allowed only when P0.8's 25,000-feature-row and
60-second transaction gates pass.

For a staged unit, the package chooses the slot opposite each listing's active
slot. If no publication exists, it chooses a deterministic initial slot. In
bounded commits it replaces only that listing's inactive payload with a
complete candidate image:

```text
currently published rows that remain valid
+ newly calculated or corrected rows
- source-deleted or policy-removed rows
= complete candidate state for that listing and publication coverage
```

Copying an unchanged row between slots preserves its source values, analytical
values, null mask, calculation version, benchmark ID, `run_id`, and timestamps.
It is not counted as a recalculation or last-write update. Recalculated rows use
the candidate run lineage and timestamps.

Committed inactive-slot batches are resumable but unpublished. The package
must not stage into a slot currently active for the same listing. The global
P0.10 writer lock prevents another job from choosing or mutating any target
payload concurrently.

## Atomic Publication Units

A publication unit is the exact normalized listing set, date/coverage request,
calculation version, and benchmark contract closed over all P0.7 dependencies.
It is not a provider request, database batch, Airflow task, or report section.
Filtering creates a scoped unit and cannot claim broader readiness.

### Daily Refresh

The daily unit contains the exact active P0.6-eligible listing set selected for
one effective date, including every P0.7 correction dependency and the resolved
SPX prerequisite for supported subjects. The listing set is frozen during
planning and re-resolved at finalization.

At no more than 25,000 feature writes and within the 60-second bound, daily
publication uses one in-place terminal transaction across the whole unit. It
upserts/deletes payload rows, activates new memberships, and marks the
publication `PUBLISHED` together. A filtered daily run publishes only its exact
scope. A complete-universe readiness query remains false unless all listings
required by that broader scope are independently current and compatible.

If the daily dependency closure exceeds a transaction or resource bound, it is
reclassified as a staged backfill-class unit. The writer does not split one
effective-date publication into visible subtransactions.

### Subject Or SPX Correction

The correction unit is the complete P0.7 affected-listing/date closure. A
recent correction may use the in-place path only when the entire closure meets
daily transaction bounds. An older subject correction, benchmark correction,
or deletion with a larger closure rebuilds complete candidate images in
inactive slots and flips every affected membership together.

An SPX-driven unit includes the benchmark's own base-feature correction and
all affected supported-subject SPX fields. It cannot publish provider or market
subsets that omit a supported subject in its computed dependency closure.

### Calculation-Version Rebuild

A semantic calculation-version change always uses inactive slots. Every
selected listing's complete published/source coverage is rebuilt under one
target version before any pointer changes. The unit publishes all selected
memberships together, so an individual listing never exposes mixed versions.

A scoped version rollout may coexist with older-version listings outside its
declared scope, but only the scoped readiness predicate may pass. Global target-
version readiness remains false until the complete global scope is published.

### Historical Backfill

Every backfill uses inactive slots and bounded resumable commits. For each
selected listing, the candidate image combines previously published rows that
remain in scope with the requested new/recalculated coverage. A date-bounded
backfill must not discard published rows outside its requested dates.

No batch, resume cursor, provider/market cohort, or partially completed listing
is model-ready. The exact requested backfill unit flips only after every
listing image, count, version, benchmark fact, report, and final source check
passes. Initial rollout may publish the deliberate cohort units defined by
P0.8, but a cohort publication is never labeled full-universe ready.

### Eligibility Removal, No-Op, And Dry Run

P0.6 eligibility loss publishes an active `REMOVE` membership atomically. The
logical current view stops exposing the listing; inactive physical payload may
be cleaned or overwritten later without touching source data.

A healthy no-op creates durable run reports referring to the existing
publication/readiness token but does not create a new published feature unit or
change payload timestamps. A dry run never writes payload, membership, or
publication state and cannot create readiness.

## Candidate Validation

Before a publication becomes `PREPARED`, the package validates its complete
unit, not just the last batch:

- the normalized listing set and source keys equal the requested P0.6/P0.7
  scope, with no missing, extra, or duplicate logical rows;
- copied OHLCV agrees exactly and null-safely with current source rows;
- history counts, calculation version, source coverage, and generated values
  are complete and internally consistent;
- every analytical null/value matches the formula and recalculation contracts;
- the exact active SPX identity is resolved where required, daily benchmark
  coverage is ready, and supported/unsupported row shape matches P0.5;
- candidate row and membership counts reconcile with inserted, updated,
  removed, copied-equivalent, and total counts;
- every inactive target slot contains a complete candidate image for the
  listing, including preserved out-of-range published rows; and
- JSON and PDF bytes render within P0.8 bounds and their facts match the
  candidate publication ID, scope, counts, version, and benchmark.

Expected warm-up nulls do not make a unit incomplete. Unexpected nulls,
non-finite output, missing benchmark semantics, or an unexplained count
difference prevent `PREPARED`.

## Terminal Finalization Sequence

The normal workflow order is fixed:

1. acquire P0.10's global writer lock and create a `BUILDING` publication;
2. plan, calculate, validate, and either retain bounded in-place changes or
   commit resumable inactive-slot batches;
3. render and durably store the candidate's final JSON/PDF report pair;
4. mark the publication `PREPARED` with exact report IDs and counts;
5. complete the Core run successfully with that prepared publication ID; and
6. as the terminal operation, execute one PostgreSQL transaction that
   revalidates the lock, Core success, report existence, source/scope/version/
   benchmark facts and candidate counts, applies bounded in-place changes when
   applicable, switches all memberships, marks `PUBLISHED`, and commits.

The package makes no commit-owning service call after step 6. Returning the
already-constructed compact result is not a durability step. This ordering
matches live Core behavior, whose run and object repositories commit their own
transactions, while ensuring model-visible data changes only in the final
database commit.

If step 6 fails, its payload and membership changes roll back together. The
publication becomes `FAILED`, and the already-succeeded Core run is corrected
to failed with a safe finalization summary. Candidate report objects remain
bounded failed-run evidence and do not make data visible.

## Crash Recovery

Recovery is deterministic and lock-protected:

| Crash point | Visible state | Recovery |
|---|---|---|
| before a prepared candidate | prior publication only | fail/abandon the run and clean or resume bounded inactive payload |
| after `PREPARED`, before Core success | prior publication only | revalidate and resume, or mark failed/abandoned |
| after Core success, before terminal commit | prior publication only | reacquire the same lock, revalidate the prepared candidate, then publish or mark it/Core failed |
| after terminal commit, before caller response | complete new publication | return/inspect the already-published result; never replay the unit as new work |

`BUILDING` and `PREPARED` records never satisfy readiness. Stale inactive-slot
payload is harmless until explicitly selected by a later prepared publication.
Cleanup may remove failed/abandoned membership and inactive payload only after
proving it is not active for that listing.

## Readiness Predicate And Consumer Snapshot

Readiness is evaluated for an exact requested listing/date scope, effective
date, calculation version, and benchmark expectation. `PUBLISHED` alone is
necessary but not sufficient. A request is ready only when all of these hold in
one database snapshot:

1. the current P0.6/status selector resolves the expected listing set, and
   every required listing has exactly one active membership;
2. each membership is `PRESENT`, references a `PUBLISHED` publication, exposes
   a complete slot image for the requested coverage, and has the requested
   calculation version;
3. logical view keys/counts match current selected source keys/counts, copied
   OHLCV and history counts agree, and there are no extra or missing rows;
4. all participating publications use one compatible formula profile and, for
   supported subjects, the same currently resolved SPX identity/contract;
5. daily scopes have the exact-date SPX bar required by P0.5 and upstream
   source readiness required by I3.6;
6. benchmark IDs and all 11 SPX fields have the required supported/unsupported,
   alignment, warm-up, and denominator shape; and
7. the request's effective date/range is inside published coverage, with no
   failed, removed, building, or stale candidate substituted for a required
   listing.

An exact filtered scope may be ready while a broader scope is not. Active
memberships may originate from different atomic publications only when their
versions, benchmark contract, source state, and requested coverage are mutually
compatible. A no-op returns the existing compatible publication set.

Readiness and model-input rows must be read in one package-owned, read-only
`REPEATABLE READ` transaction. The service first returns a deterministic token
derived from the sorted active `(provider_listing_id, publication_id, slot)`
set plus scope/version/benchmark/effective-date facts, then reads the published
view in the same snapshot. A token is not reusable in a later transaction.

The published view prevents staged or slot-mixed visibility, but a bare view
query is not itself a readiness claim because upstream OHLCV can change after
publication. Consumers must use the readiness-aware package query. If source
changes before the snapshot, readiness fails closed; if it commits after the
snapshot, PostgreSQL MVCC keeps both readiness and feature rows on the same
prior complete snapshot.

Bounded failure reasons include:

```text
NO_ACTIVE_PUBLICATION
SCOPE_MISMATCH
COVERAGE_INCOMPLETE
VERSION_MISMATCH
SOURCE_DRIFT
PUBLICATION_NOT_READY
BENCHMARK_UNAVAILABLE
BENCHMARK_MISMATCH
SPX_COVERAGE_INCOMPLETE
```

These are diagnostics, not sentinel feature values. A failure returns no model
rows and does not fall back to an older incompatible version or proxy benchmark.

## Rollback And Cleanup

A failed in-place terminal transaction leaves the prior publication unchanged.
After a successful in-place publication, V1 does not retain overwritten feature
revisions; correcting it means a new publication rebuilt from current source,
not a hidden database rollback to obsolete provider values.

A staged publication leaves the former payload in the opposite slot. It may be
reactivated only through a new validated publication proving that its source,
version, scope, and benchmark still satisfy readiness. Otherwise rollback is a
fresh rebuild. The old inactive payload remains until that slot is safely
reused or explicitly cleaned; it is not permanent revision history.

Publication records and bounded membership facts may remain as operational
history after payload reuse. Core run cleanup sets nullable lineage to null and
does not remove published features. Report cleanup removes evidence but does
not retroactively invalidate a publication that verified it at finalization.

## Required Contract Tests

Implementation tests must cover at least:

1. view visibility with listings independently active in slots A and B;
2. in-place daily success, rollback, no-op, and the 25,000-row/60-second
   fallback to staging;
3. bounded staged backfill with resume and zero visibility before one pointer
   flip;
4. subject and SPX corrections on both in-place and staged paths;
5. version rebuild with no mixed-version listing and scoped/global readiness;
6. eligibility `REMOVE`, source cascade, inactive listing, and preserved source
   data;
7. every publication state transition and rejection of active membership to a
   non-published or incomplete candidate;
8. failure at every finalization step plus all four crash-recovery windows;
9. source/benchmark change between preparation and finalization;
10. report storage or Core completion failure preventing publication;
11. final-commit success followed by caller failure without duplicate replay;
12. readiness failure for every bounded reason and zero returned model rows;
13. one-snapshot token/data consistency under concurrent source/publication
    commits;
14. slot reuse/cleanup without touching active payload; and
15. P0.8 transaction, disk, plan, latency, report, and rollout gates.
