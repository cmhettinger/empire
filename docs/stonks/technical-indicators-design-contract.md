# Daily Technical Indicators Design Contract

## Status And Purpose

This document preserves the agreed design baseline for Empire's first daily
technical-indicator capability. It is the required input to the
[technical indicators package action plan](../todo/tech-ind-task-plan.md), not
a retrospective or an invitation to rediscover the scope in each task.

Implementation tasks may refine a formula where this document explicitly
records an open decision, or revise the design when evidence proves a problem.
Material changes must update this contract and explain the evidence. The
package boundary, provider-native grain, read-optimized persistence strategy,
initial feature families, SPX identity, validation split, and deferred families
are already selected.

No table or package described here exists yet. The active task plan controls
implementation order and verification.

## Selected Architecture

The reusable package is:

```text
distribution: empire-stonks-technicals
import:       empire_stonks_technicals
location:     packages/empire-stonks-technicals
```

The dependency direction is:

```text
empire-stonks-ohlcv
        |
        v
stonks.ohlcv_daily
        |
        v
empire-stonks-technicals
        |
        v
stonks.ohlcv_daily_technicals
        |
        v
reports / target screens / future backtests
```

`empire-stonks-ohlcv` owns provider acquisition, parsing, listing identity,
daily-bar persistence, and source semantics. It must not import technicals.

`empire-stonks-technicals` owns chronological input reads, benchmark
resolution, calculations, validation, recalculation planning, feature
persistence, operational queries, Core runners, reports, and thin commands.

Strategies and future backtests consume stored features. They own thresholds,
target labels, execution timing, portfolio construction, costs, and scoring.
Airflow only invokes package workflows.

## Provider-Native Identity And Source Semantics

The initial technical grain is one provider-native series and date:

```text
(provider_listing_id, trading_date)
```

It does not use canonical `stonks.listing`, merge providers, or assert that a
provider ticker represented one real-world listing through all history.

Indicators inherit the owning provider series' adjustment and correction
semantics. The technical package does not reconstruct splits, distributions,
or adjusted histories. A split or other discontinuity in an unadjusted series
can affect returns, averages, volatility, RSI, ATR, Bollinger state, breakouts,
and model signals. The initial eligible-source policy must therefore be audited
and reported rather than assumed.

The table is current calculated state. It does not preserve technical
revisions. Source corrections and calculation-version changes update affected
rows through a deterministic rebuild policy.

## Primary Table Shape

The selected primary table is:

```text
stonks.ohlcv_daily_technicals
```

Its primary key is `(provider_listing_id, trading_date)`. The same composite
columns reference `stonks.ohlcv_daily` with deletion cascading from the owning
bar. The row also carries a nullable FK to the provider listing used as the
relative-strength benchmark and a nullable FK to `core.core_run`.

The table is a wide, read-optimized feature store. Storage minimization is not
the goal, but width still affects I/O and must be measured. Features requiring
historical windows, recursive state, or cross-series alignment are calculated
once and stored. Strategy thresholds remain query-time comparisons.

The row copies source open, high, low, close, and volume so an ordinary daily
target scan does not join `ohlcv_daily`. The Python writer must prove copied
values agree with the owning source bar.

An additional recurrence-state table is not selected by default. It may be
added only if the recursive-equivalence prototype proves it is required for
exact and performant EMA, RSI, ATR, ADX, or MACD updates.

## Type And Validation Decisions

- Copied OHLCV values retain source-compatible exact `NUMERIC` types.
- Derived analytical features normally use `DOUBLE PRECISION` for TA-Lib,
  NumPy, comparison, sorting, and storage performance.
- Percentage-named values contain ratios: `0.05` is 5 percent.
- Missing or insufficient-history output is SQL null, never zero.
- Python is the only supported normal writer and performs exhaustive finite,
  formula, source-consistency, warm-up, and benchmark validation.
- An invalid internally calculated batch fails; it is not treated as dirty
  vendor input and invalid values are not silently changed to null.
