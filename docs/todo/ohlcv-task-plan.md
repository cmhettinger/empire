# OHLCV Package Action Plan

This document tracks the implementation roadmap for provider-native daily
OHLCV ingestion in Empire Stonks.

The first implementation is intentionally narrow. It downloads provider source
data, retains the raw objects briefly through Empire Core, parses provider-native
listing series and daily bars, and stores current provider-native values in the
`stonks` schema. It does not reconcile those series to canonical issuers,
securities, listings, or exchanges.

The initial providers are:

- EODData
- Stooq
- Yahoo Finance

The implementation should establish one complete provider path before expanding
the same small set of package contracts to the other providers.

## Starting A Task In A New Codex Chat

For a new implementation chat, copy the prompt below and replace `<TASK_ID>`
with the task to complete, such as `B1.1` or `E6.3`. The prompt tells Codex to
read the repository instructions and current documentation, honor completed
prerequisites and prior `Done:` notes, keep the work within the named task,
validate the implementation, and update this checklist when finished.

```text
Complete task <TASK_ID> from docs/todo/ohlcv-task-plan.md.

Before making changes, read AGENTS.md, docs/todo/ohlcv-plan.md, the full
docs/todo/ohlcv-task-plan.md, and docs/todo/ohlcv-task-plan-archive.md. Inspect
the current repository state and the Done: notes for completed prerequisite
tasks; do not assume the plan is newer than the live code.

Implement the named task completely and keep the work scoped to that task and
its necessary integration points. Follow the existing Empire architecture,
package, database, environment, Core, and Airflow conventions. Preserve
unrelated user changes and do not begin later tasks unless they are inseparable
from completing this one; if so, explain why.

Run formatting, linting, focused tests, import checks, and database or Airflow
validation appropriate to the files changed. Fix failures caused by the work.
When the task is complete, mark its checkbox [x] in
docs/todo/ohlcv-task-plan.md and add a terse dated Done: note listing the key
files changed and exact verification results. Summarize the implementation,
non-obvious decisions, and any remaining risks. If the task cannot be completed,
leave it unchecked and report the concrete blocker instead of weakening the
completion criteria.
```

## Package Boundary

`empire-stonks-ohlcv` owns:

- Provider-specific source acquisition and parsing for OHLCV inputs.
- Shared provider-listing and daily-bar dataclasses.
- Provider-native listing-series persistence.
- Provider-native daily OHLCV persistence.
- Idempotent current-state upserts.
- Empire Core run tracking and short-lived raw-object storage integration.
- Durable source-content identity through `stonks.provider_source_snapshot`.
- Daily and historical-import runners.
- OHLCV validation, freshness, coverage, and operational reports.
- Thin CLI entrypoints called by operators and Airflow.

`empire-stonks-ohlcv` does not own:

- Canonical issuer, security, listing, exchange, or symbol-history mutation.
- Provider-to-canonical listing mappings.
- Ticker-reuse detection or reconstruction of real-world identity changes.
- Cross-provider price normalization or provider-consensus values.
- Corporate-action normalization or adjustment reconstruction.
- Sector, industry, fundamentals, descriptive enrichment, or other non-OHLCV
  metadata that a provider may expose.
- An authoritative canonical OHLCV series.

The future `empire-stonks-ohlcv-bridge` package is deferred until the OHLCV
package is stable and the security master is further along. No bridge package,
mapping table, mapping status, or `listing_id` dependency is part of phases
0-11 below.

## Initial Data Contract

A `provider_listing` is a provider-scoped market/symbol series. It is not a
claim that the ticker has represented one real-world listing for all time.
Initial ingestion may identify a series by provider-native market/ticker text
or by a provider-contract stable ticker with the native request symbol retained
in metadata. If provider reuse is not detectable from the input, ingestion may
continue writing the same provider series. A future temporal bridge can map
different date ranges of that series to different canonical listings.

`ohlcv_daily` stores values as supplied by each provider. The package does not
normalize price adjustment bases or reconcile disagreements across providers.
Provider-native adjustment semantics must be documented in provider source
contracts and operational reports so consumers do not assume unlike series are
comparable. They are not stored as columns on each listing or bar.

The initial database shape is deliberately limited to:

```text
stonks.provider_listing
stonks.ohlcv_daily
```

The package reuses these existing tables rather than creating equivalents:

```text
stonks.provider
stonks.instrument_type
stonks.provider_source_snapshot
stonks.provider_source_snapshot_object
core.core_run
core.stored_object
```

Raw provider objects should normally expire after approximately seven days.
Their durable checksum/source/parser identity remains in
`stonks.provider_source_snapshot` after Core removes the physical object and its
membership link. Database OHLCV rows remain the long-lived parsed output.

The initial package stores current provider values. An idempotent rerun skips
unchanged rows and a later provider correction may update the existing daily
row. It does not add an append-only bar-revision table. Exceptional manual
database corrections remain an operator responsibility during this phase.

Airflow is orchestration only. Provider acquisition, parsing, persistence,
validation, reporting, and sequencing belong in the package.

