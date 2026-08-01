# empire-stonks-ohlcv

Reusable provider-native daily OHLCV ingestion utilities for Empire stonks.

This package will own source acquisition and parsing, provider-native listing
series and daily-bar persistence, Empire Core run and raw-object integration,
and provider-scoped validation and reporting. Airflow and other runtimes should
call package-owned functions rather than embedding ingestion logic directly.

The package stores values as supplied by each provider. It does not normalize
values across providers, map provider series to canonical securities or
listings, or construct an authoritative OHLCV history.

## Configuration

Package configuration is read only from the process environment. Runtime
wrappers, Docker Compose, and Airflow are responsible for loading environment
files; this package does not load `.env` files or assume a repository path.

Common settings and defaults are:

```text
EMPIRE_STORAGE_KEY_STONKS_OHLCV=stonks/ohlcv
EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS=7
EMPIRE_STONKS_OHLCV_HTTP_TIMEOUT_SECONDS=30
EMPIRE_STONKS_OHLCV_MAX_RETRIES=3
```

EODData nightly acquisition uses:

```text
EMPIRE_STONKS_OHLCV_EODDATA_API_KEY=<required secret>
EMPIRE_STONKS_OHLCV_EODDATA_BASE_URL=https://api.eoddata.com
EMPIRE_STONKS_OHLCV_EODDATA_EXCHANGES=NYSE,NASDAQ,AMEX
EMPIRE_STONKS_OHLCV_EODDATA_REQUEST_DELAY_SECONDS=2
EMPIRE_STONKS_OHLCV_EODDATA_RECONCILIATION_SESSIONS=7
```

The initial source contract makes Symbol List requests for all three exchanges
before their effective-date Quote List requests. It stores six exchange-scoped
JSON objects and keeps EODData name/type/currency data best-effort on provider
listings while leaving `instrument_type_code` as `UNKNOWN`. See
[`docs/stonks/ohlcv-eoddata-source-contract.md`](../../docs/stonks/ohlcv-eoddata-source-contract.md)
for request, duplicate, reconciliation, delivery, and provider-native value
semantics.

Stooq and Yahoo do not require credentials in the current package contract.

Yahoo daily and historical Chart acquisition uses:

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

The selected source is bounded, single-symbol `1d` JSON from Yahoo's Chart
resource for the reviewed `XIDX` seed universe. The one-time historical
backfill and repeated daily/reconciliation workflow share source code
`yahoo_daily`; adjusted close remains raw/report-only and is never substituted
for the stored native close. See
[`docs/stonks/ohlcv-yahoo-source-contract.md`](../../docs/stonks/ohlcv-yahoo-source-contract.md)
for the request, response, identity, pacing, adjustment, compliance, and raw
object contract. The shared calendar-close/local-cutoff policy, provider-date
rules, observed-only fallback, eligibility, and reconciliation design is in
[`docs/stonks/ohlcv-market-session-contract.md`](../../docs/stonks/ohlcv-market-session-contract.md).

## Market-session eligibility

`MarketSessionService` consumes immutable `SessionPolicy` values loaded by its
caller from `stonks.ohlcv_session_policy`. Its default
`PandasMarketCalendarProvider` adapter resolves authoritative exchange
schedules through `pandas_market_calendars`; callers can inject another adapter
for deterministic tests.

Calendar-backed close policies derive each `ExpectedSession` from the calendar
label and exact close, including holidays, early closes, and daylight-saving
changes. Calendar-backed local-cutoff policies retain the authoritative label
but use the configured provider settlement cutoff. `eligible_sessions()` and
`eligible_missing_sessions()` accept an explicit aware clock value and return
only work whose UTC eligibility time has passed.

Observed-only publisher and DXY policies intentionally return no expected
sessions. `observed_poll_candidate()` says only when a bounded provider range
may be polled; it never claims that a weekend, holiday, or weekday bar exists.
Provider timestamps are converted under the provider response's validated IANA
time zone and the policy's explicit date rule, and must match a planned
calendar label when a calendar is assigned. The session-policy time zone owns
calendar/cutoff eligibility and need not equal the provider response time zone.
Unknown calendars, time zones, unsafe calendar warnings, ambiguous local wall
times, and mismatched provider dates fail closed with no fallback calendar or
synthetic bar.

EODData persists the reviewed `ED_XNYS_1900_60M` and
`ED_XNAS_1900_60M` policies and resolves them by exact configured exchange
through `resolve_eoddata_exchange_policies()`. The EODData listing writer binds
each newly discovered NYSE, NASDAQ, or AMEX series to that resolved policy in
the same import transaction without changing operator-owned active/inactive
status. Existing missing or mismatched assignments, unknown exchanges, and
drifted policy rows fail closed; no market inherits an Eastern or NYSE default.

