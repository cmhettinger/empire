# OHLCV Architecture Plan

## Overview

This document defines the initial architecture for adding daily and historical backfill OHLCV market data to the Empire Stonks platform.

The design intentionally separates canonical financial identity from provider-native market data. This allows OHLCV ingestion and daily update work to proceed independently while security-master reconciliation continues.

The architecture is divided into three modules:

1. `empire-stonks-security-master`
2. `empire-stonks-ohlcv`
3. `empire-stonks-ohlcv-bridge`

Supporting artifacts for run tracking, provenance, and source-object retention are provided by `empire-core` and its object-store services rather than duplicated inside the OHLCV package.

The initial market-data providers are expected to include:

- Stooq
- EODData
- Yahoo Finance

Each provider may represent the same real-world listing differently. Provider-native identities are therefore retained independently and reconciled to canonical listings later through the bridge module.

---

# Architectural Principles

## Keep canonical identity separate from provider data

The security master answers:

> What is the canonical issuer, security, and listing?

The OHLCV module answers:

> What listing did a provider publish, and what OHLCV values did it provide?

The bridge answers:

> Which provider listing corresponds to which canonical listing?

These are different facts and should not be forced into the same model.

## Allow OHLCV ingestion before reconciliation

A provider listing does not need a resolved `listing_id` before data can be imported.

For example:

```text
STOOQ   / US   / XOM
EODDATA / NYSE / XOM
YAHOO   / NYQ  / XOM
```

Each provider representation receives its own durable UUID and may accumulate OHLCV history immediately.

Later, the bridge may resolve all three provider instruments to the same canonical listing.

## Provider listings are permanent identities

A `provider_listing` record is not a temporary placeholder that is replaced after reconciliation.

It permanently identifies a provider-native object and preserves:

- Provider namespace
- Provider market
- Provider ticker
- Provider metadata
- Source-specific adjustment semantics
- Source-specific OHLCV history
- Provenance for later authoritative-series construction

## Do not let OHLCV ingestion mutate the security master

The OHLCV module may create and update provider-native listings and OHLCV rows.

It must not create, promote, merge, or modify canonical:

- Issuers
- Securities
- Listings
- Canonical symbol history
- Canonical identity decisions

## Make mappings temporal

Provider listings may change meaning over time because of:

- Ticker reuse
- Exchange transfers
- Corporate reorganizations
- Provider symbology changes
- Incorrect historical mappings
- Listing replacements

Mappings between provider listings and listings should therefore support `valid_from` and `valid_to`.

## Preserve provider-native markets

Provider markets should attempt to map to canonical exchange codes.

Examples:

```text
Provider   Provider market   Canonical exchange
---------  ---------------  ------------------
EODDATA    NYSE              NYSE
YAHOO      NYQ               NYSE
STOOQ      US                unresolved or broad market
```

The provider-native market metadata should be retained even if a canonical `exchange_id` is later assigned.

## Reuse shared Empire reference data

The OHLCV module should reuse existing stonks shared reference tables where appropriate, including examples:

- `provider`
- `exchange`
- `instrument_class`
- `instrument_type`
- `currency`
- `confidence_level`

The OHLCV module should not introduce a duplicate provider table or a parallel instrument taxonomy.

## Reuse Empire Core provenance

Package-specific import-run and source-artifact tables should be unnecessary.

The OHLCV module should reuse:

- Empire Core run tracking
- Empire Core run contexts
- Empire object store
- Existing object-store references
- Existing execution provenance conventions

---

# Module Architecture

