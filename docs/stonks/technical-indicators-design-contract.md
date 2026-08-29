# Daily Technical Indicators Design Contract

## Status And Purpose

This document preserves the agreed design baseline for Empire's first daily
technical-indicator capability. It is the required input to the
[technical indicators package action plan](../todo/tech-ind-task-plan.md), not
a retrospective or an invitation to rediscover the scope in each task.

P0.1 ratified this document on 2026-08-09 as the authoritative V1 baseline
after auditing the live OHLCV schema/package, completed OHLCV contracts, Core
run/object services, `empire-reports`, runtime wrappers, and Airflow DAGs. The
ratification confirms the selected scope and resolves live-convention
ambiguities below; it does not preempt the narrowly assigned open decisions at
the end of this document.

Implementation tasks may refine a formula where this document explicitly
records an open decision, or revise the design when evidence proves a problem.
Material changes must update this contract and explain the evidence. The
package boundary, provider-native grain, read-optimized persistence strategy,
initial feature families, SPX identity, validation split, and deferred families
are already selected.

As of ratification, no technical-indicator table or package described here
exists. The active task plan controls implementation order and verification.

## Ratified Live-Convention Handoff

The live repository establishes these implementation constraints for the V1
baseline:

- `stonks.ohlcv_daily` is provider-native current state keyed by
  `(provider_listing_id, trading_date)`. Its OHLC fields are
  `NUMERIC(30,10)`, volume is nullable `NUMERIC(30,8)`, its owning
  provider-listing FK cascades deletes, and corrections update only distinct
  source values. Technicals must read this table without mutating it.
- The upstream `change`, `changepct`, `typ`, `hl_range`, and `oc_range`
  columns remain OHLCV-owned daily conveniences. They are not copied into the
  V1 technical table and do not replace the technical package's chronological,
  versioned calculations.
- Individual OHLCV rows intentionally have no Core-run or source-snapshot
  lineage. Missing technical rows, copied-source drift, calculation-version
  drift, and source-row deletion are therefore detected from current source
  state; tech-indicator code must not invent unavailable per-bar provenance.
- Core integration uses injected `RunService`, `ObjectStore`, and database
  services with `domain="stonks"`. The technical row's nullable `run_id` is
  non-owning last-write lineage and uses `ON DELETE SET NULL`, consistent with
  cleanup-safe optional Core lineage; deleting a Core run must never delete a
  source or technical row.
- Domain code owns report facts, report-specific models and sections, Core
  object keys, object kinds, logical names, metadata, and retention.
  `empire-reports` owns reusable rendering contracts, branding, and PDF
  primitives. Technical JSON serialization is deterministic and rejects
  non-finite values before Core storage, matching the OHLCV domain serializers.
  Substantive run artifacts are durable run-scoped `report.json` and
  `report.pdf` objects stored through Core. P0.2 freezes their exact
  tech-indicator identifiers below.
- Reusable packages read configuration from `os.environ` and receive injected
  services. `bin` wrappers load environment files, and Airflow DAGs only
  construct runtime services, validate context/overrides, call package runners,
  and return compact secret-safe results.
- The reviewed SPX identity exists in the live Yahoo seed as active
  `YAHOO/XIDX/SPX` with `metadata.YahooTicker = ^GSPC`. Resolution remains by
  those stable facts and must not hardcode its generated UUID.
- Source semantics are intentionally unlike: EODData and Stooq adjustment and
  volume bases are unspecified, while Yahoo stores native unadjusted Chart
  OHLC and does not persist adjusted close. Technicals inherit and disclose
  those semantics. P0.6 freezes initial eligibility and comparability rules in
  [`tech-indicators-source-value-policy-v1.md`](tech-indicators-source-value-policy-v1.md).

These findings do not change the selected provider-native grain, wide
published current-state relation, initial feature inventory, formula direction,
SPX benchmark, validation split, publication/concurrency requirements, or
deferred families. A later contradiction with live implementation requires an
explicit contract amendment with evidence rather than an implicit task-level
departure.

## Selected Architecture

The reusable package is:

```text
distribution: empire-stonks-tech-indicators
import:       empire_stonks_tech_indicators
location:     packages/empire-stonks-tech-indicators
```

The dependency direction is:

```text
empire-stonks-ohlcv
        |
        v
stonks.ohlcv_daily
        |
        v
empire-stonks-tech-indicators
        |
        v
stonks.ohlcv_daily_tech_indicators
        |
        v
reports / target screens / future backtests
```