`plan_eoddata_exchange_work()` resolves those policies and compares each
exchange's authoritative eligible sessions with stored bars for active EODData
listings. An eligible date with no active-listing bars is retryable until it is
filled. Complete dates are skipped unless they are among the most recent
configured reconciliation sessions, where repeat requests allow provider
corrections to converge. The recent window is resolved from each exchange
calendar against the supplied clock, so an old completed effective date is not
made recent merely by planning that date alone. Ineligible sessions and
exchanges whose discovered listings are all inactive produce no work. A
first-discovery exchange with no listings remains due so its Symbol List can be
acquired. Planning is pure and idempotent for the same database state and aware
clock value.

`run_eoddata_daily()` plans inside its Core run and acquires only the ordered
exchange partitions that have due work. An all-ineligible or inactive result is
a successful no-op that still stores the normal durable JSON/PDF reports and
completes Core lifecycle. Requested exchanges retain Symbol-before-Quote
ordering and one scoped atomic import; a later partition failure retains prior
raw evidence and fails with only its safe market/source scope. The report and
compact result include expected/eligible/missing session coverage, ineligible
and planned exchange counts, recovered HTTP retries, and current rows corrected
during recent-session reconciliation. The operator CLI remains compatible with
its explicit `--effective-date YYYY-MM-DD` input.

## Yahoo Chart acquisition

`acquire_yahoo_objects()` accepts caller-planned
`YahooAcquisitionRequest` values for active seeded listings. Each
`YahooListingTarget` carries the durable provider-listing UUID, stable Empire
ticker, and exact `metadata.YahooTicker` request symbol. Batch validation
rejects duplicate ranges, conflicting UUID identities, and a Yahoo symbol
assigned to multiple listing UUIDs.

The acquisition service percent-encodes one Yahoo symbol as one Chart path
segment and constructs explicit UTC `period1` inclusive and `period2` exclusive
bounds. Backfills are split into deterministic ascending chunks no larger than
`EMPIRE_STONKS_OHLCV_YAHOO_BACKFILL_CHUNK_DAYS`; daily plans use the tighter
`EMPIRE_STONKS_OHLCV_YAHOO_DAILY_REQUEST_MAX_DAYS`. Requests remain serial and
use the configured normal delay,
jitter, bounded retries, `Retry-After`, exponential retry delay, and
post-failure cooldown. Transport, sleep, random, and clock dependencies are
injectable.

Every HTTP 200 body is stored through Core before its Chart envelope is
classified. This preserves short-lived evidence for malformed JSON, provider
errors, symbol mismatches, and recognized no-data responses without copying
provider body text into operational results. `YahooAcquisitionResult` retains
ordered per-chunk `stored`, `missing`, or `failed` outcomes, so one listing
failure does not discard successful raw objects. Non-200 and transport
failures are represented only by bounded, secret-safe status and reason codes.

## Yahoo Chart parsing

`parse_yahoo_chart()` validates one stored Chart body against its
`YahooAcquisitionRequest`, the exact seeded `ProviderListing`, and its
`SessionPolicy`. Calendar-backed parsing requires caller-supplied planned
session labels. Observed-only parsing derives provider-local dates but accepts
them only inside the bounded acquisition range. The response symbol must match
`metadata.YahooTicker`, and the validated response time zone must agree with
the policy at every provider timestamp.

The parser checks the Chart envelope and positional array lengths before
processing observations. JSON decimals are decoded directly to `Decimal`;
native unadjusted quote OHLC becomes the shared `DailyBar`, null volume remains
`None`, and a returned zero remains zero. Optional adjusted close is retained
only as `YahooAdjustedClose` parse diagnostics and is never substituted for
native close or added to shared persistence.

Rows with invalid OHLCV, timestamps, or unplanned dates are rejected with
bounded safe issues. Equal same-date observations collapse deterministically;
conflicting OHLCV or adjusted-close observations reject that date. The
manifested repository fixture is constructed from the documented Chart format
and tests exact symbol punctuation, session-date handling, Decimal fidelity,
nullable volume, adjusted-close separation, and event-data exclusion without
making live requests.

## Yahoo import service

`import_yahoo_ranges()` composes acquired Yahoo outcomes and their matching
validated parse results into independently committed request chunks. Before
registering a snapshot or writing bars, each chunk locks and resolves the exact
seeded `provider_listing_id`. The row must remain active and agree with the
request's Empire ticker, `metadata.YahooTicker`, provider/market identity,
instrument details, and parsed session-policy code. The service never calls
the provider-listing upsert path, so an unknown UUID or changed seed identity
fails closed instead of creating or silently remapping a Yahoo series.

Every stored HTTP 200 body that belongs to a valid seeded listing receives
durable source-snapshot identity, including recognized no-data and
acquisition/parse failures. Bars are written only for matching successful
parse results through the shared current-state daily-bar writer. Reprocessing
equal values reports them as unchanged; later native provider corrections
update the current row.

