# Tech-Indicators Publication Schema V1

Status: frozen S2.2 implementation contract as of 2026-08-09.

This document translates
[`tech-indicators-publication-contract-v1.md`](tech-indicators-publication-contract-v1.md)
into exact V1 auxiliary relation columns, lifecycle vocabulary, membership
facts, and published-view selection. The shared 90-column payload signature is
frozen in
[`tech-indicators-payload-schema-v1.md`](tech-indicators-payload-schema-v1.md).
S2.3 owns keys, FKs, delete actions, and checks; S2.4 owns indexes; S2.5 creates
the relations and view without changing this schema.
Those S2.3 rules and the Python-validation boundary are frozen in
[`tech-indicators-constraints-v1.md`](tech-indicators-constraints-v1.md).
The minimal S2.4 payload and auxiliary index decision is frozen in
[`tech-indicators-indexes-v1.md`](tech-indicators-indexes-v1.md).

## Recurrence State Is Rejected

B1.2 proved exact V1 append/correction output by calculating each affected
listing from its earliest eligible source observation and writing only the
affected suffix. Bounded restart was not equivalent. Persisting recurrence
state would make Empire version TA-Lib's private EMA, RSI, ATR, DI/ADX, and
MACD continuation state without a performance need.

Therefore S2.2 rejects
`stonks.ohlcv_daily_tech_indicators_state`. S2.5 must not create that table, a
replacement checkpoint table, recurrence columns in either payload slot, or
generic state JSON. Resume state is publication/listing completion state, not
mathematical recurrence state. W7.4 has no V1 state writer.

## Publication Relation

`stonks.tech_indicators_publication` stores one bounded candidate/publication
unit using this exact ordered column block:

```sql
publication_id UUID NOT NULL DEFAULT gen_random_uuid(),
publication_kind VARCHAR(32) NOT NULL,
status VARCHAR(16) NOT NULL,
calculation_version VARCHAR(64) NOT NULL,
publication_method VARCHAR(16) NULL,
scope_schema_version SMALLINT NULL,
scope_hash CHAR(64) NULL,
effective_date DATE NULL,
requested_start_date DATE NULL,
requested_end_date DATE NULL,
run_id UUID NULL,
benchmark_required BOOLEAN NULL,
benchmark_provider_listing_id UUID NULL,
benchmark_contract_version VARCHAR(64) NULL,
benchmark_coverage_start_date DATE NULL,
benchmark_coverage_end_date DATE NULL,
benchmark_source_row_count BIGINT NULL,
expected_listing_count INTEGER NULL,
expected_source_row_count BIGINT NULL,
expected_payload_row_count BIGINT NULL,
inserted_row_count BIGINT NULL,
updated_row_count BIGINT NULL,
deleted_row_count BIGINT NULL,
equivalent_row_count BIGINT NULL,
warning_count INTEGER NULL,
failure_count INTEGER NULL,
completed_batch_count INTEGER NULL,
staged_payload_row_count BIGINT NULL,
resume_provider_listing_id UUID NULL,
resume_trading_date DATE NULL,
resume_cursor_updated_at TIMESTAMPTZ NULL,
json_report_object_id UUID NULL,
pdf_report_object_id UUID NULL,
source_validated_at TIMESTAMPTZ NULL,
prepared_at TIMESTAMPTZ NULL,
published_at TIMESTAMPTZ NULL,
failed_at TIMESTAMPTZ NULL,
abandoned_at TIMESTAMPTZ NULL,
retired_at TIMESTAMPTZ NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Only `publication_id`, `created_at`, and `updated_at` have database defaults.
The workflow supplies kind, initial status, and calculation version on a
`BUILDING` row. Resolved method, scope, benchmark, count, cursor, report,
validation, and terminal fields remain null until their owning lifecycle
stage; zero never means unknown.

### Exact Vocabulary And Lifecycle

`publication_kind` is exactly:

```text
DAILY
CORRECTION
VERSION_REBUILD
BACKFILL
ELIGIBILITY_REMOVAL
```

`CORRECTION` covers subject and SPX dependency closures; scope and benchmark
facts distinguish them. Recovery continues the original publication. Healthy
no-op and dry-run workflows create no publication row.

`publication_method` is exactly `IN_PLACE`, `STAGED`, or `MEMBERSHIP_ONLY`.
`IN_PLACE` applies the bounded payload mutation in the terminal transaction;
`STAGED` commits inactive-slot images in bounded batches;
`MEMBERSHIP_ONLY` is restricted to `ELIGIBILITY_REMOVAL`. Method is null only
before planning selects a safe path and is immutable afterward.

`status` is exactly:

```text
BUILDING
PREPARED
PUBLISHED
FAILED
ABANDONED
RETIRED
```

Transitions are one-way:

```text
BUILDING -> PREPARED -> PUBLISHED -> RETIRED
    |           |
    +----------> FAILED
    +----------> ABANDONED
