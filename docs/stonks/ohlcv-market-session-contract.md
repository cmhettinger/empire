# OHLCV Market-Session Eligibility Contract

## Status And Scope

This document defines the shared market-session and daily-bar eligibility
contract for `empire-stonks-ohlcv`. Yahoo is the first consumer, and the same
contract is intended for calendar-aware EODData scheduling. Provider
acquisition, parsing, and Airflow orchestration remain separate concerns.

The contract answers four questions for each active provider listing:

1. Which dates are authoritative expected market sessions?
2. When is a completed session eligible for provider acquisition?
3. How does a provider daily timestamp become `ohlcv_daily.trading_date`?
4. Which eligible dates are missing or should be reconciled?

The contract never creates price data. It produces dates and eligibility
decisions; only a validated provider observation can create or update an
`ohlcv_daily` row.

## Selected Calendar Library

Empire selects
[`pandas_market_calendars`](https://pandas-market-calendars.readthedocs.io/en/stable/)
for calendar-backed policies. Y8.5 should add a Poetry dependency compatible
with the current major version (`>=5.4,<6`) and lock the resolved dependency
graph.

This dependency is justified despite bringing pandas because maintaining
global exchange holidays, historical rule changes, daylight-saving
transitions, special sessions, and early closes ourselves would be a larger
and riskier capability. The library provides registered calendar names,
timezone-aware valid days and schedules, special closes, equity/futures/OTC
and bond calendars, and access to the `exchange_calendars` set. Those are
exactly the rules the planner needs and materially reduce Empire-owned
calendar code.

The library is a schedule engine, not an authority for provider publication
behavior. A listed calendar name is not sufficient evidence that it matches a
Yahoo symbol. Every persisted mapping must be reviewed and verified with
representative dates before activation.

Empire uses the library through a small package-owned adapter:

- Resolve the exact registered `calendar_name`; never infer one from a Yahoo
  suffix, response time zone, country, or another listing.
- Request timezone-aware schedules containing `market_close`.
- Preserve the schedule index as the authoritative session label.
- Use the schedule's actual close, including early closes.
- Treat warnings that affect requested session labels or closes, unknown
  names, empty schedules in a range that should contain sessions, and naive or
  malformed timestamps as errors. Dependency deprecations and warnings about
  unused intraday break fields must be explicitly tested and narrowly handled,
  not globally silenced.
- Convert final eligibility instants to aware UTC `datetime` values.

No library calendar is silently replaced with Monday-through-Friday logic,
NYSE, UTC, or `America/New_York`.

## Persisted Policy Design

Y8.4 should add one reusable `stonks.ohlcv_session_policy` table and a nullable
foreign key from `stonks.provider_listing.session_policy_code`. A policy row is
shared by listings with identical session behavior; policy facts do not belong
in provider-listing JSON metadata.

The smallest persisted policy is:

| Column | Contract |
|--------|----------|
| `session_policy_code` | Uppercase stable primary key, at most 32 characters |
| `calendar_name` | Exact library calendar name, or null for observed-only behavior |
| `timezone_name` | Required IANA time-zone name |
| `eligibility_rule` | `SESSION_CLOSE` or `LOCAL_CUTOFF` |
| `cutoff_local_time` | Local wall-clock `TIME`, required only for `LOCAL_CUTOFF` |
| `availability_delay_minutes` | Non-negative integer added after close or cutoff |
| `session_date_rule` | `CALENDAR_SESSION`, `PROVIDER_LOCAL_DATE`, or `PROVIDER_DAILY_SETTLEMENT` |
| `description` | Required operator-readable explanation of the mapping |

Normal created/updated timestamps follow existing Stonks reference-table
conventions. A separate active flag is unnecessary: activation remains on
`provider_listing.status`, and policy changes occur through reviewed
migrations.

Database checks must enforce:

- `SESSION_CLOSE` requires `calendar_name`, forbids `cutoff_local_time`, and
  uses `CALENDAR_SESSION`.
- `LOCAL_CUTOFF` requires `cutoff_local_time`.
- `CALENDAR_SESSION` requires `calendar_name`.
- Delay is non-negative and bounded to at most seven days.
- Codes and text values are non-empty and trimmed.

A `LOCAL_CUTOFF` policy may have a verified calendar. With one, the calendar
defines expected session dates while the cutoff defines eligibility. Without
one, the policy is deliberately **observed-only**: it defines when polling is
due but cannot assert that a particular date is an expected session.

Every active Yahoo seed row must have a policy in Y8.4. Existing providers may
remain unassigned until their calendar mapping phase. An active listing with
no policy is a configuration error and is excluded from automated planning;
it is never assigned a default calendar.

The Empire codes in the Yahoo inventory are the stable
`provider_listing.ticker` values within the `YAHOO`/`XIDX` scope. The exact
Yahoo request symbol is retained in provider-listing metadata as
`YahooTicker`; it does not warrant a Yahoo-specific relational column or a
generic alias table. Session policies remain normalized and must not be placed
in metadata.

## Package-Owned Value Contract

Y8.5 should expose immutable typed values equivalent to:

```python
SessionPolicy(
    code: str,
    calendar_name: str | None,
    timezone_name: str,
    eligibility_rule: EligibilityRule,
    cutoff_local_time: time | None,
    availability_delay: timedelta,
    session_date_rule: SessionDateRule,
)

ExpectedSession(
    session_date: date,
    eligible_at: datetime,  # aware UTC
)
```

The value object validates the same invariants as the database and resolves
`timezone_name` with stdlib `zoneinfo.ZoneInfo`. The calendar adapter and clock
are injected into planning services so tests do not depend on host time,
network access, or Airflow.

The database stores policy and listing assignment. It does not materialize a
session calendar, missing-session rows, eligibility timestamps, retry state,
or synthetic daily bars.

## Expected Sessions And `eligible_at`

### Calendar-backed `SESSION_CLOSE`

For each schedule row:

```text
session_date = calendar schedule label
eligible_at = market_close + availability_delay
```

`market_close` is the aware close returned for that exact session. This
automatically respects the exchange time zone, daylight-saving rules,
holidays, and early closes. The result is normalized to UTC only after the
delay is applied to the aware instant.

### Calendar-backed `LOCAL_CUTOFF`

For each authoritative calendar session label:

```text
cutoff = session_date + cutoff_local_time in timezone_name
eligible_at = cutoff + availability_delay
```

Ambiguous or nonexistent local wall times caused by a daylight-saving
transition are configuration errors unless the mapping has an explicit tested
resolution. Empire does not guess a UTC offset.

This form supports provider daily-settlement behavior whose bar becomes
available later than the exchange's primary close.

### Observed-only `LOCAL_CUTOFF`

No expected-session set is generated. The cutoff creates a bounded polling
candidate, not a claim that a bar must exist:

```text
poll_at = local candidate date + cutoff_local_time + availability_delay
```

The planner may poll the current bounded provider range after `poll_at` and
re-poll it on later runs. Only provider-returned, validated dates become real
sessions. A weekday candidate is never inserted into `ohlcv_daily` and is not
reported as an authoritative missing session.

## Session-Date Rules

### `CALENDAR_SESSION`

Use the authoritative calendar schedule label as `trading_date`. The provider
timestamp must map unambiguously to that planned label under the policy time
zone and request window. A UTC date obtained by truncating a timestamp is not
accepted.

### `PROVIDER_LOCAL_DATE`

Convert the aware provider timestamp to `timezone_name` and take its local
date, or accept an explicit provider-local date when the source contract
supplies no timestamp and requires exact equality with the requested date.
This is for publisher-calculated indexes, DXY-style provider days, and
EODData's explicit exchange-local `dateStamp`. With a calendar, the derived or
explicit date must be one of the planned calendar labels. Without a calendar,
it is an observed provider date and receives no inferred holiday semantics.

### `PROVIDER_DAILY_SETTLEMENT`

Convert the Yahoo daily timestamp to the policy time zone and use the
provider's local daily label. The date must match exactly one planned product
calendar label when a calendar is assigned. Empire does not shift a futures
bar forward or backward because an overnight session began on another civil
date.

If fixtures show that a provider label does not align with the proposed
calendar, that mapping remains observed-only or inactive until an explicit,
tested rule is designed. One-day heuristics are forbidden.

## Yahoo Policy Families

Y8.4 owns the exact policy rows and all 93 assignments. It must use these
families:

| Yahoo family | Policy behavior |
|--------------|-----------------|
| Exchange-traded cash indexes | Verified local exchange calendar, `SESSION_CLOSE`, `CALENDAR_SESSION`, reviewed post-close delay |
| Publisher-calculated indexes with a verified representative calendar | That calendar, `SESSION_CLOSE`, `CALENDAR_SESSION`, conservative publisher delay |
| Publisher-calculated indexes without one authoritative calendar | Observed-only `LOCAL_CUTOFF`, `PROVIDER_LOCAL_DATE`; no authoritative gap claim |
| DXY (`DX-Y.NYB`) | `LOCAL_CUTOFF`, `PROVIDER_LOCAL_DATE`, and a conservative 120-minute delay; use an ICE calendar only after fixture alignment proves it |
| Yahoo `=F` continuous futures | `LOCAL_CUTOFF` at an initial conservative `22:00 America/New_York`, `PROVIDER_DAILY_SETTLEMENT`, then next-run reconciliation; use a product calendar only when its labels are verified |

The table's delays are explicit starting policy, not claims about a Yahoo
service-level agreement. Initial cash-index guidance remains 90 minutes for
U.S. listings, 120 minutes for European and volatility listings, 120-180
minutes for Asian listings, and 4-8 hours for publisher indexes. Y8.4 must
choose one integer per policy rather than store a range.

Generic `CME` or `ICE` calendar names must not be assigned to all futures by
venue family. Equity, energy, metals, grains, livestock, and soft commodities
can have different holiday and settlement behavior. A listing whose exact
product schedule is not supported safely starts observed-only.

## EODData Exchange Policy Families

EODData acquisition is exchange-bulk rather than listing-by-listing. The
configured exchange partition is therefore the reviewed policy lookup key;
every active EODData listing discovered under that exact `market` inherits the
partition policy. The initial configuration and complete mapping are:

| EODData exchange | Policy code | Calendar | Local time zone | Eligibility | Session-date rule |
|------------------|-------------|----------|-----------------|-------------|-------------------|
| `NYSE` | `ED_XNYS_1900_60M` | `XNYS` | `America/New_York` | `LOCAL_CUTOFF` at `19:00` plus 60 minutes | `PROVIDER_LOCAL_DATE` |
| `NASDAQ` | `ED_XNAS_1900_60M` | `NASDAQ` | `America/New_York` | `LOCAL_CUTOFF` at `19:00` plus 60 minutes | `PROVIDER_LOCAL_DATE` |
| `AMEX` | `ED_XNYS_1900_60M` | `XNYS` | `America/New_York` | `LOCAL_CUTOFF` at `19:00` plus 60 minutes | `PROVIDER_LOCAL_DATE` |

`XNYS` and `NASDAQ` are exact registered
`pandas_market_calendars` names. Both provide authoritative U.S. cash-equity
session labels, holidays, regular closes, and early closes in
`America/New_York`. The selected library has no registered `AMEX` or `XASE`
calendar. `AMEX` therefore uses the reviewed `XNYS` schedule as its explicit
fallback: NYSE American follows the same published U.S. equity holiday and
core-session early-close calendar. This fallback is limited to the EODData
`AMEX` exchange code; it is not a general market-name alias.

The provider says daily data may continue to receive corrections until 7 p.m.
market time. The local `19:00` cutoff models that publication boundary and the
60-minute availability delay preserves the existing no-earlier-than-8-p.m.
operational buffer. Using a calendar-backed `LOCAL_CUTOFF`, rather than a fixed
delay from the actual exchange close, also keeps an early-close session
ineligible until 8 p.m. Eastern. The EODData `dateStamp` is an explicit local
provider date; it must equal the requested date and one authoritative planned
calendar label before its bar can be accepted.

These policy codes are deliberately separate from Yahoo policy codes even
when they share a calendar. Availability is a provider/source fact, and a
Yahoo delay change must not alter EODData eligibility. C9.2 owns the minimal
durable policy rows and exact exchange-policy resolution mechanism.

Policy resolution fails closed. The configured EODData exchange set must
match the reviewed mapping exactly, every resolved policy must satisfy the
shared persisted-policy invariants, and every calendar must resolve with the
expected `America/New_York` schedule time zone. An unknown exchange, missing
mapping, missing policy row, unsupported calendar, unexpected calendar time
zone, or ambiguous provider date excludes that exchange from automated work
and produces a safe policy error. Empire does not substitute `XNYS`, a
weekday calendar, U.S. Eastern time, or an observed-only policy at runtime.
Adding or changing an exchange requires a reviewed contract update, calendar
verification, and an explicit C9.2-style configuration or migration.

## Completeness And Missing Sessions

For a calendar-backed listing at aware time `now`:

```text
eligible_expected = {
    session_date
    for expected session
    if eligible_at <= now
}

stored = {
    trading_date
    from ohlcv_daily
    for the provider listing
}

missing = eligible_expected - stored
```

Only eligible dates can be missing. Future or completed-but-not-yet-eligible
sessions are reported as `INELIGIBLE`, not missing. Stored dates outside the
calendar are anomalies for review; they do not alter the expected calendar.

For an observed-only listing, Empire cannot calculate `eligible_expected`.
After a due poll:

- A returned valid new date is an observed completed session.
- No new date is `UNCONFIRMED_ABSENCE`, not a missing market session.
- An unchanged latest date can be reported as stale relative to the last
  successful observation.
- Acquisition or parsing failure remains retryable.

The distinction must survive into run results and reports so coverage
percentages never mix authoritative calendar gaps with provider silence.

## No Synthetic Bars

The planner and writer must never create:

- Saturday or Sunday rows merely to make a continuous axis.
- Exchange-holiday rows.
- Repeated or forward-filled OHLC values.
- Zero-valued placeholder OHLC or volume.
- A row for a polling candidate with no provider observation.

A provider-returned weekend or off-calendar date is not silently discarded or
normalized. Calendar-backed policies quarantine it as a policy/date mismatch.
Observed-only policies retain it only after normal source validation and flag
it as an anomalous provider date. Presentation layers may render null calendar
gaps or forward-fill for display without writing those values to
`ohlcv_daily`.

## Retry And Reconciliation

Planning is stateless and idempotent:

- A missing eligible calendar session remains in later plans until a valid bar
  is stored.
- An observed-only due poll remains retryable until a later successful
  response establishes the provider state.
- Transport retry within one acquisition follows the bounded Yahoo source
  contract; exhausted work waits for the next DAG or operator run.
- There is no permanent "attempted" marker that suppresses a missing date.
- One listing's calendar or provider failure does not block valid work for
  other listings.

`EMPIRE_STONKS_OHLCV_YAHOO_RECONCILIATION_SESSIONS` controls the Yahoo
reconciliation depth. Production policy should remain in the requested 5-7
session range; the source contract currently defaults to seven and config
validation permits a wider 1-30 operator safety range.

For calendar-backed listings, reconciliation selects the latest `N` eligible
expected session labels, whether stored or missing. For observed-only
listings, it selects the latest `N` distinct provider-observed/stored dates and
requests a bounded range that can return them; it may also include the current
due polling range. Reconciliation never manufactures an expected date merely
to reach `N`.

The normal parser and current-state upsert path handles both initial ingestion
and reconciliation. A late observation fills a missing row. Corrected OHLC or
volume updates the current row and is reported. An unchanged row is a no-op.

## Safe Failure Rules

The affected listing is excluded from automated work and reported with a
stable policy error when:

- Its active row has no policy or references no existing policy.
- Its IANA time zone is unknown.
- Its calendar name is not registered by the selected library.
- The calendar time zone and persisted policy time zone are inconsistent
  without an explicit tested reason.
- A required schedule has no usable close, returns a naive timestamp, or
  raises a calendar warning/error.
- A cutoff falls in an unresolved daylight-saving ambiguity.
- A provider timestamp cannot map to exactly one allowed session date.
- A returned date conflicts with a calendar-backed policy.

Failure is per listing. Empire logs and reports the provider/listing identity,
policy code, bounded date range, and safe reason; it does not fall back to
another calendar, mutate the policy, or write an ambiguous bar.

Observed-only is an explicit reviewed policy, not an automatic fallback. An
unsupported calendar discovered at runtime is an error until a migration
deliberately assigns a verified alternative or an observed-only policy.

## Implementation And Verification Handoff

Y8.4 must implement the table, constraints, foreign key, policy seeds, and
Yahoo assignments. Its migration tests must prove every active Yahoo listing
has one valid policy, uses the Empire code as its ticker, retains one unique
non-blank `YahooTicker`, and never stores either identity in `market`.

Y8.5 must implement the typed policy, calendar adapter, UTC eligibility
calculation, and safe errors. Required tests include:

- A normal close and an early close under the same policy.
- Exchange holidays and disjoint U.S., European, and Asian holidays.
- Both sides of daylight-saving changes and UTC-date crossings.
- A publisher observed-only cutoff with no fabricated expected session.
- DXY cutoff behavior.
- A verified futures session and an ambiguous provider futures date.
- Unknown calendars, unknown time zones, and calendar warnings.

Y8.10 and Y8.11 then own database completeness queries, bounded pull plans,
retry/no-op behavior, and reconciliation results. Airflow only invokes the
package-owned runner frequently enough for the planner to find newly eligible
work.