One transaction is used per acquired request chunk. A seed-resolution or
persistence failure rolls back only that chunk, while prior and subsequent
chunks retain their commits. `YahooImportResult` groups the safe chunk
outcomes by durable listing UUID and reports imported, missing, failed,
snapshot, accepted/rejected-row, and aggregate bar-write counts without
provider body text or exception details.

## Yahoo historical backfill

`run_yahoo_backfill()` owns the manual historical sequence under one Core run.
It enumerates every active `YAHOO`/`XIDX` seed with its exact
`metadata.YahooTicker` and session policy, applies the explicit
`YahooBackfillScope`, acquires deterministic source-bounded Chart chunks, reads
the stored Core bodies, resolves calendar labels, parses them, and sends each
chunk through `import_yahoo_ranges()`. Raw objects, source snapshots, current
bars, Core lifecycle, and the durable JSON execution report therefore share
the same lineage without moving business logic into the CLI.

The default scope includes all active Yahoo seeds. Repeated `--ticker` options
can select a reviewed subset. `--resume-from` is inclusive in stable Empire
ticker order and, when combined with `--ticker`, must name one of those
explicit tickers. A resumed listing reacquires its bounded range chunks;
already committed equal chunks report unchanged, so retrying after a partial
run is safe without a second checkpoint table. Provider, parse, seed, or
persistence failures remain per-chunk `WARN` outcomes while successful chunks
and listings retain their commits. Systemic enumeration, acquisition,
reporting, or Core failures fail the tracked run with a secret-safe stage.

Run the operator wrapper from the repository root:

```bash
bin/stonks-ohlcv-yahoo-backfill \
  --effective-date 2026-07-30 \
  --start-date 1965-01-01 \
  --end-date-exclusive 2026-07-31
```

The start date defaults to
`EMPIRE_STONKS_OHLCV_YAHOO_BACKFILL_START_DATE`; the exclusive end defaults to
the day after `--effective-date`. The acquisition layer still enforces
`EMPIRE_STONKS_OHLCV_YAHOO_BACKFILL_CHUNK_DAYS`. Progress is emitted as
secret-safe JSON on stderr and successful stdout is one compact JSON summary
containing the Core run/report identities and aggregate outcomes. The stored
report contains bounded per-listing/chunk acquisition, parse, lineage, and
write details plus persisted in-scope date coverage. It uses the shared
schema-version-2 provider report contract.

## Yahoo daily completeness planning

`plan_yahoo_daily_completeness()` is the package-owned read/plan boundary for
the Yahoo daily runner. Its caller supplies an inclusive date window, an
aware clock value, the configured maximum Yahoo request length, and optional
exact Empire ticker filters. The planner enumerates active seeded listings,
loads only their in-window `ohlcv_daily.trading_date` values, resolves each
distinct session policy once, and returns deterministic per-listing decisions
plus tightly bounded `YahooRequestMode.DAILY` pulls.

For calendar-backed policies, pulls contain only eligible expected session
labels absent from current storage. Stored sessions split pull ranges, future
or not-yet-eligible sessions create no work, and a completed rerun is a no-op.
There is no attempted-work state: an eligible date remains in later plans
until a valid bar exists. Source request bounds are never widened merely to
combine work, and each pull retains the exact missing labels that justify its
continuous Yahoo Chart range.

Observed-only policies remain explicitly different. A due unstored date is a
`DUE_OBSERVED_POLL` candidate, not an authoritative missing session; no
expected-session or coverage claim is created. Calendar-policy failures are
isolated to their listing with a stable safe reason while valid listings keep
their plans. Acquisition, reconciliation, Core run lifecycle, and reporting
remain owned by Y8.11-Y8.13.

## Yahoo recent-session reconciliation

`plan_yahoo_recent_reconciliation()` composes the completeness plan with
`EMPIRE_STONKS_OHLCV_YAHOO_RECONCILIATION_SESSIONS`. Within the caller's
explicit bounded lookback, calendar-backed listings select the latest `N`
eligible expected labels whether each row is stored or missing. Observed-only
listings select their latest `N` stored provider dates and may add the latest
due polling candidate; those dates remain observations/candidates rather than
authoritative expected sessions. Continuous Chart requests are split whenever
the configured source request bound requires it.

Reconciliation acquisition uses the same parser and
`import_yahoo_ranges()`/`upsert_daily_bars()` path as ordinary ingestion. A
`YahooImportInput` marked `RECONCILIATION` first compares incoming OHLCV with
the exact current rows after applying the writer's database-scale rounding.
Results distinguish inserted late or newly corrected provider dates,
unchanged rows, and corrected rows. Corrected rows retain ordered old/new
differences for `open`, `high`, `low`, `close`, and `volume`, including null
volume transitions, while persistence counts remain authoritative and must
agree with those comparisons.