```

The writer changes `updated_at` on a real lifecycle change and sets only the
timestamp matching that transition. Timestamps do not replace status.

### Scope, Benchmark, Counts, And Evidence

`scope_schema_version = 1`; `scope_hash` is lowercase SHA-256 of P0.10's
canonical resolved-scope JSON. Both are null before concrete listing resolution
and immutable once populated. Listing membership is normalized, not JSON.

`effective_date` applies only to `DAILY` and date-scoped `CORRECTION` units.
`requested_start_date`/`requested_end_date` are inclusive request bounds, not
slot coverage. Null means a date does not apply.

The V1 benchmark-contract identity is `TECH_INDICATORS_SPX_V1`. A prepared unit
with supported subjects has `benchmark_required = true` plus the resolved UUID,
contract identity, and exact source coverage/count used through the candidate
horizon. With no supported subject, the boolean is false and all benchmark
detail fields are null. These facts do not replace terminal revalidation.

`source_validated_at` records complete candidate/source comparison time. There
is no `is_ready`, `is_complete`, source-snapshot shortcut, opaque state JSON,
or trusted timestamp marker; finalization re-runs exact checks.

The `expected_*` fields are complete prepared-unit counts. Inserted, updated,
deleted, and equivalent rows remain distinct actual outcomes. Count fields are
null before known and zero only for a genuine known zero. S2.3 freezes
nonnegative and status-dependent shapes.

Every committed `STAGED` batch atomically increments `completed_batch_count`,
sets cumulative `staged_payload_row_count`, and stores the deterministic latest
cursor as `(resume_provider_listing_id, resume_trading_date)` plus
`resume_cursor_updated_at`. Cursor order is P0.7's provider/listing/date order.
Resume matches the immutable scope hash and revalidates inactive payload
through this cursor. Non-staged prepared units have known zero batch/payload
counts and null cursor fields. This is workflow progress, not recurrence state
or publication readiness.

`run_id`, `json_report_object_id`, and `pdf_report_object_id` are nullable,
cleanup-safe Core evidence. Later Core retention does not delete, retire, or
change a correct publication. S2.3 freezes their FK actions.

## Membership Relation

`stonks.tech_indicators_publication_listing` stores one candidate membership
per publication/provider listing using this exact ordered column block:

```sql
publication_id UUID NOT NULL,
provider_listing_id UUID NOT NULL,
action VARCHAR(16) NOT NULL,
target_slot CHAR(1) NULL,
calculation_version VARCHAR(64) NOT NULL,
source_coverage_start_date DATE NULL,
source_coverage_end_date DATE NULL,
source_row_count BIGINT NOT NULL,
payload_row_count BIGINT NOT NULL,
benchmark_provider_listing_id UUID NULL,
candidate_completed_at TIMESTAMPTZ NOT NULL,
is_active BOOLEAN NOT NULL DEFAULT false,
activated_at TIMESTAMPTZ NULL,
deactivated_at TIMESTAMPTZ NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Only `is_active`, `created_at`, and `updated_at` have defaults. There is no
array/JSON listing set, marker row, global active slot, generation number, or
slot pointer on `provider_listing`.

`action` is `PRESENT` or `REMOVE`:

- `PRESENT` selects target slot `A` or `B`. Coverage/counts describe the
  complete listing image. A selected zero-bar listing has null coverage dates
  and zero source/payload counts but still has membership.
- `REMOVE` has null slot/dates/benchmark and zero source/payload counts. It
  suppresses older payload without an all-null row or source deletion.

For `PRESENT`, date-bounded work preserves published rows outside the request,
so membership facts cover the complete image, not one batch. Benchmark UUID is
populated for supported subjects and null for unsupported subjects, including
Yahoo SPX.

`candidate_completed_at` records completed per-listing candidate facts but
does not expose them. Terminal publication sets the new row active/activated,
deactivates the prior row, and sets its deactivation timestamp atomically. A
historical membership is never reactivated; rollback/reuse gets a new validated
publication and membership row.

S2.3 freezes composite identity, one-active-membership uniqueness, FKs,
action/slot/count/coverage/benchmark/timestamp shapes, and the requirement that
active membership has a `PUBLISHED` parent.

## Exact Published View

The view selects only active `PRESENT` membership from `PUBLISHED` parents by
listing and slot. A membership selects a complete listing image, so the view
needs no date filter. Both arms use `UNION ALL`, explicitly project the exact
ordered S2.1 columns, and never use `SELECT *`.