Runtime configuration follows the existing Empire boundary. Local shells,
`bin` wrappers, Docker Compose, and Airflow load values from
`deploy/env/local.env`; reusable package code reads only `os.environ`. The
package must not load `.env` files, depend on the repository path, or copy
provider credentials into Core run parameters, object metadata, logs, reports,
or Airflow task payloads.

---

## How To Use This Checklist

Each task is intended to fit in one focused work session. A task is complete
only when the code/doc changes are made, the listed verification passes, and the
status checkbox is updated.

Default working pattern: use one Codex chat per task ID, such as `P0.1`,
`S2.1`, or `E6.1`. Start the chat by naming the task ID and asking Codex to read
this document, complete that task, run the listed verification, and update the
checkbox plus `Done:` note. Adjacent tiny tasks may be combined when they are
naturally coupled, but large tasks should be split in this document rather than
stretched across a long chat. New chats should start by reading the prior task's
`Done:` note in this plan or its archive and the current live repository state.

Status format:

- `[ ]` Not started
- `[~]` In progress
- `[x]` Complete

When completing a task, add a short `Done:` note under the task with the date,
the key files changed, and the verification command/result. Keep the notes terse
so this remains useful as a working reference.

---

## Completed Phase Archive

Fully completed phases and their `Done:` notes are moved to the
[OHLCV package action plan archive](ohlcv-task-plan-archive.md) to keep this
active checklist focused. Phases 0-7 are currently archived there;
their task IDs remain valid dependencies for active work.

## Phase 8: Yahoo Daily End-To-End Vertical Slice

Goal: seed the deliberately bounded Yahoo benchmark universe, backfill its
provider-native daily bars, and keep every eligible completed market session
current without using Yahoo for ordinary equities already covered by EODData.
Calendar-aware eligibility, retries, and reconciliation belong in the package;
Airflow only invokes that logic.

### Initial Yahoo Seed Universe

Y8.4 must seed the following 93 provider listings. `Empire code` is the stable
`provider_listing.ticker` inside the provider-scoped `XIDX` market. `Yahoo
ticker` is the exact acquisition symbol stored as metadata key `YahooTicker`;
it is not a second relational ticker column and is never stored in `market`.
The migration should preserve this reviewed starting universe while allowing a
later migration to add, correct, deactivate, or remove individual listings.