Native Yahoo close remains the persisted close. When the current response
contains adjusted close, reconciliation reports its value and difference from
that response's native close and records that adjusted close was not persisted.
It does not claim a historical adjusted-close correction because no prior
adjusted-close value exists after raw cleanup. Likewise, a newly returned
valid planned provider date is inserted through the normal upsert, but Empire
does not heuristically delete or re-key a different stored date based only on
provider silence or matching prices. Durable reports consuming these bounded
results do not require a revision table.

## Yahoo stored reports

`build_yahoo_backfill_report()` and `build_yahoo_daily_report()` use the shared
provider JSON report schema while keeping Yahoo's calendar semantics explicit.
Backfill reports label their phase `initial_ingestion` and include exact
post-import scoped bar coverage. Daily reports keep `daily_ingestion` and
`reconciliation` as separate phase results, including request attempts and
retries, secret-safe acquisition/import failures, parse failures, correction
counts, field-level differences, and adjusted-close diagnostics.

Daily coverage combines the planner's expected/eligible session labels with a
post-import read of current `ohlcv_daily` dates. Reports separate not-yet-
eligible sessions from eligible missing sessions and identify a listing as
stale only when its latest stored date trails its latest eligible calendar
session. Observed-only policies expose unresolved poll candidates with no
authoritative coverage percentage or missing-session claim. Per-listing
calendar-policy errors remain bounded report warnings rather than invalidating
healthy listings.

Every completed Yahoo backfill and daily run stores a deterministic JSON report
and a professional human-readable PDF companion under
`<storage_key>/yahoo/runs/YYYY/MM/DD/<run_id>/reports/` as `report.json` and
`report.pdf`. JSON uses the shared `stonks_ohlcv_provider_report` object kind;
PDF uses `stonks_ohlcv_provider_pdf_report` and the shared Empire letter-format
title page, branding, headers, footers, tables, and internal-use marking. The
PDF presents executive, scope, acquisition/persistence, coverage, health, and
native-value sections with bounded listing and issue samples. JSON remains
authoritative for the complete structured evidence.

Both report objects are durable and have no expiration; acquisition objects
retain their configured short expiry. The reports contain safe phase, health,
correction, and native-value facts directly, so they stay readable after raw-
object cleanup. Yahoo request symbols, endpoint URLs, response bodies,
credentials, and exception text are not report inputs. CLI and Airflow results
return both `report_object_id` and `pdf_report_object_id`.

## Yahoo daily runner

`run_yahoo_daily()` owns the complete reusable daily sequence under one Core
run. It plans eligible missing sessions over an explicit inclusive
`YahooDailyScope`, imports those pulls with per-listing isolation, plans the
configured recent-session reconciliation window, imports corrections through
the normal upsert path, stores the post-import health report, and completes the
Core lifecycle. Calendar-policy errors and individual acquisition, parse, or
persistence failures remain safe `WARN` results; a systemic planning,
reporting, or Core failure fails the run.

Sessions successfully acquired during missing-session ingestion are already
provider-fresh, so the same dates are omitted from reconciliation within that
Core run. A failed acquisition has no fresh object and remains eligible for the
reconciliation phase's bounded retry. Later runs still reconcile the latest
configured sessions normally. This prevents duplicate raw-object identities
and unnecessary same-run provider calls without suppressing retries.

The operator wrapper defaults its inclusive start to
`EMPIRE_STONKS_OHLCV_YAHOO_DAILY_LOOKBACK_DAYS` ending on the required
effective date. Optional exact dates and repeated Empire tickers support
bounded diagnostics:

```bash
bin/stonks-ohlcv-yahoo-daily \
  --effective-date 2026-07-31 \
  --ticker SPX
```

The wrapper loads `deploy/env/local.env` through `bin/env-load`, prints only
secret-safe JSON progress on stderr, and emits one compact result on stdout.
The package itself never loads an environment file and remains usable by the
next thin Airflow DAG.

The Stooq historical backfill accepts one operator-supplied
`d_us_txt.zip`, normally at `$EMPIRE_TEMP_DIR/d_us_txt.zip`. It copies the
archive into Core, streams only the Nasdaq, NYSE, and NYSE MKT stock partitions,
and never automates Stooq download or browser verification. See
[`docs/stonks/ohlcv-stooq-history-source-contract.md`](../../docs/stonks/ohlcv-stooq-history-source-contract.md)
for archive layout, filters, native semantics, progress, and restart rules.

`StooqHistoryParser` inspects the ZIP central directory, selects deterministic
recursive stock members using `StooqHistoryScope`, and yields one-shot
`StooqHistoryChunk` records bounded by an explicit positive bar count. It keeps
only one ticker member plus the current output chunk in memory. After complete
consumption, `parser.summary` exposes per-market input, filtered, accepted,
rejected, and duplicate counts with bounded safe issue samples. Core run
orchestration and report storage are described below.

