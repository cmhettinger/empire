# Stonks Securities Red-Team Review

Review date: 2026-06-20

Scope: `empire-stonks-securities` SEC security-master implementation and
Airflow DAG chain.

## Executive Summary

Verdict: **Mostly ready for daily-refresh hardening, not ready for
backfill.**

The implementation has solid package/DAG separation, good CIK anchoring,
conservative unknown-exchange handling, and useful validation/conflict/daily
summary artifacts. Biggest risks are around unchanged-source reruns,
ticker-based provisional security identity, and listing lifecycle/ticker-change
handling.

Validation run:

- `make db-validate` passed: Flyway validated 19 migrations against PostgreSQL
  18.4.
- `packages/empire-stonks-securities/.venv/bin/python -m pytest packages/empire-stonks-securities`
  passed: 91 passed.

## Critical Issues

1. **Unchanged SEC files can starve downstream run-scoped DAGs.**
   Observations use `ON CONFLICT (provider_code, raw_key) DO NOTHING`, and
   `raw_key` includes file checksum/object identity plus row hash. An unchanged
   file can skip inserting current-run observations. Issuer/security/listing
   selectors then scope by joining `provider_observation.object_id` to the
   current `stored_object.run_id`, so a valid unchanged daily scrape can produce
   zero current-run observations and downstream stages may do nothing or
   under-report.  **DONE**

2. **Listing identity does not handle ticker changes safely yet.**
   Listing upsert looks up active listings by `(exchange_id, ticker_norm)`, not
   by `(security_id, exchange_id)` plus symbol history. If the same security
   changes ticker on the same exchange, the code can create a second active
   listing and leave the old one active. The schema prevents duplicate active
   exchange/ticker pairs, but not duplicate active security/exchange listings.  **DONE**

## High Priority Issues

1. **Security identity is still too ticker-shaped for backfill.**
   Provisional securities are resolved by issuer plus ticker identifier. That is
   acceptable as bootstrap, but it can merge or split incorrectly
   once ticker reuse, share classes, preferreds, funds, and historical records
   arrive. **DONE**

2. **Active symbol-history safety is incomplete.**
   `listing_symbol_history` allows multiple `valid_to IS NULL` rows per listing.
   Conflict reporting warns, but the schema/code do not prevent it. Before
   backfill, add a policy for closing prior active symbols or blocking ambiguous
   changes.  **DONE**

3. **Validation status hides warnings behind legacy success semantics.**
   Validation now follows `PASS/WARN/FAIL`, matching conflict and summary
   semantics.  **DONE**

## Medium Priority Issues

1. Daily summary marks zero observations/evidence as `PASS` because
   `_positive_or_zero` treats `0` as healthy. That can mask the unchanged-file
   starvation case.  **DONE**
2. Ticker normalization is only `upper()`. That is okay for SEC ingestion, but
   OHLCV/provider mapping will need explicit normalization/display rules for
   class separators and provider-specific symbols.
3. Verify has no durable report artifact linked into daily summary; summary
   hardcodes verify stage as `UNKNOWN`.  **DONE**

## Low Priority / Nice To Have

1. Add a small source snapshot identity model or table before backfill, so
   observations can be deduped by content while runs still retain explicit
   membership.
2. Make DAG trigger conf builders less stringly typed over time. Current wrappers
   are thin and acceptable, just brittle.
3. Add tests for unchanged-source reruns and ticker-change listing behavior.

## Things That Look Good

- CIK handling is consistent and padded to 10 digits before issuer upsert.
- Unknown exchanges are skipped/logged instead of creating bad exchange rows.
- Evidence links exist at issuer/security/listing levels.
- DAGs stay thin and call reusable package functions.
- Reports are deterministic JSON artifacts with useful health telemetry.
- SEC download behavior includes User-Agent, retries, rate limiting, temp
  `.part` writes, metadata, checksum, and non-empty validation.

## Recommended Punchlist

1. Fix unchanged-source rerun semantics: either create per-run observation
   membership, include current object/run identity in `raw_key`, or let
   downstream stages resolve observations by checksum/source snapshot rather than
   only `po.object_id`.
2. Add listing lifecycle rules for ticker changes: find active listing by
   `security_id + exchange_id`, close/transition prior symbol history
   conservatively, and fail on ambiguous cases.
3. Harden provisional security identity before backfill: introduce an explicit
   provisional identity key/policy that can evolve beyond issuer+ticker.
4. Make validation status `PASS/WARN/FAIL` and make zero current-run
   observations/evidence suspicious when required sources are present.
5. Add focused tests for unchanged daily input, rerun safety, ticker change,
   duplicate active symbol history, and same security/exchange duplicate
   listings.
6. Produce durable verify report artifacts or remove the permanent `UNKNOWN`
   from daily summary.

## Backfill Readiness

**Not ready for backfill yet.** The daily shape is promising, but
backfill will amplify the current weak points: unchanged-source run membership,
issuer+ticker provisional security identity, and listing/symbol lifecycle. Fix
those first, then backfill becomes much safer.

## Backfill Readiness After Fixes

Yes, with one important nuance: once those issues are addressed, I’d consider it architecturally 
ready to begin backfill and future hydration work, not **done forever.**

The punchlist covers the big foundation risks:
- stable rerun/run-membership semantics
- safer provisional security identity
- listing and symbol lifecycle rules
- clearer PASS/WARN/FAIL health signals
- tests for the failure modes that would quietly corrupt the security master

After that, I’d feel good moving into backfill/security hydration in controlled layers: first 
backfill observations/source snapshots, then issuer/security/listing enrichment, then security 
type hydration, then provider symbol/OHLCV mapping. Each layer will still need its own validation rules, 
but the core identity chain should be sturdy enough to grow on.

The one thing I would not skip is a small “backfill readiness validation” run after the fixes: simulate 
unchanged daily input, a ticker change, duplicate ticker/share-class cases, unknown exchange rows, and 
historical observations landing beside current observations. If those pass cleanly, then yes: green light
to start the backfill phase.
