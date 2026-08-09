# Tech-Indicators Performance And Release Gates V1

Status: frozen implementation contract for P0.8, amended by P0.9-P0.10 on 2026-08-09.

This document sets the representative sizes, performance targets, resource
bounds, query-plan expectations, report limits, and staged release criteria for
V1. It extends the
[`technical-indicators-design-contract.md`](technical-indicators-design-contract.md)
and the frozen feature, formula, SPX, source-value, and recalculation contracts.

Correctness, isolation, bounded resources, and atomic visibility are hard
gates. Timing targets are release gates on the local Empire runtime described
below. A missed target requires measurement and tuning or an explicit contract
revision with evidence; it must not be relabeled healthy. The atomic
publication mechanism is frozen in
[`tech-indicators-publication-contract-v1.md`](tech-indicators-publication-contract-v1.md),
and the deliberately serialized writer lock is frozen in
[`tech-indicators-concurrency-contract-v1.md`](tech-indicators-concurrency-contract-v1.md).

## Measured Planning Baseline

Read-only queries on 2026-08-09 applied P0.6's exact eligibility predicate to
the live PostgreSQL database. Source coverage was current through 2026-08-03.
These figures are planning evidence, not invariants for future runs.

| Measure | Observed value |
|---|---:|
| Active eligible provider listings | 22,261 |
| Active eligible listings with at least one bar | 21,817 |
| Eligible bars | 20,584,282 |
| EODData eligible bars | 93,049 |
| Stooq eligible bars | 20,475,736 |
| Yahoo SPX bars | 15,497 |
| Series-length minimum / median | 0 / 8 |
| Series-length p95 / p99 | 5,380 / 8,726 |
| Largest series | 16,238 |
| Latest EODData-plus-SPX slice | 11,743 rows on 2026-08-03 |
| Largest eligible date slice since 2025-01-01 | 20,284 rows |
| Eligible dates since 2025-01-01 | 399 |
| Mean / p95 eligible rows per such date | 7,187.29 / 8,235.1 |

The current `ohlcv_daily` table is 2,896 MB of heap, 2,517 MB of indexes, and
5,414 MB total. The local PostgreSQL 18.4 container reports 128 MB
`shared_buffers`, 4 MB `work_mem`, and 64 MB `maintenance_work_mem`. The host
had 496 GiB available on the data volume. The technical table does not yet
exist, so its row width, indexes, and actual size must be measured by W7.9
rather than presented here as observed facts.

Completed OHLCV run evidence provides useful lower-layer comparisons:

- V10.9 imported 20,475,736 Stooq bars in 4:41:30.9 using 410 chunks no larger
  than 50,000 rows, averaging about 1,212 accepted rows/second.
- V10.11 read and recomputed invariants for all 20,671,779 OHLCV rows with zero
  discrepancies.
- Existing durable OHLCV reports have observed maximum sizes of 911,635 bytes
  for JSON and 220,281 bytes for PDF.

Technical rows are substantially wider than OHLCV rows, and calculation adds
TA-Lib, validation, SPX alignment, and publication work. The gates below do not
assume the OHLCV import rate is directly achievable.

## Representative Workloads

Every performance task must exercise these named sizes. Smaller fixtures alone
cannot satisfy a release gate.

| Workload | Representative bound |
|---|---:|
| Short/warm-up listing | 8 source observations |
| P95 listing | at least 5,380 observations |
| P99 listing | at least 8,726 observations |
| Maximum-history listing | at least 16,238 observations; test envelope 20,000 |
| Ordinary daily/recent-correction slice | up to 25,000 output rows |
| Bounded backfill pilot | 100 deterministic listings and no more than 1,000,000 rows |
| Provider/market cohort | one exact P0.6 provider/market partition |
| Full initial rebuild | current eligible universe, initially 20,584,282 rows |

Synthetic data may reach an envelope, but at least one database benchmark must
use real provider-native row shapes and observed history distributions. Tests
must include null Yahoo volume, calendar gaps, zero volume, short histories,
and SPX-supported plus unsupported subjects.

An old subject or SPX correction whose conservative P0.7 suffix exceeds 25,000
rows is a backfill-class workload. It is still correct and resumable, but it is
not held to the ordinary daily latency target.

## Timing And Memory Gates

Measure wall-clock time from validated scope/readiness planning through report
bytes, including database reads, calculation, validation, persistence or
staging, publication, and summary queries. Provider acquisition is upstream
and excluded. Measure peak resident set size for the tech-indicators process or
Airflow task container. Record database and host/container versions with every
published benchmark.

