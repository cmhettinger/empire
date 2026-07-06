```mermaid
erDiagram
  identifier_type {
    VARCHAR id_type PK
    TEXT id_name
    VARCHAR applies_to
    TEXT description
    BOOL is_active
  }

  provider {
    VARCHAR provider_code PK
    TEXT provider_name
    VARCHAR provider_type
    TEXT website
    TEXT description
    BOOL is_active
  }

  security {
    UUID security_id PK
    UUID issuer_id
    VARCHAR instrument_type_code
    TEXT security_title
    TEXT share_class
    VARCHAR currency_code
    VARCHAR status
    DATE first_seen
    DATE last_seen
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
    VARCHAR identity_status
  }

  security_identifier {
    UUID security_identifier_id PK
    UUID security_id FK
    VARCHAR id_type FK
    TEXT id_value
    DATE valid_from
    DATE valid_to
    VARCHAR provider_code FK
    VARCHAR confidence_code
    TIMESTAMPTZ created_at
  }

  provider ||--o{ security_identifier : "fk_security_identifier_provider"
  security ||--o{ security_identifier : "fk_security_identifier_security"
  identifier_type ||--o{ security_identifier : "fk_security_identifier_type"
```
