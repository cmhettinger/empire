# Tech-Indicators SPX Contract V1

Status: frozen implementation contract for P0.5 as of 2026-08-09.

This document is authoritative for the V1 SPX benchmark identity, supported
subject predicate, exact-date alignment, price-ratio trends, relative returns,
beta, correlation, complete-window behavior, and benchmark-unavailable
outcomes. It extends the
[`tech-indicators-formula-spec-v1.md`](tech-indicators-formula-spec-v1.md)
without changing that specification's observation, denominator, finite-output,
or tolerance rules.

The initial source-value and adjustment/comparability policy is frozen in
[`tech-indicators-source-value-policy-v1.md`](tech-indicators-source-value-policy-v1.md).
It selects both supported subject cohorts plus the exact Yahoo SPX row for base
calculation without changing this contract's formulas or support predicate.
Correction and affected-range planning is frozen in
[`tech-indicators-recalculation-contract-v1.md`](tech-indicators-recalculation-contract-v1.md).
P0.9 owns atomic publication.

## Benchmark Identity And Resolution

The only V1 broad-market benchmark is the existing provider listing with these
stable facts:

```text
provider_code = YAHOO
market = XIDX
ticker = SPX
instrument_type_code = EQUITY_INDEX
status = ACTIVE
metadata.YahooTicker = ^GSPC
```

Resolution queries `stonks.provider_listing`; it never hardcodes or configures
the generated `provider_listing_id`. The resolver must:

1. select the exact case-sensitive `(YAHOO, XIDX, SPX)` identity;
2. require exactly one row;
3. require `status = ACTIVE`;
4. require `instrument_type_code = EQUITY_INDEX`;
5. require `metadata` to be a JSON object whose string `YahooTicker` is exactly
   `^GSPC`; and
6. return that row's UUID as the benchmark identity.

Additional reviewed metadata keys are allowed. `name`, the generated UUID,
Yahoo response descriptions, and request URLs are not identity. The resolver
does not substitute another S&P series, ETF, future, index, or provider.

For a scope containing any SPX-supported subject, missing, duplicate,
inactive, mistyped, or metadata-drifted resolution is a hard preflight failure.
No supported-subject feature rows or publication readiness may be written with
a guessed benchmark or a null benchmark identity. A scope containing only
unsupported subjects may skip resolution because every SPX field is
contractually null.

## SPX-Supported Subject Predicate

V1 supports SPX-relative features only for provider-native U.S. cash-equity
series selected from the two implemented stock feeds:

| Provider | Exact markets | Additional required fact |
|---|---|---|
| `EODDATA` | `NYSE`, `NASDAQ`, `AMEX` | `upper(btrim(metadata ->> 'type')) = 'EQUITY'` |
| `STOOQ` | `nasdaq`, `nyse`, `nysemkt` | none; these are the source contract's selected U.S. stock partitions |

The comparison is exact except for the documented case-insensitive EODData
`metadata.type` value. Missing or non-string EODData type metadata is
unsupported. Provider-listing `instrument_type_code` is not used for these
feeds because both currently persist `UNKNOWN` rather than inventing a
canonical classification.

All Yahoo `XIDX` series—including SPX itself—and every other provider, market,
index, volatility index, yield, currency, commodity, or futures series are
unsupported in V1. There is no canonical-listing join, ticker inference,
market-name folding, or proxy mapping.

Provider-listing `status` controls work selection under P0.7; it does not
change the historical semantic support predicate. The source-value policy
selects both supported source cohorts. A future source-policy exclusion means
no selected row, not a different SPX formula.

For a supported subject and healthy resolution,
`relative_strength_benchmark_provider_listing_id` is the resolved SPX UUID on
every persisted technical row, including warm-up or nonaligned rows. For an
unsupported subject, that column and all 11 SPX fields are null:

```text
rel_spx
pct_rel_spx_20, pct_rel_spx_50
relative_return_spx_20d_pct, relative_return_spx_63d_pct
relative_return_spx_126d_pct, relative_return_spx_252d_pct
spx_beta_60d, spx_beta_252d
spx_correlation_60d, spx_correlation_252d
```

`SUBJECT_UNSUPPORTED` is an expected coverage reason, not a calculation error
or warning.

