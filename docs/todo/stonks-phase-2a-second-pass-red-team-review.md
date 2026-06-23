# Executive Summary

Verdict:
- Ready for backfill: Not ready to run a historical backfill into canonical issuer/security/listing tables yet. Ready to start a separate backfill design/build phase.
- Ready for hydration: Ready with caveats for design/build of security type, fund, bond, identifier, and provider-mapping hydration. Do not let hydration promote or merge provisional securities until reconciliation rules exist.
- Top remaining risks:
  1. A date-less ticker change can update `listing.current_ticker` / `listing.ticker_norm` before symbol-history insertion refuses to create an ambiguous active symbol, leaving listing state out of sync with symbol history.
  2. SEC-created security identity is still provisional and ticker-assisted. That is correct for Phase 2A, but broad backfill or hydration needs explicit promotion, merge, split, and confidence semantics before it writes stronger identity facts.

Overall: the daily SEC Phase 2A path is materially stronger than the previous review. The major prior failures appear fixed: run reports are durable and run-scoped, unchanged source files no longer imply starvation, listing identity is no longer ticker-first, active symbol history is guarded, and validation/reporting now use PASS/WARN/FAIL. I would proceed with the next design phases, not with a large canonical backfill load.

# Critical Issues

## 1. Date-less ticker changes can desynchronize listing current state and symbol history

Evidence:
- `_upsert_listing` updates `listing.current_ticker` and `listing.ticker_norm` before `_insert_symbol_history` runs.
- `_insert_symbol_history` refuses an ambiguous ticker change when `valid_from is None` and an active symbol already exists.
- The regression test verifies that no second active symbol is created, but does not assert that `listing.current_ticker` remains aligned with the old active history row.

Why this matters:
For current SEC daily files, `seen_date` normally comes from `downloaded_at`, so the happy path has a date. Backfill and provider mapping are more likely to expose partial or date-less observations. In that case the table-level current listing state can say one ticker while `listing_symbol_history` says another.

Impact:
This can corrupt canonical listing state for ambiguous observations. It is especially risky because downstream provider mapping will likely read the denormalized current ticker.

Recommended fix:
Make ticker mutation and symbol-history insertion a single decision. If the symbol change is ambiguous, do not update `listing.current_ticker` / `ticker_norm`; emit warning evidence or conflict output instead.

# High Priority Issues

## 1. Security promotion and merge rules are not implemented yet

SEC-created securities are correctly marked as provisional/current-state bootstrap records, but the package still resolves provisional securities by issuer plus ticker evidence. This is acceptable for Phase 2A daily current listings; it is not enough for historical ticker reuse, share-class changes, funds, bonds, ADRs, or provider symbol mapping.

Before backfill/hydration mutates canonical security identity, build the reconciliation service described in `docs/todo/stonks-securities-provisional-status.md`: promotion, merge/split rules, confidence changes, and identity audit reporting.

## 2. Active listing uniqueness is validated, not enforced

`V2026.06.21.0001__stonks_listing_identity_security_exchange.sql` replaces the old unique ticker lookup with non-unique active indexes. Validation and conflict reports detect `same_security_exchange_multiple_active_listings`, but the database does not prevent duplicate active `(security_id, exchange_id)` listings.

That is reasonable during repair, but before high-volume backfill/provider mapping, add a cleanup plan and then enforce the invariant with a partial unique index once production data is clean.

## 3. Backfill source model needs a clear landing contract

The schema still has the older `source_observation` / `source_evidence` tables alongside the newer `provider_observation` / `provider_evidence` and `provider_source_snapshot` flow. The daily SEC pipeline uses the provider observation model. Historical EDGAR/index/submissions work should not start writing until it is clear whether it will extend the provider model, retire the older source model, or map one into the other.

## 4. Report objects are path-scoped but not run-context-owned

Verify, validation, conflict, and summary reports now write to deterministic run-report paths, which is good. They are stored with `run_context=None` and `object_scope="manual"` even inside Airflow. That does not break the JSON report path, but it weakens object-store lineage and may make future dashboards or cleanup less precise.

# Medium Priority Issues

## 1. README status is stale

`packages/empire-stonks-securities/README.md` still says normalization and database loading should be added in later phases, even though observations, issuers, securities, listings, validation, conflicts, verify, and daily summary are now implemented. Update it before the next handoff.

## 2. Conflict report naming still carries `phase_2a`

