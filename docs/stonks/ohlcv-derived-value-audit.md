# OHLCV Derived-Value Consistency Audit

## Decision

The 2026-08-02 read-only audit found no derived-value discrepancies in the
live `stonks.ohlcv_daily` table. No repair command, repair workflow, or
scheduled mutation is justified.

## Method

The audit ordered every bar by `(provider_listing_id, trading_date)` and used
the nearest earlier stored row from `lag()`. It recomputed the writer contract
with PostgreSQL numeric arithmetic and eight-decimal `round()`:

```text
change    = close - predecessor_close
changepct = change / predecessor_close
typ       = (high + low + close) / 3
hl_range  = high - low
oc_range  = close - open
```

The first stored row for a listing expects null `change` and `changepct`.
When the predecessor close is zero, only `changepct` expects null. Comparisons
used null-safe `IS DISTINCT FROM` semantics.

## Live Results

All five individual mismatch counts and the combined mismatch count were zero
for every provider/market partition:

| Provider | Market | Rows | First rows | Zero-close predecessors | Date gaps | Updated rows | Any mismatch |
|---|---:|---:|---:|---:|---:|---:|---:|
| EODDATA | AMEX | 30,467 | 4,539 | 0 | 12,988 | 12,954 | 0 |
| EODDATA | NASDAQ | 34,912 | 5,410 | 0 | 14,923 | 14,737 | 0 |
| EODDATA | NYSE | 22,103 | 3,262 | 0 | 9,481 | 9,411 | 0 |
| STOOQ | nasdaq | 9,082,078 | 4,704 | 3 | 2,077,575 | 0 | 0 |
| STOOQ | nyse | 10,558,875 | 4,537 | 0 | 2,337,107 | 0 | 0 |
| STOOQ | nysemkt | 834,783 | 321 | 0 | 199,531 | 0 | 0 |
| YAHOO | XIDX | 108,561 | 90 | 0 | 23,888 | 3 | 0 |
| **Total** | — | **20,671,779** | **22,863** | **3** | **4,675,493** | **37,105** | **0** |

`Date gaps` counts rows whose predecessor is more than one calendar day
earlier; this verifies that weekend, holiday, and larger stored-history gaps
still use the nearest stored predecessor. `Updated rows` counts live rows whose
`updated_at` is later than `created_at`, providing a bounded check over current
post-insert state. No discrepancy samples exist to report.

## Regression Evidence

The focused database-backed daily-bar writer suite passed six tests. It covers
out-of-order input, unchanged reruns, insertion into an existing date gap,
provider correction, recalculation of the immediately following stored bar,
null volume, and invalid or missing listing inputs. The full package and
combined provider regressions had already passed in V10.3 and V10.7.

This audit describes the current live table. Future imports remain protected
by the shared writer and its focused regression tests; a new repair workflow
should be considered only if a later null-safe full-table audit finds actual
discrepancies.
