# Technical-Indicator Representative Performance Gate (V12.6)

Date: 2026-08-29

Decision: pass for the bounded development gate. No measured result justifies
an implementation, index, or configuration change. Production-scale rebuild,
full populated-universe summary/no-op, cohort rollout, and live cadence remain
Phase 13 gates and were not run on the development laptop.

## Runtime And Current Scope

- macOS 26.5.2 arm64 host, Python 3.14.6.
- `empire-stonks-tech-indicators` 0.1.0, TA-Lib 0.7.1, NumPy 2.4.6,
  and Airflow 3.2.1.
- PostgreSQL 18.4 with `shared_buffers=128MB`, `work_mem=4MB`, and
  `maintenance_work_mem=64MB`.
- 22,261 active P0.6-eligible listings, 21,817 with source bars, and
  20,584,282 eligible bars from 1962-01-02 through 2026-08-03.
- The active published technical view had zero rows. Slot A had 8,192 heap
  bytes, 4,620,288 index bytes, zero live tuples, and three estimated dead
  tuples; slot B had zero heap bytes, 581,632 index bytes, and zero live/dead
  tuples.

The source and technical counts came from a repeatable-read, read-only bounded
aggregate. No source or feature values were returned.

## Calculation Envelope

The repeatable aggregate-only
[calculation probe](../../tools/tech-indicators/calculation-performance-benchmark.py)
is repository-owned.
It exercises the actual normalize, assemble, SPX-align, and validate path with
one 20,000-observation EODData subject and an exact-date Yahoo SPX benchmark.
The generated histories contain calendar gaps and nullable benchmark volume.

| Case | Calculated rows | Write suffix | Wall time |
|---|---:|---:|---:|
| Full rebuild | 20,000 | 20,000 | 17.065 s |
| Append | 20,000 | 1 | 17.321 s |
| Source correction at observation 19,500 | 20,000 | 500 | 17.647 s |
| SPX correction at observation 19,500 | 20,000 | 500 | 17.453 s |

The source correction changed all 500 suffix rows. The SPX correction changed
253 suffix rows, consistent with bounded relative-window propagation. Total
probe time was 69.628 seconds and peak RSS was 271.375 MiB. Every case passed
the 120-second single-listing gate and the process passed the 512-MiB gate.

## Pilot, Persistence, And Storage

The existing disposable logged-schema W7.9 harness was rerun against the
current 100 longest eligible provider-native histories. It calculated,
validated, and persisted exactly 1,000,000 rows in 989.238 seconds:

- source reads: 3.713 seconds;
- calculation and validation: 869.603 seconds;
- writes: 96.207 seconds;
- sustained calculation/validation/persistence: 1,035.40 rows/second;
- peak RSS: 412.469 MiB; and
- maximum default 5,000-row transaction: 0.635 seconds.

The throughput exceeds the 250-row/second floor, total time is below one hour,
RSS is below 2 GiB, and transactions are below both the 30-second target and
60-second hard maximum. The current 25,000-row cases measured:

| Case | Total | Median transaction | Maximum transaction |
|---|---:|---:|---:|
| Equivalent upsert, batch 5,000 | 1.997 s | 0.383 s | 0.456 s |
| Correction upsert, batch 5,000 | 2.552 s | 0.515 s | 0.548 s |
| Insert, batch 1,000 | 2.383 s | 0.095 s | 0.100 s |
| Insert, batch 5,000 | 2.507 s | 0.466 s | 0.658 s |
| Insert, batch 10,000 | 2.314 s | 0.920 s | 0.943 s |

The 5,000-row default remains the simplest balanced choice. The million-row
relation used 813,932,544 heap bytes and 121,348,096 index bytes, or
935,526,400 bytes total. It generated 1,222,512,408 WAL bytes. At 935.5264
bytes per row, two current-universe slots project to 35.869 GiB, below the
40-GiB gate. Available disk was 457,730,846,720 bytes versus a required
87,765,975,184 bytes, so the coexistence/headroom gate passed.