- PostgreSQL retains structural integrity: PK/FKs, delete actions, calculation
  version shape, basic bounds, streak shape, and relative-field dependencies.
- The migration does not need one enormous constraint repeating every float
  column for `NaN` and infinities.

Cheap deterministic same-row arithmetic may use PostgreSQL `STORED` generated
columns. This keeps reads fast and prevents Python from persisting inconsistent
copies of formulas derivable from the same row.

## Column Ownership Baseline

The exact Flyway DDL is finalized in Phase 2, but tasks should begin from this
ownership split.

### Identity And Metadata

| Column | Owner and intent |
|--------|------------------|
| `provider_listing_id` | Subject provider series; part of PK and source-bar FK |
| `trading_date` | Provider trading date; part of PK and source-bar FK |
| `relative_strength_benchmark_provider_listing_id` | Nullable benchmark provider listing FK |
| `history_observation_count` | Python-calculated subject history sufficiency |
| `calculation_version` | Required uppercase/trimmed formula profile version |
| `run_id` | Nullable Core run FK for the last calculation write |
| `calculated_at` | Time the feature values were calculated |
| `created_at`, `updated_at` | Current-state persistence timestamps |

### Copied Source Values

```text
open
high
low
close
volume
```

### Python-Calculated Historical Or Cross-Series Values

```text
return_1d_pct, return_2d_pct, return_3d_pct, return_5d_pct
return_10d_pct, return_20d_pct, return_63d_pct
return_126d_pct, return_252d_pct
gap_1d_pct
sma_20, sma_50, sma_200
ema_12, ema_20, ema_26, ema_50
sma_50_change_20d_pct, sma_200_change_20d_pct
hh_20, hh_50, hh_252
ll_20, ll_50
rsi_14
atr_14
return_volatility_20d_pct, return_volatility_60d_pct
return_1d_zscore_20d, return_3d_zscore_20d
price_stddev_20
plus_di_14, minus_di_14, adx_14
macd_12_26, macd_signal_12_26_9, macd_histogram_12_26_9
volume_avg_20, volume_avg_60, dollar_volume_avg_20
consecutive_up_days, consecutive_down_days
rel_spx, pct_rel_spx_20, pct_rel_spx_50
relative_return_spx_20d_pct, relative_return_spx_63d_pct
relative_return_spx_126d_pct, relative_return_spx_252d_pct
spx_beta_60d, spx_correlation_60d
spx_beta_252d, spx_correlation_252d
```

Phase 1 may move a recursive output between Python-calculated and generated
ownership only if the pinned TA-Lib equivalence proof supports it.

### Stored Same-Row Derived Candidates

```text
dollar_volume
intraday_return_1d_pct
daily_range_pct
close_location_1d
pct_sma_20, pct_sma_50, pct_sma_200
pct_ema_20, pct_ema_50
pct_sma_20_vs_50, pct_sma_20_vs_200, pct_sma_50_vs_200
pct_hh_20, pct_hh_50, pct_hh_252
pct_ll_20, pct_ll_50
atr_pct_14
bollinger_percent_b_20_2
bollinger_bandwidth_20_2
volume_ratio_20
macd_12_26_pct
macd_histogram_12_26_9_pct
```

These should be `STORED` generated columns when PostgreSQL supports the exact
agreed expression cleanly. Otherwise Python may write them, but the choice must
be explicit and formula-tested.

## Formula Baseline

Phase 0 must turn these definitions into exact tests. It should not choose a
different feature concept without updating this contract.

### Observation Windows And Returns

Lookbacks count ordered stored observations for the subject, not calendar-day
offsets:

```text
return_Nd_pct = close(t) / close(t-N observations) - 1
```

The result is null before the lag exists or when the agreed denominator policy
rejects the prior close. Calculations at date `t` never read dates after `t`.

```text
gap_1d_pct = open(t) / close(t-1 observation) - 1
intraday_return_1d_pct = close(t) / open(t) - 1
daily_range_pct = (high(t) - low(t)) / abs(close(t))
close_location_1d = (close(t) - low(t)) / (high(t) - low(t))
```

