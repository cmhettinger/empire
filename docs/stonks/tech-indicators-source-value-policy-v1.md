# Tech-Indicators Source-Value Policy V1

Status: frozen implementation contract for P0.6 as of 2026-08-09.

This document selects the provider-native OHLCV series eligible for the initial
tech-indicators calculator and freezes the claims consumers may make about
their values. It extends the
[`technical-indicators-design-contract.md`](technical-indicators-design-contract.md)
without creating adjusted, normalized, canonical, or cross-provider data.

The policy is deliberately independent of `provider_listing.status`. It says
whether a listing's source-value semantics are supported. Active, inactive,
explicit-backfill, source-correction, and affected-range behavior is frozen in
[`tech-indicators-recalculation-contract-v1.md`](tech-indicators-recalculation-contract-v1.md).
P0.5 remains authoritative for SPX-relative subject support.

## Initial Eligibility Predicate

A provider listing is source-value eligible only when it matches one row of
this table. Comparisons are exact and case-sensitive unless stated otherwise.

| Provider | Exact eligible identity | Additional required facts |
|---|---|---|
| `EODDATA` | market in `NYSE`, `NASDAQ`, `AMEX` | `metadata` is a JSON object and `upper(btrim(metadata ->> 'type')) = 'EQUITY'` |
| `STOOQ` | market in `nasdaq`, `nyse`, `nysemkt` | none; these exact markets are the selected U.S. stock partitions in the Stooq source contract |
| `YAHOO` | `market = XIDX`, `ticker = SPX` | `instrument_type_code = EQUITY_INDEX`; `metadata` is a JSON object whose string `YahooTicker` is exactly `^GSPC` |

The EODData type value alone is case-insensitive and whitespace-trimmed.
Missing, null, non-string, or different `metadata.type` is unsupported. Stooq
market names must not be folded to EODData spellings. Yahoo identity drift is
unsupported and separately causes the P0.5 benchmark resolver to fail closed
when an SPX-supported subject is selected.

Every other provider listing is initially source-value unsupported, including
the remainder of Yahoo's heterogeneous benchmark universe. Unsupported
listings are omitted from calculator selection; the calculator does not create
an all-null feature row for them. Expansion requires a reviewed change to this
contract and a new calculation version when persisted results could change.

`SOURCE_VALUE_UNSUPPORTED` is the bounded exclusion category. Implementations
may refine it in diagnostics as `UNSUPPORTED_PROVIDER`, `UNSUPPORTED_MARKET`,
`UNSUPPORTED_EODDATA_TYPE`, or `UNSUPPORTED_YAHOO_SERIES`; these are report and
calculation diagnostics, not new database columns.

## Audited Provider Semantics

The calculator copies the accepted `ohlcv_daily` values and computes directly
from them. The provider disclosures below are inherited from the implemented
OHLCV source contracts and durable report payloads:

- [`ohlcv-eoddata-source-contract.md`](ohlcv-eoddata-source-contract.md)
- [`ohlcv-stooq-history-source-contract.md`](ohlcv-stooq-history-source-contract.md)
- [`ohlcv-yahoo-source-contract.md`](ohlcv-yahoo-source-contract.md)

| Provider | Price and adjustment basis | Volume and currency basis | Corporate actions and corrections |
|---|---|---|---|
| `EODDATA` | Quote List OHLC is provider supplied; adjustment basis is `unspecified_by_eoddata_quote_list`; adjusted close is absent | volume is required and `provider_supplied_unspecified`; listing currency is best-effort metadata only and does not prove bar currency | no adjustment reconstruction; corrections overwrite the same provider series/date |
| `STOOQ` | history-bundle OHLC is provider supplied; adjustment basis is `unspecified_by_stooq_history_bundle`; adjusted close is absent | volume is required, may be fractional or zero, and is `provider_supplied_unspecified_fractional_allowed`; currency is unspecified | corporate-action interpretation is unspecified; corrections overwrite the same provider series/date |
| `YAHOO` | native unadjusted Chart quote OHLC is persisted; optional adjusted close is diagnostic only and never substitutes for close | volume is nullable and a returned zero remains zero; no currency repair or conversion occurs | event objects are ignored; no price repair, back-adjustment, or split reconstruction; corrections overwrite the same provider listing/date |