## Query And Summary Plans

All cases ran five times without controlled cache reset and make no cold-cache
claim. Required indexes were used and no case performed temporary I/O.

| Query | Rows | Median | Maximum | P0.8 median / maximum |
|---|---:|---:|---:|---:|
| Listing-history keyset page | 1,000 | 0.398 ms | 0.739 ms | 100 / 500 ms |
| Latest-date slice | 25,000 | 33.941 ms | 34.648 ms | 250 / 1,000 ms |
| Latest-date RSI rank | 25,000 | 41.840 ms | 42.541 ms | 500 / 2,000 ms |
| Million-row coverage | 1,000,000 | 274.091 ms | 374.153 ms | 10,000 / 30,000 ms |

The rank used a 2,526-KiB in-memory quicksort under the 4-MiB `work_mem`
baseline. The complete 76-feature report-summary set measured 483.405 ms
median and 486.467 ms maximum over one million rows on the repeated idle probe.
Linear current-universe projections are 9.95 seconds median and 10.01 seconds
maximum, inside the 10-second/30-second gates. An immediately preceding
diagnostic run measured 498.034/586.197 ms (10.25/12.07-second projections);
the repeated otherwise-idle result governs the gate and shows no stable
regression warranting query changes.

## Publication, Lock, Runner, And Reports

Exact rollback/cleanup-safe integration paths were timed with pytest duration
reporting and `/usr/bin/time -l`:

| Case | Wall time |
|---|---:|
| Staged atomic publication fixture | 0.24 s |
| In-place atomic publication fixture | 0.04 s |
| Lock acquisition/contention/reacquisition fixture | 0.06 s |
| Vertical append/no-op/correction/version/resume workflow | 14.47 s |
| Healthy no-op workflow fixture | 5.70 s |
| Daily PDF render | 0.27 s |
| Largest bounded-sample PDF render | 0.16 s |
| Backfill partial PDF render | 0.15 s |

The publication/lock/report group passed 12 tests in 1.02 seconds with
137,199,616 bytes maximum RSS. The vertical/no-op group passed two tests in
20.32 seconds with 336,756,736 bytes maximum RSS. These are below the relevant
512-MiB report and 1-GiB daily bounds.

Daily/backfill JSON sizes were 19,795 and 20,240 bytes. Across pass, warning,
no-op, partial, failure, and maximum-sample PDF cases, artifacts ranged from
174,207 to 177,374 bytes and 11 to 12 pages. All remain far below the 2-MiB
JSON, 5-MiB PDF, and 25-page gates.

The exact staged finalizer fixture is deliberately small; its validation is
combined with the million-row staged-clone and 25,000-row upsert measurements.
The current database cannot supply a full populated-universe healthy no-op or
exact full-scope summary because the published technical view is empty. Those
production-scale confirmations remain required after P13.10 builds coverage
and before P13.14 enables cadence.

## Commands And Safety

The representative commands were run from the repository root after loading
the local environment:

```bash
PYTHONPATH=packages/empire-stonks-tech-indicators/src:\
packages/empire-core/src:packages/empire-reports/src \
  packages/empire-stonks-tech-indicators/.venv/bin/python \
  tools/tech-indicators/calculation-performance-benchmark.py

PYTHONPATH=packages/empire-stonks-tech-indicators/src:\
packages/empire-core/src:packages/empire-reports/src \
  packages/empire-stonks-tech-indicators/.venv/bin/python \
  tools/tech-indicators/persistence-benchmark.py --airflow-version 3.2.1

PYTHONPATH=packages/empire-stonks-tech-indicators/src:\
packages/empire-core/src:packages/empire-reports/src \
  packages/empire-stonks-tech-indicators/.venv/bin/python \
  tools/tech-indicators/report-summary-benchmark.py
```

Both database harnesses removed their uniquely named scratch schemas; a
post-run namespace query returned zero residue. Publication, lock, vertical,
and no-op fixtures used rollback or explicit cleanup. No broad source or
technical backfill, production publication, remediation, or live cadence ran.
