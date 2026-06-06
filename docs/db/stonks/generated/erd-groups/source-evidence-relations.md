```mermaid
flowchart LR
  issuer["issuer"]
  listing["listing"]
  security["security"]
  security_event["security_event"]
  source_evidence["source_evidence"]
  source_observation["source_observation"]

  security -->|fk_listing_security| listing
  issuer -->|fk_security_issuer| security
  issuer -->|fk_security_event_issuer| security_event
  listing -->|fk_security_event_listing| security_event
  security -->|fk_security_event_security| security_event
  security_event -->|fk_source_evidence_event| source_evidence
  issuer -->|fk_source_evidence_issuer| source_evidence
  listing -->|fk_source_evidence_listing| source_evidence
  source_observation -->|fk_source_evidence_obs| source_evidence
  security -->|fk_source_evidence_security| source_evidence
```