## Exact-Date Aligned Close Sequence

For one supported subject, inner-join its source bars with the resolved SPX
bars on exact `trading_date` and order the intersection ascending:

```text
A[k] = (D[k], S[k], B[k])

D[k] = exact shared trading_date
S[k] = subject close on D[k]
B[k] = SPX close on D[k]
```

Only dates present for both series enter `A`. There is no forward fill,
backfill, nearest-date match, calendar coercion, synthetic holiday row, or use
of a different benchmark date. Calendar gaps are retained: consecutive aligned
observations may be separated by any number of calendar days.

Every SPX feature stored on subject date `t` requires a current aligned pair
whose `D[k] = t`. If SPX lacks that exact date, all SPX feature values on the
subject row are null with reason `CURRENT_DATE_NOT_ALIGNED`; the resolved
benchmark UUID remains populated. Prior aligned history is never carried
forward to make the current date appear aligned.

`history_observation_count` remains the subject's native source-observation
count. It is not replaced by an aligned count. The calculator exposes these
non-persisted diagnostics for each supported row or bounded report aggregate:

```text
aligned_close_observation_count = count of D[j] <= subject trading_date
trailing_valid_aligned_return_count = number of consecutive valid aligned
                                      return pairs ending at current k, or 0
                                      when the current date is not aligned
```

The trailing count resets to zero at an invalid aligned return pair. Calendar
gaps do not reset it because both series use the same two aligned endpoints.

## Aligned One-Observation Returns

For aligned index `k >= 1`:

```text
subject_aligned_return[k] = distance(S[k], S[k-1])
spx_aligned_return[k]     = distance(B[k], B[k-1])
```

An aligned return pair is valid only when both results are non-null and finite.
This construction deliberately calculates both returns across the same two
shared dates. It does not independently calculate each provider's native
one-observation return and then join mismatched return horizons by end date.

An `N`-return complete window ending at `k` is exactly the ordered pairs
`k-N+1` through `k`. It requires `k >= N` and all `N` pairs to be valid. An
invalid pair makes the field null; the calculator does not drop it and pull an
older pair into the window.

## SPX Price Ratio And Ratio Trend

For every aligned close pair:

```text
q[k] = divide(S[k], B[k])
rel_spx[D[k]] = q[k]
```

A zero SPX close makes `q[k]` null under the exact-zero rule. Negative nonzero
closes remain calculable because the upstream source contract permits them.

For `N` in 20 and 50:

```text
q_mean_N[k] = sum(q[j] for j in k-N+1..k) / N
pct_rel_spx_N[D[k]] = distance(q[k], q_mean_N[k])
```

The window contains exactly `N` aligned close observations, includes the
current pair, and requires every `q` to be non-null. The first eligible aligned
indexes are 19 and 49. An exactly zero ratio mean yields null.

## Compounded Relative Returns

For `N` in 20, 63, 126, and 252, require a complete `N`-return aligned window:

```text
subject_gross_N[k] =
    product(1 + subject_aligned_return[j] for j in k-N+1..k)

spx_gross_N[k] =
    product(1 + spx_aligned_return[j] for j in k-N+1..k)

relative_return_spx_Nd_pct[D[k]] =
    distance(subject_gross_N[k], spx_gross_N[k])
```

Products are evaluated in chronological order. Mathematically, when every
required division is valid, the formula equals:

```text
(S[k] / S[k-N]) / (B[k] / B[k-N]) - 1
```

The first eligible aligned index is `N`, because `N` returns require `N + 1`
aligned closes. A null aligned return makes the field null, an exactly zero SPX
gross makes the division null, and a non-finite product fails calculation. No
pair is skipped.

## Sample Beta And Pearson Correlation

For `N` in 60 and 252, use the complete `N`-return aligned window ending at
`k`. Let its subject returns be `x[1..N]` and SPX returns be `y[1..N]`:

```text
mean_x = sum(x) / N
mean_y = sum(y) / N

sample_covariance =
    sum((x[j] - mean_x) * (y[j] - mean_y) for j in 1..N) / (N - 1)

sample_variance_x =
    sum((x[j] - mean_x)^2 for j in 1..N) / (N - 1)

sample_variance_y =
    sum((y[j] - mean_y)^2 for j in 1..N) / (N - 1)

spx_beta_Nd[D[k]] = divide(sample_covariance, sample_variance_y)

spx_correlation_Nd[D[k]] =
    divide(
        sample_covariance,
        sqrt(sample_variance_x) * sqrt(sample_variance_y),
    )
```

