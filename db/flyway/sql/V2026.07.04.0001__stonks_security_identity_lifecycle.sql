-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_security_identity_lifecycle
--
-- Purpose:
--   Add the minimal canonical lifecycle state for security identity
--   reconciliation. Existing SEC-bootstrapped securities are provisional by
--   contract; later reconciliation audit tables will explain dry-run
--   evaluations and applied promotions.
-- =====================================================================

SET search_path TO stonks, public;

ALTER TABLE security
    ADD COLUMN identity_status VARCHAR(24);

UPDATE security
SET identity_status = 'PROVISIONAL'
WHERE identity_status IS NULL;

ALTER TABLE security
    ALTER COLUMN identity_status SET DEFAULT 'PROVISIONAL',
    ALTER COLUMN identity_status SET NOT NULL,
    ADD CONSTRAINT ck_security_identity_status
        CHECK (identity_status IN (
            'PROVISIONAL',
            'CONFIRMED'
        ));

CREATE INDEX IF NOT EXISTS ix_security_identity_status
    ON security (identity_status);

CREATE INDEX IF NOT EXISTS ix_security_provisional_issuer
    ON security (issuer_id, last_seen DESC, security_id)
    WHERE identity_status = 'PROVISIONAL';
