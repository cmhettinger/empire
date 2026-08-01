-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_deactivate_stale_yahoo_set
--
-- Purpose:
--   Preserve the corrected Yahoo SET identity and accepted history while
--   excluding the series after targeted verification proved that the exact
--   Chart symbol stopped supplying complete daily OHLC after 2026-07-17.
-- =====================================================================

SET search_path TO stonks, public;

UPDATE provider_listing AS listing
SET
    status = 'INACTIVE',
    metadata = coalesce(listing.metadata, '{}'::jsonb)
        || jsonb_build_object(
            'YahooSeedReview', jsonb_build_object(
                'reviewed_on', '2026-08-01',
                'disposition', 'UNAVAILABLE_STALE_HISTORY',
                'previous_disposition',
                    listing.metadata #>> '{YahooSeedReview,disposition}',
                'last_complete_provider_date', DATE '2026-07-17',
                'evidence',
                    'Corrected ^SET.BK Chart symbol returns no completed OHLC after the last complete date',
                'reactivation_condition',
                    'Exact symbol resumes continuous completed daily history'
            )
        ),
    updated_at = now()
WHERE listing.provider_code = 'YAHOO'
  AND listing.market = 'XIDX'
  AND listing.ticker = 'SET';

DO $migration$
BEGIN
    IF (
        SELECT count(*)
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND status = 'ACTIVE'
    ) <> 83 THEN
        RAISE EXCEPTION 'expected 83 active Yahoo XIDX listings after SET verification';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker = 'SET'
          AND status = 'INACTIVE'
          AND metadata ->> 'YahooTicker' = '^SET.BK'
          AND metadata #>> '{YahooSeedReview,disposition}'
              = 'UNAVAILABLE_STALE_HISTORY'
          AND metadata #>> '{YahooSeedReview,previous_disposition}'
              = 'CORRECTED_TICKER'
          AND metadata #>> '{YahooSeedReview,last_complete_provider_date}'
              = '2026-07-17'
    ) THEN
        RAISE EXCEPTION 'Yahoo SET stale disposition did not converge';
    END IF;
END;
$migration$;
