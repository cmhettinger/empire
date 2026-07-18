# EODData Nightly Source Contract

## Status And Scope

This document is the production source contract for the initial EODData daily
vertical slice in `empire-stonks-ohlcv`. It selects the provider endpoints,
request partitions, runtime configuration, response interpretation, duplicate
policy, and provider-native value semantics implemented by Phase 6.

The workflow imports provider-native listings and daily bars for exactly these
EODData exchange codes:

```text
NYSE
NASDAQ
AMEX
```

It does not map those codes to canonical Empire exchanges or infer canonical
security identity. EODData values remain isolated from Stooq, Yahoo, and future
canonical series.

The provider documentation used for this contract is:

- [EODData API](https://api.eoddata.com/), including the Symbol List and Quote
  List operations.
- [EODData API service](https://www.eoddata.com/products/API.aspx), including
  query-string API-key authentication and advertised end-of-day OHLCV scope.
- [EODData availability FAQ](https://www.eoddata.com/support/FAQ.aspx), which
  says data begins arriving at approximately 5 p.m. market time and receives
  updates and corrections until 7 p.m. market time.
- [EODData membership information](https://www.eoddata.com/products/), which
  describes exchange-local timing and plan-dependent API rate limits.

The sanitized daily-format evidence in
[`ohlcv-eoddata-daily-format.md`](ohlcv-eoddata-daily-format.md) remains the
fixture-level evidence for the observed Quote List JSON representation.

## Runtime Configuration

Runtime code reads only `os.environ`. Local wrappers load
`deploy/env/local.env` through `bin/env-load`; Docker Compose and Airflow pass
the same settings through their runtime environments. Package code never opens
an environment file.

The EODData settings are:

```text
EMPIRE_STONKS_OHLCV_EODDATA_API_KEY=<required secret>
EMPIRE_STONKS_OHLCV_EODDATA_BASE_URL=https://api.eoddata.com
EMPIRE_STONKS_OHLCV_EODDATA_EXCHANGES=NYSE,NASDAQ,AMEX
```

`API_KEY` is required only when EODData acquisition runs. It is sent as the
`apiKey` query parameter. A query-bearing URL, request headers, credential
value, or complete request object must never appear in logs, exceptions, Core
run parameters, object metadata, reports, filenames, or Airflow payloads.

`BASE_URL` is non-secret. Its default and initial production value are
`https://api.eoddata.com`. Implementations remove a trailing slash before
joining the fixed endpoint paths. Production configuration must use HTTPS and
must not include user information, a query, or a fragment. Tests inject a
transport and do not require a live URL.

`EXCHANGES` is an explicit ordered allowlist. Initial configuration must
contain each of `NYSE`, `NASDAQ`, and `AMEX` exactly once and no other value.
Whitespace around comma-separated items may be removed while reading config,
but the request and stored `market` values use the exact uppercase codes above.
The deterministic request order is NYSE, NASDAQ, then AMEX.

The existing common timeout, retry, raw-retention, and storage-key settings
also apply:

```text
EMPIRE_STONKS_OHLCV_HTTP_TIMEOUT_SECONDS=30
EMPIRE_STONKS_OHLCV_MAX_RETRIES=3
EMPIRE_STONKS_OHLCV_EODDATA_REQUEST_DELAY_SECONDS=2
EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS=7
EMPIRE_STORAGE_KEY_STONKS_OHLCV=stonks/ohlcv
```

EODData membership levels have plan-dependent call limits. One normal nightly
run makes six initial HTTP requests before any bounded retry: two endpoints for
three exchanges. Acquisition spaces consecutive requests by the configured
delay, treats rate limiting as an explicit provider response, honors a safe
`Retry-After` value when supplied, and never logs the authenticated URL. When
the provider omits `Retry-After`, bounded exponential backoff begins at two
seconds.

## Effective Date And Delivery Window

Every run has one explicit effective date. It is the intended US exchange
trading date, represented as `YYYY-MM-DD`, and is used for the Core run and
object path. Package code must not derive it from wall-clock time or from a
Symbol List row.

The Quote List request sends the effective date as `DateStamp`. Every accepted
Quote List row must carry that same `dateStamp`. The Symbol List endpoint has no
effective-date request parameter in this workflow; a symbol row's `dateStamp`
is provider observation data and does not define listing validity, activity,
`first_seen`, or `last_seen`.

EODData says end-of-day data may be corrected until 7 p.m. market time. Any
future nightly schedule should therefore run no earlier than 8 p.m. in the
`America/New_York` timezone, leaving a one-hour operational buffer for NYSE,
NASDAQ, and AMEX. The initial Airflow DAG is manual-only (`schedule=None`), with
catchup disabled and at most one active DAG run. Manual runs and reruns may
provide `dag_run.conf.effective_date` as an explicit `YYYY-MM-DD` override; if
omitted, the DAG derives the New York date from `data_interval_end`.

Empire does not yet own an exchange calendar. A weekday may be a market
holiday, and a provider may publish late. Consequently, response dates and
freshness are validated and reported, but the ingestion contract does not
claim that every weekday must contain bars.

## Ordered Requests

Acquisition completes all Symbol List requests before any Quote List request:

```text
GET <base-url>/Symbol/List/NYSE?apiKey=<secret>
GET <base-url>/Symbol/List/NASDAQ?apiKey=<secret>
GET <base-url>/Symbol/List/AMEX?apiKey=<secret>

GET <base-url>/Quote/List/NYSE?apiKey=<secret>&DateStamp=YYYY-MM-DD
GET <base-url>/Quote/List/NASDAQ?apiKey=<secret>&DateStamp=YYYY-MM-DD
GET <base-url>/Quote/List/AMEX?apiKey=<secret>&DateStamp=YYYY-MM-DD
```

Query parameter order is not semantically significant and must not be used as
object identity. Each successful response is stored through Empire Core before
the next stage consumes it. A later request failure leaves already stored raw
objects available for inspection; it does not begin the database transaction
or delete raw evidence.

Both endpoints must return HTTP 200 and a UTF-8 JSON top-level array. HTML,
malformed JSON, a non-array top level, an authentication/authorization error,
or another non-success response is not a valid empty feed.

## Source Identity And Raw Objects

The established source identities remain:

| Purpose | `source_code` | `parser_version` |
|---------|---------------|------------------|
| Symbol List discovery | `eoddata_symbol_list` | `1.0.0` |
| Daily Quote List | `eoddata_daily` | `1.0.0` |

Exchange is a request partition, not a source code. The six raw objects use
`application/json` and these exact filenames beneath their source-code keys:

| Source code | Exchange | Filename |
|-------------|----------|----------|
| `eoddata_symbol_list` | NYSE | `raw-nyse.json` |
| `eoddata_symbol_list` | NASDAQ | `raw-nasdaq.json` |
| `eoddata_symbol_list` | AMEX | `raw-amex.json` |
| `eoddata_daily` | NYSE | `raw-nyse.json` |
| `eoddata_daily` | NASDAQ | `raw-nasdaq.json` |
| `eoddata_daily` | AMEX | `raw-amex.json` |

The existing raw-object metadata allowlist is extended for these objects by
one safe scalar:

```json
{
  "schema_version": 1,
  "provider_code": "EODDATA",
  "source_code": "eoddata_symbol_list",
  "parser_version": "1.0.0",
  "market": "NYSE",
  "effective_date": "YYYY-MM-DD",
  "acquired_at": "UTC RFC 3339 timestamp",
  "retention_days": 7
}
```

For a daily object, `source_code` is `eoddata_daily`. `effective_date` is the
run scope even for the undated Symbol List request. Core's first-class fields
remain authoritative for filename, media type, size, checksum, and object key.

## Symbol List Contract

### Selected fields

The Symbol List response is used only for listing discovery and best-effort
descriptive metadata. The selected provider fields map as follows:

| Shared listing field | EODData source |
|----------------------|----------------|
| `provider_code` | Constant `EODDATA` |
| `market` | Trusted exchange request partition |
| `ticker` | Required `code` |
| `name` | Optional non-blank `name` |
| `instrument_type_code` | Constant `UNKNOWN` |
| metadata `type` | Optional non-blank `type` |
| metadata `currency` | Optional non-blank `currency` |

Only present, usable `type` and `currency` values are included in the metadata
object. If neither is usable, metadata is `None`. Missing, null, blank, or
unexpectedly typed optional descriptive values do not invalidate the provider
identity; they are omitted and may be counted as warnings by the later
validation/report contract. They are not inferred from the exchange, provider
marketing material, or another symbol.

`instrument_type_code` remains `UNKNOWN` even when EODData supplies a value
such as `Equity`. Empire has not approved a mapping from provider types to
`stonks.instrument_type`.

Although observed Symbol List rows also contain `dateStamp`, OHLC, volume,
open-interest, previous-close, and change-like fields, this workflow ignores
all of them. Only Quote List supplies `ohlcv_daily` inputs. In particular,
provider `change` is never stored as Empire's derived `change` value.

### Symbol identity and duplicates

Within one exchange payload, rows are grouped by the exact case-sensitive
`code`. The exchange request partition plus that exact code forms the provider
listing identity. The parser does not trim or case-normalize a code; an empty,
blank, surrounding-whitespace, or non-string code is structurally invalid.

Duplicate codes are resolved before shared persistence:

- For each of `name`, `type`, and `currency`, ignore missing/null/blank values
  and collect the distinct usable values without normalization.
- If every field has zero or one distinct usable value, the duplicate group is
  compatible. Emit one listing using the available values and record the
  collapsed row count as a warning/metric.
- If any field has more than one distinct usable value, the duplicate group is
  conflicting. Reject the entire provider-listing identity and record a
  bounded issue containing only the safe exchange, code, and conflicting field
  names. Do not select the first, last, newest, or most complete row.

Rows for the same ticker on different exchanges are different provider
listings and are not duplicates.

An empty Symbol List array is a hard source failure because the selected
endpoint is expected to provide the exchange inventory. A missing symbol does
not delete or inactivate an existing `provider_listing`; `status` remains
operator-owned.

## Quote List Contract

Each selected Quote List row has this shape:

| Shared bar input | EODData source |
|------------------|----------------|
| listing market | Required `exchangeCode` |
| listing ticker | Required `symbolCode` |
| interval guard | Required literal `d` in `interval` |
| `trading_date` | Required `dateStamp` matching the run effective date |
| `open` | Required finite JSON number `open` |
| `high` | Required finite JSON number `high` |
| `low` | Required finite JSON number `low` |
| `close` | Required finite JSON number `close` |
| `volume` | Required non-negative JSON number `volume` |

Numbers are parsed directly to `Decimal` without a binary-float round trip.
Zero volume is valid. The shared OHLC invariants still apply. The provider
supplies no adjusted-close field in the selected response.

`exchangeCode` must exactly equal the trusted request partition,
`symbolCode` must be a valid exact provider ticker, `interval` must be `d`, and
`dateStamp` must equal the explicit effective date. An exchange, interval, or
date mismatch is a structural payload failure rather than a second request
scope silently entering the run.

Quote rows are grouped by exact `(exchangeCode, symbolCode, dateStamp)` before
persistence:

- Duplicate rows whose five OHLCV input values are exactly equal collapse to
  one bar and produce a duplicate warning/metric.
- If any OHLCV input differs, reject the entire duplicate bar identity and
  record a bounded issue. Never use first-wins or last-wins behavior.

Every accepted quote must reconcile to an accepted Symbol List identity for
the same exchange in the same run. A quote without such a listing is rejected
and reported; the Quote List parser does not synthesize a listing. A Symbol
List identity without a quote is normal and is still upserted as a provider
listing.

An empty Quote List array is structurally valid because the effective date may
be a holiday or other non-trading date. It imports no bars and produces a
warning/freshness signal. This contract deliberately does not distinguish a
holiday from late or missing provider delivery without an exchange calendar.

## Provider-Native Value Semantics

EODData describes the selected feed as end-of-day OHLCV, but the selected
response and available provider documentation do not establish whether its
OHLC fields are split/dividend adjusted, whether volume is adjusted, or whether
corrections follow a versioned policy. Therefore Empire records these semantics
as:

```text
bar_interval = daily
ohlc_adjustment_basis = unspecified
adjusted_close_present = false
volume_adjustment_basis = unspecified
provider_corrections = overwrite current value on later import
```

The EODData Symbol List `currency` value is best-effort listing metadata only.
It does not trigger price conversion and does not prove the currency of an
individual stored bar. Empire stores `open`, `high`, `low`, `close`, and
`volume` exactly as parsed from Quote List, subject only to the shared database
scale and validation contracts.

Empire calculates `change`, `changepct`, `typ`, `hl_range`, and `oc_range` from
stored-scale values. It ignores any provider-supplied change, previous-close,
technical, or adjustment field outside the selected Quote List OHLCV inputs.

Operational reports must repeat the unspecified adjustment and currency
caveats so consumers do not compare EODData values to other providers as if
their bases were known to match.

## Failure, Warning, And Rerun Expectations

Hard source or structural failures include authentication failure, malformed
or non-array JSON, an empty Symbol List, and exchange/date/interval scope
mismatches. Already stored raw objects remain available, and no listing or bar
database changes from the attempt commit.

Record-level conditions such as conflicting duplicate identities, invalid
OHLCV rows, and quotes without accepted listings are rejected and reported
under the shared E6.5 validation/result contract. Compatible duplicates and an
empty Quote List are warnings. Symbols without a quote and absent optional
listing metadata are expected provider conditions, though aggregate metadata
omission counts may still appear in reports.

A safely rejected group does not fail the completed run. It produces a `WARN`
report outcome and is counted under its exact market, source, and rejection
reason with separate grouped-identity and raw-row totals. `FAIL` is reserved for
partition/run-integrity failures. Aborting acquisition and parsing failures add
the safe market and source code to the Core failure summary when the failing
partition is known; persistence/reporting failures remain whole-run scoped.

Report coverage, freshness, series, and weekday-gap health are evaluated as of
the run effective date. Stored bars from a later successful run are excluded
from those calculations, so rerunning an older provider date does not create
false future-date failures. Wrong-date rows in the current payload still fail
the trusted request-scope checks before persistence.

All issue samples are bounded and contain only safe provider identity fields;
they never include response bodies, authenticated URLs, request headers, or
credentials.

Reacquiring or reparsing the same content is safe. Source snapshots use the
existing provider/source/checksum identity, compatible duplicates produce
deterministic shared records, listing writes are idempotent, identical bars are
unchanged, and a later provider correction updates the current bar rather than
creating a revision row.

## Explicit Exclusions

This source contract does not authorize:

- Canonical exchange, security, or listing mapping.
- Inference of instrument type from EODData `type`.
- Automatic inactivation or deletion when a symbol disappears.
- Bars from Symbol List quote-like fields.
- Intraday, weekly, monthly, historical-range, split, dividend, fundamental,
  profile, technical-indicator, or enrichment endpoints.
- Price/currency conversion, adjustment reconstruction, cross-provider merge,
  or authoritative OHLCV selection.
- Per-row Core run or source-snapshot foreign keys.