The exact report labels remain owned by the OHLCV implementation. A future
source-contract or report-label change must be reviewed here before technical
results are represented as equivalent.

Yahoo is initially restricted to SPX because V1 needs that exact benchmark for
market context but has no approved consumer for technical rows across the
broader mix of global indexes, volatility indexes, yields, currencies,
commodities, and futures. SPX receives ordinary non-SPX technical features.
Under the P0.5 subject predicate, its benchmark ID and all SPX-relative fields
remain null.

## Permitted And Prohibited Claims

The following are permitted:

- Describe a value as calculated from one exact provider-native listing.
- Compare one eligible listing with its own earlier observations, while
  disclosing that provider corrections and corporate actions can change or
  discontinuously move the series.
- Calculate dimensionless ratios and the nominal `dollar_volume` expression
  defined by the formula contract.
- For P0.5-supported EODData and Stooq subjects, describe SPX fields as
  provider-native price-relative statistics using exact common dates.

The following are not permitted:

- Calling any price, return, volume, or dollar-volume series adjusted,
  split-adjusted, dividend-adjusted, total-return, normalized, consolidated,
  canonical, consensus, or authoritative.
- Inferring bar currency from listing metadata or treating
  `dollar_volume = abs(close) * volume` as USD.
- Merging provider listings, filling one provider from another, inferring
  identity from tickers, or comparing values as though adjustment, currency,
  units, and corporate-action treatment match.
- Publishing cross-listing liquidity ranks from raw volume or dollar volume
  without a future consumer contract that proves compatible units, currency,
  adjustment basis, and universe membership.
- Describing SPX-relative output as total-return alpha or as proof that the
  subject and benchmark share adjustment or currency semantics.

V1 dollar-volume and volume averages are meaningful only as nominal,
within-listing time-series features. Dimensionless output does not itself prove
cross-listing comparability. Reports and exports must retain provider, market,
ticker, and this policy's native-semantics disclosure wherever values could be
interpreted outside their owning listing.

## Nulls, Discontinuities, And Corrections

Missing Yahoo SPX volume propagates to volume-dependent fields under the
feature and formula contracts; it never makes price-dependent fields null and
is never converted to zero. EODData and Stooq require non-null source volume.

A provider split, distribution, currency-unit change, methodology change, or
other discontinuity can affect returns, averages, volatility, TA-Lib output,
breakouts, dollar volume, and SPX-relative statistics. V1 does not detect or
repair those events. Consumers must not reinterpret the resulting movement as
an economically normalized return.

`ohlcv_daily` is current state. A provider correction may replace previously
stored OHLCV without an append-only bar revision. The tech-indicators package
must not mutate source bars. The
[`tech-indicators-recalculation-contract-v1.md`](tech-indicators-recalculation-contract-v1.md)
defines how source drift selects technical rows, and P0.9 defines atomic
publication.

## Evidence Boundary And Implementation Tests

OHLCV V10.11's
[`ohlcv-derived-value-audit.md`](ohlcv-derived-value-audit.md) audited all
20,671,779 stored bars and found no discrepancies in the shared derived-value
invariants, including first rows, zero-close predecessors, date gaps, and
corrected rows. That proves internal consistency of the current source table.
It does not prove adjustment, currency, volume, corporate-action, or
cross-provider comparability.

Implementation tests must cover:

- every exact eligible provider/market predicate and case-sensitive near miss;
- EODData type case/whitespace handling and missing or non-string metadata;
- Yahoo SPX identity facts and rejection of every other Yahoo series;
- source-value eligibility independent of listing status;
- null Yahoo volume propagation without zero synthesis;
- exact OHLCV report semantics and no adjusted-close substitution;
- omission of unsupported listings and bounded exclusion reasons; and
- report/export disclosure that rejects normalized, USD, total-return, or
  cross-provider-comparability claims.
