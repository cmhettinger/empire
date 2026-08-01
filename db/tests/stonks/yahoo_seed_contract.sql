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

CREATE OR REPLACE FUNCTION pg_temp.expect_failure(
    statement TEXT,
    expected_state TEXT,
    expected_constraint TEXT,
    label TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $function$
DECLARE
    actual_state TEXT;
    actual_constraint TEXT;
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        actual_state := SQLSTATE;
        GET STACKED DIAGNOSTICS actual_constraint = CONSTRAINT_NAME;

        IF actual_state <> expected_state THEN
            RAISE EXCEPTION
                '%: expected SQLSTATE %, got %',
                label,
                expected_state,
                actual_state;
        END IF;

        IF actual_constraint IS DISTINCT FROM expected_constraint THEN
            RAISE EXCEPTION
                '%: expected constraint %, got %',
                label,
                expected_constraint,
                actual_constraint;
        END IF;

        RETURN;
    END;

    RAISE EXCEPTION '%: statement unexpectedly succeeded', label;
END;
$function$;

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 84
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND status = 'ACTIVE'
    ),
    'Yahoo seed contains exactly 84 active XIDX listings after review'
);

SELECT pg_temp.assert_true(
    (
        SELECT count(DISTINCT ticker) = 93
           AND bool_and(ticker = upper(ticker))
           AND bool_and(ticker ~ '^[A-Z0-9]+$')
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
    ),
    'Yahoo seed uses unique stable Empire ticker codes'
);

SELECT pg_temp.assert_true(
    (
        SELECT count(DISTINCT metadata ->> 'YahooTicker') = 93
           AND bool_and(jsonb_typeof(metadata -> 'YahooTicker') = 'string')
           AND bool_and(metadata ->> 'YahooTicker' <> '')
           AND bool_and(
               metadata ->> 'YahooTicker'
               = btrim(metadata ->> 'YahooTicker')
           )
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
    ),
    'Yahoo seed retains one unique non-blank YahooTicker per listing'
);

SELECT pg_temp.assert_true(
    NOT EXISTS (
        SELECT 1
        FROM provider_listing AS listing
        LEFT JOIN ohlcv_session_policy AS policy
          USING (session_policy_code)
        WHERE listing.provider_code = 'YAHOO'
          AND listing.market = 'XIDX'
          AND (
              listing.session_policy_code IS NULL
              OR policy.session_policy_code IS NULL
          )
    ),
    'every Yahoo listing resolves an explicit session policy'
);

SELECT pg_temp.assert_true(
    NOT EXISTS (
        SELECT 1
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND instrument_type_code NOT IN (
              'YIELD_INDEX',
              'EQUITY_INDEX',
              'COMMODITY_INDEX',
              'CURRENCY_INDEX',
              'VOLATILITY_INDEX',
              'CONTINUOUS_FUTURE_COMMODITY',
              'CONTINUOUS_FUTURE_EQUITY'
          )
    ),
    'Yahoo seed contains no ordinary equities'
);

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 56
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND instrument_type_code = 'EQUITY_INDEX'
    )
    AND (
        SELECT count(*) = 6
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND instrument_type_code = 'VOLATILITY_INDEX'
    )
    AND (
        SELECT count(*) = 3
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND instrument_type_code = 'YIELD_INDEX'
    )
    AND (
        SELECT count(*) = 2
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND instrument_type_code = 'COMMODITY_INDEX'
    )
    AND (
        SELECT count(*) = 1
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND instrument_type_code = 'CURRENCY_INDEX'
    )
    AND (
        SELECT count(*) = 4
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND instrument_type_code = 'CONTINUOUS_FUTURE_EQUITY'
    )
    AND (
        SELECT count(*) = 21
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND instrument_type_code = 'CONTINUOUS_FUTURE_COMMODITY'
    ),
    'Yahoo seed instrument-type distribution matches the reviewed universe'
);

SELECT pg_temp.assert_true(
    (
        SELECT metadata ->> 'YahooTicker' = '^GSPC'
           AND session_policy_code = 'YH_XNYS_CLOSE_90M'
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker = 'SPX'
    ),
    'representative U.S. cash index is mapped'
);

SELECT pg_temp.assert_true(
    (
        SELECT metadata ->> 'YahooTicker' = '^FTSE'
           AND session_policy_code = 'YH_XLON_CLOSE_120M'
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker = 'FTSE'
    )
    AND (
        SELECT metadata ->> 'YahooTicker' = '^N225'
           AND session_policy_code = 'YH_XTKS_CLOSE_180M'
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker = 'N225'
    ),
    'representative European and Asian cash indexes are mapped'
);

