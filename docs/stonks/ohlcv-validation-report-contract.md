# OHLCV Validation, Counts, And Report Contract

## Scope

This contract defines the provider-neutral validation outcomes, scoped counts,
issue sampling, and health-report meanings used by the initial EODData, Stooq,
and Yahoo vertical slices. Provider parsers retain their own source formats and
may reject source-specific conditions, but they carry outcomes through the
shared records in `empire_stonks_ohlcv.validation`.

This contract does not add an exchange calendar, canonical listing mapping,
cross-provider normalization, database health queries, or report storage.
E6.6 owns transactional EODData persistence, E6.7 owns the first health queries,
and E6.8 owns report construction and Core object storage.

## Structural Validation

An accepted shared daily bar has:

- An exact provider listing identity and a `date` trading date.
- Finite `Decimal` values for `open`, `high`, `low`, and `close`; none may be
  null.
- `high >= low`, `high >= open`, `high >= close`, `low <= open`, and
  `low <= close`.
- Either null volume when the provider source contract permits missing volume,
  or a finite, non-negative `Decimal` volume. EODData requires volume; a null,
  missing, non-numeric, non-finite, or negative EODData volume is rejected.

Prices are not required to be positive. That would impose a market-domain rule
not present in the database contract. Persistence converts accepted values to
the database scales and calculates derived values; parsers and validators never
accept provider-supplied derived values.

The immutable `DailyBar` model enforces the provider-neutral numeric and OHLC
invariants. A parser must enforce its source-specific identity, date, interval,
nullability, and volume rules before producing accepted shared records.

## Outcome Severity

### Hard failures

A hard failure aborts parsing or the transactional import. It produces no
successful write counts. Raw objects already stored through Core remain
available. Hard failures include:

- Transport, authentication, required-object, content-type, malformed JSON,
  and non-array payload failures.
- An empty feed when its provider contract requires inventory, such as EODData
  Symbol List.
- Trusted request-scope mismatches such as provider, exchange, interval, or
  effective date.
- Structurally invalid required native identities.
- A parser emitting duplicate shared listing identities or duplicate bar dates
  after its documented duplicate policy should have resolved them.
- Source metadata that does not exactly match acquired objects.
- Database, constraint, or transaction failures. Persistence failures are not
  converted into rejected records.

### Rejected records

A rejected record or grouped identity is excluded while other valid records in
the source partition may continue. Initial examples are conflicting EODData
Symbol List duplicates, invalid Quote List OHLCV groups, conflicting Quote List
duplicates, and quotes without an accepted same-exchange Symbol List identity.

`rejected_records` counts post-grouping record identities, not raw rows. A
provider-specific result may additionally retain rejected-row counts for
diagnostics. Rejected identities have rejection issues; they do not reach either
writer.

Rejected identities are not hard failures. A completed import with any row
rejections has report outcome `WARN`, provided no partition/run-integrity
failure is present. Every rejection bucket retains its exact `market`,
`source_code`, reason `code`, rejected identity count, rejected raw-row count,
and bounded safe samples.

### Warnings and expected conditions

Compatible duplicate groups and a structurally valid empty optional feed are
warnings. Missing best-effort descriptive metadata may be counted as a warning
without invalidating a listing. A discovered symbol with no quote is an
expected listing-feed condition and is reported as a count, not a failure.

Warnings do not change accepted records. Inactive provider listings are
operator-owned; skipping their bars is a persistence outcome and must not be
reported as a provider parse failure.

## Bounded Issues

Hard failures and warnings use bounded issue summaries. Row rejections use
`RowRejectionSummary`, which applies the same `MAX_ISSUE_SAMPLES` (100) bound
within each exact market/source/reason bucket. `sample_count` and `truncated`
make omission explicit.

Providers order samples by their stable source order, configured market order,
exact provider record identity, and issue code. Samples may contain safe source
codes, market/ticker references, and conflicting field names. They must not
contain payload bodies, credentials, authenticated URLs, request headers,
account data, or uncontrolled transport/database exception text.

## Count Grains

Counts from different grains are never added together as if they represented
the same records.

### Feed outcomes

Each `FeedOutcomeCounts` is keyed by exact `(source_code, market)` and contains:

- `input_rows`: raw rows in that source partition.
- `accepted_records`: unique shared records emitted after grouping,
  source-specific validation, and reconciliation.
- `rejected_records`: unique grouped identities rejected after grouping.
- `duplicate_rows_collapsed`: extra compatible raw rows removed by the
  deterministic duplicate policy.