| Empire code | Yahoo ticker | Name | Instrument type |
|-------------|--------------|------|-----------------|
| SPX | ^GSPC | S&P 500 Index | EQUITY_INDEX |
| DJI | ^DJI | Dow Jones Industrial Average | EQUITY_INDEX |
| DJT | ^DJT | Dow Jones Transportation Average | EQUITY_INDEX |
| DJU | ^DJU | Dow Jones Utility Average | EQUITY_INDEX |
| NDX | ^NDX | Nasdaq-100 Index | EQUITY_INDEX |
| IXIC | ^IXIC | Nasdaq Composite Index | EQUITY_INDEX |
| NYA | ^NYA | NYSE Composite Index | EQUITY_INDEX |
| RUT | ^RUT | Russell 2000 Index | EQUITY_INDEX |
| RUA | ^RUA | Russell 3000 Index | EQUITY_INDEX |
| W5000 | ^W5000 | Wilshire 5000 Total Market Index | EQUITY_INDEX |
| OEX | ^OEX | S&P 100 Index | EQUITY_INDEX |
| SP400 | ^SP400 | S&P MidCap 400 Index | EQUITY_INDEX |
| SP600 | ^SP600 | S&P SmallCap 600 Index | EQUITY_INDEX |
| SOX | ^SOX | PHLX Semiconductor Index | EQUITY_INDEX |
| NYFANG | ^NYFANG | NYSE FANG+ Index | EQUITY_INDEX |
| VIX | ^VIX | CBOE Volatility Index | VOLATILITY_INDEX |
| VXN | ^VXN | CBOE Nasdaq-100 Volatility Index | VOLATILITY_INDEX |
| RVX | ^RVX | CBOE Russell 2000 Volatility Index | VOLATILITY_INDEX |
| VVIX | ^VVIX | CBOE VIX Volatility Index | VOLATILITY_INDEX |
| SKEW | ^SKEW | CBOE SKEW Index | VOLATILITY_INDEX |
| MOVE | ^MOVE | ICE BofA MOVE Bond Volatility Index | VOLATILITY_INDEX |
| UST5Y | ^FVX | U.S. Treasury 5-Year Yield Index | YIELD_INDEX |
| UST10Y | ^TNX | U.S. Treasury 10-Year Yield Index | YIELD_INDEX |
| UST30Y | ^TYX | U.S. Treasury 30-Year Yield Index | YIELD_INDEX |
| FTSE | ^FTSE | FTSE 100 Index | EQUITY_INDEX |
| DAX | ^GDAXI | DAX 40 Index | EQUITY_INDEX |
| CAC | ^FCHI | CAC 40 Index | EQUITY_INDEX |
| STOXX50E | ^STOXX50E | EURO STOXX 50 Index | EQUITY_INDEX |
| STOXX600 | ^STOXX | STOXX Europe 600 Index | EQUITY_INDEX |
| IBEX | ^IBEX | IBEX 35 Index | EQUITY_INDEX |
| AEX | ^AEX | AEX Netherlands Index | EQUITY_INDEX |
| SMI | ^SSMI | Swiss Market Index | EQUITY_INDEX |
| FTSEMIB | FTSEMIB.MI | FTSE MIB Index | EQUITY_INDEX |
| OMXSTO30 | ^OMX | OMX Stockholm 30 Index | EQUITY_INDEX |
| BEL20 | ^BFX | BEL 20 Index | EQUITY_INDEX |
| PSI20 | PSI20.LS | PSI 20 Index | EQUITY_INDEX |
| ISEQ | ^ISEQ | ISEQ Overall Index | EQUITY_INDEX |
| N225 | ^N225 | Nikkei 225 Index | EQUITY_INDEX |
| HSI | ^HSI | Hang Seng Index | EQUITY_INDEX |
| HSCEI | ^HSCE | Hang Seng China Enterprises Index | EQUITY_INDEX |
| KOSPI | ^KS11 | KOSPI Composite Index | EQUITY_INDEX |
| SHCOMP | 000001.SS | Shanghai Composite Index | EQUITY_INDEX |
| CSI300 | 000300.SS | CSI 300 Index | EQUITY_INDEX |
| SZCOMPONENT | 399001.SZ | Shenzhen Component Index | EQUITY_INDEX |
| TWSE | ^TWII | Taiwan Weighted Index | EQUITY_INDEX |
| STI | ^STI | Straits Times Index | EQUITY_INDEX |
| SET | ^SET | Stock Exchange of Thailand SET Index | EQUITY_INDEX |
| JCI | ^JKSE | Jakarta Composite Index | EQUITY_INDEX |
| KLCI | ^KLSE | FTSE Bursa Malaysia KLCI Index | EQUITY_INDEX |
| PSEI | PSEI.PS | Philippine Stock Exchange PSEi Index | EQUITY_INDEX |
| NIFTY50 | ^NSEI | Nifty 50 Index | EQUITY_INDEX |
| SENSEX | ^BSESN | BSE Sensex Index | EQUITY_INDEX |
| ASX200 | ^AXJO | S&P/ASX 200 Index | EQUITY_INDEX |
| TSXCOMP | ^GSPTSE | S&P/TSX Composite Index | EQUITY_INDEX |
| BOVESPA | ^BVSP | Bovespa Index | EQUITY_INDEX |
| MEXIPC | ^MXX | S&P/BMV IPC Index | EQUITY_INDEX |
| MERVAL | ^MERV | S&P MERVAL Index | EQUITY_INDEX |
| IPSA | ^IPSA | S&P IPSA Index | EQUITY_INDEX |
| JTOPI | ^JA0R.JO | FTSE/JSE Top 40 Index | EQUITY_INDEX |
| XU100 | XU100.IS | BIST 100 Index | EQUITY_INDEX |
| TA125 | ^TA125.TA | TA-125 Index | EQUITY_INDEX |
| TASI | ^TASI.SR | Tadawul All Share Index | EQUITY_INDEX |
| MSCIWORLD | ^990100-USD-STRD | MSCI World Index | EQUITY_INDEX |
| MSCIEM | ^891800-USD-STRD | MSCI Emerging Markets Index | EQUITY_INDEX |
| MSCIACWI | ^892400-USD-STRD | MSCI All Country World Index | EQUITY_INDEX |
| GSCI | ^SPGSCI | S&P GSCI Commodity Index | COMMODITY_INDEX |
| BCOM | ^BCOM | Bloomberg Commodity Index | COMMODITY_INDEX |
| DXY | DX-Y.NYB | ICE U.S. Dollar Index | CURRENCY_INDEX |
| ES | ES=F | E-mini S&P 500 Futures | CONTINUOUS_FUTURE_EQUITY |
| NQ | NQ=F | E-mini Nasdaq-100 Futures | CONTINUOUS_FUTURE_EQUITY |
| YM | YM=F | E-mini Dow Jones Industrial Average Futures | CONTINUOUS_FUTURE_EQUITY |
| RTY | RTY=F | E-mini Russell 2000 Futures | CONTINUOUS_FUTURE_EQUITY |
| WTI | CL=F | WTI Crude Oil Futures | CONTINUOUS_FUTURE_COMMODITY |
| BRENT | BZ=F | Brent Crude Oil Futures | CONTINUOUS_FUTURE_COMMODITY |
| NATGAS | NG=F | Henry Hub Natural Gas Futures | CONTINUOUS_FUTURE_COMMODITY |
| HEATOIL | HO=F | New York Harbor ULSD Heating Oil Futures | CONTINUOUS_FUTURE_COMMODITY |
| RBOB | RB=F | RBOB Gasoline Futures | CONTINUOUS_FUTURE_COMMODITY |
| GOLD | GC=F | Gold Futures | CONTINUOUS_FUTURE_COMMODITY |
| SILVER | SI=F | Silver Futures | CONTINUOUS_FUTURE_COMMODITY |
| COPPER | HG=F | Copper Futures | CONTINUOUS_FUTURE_COMMODITY |
| PLATINUM | PL=F | Platinum Futures | CONTINUOUS_FUTURE_COMMODITY |
| PALLADIUM | PA=F | Palladium Futures | CONTINUOUS_FUTURE_COMMODITY |
| CORN | ZC=F | Corn Futures | CONTINUOUS_FUTURE_COMMODITY |
| WHEAT | ZW=F | Chicago SRW Wheat Futures | CONTINUOUS_FUTURE_COMMODITY |
| SOYBEANS | ZS=F | Soybean Futures | CONTINUOUS_FUTURE_COMMODITY |
| SOYMEAL | ZM=F | Soybean Meal Futures | CONTINUOUS_FUTURE_COMMODITY |
| SOYOIL | ZL=F | Soybean Oil Futures | CONTINUOUS_FUTURE_COMMODITY |
| COFFEE | KC=F | Coffee C Futures | CONTINUOUS_FUTURE_COMMODITY |
| SUGAR | SB=F | Sugar No. 11 Futures | CONTINUOUS_FUTURE_COMMODITY |
| COCOA | CC=F | Cocoa Futures | CONTINUOUS_FUTURE_COMMODITY |
| COTTON | CT=F | Cotton No. 2 Futures | CONTINUOUS_FUTURE_COMMODITY |
| LIVECATTLE | LE=F | Live Cattle Futures | CONTINUOUS_FUTURE_COMMODITY |
| LEANHOGS | HE=F | Lean Hogs Futures | CONTINUOUS_FUTURE_COMMODITY |

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| Y8.1 | [x] | Document the Yahoo source and bounded-universe contract | Record the chosen daily OHLCV endpoint, `EMPIRE_STONKS_OHLCV_YAHOO_*` settings, request/range limits, ticker and provider-date semantics, time zones, native adjusted-close and volume behavior, rate/error behavior, and Core raw retention. Explicitly limit Yahoo to the seeded indexes, yield and volatility indexes, currency and commodity indexes, and continuous futures; exclude ordinary equities and non-OHLCV enrichment. Runtime values come from `deploy/env/local.env`. | H7.8, A5.1-A5.2 |
| Y8.2 | [x] | Design the shared market-session eligibility contract | Define the smallest reusable representation for each provider listing's calendar, local session/time zone, post-close delay, and session-date rule. Cover exchange-traded cash indexes, publisher-calculated indexes, DXY, and Yahoo `=F` provider daily-settlement series. Define `eligible_at`, missing-session detection, no synthetic weekend/holiday bars, retry behavior, and a configurable 5-7-session reconciliation window. Record why the selected market-calendar library is justified and how unsupported calendars or provider-date ambiguity fail safely. | Y8.1, M3.7 |
| Y8.3 | [x] | Add Yahoo instrument taxonomy migration | Add an idempotent Flyway migration for `YIELD_INDEX`, `EQUITY_INDEX`, `COMMODITY_INDEX`, `CURRENCY_INDEX`, `CONTINUOUS_FUTURE_COMMODITY`, and `CONTINUOUS_FUTURE_EQUITY`, using existing `INDEX` and `DERIVATIVE` classes and the reference-data upsert convention. Database validation and generated Stonks schema docs pass. | Y8.2 |
| Y8.4 | [x] | Add Stonks session-policy table and seed Yahoo provider listings | Implement the Y8.2 persistence design inside the existing `stonks` PostgreSQL schema and seed the complete reviewed Yahoo catalog into `stonks.provider_listing` under the existing `YAHOO` provider. Store the Empire code as `provider_listing.ticker`, store the exact acquisition symbol as metadata key `YahooTicker`, add no Yahoo-specific relational ticker column, and never overload `market`. Attach an instrument type and explicit session policy to every row. The migration is deterministic/idempotent, rejects missing provider/type/calendar references, contains no ordinary equities, and has assertions/tests for representative cash indexes, global indexes, yields, volatility, DXY, equity-index futures, and commodity futures. | Y8.2-Y8.3 |
| Y8.5 | [x] | Implement calendar and eligibility services | Add package-owned services that resolve expected sessions from the configured market calendar, honor local holidays and early closes, calculate `eligible_at = session_close + availability_delay`, and return only eligible missing sessions. Implement an explicit provider-daily-settlement cutoff for Yahoo continuous futures and safe handling for publisher indexes without an exchange calendar. Tests cross UTC/date boundaries, DST, holidays, early closes, disjoint country holidays, reruns, and unknown calendars. | Y8.4 |
| Y8.6 | [x] | Implement Yahoo acquisition | Acquire bounded historical ranges for selected seeded Yahoo listings with injected HTTP dependencies, timeouts, bounded retries, request pacing, and chunking where the source requires it. Store every response through Core with durable snapshot identity and secret-safe errors/metadata. Tests cover rate limiting, empty/malformed/error payloads, partial symbol failures, and request-boundary dates. | Y8.1, Y8.4-Y8.5, C4.2, A5.5 |
| Y8.7 | [ ] | Implement Yahoo parser | Parse Yahoo fixtures into shared provider-listing and daily-bar records with correct provider session dates, nullable volume where valid, deterministic duplicate handling, and documented adjusted-close treatment consistent with the shared table contract. Do not silently substitute adjusted close for native close or add Yahoo-only columns. | Y8.1, Y8.6, A5.3-A5.4 |
| Y8.8 | [ ] | Implement Yahoo import service | Compose validation, snapshot registration, seeded provider-listing resolution, daily-bar upserts, and per-listing import summaries. Do not create unseeded Yahoo listings during normal import. Unchanged reruns skip writes, later provider corrections update current rows, and one listing failure does not discard successful listings. | Y8.6-Y8.7, E6.5-E6.6 |
| Y8.9 | [ ] | Add Yahoo historical backfill runner and CLI | Add a package-owned backfill runner, operator CLI, and `bin` wrapper using `bin/env-load`. It enumerates all active seeded Yahoo listings, accepts explicit bounded date/range controls and safe resume/retry behavior, imports available history in source-safe chunks, records Core lifecycle/lineage, and emits a secret-safe machine-readable summary and report. Tests cover full enumeration, partial restart, unchanged rerun, correction, and partial failure. | Y8.8, B1.8 |
| Y8.10 | [ ] | Implement Yahoo daily completeness planning | For each active seeded Yahoo listing, determine completed expected sessions, calculate eligibility, compare them with stored `ohlcv_daily` rows, and produce a bounded pull plan containing only eligible missing sessions. A rerun before eligibility or after completion is a no-op; a failed/missing session remains retryable on a later run. Tests prove one record per real market session across U.S., European, Asian, and futures examples. | Y8.5, Y8.8-Y8.9 |
| Y8.11 | [ ] | Add recent-session reconciliation | Add a daily reconciliation pass that re-pulls the configured recent 5-7 expected sessions, compares provider OHLC, close/adjustment semantics, and volume with current rows, and applies idempotent corrections through the normal upsert path. Surface corrected-row counts and field-level differences in run results/reports without adding a bar-revision table. Tests cover late bars, changed values, null volume, provider-date corrections, and unchanged history. | Y8.7-Y8.10 |
| Y8.12 | [ ] | Build and store Yahoo reports | Reuse the shared report contract for Yahoo-scoped backfill and daily health, expected-session coverage, ineligible versus missing sessions, stale listings, retries/failures, reconciliation corrections, calendar-policy errors, and native adjustment notes. Reports distinguish initial ingestion from reconciliation and remain queryable after raw-object cleanup. | Y8.9-Y8.11, E6.7-E6.8 |
| Y8.13 | [ ] | Add Yahoo daily runner and CLI | Add package-owned sequencing and an operator CLI/`bin` wrapper that run eligibility planning, eligible missing-session ingestion, recent-session reconciliation, Core lifecycle, and reporting with configured request bounds. Tests cover no-op, success, partial failure, retry, correction, and idempotent rerun. | Y8.10-Y8.12, B1.8 |
| Y8.14 | [ ] | Add the initially manual Yahoo DAG | Add `dags/stonks/stonks_ohlcv_yahoo_daily_scrape.py` as a thin manually triggered DAG that invokes the daily runner. Keep schedule selection out of the DAG's business logic; document the intended eventual multi-run cadence (for example 06:00, 10:00, 13:00, 18:00, and 23:00 America/New_York, or hourly if live request volume permits) and leave automatic enablement to the rollout gate. DAG tests prove importability, manual schedule state, parameter forwarding, no-op success, and failure propagation. | Y8.13, B1.5-B1.7 |
| Y8.15 | [ ] | Verify the Yahoo vertical workflow | Run the complete fixture path from seeded listings through backfill, eligibility-based daily ingestion, reconciliation, stored reports, and raw-object cleanup. Verify lineage, secret safety, request bounds, calendar behavior, provider isolation, reruns, corrections, and coexistence with EODData and historical Stooq data. Verify the manual DAG is discovered in its Airflow runtime. | Y8.14, M3.7 |