## Full Module Relationship

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│                 empire-stonks-securities                                      │
│                                                                               │
│  Owns canonical identity and shared reference data.                           │
│                                                                               │
│  ┌──────────┐      ┌───────────┐      ┌───────────┐                           │
│  │ issuer   │ 1:N  │ security  │ 1:N  │ listing   │                           │
│  │----------├─────►│-----------├─────►│-----------│                           │
│  │issuer_id │      │security_id│      │listing_id │                           │
│  └──────────┘      │issuer_id  │      │security_id|                           │
│                    └───────────┘      │exchange_id|                           │
│                                       └──────┬────┘                           │
│                                              │ N:1                            │
│                                              ▼                                │
│                                       ┌──────────┐                            │
│                                       │ exchange │                            │
│                                       └──────────┘                            │
│                                                                               │
│  Shared reference tables:                                                     │
│                                                                               │
│  ┌──────────┐  ┌─────────────────┐  ┌──────────┐  ┌─────────────────┐         │
│  │ provider │  │ instrument_type │  │ currency │  │ confidence_level│         │
│  └──────────┘  └─────────────────┘  └──────────┘  └─────────────────┘         │
│                                                                               │
│  Does not know about provider listings or OHLCV rows.                         │
└───────────────────────────────▲───────────────────────────────────────────────┘
                                │
                                │ References canonical listing_id
                                │
┌───────────────────────────────┴──────────────────────────────────────────────┐
│                  empire-stonks-ohlcv-bridge                                  │
│                                                                              │
│  Owns the relationship between provider-native instruments and canonical     │
│  security-master listings.                                                   │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ provider_listing_mapping                                               │  │
│  │------------------------------------------------------------------------│  │
│  │ provider_listing_mapping_id                                 UUID PK    │  │
│  │ provider_listing_id                                         UUID FK    │  │
│  │ listing_id                                                  FK         │  │
│  │ valid_from                                                  DATE NULL  │  │
│  │ valid_to                                                    DATE NULL  │  │
│  │ mapping_status                                                         │  │
│  │ confidence_level_code                                       FK NULL    │  │
│  │ mapping_method                                              NULL       │  │
│  │ evidence                                                    JSONB NULL │  │
│  │ created_by_run_id                                           UUID NULL  │  │
│  │ created_at                                                             │  │
│  │ updated_at                                                             │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  Depends on both adjacent modules.                                           │
│  Neither adjacent module depends on this module.                             │
└───────────────────────────────▲──────────────────────────────────────────────┘
                                │
                                │ References provider_instrument_id
                                │
┌───────────────────────────────┴──────────────────────────────────────────────┐
│                       empire-stonks-ohlcv                                    │
│                                                                              │
│  Owns provider-native listings and daily OHLCV data.                         │
│                                                                              │
│  Reuses shared provider, exchange, currency, and instrument-type references. │
│  Reuses Empire Core for run tracking and source-object provenance.           │
│                                                                              │
│  ┌──────────────┐                                                            │
│  │ provider     │                                                            │
│  │ shared ref   │                                                            │
│  └──────┬───────┘                                                            │
│         │                                                                    │
│         │                                                                    │
│         │                                                                    │
│         │                                                                    │
│         │                 ┌────────────────────────────────────────────┐     │
│         └────────────────►│ provider_listing                           │     │
│                           │--------------------------------------------│     │
│                           │ provider_listing_id             UUID PK    │     │
│                           │ provider_code                   FK         │     │
│                           │ provider_market                 VARCHAR    │     │
│                           │ ticker                          VARCHAR    │     │
│                           │ provider_listing_name           VARCHAR    │     │
│                           │ instrument_type_code            FK NULL    │     │
│                           │ currency_code                   FK NULL    │     │
│                           │ price_adjustment_code           NULL       │     │
│                           │ volume_adjustment_code          NULL       │     │
│                           │ first_seen                      DATE       │     │
│                           │ last_seen                       DATE       │     │
│                           │ status                                     │     │
│                           │ raw_metadata                    JSONB NULL │     │
│                           │ created_at                      TIMESTAMPTZ│     │
│                           │ updated_at                      TIMESTAMPTZ│     │
│                           │                                            │     │
│                           │ UNIQUE(provider_code,                      │     │
│                           │        provider_market,                    │     │
│                           │        ticker)                             │     │
│                           └───────────────────┬────────────────────────┘     │
│                                               │ 1:N                          │
│                                               ▼                              │
│                           ┌────────────────────────────────────────────┐     │
│                           │ ohlcv                                      │     │
│                           │--------------------------------------------│     │
│                           │ provider_listing_id             PK/FK      │     │
│                           │ trading_date                    PK         │     │
│                           │ open                                       │     │
│                           │ high                                       │     │
│                           │ low                                        │     │
│                           │ close                                      │     │
│                           │ volume                                     |     │
│                           │ adjusted_close                 NULL        │     │
│                           │ created_by_run_id              FK NULL     │     │
│                           │ updated_by_run_id              FK NULL     │     │
│                           │ source_object_id               FK NULL     │     │
│                           │ quality_status                  NULL       │     │
│                           │ created_at                                 │     │
│                           │ updated_at                                 │     │
│                           └────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Package Dependency Shape

