# Tech-Indicators Payload Schema V1

Status: frozen S2.1 implementation contract as of 2026-08-09.

This document translates the frozen 90-column
[`tech-indicators-feature-profile-v1.md`](tech-indicators-feature-profile-v1.md)
into the exact PostgreSQL payload and published-view column contract. It is
authoritative for column names, order, types, nullability, generated
expressions, defaults, ownership, and column comments in both physical slots.
The formula specification remains authoritative for calculation semantics.

S2.2 freezes publication/membership columns, rejects recurrence state, and
supplies the final view join in
[`tech-indicators-publication-schema-v1.md`](tech-indicators-publication-schema-v1.md).
S2.3 owns keys, foreign keys, checks, delete actions, and grants. S2.4 owns
indexes. S2.5 must create the tables and view without changing this signature.
The exact S2.3 integrity and Python-validation boundary is frozen in
[`tech-indicators-constraints-v1.md`](tech-indicators-constraints-v1.md).
The exact S2.4 payload access indexes and evidence are frozen in
[`tech-indicators-indexes-v1.md`](tech-indicators-indexes-v1.md).

## Physical Relations And Shared Signature

The two physical payload relations are:

```text
stonks.ohlcv_daily_tech_indicators_a
stonks.ohlcv_daily_tech_indicators_b
```

They use the following column block verbatim and in this order. Constraint and
index clauses follow this block in S2.3-S2.4. There is no slot discriminator,
publication ID, readiness marker, JSON metadata, adjusted close, upstream
derived OHLCV convenience, or recurrence state in either payload row.

