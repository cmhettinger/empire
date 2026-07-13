# OHLCV Architecture Plan

## Overview

THIS DOCUMENT IS OBE - KEEPING FOR LEGACY REFERENCE ONLY

This document defines the initial architecture for adding historical and daily OHLCV market data to the Empire Stonks platform.

The design intentionally separates canonical financial identity from provider-native market data. This allows OHLCV ingestion and daily update work to proceed independently while security-master reconciliation continues.

The architecture is divided into three modules:

1. `empire-stonks-security-master`
2. `empire-stonks-ohlcv`
3. `empire-stonks-ohlcv-bridge`

Supporting run tracking, provenance, and source-object retention are provided by `empire-core` and its object-store services rather than duplicated inside the OHLCV package.

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

> What instrument did a provider publish, and what OHLCV values did it provide?

The bridge answers:

> Which provider instrument corresponds to which canonical listing?

These are different facts and should not be forced into the same model.

## Allow OHLCV ingestion before reconciliation

A provider instrument does not need a resolved `listing_id` before data can be imported.

For example:

```text
STOOQ   / US   / XOM
EODDATA / NYSE / XOM
YAHOO   / NYQ  / XOM
```

Each provider representation receives its own durable `provider_instrument_id` UUID and may accumulate OHLCV history immediately.

Later, the bridge may resolve all three provider instruments to the same canonical listing.

## Provider instruments are permanent identities

A `provider_instrument` record is not a temporary placeholder that is replaced after reconciliation.

It permanently identifies a provider-native object and preserves:

- Provider namespace
- Provider market code
- Provider ticker
- Provider metadata
- Source-specific adjustment semantics
- Source-specific OHLCV history
- Provenance for later authoritative-series construction

## Do not let OHLCV ingestion mutate the security master

The OHLCV module may create and update provider-native identities and OHLCV rows.

It must not create, promote, merge, or modify:

- Issuers
- Securities
- Listings
- Canonical symbol history
- Canonical identity decisions

## Make mappings temporal

Provider instruments may change meaning over time because of:

- Ticker reuse
- Exchange transfers
- Corporate reorganizations
- Provider symbology changes
- Incorrect historical mappings
- Listing replacements

Mappings between provider instruments and listings should therefore support `valid_from` and `valid_to`.

## Preserve provider-native market codes

Provider market codes should not be assumed to equal canonical exchange codes.

Examples:

```text
Provider   Provider market code   Canonical exchange
---------  ---------------------  ------------------
EODDATA    NYSE                   NYSE
YAHOO      NYQ                    NYSE
STOOQ      US                     unresolved or broad market
```

The provider-native code should be retained even after a canonical `exchange_id` is assigned.

## Reuse shared Empire reference data

The OHLCV module should reuse existing shared reference tables where appropriate, including:

- `provider`
- `exchange`
- `instrument_class`
- `instrument_type`
- `currency`
- `confidence_level`

The OHLCV module should not introduce a duplicate provider table or a parallel instrument taxonomy.

## Reuse Empire Core provenance

Package-specific import-run and source-artifact tables are unnecessary.

The OHLCV module should reuse:

- Empire Core run tracking
- `RunContext`
- Empire object store
- Existing object-store references
- Existing execution provenance conventions

---

# Module Architecture

## Full Module Relationship

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                 empire-stonks-security-master                               │
│                                                                              │
│  Owns canonical identity and shared reference data.                          │
│                                                                              │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐                           │
│  │ issuer   │ 1:N  │ security │ 1:N  │ listing  │                           │
│  │----------├─────►│----------├─────►│----------│                           │
│  │ issuer_id│      │security_id│      │listing_id│                           │
│  └──────────┘      │ issuer_id │      │security_id                           │
│                    └───────────┘      │ exchange_id                          │
│                                       └──────┬───┘                           │
│                                              │ N:1                            │
│                                              ▼                                │
│                                       ┌──────────┐                           │
│                                       │ exchange │                           │
│                                       └──────────┘                           │
│                                                                              │
│  Shared reference tables:                                                    │
│                                                                              │
│  ┌──────────┐  ┌─────────────────┐  ┌──────────┐  ┌─────────────────┐       │
│  │ provider │  │ instrument_type │  │ currency │  │ confidence_level│       │
│  └──────────┘  └─────────────────┘  └──────────┘  └─────────────────┘       │
│                                                                              │
│  Does not know about provider instruments or OHLCV rows.                     │
└───────────────────────────────▲──────────────────────────────────────────────┘
                                │
                                │ References canonical listing_id
                                │
