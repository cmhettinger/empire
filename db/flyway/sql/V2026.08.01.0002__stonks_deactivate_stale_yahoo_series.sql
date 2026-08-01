-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_deactivate_stale_yahoo_series
--
-- Purpose:
--   Preserve six reviewed Yahoo benchmark identities and their historical
--   bars while excluding series whose Chart responses stopped supplying
--   complete daily OHLC. Do not hide eligible gaps with calendar changes or
--   substitute a proxy instrument.
-- =====================================================================

SET search_path TO stonks, public;

WITH stale_series (ticker, last_complete_provider_date) AS (
    VALUES
        ('BCOM', DATE '2026-07-17'),
        ('CSI300', DATE '2026-07-17'),
        ('MOVE', DATE '2026-07-17'),
        ('PSEI', DATE '2026-07-17'),
        ('TASI', DATE '2026-07-16'),
        ('W5000', DATE '2026-07-17')
)
UPDATE provider_listing AS listing
SET
    status = 'INACTIVE',
    metadata = coalesce(listing.metadata, '{}'::jsonb)
        || jsonb_build_object(
            'YahooSeedReview', jsonb_build_object(
                'reviewed_on', '2026-08-01',
                'disposition', 'UNAVAILABLE_STALE_HISTORY',
                'last_complete_provider_date',
                    stale.last_complete_provider_date,
                'evidence',
                    'Yahoo Chart returns empty OHLC placeholders after the last complete date',
                'reactivation_condition',
                    'Exact symbol resumes continuous completed daily history'
            )
        ),
    updated_at = now()
FROM stale_series AS stale
WHERE listing.provider_code = 'YAHOO'
  AND listing.market = 'XIDX'
  AND listing.ticker = stale.ticker;

DO $migration$
BEGIN
    IF (
        SELECT count(*)
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND status = 'ACTIVE'
    ) <> 84 THEN
        RAISE EXCEPTION 'expected 84 active Yahoo XIDX listings after stale review';
    END IF;

    IF (
        SELECT count(*)
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker IN ('BCOM', 'CSI300', 'MOVE', 'PSEI', 'TASI', 'W5000')
          AND status = 'INACTIVE'
          AND metadata #>> '{YahooSeedReview,disposition}'
              = 'UNAVAILABLE_STALE_HISTORY'
          AND metadata #>> '{YahooSeedReview,last_complete_provider_date}'
              = CASE ticker
                  WHEN 'TASI' THEN '2026-07-16'
                  ELSE '2026-07-17'
              END
    ) <> 6 THEN
        RAISE EXCEPTION 'Yahoo stale seed dispositions did not converge';
    END IF;
END;
$migration$;
