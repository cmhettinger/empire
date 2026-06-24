-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_add_sec_cboe_exchange_alias
--
-- Purpose:
--   Map the SEC raw CBOE exchange value to Empire's canonical Cboe BZX
--   exchange.
--
-- Notes:
--   - This migration adds an alias only; it does not create a new exchange.
--   - SEC company_tickers_exchange currently emits plain CBOE for Cboe
--     listed symbols that align with Empire's existing CBOEBZX venue.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- SEC / EDGAR Cboe exchange alias
-- ---------------------------------------------------------------------

INSERT INTO exchange_alias (
    exchange_id,
    provider_code,
    raw_name,
    normalized_name,
    is_active
)
SELECT e.exchange_id, 'SEC', 'CBOE', 'CBOEBZX', TRUE
FROM exchange e
WHERE e.exchange_code = 'CBOEBZX'
ON CONFLICT (provider_code, raw_name) DO UPDATE
SET
    exchange_id = EXCLUDED.exchange_id,
    normalized_name = EXCLUDED.normalized_name,
    is_active = TRUE;
