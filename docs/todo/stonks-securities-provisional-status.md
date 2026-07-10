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

## First Reconciliation Evidence Types

This is the initial contract for derived reconciliation evidence. It defines
what the collector must be able to describe, but does not select a storage
table or make promotion decisions. The collector must retain links to the
supporting `provider_observation`, `provider_evidence`, and, where applicable,
`provider_source_snapshot` rows. A derived summary never replaces that source
trail.

Evidence is evaluated per provisional `security_id`. Missing evidence is not a
conflict. A conflict exists only when the collected observations identify an
incompatible issuer, security, listing, ticker, exchange, or SEC class/series
value. Later confidence rules decide how many supporting observations are
needed for promotion; this contract deliberately does not assign scores.

### `SEC_ISSUER_SECURITY_MATCH`

Records that a SEC ticker observation identifies the same issuer and
provisional security already linked by `provider_evidence`.

- Requires a normalized SEC CIK, a non-null `issuer_id`, a non-null
  `security_id`, and the supporting `provider_observation_id` /
  `provider_evidence_id`.
- Carries the observed ticker and the issuer CIK used for the match so an
  evaluator can distinguish a repeat confirmation from an issuer mismatch.
- Supports the issuer-to-security relationship only. It does not establish the
  security's instrument type or prove that the ticker is permanent.
- An observation linked to a different issuer or security for the same
  candidate is recorded as conflicting evidence, not folded into this match.

### `SEC_TICKER_EXCHANGE_STABILITY`

Summarizes repeated SEC ticker/exchange observations for one security and
listing. It is emitted only when both the normalized ticker and resolved
exchange/listing are present.

- Groups observations by `security_id`, `listing_id`, normalized ticker, and
  resolved exchange identity.
- Records the distinct supporting observations and source snapshots, plus
  first- and last-observed timestamps. Repeated delivery of the same snapshot
  may be reported as context but does not increase the distinct-snapshot count.
- A collector may emit a one-observation summary for visibility, but must label
  it as insufficiently repeated; only two or more distinct source snapshots
  qualify as stable evidence.
- A ticker/exchange observation attached to another security or listing is
  conflicting evidence. Ticker continuity alone must not cause two securities
  or issuers to be merged.

### `SEC_SOURCE_SNAPSHOT_CONTINUITY`

Records that a specific SEC observation-to-entity mapping persists across
distinct semantic source snapshots. `provider_source_snapshot` is the
continuity unit because it identifies source content by provider, source, and
content hash; run IDs and stored objects are execution/artifact context only.

- Groups a candidate mapping by its SEC provider/source, entity identifiers,
  and normalized observed values, then orders distinct snapshots by their
  observation or snapshot timestamps.
- Records snapshot IDs, source code, content hashes, first/last seen times,
  and the number of distinct snapshots. It also retains current-run stored
  object membership when available for reporting and traceability.
- Multiple stored objects linked to one snapshot prove repeat delivery of the
  same content, not independent confirmation. A missing retained object does
  not invalidate the canonical snapshot or its parsed observation.
- A changed mapping is context or conflict according to the observed values;
  it must never be silently treated as continuity.

### `SEC_SERIES_CLASS_IDENTIFIER` (placeholder)

Reserves a high-confidence evidence type for SEC Investment Company
series/class data. No evidence of this type is emitted until the SEC source,
parser, and identifier mapping are implemented and validated.

- The eventual record must retain the SEC dataset/source, source snapshot,
  series identifier, class/contract identifier, issuer/security targets, and
  the supporting raw observation/evidence links.
- It may support instrument classification or a promotion candidate once later
  confidence rules explicitly allow it; the placeholder itself grants no
  confidence and causes no lifecycle mutation.
- Missing series/class data remains a missing evidence class, not evidence
  that a security is common stock or that its current issuer/ticker mapping is
  wrong.

## Reconciliation Evidence Storage Decision

`provider_evidence` is necessary but is not sufficient storage for this
contract. It is the immutable provider-lineage link from one
`provider_observation` to one or more canonical targets. Its role values
(`CREATED_FROM`, `UPDATED_FROM`, and similar source facts) describe that raw
relationship; they cannot express a typed, normalized, security-level summary
of multiple observations, its distinct source snapshots, or an idempotent
derived-evidence key. Reusing it for reconciliation summaries would conflate
raw SEC ingestion with later reconciliation interpretation and make a changed
summary indistinguishable from a new provider fact.