`empire-stonks-ohlcv` owns provider acquisition, parsing, listing identity,
daily-bar persistence, and source semantics. It must not import
`empire_stonks_tech_indicators`.

`empire-stonks-tech-indicators` owns chronological input reads, benchmark
resolution, calculations, validation, recalculation planning, feature
persistence, operational queries, Core runners, reports, and thin commands.

Strategies and future backtests consume stored features. They own thresholds,
target labels, execution timing, portfolio construction, costs, and scoring.
Airflow only invokes package workflows.

## Frozen Naming Contract

P0.2 selects `tech-indicators` as the only abbreviated capability stem for
code and operational identifiers. Do not introduce `technicals` or a fully
spelled `technical-indicators` variant. Human prose may continue to say
"technical indicators."

Use hyphens where the host convention permits them and underscores where it
does not:

| Surface | Frozen V1 identifier |
|---------|----------------------|
| Poetry distribution | `empire-stonks-tech-indicators` |
| Python import | `empire_stonks_tech_indicators` |
| Package directory | `packages/empire-stonks-tech-indicators` |
| Environment prefix | `EMPIRE_STONKS_TECH_INDICATORS_` |
| Published consumer view | `stonks.ohlcv_daily_tech_indicators` |
| Physical payload slot A | `stonks.ohlcv_daily_tech_indicators_a` |
| Physical payload slot B | `stonks.ohlcv_daily_tech_indicators_b` |
| Publication table | `stonks.tech_indicators_publication` |
| Publication membership table | `stonks.tech_indicators_publication_listing` |
| Writer-lock seed | `empire:stonks:tech-indicators:writer:v1` |
| Writer-lock key | `7681980501239933110` |
| Conditional recurrence-state table | `stonks.ohlcv_daily_tech_indicators_state` |
| Initial calculation version | `TECH_INDICATORS_V1` |
| Core domain | `stonks` |
| Daily Core job | `stonks_tech_indicators_daily` |
| Backfill Core job | `stonks_tech_indicators_backfill` |
| Storage-key environment variable | `EMPIRE_STORAGE_KEY_STONKS_TECH_INDICATORS` |
| Default storage-key prefix | `stonks/tech-indicators` |
| JSON object kind | `stonks_tech_indicators_report` |
| PDF object kind | `stonks_tech_indicators_pdf_report` |
| Daily report ID | `stonks.tech-indicators.daily` |
| Backfill report ID | `stonks.tech-indicators.backfill` |
| Config CLI/wrapper | `stonks-tech-indicators-config` |
| Daily CLI/wrapper | `stonks-tech-indicators-daily` |
| Backfill CLI/wrapper | `stonks-tech-indicators-backfill` |
| Inspect CLI/wrapper | `stonks-tech-indicators-inspect` |
| Airflow DAG/module stem | `stonks_tech_indicators_daily_refresh` |
| Airflow task ID | `run_tech_indicators_daily` |

The two Core report artifact names per job are also frozen:

| Workflow | JSON logical name | PDF logical name |
|----------|-------------------|------------------|
| Daily | `tech_indicators_daily_report` | `tech_indicators_daily_pdf_report` |
| Backfill | `tech_indicators_backfill_report` | `tech_indicators_backfill_pdf_report` |

Both formats for one workflow use the same report ID because they render the
same operational facts. The initial report schema version is integer `1`; R8.1
owns its fields. Filenames remain `report.json` and `report.pdf`. Run-scoped
objects use this path, partitioned by the Core run's effective date:

```text
stonks/tech-indicators/runs/YYYY/MM/DD/<run_id>/reports
```

The initial calculation version is an immutable formula-profile identity, not
the Poetry package version. Formula-semantic changes receive a new uppercase
identifier such as `TECH_INDICATORS_V2`; code fixes that do not alter accepted
outputs do not. The exact database constraint is finalized in S2.3.

The conditional state-table name is reserved, not approval to create the
table. B1.2 rejected recurrence state for V1; S2.2 must record that decision
and must not design a state table.
P0.9 freezes the two payload slots, publication table, membership table, and
published view above. They do not reuse the conditional recurrence-state name.
S2.2 translates that mechanism and state rejection into the exact
[`tech-indicators-publication-schema-v1.md`](tech-indicators-publication-schema-v1.md)
auxiliary and view contract.