```text
empire-stonks-securities             empire-stonks-ohlcv
               ▲                                ▲
               │                                │
               └── empire-stonks-ohlcv-bridge ──┘
```

The arrows above represent package dependencies.

```text
empire-stonks-ohlcv-bridge
    depends on empire-stonks-securities
    depends on empire-stonks-ohlcv

empire-stonks-securities
    does not depend on empire-stonks-ohlcv
    does not depend on empire-stonks-ohlcv-bridge

empire-stonks-ohlcv
    does not depend on canonical issuer, security, or listing identity
    does not depend on empire-stonks-ohlcv-bridge
```

All three modules may depend on `empire-core` for run tracking, object-store access, and shared infrastructure.

---

# Module Responsibilities

## `empire-stonks-securities`

The security-master module owns canonical financial identity and shared reference data.

### Primary responsibilities

- Canonical issuer identity
- Canonical security identity
- Canonical listing identity
- Exchange reference data
- Canonical symbol history
- Instrument classification
- Currency references
- Provider references
- Confidence-level references
- Security identity reconciliation
- Promotion, merge, split, and conflict handling

### Core identity chain

```text
issuer
   │
   ▼
security
   │
   ▼
listing
   │
   ▼
exchange
```

### Existing shared taxonomy

```text
instrument_class
      │
      │ 1:N
      ▼
instrument_type
      │
      ├────────────► security.instrument_type_code
      │
      └────────────► provider_listing.instrument_type_code
```

The same instrument taxonomy should be used by both the security master and the OHLCV module.

The provider-native classification should still be retained in raw metadata when available.

---

## `empire-stonks-ohlcv`

The OHLCV module owns provider-native market listings and historical or daily OHLCV rows.

It does not require canonical listing reconciliation before ingestion.

### Primary responsibilities

- Provider-market discovery
- Provider-listing discovery
- Provider-native listing identity
- Historical OHLCV backfill
- Daily incremental OHLCV imports
- Idempotent upserts
- Source-object provenance through Empire Core
- Data-quality validation
- Gap detection
- Stale-series detection
- Provider coverage reporting

### Initial providers

```text
STOOQ
EODDATA
YAHOO
```

Each provider has its own provider-native instruments.

```text
STOOQ   / US   / XOM  ─┐
EODDATA / NYSE / XOM ──┼─ later resolved to one canonical listing
YAHOO   / NYQ  / XOM ──┘
```

The provider-specific UUIDs remain permanent even after reconciliation.

### Core OHLCV relationship

```text
provider
   │
   ▼
provider_listing
   │
   ▼
ohlcv
```

---

## `empire-stonks-ohlcv-bridge`

The bridge module connects provider-native OHLCV listings to canonical listings.

It depends on both the securities and OHLCV modules.

Neither core module depends on the bridge.

### Primary responsibilities

- Candidate listing mappings
- Confirmed listing mappings
- Mapping confidence
- Mapping evidence
- Temporal mapping validity
- Ambiguity handling
- Conflict handling
- Rejected mappings
- Superseded mappings
- Manual and automated review outcomes

### Core bridge relationship

```text
provider_listing
        │
        ▼
listing
        │
        ▼
security
        │
        ▼
issuer
```

### Recommended mapping states

```text
UNRESOLVED
CANDIDATE
CONFIRMED
AMBIGUOUS
CONFLICTED
REJECTED
```

---

# Table Plan

## Security Master Tables Reused by OHLCV

The OHLCV and bridge modules should reuse existing reference tables rather than duplicate them.

### `provider`

Existing generic provider table.

```text
provider
--------
provider_code       PK
provider_name
provider_type
website
description
is_active
```