- `warning_count`: warning events for that source partition.

These values are not a required arithmetic partition of `input_rows` because a
compatible duplicate group can later be rejected during cross-feed
reconciliation. Listing-feed and quote-feed counts remain separate even when
their accepted records are carried in one reconciled shared output.

### Persistence outcomes

Each `SourceMarketWriteCounts` is keyed by exact
`(source_code, market, record_kind)`, where `record_kind` is `listing` or `bar`.
Its existing `PersistenceCounts` contains mutually exclusive `inserted`,
`updated`, and `unchanged` input outcomes plus separate `derived_updated`
maintenance. Bar records also carry `skipped_inactive`; listing records always
use zero because inactivity does not prevent listing metadata resolution.

Listing writes and bar writes remain separate by source and market. Aggregate
provider totals may sum the same record kind across markets, but reports must
retain the scoped rows. A rolled-back transaction has no successful write
counts.

### Cross-feed outcomes

`CrossFeedOutcomeCounts` retains exact reconciliation outcomes for one market:
`listings_without_bars` counts accepted discovery identities with no source bar,
and `bars_without_listings` counts bar identities rejected because the same-
market listing feed did not contain them. These expected/rejected cross-feed
conditions remain distinct from generic feed rejection and duplicate counts.

### Shared validation boundary

`ProviderValidationResult` carries accepted `ParsedProviderOutput` into
persistence alongside feed counts, typed row-rejection buckets, and bounded
hard-failure/warning summaries. Its
compact JSON form reports sources and counts without serializing every bar.
Provider-specific parsers may keep richer diagnostics, but persistence and
reporting consume this shared boundary.

## Health And Coverage Metrics

Health metrics are provider- and market-scoped. Normal freshness, stale-series,
and gap sections include active listings only. Inactive listings appear in a
separate count or section and do not create ordinary provider-health warnings.

For an explicit report `as_of_date`:

- `first_trading_date` and `last_trading_date` are the minimum and maximum
  stored dates in scope.
- `bar_count` is the stored current-row count, not an expected-session count.
- `listing_count`, `listings_with_bars`, and `listings_without_bars` describe
  active provider series; inactive listing counts are separate.
- `latest_bar_calendar_age_days` is
  `as_of_date - last_trading_date` in calendar days, or null when no bar exists.
- `latest_bar_weekday_age` counts Monday-Friday dates in
  `(last_trading_date, as_of_date]`, or is null when no bar exists.
- Provider/market freshness is `current` at weekday age 0, `delayed` at weekday
  age 1, `stale_candidate` at weekday age 2 or greater, and `no_data` when no
  bar exists. A future last date is a data-quality failure rather than a
  negative age.
- An active series is a stale candidate when its weekday age is at least 2.
  An active series with no bars is reported separately as a no-data candidate.
- A weekday-shaped gap is a missing Monday-Friday date strictly between two
  stored dates for one active series. Gap totals are complete; samples are
  deterministic and bounded by the shared issue limit.

`latest_bar_weekday_age`, stale candidates, and weekday-shaped gaps are
operational heuristics only. Empire does not yet own an authoritative exchange
calendar, so holidays and exceptional closures can resemble missing bars.
Reports must use `candidate`/`warning` language and must not claim these dates
are definitively missing exchange sessions.

## Stored Report Shape

The EODData JSON report uses `schema_version: 2` and contains:

```text
schema_version
provider_code
effective_date
generated_at
outcome
sources[]
  source_code
  parser_version
  acquired_objects by market
markets[]
  market
  row_rejections
  listing_feed
  quote_or_bar_feed
  listing_write
  bar_write
  duplicate_outcomes
  cross_feed_outcomes
  coverage
  freshness
  stale_candidates
  weekday_gap_warnings
inactive_series
hard_failures by market and reason
row_rejections by market, source, and reason
warnings
native_value_semantics
```

Every market section retains the scoped feed/write records and its rejection
summary. Top-level row rejections include rejected identity and raw-row totals;
hard failures contain an entry for every configured market and reason counts
for affected markets. `PASS` means no hard failures, rejections, or warnings;
safe rejections or warnings produce `WARN`; only integrity failures produce
`FAIL`. Native-value notes state interval, adjustment basis, adjusted-close
presence, volume basis, correction behavior, and provider-specific currency
caveats. Reports and Core run summaries remain secret-safe; only the stored
report contains detailed health samples, while Airflow and CLI results stay
compact.
