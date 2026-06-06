-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_security_master_naming_cleanup
--
-- Purpose:
--   Normalize security-master naming around provider-supplied data.
--
-- Notes:
--   - Preserve existing data by using table, column, constraint, and index
--     renames.
--   - "provider" means the organization supplying data.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Provider-backed code columns
-- ---------------------------------------------------------------------

ALTER TABLE exchange_alias
    RENAME COLUMN source_code TO provider_code;

ALTER TABLE exchange_alias
    RENAME CONSTRAINT ck_exchange_alias_source_upper TO ck_exchange_alias_provider_upper;

ALTER TABLE exchange_alias
    RENAME CONSTRAINT exchange_alias_source_code_not_null TO exchange_alias_provider_code_not_null;

ALTER TABLE exchange_alias
    RENAME CONSTRAINT uq_exchange_alias_source_raw TO uq_exchange_alias_provider_raw;

ALTER INDEX ix_exchange_alias_source
    RENAME TO ix_exchange_alias_provider;

ALTER TABLE issuer_identifier
    RENAME COLUMN source_code TO provider_code;

ALTER TABLE issuer_identifier
    RENAME CONSTRAINT ck_issuer_identifier_source_upper TO ck_issuer_identifier_provider_upper;

ALTER INDEX ix_issuer_identifier_source
    RENAME TO ix_issuer_identifier_provider;

ALTER TABLE issuer_name_history
    RENAME COLUMN source_code TO provider_code;

ALTER TABLE issuer_name_history
    RENAME CONSTRAINT ck_issuer_name_source_upper TO ck_issuer_name_provider_upper;

ALTER INDEX ix_issuer_name_history_source
    RENAME TO ix_issuer_name_history_provider;

ALTER TABLE security_identifier
    RENAME COLUMN source_code TO provider_code;

ALTER TABLE security_identifier
    RENAME CONSTRAINT ck_security_identifier_source_upper TO ck_security_identifier_provider_upper;

ALTER INDEX ix_security_identifier_source
    RENAME TO ix_security_identifier_provider;

ALTER TABLE listing_symbol_history
    RENAME COLUMN source_code TO provider_code;

ALTER TABLE listing_symbol_history
    RENAME CONSTRAINT ck_listing_symbol_source_upper TO ck_listing_symbol_provider_upper;

ALTER INDEX ix_listing_symbol_source
    RENAME TO ix_listing_symbol_provider;

ALTER TABLE issuer_classification
    RENAME COLUMN source_code TO provider_code;

ALTER TABLE issuer_classification
    RENAME CONSTRAINT ck_issuer_class_source_upper TO ck_issuer_class_provider_upper;

ALTER INDEX ix_issuer_class_source
    RENAME TO ix_issuer_class_provider;

ALTER TABLE security_event
    RENAME COLUMN source_code TO provider_code;

ALTER TABLE security_event
    RENAME CONSTRAINT ck_security_event_source_upper TO ck_security_event_provider_upper;

ALTER INDEX ix_security_event_source
    RENAME TO ix_security_event_provider;

-- ---------------------------------------------------------------------
-- Provider observations and evidence
-- ---------------------------------------------------------------------

ALTER TABLE source_observation
    RENAME COLUMN source_obs_id TO provider_observation_id;

ALTER TABLE source_observation
    RENAME COLUMN source_code TO provider_code;

ALTER TABLE source_observation
    RENAME COLUMN source_date TO provider_date;

ALTER TABLE source_observation
    RENAME CONSTRAINT source_observation_pkey TO provider_observation_pkey;

ALTER TABLE source_observation
    RENAME CONSTRAINT ck_source_obs_source_upper TO ck_provider_observation_provider_upper;

ALTER TABLE source_observation
    RENAME CONSTRAINT fk_source_obs_provider TO fk_provider_observation_provider;

ALTER TABLE source_observation
    RENAME CONSTRAINT source_observation_source_obs_id_not_null TO provider_observation_provider_observation_id_not_null;

ALTER TABLE source_observation
    RENAME CONSTRAINT source_observation_source_code_not_null TO provider_observation_provider_code_not_null;

ALTER TABLE source_observation
    RENAME CONSTRAINT source_observation_observed_at_not_null TO provider_observation_observed_at_not_null;

ALTER TABLE source_observation
    RENAME CONSTRAINT source_observation_created_at_not_null TO provider_observation_created_at_not_null;

ALTER TABLE source_observation
    RENAME TO provider_observation;

ALTER INDEX ux_source_obs_raw_key
    RENAME TO ux_provider_observation_raw_key;

ALTER INDEX ix_source_obs_source_date
    RENAME TO ix_provider_observation_provider_date;

ALTER INDEX ix_source_obs_accession
    RENAME TO ix_provider_observation_accession;

ALTER INDEX ix_source_obs_object
    RENAME TO ix_provider_observation_object;

ALTER TABLE source_evidence
    RENAME COLUMN source_evidence_id TO provider_evidence_id;

ALTER TABLE source_evidence
    RENAME COLUMN source_obs_id TO provider_observation_id;

ALTER TABLE source_evidence
    RENAME CONSTRAINT source_evidence_pkey TO provider_evidence_pkey;

ALTER TABLE source_evidence
    RENAME CONSTRAINT ck_source_evidence_role TO ck_provider_evidence_role;

ALTER TABLE source_evidence
    RENAME CONSTRAINT fk_source_evidence_obs TO fk_provider_evidence_observation;

ALTER TABLE source_evidence
    RENAME CONSTRAINT fk_source_evidence_issuer TO fk_provider_evidence_issuer;

ALTER TABLE source_evidence
    RENAME CONSTRAINT fk_source_evidence_security TO fk_provider_evidence_security;

ALTER TABLE source_evidence
    RENAME CONSTRAINT fk_source_evidence_listing TO fk_provider_evidence_listing;

ALTER TABLE source_evidence
    RENAME CONSTRAINT fk_source_evidence_event TO fk_provider_evidence_event;

ALTER TABLE source_evidence
    RENAME CONSTRAINT ck_source_evidence_target TO ck_provider_evidence_target;

ALTER TABLE source_evidence
    RENAME CONSTRAINT source_evidence_source_evidence_id_not_null TO provider_evidence_provider_evidence_id_not_null;

ALTER TABLE source_evidence
    RENAME CONSTRAINT source_evidence_source_obs_id_not_null TO provider_evidence_provider_observation_id_not_null;

ALTER TABLE source_evidence
    RENAME CONSTRAINT source_evidence_evidence_role_not_null TO provider_evidence_evidence_role_not_null;

ALTER TABLE source_evidence
    RENAME CONSTRAINT source_evidence_created_at_not_null TO provider_evidence_created_at_not_null;

ALTER TABLE source_evidence
    RENAME TO provider_evidence;

ALTER INDEX ix_source_evidence_obs
    RENAME TO ix_provider_evidence_observation;

ALTER INDEX ix_source_evidence_issuer
    RENAME TO ix_provider_evidence_issuer;

ALTER INDEX ix_source_evidence_security
    RENAME TO ix_provider_evidence_security;

ALTER INDEX ix_source_evidence_listing
    RENAME TO ix_provider_evidence_listing;

ALTER INDEX ix_source_evidence_event
    RENAME TO ix_provider_evidence_event;
