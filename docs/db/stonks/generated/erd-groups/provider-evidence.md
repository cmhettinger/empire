```mermaid
erDiagram
  issuer {
    UUID issuer_id PK
    VARCHAR cik
    VARCHAR issuer_type
    TEXT current_name
    VARCHAR country_alpha2
    VARCHAR sic_code
    VARCHAR status
    DATE first_seen
    DATE last_seen
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
  }

  listing {
    UUID listing_id PK
    UUID security_id FK
    UUID exchange_id
    TEXT current_ticker
    TEXT ticker_norm
    VARCHAR currency_code
    BOOL is_primary
    VARCHAR status
    DATE valid_from
    DATE valid_to
    DATE first_seen
    DATE last_seen
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
  }

  provider {
    VARCHAR provider_code PK
    TEXT provider_name
    VARCHAR provider_type
    TEXT website
    TEXT description
    BOOL is_active
  }

  provider_evidence {
    UUID provider_evidence_id PK
    UUID provider_observation_id FK
    UUID issuer_id FK
    UUID security_id FK
    UUID listing_id FK
    UUID event_id FK
    VARCHAR evidence_role
    TEXT notes
    TIMESTAMPTZ created_at
  }

  provider_observation {
    UUID provider_observation_id PK
    VARCHAR provider_code FK
    DATE provider_date
    TIMESTAMPTZ observed_at
    TEXT accession_no
    VARCHAR form_type
    DATE filing_date
    UUID object_id
    TEXT object_key
    TEXT source_url
    TEXT raw_key
    JSONB summary_json
    TIMESTAMPTZ created_at
    UUID source_snapshot_id FK
  }

  provider_source_snapshot {
    UUID source_snapshot_id PK
    VARCHAR provider_code FK
    VARCHAR source_code
    CHAR content_sha256
    UUID first_seen_object_id
    UUID first_seen_run_id
    VARCHAR parser_version
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
  }

  provider_source_snapshot_object {
    UUID source_snapshot_object_id PK
    UUID source_snapshot_id FK
    UUID object_id
    TIMESTAMPTZ created_at
  }

  security {
    UUID security_id PK
    UUID issuer_id FK
    VARCHAR instrument_type_code
    TEXT security_title
    TEXT share_class
    VARCHAR currency_code
    VARCHAR status
    DATE first_seen
    DATE last_seen
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
  }

  security_event {
    UUID event_id PK
    UUID issuer_id FK
    UUID security_id FK
    UUID listing_id FK
    VARCHAR event_type
    DATE event_date
    VARCHAR provider_code FK
    VARCHAR confidence_code
    TEXT description
    JSONB details_json
    TIMESTAMPTZ created_at
  }

  security ||--o{ listing : "fk_listing_security"
  security_event ||--o{ provider_evidence : "fk_provider_evidence_event"
  issuer ||--o{ provider_evidence : "fk_provider_evidence_issuer"
  listing ||--o{ provider_evidence : "fk_provider_evidence_listing"
  provider_observation ||--o{ provider_evidence : "fk_provider_evidence_observation"
  security ||--o{ provider_evidence : "fk_provider_evidence_security"
  provider ||--o{ provider_observation : "fk_provider_observation_provider"
  provider_source_snapshot ||--o{ provider_observation : "provider_observation_source_snapshot_id_fkey"
  provider ||--o{ provider_source_snapshot : "provider_source_snapshot_provider_code_fkey"
  provider_source_snapshot ||--o{ provider_source_snapshot_object : "provider_source_snapshot_object_source_snapshot_id_fkey"
  issuer ||--o{ security : "fk_security_issuer"
  issuer ||--o{ security_event : "fk_security_event_issuer"
  listing ||--o{ security_event : "fk_security_event_listing"
  provider ||--o{ security_event : "fk_security_event_provider"
  security ||--o{ security_event : "fk_security_event_security"
```