Done: 2026-07-29 — selected bounded single-symbol Yahoo Chart `1d` JSON for
both seeded-universe backfill and daily/reconciliation in
`docs/stonks/ohlcv-yahoo-source-contract.md`; added validated, secret-safe
Yahoo settings in `packages/empire-stonks-ohlcv/src/empire_stonks_ohlcv/config.py`
and the OHLCV sections of `deploy/env/local{,.example}.env`; aligned the
architecture/package docs and config/secret tests. Focused tests passed (47),
the full package suite passed (397 passed, 17 skipped), and `poetry check`,
`compileall`, example-environment config smoke, environment-key parity,
88-column changed-Python scan, and `git diff --check` passed.

Done: 2026-07-29 — designed the shared provider-listing session policy in
`docs/stonks/ohlcv-market-session-contract.md`: selected
`pandas_market_calendars`, defined the normalized policy/FK handoff for Y8.4,
calendar-close and local-cutoff eligibility, three provider-date rules,
authoritative versus observed-only completeness, safe retry/reconciliation,
no-synthetic-bar invariants, and fail-closed behavior for unsupported or
ambiguous mappings. Documentation validation and `git diff --check` passed.

Done: 2026-07-29 — added idempotent migration
`V2026.07.29.0001__stonks_add_yahoo_instrument_taxonomy.sql` with the six
reviewed Yahoo index and continuous-future types under the existing `INDEX`
and `DERIVATIVE` classes. Flyway applied and validated all 33 migrations; a
direct second execution succeeded and retained exactly six active rows with
the expected classes. The transactional OHLCV schema contract passed, and
canonical Core/Stonks schema plus all Stonks ERD groups regenerated without
structural diffs. `git diff --check` passed.

