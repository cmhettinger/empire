-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_listing_active_security_exchange_guard
--
-- Purpose:
--   Enforce the listing identity invariant introduced by
--   V2026.06.21.0001: one active listing per security on an exchange.
--   Historical/closed listings remain allowed.
-- =====================================================================

SET search_path TO stonks, public;

DO $$
DECLARE
    duplicate_count integer;
BEGIN
    SELECT COUNT(*)
    INTO duplicate_count
    FROM (
        SELECT security_id, exchange_id
        FROM listing
        WHERE valid_to IS NULL
          AND status = 'ACTIVE'
        GROUP BY security_id, exchange_id
        HAVING COUNT(*) > 1
    ) duplicates;

    IF duplicate_count > 0 THEN
        RAISE EXCEPTION
            'Cannot create ux_listing_one_active_per_security_exchange: % duplicate active security/exchange listing group(s) exist.',
            duplicate_count
            USING HINT = 'Run the stonks securities validation/conflict reports and close or merge duplicate active listing rows first.';
    END IF;
END $$;

DROP INDEX IF EXISTS ix_listing_active_security_exchange;

CREATE UNIQUE INDEX IF NOT EXISTS ux_listing_one_active_per_security_exchange
    ON listing (security_id, exchange_id)
    WHERE valid_to IS NULL
      AND status = 'ACTIVE';
