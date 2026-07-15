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

        IF expected_constraint IS NOT NULL
           AND actual_constraint IS DISTINCT FROM expected_constraint THEN
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

INSERT INTO provider (
    provider_code,
    provider_name,
    provider_type,
    description
)
VALUES (
    'OHLCV_TEST',
    'OHLCV Schema Contract Test',
    'DATA_SOURCE',
    'Transaction-scoped schema contract fixture'
);

INSERT INTO instrument_class (
    class_code,
    class_name,
    description
)
VALUES (
    'OHLCV_TEST',
    'OHLCV Schema Contract Test',
    'Transaction-scoped schema contract fixture'
);

INSERT INTO instrument_type (
    type_code,
    class_code,
    type_name,
    description
)
VALUES (
    'OHLCV_TEST',
    'OHLCV_TEST',
    'OHLCV Schema Contract Test',
    'Transaction-scoped schema contract fixture'
);

-- Exact, case-sensitive provider-series identity and default instrument type.
INSERT INTO provider_listing (
    provider_code,
    market,
    ticker,
    first_seen,
    last_seen
)
VALUES (
    'OHLCV_TEST',
    'NYSE',
    'CaseTest',
    DATE '2024-01-02',
    DATE '2024-01-03'
);

INSERT INTO provider_listing (provider_code, market, ticker)
VALUES ('OHLCV_TEST', 'NYSE', 'casetest');

INSERT INTO provider_listing (provider_code, market, ticker)
VALUES ('OHLCV_TEST', 'nyse', 'CaseTest');

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 3
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
    ),
    'case variants remain distinct provider listings'
);

SELECT pg_temp.assert_true(
    (
        SELECT instrument_type_code = 'UNKNOWN'
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
          AND market = 'NYSE'
          AND ticker = 'CaseTest'
    ),
    'provider listing defaults instrument type to UNKNOWN'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO provider_listing (provider_code, market, ticker)
        VALUES ('OHLCV_TEST', 'NYSE', 'CaseTest')
    $sql$,
    '23505',
    'uq_provider_listing_identity',
    'exact provider listing identity is unique'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO provider_listing (provider_code, market, ticker)
        VALUES ('MISSING_PROVIDER', 'NYSE', 'MISSING')
    $sql$,
    '23503',
    'fk_provider_listing_provider',
    'provider listing requires a provider'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO provider_listing (
            provider_code,
            market,
            ticker,
            instrument_type_code
        )
        VALUES ('OHLCV_TEST', 'NYSE', 'BAD_TYPE', 'MISSING_TYPE')
    $sql$,
    '23503',
    'fk_provider_listing_instrument_type',
    'provider listing requires an instrument type'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO provider_listing (provider_code, market, ticker)
        VALUES ('OHLCV_TEST', ' NYSE', 'BAD_MARKET')
    $sql$,
    '23514',
    'ck_provider_listing_market',
    'provider market rejects surrounding spaces'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO provider_listing (provider_code, market, ticker)
        VALUES ('OHLCV_TEST', 'NYSE', 'BAD_TICKER ')
    $sql$,
    '23514',
    'ck_provider_listing_ticker',
    'provider ticker rejects surrounding spaces'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO provider_listing (
            provider_code,
            market,
            ticker,
            first_seen
        )
        VALUES ('OHLCV_TEST', 'NYSE', 'ONE_DATE', DATE '2024-01-02')
    $sql$,
    '23514',
    'ck_provider_listing_seen_dates',
    'coverage dates must be populated together'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO provider_listing (
            provider_code,
            market,
            ticker,
            first_seen,
            last_seen
        )
        VALUES (
            'OHLCV_TEST',
            'NYSE',
            'REVERSED_DATES',
            DATE '2024-01-03',
            DATE '2024-01-02'
        )
    $sql$,
    '23514',
    'ck_provider_listing_seen_dates',
    'coverage dates reject a reversed range'
);

UPDATE provider_listing
SET instrument_type_code = 'OHLCV_TEST'
WHERE provider_code = 'OHLCV_TEST'
  AND market = 'NYSE'
  AND ticker = 'CaseTest';

-- A valid daily bar accepts nullable prior-close-derived fields.
INSERT INTO ohlcv_daily (
    provider_listing_id,
    trading_date,
    open,
    high,
    low,
    close,
    volume,
    change,
    changepct,
    typ,
    hl_range,
    oc_range
)
SELECT
    provider_listing_id,
    DATE '2024-01-02',
    10.0000000000,
    12.0000000000,
    9.0000000000,
    11.0000000000,
    NULL,
    NULL,
    NULL,
    10.66666667,
    3.00000000,
    1.00000000
