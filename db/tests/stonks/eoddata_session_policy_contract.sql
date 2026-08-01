\set ON_ERROR_STOP on

BEGIN;

SET search_path TO stonks, public;

CREATE OR REPLACE FUNCTION pg_temp.assert_true(
    condition BOOLEAN,
    label TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $function$
BEGIN
    IF condition IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'assertion failed: %', label;
    END IF;
END;
$function$;

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 2
           AND bool_and(timezone_name = 'America/New_York')
           AND bool_and(eligibility_rule = 'LOCAL_CUTOFF')
           AND bool_and(cutoff_local_time = TIME '19:00')
           AND bool_and(availability_delay_minutes = 60)
           AND bool_and(session_date_rule = 'PROVIDER_LOCAL_DATE')
        FROM ohlcv_session_policy
        WHERE session_policy_code IN (
            'ED_XNYS_1900_60M',
            'ED_XNAS_1900_60M'
        )
    ),
    'EODData policy rows match the reviewed local cutoff contract'
);

SELECT pg_temp.assert_true(
    (
        SELECT calendar_name = 'XNYS'
        FROM ohlcv_session_policy
        WHERE session_policy_code = 'ED_XNYS_1900_60M'
    )
    AND (
        SELECT calendar_name = 'NASDAQ'
        FROM ohlcv_session_policy
        WHERE session_policy_code = 'ED_XNAS_1900_60M'
    ),
    'EODData policies retain exact supported calendar names'
);

SELECT pg_temp.assert_true(
    NOT EXISTS (
        SELECT 1
        FROM provider_listing
        WHERE provider_code = 'EODDATA'
          AND market IN ('NYSE', 'NASDAQ', 'AMEX')
          AND session_policy_code IS DISTINCT FROM CASE market
              WHEN 'NASDAQ' THEN 'ED_XNAS_1900_60M'
              ELSE 'ED_XNYS_1900_60M'
          END
    ),
    'existing configured EODData listings have exact policy assignments'
);

INSERT INTO provider_listing (
    provider_code,
    market,
    ticker,
    status,
    session_policy_code
)
VALUES
    (
        'EODDATA',
        'NYSE',
        'C92_ACTIVE_TEST',
        'ACTIVE',
        'ED_XNYS_1900_60M'
    ),
    (
        'EODDATA',
        'NASDAQ',
        'C92_INACTIVE_TEST',
        'INACTIVE',
        'ED_XNAS_1900_60M'
    );

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 2
           AND count(*) FILTER (WHERE status = 'INACTIVE') = 1
        FROM provider_listing
        WHERE ticker IN ('C92_ACTIVE_TEST', 'C92_INACTIVE_TEST')
          AND session_policy_code IS NOT NULL
    ),
    'active and inactive EODData listings retain explicit policies'
);

INSERT INTO provider_listing (
    provider_code,
    market,
    ticker,
    status
)
VALUES ('EODDATA', 'UNREVIEWED', 'C92_UNKNOWN_TEST', 'ACTIVE');

SELECT pg_temp.assert_true(
    (
        SELECT session_policy_code IS NULL
        FROM provider_listing
        WHERE provider_code = 'EODDATA'
          AND market = 'UNREVIEWED'
          AND ticker = 'C92_UNKNOWN_TEST'
    ),
    'database does not assign a fallback policy to an unknown market'
);

ROLLBACK;
