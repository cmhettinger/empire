-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_listing_symbol_active_guard
--
-- Purpose:
--   Prevent a listing from silently accumulating multiple active/current
--   symbols when existing data is already clean. If existing duplicates are
--   present, validation and conflict reports identify the affected listings
--   without performing unsafe automatic cleanup.
-- =====================================================================

SET search_path TO stonks, public;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM listing_symbol_history
        WHERE valid_to IS NULL
        GROUP BY listing_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE NOTICE 'Skipping ux_listing_symbol_one_active_per_listing because duplicate active symbols already exist; run validation/conflict reports for diagnostics.';
    ELSE
        EXECUTE '
            CREATE UNIQUE INDEX IF NOT EXISTS ux_listing_symbol_one_active_per_listing
            ON listing_symbol_history (listing_id)
            WHERE valid_to IS NULL
        ';
    END IF;
END $$;
