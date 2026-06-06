```mermaid
flowchart LR
  identifier_type["identifier_type"]
  provider["provider"]
  security["security"]
  security_identifier["security_identifier"]

  provider -->|fk_security_identifier_provider| security_identifier
  security -->|fk_security_identifier_security| security_identifier
  identifier_type -->|fk_security_identifier_type| security_identifier
```
