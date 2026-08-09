# Tech-Indicators I3.7 Large-Read Evidence

Date: 2026-08-09

This is the read-only I3.7 input-service benchmark required by the frozen
[performance gates](tech-indicators-performance-release-gates-v1.md). The
repeatable probe is
[`tools/tech-indicators/large-read-smoke.py`](../../tools/tech-indicators/large-read-smoke.py).
It uses caller-owned `REPEATABLE READ, READ ONLY` transactions and does not
create or publish technical rows.

## Representative Database

- PostgreSQL 18.4, Python 3.14.6, `shared_buffers=128MB`, `work_mem=4MB`.
- 23,386 provider listings, 22,261 active P0.6-eligible listings, and
  20,684,494 OHLCV rows.
- The longest eligible listing contained 16,238 observations from 1962-01-02
  through 2026-07-17, satisfying the real P99 and maximum-history workload.
- The published technical view contained zero rows. The source-side and empty
  published-view plans are valid I3 input evidence; populated wide-payload,
  slot-size, and final published-view evidence remains mandatory in W7.9 and
  V12.6.

## Result

The public source reader returned the 16,238-row history as exact pages of
10,000 and 6,238 rows, then returned the first full-universe page at exactly
10,000 rows. State comparison returned one bounded summary page. The public
input/readiness portion took 2.267 seconds, the complete probe took 5.131
seconds, and peak process RSS was 103.83 MiB, below the 10-second/256-MiB smoke
gate. All work remained in the caller's read-only repeatable-read transaction.

A one-millisecond statement timeout cancelled the representative eligible
OHLCV aggregate. PostgreSQL left the caller transaction in its failed state;
the caller rolled it back and successfully executed a new query. This proves
the package does not hide transaction recovery or cancellation ownership.

The initial public source keyset used display identity before the database
natural key. I3.7 corrected it to `(provider_listing_id, trading_date)`, which
matches the primary key and prevents a full-universe display-order sort while
retaining deterministic pages.

## Five-Run Query Plans

The otherwise idle local stack was not cache-reset, so these are warm/local
measurements and make no cold-cache claim.

| Case | Rows | Plan | Buffers on final run | Sort/temp I/O | Execution median / max |
|---|---:|---|---:|---|---:|
| Exact listing page | 10,000 | limit over `pk_ohlcv_daily` index scan; one loop | 270 hits, 0 reads | none / none | 1.30 / 1.59 ms |
| Full eligible source page | 50,000 | limit over natural-key index scan; one loop | 1,591 hits, 0 reads | none / none | 7.57 / 8.03 ms |
| Source/published drift page | 50,000 | merge left join with source index-only scan; one loop | 642 hits, 0 reads | 25 KiB in-memory quicksort of the empty two-slot view / none | 6.77 / 7.15 ms |

The exact-listing and full-scope page plans had no explicit sort or temporary
I/O. The drift plan's 25 KiB sort applies to the currently empty published
two-slot append; it is recorded rather than generalized to a populated view.
W7.9 must repeat that plan after representative payload rows exist.

## Reproduction

From the repository root with the local Empire database running:

```bash
source bin/env-load deploy/env/local.env
PYTHONPATH=packages/empire-core/src:packages/empire-stonks-tech-indicators/src \
  packages/empire-core/.venv/bin/python \
  tools/tech-indicators/large-read-smoke.py
```

The probe emits bounded JSON facts only: versions, counts, page sizes, timing,
RSS, plan summaries, transaction/cancellation outcomes, and one representative
listing identity. It emits no environment dump, feature payload, or raw plan.
