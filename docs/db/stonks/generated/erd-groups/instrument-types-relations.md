```mermaid
flowchart LR
  instrument_class["instrument_class"]
  instrument_type["instrument_type"]
  security["security"]

  instrument_class -->|fk_instrument_type_class| instrument_type
  instrument_type -->|fk_security_type| security
```
