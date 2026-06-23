# Empire Stonks Security Master

## Overview

The Security Master is designed around a simple core relationship:

```text
issuer
  └── security
        └── listing
              └── listing_symbol_history
```

Everything else in the schema exists to support, classify, identify, enrich, validate, or provide historical context for that chain.

---

# Reference Data

Reference tables provide standardized codes and metadata used throughout the security master.

```text
                    ┌────────────────────┐
                    │ iso3166_country    │
                    └─────────┬──────────┘
                              │
                              │
┌────────────────────┐        │        ┌────────────────────┐
│ iso4217_currency   │        │        │ iso10383_mic       │
└─────────┬──────────┘        │        └─────────┬──────────┘
          │                   │                  │
          │                   │                  │
          v                   v                  v
┌────────────────────────────────────────────────────────────┐
│ exchange                                                   │
└───────────────┬────────────────────────────────────────────┘
                │
                v
        ┌──────────────────┐
        │ exchange_alias   │
        └──────────────────┘
```

## Purpose

### iso3166_country

Reference list of countries.

Examples:

- US
- CA
- GB
- JP

### iso4217_currency

Reference list of currencies.

Examples:

- USD
- CAD
- EUR
- GBP

### iso10383_mic

ISO market identifier codes.

Examples:

- XNAS
- XNYS
- ARCX

### exchange

Normalized exchange master.

Examples:

- NASDAQ
- NYSE
- NYSE Arca
- CBOE

### exchange_alias

Historical and alternate names for exchanges.

Examples:

- Nasdaq Stock Market
- NASDAQ Global Select
- NYSE MKT

---

# Core Security Hierarchy

This is the heart of the model.

```text
┌──────────────────┐
│ issuer           │
└────────┬─────────┘
         │
         │ 1 issuer has many securities
         v
┌──────────────────┐
│ security         │
└────────┬─────────┘
         │
         │ 1 security has many listings
         v
┌──────────────────┐        ┌──────────────────┐
│ listing          │───────>│ exchange         │
└────────┬─────────┘        └──────────────────┘
         │
         │ 1 listing has ticker history
         v
┌──────────────────────────┐
│ listing_symbol_history   │
└──────────────────────────┘
```

## issuer

Represents the legal entity.

Examples:

- Apple Inc.
- Microsoft Corporation
- Berkshire Hathaway Inc.

An issuer may have many securities.

---

## security

Represents a tradable financial instrument.

Examples:

- Apple common stock
- Berkshire Hathaway Class A
- Berkshire Hathaway Class B
- SPY ETF

A security belongs to one issuer.

A security may have multiple listings.

### Phase 2A SEC Ticker Observations

Phase 2A creates provisional issuer-linked securities from SEC ticker observations
after issuers have been established by CIK. These rows use the observed
`issuer + ticker_norm` as a temporary identity anchor so later security-master
steps have a concrete security record to enrich.

This is a current-state bootstrap resolver, not final historical identity.
Ticker is stored as observed medium-confidence evidence, not treated as a
permanent security identity. The resulting `UNKNOWN` securities are future-
upgradable records: later backfill, fund/class datasets, exchange directories,
filings, or provider identifiers can add stronger identifiers and promote or
reconcile the provisional records without corrupting the raw SEC evidence.

The SEC ticker files do not prove that the instrument is common stock. For that
reason, Phase 2A writes these securities with the conservative `UNKNOWN`
instrument type and stores the observed ticker as a `TICKER` security identifier.
Later enrichment may promote the instrument type to `COMMON_STOCK`, `ETF`, `ADR`,
`PREFERRED`, or another more specific type when stronger evidence is available.

Phase 2A does not create listings or `listing_symbol_history` rows. Exchange and
listing normalization are separate follow-on steps.

### Ticker Normalization Scope

In Phase 2A, `ticker_norm` means the SEC-normalized ticker observed in SEC
security-master sources. The normalization rule is intentionally
backward-compatible with the original ingestion behavior: trim surrounding
whitespace, uppercase letters, and preserve internal punctuation and separators.
For example, `brk-b`, `brk.b`, and `bf/b` become `BRK-B`, `BRK.B`, and `BF/B`;
SEC ingestion does not convert dots to dashes, dashes to dots, or remove slashes.

`ticker_norm`, display symbols, provider symbols, and durable canonical symbols
are not interchangeable. Yahoo, Stooq, EODData, exchange directories, and future
OHLCV providers may use different symbol conventions for share classes,
preferreds, warrants, units, rights, foreign tickers, and exchange suffixes.
Those mappings belong in a future provider-symbol reconciliation phase. SEC
ingestion should not encode Yahoo/Stooq/EODData assumptions.

---

## listing

Represents a security trading on a specific exchange.

Examples:

- AAPL on NASDAQ
- BRK.A on NYSE
- SPY on NYSE Arca

A listing belongs to one security and one exchange.

### Phase 2A SEC Exchange Observations

Phase 2A creates current active listings from
`sec_company_tickers_exchange` observations after issuers and provisional
securities exist. The listing identity is the existing security, the resolved
exchange, and not the ticker. The observed current ticker is copied onto the
listing for convenience, but symbol changes are represented in
`listing_symbol_history`.

Exchange names are resolved through the existing `exchange` and `exchange_alias`
reference tables. Unknown exchange names are skipped and logged; this step does
not create new exchange records.

`sec_company_tickers` observations generally do not create listings because that
source does not include exchange information. Historical ticker reconstruction,
delisting detection, inactive listing closure, and exchange-specific enrichment
are future milestones.