Zero denominators yield null. An unchanged close resets both streaks to zero;
otherwise the current date is included in the applicable streak.

### Moving Averages And Trend Distances

```text
pct_sma_N = close / sma_N - 1
pct_ema_N = close / ema_N - 1
pct_sma_short_vs_long = sma_short / sma_long - 1

sma_N_change_20d_pct =
    sma_N(t) / sma_N(t-20 observations) - 1
```

SMA periods are 20, 50, and 200. EMA periods are 12, 20, 26, and 50. TA-Lib
initialization and unstable-period behavior are pinned by calculation version.

### Recent High And Low Relationships

The current observation is included:

```text
hh_N = maximum(high over N observations)
ll_N = minimum(low over N observations)
pct_hh_N = close / hh_N - 1
pct_ll_N = close / ll_N - 1
```

High windows are 20, 50, and 252. Low windows are 20 and 50.

### Volatility, Momentum, And Bands

RSI 14, ATR 14, +DI 14, -DI 14, and ADX 14 use the pinned TA-Lib/Wilder
contract. ATR percentage is:

```text
atr_pct_14 = atr_14 / abs(close)
```

Return volatility uses rolling one-observation returns. Phase P0.4 must select
sample versus population deviation and confirm whether values remain daily or
are annualized; the selected column names must make that unit unambiguous.

The z-score columns use a 20-observation reference distribution. P0.4 must
freeze whether the current return participates in that distribution. Zero
standard deviation yields null.

Bollinger uses the pinned TA-Lib 20-observation, 2-standard-deviation contract:

```text
middle = sma_20
upper = sma_20 + 2 * price_stddev_20
lower = sma_20 - 2 * price_stddev_20
bollinger_percent_b_20_2 = (close - lower) / (upper - lower)
bollinger_bandwidth_20_2 = (upper - lower) / abs(middle)
```

Upper and lower bands are not stored because they are exact reconstructions of
stored inputs.

MACD uses 12/26/9. The pinned TA-Lib outputs own the raw line, signal, and
histogram. Normalized values are intended for cross-sectional comparison:

```text
macd_12_26_pct = macd_12_26 / abs(ema_26)
macd_histogram_12_26_9_pct = macd_histogram_12_26_9 / abs(close)
```

Phase B1.2 must verify whether independently stored EMA 12/26 values reproduce
TA-Lib's MACD line at every accepted date before any generated-column shortcut
is used.

### Volume And Liquidity

Missing provider volume stays null. It is never converted to zero.

```text
dollar_volume = abs(close) * volume
volume_avg_N = average(volume over a complete N-observation window)
dollar_volume_avg_20 = average(dollar_volume over 20 observations)
volume_ratio_20 = volume / volume_avg_20
```

Volume windows are 20 and 60. Phase P0.6 must state which source/instrument
types make dollar-volume comparisons meaningful.

## SPX Benchmark Contract

The initial broad benchmark is resolved by stable provider identity:

```text
provider_code = YAHOO
market = XIDX
ticker = SPX
metadata.YahooTicker = ^GSPC
```

The generated UUID and Yahoo request symbol are not hardcoded as identity.
Resolution must find exactly one reviewed eligible provider listing and fail
closed on absence, duplication, inactivity, or material metadata drift.

Subject and SPX rows align only where both have the exact trading date. No
forward fill, nearest date, synthetic holiday row, or calendar coercion is
allowed.

```text
rel_spx = subject_close / spx_close

pct_rel_spx_N =
    rel_spx / sma(rel_spx, N aligned observations) - 1

relative_return_spx_N =
    (1 + subject_return_N) / (1 + spx_return_N) - 1

spx_beta_N =
    sample_covariance(subject_1d_return, spx_1d_return)
    / sample_variance(spx_1d_return)

spx_correlation_N =
    Pearson correlation of aligned subject and SPX 1d returns
```