Done: 2026-07-30 — added
`V2026.07.30.0001__stonks_add_ohlcv_session_policies_and_yahoo_listings.sql`
inside the existing `stonks` schema with the normalized session-policy table,
nullable provider-listing FK, policy-shape constraints, Yahoo metadata
constraint, and unique `YahooTicker` expression index. Seeded 49 reviewed
policies and all 93 active `YAHOO`/`XIDX` listings with the Empire code as
`provider_listing.ticker`, the exact request symbol in `metadata.YahooTicker`,
and an explicit instrument type and policy. Calendar-backed policy names were
resolved and year schedules exercised with `pandas_market_calendars` 5.4.0;
unsupported or provider-calculated cases use explicit observed-only policies.
Flyway applied and validated all 34 migrations, direct migration replay
succeeded, both OHLCV schema and Yahoo seed SQL contracts passed, the full
package suite passed (397 passed, 17 skipped), and canonical Stonks
schema/Mermaid/pg-diagram documentation regenerated. `git diff --check`
passed.

Done: 2026-07-30 — added immutable session-policy, calendar-schedule,
expected-session, and observed-poll values plus the package-owned
`MarketSessionService`. The narrow `pandas_market_calendars` adapter resolves
authoritative closes and fails closed for unknown calendars or unreviewed
warnings. Eligibility supports exact close delays, provider-local cutoffs,
Yahoo daily-settlement labels, eligible-missing selection, and explicit
observed-only polling without synthetic sessions. Tests cover normal and early
closes, DST, UTC-date crossings, disjoint U.S./European/Asian holidays,
idempotent reruns, futures ambiguity, unsafe calendars/time zones/warnings, and
ambiguous or nonexistent local times. The full package suite passed (420
passed, 17 skipped).