```sql
CREATE VIEW stonks.ohlcv_daily_tech_indicators AS
WITH active_membership AS (
    SELECT membership.provider_listing_id, membership.target_slot
    FROM stonks.tech_indicators_publication_listing AS membership
    INNER JOIN stonks.tech_indicators_publication AS publication
        ON publication.publication_id = membership.publication_id
    WHERE membership.is_active
      AND membership.action = 'PRESENT'
      AND publication.status = 'PUBLISHED'
)
SELECT
    payload_a.provider_listing_id,
    payload_a.trading_date,
    payload_a.relative_strength_benchmark_provider_listing_id,
    payload_a.history_observation_count,
    payload_a.calculation_version,
    payload_a.run_id,
    payload_a.calculated_at,
    payload_a.created_at,
    payload_a.updated_at,
    payload_a.open,
    payload_a.high,
    payload_a.low,
    payload_a.close,
    payload_a.volume,
    payload_a.return_1d_pct,
    payload_a.return_2d_pct,
    payload_a.return_3d_pct,
    payload_a.return_5d_pct,
    payload_a.return_10d_pct,
    payload_a.return_20d_pct,
    payload_a.return_63d_pct,
    payload_a.return_126d_pct,
    payload_a.return_252d_pct,
    payload_a.gap_1d_pct,
    payload_a.sma_20,
    payload_a.sma_50,
    payload_a.sma_200,
    payload_a.ema_12,
    payload_a.ema_20,
    payload_a.ema_26,
    payload_a.ema_50,
    payload_a.sma_50_change_20d_pct,
    payload_a.sma_200_change_20d_pct,
    payload_a.hh_20,
    payload_a.hh_50,
    payload_a.hh_252,
    payload_a.ll_20,
    payload_a.ll_50,
    payload_a.rsi_14,
    payload_a.atr_14,
    payload_a.return_volatility_20d_pct,
    payload_a.return_volatility_60d_pct,
    payload_a.return_1d_zscore_20d,
    payload_a.return_3d_zscore_20d,
    payload_a.price_stddev_20,
    payload_a.plus_di_14,
    payload_a.minus_di_14,
    payload_a.adx_14,
    payload_a.macd_12_26,
    payload_a.macd_signal_12_26_9,
    payload_a.macd_histogram_12_26_9,
    payload_a.volume_avg_20,
    payload_a.volume_avg_60,
    payload_a.dollar_volume_avg_20,
    payload_a.consecutive_up_days,
    payload_a.consecutive_down_days,
    payload_a.rel_spx,
    payload_a.pct_rel_spx_20,
    payload_a.pct_rel_spx_50,
    payload_a.relative_return_spx_20d_pct,
    payload_a.relative_return_spx_63d_pct,
    payload_a.relative_return_spx_126d_pct,
    payload_a.relative_return_spx_252d_pct,
    payload_a.spx_beta_60d,
    payload_a.spx_beta_252d,
    payload_a.spx_correlation_60d,
    payload_a.spx_correlation_252d,
    payload_a.dollar_volume,
    payload_a.intraday_return_1d_pct,
    payload_a.daily_range_pct,
    payload_a.close_location_1d,
    payload_a.pct_sma_20,
    payload_a.pct_sma_50,
    payload_a.pct_sma_200,
    payload_a.pct_ema_20,
    payload_a.pct_ema_50,
    payload_a.pct_sma_20_vs_50,
    payload_a.pct_sma_20_vs_200,
    payload_a.pct_sma_50_vs_200,
    payload_a.pct_hh_20,
    payload_a.pct_hh_50,
    payload_a.pct_hh_252,
    payload_a.pct_ll_20,
    payload_a.pct_ll_50,
    payload_a.atr_pct_14,
    payload_a.bollinger_percent_b_20_2,
    payload_a.bollinger_bandwidth_20_2,
    payload_a.volume_ratio_20,
    payload_a.macd_12_26_pct,
    payload_a.macd_histogram_12_26_9_pct
FROM stonks.ohlcv_daily_tech_indicators_a AS payload_a
INNER JOIN active_membership
    ON active_membership.provider_listing_id = payload_a.provider_listing_id
   AND active_membership.target_slot = 'A'
UNION ALL
SELECT
    payload_b.provider_listing_id,
    payload_b.trading_date,
    payload_b.relative_strength_benchmark_provider_listing_id,
    payload_b.history_observation_count,
    payload_b.calculation_version,
    payload_b.run_id,
    payload_b.calculated_at,
    payload_b.created_at,
    payload_b.updated_at,
    payload_b.open,
    payload_b.high,
    payload_b.low,
    payload_b.close,
    payload_b.volume,
    payload_b.return_1d_pct,
    payload_b.return_2d_pct,
    payload_b.return_3d_pct,
    payload_b.return_5d_pct,
    payload_b.return_10d_pct,
    payload_b.return_20d_pct,
    payload_b.return_63d_pct,
    payload_b.return_126d_pct,
    payload_b.return_252d_pct,
    payload_b.gap_1d_pct,
    payload_b.sma_20,
    payload_b.sma_50,
    payload_b.sma_200,
    payload_b.ema_12,
    payload_b.ema_20,
    payload_b.ema_26,
    payload_b.ema_50,
    payload_b.sma_50_change_20d_pct,
    payload_b.sma_200_change_20d_pct,
    payload_b.hh_20,
    payload_b.hh_50,
    payload_b.hh_252,
    payload_b.ll_20,
    payload_b.ll_50,
    payload_b.rsi_14,
    payload_b.atr_14,
    payload_b.return_volatility_20d_pct,
    payload_b.return_volatility_60d_pct,
    payload_b.return_1d_zscore_20d,
    payload_b.return_3d_zscore_20d,
    payload_b.price_stddev_20,
    payload_b.plus_di_14,
    payload_b.minus_di_14,
    payload_b.adx_14,
    payload_b.macd_12_26,
    payload_b.macd_signal_12_26_9,
    payload_b.macd_histogram_12_26_9,
    payload_b.volume_avg_20,
    payload_b.volume_avg_60,
    payload_b.dollar_volume_avg_20,
    payload_b.consecutive_up_days,
    payload_b.consecutive_down_days,
    payload_b.rel_spx,
    payload_b.pct_rel_spx_20,
    payload_b.pct_rel_spx_50,
    payload_b.relative_return_spx_20d_pct,
    payload_b.relative_return_spx_63d_pct,
    payload_b.relative_return_spx_126d_pct,
    payload_b.relative_return_spx_252d_pct,
    payload_b.spx_beta_60d,
    payload_b.spx_beta_252d,
    payload_b.spx_correlation_60d,
    payload_b.spx_correlation_252d,
    payload_b.dollar_volume,
    payload_b.intraday_return_1d_pct,
    payload_b.daily_range_pct,
    payload_b.close_location_1d,
    payload_b.pct_sma_20,
    payload_b.pct_sma_50,
    payload_b.pct_sma_200,
    payload_b.pct_ema_20,
    payload_b.pct_ema_50,
    payload_b.pct_sma_20_vs_50,
    payload_b.pct_sma_20_vs_200,
    payload_b.pct_sma_50_vs_200,
    payload_b.pct_hh_20,
    payload_b.pct_hh_50,
    payload_b.pct_hh_252,
    payload_b.pct_ll_20,
    payload_b.pct_ll_50,
    payload_b.atr_pct_14,
    payload_b.bollinger_percent_b_20_2,
    payload_b.bollinger_bandwidth_20_2,
    payload_b.volume_ratio_20,
    payload_b.macd_12_26_pct,
    payload_b.macd_histogram_12_26_9_pct
FROM stonks.ohlcv_daily_tech_indicators_b AS payload_b
INNER JOIN active_membership
    ON active_membership.provider_listing_id = payload_b.provider_listing_id
   AND active_membership.target_slot = 'B';
```

