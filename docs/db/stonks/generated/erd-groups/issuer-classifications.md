```mermaid
erDiagram
  classification_code {
    UUID class_code_id PK
    VARCHAR class_system FK
    VARCHAR code
    TEXT label
    TEXT description
    BOOL is_active
  }

  classification_system {
    VARCHAR class_system PK
    TEXT system_name
    VARCHAR provider_code FK
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

  issuer_classification {
    UUID issuer_class_id PK
    UUID issuer_id FK
    UUID class_code_id FK
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

  classification_system ||--o{ classification_code : "fk_classification_code_system"
  provider ||--o{ classification_system : "fk_classification_system_provider"
  classification_code ||--o{ issuer_classification : "fk_issuer_class_code"
  issuer ||--o{ issuer_classification : "fk_issuer_class_issuer"
  provider ||--o{ issuer_classification : "fk_issuer_class_provider"
```