`StooqHistoryChunkWriter` writes parser chunks in strict numeric order. Each
chunk independently resolves its distinct provider listings, skips bars for
inactive series, upserts active daily bars, and commits exactly once. A failure
rolls back only that chunk and increments the bounded cumulative failure count;
previous chunk commits remain durable and a new writer can safely replay the
same chunks. Per-chunk results and `writer.summary` keep listing and bar
inserted, updated, unchanged, and derived-only update counts separate.

`run_stooq_history_backfill()` owns the manual backfill sequence without adding
a DAG. It starts one heartbeat-enabled Core run with the exact safe scope and
chunk parameters, copies the operator-owned `d_us_txt.zip` to the normal
short-lived `raw.zip` object, preflights and streams that stored copy, registers
its checksum-based `stooq_history` source snapshot, and delegates each chunk to
the writer. Progress payloads are emitted after discovery, every 100 completed
members, and every committed chunk. Success and failure Core summaries retain
the checksum, source-snapshot identity when registered, parser position, write
counts, and last committed chunk needed for an idempotent new-run replay.

Every completed run stores a durable JSON provider report and branded PDF
companion at the shared Core `reports/report.json` and `reports/report.pdf`
paths. Both distinguish complete from partial runs, repeat the exact input
bounds and native-semantics limitations, combine parser and writer progress,
and present resulting coverage only for the selected Stooq markets and optional
tickers. The PDF uses the shared Empire report theme and keeps large ticker and
provider-series samples bounded for readability; JSON remains authoritative for
the complete structured sample. A failed chunk receives best-effort partial
FAIL reports before the Core run closes, while successful reports are PASS or
WARN according to parser rejections, collapsed duplicates, and inactive-series
skips. Core summaries and successful CLI results expose both report object IDs.

Credentials are excluded from config and credential representations. Use
`OHLCVConfig.to_safe_dict()` when placing configuration details in Core run
parameters, object metadata, reports, logs, or serialized results. Pass the
credential object itself only to provider authentication code.

## Raw object storage

`store_raw_bytes()` and `store_raw_file()` persist acquired provider payloads
through Empire Core under the active `stonks` `RunContext`. They build the
provider/effective-date/run/source key and stable raw filename, apply the
configured raw retention window, attach only allowlisted provider metadata, and
return an `AcquiredObject` containing Core's computed size and SHA-256.

The file helper moves its staged source by default, matching the existing
`empire-stonks-securities` acquisition convention; callers can request a copy
when they still own the staged file. Source-snapshot registration is a separate
persistence step and is not performed by these storage helpers.

`upsert_provider_source_snapshot()` performs that caller-transaction-owned
step. It verifies the `AcquiredObject` against the current Core raw-object row,
upserts the existing Stonks source identity by provider, source code, and Core
checksum, and idempotently links every concrete stored object carrying that
content. It reuses `stonks.provider_source_snapshot` and
`stonks.provider_source_snapshot_object`; it does not create package-specific
lineage tables or commit independently.

Core metadata purge is lineage-safe: deleting an expired raw
`core.stored_object` cascades only its
`provider_source_snapshot_object` membership and clears the snapshot's nullable
first-seen object reference. The durable source snapshot, provider listing, and
OHLCV bars remain independent and queryable.

## Core run lifecycle

`run_provider_import()` starts the approved provider job through Core, passes
the active `RunContext` to package-owned work, and completes or fails the run.
Successful Core summaries contain only provider and import counts; acquired
object details and issue text remain outside the run record. Failures store a
fixed secret-safe message and compact failure summary before re-raising the
original exception to the caller.

The wrapper accepts injected work and `RunService` collaborators for reusable
CLI, Airflow, and test use. It owns run lifecycle only.

## Acquisition-to-import boundary

`execute_import_boundary()` composes injected acquisition and parsing work with
the shared persistence helpers. Acquisition finishes first, and Core raw-object
writes remain independently committed. Parsing then completes in memory before
the boundary opens one caller connection transaction for every source-snapshot,
provider-listing, and daily-bar write. That transaction commits once on success
and rolls back in full on any persistence or commit error.

Failures raise `OHLCVWorkflowError` with only one allowlisted stage:
`acquisition`, `parsing`, or `persistence`. `run_provider_import()` records that
stage in its otherwise detail-free failure summary and re-raises the exception;
provider exception text is retained only as the Python cause and is never sent
to Core. The boundary does not delete already stored raw inputs or compensate
successful database commits. Content-identity and current-state upserts make an
identical retry safe after parsing, persistence, or later Core completion
failure.

The boundary accepts injected acquisition and parsing callables. Provider
acquisition returns stored `AcquiredObject` references; parsing returns a
`ParsedProviderOutput` containing only shared listing/bar batches and the
`ProviderSourceMetadata` source-code/parser-version pairs needed for snapshot
registration. Source metadata must exactly cover the acquired source codes,
and parsed listings must match the active provider. Provider adapters may use
functions or bound methods and do not share a downloader base class, registry,
remote request model, or arbitrary metadata contract.

