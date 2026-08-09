# Tech-Indicators Formula Specification V1

Status: frozen implementation contract for P0.4 as of 2026-08-09.

This document is the executable semantic specification for calculation version
`TECH_INDICATORS_V1`. It is authoritative for observation windows, formulas,
denominators, statistical estimators, TA-Lib parameters and warm-up handling,
and numerical comparison tolerance. The
[`tech-indicators-feature-profile-v1.md`](tech-indicators-feature-profile-v1.md)
contract remains authoritative for field presence, units, ownership, and
logical nullability.

P0.5 remains responsible for the exact SPX benchmark, subject eligibility,
alignment, and relative-statistic contract. Affected-range and recalculation
behavior is frozen in
[`tech-indicators-recalculation-contract-v1.md`](tech-indicators-recalculation-contract-v1.md).
B1.1 pins the reviewed TA-Lib and NumPy package versions without changing the
formulas below.

## Notation And Ordered Inputs

For one `provider_listing_id`, source bars are strictly ordered by
`trading_date` and assigned zero-based observation index `i`. A gap in calendar
dates does not create a synthetic observation. Every window includes the
current observation unless this specification explicitly says otherwise.

```text
O[i] = open at observation i
H[i] = high at observation i
L[i] = low at observation i
C[i] = close at observation i
V[i] = nullable volume at observation i
W(x, N, i) = x[i-N+1], ..., x[i]
```

OHLC inputs are required finite provider-native values. Volume is either null
or finite and nonnegative. Zero and negative prices remain valid inputs because
the upstream OHLCV contract does not impose positivity. Analytical arrays use
IEEE-754 double precision after a direct conversion from the exact source
`NUMERIC` value; there is no scaling, rounding, forward fill, or zero fill.

`history_observation_count[i] = i + 1`. It counts source observations through
the current row, not populated features or calendar days.

## Common Window, Null, And Denominator Rules

1. A fixed window is complete only when all required observations exist and
   every formula input in that window is non-null.
2. A lag of `N` observations requires `i >= N`; it does not mean `N` calendar
   days.
3. An Empire-authored division is null exactly when its denominator equals
   numeric zero after input conversion. Negative and arbitrarily small nonzero
   denominators remain valid. No epsilon or `isclose()` test changes formula
   eligibility.
4. If any numerator or denominator input is null, the result is null.
5. A finite-input calculation that produces a non-finite value outside a
   documented TA-Lib warm-up slot fails the active batch. It is not persisted
   as null or clamped to a finite sentinel.
6. TA-Lib's internal zero guards are part of the pinned library algorithm and
   are not replaced with Empire's division helper.
7. A null result never becomes zero. A mathematically valid zero result remains
   zero.

The pseudocode helper used below is:

```text
divide(numerator, denominator):
    if numerator is null or denominator is null or denominator == 0:
        return null
    result = numerator / denominator
    require result is finite
    return result

distance(numerator, denominator):
    ratio = divide(numerator, denominator)
    return null if ratio is null else ratio - 1
```

PostgreSQL generated expressions must implement the same exact-zero behavior
with `NULLIF(denominator, 0)`. S2.1 owns SQL casts and declared types, not a
different formula.

## Returns, Bar Structure, And Streaks

For `N` in `1, 2, 3, 5, 10, 20, 63, 126, 252`:

```text
return_Nd_pct[i] = distance(C[i], C[i-N])
```

This expands exactly to `return_1d_pct`, `return_2d_pct`, `return_3d_pct`,
`return_5d_pct`, `return_10d_pct`, `return_20d_pct`, `return_63d_pct`,
`return_126d_pct`, and `return_252d_pct`.

The first eligible observation is index `N`. A zero prior close yields null;
a negative prior close remains a valid denominator.

```text
gap_1d_pct[i]             = distance(O[i], C[i-1])
intraday_return_1d_pct[i] = distance(C[i], O[i])
daily_range_pct[i]        = divide(H[i] - L[i], abs(C[i]))
close_location_1d[i]      = divide(C[i] - L[i], H[i] - L[i])
dollar_volume[i]          = null if V[i] is null else abs(C[i]) * V[i]
```

`gap_1d_pct` is null at index zero. The same-row return is null when open is
zero, daily range is null when close is zero, and close location is null when
high equals low. Because source OHLC invariants place close inside `[low,
high]`, a non-null close location is in `[0, 1]`.

Streaks are initialized at index zero and include the current observation:

```text
consecutive_up_days[0] = 0
consecutive_down_days[0] = 0

if C[i] > C[i-1]:
    consecutive_up_days[i] = consecutive_up_days[i-1] + 1
    consecutive_down_days[i] = 0
else if C[i] < C[i-1]:
    consecutive_up_days[i] = 0
    consecutive_down_days[i] = consecutive_down_days[i-1] + 1
else:
    consecutive_up_days[i] = 0
    consecutive_down_days[i] = 0
```

## Fixed-Window Price And Volume Calculations

