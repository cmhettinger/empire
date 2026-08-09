# Tech-Indicators Recursive Equivalence Decision V1

Status: frozen B1.2 implementation decision, 2026-08-09.

This decision extends the full-series reference and affected-suffix rules in
[`tech-indicators-recalculation-contract-v1.md`](tech-indicators-recalculation-contract-v1.md).
It uses the formula semantics in
[`tech-indicators-formula-spec-v1.md`](tech-indicators-formula-spec-v1.md), the
pinned runtime in
[`tech-indicators-runtime-contract-v1.md`](tech-indicators-runtime-contract-v1.md),
and the representative 20,000-observation listing envelope in
[`tech-indicators-performance-release-gates-v1.md`](tech-indicators-performance-release-gates-v1.md).

## Decision

V1 calculates each affected provider listing from its earliest eligible source
observation through the safe run horizon. It does not use a fixed bounded
prefix or persist recurrence state.

- A tail append calculates the complete prefix and compares or writes only the
  appended suffix.
- A source correction at date `d` calculates the complete prefix and compares
  or writes the suffix from `d` through the safe run horizon.
- Missing-row, version-rebuild, and other uncertainty ranges retain the write
  semantics frozen by P0.7, but their recursive calculation input begins at
  the listing's earliest eligible observation.
- Equivalent rows before the write range are not rewritten. Full-prefix
  calculation does not expand the publication or mutation range.
- The combined calculator processes bounded listing batches and may release
  each listing's arrays after validation and persistence.

S2.2 must therefore reject a recurrence-state schema for V1, S2.5 must not
create one, and W7.4 requires no state writer. A later version may revisit this
only with a complete, versioned state design and golden equivalence evidence.

## Prototype

[`tools/tech-indicators/recursive-equivalence.py`](../../tools/tech-indicators/recursive-equivalence.py)
runs against the exact B1.1 NumPy 2.4.6 and TA-Lib 0.7.1 runtime. It creates
deterministic typical-price and high-offset fixtures with 20,000 observations
each, then evaluates:

- an append of observations 18,000 through 19,999;
- corrections at observations 5,000 and 19,500;
- full-prefix calculation with suffix-only combination; and
- a fixed 252-observation prefix restart for the same suffixes.

The compared recursive families are EMA 12/20/26/50, RSI 14, ATR 14,
PLUS_DI/MINUS_DI/ADX 14, and MACD 12/26/9. Null masks must match exactly;
finite values use absolute tolerance `1e-12` and relative tolerance `1e-10`.
The prototype fails unless every full-prefix case is equivalent and every
family is shown non-equivalent in at least one bounded-restart case. It also
enforces the P0.8 prototype gates of at most 120 seconds and 512 MiB peak RSS.

## Evidence

Both deterministic fixtures produced exact full-prefix equivalence for append
and both correction positions. The 252-observation restart failed as follows:

| Fixture | Scenario | Families with mismatches |
|---|---|---|
| Typical | Append | EMA, RSI, ATR, ADX, MACD |
| Typical | Correction at 5,000 | EMA, RSI, ATR, ADX, MACD |
| Typical | Correction at 19,500 | EMA, RSI, ATR, ADX, MACD |
| High offset | Append | RSI, ATR, ADX, MACD |
| High offset | Correction at 5,000 | RSI, ATR, ADX, MACD |
| High offset | Correction at 19,500 | RSI, ATR, ADX, MACD |

The high-offset EMA restart happened to fall within the relative tolerance;
the typical fixture proves that this is not a general fixed-prefix guarantee.
No nominal lookback or convergence heuristic is accepted.

The separately calculated `ema_12 - ema_26` also failed to reproduce TA-Lib's
single-call MACD line. On the typical fixture its first mismatch was observation
25, with 140 mismatches including eight null-mask mismatches; the high-offset
fixture had 105 mismatches including the same eight mask mismatches. The raw
MACD line, signal, and histogram therefore remain owned by one TA-Lib `MACD`
call and are not generated from stored EMA columns.

The clean local CPython 3.14.6 run completed in 0.031 seconds with 51.2 MiB peak
RSS. The CPython 3.13.13 Airflow-image run completed in 0.033 seconds with
119.9 MiB peak RSS. Timing is evidence for this prototype only, not a
replacement for W7.9 or V12.6 performance gates.

## Why State And Bounded Replay Are Rejected

EMA and Wilder recurrences retain prior state beyond their nominal periods.
Restarting the TA-Lib function API on a suffix creates a new seed rather than
restoring the full-series state. The persisted feature columns are not a
complete continuation state: RSI needs smoothed gain and loss, ATR needs its
smoothed true range, DI/ADX need directional-movement and DX/ADX state, and
MACD needs its internal EMA and signal state with TA-Lib-compatible warm-up.

Persisting a sufficient state would make Empire own a versioned replica of
TA-Lib recurrence internals, recovery rules, and atomic row/state advancement.
That complexity is not justified while full-prefix calculation is exact and
comfortably inside the representative prototype resource gates.