FROM provider_listing
WHERE provider_code = 'OHLCV_TEST'
  AND market = 'NYSE'
  AND ticker = 'CaseTest';

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 1
        FROM ohlcv_daily d
        JOIN provider_listing pl USING (provider_listing_id)
        WHERE pl.provider_code = 'OHLCV_TEST'
          AND pl.market = 'NYSE'
          AND pl.ticker = 'CaseTest'
          AND d.trading_date = DATE '2024-01-02'
          AND d.volume IS NULL
          AND d.change IS NULL
          AND d.changepct IS NULL
    ),
    'valid first daily bar is stored'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily (
            provider_listing_id,
            trading_date,
            open,
            high,
            low,
            close,
            typ,
            hl_range,
            oc_range
        )
        SELECT
            provider_listing_id,
            DATE '2024-01-02',
            10,
            12,
            9,
            11,
            10.66666667,
            3,
            1
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
          AND market = 'NYSE'
          AND ticker = 'CaseTest'
    $sql$,
    '23505',
    'pk_ohlcv_daily',
    'daily bar composite primary key is unique'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily (
            provider_listing_id,
            trading_date,
            open,
            high,
            low,
            close,
            typ,
            hl_range,
            oc_range
        )
        VALUES (
            gen_random_uuid(),
            DATE '2024-02-01',
            10,
            12,
            9,
            11,
            10.66666667,
            3,
            1
        )
    $sql$,
    '23503',
    'fk_ohlcv_daily_provider_listing',
    'daily bar requires a provider listing'
);

-- Structural OHLC and volume constraints.
SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily
            (provider_listing_id, trading_date, open, high, low, close,
             typ, hl_range, oc_range)
        SELECT provider_listing_id, DATE '2024-02-02', 9, 8, 10, 9,
               9, -2, 0
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
          AND market = 'NYSE'
          AND ticker = 'CaseTest'
    $sql$,
    '23514',
    NULL,
    'daily bar rejects high below low'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily
            (provider_listing_id, trading_date, open, high, low, close,
             typ, hl_range, oc_range)
        SELECT provider_listing_id, DATE '2024-02-03', 11, 10, 8, 9,
               9, 2, -2
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
          AND market = 'NYSE'
          AND ticker = 'CaseTest'
    $sql$,
    '23514',
    'ck_ohlcv_daily_high_bounds',
    'daily bar rejects high below open'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily
            (provider_listing_id, trading_date, open, high, low, close,
             typ, hl_range, oc_range)
        SELECT provider_listing_id, DATE '2024-02-04', 9, 12, 10, 11,
               11, 2, 2
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
          AND market = 'NYSE'
          AND ticker = 'CaseTest'
    $sql$,
    '23514',
    'ck_ohlcv_daily_low_bounds',
    'daily bar rejects low above open'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily
            (provider_listing_id, trading_date, open, high, low, close, volume,
             typ, hl_range, oc_range)
        SELECT provider_listing_id, DATE '2024-02-05', 10, 12, 9, 11, -1,
               10.66666667, 3, 1
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
          AND market = 'NYSE'
          AND ticker = 'CaseTest'
    $sql$,
    '23514',
    'ck_ohlcv_daily_volume_nonnegative',
    'daily bar rejects negative volume'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily
            (provider_listing_id, trading_date, open, high, low, close, change,
             typ, hl_range, oc_range)
        SELECT provider_listing_id, DATE '2024-02-06', 10, 12, 9, 11,
               'NaN'::numeric, 10.66666667, 3, 1
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
          AND market = 'NYSE'
          AND ticker = 'CaseTest'
    $sql$,
    '23514',
    'ck_ohlcv_daily_numeric_not_nan',
    'daily bar rejects NaN'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily
            (provider_listing_id, trading_date, open, high, low, close,
             change, changepct, typ, hl_range, oc_range)
        SELECT provider_listing_id, DATE '2024-02-07', 10, 12, 9, 11,
               NULL, 0.1, 10.66666667, 3, 1
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
          AND market = 'NYSE'
          AND ticker = 'CaseTest'
    $sql$,
    '23514',
    'ck_ohlcv_daily_changepct_requires_change',
    'daily bar rejects changepct without change'
);

