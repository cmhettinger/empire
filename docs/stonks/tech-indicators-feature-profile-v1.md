# Tech-Indicators Feature Profile V1

Status: frozen implementation contract for P0.3 as of 2026-08-09.

This document converts the ratified tech-indicators inventory into the
exact V1 row profile. It is authoritative for field presence, ownership,
units, and logical nullability. The design contract remains authoritative for
architecture and rollout sequencing. P0.4 freezes exact formulas,
complete-window mechanics, TA-Lib warm-up normalization, tolerance, and
denominator behavior in
[`tech-indicators-formula-spec-v1.md`](tech-indicators-formula-spec-v1.md).
Provider eligibility and the limits on adjustment, currency, corporate-action,
and cross-listing claims are frozen in
[`tech-indicators-source-value-policy-v1.md`](tech-indicators-source-value-policy-v1.md).

## Profile Rules

- The main table is `stonks.ohlcv_daily_tech_indicators`.
- One row is persisted for every source bar selected by the calculator, even
  when the history is too short to populate analytical fields.
- The row contains 90 columns: 9 identity/lineage columns, 5 copied OHLCV
  columns, 53 Python-computed columns, and 23 PostgreSQL `STORED` generated
  columns.
- A `_pct` suffix means a decimal ratio, not percentage points. For example,
  `0.05` means five percent.
- Price-level values remain in the provider-native price unit. Volume-level
  values remain in the provider-native volume unit.
- `dollar_volume` names a nominal provider-native price-times-volume product;
  it does not assert USD denomination or cross-provider comparability and is
  approved only as a within-listing time-series feature in V1.
- `rsi_14`, `plus_di_14`, `minus_di_14`, and `adx_14` use TA-Lib's point scale,
  conventionally 0 through 100, rather than decimal ratios.
- Return volatility is the non-annualized dispersion of one-observation
  decimal returns; the formula specification freezes its sample estimator and
  exact window mechanics.
- Expected warm-up, missing-input, zero-denominator, zero-variance, or
  unsupported-benchmark conditions are represented by SQL `NULL`, never by a
  sentinel zero. Unexpected invalid calculator output fails validation rather
  than being silently coerced.
- Python owns every historical or cross-series calculation. PostgreSQL owns
  only deterministic same-row arithmetic through `STORED` generated columns.
  Generated columns never appear in calculator upsert column lists.

## Persisted Identity, Lineage, And Source Copy

| Column | Owner | Unit / meaning | Logical nullability |
|---|---|---|---|
| `provider_listing_id` | source key | UUID for the source listing | `NOT NULL` |
| `trading_date` | source key | provider trading date | `NOT NULL` |
| `relative_strength_benchmark_provider_listing_id` | calculator lineage | UUID for the aligned SPX benchmark listing | nullable when the subject is unsupported under the [`tech-indicators-spx-contract-v1.md`](tech-indicators-spx-contract-v1.md) contract |
| `history_observation_count` | Python calculator | count of source observations available through this row | `NOT NULL`, positive integer |
| `calculation_version` | calculator lineage | frozen implementation version; V1 is `TECH_INDICATORS_V1` | `NOT NULL` |
| `run_id` | Core lineage | optional UUID of the last writing Core run | nullable for optional Core lineage and after `core.run` cleanup through `ON DELETE SET NULL` |
| `calculated_at` | calculator lineage | timestamptz for feature calculation | `NOT NULL` |
| `created_at` | database | row creation timestamptz | `NOT NULL` |
| `updated_at` | database / upsert | latest persisted calculation timestamptz | `NOT NULL` |
| `open` | source copy | provider-native price | `NOT NULL` |
| `high` | source copy | provider-native price | `NOT NULL` |
| `low` | source copy | provider-native price | `NOT NULL` |
| `close` | source copy | provider-native price | `NOT NULL` |
| `volume` | source copy | provider-native volume | nullable exactly when the source bar volume is null |

The primary row identity is `(provider_listing_id, trading_date)`. Source-copy
values represent the source bar used by the current calculation version. The
exact correction and refresh workflow is frozen in
[`tech-indicators-recalculation-contract-v1.md`](tech-indicators-recalculation-contract-v1.md).

## Persisted Python-Computed Fields

Every field in this section is inserted or updated by the reusable Python
calculator. Unless explicitly marked `NOT NULL`, it is logically nullable for
complete-window warm-up or another expected condition listed in the profile
rules.

| Columns | Unit / meaning | Logical nullability |
|---|---|---|
| `return_1d_pct`, `return_2d_pct`, `return_3d_pct`, `return_5d_pct`, `return_10d_pct`, `return_20d_pct`, `return_63d_pct`, `return_126d_pct`, `return_252d_pct` | decimal close-return ratios | nullable |
| `gap_1d_pct` | decimal open-versus-prior-close ratio | nullable |
| `sma_20`, `sma_50`, `sma_200` | provider-native price | nullable |
| `ema_12`, `ema_20`, `ema_26`, `ema_50` | provider-native price | nullable |
| `sma_50_change_20d_pct`, `sma_200_change_20d_pct` | decimal ratios | nullable |
| `hh_20`, `hh_50`, `hh_252` | provider-native high-price level | nullable |
| `ll_20`, `ll_50` | provider-native low-price level | nullable |
| `rsi_14` | TA-Lib points | nullable |
| `atr_14` | provider-native price distance | nullable |
| `return_volatility_20d_pct`, `return_volatility_60d_pct` | non-annualized decimal return dispersion | nullable |
| `return_1d_zscore_20d`, `return_3d_zscore_20d` | signed standard-deviation units | nullable |
| `price_stddev_20` | provider-native price distance | nullable |
| `plus_di_14`, `minus_di_14`, `adx_14` | TA-Lib points | nullable |
| `macd_12_26`, `macd_signal_12_26_9`, `macd_histogram_12_26_9` | provider-native price distance | nullable |
| `volume_avg_20`, `volume_avg_60` | provider-native volume | nullable |
| `dollar_volume_avg_20` | nominal provider-native price-times-volume | nullable |
| `consecutive_up_days`, `consecutive_down_days` | count of observations in the current streak | `NOT NULL`, nonnegative integer |
| `rel_spx` | subject close divided by aligned SPX close | nullable |
| `pct_rel_spx_20`, `pct_rel_spx_50` | decimal ratios | nullable |
| `relative_return_spx_20d_pct`, `relative_return_spx_63d_pct`, `relative_return_spx_126d_pct`, `relative_return_spx_252d_pct` | decimal subject-minus-SPX return ratios | nullable |
| `spx_beta_60d`, `spx_beta_252d` | dimensionless covariance ratios | nullable |
| `spx_correlation_60d`, `spx_correlation_252d` | dimensionless correlations | nullable |

