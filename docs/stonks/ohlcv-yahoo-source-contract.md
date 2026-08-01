# Yahoo Daily And Historical Source Contract

## Status And Scope

This document is the production source contract for the bounded Yahoo
benchmark universe in Phase 8 of `empire-stonks-ohlcv`. It selects the source,
request and response boundaries, runtime configuration, provider-listing
identity, native-value interpretation, raw-object layout, pacing, and failure
behavior shared by:

- A one-time, operator-controlled historical backfill.
- Repeated daily ingestion and recent-session reconciliation, initially
  invoked manually and later by a thin Airflow DAG.

The exact 93-listing starting universe is maintained in
[`docs/todo/ohlcv-task-plan.md`](../todo/ohlcv-task-plan.md#initial-yahoo-seed-universe).
Yahoo is not a second broad equity feed. Ordinary equities already covered by
EODData, profile data, fundamentals, news, options, intraday bars, and other
Yahoo enrichment are outside this contract.

The shared source identity is:

| Field | Value |
|-------|-------|
| Provider code | `YAHOO` |
| Source code | `yahoo_daily` |
| Parser version | `1.1.0` |
| Content type | `application/json` |
| Interval | `1d` |

Historical and daily requests use the same logical Chart dataset and response
shape, so they share `yahoo_daily`. Backfill is a run mode and report type, not
a second source. A materially different Yahoo dataset must receive a new source
code rather than silently reusing this one.

## Evidence And Legacy Review

The prior working implementation was reviewed from:

```text
tmp/stonks-ref/stonks/tools/misc/yahoo-index/yahoo_index.py
tmp/stonks-ref/stonks/tools/misc/yahoo-index/yahoo_index_daily.py
tmp/stonks-ref/stonks/remote/dags/yahoo/yahoo_daily_index_fetch.py
tmp/stonks-ref/stonks/apps/stonks-engine/src/stonks_engine/scrape/ohlcv/yahoo_xidx_daily/
tmp/stonks-ref/stonks/apps/stonks-engine/src/stonks_engine/scrape/ohlcv/yahoo_xidx_bulk/
```

That implementation proved these useful source behaviors:

- Yahoo symbols such as `^GSPC`, `DX-Y.NYB`, and `CL=F` can be requested as
  separate daily series.
- Historical and single-date downloads use `interval="1d"`.
- The start bound is inclusive and the end bound is exclusive.
- `auto_adjust=False` is required when using yfinance to avoid replacing
  provider OHLC with adjusted values.
- Missing daily rows are normal for some requested dates and are distinct from
  request errors.
- Serial requests, conservative spacing, jitter, bounded retry, and
  per-listing failure isolation are operationally important.
- The staged CSV shape was `ticker,date,open,high,low,close,volume`.

The old fetch/copy/ingest/map/apply stages, local incoming directories,
SQLAlchemy ownership, canonical `listing_id` mapping, synthetic zero volume,
insert-only final writes, pandas frames, and Airflow-embedded acquisition are
not carried forward. Empire uses Core raw objects, source snapshots, seeded
provider listings, shared current-state writers, package-owned sequencing, and
thin runtime callers.

[yfinance download documentation](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)
documents the inclusive start, exclusive end, daily interval, timeout, and
automatic-adjustment behavior. The
[current yfinance history implementation](https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/history.py)
provides implementation evidence for the Yahoo Chart request and response
interpretation. yfinance is evidence only; it is not an Empire runtime
dependency for this workflow.

## Source Selection And Operational Gate

Empire selects the HTTPS Yahoo Finance Chart resource:

```text
GET <base-url>/v8/finance/chart/<percent-encoded-yahoo-symbol>
```

The initial base URL is:

```text
https://query2.finance.yahoo.com
```

This Chart resource is an undocumented Yahoo Finance interface without a
published availability, retention, correction, or rate-limit guarantee. It is
not treated as an enterprise market-data contract. Before unattended
production scheduling is enabled, the operator must confirm that the intended
access, storage, and use are permitted under the applicable
[Yahoo terms](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apitnc/index.html).
Development and fixture capture use deliberately bounded requests.

Empire must not bypass authentication, browser verification, CAPTCHA,
rate-limit controls, access denials, or other provider safeguards. A response
requiring unsupported cookies, credentials, consent, or challenge handling is
a hard source failure and a reason to keep the workflow manual or disabled
until the source contract is deliberately revised.

## Runtime Configuration

Runtime code reads only `os.environ`. Local wrappers load
`deploy/env/local.env` through `bin/env-load`; Docker Compose and Airflow pass
the same values through their runtime environments. Package code never opens
an environment file.

Yahoo settings and initial defaults are:

```text
EMPIRE_STONKS_OHLCV_YAHOO_BASE_URL=https://query2.finance.yahoo.com
EMPIRE_STONKS_OHLCV_YAHOO_REQUEST_DELAY_SECONDS=25
EMPIRE_STONKS_OHLCV_YAHOO_REQUEST_JITTER_MIN_SECONDS=5
EMPIRE_STONKS_OHLCV_YAHOO_REQUEST_JITTER_MAX_SECONDS=10
EMPIRE_STONKS_OHLCV_YAHOO_FAILURE_COOLDOWN_MIN_SECONDS=8
EMPIRE_STONKS_OHLCV_YAHOO_FAILURE_COOLDOWN_MAX_SECONDS=18
EMPIRE_STONKS_OHLCV_YAHOO_BACKFILL_START_DATE=1965-01-01
EMPIRE_STONKS_OHLCV_YAHOO_BACKFILL_CHUNK_DAYS=3650
EMPIRE_STONKS_OHLCV_YAHOO_DAILY_LOOKBACK_DAYS=30
EMPIRE_STONKS_OHLCV_YAHOO_DAILY_REQUEST_MAX_DAYS=30
EMPIRE_STONKS_OHLCV_YAHOO_RECONCILIATION_SESSIONS=7
```

The common settings also apply:

```text
EMPIRE_STONKS_OHLCV_HTTP_TIMEOUT_SECONDS=30
EMPIRE_STONKS_OHLCV_MAX_RETRIES=3
EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS=7
EMPIRE_STORAGE_KEY_STONKS_OHLCV=stonks/ohlcv
```

`BASE_URL` must be an HTTPS origin without credentials, path, query, fragment,
or trailing slash. Tests inject a transport and do not use the configured
origin.

Delay, jitter, and cooldown values are finite non-negative seconds. Each
minimum must not exceed its matching maximum. The normal delay between
listings is:

```text
request_delay + random(request_jitter_min, request_jitter_max)
```

Random jitter changes timing only. Listing order, request identity, parsing,
and output remain deterministic.

`MAX_RETRIES=3` means at most three retries after the initial attempt.
`BACKFILL_START_DATE` is the default inclusive lower bound and must be an ISO
`YYYY-MM-DD` date. It does not claim Yahoo has history for every listing back
to that date. `BACKFILL_CHUNK_DAYS` must be from 1 through 3650 and bounds each
request to at most approximately ten calendar years. The CLI may tighten the
date range but may not exceed that chunk limit.

`RECONCILIATION_SESSIONS` must be from 1 through 30. The initial value of seven
means the daily workflow rechecks up to the latest seven expected sessions;
the calendar and eligibility design is finalized in Y8.2.

`DAILY_LOOKBACK_DAYS` must be from 1 through 365 and defines the default
inclusive operator planning window ending on the effective date.
`DAILY_REQUEST_MAX_DAYS` must be from 1 through 90 and bounds every range
created by daily completeness and reconciliation planning. Explicit CLI dates
may narrow the planning window but do not widen this per-request bound.

No Yahoo credential is required by this selected contract. If that changes,
the new secret must use the Yahoo prefix, receive redaction tests, and never
appear in a URL, log, exception, Core parameter, object metadata, report, or
Airflow payload.

## Provider-Listing Identity

The seed migration owns the controlled listing inventory. Normal Yahoo
acquisition and parsing must resolve one of those listings and must not create
an unseeded series.

| Shared listing field | Contract value |
|----------------------|----------------|
| `provider_code` | Constant `YAHOO` |
| `market` | Constant `XIDX` |
| `ticker` | Stable Empire code from the seed inventory |
| `name` | Reviewed seed name; Yahoo cannot overwrite it with enrichment |
| `instrument_type_code` | Reviewed seed instrument type |
| `metadata.YahooTicker` | Exact Yahoo request symbol |
| `session_policy_code` | Reviewed Y8.4 session-policy assignment |

`XIDX` is a stable Empire feed partition meaning the controlled cross-market
Yahoo benchmark universe. It is not a MIC, venue, exchange, country, or claim
that all series share one trading calendar. Per-listing session policies added
after Y8.2 own those distinctions.

The Empire code is a stable provider-scoped identifier, not a canonical
security-master ticker. The exact Yahoo symbol, including case and punctuation,
is read only from metadata key `YahooTicker` and percent-encoded as one URL path
segment. No Yahoo-specific relational ticker column or generic alias table is
needed. Normal acquisition must fail closed when `YahooTicker` is absent,
blank, non-string, or does not identify exactly one active seed row.

Yahoo Chart `meta.symbol` must agree with the requested `YahooTicker`. Safe
response facts such as `exchangeName`, `exchangeTimezoneName`, `currency`, and
`instrumentType` may be validated and reported, but they do not rewrite the
Empire ticker, `YahooTicker`, seeded identity, or session policy; infer a
canonical listing; or authorize enrichment storage.

## Request Contract

Each request addresses exactly one active seeded provider listing and resolves
its request path from `metadata.YahooTicker`. There is no multi-symbol request
and no broad Yahoo symbol discovery.

The fixed query inputs are:

```text
interval=1d
includePrePost=false
events=div,splits,capitalGains
period1=<inclusive lower Unix timestamp>
period2=<exclusive upper Unix timestamp>
```

`period1` and `period2` are bounded Unix seconds generated from an explicit
date plan. The requested range includes a small planner-owned boundary guard
when needed; the parser still accepts only planned provider session dates.
Request timestamps are not stored as bar dates.

The historical backfill:

- Uses an explicit inclusive start and end date, defaulting the start to
  `BACKFILL_START_DATE`.
- Splits each listing into deterministic ascending chunks no larger than
  `BACKFILL_CHUNK_DAYS`.
- Acquires every chunk separately and can safely resume or replay completed
  chunks through Core checksum identity and current-state upserts.
- Does not fabricate rows before the provider's first returned observation.

The daily workflow:

- Receives eligible missing sessions and the reconciliation window from the
  package-owned planner.
- May consolidate adjacent planned dates for one listing into one bounded
  request.
- Filters the response to the exact planned sessions.
- Treats no returned row for a planned session as missing/retryable, not as a
  zero-valued bar.

A completely planned daily pass can make at most one initial request per
selected listing after consolidation. The reviewed active universe therefore
has an upper bound of 90 initial requests, plus bounded retries. The original
93 seed rows remain durable: unsupported rows are inactive rather than erased.
Most repeated runs should plan substantially less work because complete
ineligible rows are skipped before acquisition.

## Response And Daily-Bar Contract

A successful response is HTTP 200, UTF-8 JSON, with:

```text
chart.error = null
chart.result = [one result]
```

The selected result contains:

```text
meta.symbol
meta.exchangeName
meta.exchangeTimezoneName
timestamp[]
indicators.quote[0].open[]
indicators.quote[0].high[]
indicators.quote[0].low[]
indicators.quote[0].close[]
indicators.quote[0].volume[]
indicators.adjclose[0].adjclose[]  # optional
```

The timestamp and quote arrays are positionally aligned. Required OHLC arrays
must match the timestamp length. Each accepted position maps as follows:

| Shared bar field | Yahoo Chart value |
|------------------|-------------------|
| `trading_date` | Provider session date derived from `timestamp` using the validated response time zone and Y8.2 session-date rule |
| `open` | `quote[0].open[index]` |
| `high` | `quote[0].high[index]` |
| `low` | `quote[0].low[index]` |
| `close` | `quote[0].close[index]` |
| `volume` | `quote[0].volume[index]`, preserving null |

Numbers are parsed to `Decimal` without a binary-float round trip. All four
OHLC values must be present and finite for an accepted bar. Yahoo volume may be
null for indexes and is preserved as `None`; missing volume must never be
converted to zero. A returned zero remains zero. Shared OHLC and non-negative
volume validation still applies.

Daily timestamps represent provider observations, not UTC calendar dates. The
parser must use validated time-zone/session rules rather than truncating a UTC
timestamp or trusting the requested date. Publisher indexes and continuous
futures require the explicit policies designed in Y8.2.

Equal duplicate observations for one `(provider_listing, trading_date)` may
collapse with a warning. Conflicting duplicates reject that date rather than
using first-wins, last-wins, highest-volume, or input-order behavior. Array
length mismatches, a symbol mismatch, malformed JSON, multiple results, or an
unexpected top-level shape are structural source failures.

A Chart result with matching `meta.symbol`, valid empty `indicators`, and a
null, absent, or empty `timestamp` is an explicit no-history response. Daily
acquisition records it as missing/retryable; historical backfill records
`no_backfill_data`. Missing indicators, non-empty indicator arrays without
timestamps, provider errors, and symbol mismatches remain distinct failures.

The 2026-08-01 availability review corrected `JTOPI` from `^JA0R.JO` to
`^J200.JO` and `SET` from `^SET` to `^SET.BK`. `IPSA`, `MSCIEM`, and `RVX`
remain as durable seed rows but are inactive with `metadata.YahooSeedReview`
explaining the unsupported Chart disposition. Active listing enumeration
therefore excludes them without deleting their reviewed identities.

## Native Adjustment And Correction Semantics

Empire stores Yahoo's native unadjusted Chart `quote` OHLC values. This matches
the legacy `auto_adjust=False` intent without depending on yfinance defaults.
Empire does not run yfinance price repair, back-adjustment, split
reconstruction, currency repair, rounding, or other transformations.

Yahoo may separately return `indicators.adjclose`. The initial shared
`ohlcv_daily` table has no adjusted-close column. Adjusted close is therefore:

- Retained in the short-lived raw response.
- Compared and described in parsing/reconciliation results when present.
- Documented in Yahoo reports as supplied but not persisted per bar.
- Never substituted for `close`.

Corporate-action event objects are ignored by this OHLCV workflow. Their
presence does not authorize corporate-action normalization or enrichment.

Yahoo may publish a bar late or correct OHLC, adjusted close, or volume after
initial availability. Current-state upserts update distinct stored OHLCV
values. The configured recent-session reconciliation pass detects and reports
corrections without creating an append-only revision table. Because adjusted
close is not persisted, it can be compared within the current raw
reconciliation operation but cannot be audited historically after raw cleanup.

## Raw Objects And Source Snapshots

Every successful HTTP response is stored through Empire Core before parsing.
One response is one `yahoo_daily` raw JSON object. Raw objects use the normal
approximately seven-day retention and durable checksum/source/parser identity.

The stable multipart filename is:

```text
raw-<provider-listing-uuid>-<start-date>-<exclusive-end-date>.json
```

The lowercase canonical provider-listing UUID avoids unsafe Yahoo punctuation
in filenames while retaining deterministic request identity. Dates are
`YYYY-MM-DD`. The raw object's safe metadata extends the common allowlist with:

```json
{
  "schema_version": 1,
  "provider_code": "YAHOO",
  "source_code": "yahoo_daily",
  "parser_version": "1.0.0",
  "provider_listing_id": "lowercase UUID",
  "market": "XIDX",
  "ticker": "stable Empire code",
  "request_start_date": "YYYY-MM-DD",
  "request_end_date_exclusive": "YYYY-MM-DD",
  "request_mode": "daily or backfill",
  "effective_date": "YYYY-MM-DD",
  "acquired_at": "UTC RFC 3339 timestamp",
  "retention_days": 7
}
```

The full URL, query string, headers, cookies, response headers, local paths, and
complete configuration dictionary are not stored. Core's first-class filename,
content type, size, checksum, and object timestamps remain authoritative.

For a daily run, `effective_date` is the explicit run date used by the planner
and Core partition. For a historical backfill, it is the operator-supplied
backfill execution/evidence date, not the first or last bar date.

## Rate, Retry, Empty, And Error Behavior

Yahoo publishes no quota or completion SLA for this selected interface. Empire
therefore uses conservative serial acquisition by default and reports actual
request outcomes.

Retryable conditions are:

- HTTP 408, 425, 429, and 5xx responses.
- Connection reset, timeout, and equivalent transient transport failures.

Other 4xx responses are non-retryable. A bounded `Retry-After` value may be
honored. Without one, retries use exponential backoff plus the configured
jitter. After one listing exhausts retries, the runner applies the configured
failure cooldown before continuing. It must not hold an Airflow worker in an
unbounded sleep; the listing remains retryable in a later run.

HTTP 200 is not sufficient by itself. HTML, empty bytes, malformed JSON,
`chart.error`, null/missing results, or an invalid Chart shape are failures or
explicit missing outcomes according to the response:

- A recognized no-data result for a valid seeded symbol/range is recorded as
  missing and retryable.
- An invalid symbol, delisted response, authorization response, or structural
  error is a listing failure.
- An entirely empty successful backfill is a failure for that listing.
- One listing failure does not discard successful raw objects or successful
  listings from the same bounded run.

Errors, logs, Core records, reports, and Airflow payloads contain only safe
provider/listing/range/status information. Raw provider error bodies remain in
the short-lived Core object when an HTTP 200 Chart payload was stored but later
failed structural/provider-error validation; their text is not copied into
operational summaries.

## Implementation Handoff

Y8.1 does not implement acquisition or parsing. The later Phase 8 tasks own:

- The completed Y8.2
  [market-session contract](ohlcv-market-session-contract.md) defines calendar,
  availability, provider-session, missing-session, and reconciliation rules.
- Y8.4 persisted session policy and seed rows.
- Y8.6 the injected HTTP transport, exact guarded timestamp construction,
  retries, raw storage, and a bounded live-format probe.
- Y8.7 fixtures and deterministic parsing against captured Chart JSON.
- Y8.9 implements seeded-universe backfill orchestration, inclusive
  Empire-ticker resume, per-chunk retry/import isolation, Core lifecycle, and
  a durable secret-safe execution report.
- Y8.10-Y8.14 completeness planning, reconciliation, reporting, CLI, and DAG.

The endpoint and response shape must be revalidated with a small permitted live
request before production fixture bytes are committed. If the provider requires
unsupported authentication/challenge behavior or the response materially
differs, revise this contract explicitly rather than hiding the change behind
yfinance, browser automation, or parser heuristics.
