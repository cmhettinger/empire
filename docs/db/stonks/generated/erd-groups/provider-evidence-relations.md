```mermaid
flowchart LR
  issuer["issuer"]
  listing["listing"]
  provider["provider"]
  provider_evidence["provider_evidence"]
  provider_observation["provider_observation"]
  provider_source_snapshot["provider_source_snapshot"]
  provider_source_snapshot_object["provider_source_snapshot_object"]
  security["security"]
  security_event["security_event"]
  security_reconciliation_evidence["security_reconciliation_evidence"]
  security_reconciliation_evidence_provider_evidence["security_reconciliation_evidence_provider_evidence"]
  security_reconciliation_evidence_source_snapshot["security_reconciliation_evidence_source_snapshot"]

  security -->|fk_listing_security| listing
  security_event -->|fk_provider_evidence_event| provider_evidence
  issuer -->|fk_provider_evidence_issuer| provider_evidence
  listing -->|fk_provider_evidence_listing| provider_evidence
  provider_observation -->|fk_provider_evidence_observation| provider_evidence
  security -->|fk_provider_evidence_security| provider_evidence
  provider -->|fk_provider_observation_provider| provider_observation
  provider_source_snapshot -->|provider_observation_source_snapshot_id_fkey| provider_observation
  provider -->|provider_source_snapshot_provider_code_fkey| provider_source_snapshot
  provider_source_snapshot -->|provider_source_snapshot_object_source_snapshot_id_fkey| provider_source_snapshot_object
  issuer -->|fk_security_issuer| security
  issuer -->|fk_security_event_issuer| security_event
  listing -->|fk_security_event_listing| security_event
  provider -->|fk_security_event_provider| security_event
  security -->|fk_security_event_security| security_event
  issuer -->|fk_sec_recon_evidence_issuer| security_reconciliation_evidence
  listing -->|fk_sec_recon_evidence_listing| security_reconciliation_evidence
  security -->|fk_sec_recon_evidence_security| security_reconciliation_evidence
  security_reconciliation_evidence -->|fk_sec_recon_evidence_provider_evidence| security_reconciliation_evidence_provider_evidence
  provider_evidence -->|fk_sec_recon_evidence_provider_source| security_reconciliation_evidence_provider_evidence
  security_reconciliation_evidence -->|fk_sec_recon_evidence_snapshot_evidence| security_reconciliation_evidence_source_snapshot
  provider_source_snapshot -->|fk_sec_recon_evidence_snapshot_source| security_reconciliation_evidence_source_snapshot
```