`CONFLICT_REPORT_NAME` is `stonks_securities_phase_2a_conflicts` while the logical name is `stonks_securities_conflicts`. The artifact works, but durable report names should describe the report, not the milestone.

## 3. Missing exchange aliases remain warning-level work

Unknown SEC exchanges are handled safely: observations are skipped for listings and surfaced as warnings rather than destructive updates. Before backfill/provider mapping, close the known alias gaps so missing exchange coverage does not create noisy unreconciled queues.

## 4. DAG smoke coverage is mostly package-level

The package has good unit coverage for helpers and report shapes. There is still limited live DAG import/smoke coverage for the full chain under Airflow, especially the Jinja conf handoff between verify, validation, conflicts, and summary.

# Low Priority / Nice To Have

- Add a short operator doc for interpreting PASS/WARN/FAIL reports and which warnings are expected on healthy zero-change days.
- Add a compact "Phase 2B entry checklist" linking this review, provisional-status notes, and report artifact examples.
- Consider adding report schema examples under docs so future dashboard work has stable sample payloads.
- Add tests that assert report object paths and object-store metadata together, not only JSON shape/path helpers.

# Regression Check: Prior Findings

- unchanged file starvation: Appears fixed. Canonical source snapshots and summary zero-delta logic distinguish unchanged sources from stage starvation.
- listing identity by ticker: Appears fixed in code. Listings are resolved by `security_id + exchange_id`; ticker/exchange duplicates are treated as conflict candidates.
- ticker-shaped security identity: Partially fixed. Code and docs now clearly label SEC-created securities as provisional, but the bootstrap resolver still uses issuer+ticker to find/create provisional security rows.
- multiple active symbol history rows: Appears fixed for normal dated ticker changes and guarded by a partial unique index when data is clean. The date-less desync issue above remains.
- validation SUCCESS vs PASS/WARN/FAIL: Fixed. Verify, validation, conflict, and summary all report PASS/WARN/FAIL-style status.
- zero observations/evidence summary issue: Appears fixed. Daily summary distinguishes unchanged sources, canonical observations available, all observations reconciled, and stage starvation.
- missing verify artifact: Fixed. Verify now writes a durable JSON report and summary links it when present.
- report path layout: Fixed. Reports use `stonks/securities/runs/YYYY/MM/DD/run-reports/{verify,validation,conflicts,summary}`.
- ticker normalization centralization: Fixed for SEC. Provider-specific Yahoo/Stooq/EODData normalization is intentionally deferred.

# Backfill Readiness Assessment

It is safe to begin a separate backfill design/build phase. It is not safe to run broad historical backfill into canonical issuer/security/listing state yet.

Minimum blockers before backfill writes canonical state:
1. Define the historical observation model and how it coexists with daily `provider_observation`.
2. Build reconciliation/promotion rules for provisional securities.
3. Fix the date-less ticker-change state/history desync.
4. Enforce active listing uniqueness after cleanup.

# Hydration Readiness Assessment

It is safe to begin hydration design and read-only enrichment experiments. It is not safe to let hydration silently promote, merge, split, or overwrite provisional securities.

Security type, fund, bond, identifier, and provider mapping phases should write additive evidence first. Promotion into canonical identity should be a separate deterministic reconciliation step with audit output.

# Recommended Next Punchlist

1. Fix listing ticker mutation so symbol-history refusal also prevents `listing.current_ticker` / `ticker_norm` changes.
2. Write the Phase 2B reconciliation design for provisional security promotion, merge/split, and confidence semantics.
3. Choose the historical backfill observation/evidence landing model before implementing EDGAR/index/submissions writers.
4. Clean existing active listing duplicates if any, then add a partial unique index for active `(security_id, exchange_id)`.
5. Update the package README to reflect the completed daily chain.
6. Rename the conflict report's internal report name away from `phase_2a`.
7. Add DAG import/conf-handoff smoke tests for the full Airflow chain.

# Verification Performed

- Reviewed package modules under `packages/empire-stonks-securities/src/empire_stonks_securities`.
- Reviewed Airflow DAGs under `dags/stonks`.
- Reviewed stonks Flyway migrations relevant to issuer/security/listing/evidence/source snapshots.
- Reviewed existing `docs/todo` notes and package README.
- Ran package tests from repo root:

```text
packages/empire-stonks-securities/.venv/bin/python -m pytest packages/empire-stonks-securities
144 passed in 0.19s
```