Core jobs use `subject_key="all_series"` for the unfiltered universe. P0.10
freezes normalized scope identity and one capability-wide writer lock below;
J9.9 implements them. Scoped values must remain secret-safe and must not
change the frozen job names.

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
and model signals. The audited initial eligibility predicate, provider
disclosures, and prohibited normalization/comparability claims are frozen in
[`tech-indicators-source-value-policy-v1.md`](tech-indicators-source-value-policy-v1.md).

The table is current calculated state. It does not preserve technical
revisions. Source corrections and calculation-version changes update affected
rows through the deterministic
[`tech-indicators-recalculation-contract-v1.md`](tech-indicators-recalculation-contract-v1.md).

## Published Relation And Payload Shape

The selected published consumer relation is:

```text
stonks.ohlcv_daily_tech_indicators
```

It is a read-only 90-column view over physical payload tables
`ohlcv_daily_tech_indicators_a` and `ohlcv_daily_tech_indicators_b`, selected by
active publication membership. Each payload table has primary key
`(provider_listing_id, trading_date)`. The same composite columns reference
`stonks.ohlcv_daily` with deletion cascading from the owning bar. A payload row
also carries a nullable FK to the provider listing used as the relative-
strength benchmark and a nullable FK to `core.core_run`.

The published view is a wide, read-optimized feature store. Storage
minimization is not the goal, but both bounded slots affect I/O and disk and
must meet P0.8. Features requiring historical windows, recursive state, or
cross-series alignment are calculated once and stored. Strategy thresholds
remain query-time comparisons.

A payload row copies source open, high, low, close, and volume so an ordinary
published target scan does not join `ohlcv_daily`. The Python writer must prove
copied values agree with the owning source bar. Readiness queries still compare
published and source state before model use.

An additional recurrence-state table is not selected by default. It may be
added only if the recursive-equivalence prototype proves it is required for
exact and performant EMA, RSI, ATR, ADX, or MACD updates.

## Type And Validation Decisions

S2.1 freezes the exact payload and published-view names, order, PostgreSQL
types, generated expressions, defaults, ownership, and comments in
[`tech-indicators-payload-schema-v1.md`](tech-indicators-payload-schema-v1.md).
The feature profile remains authoritative for logical field presence and
units; the payload schema is authoritative for its DDL translation.

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
- S2.3 freezes those exact keys, checks, lifecycle triggers, delete actions,
  and the Python-owned exhaustive validation boundary in
  [`tech-indicators-constraints-v1.md`](tech-indicators-constraints-v1.md).
- The migration does not need one enormous constraint repeating every float
  column for `NaN` and infinities.

Cheap deterministic same-row arithmetic may use PostgreSQL `STORED` generated
columns. This keeps reads fast and prevents Python from persisting inconsistent
copies of formulas derivable from the same row.

## Frozen V1 Feature Profile

The exact P0.3 field presence, units, logical nullability, and ownership
contract is frozen in
[`tech-indicators-feature-profile-v1.md`](tech-indicators-feature-profile-v1.md).
The categories below are a design summary; the feature-profile document is
authoritative when implementing the migration, calculator, repository, CLI,
reports, or DAG.

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

Phase 1 may select a recurrence strategy, but it may not silently move a V1
field between Python-calculated and generated ownership. Any ownership change
requires an explicit feature-profile amendment.

### Persisted PostgreSQL Stored Generated Values

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

These are PostgreSQL `STORED` generated columns in V1. There is no implicit
Python fallback; any required ownership change needs an explicit profile
amendment before migration implementation.

## Formula Baseline

P0.4 freezes the exact executable V1 semantics in
[`tech-indicators-formula-spec-v1.md`](tech-indicators-formula-spec-v1.md).
The formulas below are a design summary; the formula-specification document is
authoritative for implementation and tests. A different feature concept or
semantic rule requires an explicit contract and calculation-version update.

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

Exact-zero denominators yield null; negative and arbitrarily small nonzero
denominators remain valid. An unchanged close resets both streaks to zero;
otherwise the current date is included in the applicable streak. Both streaks
start at zero on the first observation.

### Moving Averages And Trend Distances

```text
pct_sma_N = close / sma_N - 1
pct_ema_N = close / ema_N - 1
pct_sma_short_vs_long = sma_short / sma_long - 1

sma_N_change_20d_pct =
    sma_N(t) / sma_N(t-20 observations) - 1
```

