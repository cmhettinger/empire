# Tech-Indicators W7.9 Persistence Evidence

Date: 2026-08-22

This is the W7.9 persistence benchmark required by the frozen
[performance gates](tech-indicators-performance-release-gates-v1.md). The
repeatable probe is
[`tools/tech-indicators/persistence-benchmark.py`](../../tools/tech-indicators/persistence-benchmark.py).
It creates a uniquely named logged schema, clones the production payload
columns, generated expressions, checks, primary key, and date-leading index,
runs the exact package `MERGE` statement, and drops the schema in `finally`.
It never writes either production payload slot or publication membership.

## Runtime And Scope

- macOS 26.5.2 arm64 host, Python 3.14.6, PostgreSQL 18.4, Airflow 3.2.1.
- `empire-stonks-tech-indicators` 0.1.0, TA-Lib 0.7.1, NumPy 2.4.6.
- PostgreSQL used `shared_buffers=128MB`, `work_mem=4MB`, and
  `maintenance_work_mem=64MB`.
- The live source contained 20,684,494 OHLCV rows and 23,386 provider
  listings. The production published technical view contained zero rows.
- The deterministic pilot selected the 100 longest active P0.6-supported
  EODData/Stooq histories, then calculated and validated their first 10,000
  observations each. Their complete live histories ranged from 10,580 through
  16,238 observations. The resulting pilot was exactly 1,000,000 rows.
- The same process also exercised a 25,000-row latest-date slice, unchanged
  replay, correction update, and 1,000/5,000/10,000-row batch sizes.

The source histories retain provider-native values and real date gaps. Existing
formula, SPX, source-policy, rebuild-equivalence, and W7.8 PostgreSQL suites
remain authoritative for short/warm-up histories, null Yahoo volume, zero
volume, supported/unsupported SPX subjects, and correction correctness. This
benchmark measures persistence and does not replace those correctness gates.

## Pilot Result

The complete run took 975.149 seconds. Source reads took 3.417 seconds,
calculation plus validation took 859.725 seconds, and database writes took
92.972 seconds. Calculation, validation, and persistence sustained 1,049.65
rows/second, above the 250-row/second floor. Peak RSS was 400.73 MiB, below the
2 GiB pilot gate.

All 1,000,000 rows reconciled as inserts. The 5,000-row default produced 200
independent commits; the maximum transaction was 0.636 seconds, below the
30-second target and 60-second hard limit. A 25,000-row exact rerun reconciled
as 25,000 unchanged rows, and a correction reconciled as 25,000 updates.

## Batch And Repeat-Write Evidence

The otherwise idle local stack was not cache-reset, so these are warm/local
measurements and make no cold-cache claim.

| Case | Transactions | Total | Median transaction | Maximum transaction |
|---|---:|---:|---:|---:|
| 25,000 inserts, batch 1,000 | 25 | 2.313 s | 0.093 s | 0.099 s |
| 25,000 inserts, batch 5,000 | 5 | 2.306 s | 0.461 s | 0.479 s |
| 25,000 inserts, batch 10,000 | 3 | 2.360 s | 0.942 s | 0.952 s |
| 25,000 equivalent rows, batch 5,000 | 5 | 2.072 s | 0.391 s | 0.503 s |
| 25,000 correction rows, batch 5,000 | 5 | 2.503 s | 0.500 s | 0.515 s |

The three insert batch sizes were effectively tied. The 5,000-row default was
marginally fastest, uses one fifth as many commits as 1,000, and halves the
largest transaction exposure of 10,000. No persistence batch setting changed.

## Heap, Index, WAL, And Disk Projection

The million-row relation used 813,948,928 heap bytes and 121,348,096 index
bytes, or 935,542,784 bytes total. The primary key plus one date-leading index
therefore added about 14.9% over heap size. The selective 25,000-row daily
slice added 23,257,088 relation bytes.

The pilot generated 1,257,475,688 WAL bytes, or 1,257.48 bytes per inserted
row. The whole benchmark, including batch comparisons, correction, daily
slice, DDL, and cleanup, generated 1,416,125,080 WAL bytes.

At 935.54 bytes per pilot row, two complete slots for the P0.8 planning
baseline of 20,584,282 rows project to 38,514,952,977 bytes, or 35.87 GiB.
That passes the 40 GiB gate with 4.13 GiB of margin. The host reported
540,469,903,360 available bytes; twice the projected additional footprint plus
10 GiB requires 87,767,324,194 bytes, so the headroom gate passed. This is a
linear planning projection, not permission to start a full backfill; V12.6 must
remeasure current counts, bloat, WAL, and free disk before rollout.

## Five-Run Query Plans

The latest-date analogue placed 25,000 synthetic same-date rows beside the
million historical rows and joined an active-membership table before
projection. It mirrors the selective two-slot access shape without creating a
real publication. W7.10 and V12.6 still own finalizer/concurrency measurements
against the exact production publication lifecycle.

| Case | Rows | Required access | Final buffers | Sort/temp I/O | Median / max |
|---|---:|---|---:|---|---:|
| Exact listing keyset page | 1,000 | `pilot_payload_pkey` index scan | 1,558 hits, 0 reads | none / none | 0.374 / 0.621 ms |
| Latest-date slice | 25,000 | date-leading payload index plus membership PK | 100,460 hits, 0 reads | none / none | 33.456 / 34.118 ms |
| Latest-date RSI rank | 25,000 | date-leading payload index plus membership PK | 100,460 hits, 0 reads | 2,526 KiB in-memory quicksort / none | 40.799 / 41.597 ms |
| Million-row coverage | 100 groups | parallel sequential aggregate | 13,894 hits, 90,442 reads | 33 KiB in-memory quicksort / none | 248.427 / 250.118 ms |

All latency maxima were far below P0.8 limits. Ranking stayed below the 4 MiB
`work_mem` baseline and performed no temporary I/O. A wide payload history page
of 5,000 rows had selected a bitmap heap scan plus explicit sort in the
diagnostic run. Reducing only that future payload-history keyset page to the
allowed 1,000-row lower bound produced the required primary-key index scan and
no sort. The existing 10,000-row narrow source-reader default remains unchanged
because I3.7 separately proved its ordered source index plan.

No new payload, feature, publication, or membership index is justified by this
evidence.

## Reproduction And Cleanup

From the repository root with local PostgreSQL running:

```bash
source bin/env-load deploy/env/local.env
PYTHONPATH=packages/empire-stonks-tech-indicators/src:\
packages/empire-core/src:\
packages/empire-core/.venv/lib/python3.14/site-packages \
  packages/empire-stonks-tech-indicators/.venv/bin/python \
  tools/tech-indicators/persistence-benchmark.py \
  --airflow-version 3.2.1
```

The probe emits one bounded JSON document with counts, versions, timing, RSS,
batch distributions, sizes, WAL, projections, and summarized plans. It emits
no feature payloads, environment dump, or credentials. Normal completion and
handled failure both drop the unique `tech_indicators_w79_*` schema. A process
kill can be audited with `pg_namespace` and cleaned only after confirming the
exact prefix and absence of an active benchmark session.
