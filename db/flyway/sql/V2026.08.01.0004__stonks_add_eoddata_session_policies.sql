-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_add_eoddata_session_policies
--
-- Purpose:
--   Persist the reviewed EODData exchange session policies and attach them
--   to existing dynamically discovered provider listings.
-- =====================================================================

SET search_path TO stonks, public;

INSERT INTO ohlcv_session_policy (
    session_policy_code,
    calendar_name,
    timezone_name,
    eligibility_rule,
    cutoff_local_time,
    availability_delay_minutes,
    session_date_rule,
    description
)
VALUES
    (
        'ED_XNYS_1900_60M',
        'XNYS',
        'America/New_York',
        'LOCAL_CUTOFF',
        TIME '19:00',
        60,
        'PROVIDER_LOCAL_DATE',
        'EODData NYSE and AMEX after the 7 p.m. correction cutoff'
    ),
    (
        'ED_XNAS_1900_60M',
        'NASDAQ',
        'America/New_York',
        'LOCAL_CUTOFF',
        TIME '19:00',
        60,
        'PROVIDER_LOCAL_DATE',
        'EODData Nasdaq after the 7 p.m. correction cutoff'
    )
ON CONFLICT (session_policy_code) DO UPDATE
SET
    calendar_name              = EXCLUDED.calendar_name,
    timezone_name              = EXCLUDED.timezone_name,
    eligibility_rule           = EXCLUDED.eligibility_rule,
    cutoff_local_time          = EXCLUDED.cutoff_local_time,
    availability_delay_minutes = EXCLUDED.availability_delay_minutes,
    session_date_rule          = EXCLUDED.session_date_rule,
    description                = EXCLUDED.description;

UPDATE provider_listing
SET
    session_policy_code = CASE market
        WHEN 'NASDAQ' THEN 'ED_XNAS_1900_60M'
        ELSE 'ED_XNYS_1900_60M'
    END,
    updated_at = now()
WHERE provider_code = 'EODDATA'
  AND market IN ('NYSE', 'NASDAQ', 'AMEX')
  AND session_policy_code IS DISTINCT FROM CASE market
      WHEN 'NASDAQ' THEN 'ED_XNAS_1900_60M'
      ELSE 'ED_XNYS_1900_60M'
  END;
