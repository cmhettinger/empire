# Technical-Indicator Correctness And Isolation Audit (V12.5)

Date: 2026-08-29

Decision: pass. The V1 calculation, persistence, publication, isolation, and
recovery contracts passed the bounded development audit. This evidence does not
authorize production cadence or a broad source or technical-indicator backfill.

## Runtime

- macOS arm64 development host, Python 3.14.6.
- `empire-stonks-tech-indicators` 0.1.0, TA-Lib 0.7.1, NumPy 2.4.6.
- PostgreSQL 18.4 in the local Empire Compose environment.
- Calculation version `TECH_INDICATORS_V1`.

## Audit Matrix

| Contract | Evidence | Result |
|---|---|---|
| Independent calculations | Committed OHLCV golden fixture, three seeded generated histories, scalar reference formulas, flat-series edge cases, and pinned TA-Lib outputs | Pass |
| Gaps and short history | Non-calendar-spaced histories, exact observation warm-up, 1/3/10/15/19-observation histories, missing volume, and exact-date SPX gaps | Pass |
| Incremental equivalence | Full rebuild, append, interrupted resume, source correction, SPX insert/change/delete, no-op rerun, and calculation-version rebuild | Pass |
| Stored versus fresh | Rollback-only generated PostgreSQL audit across EODData, Stooq, Yahoo index, and Yahoo benchmark shapes | Pass |
| Provider and version isolation | Provider-scoped persistence, A/B membership, correction locality, version rebuild, and mixed-version rejection | Pass |
| Publication visibility | Staged and in-place publication plus concurrent readers that observe either the complete old image or complete new image | Pass |
| Benchmark completeness | Exact SPX identity/date alignment and rejection of incomplete, partial, cancelled, deleted, or mismatched benchmark evidence | Pass |
| Global writer lock | Contention before state creation, contention after terminal state, transaction ownership, and connection-loss release | Pass |
| Failure recovery | Injected calculation/persistence/report failures, retry convergence, partial-resume cleanup, and Core lifecycle evidence | Pass |

## Stored-Feature Audit

`test_correctness_audit_integration.py` creates four deterministic provider
histories inside a transaction that is always rolled back:

- 280 gapped EODData observations;
- 280 gapped Stooq observations;
- 10 gapped Yahoo index observations with nullable volume; and
- 280 gapped Yahoo benchmark observations with nullable volume.

The test persists 850 rows to an inactive payload slot and reads them back from
PostgreSQL. For every row it compares the provider/date key, source copy,
benchmark lineage, history count, calculation version, all 53 Python-calculated
features, and all 23 PostgreSQL-generated features with a freshly assembled
row. The 23 generated expectations are calculated independently in the test.
The focused golden suites separately compare the 53 Python features with
independent scalar formulas and pinned TA-Lib 0.7.1.

The audit then changes one middle Stooq source observation, recalculates and
upserts that listing, verifies both changed and unchanged rows, compares the
complete stored image again, and proves the EODData, Yahoo subject, and Yahoo
benchmark rows are byte-for-byte unchanged. Exact-date SPX alignment includes
both populated post-warm-up values and deliberate date gaps; the short Yahoo
subject remains warm-up null and has no benchmark lineage.

## Existing Development Data

A repeatable-read, read-only, aggregate-only query inspected the existing local
database. It returned no OHLCV or feature values and performed no mutation.
The active source inventory was bounded to seven provider/market aggregates:

| Provider | Markets | Active listings | Source rows | Date extent |
|---|---:|---:|---:|---|
| EODDATA | 3 | 13,247 | 100,115 | 2026-07-14 to 2026-08-03 |
| STOOQ | 3 | 9,562 | 20,475,736 | 1962-01-02 to 2026-07-17 |
| YAHOO | 1 | 83 | 106,001 | 1965-01-04 to 2026-08-03 |

The active published technical view contained zero rows and therefore offered
no existing feature values to compare. The rollback-only generated audit above
provided the stored-versus-fresh PostgreSQL evidence without running a broad
technical backfill. No source backfill, technical backfill, live cadence,
publication, remediation, or durable test write was performed.

## Exact Verification

From the repository root with the local PostgreSQL environment running:

```bash
poetry --directory packages/empire-stonks-tech-indicators run pytest \
  tests/test_core_golden.py tests/test_talib_adapter.py \
  tests/test_talib_golden.py tests/test_spx_golden.py \
  tests/test_spx_corrections.py tests/test_rebuild_equivalence.py \
  tests/test_affected_ranges.py tests/test_assembly.py \
  tests/test_validation.py tests/test_failure_safety.py -q
```

Result: 107 passed.

```bash
source bin/env-load >/dev/null
poetry --directory packages/empire-stonks-tech-indicators run pytest \
  tests/test_correctness_audit_integration.py \
  tests/test_persistence_integration.py \
  tests/test_publication_integration.py \
  tests/test_writer_lock_integration.py \
  tests/test_runner_vertical_integration.py \
  tests/test_daily_runner_integration.py \
  tests/test_daily_noop_integration.py \
  tests/test_backfill_runner_integration.py \
  tests/test_queries_integration.py \
  tests/test_core_lifecycle_integration.py \
  tests/test_daily_publication_integration.py -q
```

Result: 27 passed.

The package-wide regression result and repository hygiene checks are recorded
in the V12.5 Done note in `docs/todo/tech-ind-task-plan.md`.