For each selected period `N`, the simple moving average is the arithmetic mean
of the complete close window and must match `TA-Lib SMA`:

```text
sma_N[i] = sum(W(C, N, i)) / N
```

SMA periods are 20, 50, and 200. The first eligible index is `N - 1`.

For high periods 20, 50, and 252 and low periods 20 and 50:

```text
hh_N[i] = max(W(H, N, i))
ll_N[i] = min(W(L, N, i))
```

This produces `hh_20`, `hh_50`, `hh_252`, `ll_20`, and `ll_50`. The current
observation participates, and the first eligible index is `N - 1`.

Volume calculations require complete windows with no null volume:

```text
volume_avg_N[i] = sum(W(V, N, i)) / N
    for N in 20, 60

dollar_volume_avg_20[i] =
    sum(abs(C[j]) * V[j] for j in i-19..i) / 20
```

The outputs are `volume_avg_20`, `volume_avg_60`, and
`dollar_volume_avg_20`. A null volume anywhere in the window makes that
window's result null. Zero volume is valid. Dollar-volume averaging uses the
same per-observation absolute close formula as `dollar_volume`; it does not
claim USD denomination.

## Return Volatility And Z-Scores

Define the one-observation return series:

```text
r1[i] = distance(C[i], C[i-1])
```

Return volatility is the sample standard deviation of the complete trailing
`N` one-observation returns, including the current return, and is not
annualized:

```text
mean = sum(r1[j] for j in i-N+1..i) / N
return_volatility_Nd_pct[i] =
    sqrt(sum((r1[j] - mean)^2 for j in i-N+1..i) / (N - 1))
    for N in 20, 60
```

The outputs are `return_volatility_20d_pct` and
`return_volatility_60d_pct`. Their first eligible indexes are 20 and 60
respectively because `N` returns need `N + 1` closes. A constant-return window
produces valid volatility `0.0`. Any null return makes the window result null.

For z-scores, the current return is the tested value and is excluded from the
20-return reference distribution. Define:

```text
rK[i] = distance(C[i], C[i-K])
reference = rK[i-20], ..., rK[i-1]
reference_mean = sum(reference) / 20
reference_sample_stddev =
    sqrt(sum((x - reference_mean)^2 for x in reference) / 19)

return_Kd_zscore_20d[i] =
    divide(rK[i] - reference_mean, reference_sample_stddev)
    for K in 1, 3
```

The first eligible index is 21 for `return_1d_zscore_20d` and 23 for
`return_3d_zscore_20d`. A null tested return, any null reference return, or
exactly zero reference standard deviation yields null. Excluding the current
return makes the reference strictly historical while using no future data.

## TA-Lib Runtime Contract

V1 uses TA-Lib's Function API over contiguous double-precision arrays with:

```text
compatibility = DEFAULT
unstable period = 0 for every function
```

The package must assert these settings before calculation. It must not inherit
process-global MetaStock compatibility or a caller-modified unstable period.
Calls use the explicit parameters below rather than library defaults.

| Persisted outputs | Required call | First valid index / null prefix |
|---|---|---:|
| `sma_20`, `sma_50`, `sma_200` | `SMA(C, timeperiod=N)` | `N - 1` |
| `ema_12`, `ema_20`, `ema_26`, `ema_50` | `EMA(C, timeperiod=N)` | `N - 1` |
| `rsi_14` | `RSI(C, timeperiod=14)` | 14 |
| `atr_14` | `ATR(H, L, C, timeperiod=14)` | 14 |
| `price_stddev_20` | `STDDEV(C, timeperiod=20, nbdev=1.0)` | 19 |
| `plus_di_14` | `PLUS_DI(H, L, C, timeperiod=14)` | 14 |
| `minus_di_14` | `MINUS_DI(H, L, C, timeperiod=14)` | 14 |
| `adx_14` | `ADX(H, L, C, timeperiod=14)` | 27 |
| `macd_12_26`, `macd_signal_12_26_9`, `macd_histogram_12_26_9` | `MACD(C, fastperiod=12, slowperiod=26, signalperiod=9)` | 33 for all three |

Every position before the listed first-valid index is SQL null. TA-Lib's
expected pre-lookback `NaN` values are normalized to null. At or after the
first-valid index, every listed output must be finite; `NaN` or infinity is a
hard calculation failure.

`STDDEV(..., nbdev=1.0)` uses the library's population variance for the
20-close Bollinger state. This intentionally differs from the sample estimator
used for return volatility and z-score reference distributions.

The V1 full-series reference for recursive indicators begins at the earliest
stored source observation for that provider listing. EMA uses the TA-Lib seed,
the SMA of the first `N` closes, followed by `alpha = 2 / (N + 1)` recursion.
RSI, ATR, DI, and ADX use TA-Lib's Wilder calculations. MACD is the three-output
result from the one `MACD` call; it is not reconstructed from the separately
stored `ema_12` and `ema_26`. B1.2 may select an incremental state/replay
strategy only if it reproduces this full-series reference within the frozen
tolerance.

