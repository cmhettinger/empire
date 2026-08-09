# Tech-Indicators Initial Indexes V1

Status: frozen S2.4 implementation contract as of 2026-08-09.

This document selects the smallest V1 access-index set for the payload,
publication, and membership relations frozen in
[`tech-indicators-payload-schema-v1.md`](tech-indicators-payload-schema-v1.md),
[`tech-indicators-publication-schema-v1.md`](tech-indicators-publication-schema-v1.md),
and
[`tech-indicators-constraints-v1.md`](tech-indicators-constraints-v1.md).
S2.5 implements this exact set. W7.9 and V12.6 own later measurement-driven
tuning; they may not add an index without preserving new plan evidence.

## Selected Index Set

S2.3 already gives each payload slot its composite primary-key B-tree in
listing/date order. S2.4 adds exactly one non-integrity index to each slot:

```sql
CREATE INDEX ix_ohlcv_daily_tech_indicators_a_trading_date
    ON stonks.ohlcv_daily_tech_indicators_a (
        trading_date DESC,
        provider_listing_id
    );

CREATE INDEX ix_ohlcv_daily_tech_indicators_b_trading_date
    ON stonks.ohlcv_daily_tech_indicators_b (
        trading_date DESC,
        provider_listing_id
    );
```

`DESC` matches the live OHLCV freshness-index convention. PostgreSQL B-trees
can scan in either direction, so this also supports ascending date ranges. The
second key makes same-date identity order deterministic without adding feature
payload to the index.

No non-integrity access index is added to
`stonks.tech_indicators_publication` or
`stonks.tech_indicators_publication_listing`. Their V1 access paths are already
covered by:

- publication primary key `(publication_id)` for lifecycle ownership;
- membership primary key `(publication_id, provider_listing_id)` for candidate
  enumeration, count reconciliation, and retirement checks; and
- S2.3's partial unique integrity index on active `provider_listing_id`, which
  also bounds the active-membership side of the published view to at most one
  row per listing.

Publication volume is run-sized rather than payload-sized. A status, kind,
scope-hash, timestamp, slot, or action index is not justified before an actual
recovery/report query demonstrates a selective access path.

## Representative Access Paths

Package queries must use the selected keys as follows. Examples show one
physical slot; published-view queries apply the same date predicate to both
arms through the view.

### Listing History

History is keyset-paged in primary-key order. The default 10,000-row page is
required to prevent PostgreSQL from preferring a bitmap scan plus an explicit
sort for a whole long history.

```sql
SELECT provider_listing_id, trading_date, /* only required feature columns */
FROM stonks.ohlcv_daily_tech_indicators_a
WHERE provider_listing_id = :provider_listing_id
  AND trading_date > :after_trading_date
ORDER BY trading_date
LIMIT :page_size;
```

The same primary key supports reverse latest-observation lookup. No duplicate
`(provider_listing_id, trading_date DESC)` index is added.

### Latest-Date Slice And Ranking

Latest-date and model-input reads constrain the date before projecting only
needed columns:

```sql
SELECT provider_listing_id, trading_date, close, rsi_14
FROM stonks.ohlcv_daily_tech_indicators
WHERE trading_date = :trading_date;
```

A rank reads the same bounded slice and sorts one selected feature:

```sql
SELECT provider_listing_id, rsi_14
FROM stonks.ohlcv_daily_tech_indicators
WHERE trading_date = :trading_date
ORDER BY rsi_14 DESC NULLS LAST
LIMIT 25000;
```

The date-leading indexes prevent either view arm from scanning its complete
payload. The active-membership integrity index and publication primary key
then validate visibility. Ranking does not project the 90-column row.

### Backfill And Resume

Payload/source work streams in the shared natural-key order with a bounded
cursor:

```sql
SELECT provider_listing_id, trading_date, /* bounded write/read columns */
FROM stonks.ohlcv_daily_tech_indicators_a
WHERE (provider_listing_id, trading_date)
    > (:resume_provider_listing_id, :resume_trading_date)
ORDER BY provider_listing_id, trading_date
LIMIT :page_size;
```

The primary key provides deterministic order with no external sort. A broad
full scan remains allowed when PostgreSQL measures it cheaper, but the package
must not request an unbounded ordered result.

### Source Correction And Drift

Exact source/payload comparison joins the identical composite keys and pages
the result in that order:

```sql
SELECT source.provider_listing_id, source.trading_date
FROM stonks.ohlcv_daily AS source
LEFT JOIN stonks.ohlcv_daily_tech_indicators_a AS payload
    USING (provider_listing_id, trading_date)
WHERE (source.provider_listing_id, source.trading_date)
    > (:after_provider_listing_id, :after_trading_date)
ORDER BY source.provider_listing_id, source.trading_date
LIMIT :page_size;
```

