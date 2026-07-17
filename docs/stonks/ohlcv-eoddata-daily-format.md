# EODData Daily Fixture Format Evidence

## Scope

This note records the evidence used to construct the first sanitized EODData
daily parser fixture for A5.3. The full production interpretation is now
defined by
[`ohlcv-eoddata-source-contract.md`](ohlcv-eoddata-source-contract.md),
including authentication, request partitions, duplicate handling, native price
semantics, and delivery timing.

## Request evidence

The user-provided legacy client requests one exchange and effective date with:

```text
GET <base-url>/Quote/List/<exchange>
    ?ApiKey=<runtime-secret>
    &DateStamp=YYYY-MM-DD
```

This preserves the casing used by that evidence request. The production
contract selects the provider-documented `apiKey` spelling.

It expects HTTP 200 and a top-level JSON array. The active Empire environment
uses `EMPIRE_STONKS_OHLCV_EODDATA_BASE_URL` and
`EMPIRE_STONKS_OHLCV_EODDATA_API_KEY`; the credential is never written to a
fixture, manifest, command output, or this document.

On 2026-07-16, a bounded authenticated request for exchange `NASDAQ` and
`DateStamp=2026-07-15` returned HTTP 200, 1,103,147 bytes, and 5,013 rows. The
temporary response was inspected locally and was not committed.

## Observed JSON format

The response was pretty-printed JSON with a top-level array. Each inspected row
had exactly these fields:

| Field | Observed JSON type | Observed role |
|-------|--------------------|---------------|
| `exchangeCode` | string | Provider-native market code (`NASDAQ`) |
| `symbolCode` | string | Provider-native symbol text |
| `interval` | string | Daily interval marker (`d`) |
| `dateStamp` | string | Trading date in `YYYY-MM-DD` form |
| `open` | number | Provider-supplied open |
| `high` | number | Provider-supplied high |
| `low` | number | Provider-supplied low |
| `close` | number | Provider-supplied close |
| `volume` | number | Provider-supplied volume |

Across this one response, `exchangeCode` was always `NASDAQ`, `interval` was
always `d`, and none of the OHLCV fields was null. Three rows had zero volume.
No inspected row had a zero OHLC value. These observations describe only the
sample and do not establish general provider nullability or value semantics.

## Fixture derivation

The committed `nasdaq_daily_valid.json` fixture uses the same top-level shape,
field names, field order, string forms, numeric JSON forms, daily marker, and
NASDAQ market value. It is constructed rather than copied: real symbols were
replaced with fixed fictional values and prices/volumes were replaced with
small representative values. The two rows cover ordinary OHLCV, exact symbol
case and punctuation, four-decimal numeric text, an equal open/high value, and
the observed zero-volume case.

The fixture deliberately excludes response rows and any non-OHLCV metadata not
needed for those parser behaviors. Additional valid or invalid fixtures require
new documented evidence or an explicit parser-contract case.