Relative-return windows are 20, 63, 126, and 252. Beta/correlation windows are
60 and 252. They require complete aligned windows; zero benchmark variance or
insufficient alignment yields null. Correlation must remain within `[-1, 1]`
subject to an explicitly tested floating tolerance. Beta has no arbitrary
database bound.

SPX features are not automatically meaningful for every global index,
currency, commodity, or futures series. Phase P0.5/P0.6 must freeze the initial
eligible subject policy. Unsupported subjects retain null SPX fields.

Sector-relative features remain deferred until Empire owns point-in-time
subject membership and benchmark mappings.

## Query-Time Versus Stored Decisions

Historical windows, recursion, and cross-series values are stored. Simple
strategy rules remain query-time expressions:

```text
close > sma_200
sma_50 > sma_200
rsi_14 > configured threshold
return_3d_pct <= configured threshold
pct_hh_20 between configured bounds
dollar_volume_avg_20 >= configured threshold
```

The table does not persist `above_sma_*`, `rsi_gt_70`, `rsi_lt_30`, model target
flags, or other threshold-specific booleans. Market context reads the SPX
technical row once; it is not copied into every subject row.

## Initial Index Direction

The baseline access paths are:

```text
PRIMARY KEY (provider_listing_id, trading_date)
date-leading latest-day scan index
```

Candidate ranking indexes include RSI, average dollar volume, and SPX-relative
return, but Phase S2.4 must require representative `EXPLAIN` evidence. The
design deliberately rejects:

- One index per indicator.
- A broad covering index containing most feature columns.
- Low-selectivity multi-boolean indexes.
- Strategy-threshold partial indexes before a stable consumer exists.

A latest-day slice of tens of thousands of precomputed rows should normally be
cheap. Index count must balance read evidence against daily/backfill write cost.

## Recalculation And Performance Direction

Repeated target queries must not execute rolling windows. The package computes
features once, validates them, bulk persists them, and lets screens compare
stored values.

Daily append, source correction, SPX correction, missing technical row, and
calculation-version change are separate work-planning cases. Recursive
indicators make correction replay nontrivial: a historical input can affect a
suffix beyond its nominal period. Phase B1.2 must prove an exact strategy before
the state schema is frozen.

Required properties are:

- Full rebuild and accepted incremental output agree within the frozen numeric
  tolerance.
- Daily work is bounded by listing/date batches with controlled memory.
- Historical backfill is resumable with deterministic cursors and independent
  commits.
- Source bars are never mutated by technical calculation.
- Invalid internally generated values fail the active batch.
- Version changes cause explicit recalculation rather than mixed semantics.

TA-Lib is selected because its native calculations materially reduce Empire
formula code and are fast over contiguous arrays. Empire still owns input
ordering, formula parameters, warm-up interpretation, versioning, validation,
persistence, and independent regression tests.

## Publication, Readiness, And Concurrency Contract

Calculation completion and feature publication are separate concepts. A
successful calculation run must not make a partially refreshed effective date,
mixed calculation versions, incomplete SPX-relative results, or a partially
rebuilt scope available to model consumers as ready data.

Phase P0.9 must define the V1 publication unit and readiness predicate for
daily refreshes, corrections, and backfills. The implementation may use one
database transaction when that meets the performance gate, or an explicit
staging/generation and atomic publication mechanism when bounded commits are
required. A completion marker by itself is insufficient if current-state rows
can be overwritten and expose mixed semantics before the marker changes. The
selected mechanism must preserve these invariants:

- A consumer observes either the previously complete publication or the newly
  complete publication, never an in-progress mixture.
- One published unit has one calculation version and one resolved benchmark
  contract.
- Model-input and readiness queries fail closed unless the requested
  scope/effective date/version/benchmark coverage is published as complete.
- Resumable backfill progress may be inspectable, but incomplete batches are
  not advertised as a complete model-input publication.
- Failure or cancellation rolls back the active atomic unit or leaves its
  staged generation unpublished; it cannot advance readiness.