---

## listing_symbol_history

Stores historical ticker symbols.

Examples:

| Symbol | Start Date | End Date |
|----------|------------|-----------|
| GOOG | 2004 | 2015 |
| GOOGL | 2015 | NULL |

Used to preserve ticker changes without losing history.

Each listing may have only one current active symbol at a time. Current rows have
`valid_to IS NULL`; when an unambiguous new ticker is observed for the same
security/exchange listing, the prior active symbol is closed and a new active
symbol is inserted. Missing SEC rows do not close listings or symbols.

---

# Issuer Identity and Naming

Issuer identity changes over time and can have multiple identifiers.

```text
┌──────────────────┐
│ issuer           │
└───────┬──────────┘
        │
        ├───────────────┐
        v               v
┌──────────────────┐   ┌──────────────────────┐
│ issuer_identifier│   │ issuer_name_history  │
└──────────────────┘   └──────────────────────┘
```

## issuer_identifier

Stores issuer-level identifiers.

Examples:

- SEC CIK
- LEI
- DUNS

Multiple identifiers may exist for one issuer.

---

## issuer_name_history

Tracks legal name changes.

Examples:

| Old Name | New Name |
|-----------|-----------|
| Google Inc. | Alphabet Inc. |
| Facebook, Inc. | Meta Platforms, Inc. |

---

# Security Identifiers

```text
┌──────────────────┐
│ security         │
└───────┬──────────┘
        │
        v
┌─────────────────────┐
│ security_identifier │
└─────────────────────┘
```

## security_identifier

Stores security-level identifiers.

Examples:

- CUSIP
- ISIN
- FIGI
- SEDOL

One security may have multiple identifiers.

---

# Instrument Classification

Defines what a security actually is.

```text
┌─────────────────────┐
│ instrument_class    │
└─────────┬───────────┘
          │
          │ one class has many types
          v
┌─────────────────────┐
│ instrument_type     │
└─────────┬───────────┘
          │
          │ security is typed by this
          v
┌─────────────────────┐
│ security            │
└─────────────────────┘
```

## instrument_class

High-level categories.

Examples:

- Equity
- Fund
- Debt
- Derivative

---

## instrument_type

Detailed instrument types.

Examples:

- Common Stock
- Preferred Stock
- ETF
- ETN
- Mutual Fund
- Corporate Bond
- ADR

Each security references one instrument type.

---

# Industry and Classification Systems

Supports external classification standards.

```text
┌──────────────────────┐
│ classification_code  │
└──────────┬───────────┘
           │
           v
┌────────────────────────┐
│ issuer_classification  │
└──────────┬─────────────┘
           │
           v
┌──────────────────────┐
│ issuer               │
└──────────────────────┘
```

## classification_code

Stores normalized classification codes.

Examples:

### SIC

- 3571 Electronic Computers

### NAICS

- 334111 Electronic Computer Manufacturing

### GICS

- Information Technology

---

## issuer_classification

Associates issuers with one or more classification systems.

Allows multiple systems to coexist simultaneously.

---

# Corporate Actions and Events

Tracks notable events affecting issuers, securities, or listings.

```text
                         ┌──────────────────┐
                         │ issuer           │
                         └────────┬─────────┘
                                  │
┌──────────────────────┐          │
│ security_event       │<─────────┤
└──────────┬───────────┘          │
           │                      │
           │                      v
           │             ┌──────────────────┐
           └────────────>│ security         │
                         └────────┬─────────┘
                                  │
                                  v
                         ┌──────────────────┐
                         │ listing          │
                         └──────────────────┘
```

## security_event

Examples:

- IPO
- Delisting
- Ticker Change
- Stock Split
- Reverse Split
- Name Change
- Exchange Transfer
- Merger
- Acquisition
- Bankruptcy

Events may reference an issuer, security, listing, or a combination.

---

# Provider Evidence and Lineage

Every important fact should be traceable back to a provider observation.

```text
┌──────────────────────┐
│ provider_observation │
└──────────┬───────────┘
           │
           │ one observation can support many things
           v
┌──────────────────────┐
│ provider_evidence    │
└──────┬──────┬──────┬──┘
       │      │      │
       v      v      v
┌────────┐ ┌──────────┐ ┌─────────┐
│ issuer │ │ security │ │ listing │
└────────┘ └──────────┘ └─────────┘
```

## provider_observation

Represents a raw observation from a provider.

Examples:

- SEC filing
- EDGAR bulk feed
- Exchange symbol directory
- Corporate action notice

---

## provider_evidence

Associates observations with records in the security master.

This provides:

- Auditability
- Traceability
- Historical lineage
- Provider verification

---

# Design Philosophy

The schema intentionally separates:

- Identity
- Classification
- Exchange Presence
- Events
- Evidence

from the core hierarchy.

The core remains:

```text
issuer
  └── security
        └── listing
              └── listing_symbol_history
```

Everything else exists to support that structure while preserving:

- Historical accuracy
- Multiple identifier systems
- Multiple classification systems
- Exchange history
- Corporate action history
- Full provider lineage

This design is intended to support a complete historical security master dating back to 1995 and sourced primarily from SEC EDGAR, exchange directories, and related reference datasets.

---

# Reporting Status Semantics

Phase 2A reports use a shared status model:

- `PASS`: run completed with zero warnings and zero failures.
- `WARN`: run completed with usable output, one or more warnings, and zero failures.
- `FAIL`: one or more failures make the output untrustworthy.

Reports also include `healthy`: `true` for `PASS` and `WARN`, `false` for `FAIL`.