Done: 2026-07-30 — implemented bounded, serial Yahoo Chart acquisition for
caller-selected seeded listings with immutable target/request/outcome values,
exact percent-encoded request paths, guarded inclusive/exclusive Unix bounds,
and deterministic backfill chunking. Added injected transport, sleep, random,
and clock seams; conservative pacing, jitter, `Retry-After`, exponential
retry, and failure cooldown; ambiguity checks for provider-listing and
`YahooTicker` identity; and partial-failure results. Every HTTP 200 body is
stored through Core before safe Chart-envelope classification, while non-200
and transport failures expose no body or URL content. Tests cover 408/425/429
and 5xx retries, pre-Unix-epoch boundaries, chunk edges, empty/malformed/error
payloads, symbol mismatch, missing daily data, empty backfills, raw-storage
failure, and successful listings around a failed symbol. The full package
suite passed (446 passed, 17 skipped).

## Phase 9: Calendar-Aware EODData Daily Scheduling

Goal: reuse the market-session eligibility capability proven by Yahoo so the
EODData provider requests each configured exchange only after its completed
session is expected to be available. Keep EODData's exchange-bulk source
contract and package-owned business logic intact.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| C9.1 | [ ] | Define EODData exchange session policies | Map every configured EODData exchange to a supported market calendar, local session/time zone, and post-close availability delay using the shared Y8.2 contract. Document fallbacks and fail closed for an exchange without a valid policy rather than assuming U.S. Eastern time. | Y8.15 |
| C9.2 | [ ] | Persist and resolve EODData policies | Add the minimal configuration or Flyway data required by the Y8.2 design and implement policy resolution for EODData's dynamically discovered provider listings. Tests cover all configured exchanges, holidays, early closes, DST, and unknown or inactive markets. | C9.1, Y8.5 |
| C9.3 | [ ] | Add exchange-level eligibility and reconciliation planning | Before an exchange-bulk EODData request, determine whether its latest expected session is complete and eligible, whether rows are missing, and whether it falls in the configured recent-session reconciliation window. Skip ineligible/complete work while preserving bounded retry and correction behavior. Tests cover exchanges with different calendars on the same date and idempotent repeated runs. | C9.2, E6.10-E6.12 |
| C9.4 | [ ] | Integrate calendar planning into the EODData runner and reports | Run only planned exchange work, preserve Core lifecycle and partial-exchange failure handling, and report expected-session coverage, ineligible exchanges, missing rows, retries, and corrected current rows. Existing CLI behavior remains compatible and secret safe. | C9.3, E6.7-E6.10 |
| C9.5 | [ ] | Convert the EODData DAG to eligibility-driven multi-run operation | Keep the DAG thin and invoke it often enough to cover configured exchange closes; the package planner decides whether work is due. Initially retain a safe manual/disabled state until the rollout gate. DAG tests cover discovery, schedule configuration, no-op runs, and failure propagation. | C9.4, B1.5-B1.7 |
| C9.6 | [ ] | Verify calendar-aware EODData end to end | Run multi-calendar fixtures through planning, acquisition, persistence, reconciliation, and reports. Prove there are no fabricated weekend/holiday rows, completed rows are skipped, missing rows retry, corrections converge, and Yahoo/EODData policies coexist without provider leakage. | C9.5, Y8.15 |