- Publication state, if required, is package-owned durable data with database
  constraints and is covered by Flyway, cleanup, and recovery contracts.

Concurrency protection also belongs to the package. Airflow
`max_active_runs`, pools, and task coordination are useful secondary controls,
but do not protect against simultaneous CLI runs, manual DAG runs, source
reruns, or backfills.

Phase P0.10 must freeze a PostgreSQL-backed lock contract, normally advisory
locking, with a deterministic identity derived from job kind, calculation
version, provider/listing scope, and effective date or date range. Daily,
backfill, CLI, and Airflow paths must acquire the same conflicting lock before
readiness/planning and hold it through database publication. Lock contention
has a bounded, explicit fail-or-healthy-no-op policy; runners do not wait
indefinitely. Scope normalization must make any jobs capable of writing the
same current-state rows conflict, including different job kinds and calculation
versions; version cannot partition locks that protect the same rows. Tests must
cover overlapping and nonoverlapping scopes, lock release after
success/failure/cancellation, and recovery after process or database-session
loss.

## Run Reports And Operational Surfaces

The package provides daily and historical-backfill Core runners, package
commands, `bin/` wrappers, and a thin Airflow DAG after the calculation and
persistence paths are proven.

Every substantive run produces durable:

```text
report.json
report.pdf
```

Reports include run/scope identity, calculation and TA-Lib/NumPy versions,
source readiness, provider/market/listing/date coverage, insert/update/unchanged
counts, warm-up and null coverage, benchmark coverage, warnings/failures,
timing, throughput, and bounded diagnostics. The PDF uses Empire branding and
renders the same operational facts professionally. Neither report is an
investment recommendation or a dump of feature rows.

Airflow coordination must join successful EODData and Yahoo/SPX readiness for
the same effective date. Task timing alone is insufficient. The package owns a
readiness decision, and repeated source runs must lead to idempotent,
nonconcurrent refresh behavior. Airflow must call the same package-owned
publication and locking paths as CLI and manual execution.

## Deliberately Deferred Features

The initial rollout does not include:

- Bollinger upper/lower columns, because they are reconstructible.
- Strategy flags or model-specific thresholds.
- Sector-relative returns without point-in-time mappings.
- Cross-sectional ranks without a historical universe contract.
- Stochastic, Williams `%R`, CCI, MFI, OBV, Chaikin A/D, Aroon, Parabolic SAR,
  Ichimoku, Keltner, named candlestick patterns, and cycle/Hilbert families.
- Intraday indicators or true session VWAP.
- Canonical or cross-provider-consensus technical histories.
- Append-only technical revision history.
- Portfolio/backtest execution and performance analytics.

These omissions are deliberate, not evidence that a family was overlooked.
The initial profile already covers returns, trend direction, trend strength,
momentum, range position, volatility, volatility regime, volume/liquidity,
bar structure, broad-market relative performance, beta, and correlation.

## Open Decisions Assigned To The Task Plan

The following require evidence and are already assigned to task IDs; future
chats should resolve them rather than reopen the entire design:

| Decision | Owning tasks |
|----------|--------------|
| Exact naming/version/report/object conventions | P0.2 |
| Final generated-column ownership and DDL types | S2.1-S2.3 |
| Sample/population and annualized/daily volatility | P0.4 |
| Z-score reference inclusion | P0.4 |
| Eligible source and SPX subject universes | P0.5-P0.6 |
| TA-Lib/NumPy versions and Airflow packaging | B1.1 |
| Recursive incremental/state-table strategy | B1.2, S2.2 |
| Initial evidence-backed indexes | S2.4 |
| Performance thresholds and batch sizes | P0.8, W7.9, V12.6 |
| Atomic publication unit and readiness predicate | P0.9, S2.2, W7.10 |
| Package-owned lock identity and contention policy | P0.10, J9.9 |
| Airflow source-completion coordination | A11.1-A11.8 |

Any new indicator or material formula change requires a concrete consumer,
versioned semantics, incremental behavior, storage/query justification, and an
independent regression reference.