The EODData, Stooq historical, and Yahoo Chart endpoints or inputs are selected
in their source contracts. Provider implementations retain injected
acquisition/parser seams and the shared persistence boundary.

Production source metadata is exposed as immutable constants:

| Provider workflow | Source code | Parser version |
|-------------------|-------------|----------------|
| EODData symbol discovery | `eoddata_symbol_list` | `1.0.0` |
| EODData nightly daily | `eoddata_daily` | `1.0.0` |
| Stooq nightly daily | `stooq_daily` | `1.0.0` |
| Stooq historical files | `stooq_history` | `1.0.0` |
| Yahoo controlled-symbol daily and historical Chart | `yahoo_daily` | `1.0.0` |

Source codes identify logical feeds, not endpoints, dates, symbols, or file
partitions. Parser versions use source-specific `MAJOR.MINOR.PATCH` values and
change when parsing or interpretation can change shared output. Stooq daily and
historical records discover their own series. Yahoo has no broad symbol
discovery; its seeded historical and daily modes share the same Chart source
identity and format.

## Provider fixtures

Parser fixtures follow [the package fixture policy](tests/fixtures/README.md).
Each small raw payload is paired with a manifest that records its documented
format reference, production source/parser identity, provenance, sanitization,
size, checksum, and intended cases. Policy tests reject unmanifested,
oversized, drifted, unsafe, or unknown-source payloads.

Provider payloads are added only after repository evidence or a source-contract
task documents the real format. Tests never acquire live fixture data.

Provider parser tests reuse `tests/parser_contract.py`. They adapt their parser
to a bytes-in callable and provide exact valid and invalid cases, declaring
whether a bar source permits absent volume or is listing-only. The assertions
verify provider and native identity, optional/required volume behavior,
`date`/`Decimal` types, deterministic ordered output, and deterministic
`OHLCVParseError` rejection. This test seam does not impose one production
parser signature.

## Provider runner seam

`run_provider_pipeline()` accepts an existing `RunService`, caller-owned
database connection, and injected A5.1 acquisition/parser callables. It composes
the Core lifecycle with `execute_import_boundary()` and returns the same compact
`OHLCVRunResult`. Invalid collaborators are rejected before a Core run starts;
workflow failures retain the secret-safe acquisition/parsing/persistence stage.

The package seam performs no network access by itself and does not load an
environment file, create a provider registry, or depend on Airflow. Future
provider runners bind their concrete collaborators; CLI and Airflow callers
only establish runtime scope and call the package.

## CLI

Local commands use `bin/env-load` to load `deploy/env/local.env` before calling
package-owned command modules. The initial configuration check prints only the
secret-safe configuration summary:

```bash
bin/stonks-ohlcv-config
bin/stonks-ohlcv-config --env-file deploy/env/local.example.env
```

The same command is exposed as the package script `stonks-ohlcv-config` for
installed runtimes; environment loading remains the caller's responsibility.

Run the EODData daily workflow with an explicit provider date:

```bash
bin/stonks-ohlcv-eoddata-daily --effective-date 2026-07-15
bin/stonks-ohlcv-eoddata-daily \
  --effective-date 2026-07-15 \
  --env-file deploy/env/local.example.env
```

The wrapper sources `bin/env-load`, defaults to `deploy/env/local.env`, and
suppresses environment-loader status output so successful stdout is exactly one
compact JSON object. The installed `stonks-ohlcv-eoddata-daily` package command
expects its runtime environment to be loaded already. Invalid dates are rejected
before opening a database connection; runtime failures print only a fixed safe
message and return nonzero.

Run the one-shot Stooq historical backfill against an operator-supplied archive:

```bash
bin/stonks-ohlcv-stooq-backfill \
  --input-path "$EMPIRE_TEMP_DIR/d_us_txt.zip" \
  --effective-date 2026-07-18 \
  --start-date 2024-01-01 \
  --market nasdaq \
  --ticker AACB.US \
  --chunk-size 50000
```

`--market` and `--ticker` are repeatable exact filters; omitting them selects all
three supported markets and all their tickers. The optional inclusive start/end
dates are trading-date filters. Chunk size defaults to 50,000 bars and is capped
at 100,000 bars per transaction. The wrapper validates the local
`d_us_txt.zip`, sources `bin/env-load`, and invokes the package command; it does
not download from Stooq or add a DAG. Progress is emitted as JSON lines on
stderr, while successful stdout contains only the compact final JSON result.
That result includes the stored JSON and PDF report object IDs. Runtime failures
return nonzero with a fixed safe message.

## EODData acquisition

`acquire_eoddata_objects()` performs the package-owned EODData acquisition
stage. It requests NYSE, NASDAQ, and AMEX Symbol List payloads first, followed
by the three effective-date Quote List payloads, and stores every validated
JSON array immediately through Core. The returned tuple contains six
`AcquiredObject` references in that deterministic order.