Expected OHLCV provider rows include:

```text
STOOQ
EODDATA
YAHOO
```

### `exchange`

Existing canonical exchange reference.


### `instrument_class`

Existing high-level classification reference.

### `instrument_type`

Both canonical securities and provider-native listings should reference this table.

---

## OHLCV Module Tables

## `provider_listing`

Represents a durable provider-native listing.

### Classification rule

`instrument_type_code` should contain Empire's normalized interpretation of the provider instrument.

The original vendor classification should remain available through provider-native fields or `raw_metadata` when possible.

---

## `ohlcv`

Stores provider-native daily OHLCV rows.

### Initial scope

The first version assumes:

- Daily bars
- One stored interpretation per provider instrument
- No intraday data
- No parallel regular-session and extended-session streams
- No multiple adjustment variants stored side by side

Because of that, a separate `market_data_series` table is not required.

---

# Bridge Module Tables

## `provider_listing_mapping`

Maps a provider-native instrument to a canonical security-master listing.

### Purpose

This table owns the claim:

> This provider listing corresponds to this canonical listing for this effective period.

### Temporal requirement

Mappings should not be treated as permanently timeless.

```text
provider_listing_id
    -> listing_id
    -> valid_from
    -> valid_to
```

### Expected cardinality

A provider listing may have:

- No confirmed listing
- One current listing
- Different listings over different time periods
- Multiple candidates during reconciliation
- Rejected mappings

---

# Data Flow

## OHLCV Ingestion

```text
Provider source
      │
      ▼
Empire object store
      │
      ▼
RunContext / Empire Core run
      │
      ▼
provider_listing
      │
      ▼
ohlcv
```

The import process may create provider listings and OHLCV rows.

It must not create canonical issuer, security, or listing records.

## Identity Reconciliation

```text
provider_listing
        │
        ▼
candidate matching
        │
        ▼
canonical listing
        │
        ▼
security
        │
        ▼
issuer
```

## Multi-Provider Example

```text
STOOQ instrument UUID
    provider key: US / XOM
          │
          ├── Stooq OHLCV rows
          │
          └── bridge mapping ──────────┐
                                       │
EODDATA instrument UUID                │
    provider key: NYSE / XOM           │
          │                            │
          ├── EODData OHLCV rows       ├──► canonical NYSE XOM listing
          │                            │
          └── bridge mapping ──────────┤
                                       │
YAHOO instrument UUID                  │
    provider key: NYQ / XOM            │
          │                            │
          ├── Yahoo OHLCV rows         │
          │                            │
          └── bridge mapping ──────────┘
```

---

# Authoritative OHLCV Strategy

The long-term goal is one authoritative OHLCV history per canonical tradable instrument.

The first phase stores provider-native histories separately.

```text
provider_listing
        │
        ▼
provider-native ohlcv
```

Later, confirmed bridge mappings allow provider histories to be evaluated for canonical use.

```text
provider OHLCV
    STOOQ
    EODDATA
    YAHOO
        │
        ▼
selection and validation policy
        │
        ▼
authoritative Empire OHLCV
```

The authoritative series should not silently merge provider rows without provenance.

Examples of acceptable future behavior include:

- Stooq as primary
- EODData as fallback
- Yahoo for selected global indices
- Second-provider validation for suspicious bars
- Explicit, auditable gap filling
- Manual overrides with retained evidence

The initial schema does not need to finalize the authoritative-series storage model, but it must preserve enough provider identity and provenance to build one later.

---

# Risks and Required Safeguards

## Ticker reuse

`provider listing + market + ticker` cannot always be assumed to represent the same real-world instrument forever.

When reuse is detected:

- Preserve the old provider instrument
- Create a new provider-instrument UUID
- Use temporal bridge mappings
- Do not rewrite old OHLCV ownership

## Provider disagreement

Different providers may disagree on:

- Trading dates
- Prices
- Volume
- Adjustments
- Exchange assignment
- Instrument type
- Symbol history

Provider-native histories must remain separate until an explicit canonical selection process is applied.

## Adjustment mismatch

Do not compare or merge unlike histories without normalization.

Possible differences include:

- Raw prices
- Split-adjusted prices
- Dividend-adjusted prices
- Total-return-adjusted prices
- Adjusted or unadjusted volume
- Regular-session or extended-session values

## Unresolved identity

Unresolved provider instruments remain valid OHLCV records.

However, downstream applications should distinguish between:

- Provider-native data
- Candidate mappings
- Confirmed canonical mappings

A provider-native chart may work without a listing.

Issuer-level analytics, portfolio reporting, and canonical security aggregation should normally require a confirmed bridge.

## Index and benchmark handling

The initial bridge is centered on:

```text
provider_listingt -> listing
```

Some provider instruments may instead represent:

```text
provider_listing -> index
provider_listing -> benchmark
provider_listing -> currency pair
provider_listing -> commodity
```

The first implementation may focus on listing mappings.

Future canonical models can add sibling bridge tables without changing the OHLCV module.

---

# Initial Build Scope

## Security Master (empire-stonks-securities)

Continue the existing reconciliation and promotion work independently.

No OHLCV dependency is required.

## OHLCV Module (empire-stonks-ohlcv)

Initial tables:

```text
provider_listing
ohlcv
```

Initial capabilities:

1. Register Stooq, EODData, and Yahoo in the shared `provider` table.
2. Discover provider-native markets
3. Create durable provider-listing UUIDs.
4. Import historical daily OHLCV.
5. Run daily incremental updates.
6. Use idempotent upserts.
7. Retain raw source objects through Empire Core.
8. Link changes to Empire Core run records.
9. Validate OHLCV invariants.
10. Report missing bars, stale series, and coverage gaps.

## OHLCV Bridge

Initial table:

```text
provider_listing_mapping
```

Initial capabilities:

1. Create unresolved and candidate mappings.
2. Confirm provider-instrument-to-listing mappings.
3. Store confidence and evidence.
4. Support effective dates.
5. Flag ambiguous and conflicting mappings.
6. Keep bridge writes isolated from both core modules.

---

# Final Ownership Summary

```text
┌──────────────────────────────────┐
│ empire-stonks-securities.        │
│----------------------------------│
│ Canonical financial identity     │
│                                  │
│ issuer                           │
│ security                         │
│ listing                          │
│ exchange                         │
│ provider                         │
│ instrument_class                 │
│ instrument_type                  │
│ currency                         │
│ confidence levels                │
└────────────────▲─────────────────┘
                 │
                 │ canonical listing reference
                 │
┌────────────────┴─────────────────┐
│ empire-stonks-ohlcv-bridge       │
│----------------------------------│
│ Identity relationship            │
│                                  │
│ provider_listing_mapping.        │
│ mapping status                   │
│ confidence                       │
│ evidence                         │
│ temporal validity                │
└────────────────▲─────────────────┘
                 │
                 │ provider instrument reference
                 │
┌────────────────┴─────────────────┐
│ empire-stonks-ohlcv              │
│----------------------------------│
│ Provider-native market data      │
│                                  │
│ provider_market                  │
│ provider_instrument              │
│ ohlcv                            │
└──────────────────────────────────┘

All modules reuse empire-core for:
- Run tracking
- RunContext
- Object-store persistence
- Source-object provenance
- Shared infrastructure
```

This architecture allows OHLCV ingestion and daily processing to proceed immediately while canonical security-master reconciliation continues independently.

## First Priority Build: OHLCV Module (empire-stonks-ohlcv)

Initial design/build elements:

Generate stonks-ohlcv-plan.md with steps for module buildout (similar to docs/todo/reconciliation-plan.md) which should
include at minimum:

0. Generate new empire-stonks-ohlcv package and integrate into empire airflow stack
1. Register Stooq, EODData, and Yahoo in the shared `provider` table.
2. Design empire-stonks-ohlcv tables and flyway scripts in the stonks schema of empire postgres
3. Create dag for importing nightly eoddata records.
3. Create dag for importing nightly stooq records.
4. Create one-time use utility to import historical daily OHLCV from stooq.
5. Run daily incremental updates.
6. Use idempotent upserts.
7. Generate daily reports include status missing bars, stale series, and coverage gaps.
