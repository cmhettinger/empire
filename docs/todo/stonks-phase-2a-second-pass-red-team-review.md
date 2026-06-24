# Executive Summary

Verdict:
- Ready for backfill: Not ready to run a historical backfill into canonical issuer/security/listing tables yet. Ready to start a separate backfill design/build phase.
- Ready for hydration: Ready with caveats for design/build of security type, fund, bond, identifier, and provider-mapping hydration. Do not let hydration promote or merge provisional securities until reconciliation rules exist.
- Top remaining risks:
  1. SEC-created security identity is still provisional and ticker-assisted. That is correct for Phase 2A, but broad backfill or hydration needs explicit promotion, merge, split, and confidence semantics before it writes stronger identity facts.

Overall: the daily SEC Phase 2A path is materially stronger than the previous review. The major prior failures appear fixed: run reports are durable and run-scoped, unchanged source files no longer imply starvation, listing identity is no longer ticker-first, active symbol history is guarded, and validation/reporting now use PASS/WARN/FAIL. I would proceed with the next design phases, not with a large canonical backfill load.

# Critical Issues

None open.

# High Priority Issues

## 1. Security promotion and merge rules are not implemented yet

SEC-created securities are correctly marked as provisional/current-state bootstrap records, but the package still resolves provisional securities by issuer plus ticker evidence. This is acceptable for Phase 2A daily current listings; it is not enough for historical ticker reuse, share-class changes, funds, bonds, ADRs, or provider symbol mapping.

Before backfill/hydration mutates canonical security identity, build the reconciliation service described in `docs/todo/stonks-securities-provisional-status.md`: promotion, merge/split rules, confidence changes, and identity audit reporting.

# Medium Priority Issues

## 1. Missing exchange aliases remain warning-level work

Unknown SEC exchanges are handled safely: observations are skipped for listings and surfaced as warnings rather than destructive updates. Before backfill/provider mapping, close the known alias gaps so missing exchange coverage does not create noisy unreconciled queues.

## 2. DAG smoke coverage is mostly package-level

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
- multiple active symbol history rows: Fixed for normal dated ticker changes and guarded by a partial unique index when data is clean. Date-less ticker changes are blocked when they would desynchronize listing current state and active symbol history.
- multiple active listings for one security/exchange: Fixed by `V2026.06.23.0003__stonks_listing_active_security_exchange_guard.sql`, which enforces one active listing per `(security_id, exchange_id)` while allowing historical/closed rows.
- source/provider observation table split: OBE. The early `source_observation` / `source_evidence` tables are renamed by `V2026.06.06.0002__stonks_security_master_naming_cleanup.sql`; the current schema uses `provider_observation`, `provider_evidence`, and `provider_source_snapshot`.
- report object lineage: Fixed for new DAG-generated reports. Verify, validation, conflict, and daily summary reports still use deterministic run-report paths, but Airflow writers now store them with the source scrape run context and `object_scope = 'run'`.
- conflict report name: Fixed. The durable conflict report name is now `stonks_securities_conflicts`; existing historical report artifacts keep their old JSON content.
- README status: Fixed. The package README now describes the implemented daily DAG chain, current report artifacts, run-scoped report storage, and the remaining provisional-security caveat.
- validation SUCCESS vs PASS/WARN/FAIL: Fixed. Verify, validation, conflict, and summary all report PASS/WARN/FAIL-style status.
- zero observations/evidence summary issue: Appears fixed. Daily summary distinguishes unchanged sources, canonical observations available, all observations reconciled, and stage starvation.
- missing verify artifact: Fixed. Verify now writes a durable JSON report and summary links it when present.
- report path layout: Fixed. Reports use `stonks/securities/runs/YYYY/MM/DD/run-reports/{verify,validation,conflicts,summary}`.
- ticker normalization centralization: Fixed for SEC. Provider-specific Yahoo/Stooq/EODData normalization is intentionally deferred.

# Backfill Readiness Assessment

It is safe to begin a separate backfill design/build phase. It is not safe to run broad historical backfill into canonical issuer/security/listing state yet.

Minimum blockers before backfill writes canonical state:
1. Build reconciliation/promotion rules for provisional securities.

# Hydration Readiness Assessment

It is safe to begin hydration design and read-only enrichment experiments. It is not safe to let hydration silently promote, merge, split, or overwrite provisional securities.

Security type, fund, bond, identifier, and provider mapping phases should write additive evidence first. Promotion into canonical identity should be a separate deterministic reconciliation step with audit output.

# Recommended Next Punchlist

1. Write the Phase 2B reconciliation design for provisional security promotion, merge/split, and confidence semantics.
2. Add DAG import/conf-handoff smoke tests for the full Airflow chain.

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