SMA periods are 20, 50, and 200. EMA periods are 12, 20, 26, and 50. V1 uses
TA-Lib default compatibility and zero configured unstable periods; the formula
specification freezes the exact initialization and null prefixes.

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

Return volatility is the non-annualized sample standard deviation of complete
rolling windows of 20 or 60 one-observation returns, including the current
return.

The z-score columns compare the current 1- or 3-observation return with the
previous 20 corresponding returns. The current return is excluded from the
sample-standard-deviation reference distribution. Zero standard deviation
yields null.

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

Phase B1.2 proved that independently stored EMA 12/26 values do not reproduce
TA-Lib's MACD line at every accepted date. The MACD line remains an output of
the pinned three-output `MACD` call; no generated-column shortcut is allowed.

### Volume And Liquidity

Missing provider volume stays null. It is never converted to zero.

```text
dollar_volume = abs(close) * volume
volume_avg_N = average(volume over a complete N-observation window)
dollar_volume_avg_20 = average(dollar_volume over 20 observations)
volume_ratio_20 = volume / volume_avg_20
```

Volume windows are 20 and 60. Under the
[`tech-indicators-source-value-policy-v1.md`](tech-indicators-source-value-policy-v1.md),
volume and dollar-volume features are nominal within-listing time-series
features. V1 does not authorize cross-listing liquidity comparison.

## SPX Benchmark Contract

P0.5 freezes the executable benchmark, subject, alignment, statistic, and
unavailable-behavior contract in
[`tech-indicators-spx-contract-v1.md`](tech-indicators-spx-contract-v1.md).
The formulas below are a design summary; the SPX contract is authoritative for
implementation and tests.

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

Subject and SPX closes first align on their exact shared trading dates. Returns
are then calculated between consecutive aligned close pairs so both sides use
the same start and end dates. No forward fill, nearest date, synthetic holiday
row, calendar coercion, or independently joined mismatched return horizon is
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

V1 supports SPX features only for exact EODData `NYSE`/`NASDAQ`/`AMEX` Equity
metadata series and Stooq `nasdaq`/`nyse`/`nysemkt` stock partitions. Yahoo and
all other subjects retain a null benchmark ID and null SPX fields. The source-
value policy selects both supported subject cohorts and only the Yahoo SPX row
for base calculation without changing this SPX-support predicate.

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
S2.4 selected only the primary key plus one date-leading B-tree per payload
slot and rejected feature-specific indexes from live 20.7M-row plan evidence;
the exact DDL and measurements are frozen in
[`tech-indicators-indexes-v1.md`](tech-indicators-indexes-v1.md).

## Recalculation And Performance Direction

P0.7 freezes work detection, suffix invalidation, status, version, benchmark,
and deletion behavior in
[`tech-indicators-recalculation-contract-v1.md`](tech-indicators-recalculation-contract-v1.md).
P0.8 freezes representative sizes, timing/memory targets, batch/transaction,
query-plan, report, and rollout gates in
[`tech-indicators-performance-release-gates-v1.md`](tech-indicators-performance-release-gates-v1.md).
The rules below summarize those contracts.

Repeated target queries must not execute rolling windows. The package computes
features once, validates them, bulk persists them, and lets screens compare
stored values.

Daily append, source correction, SPX correction, missing technical row, and
calculation-version change are separate work-planning cases. Recursive
indicators make correction replay nontrivial: a historical input can affect a
suffix beyond its nominal period. B1.2 selected full-prefix calculation with
affected-suffix writes and no V1 recurrence-state table in
[`tech-indicators-recursive-equivalence-v1.md`](tech-indicators-recursive-equivalence-v1.md).

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

B1.1 freezes TA-Lib 0.7.1, its bundled C library 0.7.1, and NumPy 2.4.6,
including wheel, Python, license, verification, and rollback behavior, in
[`tech-indicators-runtime-contract-v1.md`](tech-indicators-runtime-contract-v1.md).

## Publication, Readiness, And Concurrency Contract

Calculation completion and feature publication are separate concepts. A
successful calculation run must not make a partially refreshed effective date,
mixed calculation versions, incomplete SPX-relative results, or a partially
rebuilt scope available to model consumers as ready data.

