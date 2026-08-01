-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_remediate_yahoo_unusable_seed_mappings
--
-- Purpose:
--   Correct two Yahoo Chart symbols that resolve to the wrong/unusable
--   series and deactivate three reviewed seeds for which Yahoo Chart does
--   not provide usable daily history. Preserve the provider evidence and
--   disposition in provider_listing.metadata.
-- =====================================================================

SET search_path TO stonks, public;

UPDATE provider_listing
SET
    metadata = coalesce(metadata, '{}'::jsonb)
        || jsonb_build_object(
            'YahooTicker', '^J200.JO',
            'YahooSeedReview', jsonb_build_object(
                'reviewed_on', '2026-08-01',
                'disposition', 'CORRECTED_TICKER',
                'previous_yahoo_ticker', '^JA0R.JO',
                'evidence', 'Yahoo Chart daily history resolves as Top 40 Index'
            )
        ),
    status = 'ACTIVE',
    updated_at = now()
WHERE provider_code = 'YAHOO'
  AND market = 'XIDX'
  AND ticker = 'JTOPI';

UPDATE provider_listing
SET
    metadata = coalesce(metadata, '{}'::jsonb)
        || jsonb_build_object(
            'YahooTicker', '^SET.BK',
            'YahooSeedReview', jsonb_build_object(
                'reviewed_on', '2026-08-01',
                'disposition', 'CORRECTED_TICKER',
                'previous_yahoo_ticker', '^SET',
                'evidence', 'Yahoo Chart daily history resolves as SET_SET Index'
            )
        ),
    status = 'ACTIVE',
    updated_at = now()
WHERE provider_code = 'YAHOO'
  AND market = 'XIDX'
  AND ticker = 'SET';

UPDATE provider_listing
SET
    status = 'INACTIVE',
    metadata = coalesce(metadata, '{}'::jsonb)
        || jsonb_build_object(
            'YahooSeedReview', jsonb_build_object(
                'reviewed_on', '2026-08-01',
                'disposition', 'UNSUPPORTED',
                'evidence', CASE ticker
                    WHEN 'RVX' THEN 'Yahoo Chart returns HTTP 404'
                    ELSE 'Yahoo Chart returns a valid envelope without daily history'
                END
            )
        ),
    updated_at = now()
WHERE provider_code = 'YAHOO'
  AND market = 'XIDX'
  AND ticker IN ('IPSA', 'MSCIEM', 'RVX');

DO $migration$
BEGIN
    IF (
        SELECT count(*)
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND status = 'ACTIVE'
    ) <> 90 THEN
        RAISE EXCEPTION 'expected 90 active Yahoo XIDX listings after remediation';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker IN ('JTOPI', 'SET')
          AND (
              status <> 'ACTIVE'
              OR metadata ->> 'YahooTicker' IS DISTINCT FROM CASE ticker
                  WHEN 'JTOPI' THEN '^J200.JO'
                  WHEN 'SET' THEN '^SET.BK'
              END
              OR metadata #>> '{YahooSeedReview,disposition}'
                  IS DISTINCT FROM 'CORRECTED_TICKER'
          )
    ) THEN
        RAISE EXCEPTION 'Yahoo corrected seed mappings did not converge';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker IN ('IPSA', 'MSCIEM', 'RVX')
          AND (
              status <> 'INACTIVE'
              OR metadata #>> '{YahooSeedReview,disposition}'
                  IS DISTINCT FROM 'UNSUPPORTED'
          )
    ) THEN
        RAISE EXCEPTION 'Yahoo unsupported seed dispositions did not converge';
    END IF;
END;
$migration$;