```sql
provider_listing_id UUID NOT NULL,
trading_date DATE NOT NULL,
relative_strength_benchmark_provider_listing_id UUID NULL,
history_observation_count INTEGER NOT NULL,
calculation_version VARCHAR(64) NOT NULL,
run_id UUID NULL,
calculated_at TIMESTAMPTZ NOT NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

open NUMERIC(30,10) NOT NULL,
high NUMERIC(30,10) NOT NULL,
low NUMERIC(30,10) NOT NULL,
close NUMERIC(30,10) NOT NULL,
volume NUMERIC(30,8) NULL,

return_1d_pct DOUBLE PRECISION NULL,
return_2d_pct DOUBLE PRECISION NULL,
return_3d_pct DOUBLE PRECISION NULL,
return_5d_pct DOUBLE PRECISION NULL,
return_10d_pct DOUBLE PRECISION NULL,
return_20d_pct DOUBLE PRECISION NULL,
return_63d_pct DOUBLE PRECISION NULL,
return_126d_pct DOUBLE PRECISION NULL,
return_252d_pct DOUBLE PRECISION NULL,
gap_1d_pct DOUBLE PRECISION NULL,
sma_20 DOUBLE PRECISION NULL,
sma_50 DOUBLE PRECISION NULL,
sma_200 DOUBLE PRECISION NULL,
ema_12 DOUBLE PRECISION NULL,
ema_20 DOUBLE PRECISION NULL,
ema_26 DOUBLE PRECISION NULL,
ema_50 DOUBLE PRECISION NULL,
sma_50_change_20d_pct DOUBLE PRECISION NULL,
sma_200_change_20d_pct DOUBLE PRECISION NULL,
hh_20 DOUBLE PRECISION NULL,
hh_50 DOUBLE PRECISION NULL,
hh_252 DOUBLE PRECISION NULL,
ll_20 DOUBLE PRECISION NULL,
ll_50 DOUBLE PRECISION NULL,
rsi_14 DOUBLE PRECISION NULL,
atr_14 DOUBLE PRECISION NULL,
return_volatility_20d_pct DOUBLE PRECISION NULL,
return_volatility_60d_pct DOUBLE PRECISION NULL,
return_1d_zscore_20d DOUBLE PRECISION NULL,
return_3d_zscore_20d DOUBLE PRECISION NULL,
price_stddev_20 DOUBLE PRECISION NULL,
plus_di_14 DOUBLE PRECISION NULL,
minus_di_14 DOUBLE PRECISION NULL,
adx_14 DOUBLE PRECISION NULL,
macd_12_26 DOUBLE PRECISION NULL,
macd_signal_12_26_9 DOUBLE PRECISION NULL,
macd_histogram_12_26_9 DOUBLE PRECISION NULL,
volume_avg_20 DOUBLE PRECISION NULL,
volume_avg_60 DOUBLE PRECISION NULL,
dollar_volume_avg_20 DOUBLE PRECISION NULL,
consecutive_up_days INTEGER NOT NULL,
consecutive_down_days INTEGER NOT NULL,
rel_spx DOUBLE PRECISION NULL,
pct_rel_spx_20 DOUBLE PRECISION NULL,
pct_rel_spx_50 DOUBLE PRECISION NULL,
relative_return_spx_20d_pct DOUBLE PRECISION NULL,
relative_return_spx_63d_pct DOUBLE PRECISION NULL,
relative_return_spx_126d_pct DOUBLE PRECISION NULL,
relative_return_spx_252d_pct DOUBLE PRECISION NULL,
spx_beta_60d DOUBLE PRECISION NULL,
spx_beta_252d DOUBLE PRECISION NULL,
spx_correlation_60d DOUBLE PRECISION NULL,
spx_correlation_252d DOUBLE PRECISION NULL,

dollar_volume DOUBLE PRECISION
    GENERATED ALWAYS AS (
        abs(close::DOUBLE PRECISION) * volume::DOUBLE PRECISION
    ) STORED,
intraday_return_1d_pct DOUBLE PRECISION
    GENERATED ALWAYS AS (
        close::DOUBLE PRECISION
            / NULLIF(open::DOUBLE PRECISION, 0.0) - 1.0
    ) STORED,
daily_range_pct DOUBLE PRECISION
    GENERATED ALWAYS AS (
        (high::DOUBLE PRECISION - low::DOUBLE PRECISION)
            / NULLIF(abs(close::DOUBLE PRECISION), 0.0)
    ) STORED,
close_location_1d DOUBLE PRECISION
    GENERATED ALWAYS AS (
        (close::DOUBLE PRECISION - low::DOUBLE PRECISION)
            / NULLIF(
                high::DOUBLE PRECISION - low::DOUBLE PRECISION,
                0.0
            )
    ) STORED,
pct_sma_20 DOUBLE PRECISION
    GENERATED ALWAYS AS (close::DOUBLE PRECISION / NULLIF(sma_20, 0.0) - 1.0) STORED,
pct_sma_50 DOUBLE PRECISION
    GENERATED ALWAYS AS (close::DOUBLE PRECISION / NULLIF(sma_50, 0.0) - 1.0) STORED,
pct_sma_200 DOUBLE PRECISION
    GENERATED ALWAYS AS (close::DOUBLE PRECISION / NULLIF(sma_200, 0.0) - 1.0) STORED,
pct_ema_20 DOUBLE PRECISION
    GENERATED ALWAYS AS (close::DOUBLE PRECISION / NULLIF(ema_20, 0.0) - 1.0) STORED,
pct_ema_50 DOUBLE PRECISION
    GENERATED ALWAYS AS (close::DOUBLE PRECISION / NULLIF(ema_50, 0.0) - 1.0) STORED,
pct_sma_20_vs_50 DOUBLE PRECISION
    GENERATED ALWAYS AS (sma_20 / NULLIF(sma_50, 0.0) - 1.0) STORED,
pct_sma_20_vs_200 DOUBLE PRECISION
    GENERATED ALWAYS AS (sma_20 / NULLIF(sma_200, 0.0) - 1.0) STORED,
pct_sma_50_vs_200 DOUBLE PRECISION
    GENERATED ALWAYS AS (sma_50 / NULLIF(sma_200, 0.0) - 1.0) STORED,
pct_hh_20 DOUBLE PRECISION
    GENERATED ALWAYS AS (close::DOUBLE PRECISION / NULLIF(hh_20, 0.0) - 1.0) STORED,
pct_hh_50 DOUBLE PRECISION
    GENERATED ALWAYS AS (close::DOUBLE PRECISION / NULLIF(hh_50, 0.0) - 1.0) STORED,
pct_hh_252 DOUBLE PRECISION
    GENERATED ALWAYS AS (close::DOUBLE PRECISION / NULLIF(hh_252, 0.0) - 1.0) STORED,
pct_ll_20 DOUBLE PRECISION
    GENERATED ALWAYS AS (close::DOUBLE PRECISION / NULLIF(ll_20, 0.0) - 1.0) STORED,
pct_ll_50 DOUBLE PRECISION
    GENERATED ALWAYS AS (close::DOUBLE PRECISION / NULLIF(ll_50, 0.0) - 1.0) STORED,
atr_pct_14 DOUBLE PRECISION
    GENERATED ALWAYS AS (atr_14 / NULLIF(abs(close::DOUBLE PRECISION), 0.0)) STORED,
bollinger_percent_b_20_2 DOUBLE PRECISION
    GENERATED ALWAYS AS (
        (
            close::DOUBLE PRECISION
            - (sma_20 - 2.0 * price_stddev_20)
        )
        / NULLIF(
            (sma_20 + 2.0 * price_stddev_20)
                - (sma_20 - 2.0 * price_stddev_20),
            0.0
        )
    ) STORED,
bollinger_bandwidth_20_2 DOUBLE PRECISION
    GENERATED ALWAYS AS (
        (
            (sma_20 + 2.0 * price_stddev_20)
                - (sma_20 - 2.0 * price_stddev_20)
        )
        / NULLIF(abs(sma_20), 0.0)
    ) STORED,
volume_ratio_20 DOUBLE PRECISION
    GENERATED ALWAYS AS (
        volume::DOUBLE PRECISION / NULLIF(volume_avg_20, 0.0)
    ) STORED,
macd_12_26_pct DOUBLE PRECISION
    GENERATED ALWAYS AS (macd_12_26 / NULLIF(abs(ema_26), 0.0)) STORED,
macd_histogram_12_26_9_pct DOUBLE PRECISION
    GENERATED ALWAYS AS (
        macd_histogram_12_26_9
            / NULLIF(abs(close::DOUBLE PRECISION), 0.0)
    ) STORED
```