┌───────────────────────────────┴──────────────────────────────────────────────┐
│                  empire-stonks-ohlcv-bridge                                 │
│                                                                              │
│  Owns the relationship between provider-native instruments and canonical     │
│  security-master listings.                                                   │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ provider_instrument_listing                                            │  │
│  │------------------------------------------------------------------------│  │
│  │ provider_instrument_listing_id                              UUID PK    │  │
│  │ provider_instrument_id                                      UUID FK    │  │
│  │ listing_id                                                  UUID FK    │  │
│  │ valid_from                                                   DATE NULL │  │
│  │ valid_to                                                     DATE NULL │  │
│  │ identity_status                                                        │  │
│  │ confidence_level_code                                       FK NULL    │  │
│  │ mapping_method                                              NULL        │  │
│  │ evidence                                                    JSONB NULL  │  │
│  │ created_by_run_id                                           UUID NULL   │  │
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
│                       empire-stonks-ohlcv                                   │
│                                                                              │
│  Owns provider-native instrument identities and daily OHLCV data.            │
│                                                                              │
│  Reuses shared provider, exchange, currency, and instrument-type references. │
│  Reuses Empire Core for run tracking and source-object provenance.           │
│                                                                              │
│  ┌──────────────┐         ┌────────────────────────────────┐                 │
│  │ provider     │         │ provider_market                │                 │
│  │ shared ref   │  1:N    │--------------------------------│                 │
│  └──────┬───────┘────────►│ provider_code             FK  │                 │
│         │                 │ provider_market_code       PK  │                 │
│         │                 │ provider_market_name           │                 │
│         │                 │ exchange_id            FK NULL │                 │
│         │                 │ mapping_status                  │                 │
│         │                 │ notes                           │                 │
│         │                 └──────────────┬─────────────────┘                 │
│         │                                │ 1:N                                │
│         │                                ▼                                    │
│         │                 ┌────────────────────────────────────────────┐       │
│         └────────────────►│ provider_instrument                        │       │
│                           │--------------------------------------------│       │
│                           │ provider_instrument_id          UUID PK    │       │
│                           │ provider_code                   FK         │       │
│                           │ provider_market_code            FK         │       │
│                           │ ticker                                     │       │
│                           │ provider_instrument_name        NULL       │       │
│                           │ instrument_type_code            FK NULL    │       │
│                           │ currency_code                   FK NULL    │       │
│                           │ price_adjustment_code           NULL       │       │
│                           │ volume_adjustment_code          NULL       │       │
│                           │ first_seen                      DATE       │       │
│                           │ last_seen                       DATE       │       │
│                           │ status                                     │       │
│                           │ raw_metadata                    JSONB NULL │       │
│                           │ created_at                      TIMESTAMPTZ│       │
│                           │ updated_at                      TIMESTAMPTZ│       │
│                           │                                            │       │
│                           │ UNIQUE(provider_code,                      │       │
│                           │        provider_market_code,               │       │
│                           │        ticker)                             │       │
│                           └───────────────────┬────────────────────────┘       │
│                                               │ 1:N                            │
│                                               ▼                                │
│                           ┌────────────────────────────────────────────┐       │
│                           │ ohlcv                                      │       │
│                           │--------------------------------------------│       │
│                           │ provider_instrument_id          PK/FK      │       │
│                           │ trading_date                    PK         │       │
│                           │ open                                       │       │
│                           │ high                                       │       │
│                           │ low                                        │       │
│                           │ close                                      │       │
│                           │ volume                                     │       │
│                           │ adjusted_close                  NULL       │       │
│                           │ created_by_run_id              FK NULL     │       │
│                           │ updated_by_run_id              FK NULL     │       │
│                           │ source_object_id               FK NULL     │       │
│                           │ quality_status                  NULL       │       │
│                           │ created_at                                 │       │
│                           │ updated_at                                 │       │
│                           └────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Package Dependency Shape