| Workload | Wall-clock target | Peak RSS target |
|---|---:|---:|
| Config/import/readiness smoke | 10 seconds | 256 MiB |
| Full active-universe healthy no-op | 60 seconds | 1 GiB |
| One 20,000-observation listing rebuild | 2 minutes | 512 MiB |
| Ordinary append or recent correction, at most 25,000 rows | 5 minutes | 1 GiB |
| Bounded pilot, at most 1,000,000 rows | 1 hour | 2 GiB |
| Full current-universe rebuild, initially 20,584,282 rows | 24 hours | 2 GiB |
| Daily JSON plus PDF report construction | 30 seconds | 512 MiB |
| Backfill JSON plus PDF report construction | 60 seconds | 512 MiB |

The sustained full-backfill floor is 250 evaluated-and-persisted rows/second
after startup. Inserted, updated, equivalent/unchanged, and deleted work must be
reported separately; a run cannot inflate throughput by counting rows it did
not read and validate. An ordinary daily run must meet both its five-minute
limit and correctness/publication gates even when no-op detection or SPX
alignment dominates its row-write count.

Peak RSS excludes PostgreSQL's separate process memory but includes NumPy,
TA-Lib, report rendering, and Python buffers. Memory must remain bounded by
configured paging and batching rather than scaling with the full universe.

## Read, Calculation, Transaction, And Staging Bounds

- Chronological source reads default to pages of 10,000 rows and may be tuned
  from 1,000 through 50,000. A caller cannot disable paging.
- Calculation holds one subject history at a time plus the bounded SPX history,
  reusable output buffers, and one write batch. It never materializes all
  listing histories or feature rows in memory.
- Persistence defaults to 5,000 feature rows per batch, may be tuned from 1,000
  through 10,000 from W7.9 evidence, and has a hard 25,000-row batch maximum.
- A normal write transaction contains at most 25,000 feature rows and targets
  at most 30 seconds from first write through commit. Sixty seconds is the hard
  representative maximum; exceeding it fails the gate and requires a smaller
  inactive-slot batch or the staged publication path frozen by P0.9.
- Daily publication may update active slots in one transaction only if the
  25,000-row, 60-second, memory, lock, and reader-visibility gates all pass.
  Broad backfills use independently committed inactive-slot batches and one
  bounded membership flip; they cannot hold one transaction for millions of
  rows.
- Every committed or staged batch records a deterministic cursor. Failure
  rolls back the active batch only, and resume does not recalculate or publish
  a previously completed batch as a second logical result.
- Progress and Core heartbeat evidence is emitted at every batch boundary and
  at least once every 30 seconds during calculation without retaining per-row
  history.

P0.9's two payload slots, publication state, and membership are purpose-
specific, constrained, cleanup-safe, and invisible to model-input queries until
atomic publication. Before broad backfill, W7.9 must measure a one-million-row
pilot and project both slots' heap, indexes, WAL, and temporary space. The
projected combined populated payload slots plus indexes must be at most 40 GiB
for the initial universe.
Available disk before a full generation must be at least twice that projected
additional footprint plus 10 GiB of headroom so old and new complete state can
coexist safely when publication requires it.

No implementation may respond to a bound failure by dropping required fields,
weakening P0.7 suffixes, skipping SPX output, disabling validation, exposing
partial rows, or increasing limits without recorded evidence.

## Query-Plan And Latency Gates

S2.4, I3.7, R8.2, and W7.9 must capture `EXPLAIN (ANALYZE, BUFFERS)` on the
representative database after statistics are current. Record actual/planned
rows, loops, buffer hits/reads, sort method and memory, temporary I/O, planning
time, and execution time. Run each latency case five times on an otherwise idle
local stack and report the median and maximum; do not claim a cold-cache result
without actually controlling the cache.

Required plan shapes are:

- Exact listing history uses the technical primary-key/index order with no
  explicit sort, sequential scan of the technical universe, or temporary I/O.
- Latest-date/model-input slices use a date-leading index and read only the
  requested date/publication scope before projecting feature columns.
- Benchmark resolution uses the unique provider identity path and returns one
  reviewed row; it never scans OHLCV history to resolve identity.
- Eligibility and state-comparison queries are set-based and page results.
  They do not issue one query per listing or use a repeated correlated scan of
  the full source/technical tables.
- Full backfill may use a sequential scan or primary-key-order index scan when
  its measured plan is cheaper, but it must stream in deterministic
  listing/date order without an unbounded external sort.
- Coverage/report aggregation may use a parallel sequential scan when the full
  scope genuinely requires it. Narrow listing/date and latest-slice queries may
  not hide a full-table scan behind acceptable wall time.
- A representative 25,000-row ranking selects only needed columns and performs
  no disk-spilled sort under the recorded 4 MB `work_mem` baseline.

Initial local latency targets are:

| Query | Median / maximum |
|---|---:|
| Exact listing history through 20,000 rows | 100 ms / 500 ms |
| Latest-date slice through 25,000 rows | 250 ms / 1 second |
| Latest-date single-feature rank through 25,000 rows | 500 ms / 2 seconds |
| Exact listing/date drift page through 50,000 joined rows | 1 second / 5 seconds |
| Full-scope coverage summary over about 20.6M rows | 10 seconds / 30 seconds |