The function accepts an injected `EODDataHTTPTransport` and sleep callable for
tests. Its default transport uses the Python standard library, keeps the API
key separate from the base URL until the request is sent, applies the common
timeout, spaces consecutive requests by the configured EODData delay, and
retries transport failures, HTTP 429, and HTTP 5xx responses up to the
configured bound. Safe numeric `Retry-After` values are honored with a
60-second cap; otherwise bounded exponential backoff starts at two seconds.

HTTP failures, malformed/non-array JSON, non-JSON media types, and empty Symbol
List payloads stop acquisition with a source/exchange-specific but secret-safe
error. Empty Quote List arrays remain valid. Successful objects from earlier
partitions remain durable when a later request fails, while response bodies,
query-bearing URLs, and transport exception details are excluded from surfaced
errors and Core metadata.

## EODData Symbol List parsing

`parse_eoddata_symbol_list()` parses one trusted NYSE, NASDAQ, or AMEX Symbol
List payload. It preserves the exact provider code as the ticker, always emits
the shared `UNKNOWN` instrument type, retains usable `name`, `type`, and
`currency` values, and ignores all quote-like fields in this discovery feed.

Compatible duplicate codes collapse without choosing an input row. Conflicting
descriptive values reject the whole exchange/code identity, and the provider-
specific result returns deterministic duplicate counts plus a bounded safe
issue sample. `to_parsed_provider_output()` adapts accepted listings to the
shared listing-batch boundary with no bars; Quote List reconciliation owns bars
in the next stage.

## EODData Quote List parsing

`parse_eoddata_quote_list()` requires one trusted exchange partition, an
explicit effective date, and that exchange's accepted Symbol List result. It
hard-fails exchange, daily-interval, and date scope mismatches, parses JSON
numbers directly to `Decimal`, and reconciles quotes only to exact accepted
same-exchange ticker identities.

Compatible quote duplicates collapse to one bar. Conflicting duplicates,
invalid OHLCV groups, and quotes without an accepted listing are rejected with
deterministic counts and bounded safe issue samples. The reconciled shared
output retains every accepted Symbol List listing and its metadata, including
listings without a quote, and attaches at most one daily bar to each batch.

## Validation and report contract

The shared validation boundary is documented in
[`docs/stonks/ohlcv-validation-report-contract.md`](../../docs/stonks/ohlcv-validation-report-contract.md).
`ProviderValidationResult` carries accepted shared batches alongside one
`FeedOutcomeCounts` per source and market, typed `RowRejectionSummary` buckets,
and separate bounded hard-failure and warning summaries.
`SourceMarketWriteCounts` preserves listing and bar write
outcomes at their distinct source/market grains for later import reports.

Issue totals remain complete while safe samples are capped at 100. The report
contract also defines active/inactive coverage, calendar and weekday freshness,
stale candidates, and weekday-shaped gap warnings as non-calendar-authoritative
operational heuristics.

## EODData atomic import

`import_eoddata_daily()` accepts the six acquired Core object references and
one `ProviderValidationResult` for each of NYSE, NASDAQ, and AMEX. It validates
the complete run shape before opening a transaction, then registers all six
source snapshots, upserts every accepted Symbol List listing, resolves active
listing IDs, and writes accepted Quote List bars in one commit boundary.

Work is ordered by production source and configured market order. Inactive
listings are still resolved and may receive metadata updates, but their bars are
excluded from the daily-bar writer and reported through `skipped_inactive`.
`EODDataImportResult` retains source/market feed and write counts, exact
market/source/reason rejection buckets, aggregate listing/bar persistence
counts, bounded validation issues, and snapshot lineage without returning full
bar payloads.

## Provider health queries

The public health helpers are provider-parameterized and return deterministic
inputs for the stored report builder:

- `select_provider_market_health()` separates active and inactive listing and
  bar coverage by market, including active first/last stored dates.
- `select_provider_series_health()` returns ordered coverage and freshness
  inputs for every active and inactive provider-native series.
- `select_provider_weekday_gaps()` counts active-series weekday-shaped gaps and
  returns at most 100 deterministic samples. These are operational candidates,
  not exchange-calendar-authoritative missing sessions.

All three helpers accept an optional inclusive `as_of_date`. EODData reports
pass their run effective date so a backdated run excludes bars that were
already imported for later dates while retaining listings with zero in-scope
bars.

The queries are read-only and do not calculate report presentation or accept an
EODData-specific exchange branch. PostgreSQL integration coverage exercises the
same provider-scoped API for EODData across NYSE, NASDAQ, and AMEX using 4,500
listings and 139,200 daily bars. Existing provider-listing and daily-bar primary
and identity indexes provide the required access paths, so E6.7 adds no schema
index.

## EODData stored report