The concrete fields are `spx_beta_60d`, `spx_beta_252d`,
`spx_correlation_60d`, and `spx_correlation_252d`. Their first eligible aligned
indexes are 60 and 252. Exact zero SPX variance makes beta null. Exact zero
subject or SPX variance makes correlation null. Beta has no arbitrary bound.

Pearson correlation is mathematically in `[-1, 1]`. Apply this explicit V1
canonicalization after a finite value is calculated:

```text
if -1 <= correlation <= 1:
    retain correlation
else if abs(correlation - 1) <= 1e-12:
    store 1.0
else if abs(correlation + 1) <= 1e-12:
    store -1.0
else:
    fail calculation
```

This bound-specific normalization uses P0.4's absolute tolerance and is the
only SPX clamp. General equivalence still uses absolute `1e-12` and relative
`1e-10` tolerance. Neither tolerance turns a nonzero variance or denominator
into zero.

## Nullability, Readiness, And Unavailable Outcomes

For a supported subject, expected field-level null reasons are:

| Condition | Result |
|---|---|
| Subject date has no exact SPX date | all 11 SPX fields null; `CURRENT_DATE_NOT_ALIGNED` |
| Current SPX denominator is zero | affected ratio fields null; `ZERO_BENCHMARK_DENOMINATOR` |
| Too few aligned closes or returns | affected family null; `ALIGNED_WARMUP` with required and observed counts |
| Required aligned return is null | affected return-statistic family null; `INVALID_ALIGNED_RETURN_WINDOW` |
| Ratio mean or SPX gross is exactly zero | affected ratio/relative-return field null; `ZERO_BENCHMARK_DENOMINATOR` |
| SPX sample variance is exactly zero | beta and correlation null; `ZERO_SPX_VARIANCE` |
| Subject sample variance is exactly zero | correlation null; `ZERO_SUBJECT_VARIANCE` |

These expected nulls do not suppress the subject technical row and never become
zero. Reasons and counts are bounded diagnostics, not extra feature columns.

A normal daily run containing supported subject bars for an effective date is
not source-ready unless the resolved SPX listing has a bar for that same date.
It must fail closed before publication rather than publish a current daily
slice whose supported subjects are all `CURRENT_DATE_NOT_ALIGNED`. Historical
backfills may contain legitimate disjoint dates; those rows retain deterministic
nulls and coverage diagnostics instead of receiving filled benchmark values.
P0.9 still decides the atomic publication unit and complete-coverage predicate.

Unexpected non-finite results, out-of-tolerance correlation, identity drift,
or inconsistent row shape are hard calculation failures. They are not reported
as ordinary benchmark unavailability.

## Required Contract Tests

Implementation tests must cover at least:

1. successful UUID resolution and each missing, duplicate, inactive,
   instrument-type-drift, and `YahooTicker`-drift failure;
2. every supported provider/market/type combination and near-miss unsupported
   combination, including all Yahoo subjects;
3. unsupported row shape: null benchmark ID and exactly 11 null SPX fields;
4. exact-date intersections with weekends, holidays, and provider-specific
   missing dates, proving no fill or mismatched return horizons;
5. current-date nonalignment with a populated benchmark UUID;
6. 20/50 ratio windows and 20/63/126/252 relative-return boundaries;
7. 60/252 beta and correlation immediately before and at complete windows;
8. zero, negative, and very small nonzero benchmark denominators;
9. zero subject/SPX variance, perfect positive/negative correlation, beta with
   no arbitrary bound, and the explicit correlation clamp/failure boundary;
10. aligned-count and bounded-reason diagnostics without persisted count
    columns; and
11. daily missing-benchmark readiness failure versus deterministic historical
    gap nulls.

Changing the benchmark identity, subject predicate, alignment sequence,
complete-window rule, relative-return compounding, estimator, correlation
canonicalization, or unavailable behavior changes V1 semantics and requires an
explicit contract and calculation-version update.