The two streak fields are the only analytical fields that are logically
`NOT NULL`; their initial and reset behavior is frozen by the formula
specification. SPX-family fields remain nullable until the SPX contract's
benchmark-support and alignment conditions are satisfied. Aligned-observation
diagnostics belong to calculation/report diagnostics and are not additional
persisted feature columns in V1.

## Persisted PostgreSQL Generated Fields

Every field in this section is a PostgreSQL `GENERATED ALWAYS AS (...) STORED`
column. All are logically nullable because either an input can be null or a
valid same-row denominator can be zero. The formula specification freezes the
expression semantics; S2.1 maps them to exact PostgreSQL DDL and types.

| Columns | Unit / meaning |
|---|---|
| `dollar_volume` | nominal provider-native price-times-volume |
| `intraday_return_1d_pct` | decimal close-versus-open ratio |
| `daily_range_pct` | decimal high-low range ratio |
| `close_location_1d` | dimensionless close location within the daily range |
| `pct_sma_20`, `pct_sma_50`, `pct_sma_200` | decimal close-versus-SMA ratios |
| `pct_ema_20`, `pct_ema_50` | decimal close-versus-EMA ratios |
| `pct_sma_20_vs_50`, `pct_sma_20_vs_200`, `pct_sma_50_vs_200` | decimal moving-average spread ratios |
| `pct_hh_20`, `pct_hh_50`, `pct_hh_252` | decimal close-versus-window-high ratios |
| `pct_ll_20`, `pct_ll_50` | decimal close-versus-window-low ratios |
| `atr_pct_14` | decimal ATR-versus-close ratio |
| `bollinger_percent_b_20_2` | dimensionless location between the reconstructed bands |
| `bollinger_bandwidth_20_2` | decimal band-width-versus-middle-band ratio |
| `volume_ratio_20` | dimensionless volume-versus-average ratio |
| `macd_12_26_pct`, `macd_histogram_12_26_9_pct` | decimal MACD-versus-normalizer ratios |

There is no Python fallback owner for these columns. If an expression cannot
be implemented cleanly as a PostgreSQL stored generated expression, the
profile must be amended explicitly before S2.1 rather than silently changing
ownership.

## Query-Time and Deliberately Non-Persisted Values

| Value family | V1 treatment |
|---|---|
| Bollinger upper and lower band levels | reconstruct at query/report time from `sma_20` and `price_stddev_20` |
| Strategy predicates such as trend, breakout, liquidity, overbought, or oversold flags | evaluate at query/report time |
| Cross-sectional ranks, percentiles, and screen-specific scores | evaluate at query/report time |
| The SPX row's own technical features and repeated market-context columns | query once for the reporting date; do not copy into every subject row |
| Aligned SPX observation counts and calculation diagnostics | emit through calculator/report diagnostics; do not add feature columns |
| Provider, market, symbol, instrument, and listing-status descriptors | join from securities reference tables when required |
| Upstream `change`, `changepct`, `typ`, `hl_range`, and `oc_range` | do not copy or use as calculation inputs |
| Adjusted close, provider adjustment assumptions, and provider volume-basis metadata | not available in the current OHLCV contract; do not invent |
| TA-Lib internal intermediates and temporary aligned arrays | calculator-local only |

## Null and Row-Presence Contract

- Incomplete history does not suppress an otherwise selected source row.
- Warm-up nulls are field-level and deterministic for a fixed source snapshot
  and calculation version.
- Missing volume propagates only into volume-dependent fields; it does not
  invalidate unrelated price fields or the row itself.
- An unsupported or insufficiently aligned SPX relationship leaves the SPX
  family null under the SPX contract; it never substitutes zeros or a different
  benchmark. Invalid benchmark identity fails preflight for supported scopes.
- Exact-zero denominators and zero-variance windows produce null where required
  by the formula specification.
- `run_id` becoming null after Core retention cleanup does not alter feature
  values, row identity, or `calculation_version`.
- Source-bar deletion remains ownership-driven through the source foreign key;
  Core run cleanup is not row ownership.

## Count Ledger

| Ownership group | Column count |
|---|---:|
| Identity, lineage, and timestamps | 9 |
| Copied OHLCV | 5 |
| Python-computed | 53 |
| PostgreSQL stored generated | 23 |
| **Total persisted V1 columns** | **90** |

Any addition, removal, rename, unit change, nullability change, or ownership
change alters the frozen V1 profile and requires an explicit contract update.
