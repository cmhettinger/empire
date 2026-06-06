```mermaid
erDiagram
  identifier_type {
    VARCHAR id_type PK
    TEXT id_name
    VARCHAR applies_to
    TEXT description
    BOOL is_active
  }

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

  issuer_identifier {
    UUID issuer_identifier_id PK
    UUID issuer_id FK
    VARCHAR id_type FK
    TEXT id_value
    DATE valid_from
    DATE valid_to
    VARCHAR provider_code FK
    VARCHAR confidence_code
    TIMESTAMPTZ created_at
  }

  issuer_name_history {
    UUID issuer_name_id PK
    UUID issuer_id FK
    TEXT name
    DATE valid_from
    DATE valid_to
    VARCHAR provider_code FK
    VARCHAR confidence_code
    TIMESTAMPTZ created_at
  }

  provider {
    VARCHAR provider_code PK
    TEXT provider_name
    VARCHAR provider_type
    TEXT website
    TEXT description
    BOOL is_active
  }

  issuer ||--o{ issuer_identifier : "fk_issuer_identifier_issuer"
  provider ||--o{ issuer_identifier : "fk_issuer_identifier_provider"
  identifier_type ||--o{ issuer_identifier : "fk_issuer_identifier_type"
  issuer ||--o{ issuer_name_history : "fk_issuer_name_issuer"
  provider ||--o{ issuer_name_history : "fk_issuer_name_provider"
```
