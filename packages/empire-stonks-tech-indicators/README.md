# empire-stonks-tech-indicators

Reusable provider-native daily technical-indicator calculation utilities for
Empire Stonks.

This package is the platform-owned boundary for technical calculation,
validation, persistence, operational reporting, and workflow runners. Airflow,
CLIs, and other runtimes will call package-owned capabilities rather than own
business logic. The B1.3 scaffold intentionally contains only the importable
package boundary; later tasks add those capabilities incrementally.

## Runtime contract

The initial package version is `0.1.0` and supports Python `>=3.11,<4.0`. Its
only runtime dependencies are the exact calculation pair frozen by B1.1:

```text
numpy==2.4.6
TA-Lib==0.7.1
```

TA-Lib uses its wheel-bundled native library. Normal installation must not
silently fall back to an unreviewed source build or system library. See the
[runtime contract](../../docs/stonks/tech-indicators-runtime-contract-v1.md)
for wheel, native-library, Python, license, verification, and rollback rules.

V1 recursive indicators calculate each affected provider listing from its
earliest eligible observation through the safe run horizon, then compare or
write only the affected suffix. Fixed bounded replay and persisted recurrence
state are not part of V1. See the
[recursive-equivalence decision](../../docs/stonks/tech-indicators-recursive-equivalence-v1.md).

Live input paging, query-plan, transaction, cancellation, and RSS verification
is provided by `tools/tech-indicators/large-read-smoke.py`; its representative
I3.7 result is recorded in the
[large-read evidence](../../docs/stonks/tech-indicators-large-read-evidence-i3.7.md).

## Ownership and configuration

Reusable package code reads configuration only from `os.environ`. It does not
load `.env` files, assume repository paths, or depend on Airflow. Environment
loading belongs to runtime wrappers, Docker Compose, Airflow, or the invoking
shell. `TechIndicatorsConfig.from_env()` validates these non-secret settings:

| Environment variable | Default | Accepted value |
|---|---:|---|
| `EMPIRE_STONKS_TECH_INDICATORS_CALCULATION_VERSION` | `TECH_INDICATORS_V1` | Exact implemented calculation version |
| `EMPIRE_STORAGE_KEY_STONKS_TECH_INDICATORS` | `stonks/tech-indicators` | Normalized relative storage prefix |
| `EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_PROVIDER_CODE` | `YAHOO` | Exact frozen value |
| `EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_MARKET` | `XIDX` | Exact frozen value |
| `EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_TICKER` | `SPX` | Exact frozen value |
| `EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_INSTRUMENT_TYPE_CODE` | `EQUITY_INDEX` | Exact frozen value |
| `EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_YAHOO_TICKER` | `^GSPC` | Exact frozen value |
| `EMPIRE_STONKS_TECH_INDICATORS_SOURCE_READ_PAGE_SIZE` | `10000` | `1000` through `50000` |
| `EMPIRE_STONKS_TECH_INDICATORS_WRITE_BATCH_SIZE` | `5000` | `1000` through `10000` |
| `EMPIRE_STONKS_TECH_INDICATORS_DIAGNOSTIC_SAMPLE_LIMIT` | `100` | `1` through `100` |

The P0.8 hard ceiling of 25,000 rows in a write transaction is a package
constant, not an environment override. Non-secret examples live in
`deploy/env/local.example.env`; the active local values live in the ignored
`deploy/env/local.env`. Airflow Compose passes the same values into every
Airflow service. Reusable package code never opens either environment file.

The package does not own an internal migration runner. Empire Flyway
migrations under `db/` own the eventual technical-indicator schema. Core run
lifecycle, JSON/PDF reports, package commands, and Airflow orchestration are
introduced only by their assigned implementation tasks.

## Public API

The package root explicitly exports one base exception and five stable failure
categories:

- `EmpireStonksTechIndicatorsError`
- `TechIndicatorsConfigError`
- `TechIndicatorsCalculationError`
- `TechIndicatorsValidationError`
- `TechIndicatorsPersistenceError`
- `TechIndicatorsWorkflowError`

It also exports the two immutable configuration types:

- `BenchmarkConfig`
- `TechIndicatorsConfig`

The immutable domain-model API consists of:

- `SourceBar` for one exact provider-native source observation
- `CalculationArrays` and `normalize_source_bars()` for strict chronological,
  contiguous source normalization with explicit nullable-volume masks
- `MaskedFloatArray`, `ReturnArrays`, and `calculate_returns()` for the nine
  fixed V1 observation-return fields and their exact null masks
- `ReturnStatisticArrays` and `calculate_return_statistics()` for 20/60-return
  sample volatility and prior-20-reference 1/3-return z-scores
- `BarStructureArrays` and `calculate_bar_structure()` for gap, same-bar
  generated-column references, and exact copied-source values
- `RangeRelationshipArrays` and `calculate_range_relationships()` for complete
  trailing 20/50/252-observation highs and 20/50-observation lows
- `VolumeLiquidityArrays` and `calculate_volume_liquidity()` for complete
  20/60-observation volume and 20-observation nominal dollar-volume averages
- `StreakArrays` and `calculate_streaks()` for non-null consecutive close-up
  and close-down observation counts
- `FeatureRow` for the fixed 65 package-written columns
- `TechIndicatorsScope` for normalized provider/listing/date selection
- `ResolvedBenchmark` for the exact resolved `YAHOO/XIDX/SPX` facts
- `TechIndicatorsIssue` for bounded secret-safe diagnostics
- `ReasonCount` and `FeatureCounts` for deterministic aggregate ledgers
- `TechIndicatorsSummary` for counts and at most 100 issue samples
- `TechIndicatorsRunResult` for compact runner output
- `EligibleListing`, `select_eligible_listings()`, and
  `iter_source_bar_pages()` for caller-transaction-owned P0.6 selection and
  bounded chronological OHLCV reads
- `resolve_spx_benchmark()` for exact fail-closed `YAHOO/XIDX/SPX` resolution
- `BenchmarkHistory` and `load_spx_benchmark_history()` for bounded exact-date
  SPX OHLCV history and close lookup
- `ListingStateComparison` and `iter_state_comparison_pages()` for paged,
  set-based current-source versus published-state drift facts
- `SourceReadinessDecision` and `decide_source_readiness()` for same-date
  OHLCV, SPX, and successful-source evidence decisions

`FeatureRow` excludes the 23 PostgreSQL-generated fields and the database-owned
`created_at` and `updated_at` timestamps. Its JSON-ready form is fixed-size;
reports and run results never embed source or feature-row collections.

Callers may catch the package base or the narrow category they can handle. The
public exceptions contain no TA-Lib values, SQL, database-driver exceptions,
connection details, or persistence implementation types. Additional public
models and capabilities are added only by their assigned tasks.

Eligible-listing selection applies the frozen EODData Equity, Stooq U.S. stock,
and exact Yahoo SPX predicates in one set-based read. Default scopes select only
active listings. Inactive listings require exact listing IDs plus
`include_inactive=True`. Inclusive date bounds limit the returned coverage
facts; zero- and short-history listings remain visible so callers can apply an
explicit minimum without confusing source-value support with history
sufficiency.

Chronological reads resolve that eligible listing set once, then use strict
provider/market/ticker/listing/date keyset pages of 1,000-50,000 rows. Each
page preserves exact `Decimal` OHLCV, nullable volume, calendar gaps, and
negative-capable source values. The package never commits, rolls back, closes,
or changes transaction isolation on the injected cursor.

Calculation normalization accepts exactly one non-empty provider-listing
series in already strict `trading_date` order; it never sorts, deduplicates, or
creates calendar observations. Exact source records remain attached for later
copy validation, while OHLCV values convert directly to read-only,
C-contiguous `float64` arrays. Missing volume is represented by `NaN` plus an
authoritative Boolean null mask, and zero volume remains zero. A finite source
value that cannot remain finite after `float64` conversion fails calculation.

V1 returns use lags of 1, 2, 3, 5, 10, 20, 63, 126, and 252 stored
observations, never calendar offsets. Each field is null through its lag;
afterward it is `close[i] / close[i-N] - 1` unless the converted prior close is
exactly zero. Negative and arbitrarily small nonzero denominators remain
eligible, valid zero returns remain zero, and non-finite calculated output
fails the calculation rather than becoming null.