P0.9 freezes the hybrid in-place/two-slot mechanism, publication units,
terminal finalization, crash recovery, and one-snapshot readiness predicate in
[`tech-indicators-publication-contract-v1.md`](tech-indicators-publication-contract-v1.md).
A bounded daily/correction unit may update its active slots in one terminal
transaction. Backfills, version rebuilds, and larger corrections build complete
inactive listing images and publish through one membership flip. A completion
marker by itself remains insufficient.

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

P0.10 freezes one capability-wide PostgreSQL transaction advisory lock in
[`tech-indicators-concurrency-contract-v1.md`](tech-indicators-concurrency-contract-v1.md).
Every daily, backfill, correction, rebuild, cleanup, resume, dry-run, CLI, and
Airflow writer path uses the same key, so even disjoint scopes and different
versions serialize. This deliberately simple V1 rule avoids overlap analysis
for an operationally single-run workflow. The lock is acquired nonblockingly
before Core/publication state, held on a dedicated transaction-pool-compatible
connection through terminal publication, and released automatically by commit,
rollback, or connection loss. Contention returns immediately without creating
workflow state. Read-only inspection and readiness remain lock-free.

## Run Reports And Operational Surfaces

The package provides daily and historical-backfill Core runners, package
commands, `bin/` wrappers, and a thin Airflow DAG after the calculation and
persistence paths are proven.

R8.1 freezes the exact shared JSON facts, enums, null/count invariants,
diagnostic bounds, and secret-safe Core metadata allowlist in
[`tech-indicators-report-schema-v1.md`](tech-indicators-report-schema-v1.md).
R8.5 freezes the companion presentation, branding, accessibility, deterministic
compaction, and methodology rules in
[`tech-indicators-pdf-design-v1.md`](tech-indicators-pdf-design-v1.md).
Later report tasks may implement renderers without changing either contract
implicitly.

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
the same effective date. Task timing alone is insufficient. A11.1 selects
asynchronous source-completion dispatch to the manual/event-woken coordinator
DAG, with the package's database-backed readiness decision as the authoritative
date join, in the
[coordination contract](tech-indicators-airflow-coordination-v1.md)
contract. A11.2 freezes a minimal package-owned output containing source
identity, effective date, Core run identity, report outcome, and a deterministic
trigger ID; it contains no credentials or raw data. Repeated source runs must
lead to idempotent, nonconcurrent refresh behavior. Airflow must call the same
package-owned publication and locking paths as CLI and manual execution.

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
| Exact naming/version/report/object conventions | P0.2 (frozen above) |
| Exact V1 field ownership, units, and logical nullability | P0.3 (frozen in `tech-indicators-feature-profile-v1.md`) |
| Final DDL types and generated expressions | S2.1-S2.3 |
| Formula, denominator, warm-up, estimator, z-score, and tolerance semantics | P0.4 (frozen in `tech-indicators-formula-spec-v1.md`) |
| SPX identity, subjects, alignment, statistics, and unavailable behavior | P0.5 (frozen in `tech-indicators-spx-contract-v1.md`) |
| Eligible source-value and adjustment/comparability policy | P0.6 (frozen in `tech-indicators-source-value-policy-v1.md`) |
| Recalculation, correction, status, version, and deletion semantics | P0.7 (frozen in `tech-indicators-recalculation-contract-v1.md`) |
| Performance, resource, query-plan, report, and release gates | P0.8 (frozen in `tech-indicators-performance-release-gates-v1.md`) |
| TA-Lib/NumPy versions and Airflow packaging | B1.1 |
| Recursive incremental/state-table strategy | B1.2 (full-prefix calculation, no V1 state table); S2.2 records the schema consequence |
| Initial evidence-backed indexes | S2.4 |
| Performance measurements and evidence-based tuning within frozen gates | W7.9, V12.6 |
| Atomic publication unit and readiness predicate | P0.9 (frozen in `tech-indicators-publication-contract-v1.md`) |
| Package-owned lock identity and contention policy | P0.10 (frozen in `tech-indicators-concurrency-contract-v1.md`) |
| Airflow source-completion coordination | A11.1-A11.3 (mechanism, signals, and manual DAG frozen in `tech-indicators-airflow-coordination-v1.md`); A11.4-A11.8 test, wire, and verify it |

Any new indicator or material formula change requires a concrete consumer,
versioned semantics, incremental behavior, storage/query justification, and an
independent regression reference.
