-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_listing_identity_security_exchange
--
-- Purpose:
--   Align listing identity with the security master model:
--   a listing is one security trading on one exchange, while ticker symbols
--   live in listing_symbol_history as time-varying attributes.
-- =====================================================================

SET search_path TO stonks, public;

DROP INDEX IF EXISTS ux_listing_active_lookup;

CREATE INDEX IF NOT EXISTS ix_listing_active_exchange_ticker
    ON listing (exchange_id, ticker_norm)
    WHERE valid_to IS NULL
      AND ticker_norm IS NOT NULL;

-- Keep this non-unique during the repair phase so pre-existing duplicates can
-- be surfaced by validation/conflict reports instead of blocking migration.
CREATE INDEX IF NOT EXISTS ix_listing_active_security_exchange
    ON listing (security_id, exchange_id)
    WHERE valid_to IS NULL
      AND status = 'ACTIVE';