SELECT pg_temp.assert_true(
    (
        SELECT metadata ->> 'YahooTicker' = '^J200.JO'
           AND metadata #>> '{YahooSeedReview,disposition}'
               = 'CORRECTED_TICKER'
           AND status = 'ACTIVE'
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker = 'JTOPI'
    )
    AND (
        SELECT metadata ->> 'YahooTicker' = '^SET.BK'
           AND metadata #>> '{YahooSeedReview,disposition}'
               = 'CORRECTED_TICKER'
           AND status = 'ACTIVE'
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker = 'SET'
    ),
    'reviewed JTOPI and SET Yahoo symbols are active and corrected'
);

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 3
           AND bool_and(status = 'INACTIVE')
           AND bool_and(
               metadata #>> '{YahooSeedReview,disposition}' = 'UNSUPPORTED'
           )
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker IN ('IPSA', 'MSCIEM', 'RVX')
    ),
    'reviewed unavailable Yahoo seeds are explicitly inactive'
);

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 6
           AND bool_and(status = 'INACTIVE')
           AND bool_and(
               metadata #>> '{YahooSeedReview,disposition}'
                   = 'UNAVAILABLE_STALE_HISTORY'
           )
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker IN ('BCOM', 'CSI300', 'MOVE', 'PSEI', 'TASI', 'W5000')
    ),
    'reviewed stale Yahoo seeds are explicitly inactive'
);

SELECT pg_temp.assert_true(
    (
        SELECT policy.calendar_name IS NULL
           AND policy.session_date_rule = 'PROVIDER_LOCAL_DATE'
        FROM provider_listing AS listing
        JOIN ohlcv_session_policy AS policy USING (session_policy_code)
        WHERE listing.provider_code = 'YAHOO'
          AND listing.market = 'XIDX'
          AND listing.ticker = 'MSCIWORLD'
    ),
    'publisher-calculated global index fails safely to observed-only'
);

SELECT pg_temp.assert_true(
    (
        SELECT metadata ->> 'YahooTicker' = '^TNX'
           AND instrument_type_code = 'YIELD_INDEX'
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker = 'UST10Y'
    )
    AND (
        SELECT metadata ->> 'YahooTicker' = '^VIX'
           AND instrument_type_code = 'VOLATILITY_INDEX'
        FROM provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND ticker = 'VIX'
    ),
    'representative yield and volatility indexes are mapped'
);

SELECT pg_temp.assert_true(
    (
        SELECT metadata ->> 'YahooTicker' = 'DX-Y.NYB'
           AND policy.calendar_name IS NULL
           AND policy.eligibility_rule = 'LOCAL_CUTOFF'
        FROM provider_listing AS listing
        JOIN ohlcv_session_policy AS policy USING (session_policy_code)
        WHERE listing.provider_code = 'YAHOO'
          AND listing.market = 'XIDX'
          AND listing.ticker = 'DXY'
    ),
    'DXY uses its explicit observed-only provider cutoff'
);

SELECT pg_temp.assert_true(
    (
        SELECT metadata ->> 'YahooTicker' = 'ES=F'
           AND policy.calendar_name = 'CME_Equity'
           AND policy.session_date_rule = 'PROVIDER_DAILY_SETTLEMENT'
        FROM provider_listing AS listing
        JOIN ohlcv_session_policy AS policy USING (session_policy_code)
        WHERE listing.provider_code = 'YAHOO'
          AND listing.market = 'XIDX'
          AND listing.ticker = 'ES'
    )
    AND (
        SELECT metadata ->> 'YahooTicker' = 'CL=F'
           AND policy.calendar_name = 'CMEGlobex_EnergyAndMetals'
        FROM provider_listing AS listing
        JOIN ohlcv_session_policy AS policy USING (session_policy_code)
        WHERE listing.provider_code = 'YAHOO'
          AND listing.market = 'XIDX'
          AND listing.ticker = 'WTI'
    )
    AND (
        SELECT metadata ->> 'YahooTicker' = 'BZ=F'
           AND policy.calendar_name IS NULL
        FROM provider_listing AS listing
        JOIN ohlcv_session_policy AS policy USING (session_policy_code)
        WHERE listing.provider_code = 'YAHOO'
          AND listing.market = 'XIDX'
          AND listing.ticker = 'BRENT'
    ),
    'representative futures use settlement or safe observed-only policies'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO provider_listing (
            provider_code,
            market,
            ticker,
            name,
            instrument_type_code,
            session_policy_code
        )
        VALUES (
            'YAHOO',
            'XIDX',
            'YAHOOSEEDBADMETA',
            'Yahoo seed contract invalid metadata fixture',
            'EQUITY_INDEX',
            'YH_XNYS_CLOSE_90M'
        )
    $sql$,
    '23514',
    'ck_provider_listing_yahoo_metadata',
    'Yahoo listing requires a non-blank YahooTicker'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO provider_listing (
            provider_code,
            market,
            ticker,
            name,
            instrument_type_code,
            metadata,
            session_policy_code
        )
        VALUES (
            'YAHOO',
            'XIDX',
            'YAHOOSEEDDUPLICATE',
            'Yahoo seed contract duplicate metadata fixture',
            'EQUITY_INDEX',
            jsonb_build_object('YahooTicker', '^GSPC'),
            'YH_XNYS_CLOSE_90M'
        )
    $sql$,
    '23505',
    'uq_provider_listing_yahoo_ticker',
    'YahooTicker is unique across Yahoo provider listings'
);

ROLLBACK;

SELECT 'Yahoo seed contract tests passed' AS result;