The view projects no publication ID, slot, action, status, readiness flag, or
report fact. Readiness-aware queries read membership/publication facts and the
view in one `REPEATABLE READ` snapshot; the bare view is only published rows.

## SQL Comments

Relation comments are exactly:

| Relation | Required comment |
|---|---|
| `stonks.tech_indicators_publication` | Candidate and published lifecycle facts for atomic provider-native tech-indicator publication units. |
| `stonks.tech_indicators_publication_listing` | Per-publication provider-listing action, complete slot image, and active published membership facts. |

Every auxiliary column must be commented with its meaning above. In
particular, comments must identify method, scope hash/version, inclusive request dates,
cleanup-safe Core evidence, benchmark identity/coverage, exact count category,
bounded staged cursor/progress, matching lifecycle timestamp, complete listing-image coverage/counts,
`PRESENT`/`REMOVE`, A/B slot, candidate completion, and activation/deactivation.
No comment may describe one timestamp, count, boolean, report reference, or the
bare view as sufficient readiness, or claim append-only revisions, canonical
identity, adjusted values, or a global slot.

## S2.3-S2.6 Handoff

Later schema work must prove:

1. exact keys/FKs/delete actions and status-dependent constraints;
2. one active membership per listing and no active membership to a
   non-`PUBLISHED` parent;
3. complete `PRESENT`/`REMOVE`, supported/unsupported benchmark, and
   zero-row/dated-coverage shapes;
4. legal lifecycle/timestamp transitions and cleanup-safe Core evidence;
5. view visibility only for active `PRESENT` membership from `PUBLISHED`
   parents, with independent A/B listings and no duplicate natural key;
6. no recurrence-state relation or generic state/readiness JSON; and
7. readiness independently revalidating current source/benchmark state.

Any auxiliary column, vocabulary, lifecycle, membership, recurrence-state, or
view-selection change requires an explicit amendment before migration.