`build_eoddata_report()` combines one `EODDataImportResult` with provider-
scoped database health queries. Its schema-version-2 JSON keeps acquisition,
feed, duplicate, cross-feed reconciliation, listing-write, and bar-write
outcomes at their source/market grains. It adds active coverage and freshness,
bounded stale/no-data and weekday-gap candidates, a separate inactive-series
summary, bounded warnings, market-specific hard failures, market/source/reason
row rejections, and the required provider-native value semantics. Safe row
rejections produce `WARN`; only partition/run-integrity failures produce
`FAIL`.

`store_eoddata_report()` writes deterministic JSON as a durable Core run object
under `<storage_key>/eoddata/runs/YYYY/MM/DD/<run_id>/reports/report.json`.
The object has no expiration and its metadata contains only schema version,
provider, effective/generated dates, and outcome. Runtime credentials are not
accepted by the report builder and are never serialized from `OHLCVConfig`.

The same completed run stores two distinct PDFs. `report.pdf` is the
human-readable run-status companion to `report.json`.
`daily-market-report.pdf` analyzes all persisted EODData bars for the effective
date whose retained provider symbol type is `Equity`. It reports exchange
breadth, close-to-close return distribution, leading advancers and decliners,
volume leaders, and supported price/volume anomalies. Market highlights and
exchange movers use reusable Empire red/green/neutral quote tiles. Ranked
equity sections normally occupy one page each with up to 12 tiles in a 4-by-3
grid followed by the matching detail table. This pattern covers session
leaders and laggards, per-exchange advancers and decliners, volume leaders,
high-volume low-movement names, and smaller configured cohorts when they fit.
Additional
tile and detail pages cover the Magnificent Seven plus versioned Dow 30 and
Nasdaq-100 configured baskets. These basket ticker sets are report-owned
analytical cohorts, not authoritative or historically effective-dated index
membership; every section reports available coverage and missing names.
Up to 12 high-volume, low-movement equities per exchange receive dedicated
tile and OHLCV detail pages when rows qualify. They require an absolute
calculated close-to-close return no greater than 0.50% and rank by reported
share volume, then smallest absolute return.
The market report uses
the shared Empire title page, disclaimer, colors, logos, Cinzel cover type, and
Source Sans 3 document type. It intentionally omits index-level benchmarks,
sector, industry, commodity, and technical-indicator sections until those
capabilities exist in the current schema.

## EODData daily runner

`run_eoddata_daily()` owns the provider's nightly package sequence under one
Core run: acquire the three Symbol List objects followed by three Quote List
objects, read and parse/reconcile them in NYSE/NASDAQ/AMEX order, execute the
atomic import, build and store the run-status and daily-market reports, and
complete the Core run.
Callers provide the connection, Core services, explicit effective date, and
runtime identity; the package neither loads environment files nor depends on
Airflow.

The returned `EODDataDailyRunResult` contains only the run and three report
object IDs, status,
effective date, aggregate write/issue and rejected-row counts, inactive skip
count, and report outcome. Core params and summaries use
`OHLCVConfig.to_safe_dict()` and never
contain credentials, source payloads, issue text, or full report contents.
Acquisition and parsing failures also record the safe market and source code
when the failed partition is known; all runtime failures record a safe stage
while the original exception is re-raised. Previously stored raw
objects and successfully committed import data are not deleted on later-stage
failure, making a new Core run for the same effective date safe to retry.

## EODData manual DAG

Airflow DAG `stonks_ohlcv_eoddata_daily_scrape` is manual-only
(`schedule=None`). It disables catchup and permits one active run so EODData
acquisitions cannot overlap. The task reads runtime settings from the
Compose-provided process environment and delegates the complete workflow to
`run_eoddata_daily()`. The package planner selects due exchanges; an
ineligible or already-complete date completes as a normal no-op run with
durable reports.

For a manual run or rerun, pass an explicit provider date with DAG run
configuration such as `{"effective_date": "2026-07-15"}`. If omitted, the DAG
uses the New York date at `data_interval_end`. The task returns only the
runner's compact secret-safe summary; detailed diagnostics remain in the stored
report.

After C9.6 and V10.8 approve live operation, the production deployment should
use `15 20-23 * * 1-5` in `America/New_York`: 20:15, 21:15, 22:15, and 23:15
ET each weekday. The first run follows the reviewed 20:00 eligibility cutoff;
the later runs provide same-date retry opportunities. Holidays and completed
exchanges remain package-planner no-ops. Local/development scheduling stays
disabled.

## Development

Install the package environment and run its tests from this directory:

```bash
poetry install
poetry run pytest
```

## Status

Shared models, provider-native persistence/query helpers, Core raw-object
storage, source-snapshot registration, run lifecycle, the transactional import
boundary, EODData six-request acquisition, and EODData Symbol List parsing are
implemented along with EODData Quote List parsing/reconciliation, atomic import,
shared provider health queries, the stored EODData report, and the manual
eligibility-driven EODData Airflow entrypoint. Later provider parsers are added
in later tasks.
