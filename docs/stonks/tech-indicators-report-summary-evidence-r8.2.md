# Tech-Indicators R8.2 Report-Summary Evidence

Date: 2026-08-22

This records the R8.2 query-plan evidence required by the frozen
[performance gates](tech-indicators-performance-release-gates-v1.md). The
repeatable probe is
[`tools/tech-indicators/report-summary-benchmark.py`](../../tools/tech-indicators/report-summary-benchmark.py).
It creates a uniquely named logged schema, clones the production payload
columns and generated expressions, loads real provider-native OHLCV shapes,
runs the exact version, history/null-reason, and feature-count aggregates five
times, and drops the schema in `finally`. It never writes either production
payload slot or publication membership.

## Runtime And Scope

- PostgreSQL 18.4 on arm64 with `shared_buffers=128MB`, `work_mem=4MB`, and
  `maintenance_work_mem=64MB`.
- The deterministic pilot selected the 100 longest active P0.6-supported
  EODData/Stooq histories and copied their first 10,000 observations: exactly
  1,000,000 wide payload rows.
- The scratch build and `ANALYZE` took 8.481 seconds. The live production
  technical relations remained empty, so this representative populated probe
  is reported separately from production state.
- W7.9 remains the calculation, validation, persistence, row-width, index, WAL,
  and disk evidence. This probe isolates R8.2's count-only report queries.

## Five-Run Plans

The otherwise idle local stack was not cache-reset, so no cold-cache claim is
made. Every plan used a parallel sequential aggregate, which P0.8 explicitly
permits for genuine full-scope report coverage. Actual and planned result rows
reconciled: version coverage 100/100, history coverage 10,000/10,010, and feature
coverage 1/1. Root loops were one in every run.

| Query | Median | Maximum | Sort | Temporary I/O |
|---|---:|---:|---|---:|
| Provider-listing/version and benchmark completeness | 93.369 ms | 100.433 ms | 39 KiB in-memory quicksort | 0 blocks |
| Observation-history/null-reason coverage | 75.915 ms | 78.603 ms | none | 0 blocks |
| All 76 populated and guaranteed-null counts | 314.172 ms | 320.746 ms | none | 0 blocks |
| Complete database summary aggregate set | 481.562 ms | 495.921 ms | as above | 0 blocks |

Across the five runs, root shared buffers ranged from 12,518 to 15,924 hits and
8,651 to 12,087 reads per query. The aggregates return 10,101 grouped/count
rows in total and no feature or OHLCV values. The feature query avoids 76
redundant null aggregates: null counts derive from total minus populated, while
one narrow history aggregate supplies exact warm-up and unsupported counts.
Contract validation rejects any resulting count overlap or mismatch.

The P0.8 full-scope baseline is about 20.6 million rows. A deliberately simple
linear projection of the measured complete-query median is 9.91 seconds and of
the measured maximum is 10.21 seconds. These are inside the initial 10-second
median and 30-second maximum targets. This is plan and projection evidence, not
a claim that the currently empty production technical view was measured at
full size; V12.6 must repeat the gate on the populated current universe.

## Reproduction And Cleanup

From the repository root with local PostgreSQL running:

```bash
source bin/env-load deploy/env/local.env
PYTHONPATH=packages/empire-stonks-tech-indicators/src:\
packages/empire-core/src \
  packages/empire-core/.venv/bin/python \
  tools/tech-indicators/report-summary-benchmark.py
```

The command emits one bounded, sorted JSON document containing database
settings, scope counts, summarized plans, buffers, sorts, temporary I/O,
planning times, and execution times. It emits no environment dump, SQL,
credentials, source rows, or feature values. Normal completion and handled
failure both remove the exact `tech_indicators_r82_<12 hex>` schema.
