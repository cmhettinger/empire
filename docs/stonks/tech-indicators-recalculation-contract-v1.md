# Tech-Indicators Recalculation Contract V1

Status: frozen implementation contract for P0.7 as of 2026-08-09.

This document defines how V1 plans work after daily appends, missing technical
rows, subject-source corrections, SPX corrections, calculation-version
changes, listing-status changes, and deletions. It extends the
[`tech-indicators-formula-spec-v1.md`](tech-indicators-formula-spec-v1.md),
[`tech-indicators-spx-contract-v1.md`](tech-indicators-spx-contract-v1.md), and
[`tech-indicators-source-value-policy-v1.md`](tech-indicators-source-value-policy-v1.md).

P0.9 still owns atomic publication and P0.10 owns concurrency. B1.2 may choose
full replay, bounded replay with proven state, or a recurrence-state table. It
may optimize input reads and calculation, but it may not narrow the output
that this contract says is potentially affected without proving equivalence to
the full-series reference.

## Full-Series Reference And Equivalence

For one provider listing and cutoff, the authoritative reference calculation
uses every current `ohlcv_daily` observation for that listing from its earliest
stored date through the cutoff, in ascending `trading_date` order. For an
SPX-supported subject it also uses the complete current benchmark sequence
required by the SPX contract. It applies one requested calculation version.

An accepted incremental result must equal a fresh reference rebuild:

- identifiers, dates, source copies, observation counts, calculation version,
  benchmark identity, and null masks compare exactly;
- finite derived values use P0.4's absolute `1e-12` and relative `1e-10`
  equivalence tolerance; and
- generated columns must agree with their current persisted inputs.

This is output equivalence, not a requirement to rewrite every evaluated row.
An equivalent persisted row is unchanged. Its `run_id`, `calculated_at`, and
`updated_at` remain unchanged. A row is written only when its exact fields,
null mask, or finite derived values are not equivalent to the reference.

## Work Range And Input Context

The planner distinguishes two ranges:

```text
write range = rows whose persisted output may need insertion, update, or delete
input context = earlier source/benchmark observations needed to calculate them
```

The write range never reads a future observation. Input context normally begins
at the listing's earliest source observation because EMA, RSI, ATR, DI, ADX,
MACD, and streaks are recursive. B1.2 may replace full-prefix reads with proven
state or replay, but the resulting rows must match the full-series reference.

For a listing-local uncertainty at date `d`, the conservative V1 write range is
the complete source-observation suffix from `d` through the safe run horizon.
There is no nominal-period cutoff or stop-after-several-equal-rows heuristic.
A later prototype may avoid unnecessary computation only when it proves that
all recurrence state and every future output remain equivalent.

The safe run horizon is normally the requested effective/end date. If an
earlier change can affect already persisted or published rows after that date,
the planner must expand through those downstream rows or reject the narrowed
scope. It must never knowingly leave a stale tail behind a successful result.
Work exceeding the ordinary daily envelope follows the backfill-class gates in
[`tech-indicators-performance-release-gates-v1.md`](tech-indicators-performance-release-gates-v1.md)
without weakening this suffix.

## Drift Detection

Planning compares current source and technical state; it does not depend on
unavailable per-bar source-run lineage. The deterministic triggers are:

| Trigger | Detection | Earliest listing-local uncertainty |
|---|---|---|
| `TAIL_APPEND` | eligible source rows exist after the last equivalent technical row | first appended source date |
| `MISSING_TECH_ROW` | a selected source key has no technical row | earliest missing source date |
| `SOURCE_COPY_DRIFT` | copied open, high, low, close, or volume differs null-safely | earliest differing source date |
| `HISTORY_COUNT_DRIFT` | stored observation count differs from the current chronological source count | earliest differing surviving source date |
| `BENCHMARK_DRIFT` | SPX source/technical drift or current exact-date alignment disagrees with persisted SPX output | earliest affected benchmark/subject date |
| `VERSION_DRIFT` | a selected row's calculation version differs from the requested implementation | first source date for that selected listing |
| `SOURCE_VALUE_ELIGIBILITY_REMOVED` | a listing with technical rows no longer satisfies P0.6 | all technical rows for that listing |
| `EXPLICIT_REBUILD` | a validated operator scope requests rebuilding supported current state | first source date in the rebuild unit, subject to downstream expansion |