Add a new append-only derived-evidence layer in `stonks` in E3.3. It belongs
beside the existing reconciliation evaluation/decision audit tables, but is
not an evaluation result and must not depend on a reconciliation run. A
collector can therefore build evidence before a dry run, and multiple dry runs
can evaluate the same stored evidence.

### Selected Tables

`security_reconciliation_evidence` stores one normalized evidence summary for
one candidate `security_id`.

- `reconciliation_evidence_id UUID` is the primary key.
- `security_id UUID NOT NULL` references `security`; `issuer_id` and
  `listing_id` are nullable foreign keys for the resolved targets described by
  the summary.
- `evidence_type VARCHAR(64) NOT NULL` is constrained initially to
  `SEC_ISSUER_SECURITY_MATCH`, `SEC_TICKER_EXCHANGE_STABILITY`,
  `SEC_SOURCE_SNAPSHOT_CONTINUITY`, and `SEC_SERIES_CLASS_IDENTIFIER`.
- `evidence_role VARCHAR(24) NOT NULL` is constrained to `SUPPORTS`,
  `CONFLICTS`, `BLOCKS`, or `CONTEXT`. This classifies the collected fact; it
  does not itself decide promotion.
- `evidence_key CHAR(64) NOT NULL` is a SHA-256 fingerprint of the canonical,
  versioned summary input: evidence type, target IDs, normalized observed
  values, provider/source identity, and distinct supporting source snapshot
  IDs. It has a unique constraint with `security_id` and `evidence_type`.
  Re-running unchanged collection therefore returns the same record; a changed
  evidence set produces a new immutable summary instead of overwriting history.
- `summary_json JSONB NOT NULL` contains the type-specific contract fields,
  including normalized CIK/ticker/exchange values, snapshot count, first/last
  observed times, insufficient-repeat marker where relevant, and conflict or
  missing-data context. It is not a replacement for relational source links.
- `collector_version VARCHAR(32) NOT NULL` and `created_at TIMESTAMPTZ NOT
  NULL DEFAULT now()` make the derivation reproducible as collector logic
  changes. No update timestamp is needed because rows are immutable.

`security_reconciliation_evidence_provider_evidence` is the required source
trail bridge. Its primary key is
`(reconciliation_evidence_id, provider_evidence_id)`, and both columns are
foreign keys. Every derived evidence record must have at least one bridge row;
the E3.3 writer enforces that invariant transactionally. Each linked
`provider_evidence` already identifies its exact `provider_observation`, so
the raw observation remains directly recoverable without duplicating mutable
observation fields.

`security_reconciliation_evidence_source_snapshot` records the distinct
semantic content snapshots used by a summary. Its primary key is
`(reconciliation_evidence_id, source_snapshot_id)`, with a foreign key to
`provider_source_snapshot`. It is required for snapshot-continuity and
ticker/exchange-stability summaries when snapshots are available; it may be
empty only for legacy evidence whose supporting observation predates snapshot
linkage. The bridge keeps snapshot identity durable even when raw stored-object
membership is later removed under retention policy.

The migration should index `(security_id, evidence_type, created_at DESC)` for
per-security evaluation, `(evidence_type, evidence_role, created_at DESC)` for
reporting, and each bridge's foreign-key column for reverse lineage. It should
not add a run ID: `core_run` is execution context, while source snapshots and
the immutable evidence key provide semantic identity.

### Evaluation Boundary

`security_reconciliation_evaluation_evidence` continues to link a dry-run
evaluation to the raw `provider_evidence` records that explain it. Before the
confidence evaluator is implemented, add a parallel evaluation-to-derived-
evidence bridge (or an equivalently explicit nullable derived-evidence link)
so an evaluation can cite both the summary it used and the underlying provider
trail. Do not store confidence scores, candidate decisions, or lifecycle
transitions in `security_reconciliation_evidence`; those remain the exclusive
responsibility of the evaluation and decision audit tables.

This selected shape preserves raw SEC lineage, gives derived evidence stable
idempotent identity, retains the source-snapshot continuity unit, and leaves
collection, confidence evaluation, and promotion independently rerunnable.

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