Return volatility is the nonannualized sample standard deviation (`N-1`) of
complete trailing 20- or 60-observation one-observation returns, including the
current return. Return z-scores test the current one- or three-observation
return against the previous 20 corresponding returns, excluding the tested
return. Incomplete windows and exact-zero reference standard deviation remain
null; non-finite calculated statistics fail calculation. Inputs retain and
validate their exact normalized source bars and return values so independently
constructed or positionally drifted series cannot be combined.

Bar structure calculates `gap_1d_pct` from the prior stored observation and
same-row intraday return, range, close location, and nominal dollar volume from
the normalized source arrays. Exact-zero denominators and null volume produce
null; zero volume remains a valid zero and dollar volume uses `abs(close)`.
The result retains the exact `SourceBar` records for later payload assembly.
Only gap is Python-written: the four same-row series are calculation references
for validating their PostgreSQL stored generated columns and are never added to
the Python write payload.

Range relationships include the current observation and populate only after a
complete stored-observation window exists. Calendar gaps create no rows, short
histories remain null, and the calculation never reads a later high or low.
The resulting price levels feed the PostgreSQL-generated close-distance fields
without moving those distance formulas into the Python write payload.

Volume and liquidity averages require complete stored-observation windows and
consume bar structure's validated `abs(close) * volume` reference. Any null
volume makes its 20- or 60-observation window null until that observation ages
out; zero volume remains populated and participates in the average. Inputs must
carry the exact same source bars and dollar-volume values, preventing positional
drift between calculation families. Dollar-volume output remains nominal
provider-native price-times-volume, not a USD or cross-listing liquidity claim.

Streaks start at zero on the first stored observation and include the current
observation after each strict close increase or decrease. An unchanged close
resets both counts to zero; calendar gaps do not. V1 recalculates streaks from
the complete source prefix, so repeated append runs and full rebuilds produce
the same read-only nonnegative integer arrays without persisted recurrence
state.

The combined core regression in `tests/test_core_golden.py` checks every
C4.2-C4.7 output against a standard-library scalar oracle under the frozen
numerical-equivalence tolerance. Its committed fixture preserves the prior
Stonks engine's linear 260-bar example for the overlapping 20-observation high,
low, and volume-average formulas, plus a provider-native discontinuity and
calendar gap. Deterministic randomized series cover null and zero volume,
short histories, all lookbacks, and future-mutation prefix isolation.

SPX resolution queries only the exact configured `YAHOO/XIDX/SPX` identity,
requires exactly one row, and separately validates active status,
`EQUITY_INDEX`, object metadata, and exact `YahooTicker=^GSPC`. Missing,
duplicate, inactive, mistyped, or metadata-drifted state raises the package's
validation exception; no UUID or proxy benchmark is hardcoded.

Benchmark history is the V1 bounded cross-series input retained alongside one
subject at a time. It is loaded through the same configured source pages,
remains strictly chronological, and exposes only exact stored dates.
`bar_on()` returns `None` for a missing date and `close_by_date()` contains no
synthetic, nearest-date, or forward-filled keys.

State comparison uses the atomic published view and the full chronological
source prefix. It distinguishes ordinary tail appends from historical missing
rows, compares copied OHLCV null-safely, detects observation-count and requested
calculation-version drift, and exposes each reason's earliest date. A version
drift conservatively promotes recalculation to the listing's first source date;
the later affected-range planner owns suffix expansion and safe horizons.

Source readiness is an effective-date input decision, not publication or model-
input readiness. It combines current eligible-scope coverage with exact SPX
identity/date requirements and same-date successful Core evidence from the
automated EODData and Yahoo daily workflows. It does not infer readiness from
task order, completion timestamps alone, or a later-dated source run. Stooq is
coverage-driven because Empire has no contracted Stooq daily workflow.
EODData evidence requires zero hard failures and missing exchange sessions;
Yahoo evidence must represent the full seeded universe or explicitly include
`SPX`, while exact SPX OHLCV coverage remains independently required whenever
the selected effective date contains supported subject bars.

## Development

From this directory:

```bash
poetry install
poetry run pytest
poetry build
```

The committed `poetry.lock` resolves the exact calculation runtime and the
development test dependency. Build output contains both a wheel and source
distribution.

The Airflow image installs the exact binary calculation runtime first, then
installs this package after Empire Core, reports, and OHLCV. The package remains
runtime-agnostic: Airflow only provides an installed execution environment and
later thin orchestration.
