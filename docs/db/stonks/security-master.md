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

---

## listing

Represents a security trading on a specific exchange.

Examples:

- AAPL on NASDAQ
- BRK.A on NYSE
- SPY on NYSE Arca

A listing belongs to one security and one exchange.

---

## listing_symbol_history

Stores historical ticker symbols.

Examples:

| Symbol | Start Date | End Date |
|----------|------------|-----------|
| GOOG | 2004 | 2015 |
| GOOGL | 2015 | NULL |

Used to preserve ticker changes without losing history.

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