The official TA-Lib API describes function lookbacks and configurable unstable
periods, and the Python wrapper documents the pre-lookback `NaN` convention:

- <https://ta-lib.org/api/>
- <https://github.com/TA-Lib/ta-lib-python>

## Trend Changes And Stored Generated Expressions

Moving-average changes are:

```text
sma_50_change_20d_pct[i]  = distance(sma_50[i], sma_50[i-20])
sma_200_change_20d_pct[i] = distance(sma_200[i], sma_200[i-20])
```

Their first eligible indexes are 69 and 219. A zero lagged SMA yields null.

The 23 stored generated fields use these exact expressions:

```text
dollar_volume = abs(close) * volume
intraday_return_1d_pct = distance(close, open)
daily_range_pct = divide(high - low, abs(close))
close_location_1d = divide(close - low, high - low)

pct_sma_20  = distance(close, sma_20)
pct_sma_50  = distance(close, sma_50)
pct_sma_200 = distance(close, sma_200)
pct_ema_20  = distance(close, ema_20)
pct_ema_50  = distance(close, ema_50)

pct_sma_20_vs_50  = distance(sma_20, sma_50)
pct_sma_20_vs_200 = distance(sma_20, sma_200)
pct_sma_50_vs_200 = distance(sma_50, sma_200)

pct_hh_20  = distance(close, hh_20)
pct_hh_50  = distance(close, hh_50)
pct_hh_252 = distance(close, hh_252)
pct_ll_20  = distance(close, ll_20)
pct_ll_50  = distance(close, ll_50)

atr_pct_14 = divide(atr_14, abs(close))

upper_20_2 = sma_20 + 2 * price_stddev_20
lower_20_2 = sma_20 - 2 * price_stddev_20
bollinger_percent_b_20_2 =
    divide(close - lower_20_2, upper_20_2 - lower_20_2)
bollinger_bandwidth_20_2 =
    divide(upper_20_2 - lower_20_2, abs(sma_20))

volume_ratio_20 = divide(volume, volume_avg_20)
macd_12_26_pct = divide(macd_12_26, abs(ema_26))
macd_histogram_12_26_9_pct =
    divide(macd_histogram_12_26_9, abs(close))
```

`upper_20_2` and `lower_20_2` are query-time intermediates, not additional
columns. A null dependency propagates to the generated result. An exactly zero
average volume, band width, absolute close, absolute EMA, or other denominator
yields null for the dependent division. In particular, zero band width makes
`bollinger_percent_b_20_2` null, while
`bollinger_bandwidth_20_2` is valid zero when `sma_20` is nonzero.

## Numerical Equivalence And Validation Tolerance

Copied `NUMERIC` source values, identifiers, dates, counts, versions, and null
masks compare exactly. Finite derived double-precision values compare with:

```text
ABSOLUTE_TOLERANCE = 1e-12
RELATIVE_TOLERANCE = 1e-10

equivalent(a, b) =
    abs(a - b) <= max(
        ABSOLUTE_TOLERANCE,
        RELATIVE_TOLERANCE * max(abs(a), abs(b)),
    )
```

This tolerance applies to independent reference tests, TA-Lib regression,
Python-versus-PostgreSQL generated-expression checks, and full-versus-
incremental rebuild equivalence. It never:

- turns a nonzero denominator into zero;
- makes null and zero equivalent;
- permits a finite value to match `NaN` or infinity;
- weakens source-copy equality; or
- changes a persisted value by rounding or clamping.

Mathematical bounds are validated separately from equivalence. V1 does not use
an epsilon to manufacture a zero variance or denominator. P0.5 must apply this
same comparison function while freezing SPX correlation/beta details and must
state any bound-specific canonicalization explicitly.

## SPX Extension

P0.5 freezes benchmark resolution, supported subjects, exact-date alignment,
relative statistics, complete windows, correlation canonicalization, and
unavailable behavior in
[`tech-indicators-spx-contract-v1.md`](tech-indicators-spx-contract-v1.md).
That extension applies this document's observation, exact-zero, finite-output,
and numerical-equivalence rules without changing the non-SPX formulas above.

## Required Contract Tests

Implementation tests must cover at least:

1. each fixed lookback immediately before and at its first eligible index;
2. observation gaps proving that lookbacks are not calendar offsets;
3. zero, negative, and very small nonzero price denominators;
4. null and zero volume, including null recovery after a rolling window;
5. flat-price and constant-return windows;
6. z-score current-value exclusion and zero reference variance;
7. exact TA-Lib calls, default compatibility, zero unstable periods, and the
   null-prefix table above;
8. post-lookback non-finite output as a hard failure;
9. generated-expression null propagation and Python/PostgreSQL agreement; and
10. full-series versus accepted incremental output under the frozen tolerance.

Changing an estimator, reference-window inclusion rule, TA-Lib parameter,
compatibility mode, unstable period, warm-up index, denominator rule, or
tolerance changes calculation semantics and requires a new calculation version
or an explicit correction to this contract before implementation.