Copied-value, count, version, and missing-row predicates are evaluated inside
that bounded set-based join. They do not require separate indexes on copied
values, `history_observation_count`, `calculation_version`, or timestamps.
SPX correction uses the date-leading index for bounded suffixes; a broad old
SPX correction is intentionally a backfill-class scan.

## Live PostgreSQL Evidence

S2.4 ran read-only `EXPLAIN (ANALYZE, BUFFERS)` against the live
`stonks.ohlcv_daily` relation on 2026-08-09. The technical relations do not
exist before S2.5, so this is directional index-selection evidence using their
exact provider-native natural key and copied source types, not a claim about
the final 90-column relation's latency.

The database was PostgreSQL 18.4 with 128 MB `shared_buffers` and 4 MB
`work_mem`. The live relation contained 20,684,494 rows and occupied 5,414 MB.
Its matching `(provider_listing_id, trading_date)` primary-key index occupied
1,442 MB; its matching `(trading_date DESC, provider_listing_id)` index
occupied 1,075 MB. Statistics were current enough for planned/actual rows to
agree at the representative narrow slices below.

Each case ran five consecutive times on the otherwise idle local stack. Cache
state was not reset, so the table reports the observed median and maximum but
does not label either result cold-cache. No case used temporary I/O.

| Access case | Representative rows | Selected plan and buffers | Sort | Execution median / maximum |
|---|---:|---|---|---:|
| Listing history | 16,238 real rows in 10,000 + 6,238 keyset pages | two `pk_ohlcv_daily` index scans; 442 shared hits on warm paired runs | none | 2.315 / 2.731 ms |
| Latest-date slice | 21,276 real rows for 2026-07-16; 20,404 planned | bitmap heap/index scan using `ix_ohlcv_daily_trading_date`; 8,851 warm buffers, 8,854 maximum | quicksort, 2,256 kB | 8.499 / 136.975 ms |
| Single-feature rank | same 21,276-row date slice; two projected columns | same date-index bitmap path; 8,851 warm buffers, 8,854 maximum | quicksort, 2,264 kB | 12.979 / 17.475 ms |
| Backfill/resume page | 50,000 of 19,129,156 planned remaining rows | one primary-key index scan; 1,605 warm buffers, 1,630 maximum | none | 6.950 / 31.952 ms |
| Source/payload drift page | 50,000 joined rows | merge left join over two primary-key index scans, one search each; 3,210 buffers | none | 27.383 / 36.015 ms |

The first latest-slice run read 8,646 heap buffers and produced the reported
136.975 ms maximum; later runs were cache hits. That is observed uncontrolled
cache behavior, not a cold-cache benchmark. Final view, wide-row, two-slot,
membership, write-cost, and disk gates remain mandatory in W7.9/V12.6.

## Rejected Initial Indexes

The evidence rejects additional V1 indexes now:

- no RSI, average-dollar-volume, SPX-relative-return, or other feature-ranking
  index: the 21,276-row date slice sorted in 2,264 kB under the 4 MB baseline,
  and one feature index would not serve the other query-time ranks;
- no broad `INCLUDE` index: copying wide feature columns would materially
  multiply both-slot storage and write amplification;
- no standalone calculation-version, observation-count, benchmark, run,
  lifecycle-status, action, or boolean index: the representative paths use
  natural keys/date, and the remaining values are low-selectivity or belong to
  small auxiliary relations;
- no duplicate descending listing/date index: the primary key scans backward;
- no BRIN date index: the provider-listing/date physical order is not globally
  date-correlated, while the live B-tree proved the bounded date path; and
- no index intended for a strategy threshold or deferred cross-sectional rank
  before a stable consumer and representative plan exist.

Core/report FK cleanup and provider-listing deletion remain semantically safe
through S2.3's delete actions. Their uncommon bulk maintenance paths must be
measured by W7.9 before adding payload-sized lineage or benchmark indexes; an
unmeasured FK-support index is not hidden in S2.5.

## S2.5 And Later Verification

S2.5 must create both date indexes exactly as written after their payload
tables, preserve S2.3's integrity index, and add no other index. Catalog tests
must prove both slots have the same primary/date index signatures and the
auxiliary tables have only their keys plus the active-membership integrity
index.

After representative technical rows exist, `ANALYZE` precedes plan capture.
I3.7, W7.9, R8.2, and V12.6 must re-run the named queries through the actual
published view, record all P0.8 plan facts and five-run latencies, measure both
slots' heap/index/WAL cost, and amend this contract before changing the set.