## Phase 10: Documentation, Verification, And Incremental Rollout

Goal: verify the package without scheduled Stooq acquisition and move from
fixture workflows to normal provider operation one proven path at a time.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| V10.1 | [ ] | Complete package README | Document scope, provider-native semantics, `deploy/env/local.env` runtime loading, `os.environ` package boundary, secret handling, CLIs, raw retention, source snapshots, tables, calendar/session policies, enabled DAGs/reports, the manual Stooq backfill boundary, and deferred bridge/enrichment work. | C9.6, Y8.15, H7.8 |
| V10.2 | [ ] | Add operator runbook | Document local secret/config setup, manual runs, each enabled provider DAG, historical Stooq file acquisition/import, Yahoo backfill, eligibility and reconciliation interpretation, report interpretation, raw-object inspection, reruns, and failure recovery without printing credentials. | V10.1 |
| V10.3 | [ ] | Run formatting and full package tests | Configured formatting/linting and the full `empire-stonks-ohlcv` test suite pass from the repository root. | V10.2 |
| V10.4 | [ ] | Run DB validation and regenerate docs | Repo-standard DB validation and Stonks schema documentation generation pass with no drift. | V10.2 |
| V10.5 | [ ] | Verify package, CLI, and DAG imports | Package, all CLI modules, and all enabled provider DAGs import cleanly in their actual runtime environments. | V10.3-V10.4 |
| V10.6 | [ ] | Verify raw-object cleanup | Expire and clean a test raw object and prove stored-object/membership rows are removed while source snapshot, provider listing, bars, session policy, and report remain queryable. | V10.4-V10.5 |
| V10.7 | [ ] | Run combined fixture regression | Run EODData, operator-supplied historical Stooq, and Yahoo fixture paths through provider reports and prove reruns, calendar isolation, provider isolation, secret safety, and report scoping. | V10.3-V10.6 |
| V10.8 | [ ] | Run and enable bounded EODData | Run bounded live EODData imports across representative calendar windows, inspect eligibility, lineage, bars, reconciliation, and reports, then enable its multi-run DAG only after results are healthy. Record the cadence and decision. | V10.7, C9.6, E6.13 |
| V10.9 | [ ] | Run bounded historical Stooq import | Run the defined limited historical import and verify performance, counts, rerun behavior, cleanup, and report visibility before expanding scope. | V10.8, H7.8 |
| V10.10 | [ ] | Run Yahoo backfill and enable daily scheduling | Run the bounded live Yahoo backfill for the reviewed seed universe, inspect calendar assignments, lineage, native semantics, bars, reports, and recent-session reconciliation, then enable the Yahoo DAG at a measured multi-run cadence only after results are healthy. Record request volume, cadence, and rollback decision. | V10.9, Y8.15 |
| V10.11 | [ ] | Audit derived daily-bar consistency | Recompute expected `change` and `changepct` from each provider listing's nearest preceding stored bar and compare them with every `ohlcv_daily` row, covering first rows, zero predecessor closes, market-session gaps, corrections, and out-of-order imports. Report bounded discrepancy counts and samples by provider and market. If discrepancies exist, identify the cause and add a tested, bounded, idempotent repair command or workflow; if none exist, record the evidence and do not add a scheduled mutation task. | V10.10, H7.8 |

## Phase 11: Stooq Daily End-To-End Vertical Slice

Goal: revisit Stooq daily acquisition only after the rest of the package is
operational, and add unattended ingestion only if Stooq provides a stable,
authorized machine-download path that does not depend on browser-challenge
automation.