```text
empire-stonks-security-master      empire-stonks-ohlcv
               ▲                         ▲
               │                         │
               └── empire-stonks-ohlcv-bridge ──┘
```

The arrows above represent package dependencies.

```text
empire-stonks-ohlcv-bridge
    depends on empire-stonks-security-master
    depends on empire-stonks-ohlcv

empire-stonks-security-master
    does not depend on empire-stonks-ohlcv
    does not depend on empire-stonks-ohlcv-bridge

empire-stonks-ohlcv
    does not depend on canonical issuer, security, or listing identity
    does not depend on empire-stonks-ohlcv-bridge
```

All three modules may depend on `empire-core` for run tracking, object-store access, and shared infrastructure.

---

# Module Responsibilities

## `empire-stonks-security-master`

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
      └────────────► provider_instrument.instrument_type_code
```

The same instrument taxonomy should be used by both the security master and the OHLCV module.

The provider-native classification should still be retained in raw metadata where available.

---

## `empire-stonks-ohlcv`

The OHLCV module owns provider-native market identities and historical or daily OHLCV rows.

It does not require canonical listing reconciliation before ingestion.

### Primary responsibilities

- Provider-market discovery
- Provider-instrument discovery
- Provider-native instrument identity
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
provider_market
   │
   ▼
provider_instrument
   │
   ▼
ohlcv
```

---

## `empire-stonks-ohlcv-bridge`

The bridge module connects provider-native OHLCV identities to canonical listings.

It depends on both the security-master and OHLCV modules.

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
provider_instrument
        │
        ▼
provider_instrument_listing
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
SUPERSEDED
```

---

# Table Plan

## Security Master Tables Reused by OHLCV

The OHLCV and bridge modules should reuse existing security-master reference tables rather than duplicate them.

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

```text
exchange
--------
exchange_id         UUID PK
exchange_code
exchange_name
mic
country_alpha2
exchange_type
is_synthetic
is_active
notes
```

### `instrument_class`

Existing high-level classification reference.

```text
instrument_class
----------------
class_code          PK
class_name
description
sort_order
is_active
```

### `instrument_type`

Existing normalized instrument-type reference.

```text
instrument_type
---------------
type_code           PK
class_code          FK
type_name
description
is_active
```

Both canonical securities and provider-native instruments should reference this table.

```text
security.instrument_type_code
provider_instrument.instrument_type_code
```

---

## OHLCV Module Tables

## `provider_market`

Represents a market namespace as defined by a provider.

This table preserves provider-native market codes and optionally maps them to a canonical exchange.

```text
provider_market
---------------
provider_code                 PK/FK
provider_market_code          PK
provider_market_name          NULL
exchange_id                   FK NULL
mapping_status
notes                         NULL
```

### Key

```text
PRIMARY KEY (
    provider_code,
    provider_market_code
)
```

### Important rule

`provider_market_code` is a provider-native value.

It must not be assumed to equal:

- `exchange.exchange_code`
- `exchange.mic`
- Any other canonical exchange identifier

Examples:

```text
provider   provider_market_code   exchange_id
---------  ---------------------  -----------
EODDATA    NYSE                   canonical NYSE UUID
YAHOO      NYQ                    canonical NYSE UUID
STOOQ      US                     NULL or broad-market mapping
```

`exchange_id` should remain nullable because some provider markets may be:

- Broad market namespaces
- Synthetic markets
- Index namespaces
- Unknown or unresolved
- Provider-specific groupings

---

## `provider_instrument`

Represents a durable provider-native instrument identity.

```text
provider_instrument
-------------------
provider_instrument_id        UUID PK
provider_code                 FK
provider_market_code          FK
ticker
provider_instrument_name      NULL
instrument_type_code          FK NULL
currency_code                 FK NULL
price_adjustment_code         NULL
volume_adjustment_code        NULL
first_seen                    DATE
last_seen                     DATE
status
raw_metadata                  JSONB NULL
created_at                    TIMESTAMPTZ
updated_at                    TIMESTAMPTZ
```

### Initial natural-key constraint

```text
UNIQUE (
    provider_code,
    provider_market_code,
    ticker
)
```

### Identity rule

The natural key is a discovery and lookup key.

The durable identity is:

```text
provider_instrument_id UUID
```

If ticker reuse is detected, the old provider instrument should not be repurposed. A new provider-instrument identity should be created.

### Classification rule

`instrument_type_code` should contain Empire's normalized interpretation of the provider instrument.

The original vendor classification should remain available through provider-native fields or `raw_metadata`.

---

## `ohlcv`

Stores provider-native daily OHLCV rows.

```text
ohlcv
-----
provider_instrument_id        PK/FK
trading_date                  PK
open
high
low
close
volume
adjusted_close                NULL
created_by_run_id             FK NULL
updated_by_run_id             FK NULL
source_object_id              FK NULL
quality_status                NULL
created_at
updated_at
```

### Primary key

```text
PRIMARY KEY (
    provider_instrument_id,
    trading_date
)
```

### Initial scope

The first version assumes:

- Daily bars
- One stored interpretation per provider instrument
- No intraday data
- No parallel regular-session and extended-session streams
- No multiple adjustment variants stored side by side

Because of that, a separate `market_data_series` table is not required initially.

### Adjustment semantics

The model must explicitly preserve what the provider's values mean.

At minimum, the provider instrument should define or inherit:

```text
price_adjustment_code
volume_adjustment_code
```

Possible future attributes include:

```text
interval_code
session_code
```

A separate series table should only be introduced when a real requirement appears, such as:

- Daily raw and daily adjusted histories for the same provider instrument
- Intraday and daily data
- Regular-session and extended-session data
- Multiple currencies
- Multiple parallel vendor series variants

---

# Bridge Module Tables

## `provider_instrument_listing`

Maps a provider-native instrument to a canonical security-master listing.

```text
provider_instrument_listing
---------------------------
provider_instrument_listing_id    UUID PK
provider_instrument_id            UUID FK
listing_id                        UUID FK
valid_from                        DATE NULL
valid_to                          DATE NULL
identity_status
confidence_level_code             FK NULL
mapping_method                    NULL
evidence                          JSONB NULL
created_by_run_id                 UUID NULL
created_at
updated_at
```

### Purpose

This table owns the claim:

> This provider instrument corresponds to this canonical listing for this effective period.

### Temporal requirement

Mappings should not be treated as permanently timeless.

```text
provider_instrument_id
    -> listing_id
    -> valid_from
    -> valid_to