The casts on copied `NUMERIC` inputs are deliberate. Python converts exact
source values directly to IEEE-754 double precision before analytical
calculation; generated arithmetic does the same rather than calculating in
arbitrary-precision numeric and casting only the final result. `NULLIF(...,
0.0)` implements the exact-zero denominator rule. SQL null propagation handles
nullable inputs, including volume. PostgreSQL owns all 23 expressions and the
Python writer must omit those columns.

The repeated Bollinger subexpressions preserve the formula specification's
floating-point evaluation order. They do not add query-time band columns or
change the formula owner.

## Published View Projection

`stonks.ohlcv_daily_tech_indicators` is a read-only view. S2.2 supplies the
membership joins and `UNION ALL`; every slot arm must project these 90 columns
explicitly in the physical order below. `SELECT *` is prohibited. Publication
or membership columns are not exposed.

```text
provider_listing_id
trading_date
relative_strength_benchmark_provider_listing_id
history_observation_count
calculation_version
run_id
calculated_at
created_at
updated_at
open
high
low
close
volume
return_1d_pct
return_2d_pct
return_3d_pct
return_5d_pct
return_10d_pct
return_20d_pct
return_63d_pct
return_126d_pct
return_252d_pct
gap_1d_pct
sma_20
sma_50
sma_200
ema_12
ema_20
ema_26
ema_50
sma_50_change_20d_pct
sma_200_change_20d_pct
hh_20
hh_50
hh_252
ll_20
ll_50
rsi_14
atr_14
return_volatility_20d_pct
return_volatility_60d_pct
return_1d_zscore_20d
return_3d_zscore_20d
price_stddev_20
plus_di_14
minus_di_14
adx_14
macd_12_26
macd_signal_12_26_9
macd_histogram_12_26_9
volume_avg_20
volume_avg_60
dollar_volume_avg_20
consecutive_up_days
consecutive_down_days
rel_spx
pct_rel_spx_20
pct_rel_spx_50
relative_return_spx_20d_pct
relative_return_spx_63d_pct
relative_return_spx_126d_pct
relative_return_spx_252d_pct
spx_beta_60d
spx_beta_252d
spx_correlation_60d
spx_correlation_252d
dollar_volume
intraday_return_1d_pct
daily_range_pct
close_location_1d
pct_sma_20
pct_sma_50
pct_sma_200
pct_ema_20
pct_ema_50
pct_sma_20_vs_50
pct_sma_20_vs_200
pct_sma_50_vs_200
pct_hh_20
pct_hh_50
pct_hh_252
pct_ll_20
pct_ll_50
atr_pct_14
bollinger_percent_b_20_2
bollinger_bandwidth_20_2
volume_ratio_20
macd_12_26_pct
macd_histogram_12_26_9_pct
```