Source `updated_at` alone is not a correction signal. The OHLCV writer skips
unchanged source values, and technical formulas do not consume OHLCV's
`change`, `changepct`, `typ`, `hl_range`, or `oc_range` convenience columns.
Only current source keys and OHLCV inputs, copied state, counts, versions, and
benchmark semantics determine recalculation.

`MISSING_TECH_ROW` invalidates a suffix even when the immediate cause might be
an accidentally deleted output row. Current state cannot distinguish that case
from a late source insertion, which shifts observation indexes and recurrence
state. Conservative suffix rebuilding preserves correctness in both cases.

## Case Semantics

### Daily Append

For an active, source-value-eligible listing whose new source rows are strictly
after its equivalent technical tail, calculate the first new source date
through the effective-date horizon. Read the required prefix or proven state.
Multiple appended observations form one suffix; gaps in calendar dates do not
create work or reset state.

A healthy rerun with no missing row, copied-source drift, count drift, version
drift, or benchmark drift is a no-op. It succeeds without feature writes; run
and report behavior is owned by J9 and R8.

### Missing Technical Row Or Late Source Insertion

The earliest selected source row without a technical row starts a suffix
rebuild. This recreates the missing row and recalculates every downstream row
through the safe horizon. An insertion before existing source observations can
change history counts, lagged windows, streaks, recursive state, and SPX
alignment; it is not treated as an isolated insert.

### Subject-Source Correction

An exact null-safe difference in copied OHLCV at date `d` starts that subject's
suffix rebuild at `d`. This applies even when only volume changed: V1 uses one
simple row-level invalidation range rather than feature-family-specific tails.
Provider corrections never mutate another provider listing.

If a source observation is inserted or deleted, the chronological count drift
on the next surviving observation also identifies the changed suffix. A source
row deleted at the end of a series has no surviving downstream output to
recalculate; its matching technical row is removed by the source FK cascade.

### SPX Source Correction

An SPX insert, OHLCV correction, or deletion has two independent effects:

1. SPX's own non-relative technical row follows the ordinary listing-local
   suffix rule. SPX itself remains an unsupported SPX-relative subject.
2. Every P0.5-supported subject with affected persisted coverage recalculates
   its SPX-family rows from the earliest affected subject date through the safe
   horizon. Active selected subjects also create any missing rows in that
   range. Unsupported subjects are not touched by benchmark drift.

The initial implementation uses a conservative supported-subject suffix. It
does not attempt to stop after the largest 252-aligned-return window. Exact
alignment can gain or lose an observation, and current state has no append-only
benchmark revision from which to infer a safe smaller range.

A deleted SPX bar cascades its own technical row. The planner detects remaining
impact from SPX observation-count drift on the next surviving benchmark row and
from supported subject rows whose current-date alignment/output no longer
matches the current benchmark date set. A deleted final benchmark date with
previously populated subject output is therefore still invalidated.

Benchmark correction maintenance includes inactive supported listings that
already have technical rows in the affected coverage; otherwise retained
historical rows would silently preserve stale SPX values. It does not append
new inactive coverage unless the operator explicitly selects that listing.

If the P0.5 benchmark resolver is missing, duplicate, inactive, or drifted, a
scope containing supported subjects fails before calculation or publication.
The package does not null old fields, guess a replacement, or publish partial
correction work. After benchmark identity is healthy again, supported subject
coverage requires a benchmark-driven rebuild before readiness can pass.

### Calculation-Version Change

Calculation versions identify immutable formula semantics. When the requested
version differs from any selected persisted row, rebuild that listing from its
first source observation through the safe horizon. A version change is never a
suffix beginning at the first mismatched row because the new implementation
may change warm-up, recursive initialization, null masks, or every output.