These are database execution targets, separate from serialization, rendering,
and network/UI time. A query that meets latency by returning an unbounded
feature payload still fails.

## Report Bounds

JSON remains authoritative for complete counts and bounded diagnostics; PDF is
the human-readable companion. Neither format contains full feature rows,
unbounded listing UUIDs, raw SQL plans, environment dumps, or recommendations.

- Complete structured counts are never sampled.
- JSON retains at most 100 diagnostic row/listing samples across the report,
  matching the live OHLCV package's bounded-sample ceiling.
- PDF shows at most 18 listing samples and 10 issue samples per rendered
  section. Additional facts remain counts in both formats.
- `report.json` must be at most 2 MiB and deterministic for the same report
  facts apart from explicitly variable run/timing identities.
- `report.pdf` must be at most 5 MiB and 25 pages. Every required section must
  remain legible; truncating text or omitting a failure to meet the bound is
  prohibited.
- Rendering must meet the timing/RSS table and pass visual inspection for
  success, warning, no-op, failure, resumed backfill, and the largest bounded
  samples.

If a legitimate result exceeds a file/page bound, store complete aggregate
facts and tighten samples or presentation. Do not split one logical report into
unbounded per-listing artifacts or serialize the feature table.

## Staged Release Gates

Progression is ordered. Each stage stores exact scope, versions, timings, peak
RSS, database counts, query plans where applicable, and JSON/PDF report IDs.

1. **Runtime gate:** pinned TA-Lib/NumPy imports and calculations pass in local
   Poetry and the built Airflow image with no dependency or license blocker.
2. **Correctness gate:** unit/golden/property tests prove every formula family,
   warm-up/null behavior, P0.7 append/correction/version equivalence, provider
   isolation, and no source mutation.
3. **Database gate:** Flyway/schema tests, generated expressions, rollback,
   idempotency, cascades, benchmark shape, publication visibility, and query
   plans pass with zero fixture residue.
4. **Single-listing gate:** short, P95, P99, and 20,000-row histories pass the
   timing, RSS, correction, deletion, and full-rebuild-equivalence gates.
5. **Pilot gate:** a deterministic 100-listing, at-most-one-million-row
   unpublished backfill passes batching, resume, report, disk projection, and
   failure recovery before publication.
6. **Daily gate:** a complete at-most-25,000-row effective-date slice passes
   source/SPX readiness, no-op, append, recent correction, atomic visibility,
   query latency, and report bounds.
7. **Cohort gate:** expand separately through Yahoo SPX, each EODData market,
   and each Stooq market. Stop between cohorts to compare reference rebuilds,
   null/warm-up coverage, throughput, table/index growth, and reports.
8. **Full-backfill gate:** run/resume the complete eligible universe only after
   the projected disk and 24-hour/2-GiB gates pass. Audit every row count,
   version, benchmark shape, source copy, and bounded report outcome.
9. **Live-daily gate:** keep the tech-indicators DAG manual initially. At least
   three consecutive ready effective dates plus an unchanged rerun must pass
   within daily targets before A11.8/V12.10 may approve a cadence.

Rollout stops and remains unpublished on any formula/equivalence mismatch,
source mutation, provider leakage, unexpected non-finite output, partial or
mixed-version visibility, incomplete benchmark semantics, lock failure,
unrecoverable resume drift, schema/query-plan regression, report fact mismatch,
disk-headroom failure, or timing/RSS/file-size bound violation. Expected
warm-up nulls and provider-native semantic disclosures are not failures when
their exact counts and reasons match the frozen contracts.

Promotion requires zero unexplained warnings, exact count reconciliation,
durable matching JSON/PDF reports, cleanup-safe Core lineage, and a documented
rollback to the previous complete publication. Enabling or scheduling normal
operation remains an explicit A11.8/V12.10 decision; completing a benchmark or
backfill does not enable it automatically.

## Required Verification Evidence

Later benchmark and rollout tasks must preserve:

- scope and current eligible listing/bar/date distributions;
- calculation, package, Python, TA-Lib, NumPy, PostgreSQL, and Airflow versions;
- wall-clock phase timings, throughput denominators, peak RSS, batch and
  transaction distributions, retries, and resume cursor;
- table/index/WAL/temporary-space measurements and free-disk projection;
- named query plans and five-run latency results;
- inserted, updated, deleted, equivalent/unchanged, warm-up/null, SPX, and
  exclusion counts; and
- matching report object identities, sizes, page count, and visual review.

Evidence contains bounded operational facts only. It must not expose secrets,
environment dumps, raw feature payloads, or complete Core parameter/metadata
documents.