The view exposes the physical `created_at` and `updated_at` values unchanged;
it does not substitute publication timestamps. It preserves exact source-copy
types and all physical column nullability.

## Metadata, Defaults, And Write Ownership

| Columns | PostgreSQL owner | Normal write behavior |
|---|---|---|
| `provider_listing_id`, `trading_date`, copied OHLCV | Python source reader/writer | supplied exactly from the owning `ohlcv_daily` row |
| benchmark ID, observation count, calculation version, run ID, `calculated_at` | Python calculator/workflow | supplied on insert; changed only for a non-equivalent calculated row |
| 53 historical/cross-series fields | Python calculator | supplied on insert/upsert, including intentional nulls |
| `created_at` | PostgreSQL default | omitted on insert; preserved on conflict and slot-equivalent copy |
| `updated_at` | PostgreSQL default plus Python persistence SQL | omitted on insert; set to the candidate calculation timestamp only for a non-equivalent update; preserved for unchanged and slot-equivalent copy |
| 23 generated fields | PostgreSQL stored expression | always omitted from insert/update/copy column lists |

`calculated_at` is the timezone-aware time at which the complete row values
were calculated. `updated_at` records when a changed current-state row was
persisted. `run_id` is nullable last-write lineage, not source ownership.
Neither slot stores a publication ID: active publication is normalized in the
S2.2 membership relation.

The only payload defaults are `now()` on `created_at` and `updated_at`.
Identifiers, counts, versions, calculation timestamps, source values, and
streaks never receive silent defaults. Logical warm-up values remain explicit
nulls.

## SQL Comment Contract

S2.5 must comment both payload tables, the published view, and every column.
The following text is canonical; plural column groups expand to one identical
comment per named column except for the column name itself.

Table A and B comment:

```text
Physical provider-native daily tech-indicator payload slot; package-written,
current-state data selected through stonks.ohlcv_daily_tech_indicators.
```

Published view comment:

```text
Read-only published provider-native daily tech-indicator rows selected by
active complete per-listing publication membership.
```

