```mermaid
flowchart LR
  issuer["issuer"]
  issuer_identifier["issuer_identifier"]
  issuer_name_history["issuer_name_history"]

  issuer -->|fk_issuer_identifier_issuer| issuer_identifier
  issuer -->|fk_issuer_name_issuer| issuer_name_history
```
