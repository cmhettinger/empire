## Future Enhancement: Security Identity Reconciliation & Provisional Promotion

### Background

Phase 2A intentionally creates **provisional securities** from SEC current ticker observations. This is the safest approach because SEC ticker files identify a tradable instrument but do **not** reliably distinguish:

- Common stock
- Preferred stock
- ADRs
- ETF shares
- Mutual fund classes
- Bond issues
- Historical ticker reuse
- Share class reorganizations

As a result, newly created securities should be considered **bootstrap identities**, not permanent truth.

---

## Goal

Build a **Security Identity Reconciliation Engine** that promotes provisional securities into fully classified, long-lived security identities as stronger evidence becomes available.

This should be a dedicated service and should **not** be part of the daily SEC ingestion pipeline.

---

## Promotion Philosophy

Security identity should become stronger over time.

```text
SEC ticker observation
        │
        ▼
Provisional Security
        │
        ├── Additional SEC observations
        ├── SEC Series/Class datasets
        ├── Security type enrichment
        ├── External identifier mapping
        ├── Historical backfill
        └── Provider reconciliation
        ▼
Confirmed Security Identity
```

Identity lifecycle should stay deliberately small. It starts with only two
states:

```
PROVISIONAL
      ↓
CONFIRMED
```

Never silently downgrade an already confirmed security.

Descriptive enrichment is separate from identity lifecycle. Attributes such as
security type, sector, industry, fund category, asset class, fundamentals, or
analytics-ready classifications should be stored as separate evidence,
classification, or enrichment data. They should not create an `ENRICHED`
identity lifecycle state.

---

## Promotion Evidence

Examples of evidence that should increase identity confidence:

### High Confidence

- SEC Investment Company Series/Class identifiers
- Stable external identifiers (CUSIP/ISIN/FIGI, if later added)
- Bond issue identifiers
- Share class identifiers

### Medium Confidence

- Stable SEC ticker + exchange observations over time
- Consistent issuer relationship
- Multiple provider agreement

### Low Confidence

- Current SEC ticker observation only
- Provider-only ticker mapping

---

## Reconciliation Responsibilities

The reconciliation engine should be responsible for:

- promoting provisional securities
- merging duplicate provisional securities when justified
- preventing ticker reuse from corrupting identity
- upgrading security types
- maintaining lineage/history
- recording evidence and confidence changes

The daily SEC pipeline should **never** perform these operations.

---

## Future Security Types

Potential future classifications include:

- Common Stock
- Preferred Stock
- ADR
- ETF
- Mutual Fund
- Closed-End Fund
- Corporate Bond
- Treasury
- Municipal Bond
- Index
- Right
- Warrant
- Unit
- Other

---

## Design Principles

- Internal `security_id` is permanent.
- Ticker is an observed identifier, not permanent identity.
- Listing identity is `(security_id, exchange_id)`.
- Symbol history is time-varying.
- Every promotion or merge must be explainable through provider observations and evidence.
- Reconciliation decisions should be deterministic and idempotent.

---

## Future Deliverables

- Security Identity Reconciliation Service
- Promotion Rules Engine
- Merge/Split Engine
- Confidence Scoring
- Manual Review Queue (optional)
- Identity Audit Report
- Reconciliation Report JSON:
  - dry-run report name/logical name `stonks_securities_reconciliation_dry_run`
  - dry-run object kind `stonks_securities_reconciliation_dry_run_report`
  - apply report name/logical name `stonks_securities_reconciliation_apply`
  - apply object kind `stonks_securities_reconciliation_apply_report`
  - object-store keys under
    `stonks/securities/runs/YYYY/MM/DD/run-reports/reconciliation/{dry-run,apply}`
- CLI entrypoint `stonks-securities-reconcile`; dry-run is the default, and
  apply requires `--apply`
- Promotion Metrics Dashboard