| Columns | Required column comment |
|---|---|
| `provider_listing_id` | Subject provider-listing UUID; source-row identity and ownership key. |
| `trading_date` | Provider trading date; source-row identity and observation date. |
| `relative_strength_benchmark_provider_listing_id` | Resolved SPX provider-listing UUID for supported subjects; null for unsupported subjects. |
| `history_observation_count` | Positive chronological subject-observation count through this row. |
| `calculation_version` | Immutable formula-profile identifier used to calculate this row. |
| `run_id` | Nullable Core run UUID for the last calculation write; non-owning lineage. |
| `calculated_at` | Time at which this row's feature values were calculated. |
| `created_at` | Time at which this physical payload row was created. |
| `updated_at` | Time at which this physical payload row last changed equivalently significant state. |
| `open`, `high`, `low`, `close` | Exact provider-native source price copied from the owning OHLCV row. |
| `volume` | Nullable provider-native source volume copied from the owning OHLCV row. |
| `return_1d_pct`, `return_2d_pct`, `return_3d_pct`, `return_5d_pct`, `return_10d_pct`, `return_20d_pct`, `return_63d_pct`, `return_126d_pct`, `return_252d_pct`, `gap_1d_pct` | Python-calculated decimal return ratio; 0.05 means five percent. |
| `sma_20`, `sma_50`, `sma_200`, `ema_12`, `ema_20`, `ema_26`, `ema_50`, `hh_20`, `hh_50`, `hh_252`, `ll_20`, `ll_50` | Python-calculated provider-native price-level feature. |
| `sma_50_change_20d_pct`, `sma_200_change_20d_pct` | Python-calculated 20-observation moving-average change ratio. |
| `rsi_14`, `plus_di_14`, `minus_di_14`, `adx_14` | Python-calculated pinned TA-Lib point-scale feature. |
| `atr_14`, `price_stddev_20`, `macd_12_26`, `macd_signal_12_26_9`, `macd_histogram_12_26_9` | Python-calculated provider-native price-distance feature. |
| `return_volatility_20d_pct`, `return_volatility_60d_pct` | Python-calculated non-annualized sample standard deviation of decimal returns. |
| `return_1d_zscore_20d`, `return_3d_zscore_20d` | Python-calculated signed standard-deviation units against the prior 20 returns. |
| `volume_avg_20`, `volume_avg_60` | Python-calculated complete-window provider-native volume average. |
| `dollar_volume_avg_20` | Python-calculated nominal provider-native price-times-volume average; not necessarily USD. |
| `consecutive_up_days`, `consecutive_down_days` | Python-calculated nonnegative current observation streak count. |
| `rel_spx` | Python-calculated exact-date aligned subject-close to SPX-close ratio. |
| `pct_rel_spx_20`, `pct_rel_spx_50` | Python-calculated aligned SPX price-ratio trend distance. |
| `relative_return_spx_20d_pct`, `relative_return_spx_63d_pct`, `relative_return_spx_126d_pct`, `relative_return_spx_252d_pct` | Python-calculated compounded exact-date aligned subject-versus-SPX return ratio. |
| `spx_beta_60d`, `spx_beta_252d` | Python-calculated sample-covariance beta over complete aligned returns. |
| `spx_correlation_60d`, `spx_correlation_252d` | Python-calculated Pearson correlation over complete aligned returns. |
| `dollar_volume` | PostgreSQL-generated absolute close times volume; nominal provider-native units, not necessarily USD. |
| `intraday_return_1d_pct`, `daily_range_pct`, `pct_sma_20`, `pct_sma_50`, `pct_sma_200`, `pct_ema_20`, `pct_ema_50`, `pct_sma_20_vs_50`, `pct_sma_20_vs_200`, `pct_sma_50_vs_200`, `pct_hh_20`, `pct_hh_50`, `pct_hh_252`, `pct_ll_20`, `pct_ll_50`, `atr_pct_14`, `macd_12_26_pct`, `macd_histogram_12_26_9_pct` | PostgreSQL-generated decimal ratio using exact-zero denominator nulling. |
| `close_location_1d` | PostgreSQL-generated close location within the same-row high-low range. |
| `bollinger_percent_b_20_2` | PostgreSQL-generated location within reconstructed 20-observation, two-standard-deviation bands. |
| `bollinger_bandwidth_20_2` | PostgreSQL-generated reconstructed band width divided by absolute SMA 20. |
| `volume_ratio_20` | PostgreSQL-generated current volume divided by 20-observation average volume. |

Migration comments may prefix a comment with `Python-calculated` or
`PostgreSQL-generated` exactly as stated above, but must not call any provider
value adjusted, normalized, canonical, consolidated, total-return, or USD.
View-column comments inherit the payload semantics; PostgreSQL does not require
duplicate `COMMENT ON COLUMN` statements for view columns when the view SQL and
view-level comment preserve this contract.

## Ownership And Count Ledger

Every column has exactly one formula or lifecycle owner:

| Group | Count | Owner |
|---|---:|---|
| identity, lineage, and timestamps | 9 | source key, Python workflow, or PostgreSQL lifecycle as named above |
| copied OHLCV | 5 | upstream source row copied by Python |
| historical/cross-series fields | 53 | Python calculator |
| stored same-row formulas | 23 | PostgreSQL generated expressions |
| **payload/view total** | **90** | — |

The package write payload remains 65 columns: 2 source keys, 5 copied source
values, 5 calculator/lineage values, and 53 Python fields. PostgreSQL adds the
two lifecycle timestamps and 23 generated fields. No column is calculated by
both Python and PostgreSQL.

## S2.5 Handoff Checks

The migration and schema tests must prove at least:

1. both payload slots expose identical ordered 90-column signatures;
2. the published view exposes the same ordered names and declared types;
3. the package write list contains exactly the 65 non-generated,
   non-database-default fields;
4. generated columns are stored, use the expressions above, propagate nulls,
   and agree with the Python reference tolerance;
5. copied source types match the live `stonks.ohlcv_daily` types exactly;
6. no adjusted value, upstream convenience, publication marker, recurrence
   state, provider descriptor, or strategy field enters the payload/view; and
7. table/view/column comments preserve provider-native semantics and formula
   ownership.

Any name, order, type, nullability, default, expression, ownership, or
projection change is a feature-profile change and requires an explicit
contract amendment before the Flyway migration.