```

### Expected cardinality

A provider instrument may have:

- No confirmed listing
- One current listing
- Different listings over different time periods
- Multiple candidates during reconciliation
- Rejected or superseded mappings

### Possible future bridge tables

The initial bridge may begin with only `provider_instrument_listing`.

Future needs may justify:

```text
provider_instrument_listing_candidate
provider_instrument_listing_conflict
provider_instrument_listing_review
provider_instrument_equivalence
```

These should remain inside the bridge package rather than either core module.

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
provider_market
      │
      ▼
provider_instrument
      │
      ▼
ohlcv
```

The import process may create provider markets, provider instruments, and OHLCV rows.

It must not create canonical issuer, security, or listing records.

## Identity Reconciliation

```text
provider_instrument
        │
        ▼
candidate matching
        │
        ▼
provider_instrument_listing
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
provider_instrument
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

`provider + market + ticker` cannot always be assumed to represent the same real-world instrument forever.

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
provider_instrument -> listing
```

Some provider instruments may instead represent:

```text
provider_instrument -> index
provider_instrument -> benchmark
provider_instrument -> currency pair
provider_instrument -> commodity
```

The first implementation may focus on listing mappings.

Future canonical models can add sibling bridge tables without changing the OHLCV module.

---

# Initial Build Scope

## Security Master

Continue the existing reconciliation and promotion work independently.

No OHLCV dependency is required.

## OHLCV Module

Initial tables:

```text
provider_market
provider_instrument
ohlcv
```

Initial capabilities:

1. Register Stooq, EODData, and Yahoo in the shared `provider` table.
2. Discover provider-native markets.
3. Create durable provider-instrument UUIDs.
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
provider_instrument_listing
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
│ empire-stonks-security-master    │
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
│ provider_instrument_listing      │
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