-- Row-local persisted formulas.
SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily
            (provider_listing_id, trading_date, open, high, low, close,
             typ, hl_range, oc_range)
        SELECT provider_listing_id, DATE '2024-02-08', 10, 12, 9, 11,
               10, 3, 1
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
          AND market = 'NYSE'
          AND ticker = 'CaseTest'
    $sql$,
    '23514',
    'ck_ohlcv_daily_typ',
    'daily bar rejects incorrect typical price'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily
            (provider_listing_id, trading_date, open, high, low, close,
             typ, hl_range, oc_range)
        SELECT provider_listing_id, DATE '2024-02-09', 10, 12, 9, 11,
               10.66666667, 2, 1
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
          AND market = 'NYSE'
          AND ticker = 'CaseTest'
    $sql$,
    '23514',
    'ck_ohlcv_daily_hl_range',
    'daily bar rejects incorrect high-low range'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily
            (provider_listing_id, trading_date, open, high, low, close,
             typ, hl_range, oc_range)
        SELECT provider_listing_id, DATE '2024-02-10', 10, 12, 9, 11,
               10.66666667, 3, 2
        FROM provider_listing
        WHERE provider_code = 'OHLCV_TEST'
          AND market = 'NYSE'
          AND ticker = 'CaseTest'
    $sql$,
    '23514',
    'ck_ohlcv_daily_oc_range',
    'daily bar rejects incorrect open-close range'
);

-- Valid corrections update current values; invalid corrections remain blocked.
UPDATE ohlcv_daily d
SET
    open = 11,
    high = 13,
    low = 10,
    close = 12,
    volume = 100,
    change = 1,
    changepct = 0.09090909,
    typ = 11.66666667,
    hl_range = 3,
    oc_range = 1,
    updated_at = now()
FROM provider_listing pl
WHERE d.provider_listing_id = pl.provider_listing_id
  AND pl.provider_code = 'OHLCV_TEST'
  AND pl.market = 'NYSE'
  AND pl.ticker = 'CaseTest'
  AND d.trading_date = DATE '2024-01-02';

SELECT pg_temp.assert_true(
    (
        SELECT d.close = 12
           AND d.change = 1
           AND d.changepct = 0.09090909
        FROM ohlcv_daily d
        JOIN provider_listing pl USING (provider_listing_id)
        WHERE pl.provider_code = 'OHLCV_TEST'
          AND pl.market = 'NYSE'
          AND pl.ticker = 'CaseTest'
          AND d.trading_date = DATE '2024-01-02'
    ),
    'valid provider correction updates the current daily bar'
);

SELECT pg_temp.expect_failure(
    $sql$
        UPDATE ohlcv_daily d
        SET typ = 0
        FROM provider_listing pl
        WHERE d.provider_listing_id = pl.provider_listing_id
          AND pl.provider_code = 'OHLCV_TEST'
          AND pl.market = 'NYSE'
          AND pl.ticker = 'CaseTest'
          AND d.trading_date = DATE '2024-01-02'
    $sql$,
    '23514',
    'ck_ohlcv_daily_typ',
    'invalid derived correction is rejected'
);

-- Reference rows are restricted while provider listings use them.
SELECT pg_temp.expect_failure(
    $sql$DELETE FROM provider WHERE provider_code = 'OHLCV_TEST'$sql$,
    '23503',
    'fk_provider_listing_provider',
    'provider deletion is restricted'
);

SELECT pg_temp.expect_failure(
    $sql$DELETE FROM instrument_type WHERE type_code = 'OHLCV_TEST'$sql$,
    '23503',
    'fk_provider_listing_instrument_type',
    'instrument type deletion is restricted'
);

-- Deleting an owned provider series cascades to its bars.
CREATE TEMP TABLE ohlcv_test_deleted_listing AS
SELECT provider_listing_id
FROM provider_listing
WHERE provider_code = 'OHLCV_TEST'
  AND market = 'NYSE'
  AND ticker = 'CaseTest';

DELETE FROM provider_listing
WHERE provider_code = 'OHLCV_TEST'
  AND market = 'NYSE'
  AND ticker = 'CaseTest';

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 0
        FROM ohlcv_daily
        WHERE provider_listing_id = (
            SELECT provider_listing_id
            FROM ohlcv_test_deleted_listing
        )
    ),
    'provider listing deletion cascades to daily bars'
);

ROLLBACK;

SELECT 'OHLCV schema contract tests passed' AS result;
