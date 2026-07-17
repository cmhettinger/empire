-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_provider_listing_status_metadata
--
-- Purpose:
--   Allow provider-native series imports to be disabled manually and retain
--   optional provider-specific listing metadata.
-- =====================================================================

SET search_path TO stonks, public;

ALTER TABLE provider_listing
    ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    ADD COLUMN metadata JSONB NULL,
    ADD CONSTRAINT ck_provider_listing_status
        CHECK (status IN ('ACTIVE', 'INACTIVE'));
