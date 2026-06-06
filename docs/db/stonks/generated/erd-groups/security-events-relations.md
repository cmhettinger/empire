```mermaid
flowchart LR
  issuer["issuer"]
  listing["listing"]
  provider["provider"]
  security["security"]
  security_event["security_event"]

  security -->|fk_listing_security| listing
  issuer -->|fk_security_issuer| security
  issuer -->|fk_security_event_issuer| security_event
  listing -->|fk_security_event_listing| security_event
  provider -->|fk_security_event_provider| security_event
  security -->|fk_security_event_security| security_event
```
