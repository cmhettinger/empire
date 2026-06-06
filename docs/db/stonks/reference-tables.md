# Empire Security Master – Reference Data Refresh Strategy

## Purpose

This document defines the maintenance strategy for all reference-data tables used by the `empire-stonks-securities` security master.

The objective is to establish a clear policy for:

* Initial population
* Ongoing refresh requirements
* Manual maintenance expectations
* Authoritative data sources

These tables support historical SEC/EDGAR security-master reconstruction from approximately 1995-present.

---

# Reference Data Refresh Matrix

| Table                       | Authoritative Source                | Initial Population | Refresh Strategy                        | Manual Maintenance |
| --------------------------- | ----------------------------------- | ------------------ | --------------------------------------- | ------------------ |
| `iso3166_country`           | ISO 3166                            | Seeded             | Rare refresh when ISO publishes changes | No                 |
| `iso4217_currency`          | ISO 4217                            | Seeded             | Rare refresh when ISO publishes changes | No                 |
| `iso10383_mic`              | ISO 10383 MIC                       | Bulk import        | Monthly ISO refresh                     | No                 |
| `iso10383_mic_cat`          | ISO 10383 MIC Categories            | Seeded             | Refresh when ISO adds categories        | No                 |
| `provider`                  | Empire Internal                     | Seeded             | As new providers are introduced         | Yes                |
| `identifier_type`           | Empire Internal                     | Seeded             | As new identifier types are needed      | Yes                |
| `classification_system`     | Empire Internal                     | Seeded             | Rare                                    | Yes                |
| `classification_code` (SIC) | SEC SIC List                        | Seeded             | Rare SEC refresh                        | No                 |
| `instrument_class`          | Empire Internal                     | Seeded             | Rare                                    | Yes                |
| `instrument_type`           | Empire Internal                     | Seeded             | As new security types are discovered    | Yes                |
| `exchange`                  | Empire Internal                     | Seeded             | Rare                                    | Yes                |
| `exchange_alias`            | SEC filings and discovered mappings | Seeded             | Incremental additions during ingestion  | Yes                |
| `confidence_level`          | Empire Internal                     | Seeded             | Rare                                    | Yes                |

---

# Refresh Policy Details

## ISO 3166 Countries

Table:

```text
iso3166_country
```

Source:

```text
ISO 3166
```

Refresh Frequency:

```text
Rare
```

Notes:

* Country codes change infrequently.
* Refresh only when ISO publishes additions, removals, or renames.

---

## ISO 4217 Currencies

Table:

```text
iso4217_currency
```

Source:

```text
ISO 4217
```

Refresh Frequency:

```text
Rare
```

Notes:

* Currency changes are uncommon.
* Refresh when new currencies are introduced or codes are retired.

---

## ISO 10383 MIC

Table:

```text
iso10383_mic
```

Source:

```text
ISO 10383 Market Identifier Codes
```

Refresh Frequency:

```text
Monthly
```

Notes:

* This table should remain a faithful copy of the ISO source.
* Do not manually edit records.
* Refresh from the published ISO MIC file.

---

## ISO 10383 MIC Categories

Table:

```text
iso10383_mic_cat
```

Source:

```text
ISO 10383
```

Refresh Frequency:

```text
As Needed
```

Notes:

* Categories change rarely.
* Refresh only when ISO introduces new category codes.

---

## Provider Registry

Table:

```text
provider
```

Source:

```text
Empire Internal
```

Refresh Frequency:

```text
Manual
```

Examples:

```text
SEC
ISO
NASDAQ
NYSE
OTC_MARKETS
CENSUS
INTERNAL
MANUAL
```

---

## Identifier Types

Table:

```text
identifier_type
```

Source:

```text
Empire Internal
```

Refresh Frequency:

```text
Manual
```

Examples:

```text
CIK
CUSIP
ISIN
FIGI
LEI
SERIES_ID
CLASS_ID
```

New identifier types should only be added when required by a new provider or ingestion source.

---

## Classification Systems

Table:

```text
classification_system
```

Source:

```text
Empire Internal
```

Refresh Frequency:

```text
Rare
```

Current Systems:

```text
SIC
NAICS
GICS
ICB
SEC_FUND
INTERNAL
```

---

## Classification Codes

Table:

```text
classification_code
```

Primary Source:

```text
SEC SIC Code List
```

Refresh Frequency:

```text
Rare
```

Notes:

* SIC is currently the only populated classification system.
* Additional systems may be populated in the future.

---

## Instrument Classes

Table:

```text
instrument_class
```

Source:

```text
Empire Internal
```

Refresh Frequency:

```text
Rare
```

Current Classes:

```text
EQUITY
FUND
INDEX
DEBT
DERIVATIVE
OTHER
```

---

## Instrument Types

Table:

```text
instrument_type
```

Source:

```text
Empire Internal
```

Refresh Frequency:

```text
As Needed
```

Notes:

* New security structures may appear over time.
* Add new types when they provide meaningful classification value.

---

## Exchanges

Table:

```text
exchange
```

Source:

```text
Empire Internal
```

Refresh Frequency:

```text
Rare
```

Notes:

* Represents canonical listing venues used by Empire.
* Not intended to mirror the full ISO MIC universe.

---

## Exchange Aliases

Table:

```text
exchange_alias
```

Source:

```text
SEC filings and discovered mappings
```

Refresh Frequency:

```text
Ongoing
```

Notes:

* Expected to grow over time.
* New aliases should be added whenever ingestion encounters previously unseen exchange names.

Examples:

```text
AMEX
NYSE Amex
NYSE MKT
NASDAQ National Market
NASDAQ Global Select Market
Pink Sheets
OTCBB
```

---

## Confidence Levels

Table:

```text
confidence_level
```

Source:

```text
Empire Internal
```

Refresh Frequency:

```text
Rare
```

Current Values:

```text
MANUAL
HIGH
MEDIUM
LOW
TRACE
CONFLICT
```

Notes:

* Used for evidence scoring and conflict resolution.
* Values should remain stable to preserve historical consistency.

---

# Guiding Principle

Reference data should remain intentionally small, stable, and highly curated.

The security master should evolve primarily through:

* SEC filings
* ISO reference feeds
* Exchange normalization
* Identifier matching

rather than through frequent changes to lookup tables.

Reference tables should change slowly and only when they improve long-term historical reconstruction quality.