T11.1 is a decision gate. A documented manual-only or defer decision completes
this phase without starting T11.2-T11.10; those implementation tasks remain
deferred until the source conditions change. A go decision continues through
T11.10.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| T11.1 | [ ] | Gate Stooq daily automation | Document current Stooq API-key enrollment, terms and rate expectations, secret handling, CSV format, and browser-verification behavior. Manually enroll if appropriate, then prove whether a key-authenticated endpoint works from a clean non-browser HTTP client without cookies or challenge circumvention. Record a go, manual-only, or defer decision. | V10.11, H7.1 |
| T11.2 | [ ] | Implement Stooq daily acquisition when approved | If T11.1 approves unattended use, acquire the selected daily source through the documented interface and store it through the Core object/snapshot flow. Tests cover success, retryable failure, challenge/error content, and secret-safe diagnostics. Do not add headless-browser, CAPTCHA-solving, or challenge-bypass code. | T11.1, C4.2, A5.5 |
| T11.3 | [ ] | Implement Stooq daily parser | Parse documented Stooq daily fixtures into shared records without EODData-specific persistence branches. Shared parser-contract tests pass. Reuse historical parsing only where the evidenced formats genuinely match. | T11.1-T11.2, H7.2, A5.3-A5.4 |
| T11.4 | [ ] | Implement Stooq daily import service | Compose validation, snapshot registration, provider-listing writes, bar upserts, and import summaries. Reruns are idempotent. | T11.2-T11.3, E6.5-E6.6 |
| T11.5 | [ ] | Build and store Stooq daily report | Reuse the shared health/report contract for Stooq-scoped freshness, coverage, stale series, gap warnings, failures, and native-semantics notes. Tests prove provider scoping and stored report paths. | T11.4, H7.5 |
| T11.6 | [ ] | Add Stooq daily CLI | Add an operator CLI and `bin` wrapper using `bin/env-load`; it runs Stooq daily import plus reporting and emits a secret-safe JSON summary. | T11.5, B1.8 |
| T11.7 | [ ] | Add Stooq daily runner | Add package-owned Stooq sequencing with Core run lifecycle and reporting. Tests cover success, failure, challenge responses, and reruns. | T11.5-T11.6 |
| T11.8 | [ ] | Decide and implement Stooq DAG mode | Select scheduled, manual-only, or limited-symbol operation based on the approved interface and implemented source constraints. Add a thin scheduled DAG only when operationally justified; never add a browser-dependent DAG. Tests cover whichever go-path mode is selected. | T11.7, B1.5-B1.7 |
| T11.9 | [ ] | Verify Stooq daily vertical workflow | Verify any enabled DAG discovery and run the full Stooq daily fixture path through reporting. Confirm lineage, report rows, secret safety, rerun behavior, and isolation from EODData, Yahoo, and historical Stooq imports. | T11.8, M3.7 |
| T11.10 | [ ] | Run bounded Stooq daily and finalize docs | Run a bounded live import and enable any selected DAG only after healthy results. Update the README and runbook with the decision and exact operational boundary. | T11.9 |

---

## Future Bridge Gate

Do not start the bridge merely because provider-native OHLCV exists. Begin
bridge planning only when both the OHLCV contracts and the relevant canonical
security-master contracts are stable enough to support temporal mappings.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| X12.1 | [ ] | Confirm bridge readiness | Record the concrete consumers and stable OHLCV/security-master contracts that require provider-to-canonical mapping. | V10.11, completed T11.1 gate decision, plus future securities readiness |
| X12.2 | [ ] | Review provider-series identity evidence | Evaluate what market, ticker, date-range, identifier, and provider metadata is actually available after live ingestion. Do not assume ticker reuse can be detected automatically. | X12.1 |
| X12.3 | [ ] | Design temporal mapping storage | Design mappings that can attach different date ranges of one provider series to different canonical listings and multiple provider series to one listing. Preserve candidate/decision evidence and ambiguity. | X12.2 |
| X12.4 | [ ] | Decide bridge package creation | Create `empire-stonks-ohlcv-bridge` only when implemented mapping or canonical-series logic justifies a separate Python package. | X12.3 |
| X12.5 | [ ] | Design authoritative-series policy | Define explicit provider selection, fallback, validation, gap-fill, adjustment-compatibility, and provenance rules before storing or exposing one canonical OHLCV history. | X12.3-X12.4 |

---

## Expected End State After Phases 0-11

When phases 0-11 are complete, Empire should have a reusable
`empire-stonks-ohlcv` package with:

- Provider-neutral listing and daily-bar dataclasses.
- Provider-specific EODData and Yahoo daily acquisition/parsing modules, a
  Stooq historical-file parser, and Stooq daily acquisition only if T11.1
  approves a sustainable machine-download path.
- Provider-native daily histories stored independently in
  `stonks.ohlcv_daily`.
- Idempotent current-state imports and update counts.
- Durable provider-source content identity after short-lived raw objects expire.
- One controlled historical Stooq import path.
- Thin Airflow DAGs for the provider modes that are operationally enabled;
  Stooq daily may remain manual-only or deferred if its automation gate fails.
- JSON health reports for ingestion counts, freshness, expected-session
  coverage, eligibility, reconciliation, stale series, and failures.
- Tests proving provider isolation, rerun safety, cleanup-safe Core object and
  snapshot integration, and runtime imports.

What should be considered done and authoritative:

- Each stored row is the current value imported for one provider-native series
  and trading date.
- The provider, exact native market text, and exact native ticker are traceable
  from each row. Adjustment semantics remain in provider source contracts and
  reports; source snapshots and import runs are not linked per row.
- Reprocessing the same input does not duplicate provider listings or bars.
- Providers can disagree without overwriting one another.

What should still be considered not done:

- Proof that a provider market/ticker series represents one real-world listing
  throughout its history.
- Detection of ticker reuse, exchange transfers, or corporate successors from
  OHLCV input alone.
- Mapping provider listings to canonical `stonks.listing` rows.
- Cross-provider adjustment normalization, price consensus, or silent merging.
- A canonical or authoritative OHLCV history.
- Intraday bars, extended-hours variants, multiple stored series variants, or a
  market calendar.
- Sector, industry, fundamentals, Finviz enrichment, or other non-OHLCV data.
- Append-only provider bar revision history or a packaged manual-correction
  workflow.

This end state is sufficient to accumulate useful daily and historical
provider-native data now while preserving a clean path to temporal canonical
mapping later.