One current-state row cannot represent two versions. P0.9 must keep the old
complete publication visible until the new rebuild unit is complete. A code
fix proven not to change accepted output retains the existing version and
should converge as an idempotent no-op.

### Active And Inactive Listings

Source-value eligibility and operational status remain separate:

- Default daily and broad backfill selection includes only `ACTIVE`, P0.6-
  eligible listings.
- An exact inactive listing may be backfilled or rebuilt only through an
  explicit listing scope with an explicit inactive opt-in. Broad
  `include_inactive` selection is not a default.
- Changing `ACTIVE` to `INACTIVE` does not delete source or technical history
  and does not by itself recalculate it. Normal append stops.
- Drift maintenance may update an inactive listing only inside its already
  persisted technical coverage. It does not extend the tail.
- Changing back to `ACTIVE` lets ordinary missing/drift detection rebuild from
  the earliest uncertainty and fill the tail.
- A version rebuild does not silently include inactive listings. Old-version
  inactive rows remain outside a new active publication until explicitly
  rebuilt.

If a listing ceases to satisfy P0.6's semantic predicate, status does not make
it eligible. Its derived technical rows are removed as one atomic cleanup unit;
source listings and bars remain untouched. If it later becomes eligible again,
an active or explicitly opted-in inactive scope performs a full rebuild.

## Deletion Behavior

| Deleted object | Required behavior |
|---|---|
| one `ohlcv_daily` source row | its same-date technical row cascades; rebuild the surviving subject suffix beginning at the earliest detected uncertainty |
| one non-benchmark technical row | treat as `MISSING_TECH_ROW` and rebuild the selected suffix |
| a non-benchmark `provider_listing` | owned source bars and technical rows cascade; no orphan or compensating technical write |
| a P0.6 eligibility fact | delete only derived technical rows atomically; never delete the listing or source bars |
| a Core run | technical `run_id` becomes null through `ON DELETE SET NULL`; feature rows and values remain |
| the SPX listing or unhealthy benchmark identity | supported-subject work fails closed; no proxy, partial publication, or automatic subject-row deletion |

The tech-indicators package never deletes or updates `ohlcv_daily` or
`provider_listing`. Direct deletion of technical rows is not a correction
workflow; normal planning restores selected missing rows from source state.

## Planning, Persistence, And Publication Boundary

The planner emits deterministic listing/date work ordered by provider code,
market, ticker, listing UUID, and date. Overlapping reasons collapse to the
earliest required start and one suffix per listing. Benchmark propagation is a
separate bounded reason/count so reports can distinguish subject-source from
SPX-driven work.

Calculation and validation complete before the caller-owned persistence unit
is committed. Inserted, updated, deleted, equivalent/unchanged, and reason
counts are reported without retaining unbounded row payloads. Resumable
backfills may use deterministic batches, but P0.9 decides when those batches
become visible as one complete publication. P0.10 decides lock overlap; neither
Airflow timing nor separate provider jobs can weaken this recalculation logic.

## Required Contract Tests

Implementation tests must cover at least:

1. tail append and an unchanged rerun;
2. missing first, middle, and final technical rows;
3. historical source insertion, OHLCV correction, volume-only correction, and
   first/middle/final source deletion;
4. calendar gaps proving observation-based suffixes;
5. SPX insert, correction, first/middle/final deletion, subject nonalignment,
   and provider isolation;
6. full rebuild versus append, missing-row, source-correction, and SPX-
   correction results under P0.4 tolerance;
7. version drift forcing a full selected-listing rebuild with exact null masks;
8. active-to-inactive retention, bounded inactive maintenance, explicit
   inactive rebuild, and reactivation catch-up;
9. P0.6 eligibility loss deleting only derived rows;
10. Core-run cleanup nulling lineage without changing features;
11. unsafe narrowed horizons expanding or failing rather than leaving a stale
    tail; and
12. deterministic reason collapse, ordering, bounded diagnostics, idempotent
    no-change persistence, and no source mutation.
