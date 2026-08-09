\set ON_ERROR_STOP on

BEGIN;

SET search_path TO stonks, public;

CREATE TEMP TABLE tech_indicators_expected_failure (
    label TEXT PRIMARY KEY
);

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
                '%: expected SQLSTATE %, got % (%)',
                label,
                expected_state,
                actual_state,
                SQLERRM;
        END IF;

        IF expected_constraint IS NOT NULL
           AND actual_constraint IS DISTINCT FROM expected_constraint THEN
            RAISE EXCEPTION
                '%: expected constraint %, got %',
                label,
                expected_constraint,
                actual_constraint;
        END IF;

        INSERT INTO tech_indicators_expected_failure VALUES (label);
        RETURN;
    END;

    RAISE EXCEPTION '%: statement unexpectedly succeeded', label;
END;
$function$;

CREATE OR REPLACE FUNCTION pg_temp.insert_warmup_payload(
    slot_name TEXT,
    listing_id UUID,
    fixture_date DATE,
    fixture_run_id UUID DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
AS $function$
DECLARE
    relation_name TEXT;
BEGIN
    IF slot_name NOT IN ('a', 'b') THEN
        RAISE EXCEPTION 'invalid fixture slot %', slot_name;
    END IF;

    relation_name := 'ohlcv_daily_tech_indicators_' || slot_name;
    EXECUTE format(
        $sql$
        INSERT INTO stonks.%I (
            provider_listing_id,
            trading_date,
            relative_strength_benchmark_provider_listing_id,
            history_observation_count,
            calculation_version,
            run_id,
            calculated_at,
            open,
            high,
            low,
            close,
            volume,
            consecutive_up_days,
            consecutive_down_days
        )
        SELECT
            source.provider_listing_id,
            source.trading_date,
            NULL,
            1,
            'TECH_INDICATORS_V1',
            $3,
            TIMESTAMPTZ '2024-02-01 00:00:00+00',
            source.open,
            source.high,
            source.low,
            source.close,
            source.volume,
            0,
            0
        FROM stonks.ohlcv_daily AS source
        WHERE source.provider_listing_id = $1
          AND source.trading_date = $2
        $sql$,
        relation_name
    ) USING listing_id, fixture_date, fixture_run_id;
END;
$function$;

-- Transaction-scoped provider, listing, source, Core, and report evidence.
INSERT INTO provider (
    provider_code,
    provider_name,
    provider_type,
    description
)
VALUES (
    'TECH_IND_TEST',
    'Tech Indicators Schema Contract Test',
    'DATA_SOURCE',
    'Transaction-scoped technical-indicators schema fixture'
);

INSERT INTO instrument_class (class_code, class_name, description)
VALUES (
    'TECH_IND_TEST',
    'Tech Indicators Schema Contract Test',
    'Transaction-scoped technical-indicators schema fixture'
);

INSERT INTO instrument_type (
    type_code,
    class_code,
    type_name,
    description
)
VALUES (
    'TECH_IND_TEST',
    'TECH_IND_TEST',
    'Tech Indicators Schema Contract Test',
    'Transaction-scoped technical-indicators schema fixture'
);

INSERT INTO provider_listing (
    provider_listing_id,
    provider_code,
    market,
    ticker,
    instrument_type_code,
    status
)
VALUES
    ('00000000-0000-4000-8000-00000000a001', 'TECH_IND_TEST', 'TEST', 'SUBJECT_A', 'TECH_IND_TEST', 'ACTIVE'),
    ('00000000-0000-4000-8000-00000000a002', 'TECH_IND_TEST', 'TEST', 'SUBJECT_B', 'TECH_IND_TEST', 'ACTIVE'),
    ('00000000-0000-4000-8000-00000000b001', 'TECH_IND_TEST', 'TEST', 'BENCHMARK', 'TECH_IND_TEST', 'ACTIVE'),
    ('00000000-0000-4000-8000-00000000c001', 'TECH_IND_TEST', 'TEST', 'SOURCE_CASCADE', 'TECH_IND_TEST', 'ACTIVE'),
    ('00000000-0000-4000-8000-00000000c002', 'TECH_IND_TEST', 'TEST', 'PROVIDER_CASCADE', 'TECH_IND_TEST', 'ACTIVE'),
    ('00000000-0000-4000-8000-00000000c003', 'TECH_IND_TEST', 'TEST', 'MEMBERSHIP_CASCADE', 'TECH_IND_TEST', 'ACTIVE'),
    ('00000000-0000-4000-8000-00000000c004', 'TECH_IND_TEST', 'TEST', 'NO_SOURCE', 'TECH_IND_TEST', 'ACTIVE');

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
    fixture.provider_listing_id,
    fixture.trading_date,
    fixture.open,
    fixture.high,
    fixture.low,
    fixture.close,
    fixture.volume,
    NULL,
    NULL,
    round((fixture.high + fixture.low + fixture.close) / 3, 8),
    round(fixture.high - fixture.low, 8),
    round(fixture.close - fixture.open, 8)
FROM (
    VALUES
        ('00000000-0000-4000-8000-00000000a001'::uuid, DATE '2024-01-02', 10::numeric, 12::numeric, 8::numeric, 11::numeric, NULL::numeric),
        ('00000000-0000-4000-8000-00000000a001'::uuid, DATE '2024-01-03', 12::numeric, 16::numeric, 10::numeric, 15::numeric, 200::numeric),
        ('00000000-0000-4000-8000-00000000a002'::uuid, DATE '2024-01-02', 20::numeric, 22::numeric, 18::numeric, 21::numeric, 50::numeric),
        ('00000000-0000-4000-8000-00000000b001'::uuid, DATE '2024-01-02', 100::numeric, 102::numeric, 98::numeric, 101::numeric, NULL::numeric),
        ('00000000-0000-4000-8000-00000000c001'::uuid, DATE '2024-01-02', 30::numeric, 32::numeric, 28::numeric, 31::numeric, 10::numeric),
        ('00000000-0000-4000-8000-00000000c002'::uuid, DATE '2024-01-02', 40::numeric, 42::numeric, 38::numeric, 41::numeric, 10::numeric)
) AS fixture(
    provider_listing_id,
    trading_date,
    open,
    high,
    low,
    close,
    volume
);

INSERT INTO core.core_run (
    run_id,
    domain,
    job_name,
    run_type,
    status,
    runner
)
VALUES
    ('10000000-0000-4000-8000-000000000001', 'stonks', 'tech_indicators_schema_test', 'manual', 'succeeded', 'agent'),
    ('10000000-0000-4000-8000-000000000002', 'stonks', 'tech_indicators_cleanup_test', 'manual', 'succeeded', 'agent');

INSERT INTO core.storage_root (
    storage_root_id,
    root_name,
    backend_type,
    base_uri
)
VALUES (
    900000001,
    'tech_indicators_schema_test',
    'filesystem',
    '/tmp/tech-indicators-schema-test'
);

INSERT INTO core.stored_object (
    object_id,
    run_id,
    storage_root_id,
    object_key,
    filename,
    domain,
    logical_name,
    content_type,
    object_kind
)
VALUES
    ('20000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', 900000001, 'tech-test/main', 'report.json', 'stonks', 'tech_test_json', 'application/json', 'stonks_tech_indicators_report'),
    ('20000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', 900000001, 'tech-test/main', 'report.pdf', 'stonks', 'tech_test_pdf', 'application/pdf', 'stonks_tech_indicators_pdf_report'),
    ('20000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000002', 900000001, 'tech-test/cleanup', 'report.json', 'stonks', 'tech_cleanup_json', 'application/json', 'stonks_tech_indicators_report'),
    ('20000000-0000-4000-8000-000000000004', '10000000-0000-4000-8000-000000000002', 900000001, 'tech-test/cleanup', 'report.pdf', 'stonks', 'tech_cleanup_pdf', 'application/pdf', 'stonks_tech_indicators_pdf_report');

-- Exact relation signatures and migration-owned index/trigger inventory.
SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 90
           AND count(*) FILTER (WHERE is_generated = 'ALWAYS') = 23
        FROM information_schema.columns
        WHERE table_schema = 'stonks'
          AND table_name = 'ohlcv_daily_tech_indicators_a'
    ),
    'payload slot A has 90 columns and 23 generated columns'
);

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 90
           AND count(*) FILTER (WHERE is_generated = 'ALWAYS') = 23
        FROM information_schema.columns
        WHERE table_schema = 'stonks'
          AND table_name = 'ohlcv_daily_tech_indicators_b'
    ),
    'payload slot B has 90 columns and 23 generated columns'
);

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 90
        FROM information_schema.columns
        WHERE table_schema = 'stonks'
          AND table_name = 'ohlcv_daily_tech_indicators'
    ),
    'published view has 90 columns'
);

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 41
        FROM information_schema.columns
        WHERE table_schema = 'stonks'
          AND table_name = 'tech_indicators_publication'
    ),
    'publication relation has 41 columns'
);

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 16
        FROM information_schema.columns
        WHERE table_schema = 'stonks'
          AND table_name = 'tech_indicators_publication_listing'
    ),
    'membership relation has 16 columns'
);

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 7
        FROM pg_indexes
        WHERE schemaname = 'stonks'
          AND tablename IN (
              'ohlcv_daily_tech_indicators_a',
              'ohlcv_daily_tech_indicators_b',
              'tech_indicators_publication',
              'tech_indicators_publication_listing'
          )
    ),
    'only the seven frozen primary, date, and integrity indexes exist'
);

SELECT pg_temp.assert_true(
    (
        SELECT is_insertable_into = 'NO'
        FROM information_schema.views
        WHERE table_schema = 'stonks'
          AND table_name = 'ohlcv_daily_tech_indicators'
    ),
    'published view is not automatically updatable'
);

SELECT pg_temp.assert_true(
    to_regclass('stonks.ohlcv_daily_tech_indicators_state') IS NULL,
    'V1 recurrence-state relation is absent'
);

-- Valid warm-up rows in both slots.
SELECT pg_temp.insert_warmup_payload(
    'a',
    '00000000-0000-4000-8000-00000000a001'::uuid,
    DATE '2024-01-02'
);
SELECT pg_temp.insert_warmup_payload(
    'b',
    '00000000-0000-4000-8000-00000000a002'::uuid,
    DATE '2024-01-02'
);

SELECT pg_temp.assert_true(
    (
        SELECT volume IS NULL
           AND dollar_volume IS NULL
           AND pct_sma_20 IS NULL
           AND pct_ema_20 IS NULL
           AND atr_pct_14 IS NULL
           AND bollinger_percent_b_20_2 IS NULL
           AND bollinger_bandwidth_20_2 IS NULL
           AND volume_ratio_20 IS NULL
           AND macd_12_26_pct IS NULL
           AND macd_histogram_12_26_9_pct IS NULL
        FROM ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id = '00000000-0000-4000-8000-00000000a001'
          AND trading_date = DATE '2024-01-02'
    ),
    'valid warm-up row preserves analytical and generated nulls'
);

SELECT pg_temp.insert_warmup_payload(
    'a',
    '00000000-0000-4000-8000-00000000a001',
    DATE '2024-01-03'
);

UPDATE ohlcv_daily_tech_indicators_a
SET
    history_observation_count = 252,
    sma_20 = 12,
    sma_50 = 10,
    sma_200 = 5,
    ema_20 = 12,
    ema_26 = 10,
    ema_50 = 10,
    hh_20 = 15,
    hh_50 = 20,
    hh_252 = 30,
    ll_20 = 10,
    ll_50 = 5,
    atr_14 = 3,
    price_stddev_20 = 2,
    macd_12_26 = 2,
    macd_histogram_12_26_9 = 1,
    volume_avg_20 = 100
WHERE provider_listing_id = '00000000-0000-4000-8000-00000000a001'
  AND trading_date = DATE '2024-01-03';

SELECT pg_temp.assert_true(
    (
        SELECT
            dollar_volume = 3000
            AND abs(intraday_return_1d_pct - 0.25) < 1e-12
            AND abs(daily_range_pct - 0.4) < 1e-12
            AND abs(close_location_1d - (5.0 / 6.0)) < 1e-12
            AND abs(pct_sma_20 - 0.25) < 1e-12
            AND abs(pct_sma_50 - 0.5) < 1e-12
            AND abs(pct_sma_200 - 2.0) < 1e-12
            AND abs(pct_ema_20 - 0.25) < 1e-12
            AND abs(pct_ema_50 - 0.5) < 1e-12
            AND abs(pct_sma_20_vs_50 - 0.2) < 1e-12
            AND abs(pct_sma_20_vs_200 - 1.4) < 1e-12
            AND abs(pct_sma_50_vs_200 - 1.0) < 1e-12
            AND abs(pct_hh_20) < 1e-12
            AND abs(pct_hh_50 + 0.25) < 1e-12
            AND abs(pct_hh_252 + 0.5) < 1e-12
            AND abs(pct_ll_20 - 0.5) < 1e-12
            AND abs(pct_ll_50 - 2.0) < 1e-12
            AND abs(atr_pct_14 - 0.2) < 1e-12
            AND abs(bollinger_percent_b_20_2 - 0.875) < 1e-12
            AND abs(bollinger_bandwidth_20_2 - (2.0 / 3.0)) < 1e-12
            AND abs(volume_ratio_20 - 2.0) < 1e-12
            AND abs(macd_12_26_pct - 0.2) < 1e-12
            AND abs(macd_histogram_12_26_9_pct - (1.0 / 15.0)) < 1e-12
        FROM ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id = '00000000-0000-4000-8000-00000000a001'
          AND trading_date = DATE '2024-01-03'
    ),
    'all 23 generated expressions match representative reference values'
);

-- Both slots enforce their independently named keys and row checks.
DO $tests$
DECLARE
    slot_name TEXT;
    relation_name TEXT;
    listing_id UUID;
    fixture_date DATE;
BEGIN
    FOREACH slot_name IN ARRAY ARRAY['a', 'b']
    LOOP
        relation_name := 'ohlcv_daily_tech_indicators_' || slot_name;
        IF slot_name = 'a' THEN
            listing_id := '00000000-0000-4000-8000-00000000a001';
            fixture_date := DATE '2024-01-02';
        ELSE
            listing_id := '00000000-0000-4000-8000-00000000a002';
            fixture_date := DATE '2024-01-02';
        END IF;

        PERFORM pg_temp.expect_failure(
            format(
                'SELECT pg_temp.insert_warmup_payload(%L, %L, %L)',
                slot_name,
                listing_id,
                fixture_date
            ),
            '23505',
            'pk_ohlcv_daily_tech_indicators_' || slot_name,
            'slot ' || slot_name || ' composite primary key is unique'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET calculation_version = %L WHERE provider_listing_id = %L AND trading_date = %L',
                relation_name,
                'bad-version',
                listing_id,
                fixture_date
            ),
            '23514',
            'ck_tech_indicators_' || slot_name || '_calculation_version',
            'slot ' || slot_name || ' rejects an invalid calculation version'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET history_observation_count = 0 WHERE provider_listing_id = %L AND trading_date = %L',
                relation_name,
                listing_id,
                fixture_date
            ),
            '23514',
            'ck_tech_indicators_' || slot_name || '_history_count',
            'slot ' || slot_name || ' requires a positive history count'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET volume = %L::numeric WHERE provider_listing_id = %L AND trading_date = %L',
                relation_name,
                'NaN',
                listing_id,
                fixture_date
            ),
            '23514',
            'ck_tech_indicators_' || slot_name || '_source_numeric',
            'slot ' || slot_name || ' rejects copied numeric NaN'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET open = high + 1 WHERE provider_listing_id = %L AND trading_date = %L',
                relation_name,
                listing_id,
                fixture_date
            ),
            '23514',
            'ck_tech_indicators_' || slot_name || '_source_bar_shape',
            'slot ' || slot_name || ' rejects invalid copied OHLC shape'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET consecutive_up_days = 1, consecutive_down_days = 1 WHERE provider_listing_id = %L AND trading_date = %L',
                relation_name,
                listing_id,
                fixture_date
            ),
            '23514',
            'ck_tech_indicators_' || slot_name || '_streaks',
            'slot ' || slot_name || ' rejects simultaneous streaks'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET rsi_14 = 101 WHERE provider_listing_id = %L AND trading_date = %L',
                relation_name,
                listing_id,
                fixture_date
            ),
            '23514',
            'ck_tech_indicators_' || slot_name || '_bounded_points',
            'slot ' || slot_name || ' rejects a bounded point above range'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET atr_14 = -1 WHERE provider_listing_id = %L AND trading_date = %L',
                relation_name,
                listing_id,
                fixture_date
            ),
            '23514',
            'ck_tech_indicators_' || slot_name || '_nonnegative_measures',
            'slot ' || slot_name || ' rejects a negative measure'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET rel_spx = 1 WHERE provider_listing_id = %L AND trading_date = %L',
                relation_name,
                listing_id,
                fixture_date
            ),
            '23514',
            'ck_tech_indicators_' || slot_name || '_benchmark_shape',
            'slot ' || slot_name || ' rejects SPX output without lineage'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET updated_at = created_at - interval %L WHERE provider_listing_id = %L AND trading_date = %L',
                relation_name,
                '1 second',
                listing_id,
                fixture_date
            ),
            '23514',
            'ck_tech_indicators_' || slot_name || '_timestamps',
            'slot ' || slot_name || ' rejects reversed timestamps'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET relative_strength_benchmark_provider_listing_id = provider_listing_id WHERE provider_listing_id = %L AND trading_date = %L',
                relation_name,
                listing_id,
                fixture_date
            ),
            '23514',
            'ck_tech_indicators_' || slot_name || '_benchmark_shape',
            'slot ' || slot_name || ' rejects self benchmarking'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET relative_strength_benchmark_provider_listing_id = %L WHERE provider_listing_id = %L AND trading_date = %L',
                relation_name,
                'ffffffff-ffff-4fff-8fff-ffffffffffff',
                listing_id,
                fixture_date
            ),
            '23503',
            'fk_tech_indicators_' || slot_name || '_benchmark_listing',
            'slot ' || slot_name || ' requires existing benchmark lineage'
        );

        PERFORM pg_temp.expect_failure(
            format(
                'INSERT INTO stonks.%I (provider_listing_id, trading_date, history_observation_count, calculation_version, calculated_at, open, high, low, close, consecutive_up_days, consecutive_down_days) VALUES (%L, %L, 1, %L, now(), 1, 2, 0, 1, 0, 0)',
                relation_name,
                '00000000-0000-4000-8000-00000000c004',
                DATE '2024-01-02',
                'TECH_INDICATORS_V1'
            ),
            '23503',
            'fk_tech_indicators_' || slot_name || '_source_bar',
            'slot ' || slot_name || ' requires an owning source bar'
        );
    END LOOP;
END;
$tests$;

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO ohlcv_daily_tech_indicators_a (
            provider_listing_id,
            trading_date,
            history_observation_count,
            calculation_version,
            calculated_at,
            open,
            high,
            low,
            close,
            consecutive_up_days,
            consecutive_down_days,
            dollar_volume
        )
        VALUES (
            '00000000-0000-4000-8000-00000000c004',
            DATE '2024-01-02',
            1,
            'TECH_INDICATORS_V1',
            now(),
            1,
            2,
            0,
            1,
            0,
            0,
            1
        )
    $sql$,
    '428C9',
    NULL,
    'generated payload columns reject explicit writes'
);

-- A resolved benchmark with warm-up-null SPX fields is valid in both slots.
UPDATE ohlcv_daily_tech_indicators_a
SET relative_strength_benchmark_provider_listing_id =
    '00000000-0000-4000-8000-00000000b001'
WHERE provider_listing_id = '00000000-0000-4000-8000-00000000a001';

UPDATE ohlcv_daily_tech_indicators_b
SET relative_strength_benchmark_provider_listing_id =
    '00000000-0000-4000-8000-00000000b001'
WHERE provider_listing_id = '00000000-0000-4000-8000-00000000a002';

SELECT pg_temp.expect_failure(
    $sql$
        DELETE FROM provider_listing
        WHERE provider_listing_id =
            '00000000-0000-4000-8000-00000000b001'
    $sql$,
    '23001',
    NULL,
    'benchmark provider-listing deletion is restricted'
);

-- Source-row and provider-listing ownership cascades affect both slots.
SELECT pg_temp.insert_warmup_payload(
    'a',
    '00000000-0000-4000-8000-00000000c001',
    DATE '2024-01-02'
);
SELECT pg_temp.insert_warmup_payload(
    'b',
    '00000000-0000-4000-8000-00000000c001',
    DATE '2024-01-02'
);

DELETE FROM ohlcv_daily
WHERE provider_listing_id = '00000000-0000-4000-8000-00000000c001'
  AND trading_date = DATE '2024-01-02';

SELECT pg_temp.assert_true(
    NOT EXISTS (
        SELECT 1 FROM ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id =
            '00000000-0000-4000-8000-00000000c001'
        UNION ALL
        SELECT 1 FROM ohlcv_daily_tech_indicators_b
        WHERE provider_listing_id =
            '00000000-0000-4000-8000-00000000c001'
    ),
    'source-row deletion cascades through both payload slots'
);

SELECT pg_temp.insert_warmup_payload(
    'a',
    '00000000-0000-4000-8000-00000000c002',
    DATE '2024-01-02'
);
SELECT pg_temp.insert_warmup_payload(
    'b',
    '00000000-0000-4000-8000-00000000c002',
    DATE '2024-01-02'
);

DELETE FROM provider_listing
WHERE provider_listing_id = '00000000-0000-4000-8000-00000000c002';

SELECT pg_temp.assert_true(
    NOT EXISTS (
        SELECT 1 FROM ohlcv_daily
        WHERE provider_listing_id =
            '00000000-0000-4000-8000-00000000c002'
        UNION ALL
        SELECT 1 FROM ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id =
            '00000000-0000-4000-8000-00000000c002'
        UNION ALL
        SELECT 1 FROM ohlcv_daily_tech_indicators_b
        WHERE provider_listing_id =
            '00000000-0000-4000-8000-00000000c002'
    ),
    'provider-listing deletion cascades through source and both payload slots'
);

-- Publication row checks and one-way lifecycle transitions.
CREATE OR REPLACE FUNCTION pg_temp.create_prepared_publication(
    fixture_kind TEXT DEFAULT 'BACKFILL',
    fixture_method TEXT DEFAULT 'STAGED'
)
RETURNS UUID
LANGUAGE plpgsql
AS $function$
DECLARE
    fixture_publication_id UUID := gen_random_uuid();
BEGIN
    INSERT INTO tech_indicators_publication (
        publication_id,
        publication_kind,
        status,
        calculation_version
    )
    VALUES (
        fixture_publication_id,
        fixture_kind,
        'BUILDING',
        'TECH_INDICATORS_V1'
    );

    UPDATE tech_indicators_publication
    SET
        publication_method = fixture_method,
        scope_schema_version = 1,
        scope_hash = repeat('a', 64),
        run_id = '10000000-0000-4000-8000-000000000001',
        benchmark_required = false,
        expected_listing_count = 2,
        expected_source_row_count = 3,
        expected_payload_row_count = 3,
        inserted_row_count = 3,
        updated_row_count = 0,
        deleted_row_count = 0,
        equivalent_row_count = 0,
        warning_count = 0,
        failure_count = 0,
        completed_batch_count = 0,
        staged_payload_row_count = 0,
        json_report_object_id =
            '20000000-0000-4000-8000-000000000001',
        pdf_report_object_id =
            '20000000-0000-4000-8000-000000000002',
        source_validated_at = now(),
        prepared_at = now(),
        status = 'PREPARED',
        updated_at = now()
    WHERE publication_id = fixture_publication_id;

    RETURN fixture_publication_id;
END;
$function$;

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version
        ) VALUES ('BACKFILL', 'PUBLISHED', 'TECH_INDICATORS_V1')
    $sql$,
    'P0001',
    NULL,
    'publication must start BUILDING'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version
        ) VALUES ('INVALID', 'BUILDING', 'TECH_INDICATORS_V1')
    $sql$,
    '23514',
    'ck_tech_indicators_publication_kind',
    'publication rejects an unknown kind'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version
        ) VALUES ('BACKFILL', 'BUILDING', 'bad-version')
    $sql$,
    '23514',
    'ck_tech_indicators_publication_version',
    'publication rejects an invalid calculation version'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            publication_method
        ) VALUES ('BACKFILL', 'BUILDING', 'TECH_INDICATORS_V1', 'INVALID')
    $sql$,
    '23514',
    'ck_tech_indicators_publication_method',
    'publication rejects an unknown method'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            publication_method
        ) VALUES ('BACKFILL', 'BUILDING', 'TECH_INDICATORS_V1', 'IN_PLACE')
    $sql$,
    '23514',
    'ck_tech_indicators_publication_method_kind',
    'publication method must match its kind'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            scope_schema_version,
            scope_hash
        ) VALUES ('BACKFILL', 'BUILDING', 'TECH_INDICATORS_V1', 1, 'bad')
    $sql$,
    '23514',
    'ck_tech_indicators_publication_scope',
    'publication rejects malformed scope identity'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            requested_start_date,
            requested_end_date
        ) VALUES (
            'BACKFILL',
            'BUILDING',
            'TECH_INDICATORS_V1',
            DATE '2024-02-01',
            DATE '2024-01-01'
        )
    $sql$,
    '23514',
    'ck_tech_indicators_publication_dates',
    'publication rejects reversed request dates'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            benchmark_required
        ) VALUES ('BACKFILL', 'BUILDING', 'TECH_INDICATORS_V1', true)
    $sql$,
    '23514',
    'ck_tech_indicators_publication_benchmark',
    'required benchmark facts must be complete'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            expected_listing_count
        ) VALUES ('BACKFILL', 'BUILDING', 'TECH_INDICATORS_V1', -1)
    $sql$,
    '23514',
    'ck_tech_indicators_publication_counts',
    'publication rejects negative counts'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            completed_batch_count,
            staged_payload_row_count
        ) VALUES ('BACKFILL', 'BUILDING', 'TECH_INDICATORS_V1', 1, 1)
    $sql$,
    '23514',
    'ck_tech_indicators_publication_cursor',
    'positive staged progress requires a complete cursor'
);

INSERT INTO tech_indicators_publication (
    publication_id,
    publication_kind,
    status,
    calculation_version
)
VALUES (
    '30000000-0000-4000-8000-000000000001',
    'BACKFILL',
    'BUILDING',
    'TECH_INDICATORS_V1'
);

SELECT pg_temp.expect_failure(
    $sql$
        UPDATE tech_indicators_publication
        SET status = 'PREPARED', prepared_at = now(), updated_at = now()
        WHERE publication_id =
            '30000000-0000-4000-8000-000000000001'
    $sql$,
    '23514',
    'ck_tech_indicators_publication_prepared_shape',
    'PREPARED publication requires complete facts and Core evidence'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            publication_method,
            completed_batch_count,
            staged_payload_row_count,
            resume_provider_listing_id,
            resume_trading_date,
            resume_cursor_updated_at
        ) VALUES (
            'DAILY',
            'BUILDING',
            'TECH_INDICATORS_V1',
            'IN_PLACE',
            1,
            1,
            '00000000-0000-4000-8000-00000000a001',
            DATE '2024-01-02',
            now()
        )
    $sql$,
    '23514',
    'ck_tech_indicators_publication_method_cursor',
    'non-staged publication rejects resume progress'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            failed_at
        ) VALUES ('BACKFILL', 'BUILDING', 'TECH_INDICATORS_V1', now())
    $sql$,
    '23514',
    'ck_tech_indicators_publication_timestamps',
    'BUILDING publication rejects a terminal timestamp'
);

SELECT pg_temp.expect_failure(
    $sql$
        UPDATE tech_indicators_publication
        SET
            status = 'PUBLISHED',
            prepared_at = now(),
            published_at = now(),
            updated_at = now()
        WHERE publication_id =
            '30000000-0000-4000-8000-000000000001'
    $sql$,
    'P0001',
    NULL,
    'BUILDING publication cannot skip PREPARED'
);

INSERT INTO tech_indicators_publication (
    publication_id,
    publication_kind,
    status,
    calculation_version
)
VALUES
    ('30000000-0000-4000-8000-000000000002', 'BACKFILL', 'BUILDING', 'TECH_INDICATORS_V1'),
    ('30000000-0000-4000-8000-000000000003', 'BACKFILL', 'BUILDING', 'TECH_INDICATORS_V1');

UPDATE tech_indicators_publication
SET status = 'FAILED', failed_at = now(), updated_at = now()
WHERE publication_id = '30000000-0000-4000-8000-000000000002';

UPDATE tech_indicators_publication
SET status = 'ABANDONED', abandoned_at = now(), updated_at = now()
WHERE publication_id = '30000000-0000-4000-8000-000000000003';

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 2
        FROM tech_indicators_publication
        WHERE publication_id IN (
            '30000000-0000-4000-8000-000000000002',
            '30000000-0000-4000-8000-000000000003'
        )
          AND status IN ('FAILED', 'ABANDONED')
    ),
    'BUILDING may terminate as FAILED or ABANDONED'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            run_id
        ) VALUES (
            'BACKFILL',
            'BUILDING',
            'TECH_INDICATORS_V1',
            'ffffffff-ffff-4fff-8fff-ffffffffffff'
        )
    $sql$,
    '23503',
    'fk_tech_indicators_publication_run',
    'publication requires an existing Core run when supplied'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            json_report_object_id
        ) VALUES (
            'BACKFILL',
            'BUILDING',
            'TECH_INDICATORS_V1',
            'ffffffff-ffff-4fff-8fff-ffffffffffff'
        )
    $sql$,
    '23503',
    'fk_tech_indicators_publication_json_report',
    'publication requires an existing JSON report object when supplied'
);

-- Candidate membership, atomic A/B visibility, uniqueness, and immutability.
CREATE TEMP TABLE active_publication AS
SELECT pg_temp.create_prepared_publication() AS publication_id;

INSERT INTO tech_indicators_publication_listing (
    publication_id,
    provider_listing_id,
    action,
    target_slot,
    calculation_version,
    source_coverage_start_date,
    source_coverage_end_date,
    source_row_count,
    payload_row_count,
    benchmark_provider_listing_id,
    candidate_completed_at
)
SELECT
    publication_id,
    '00000000-0000-4000-8000-00000000a001'::uuid,
    'PRESENT',
    'A',
    'TECH_INDICATORS_V1',
    DATE '2024-01-02',
    DATE '2024-01-03',
    2,
    2,
    NULL::uuid,
    now()
FROM active_publication
UNION ALL
SELECT
    publication_id,
    '00000000-0000-4000-8000-00000000a002'::uuid,
    'PRESENT',
    'B',
    'TECH_INDICATORS_V1',
    DATE '2024-01-02',
    DATE '2024-01-02',
    1,
    1,
    NULL::uuid,
    now()
FROM active_publication;

SELECT pg_temp.expect_failure(
    format(
        'UPDATE stonks.tech_indicators_publication_listing SET is_active = true, activated_at = now(), updated_at = now() WHERE publication_id = %L AND provider_listing_id = %L',
        (SELECT publication_id FROM active_publication),
        '00000000-0000-4000-8000-00000000a001'
    ),
    'P0001',
    NULL,
    'active membership requires a PUBLISHED parent'
);

SELECT pg_temp.expect_failure(
    format(
        'INSERT INTO stonks.tech_indicators_publication_listing (publication_id, provider_listing_id, action, calculation_version, source_row_count, payload_row_count, candidate_completed_at) VALUES (%L, %L, %L, %L, 0, 0, now())',
        (SELECT publication_id FROM active_publication),
        '00000000-0000-4000-8000-00000000c003',
        'REMOVE',
        'TECH_INDICATORS_V2'
    ),
    'P0001',
    NULL,
    'membership calculation version must match its publication'
);

SELECT pg_temp.expect_failure(
    format(
        'INSERT INTO stonks.tech_indicators_publication_listing (publication_id, provider_listing_id, action, target_slot, calculation_version, source_row_count, payload_row_count, candidate_completed_at) VALUES (%L, %L, %L, %L, %L, 0, 0, now())',
        (SELECT publication_id FROM active_publication),
        '00000000-0000-4000-8000-00000000c003',
        'REMOVE',
        'A',
        'TECH_INDICATORS_V1'
    ),
    '23514',
    'ck_tech_indicators_membership_image',
    'REMOVE membership rejects a target slot'
);

SELECT pg_temp.expect_failure(
    format(
        'INSERT INTO stonks.tech_indicators_publication_listing (publication_id, provider_listing_id, action, target_slot, calculation_version, source_row_count, payload_row_count, benchmark_provider_listing_id, candidate_completed_at) VALUES (%L, %L, %L, %L, %L, 0, 0, %L, now())',
        (SELECT publication_id FROM active_publication),
        '00000000-0000-4000-8000-00000000c003',
        'PRESENT',
        'A',
        'TECH_INDICATORS_V1',
        '00000000-0000-4000-8000-00000000b001'
    ),
    'P0001',
    NULL,
    'membership benchmark must match publication benchmark facts'
);

SELECT pg_temp.expect_failure(
    format(
        'INSERT INTO stonks.tech_indicators_publication_listing (publication_id, provider_listing_id, action, target_slot, calculation_version, source_coverage_start_date, source_coverage_end_date, source_row_count, payload_row_count, candidate_completed_at) VALUES (%L, %L, %L, %L, %L, %L, %L, 2, 2, now())',
        (SELECT publication_id FROM active_publication),
        '00000000-0000-4000-8000-00000000a001',
        'PRESENT',
        'A',
        'TECH_INDICATORS_V1',
        DATE '2024-01-02',
        DATE '2024-01-03'
    ),
    '23505',
    'pk_tech_indicators_publication_listing',
    'publication/listing candidate identity is unique'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication_listing (
            publication_id,
            provider_listing_id,
            action,
            calculation_version,
            source_row_count,
            payload_row_count,
            candidate_completed_at
        ) VALUES (
            'ffffffff-ffff-4fff-8fff-ffffffffffff',
            '00000000-0000-4000-8000-00000000c003',
            'REMOVE',
            'TECH_INDICATORS_V1',
            0,
            0,
            now()
        )
    $sql$,
    'P0002',
    NULL,
    'membership requires an existing publication'
);

UPDATE tech_indicators_publication AS publication
SET status = 'PUBLISHED', published_at = now(), updated_at = now()
FROM active_publication AS fixture
WHERE publication.publication_id = fixture.publication_id;

UPDATE tech_indicators_publication_listing AS membership
SET is_active = true, activated_at = now(), updated_at = now()
FROM active_publication AS fixture
WHERE membership.publication_id = fixture.publication_id;

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 3
           AND count(*) FILTER (
               WHERE provider_listing_id =
                   '00000000-0000-4000-8000-00000000a001'
           ) = 2
           AND count(*) FILTER (
               WHERE provider_listing_id =
                   '00000000-0000-4000-8000-00000000a002'
           ) = 1
        FROM ohlcv_daily_tech_indicators
    ),
    'published view exposes complete active A/B listing images only'
);

CREATE TEMP TABLE competing_publication AS
SELECT pg_temp.create_prepared_publication() AS publication_id;

UPDATE tech_indicators_publication AS publication
SET status = 'PUBLISHED', published_at = now(), updated_at = now()
FROM competing_publication AS fixture
WHERE publication.publication_id = fixture.publication_id;

INSERT INTO tech_indicators_publication_listing (
    publication_id,
    provider_listing_id,
    action,
    target_slot,
    calculation_version,
    source_coverage_start_date,
    source_coverage_end_date,
    source_row_count,
    payload_row_count,
    candidate_completed_at
)
SELECT
    publication_id,
    '00000000-0000-4000-8000-00000000a001',
    'PRESENT',
    'A',
    'TECH_INDICATORS_V1',
    DATE '2024-01-02',
    DATE '2024-01-03',
    2,
    2,
    now()
FROM competing_publication;

SELECT pg_temp.expect_failure(
    format(
        'UPDATE stonks.tech_indicators_publication_listing SET is_active = true, activated_at = now(), updated_at = now() WHERE publication_id = %L',
        (SELECT publication_id FROM competing_publication)
    ),
    '23505',
    'uq_tech_indicators_membership_active_listing',
    'only one active membership may exist per provider listing'
);

SELECT pg_temp.expect_failure(
    format(
        'UPDATE stonks.tech_indicators_publication_listing SET target_slot = %L WHERE publication_id = %L AND provider_listing_id = %L',
        'B',
        (SELECT publication_id FROM active_publication),
        '00000000-0000-4000-8000-00000000a001'
    ),
    'P0001',
    NULL,
    'membership candidate facts are immutable'
);

SELECT pg_temp.expect_failure(
    format(
        'UPDATE stonks.tech_indicators_publication SET calculation_version = %L WHERE publication_id = %L',
        'TECH_INDICATORS_V2',
        (SELECT publication_id FROM active_publication)
    ),
    'P0001',
    NULL,
    'publication identity and version are immutable'
);

SELECT pg_temp.expect_failure(
    format(
        'UPDATE stonks.tech_indicators_publication SET status = %L, retired_at = now(), updated_at = now() WHERE publication_id = %L',
        'RETIRED',
        (SELECT publication_id FROM active_publication)
    ),
    'P0001',
    NULL,
    'publication with active membership cannot retire'
);

SELECT pg_temp.expect_failure(
    format(
        'UPDATE stonks.tech_indicators_publication SET status = %L, failed_at = now(), published_at = NULL, updated_at = now() WHERE publication_id = %L',
        'FAILED',
        (SELECT publication_id FROM active_publication)
    ),
    'P0001',
    NULL,
    'PUBLISHED publication cannot transition to FAILED'
);

UPDATE tech_indicators_publication_listing AS membership
SET is_active = false, deactivated_at = now(), updated_at = now()
FROM active_publication AS fixture
WHERE membership.publication_id = fixture.publication_id;

SELECT pg_temp.expect_failure(
    format(
        'UPDATE stonks.tech_indicators_publication_listing SET is_active = true, deactivated_at = NULL, updated_at = now() WHERE publication_id = %L AND provider_listing_id = %L',
        (SELECT publication_id FROM active_publication),
        '00000000-0000-4000-8000-00000000a001'
    ),
    'P0001',
    NULL,
    'historical membership cannot reactivate'
);

UPDATE tech_indicators_publication AS publication
SET status = 'RETIRED', retired_at = now(), updated_at = now()
FROM active_publication AS fixture
WHERE publication.publication_id = fixture.publication_id;

SELECT pg_temp.assert_true(
    NOT EXISTS (
        SELECT 1
        FROM ohlcv_daily_tech_indicators
        WHERE provider_listing_id IN (
            '00000000-0000-4000-8000-00000000a001',
            '00000000-0000-4000-8000-00000000a002'
        )
    ),
    'deactivation and retirement remove both listing images from the view'
);

SELECT pg_temp.expect_failure(
    format(
        'DELETE FROM stonks.tech_indicators_publication WHERE publication_id = %L',
        (SELECT publication_id FROM active_publication)
    ),
    '23001',
    'fk_tech_indicators_membership_publication',
    'publication deletion is restricted while membership history exists'
);

-- Valid REMOVE membership is active but never projects payload.
CREATE TEMP TABLE removal_publication AS
SELECT pg_temp.create_prepared_publication(
    'ELIGIBILITY_REMOVAL',
    'MEMBERSHIP_ONLY'
) AS publication_id;

INSERT INTO tech_indicators_publication_listing (
    publication_id,
    provider_listing_id,
    action,
    calculation_version,
    source_row_count,
    payload_row_count,
    candidate_completed_at
)
SELECT
    publication_id,
    '00000000-0000-4000-8000-00000000a002',
    'REMOVE',
    'TECH_INDICATORS_V1',
    0,
    0,
    now()
FROM removal_publication;

UPDATE tech_indicators_publication AS publication
SET status = 'PUBLISHED', published_at = now(), updated_at = now()
FROM removal_publication AS fixture
WHERE publication.publication_id = fixture.publication_id;

UPDATE tech_indicators_publication_listing AS membership
SET is_active = true, activated_at = now(), updated_at = now()
FROM removal_publication AS fixture
WHERE membership.publication_id = fixture.publication_id;

SELECT pg_temp.assert_true(
    NOT EXISTS (
        SELECT 1 FROM ohlcv_daily_tech_indicators
        WHERE provider_listing_id =
            '00000000-0000-4000-8000-00000000a002'
    ),
    'active REMOVE membership suppresses rather than projects payload'
);

UPDATE tech_indicators_publication_listing AS membership
SET is_active = false, deactivated_at = now(), updated_at = now()
FROM removal_publication AS fixture
WHERE membership.publication_id = fixture.publication_id;

UPDATE tech_indicators_publication AS publication
SET status = 'RETIRED', retired_at = now(), updated_at = now()
FROM removal_publication AS fixture
WHERE publication.publication_id = fixture.publication_id;

-- Inactive membership follows its provider-listing ownership cascade.
INSERT INTO tech_indicators_publication_listing (
    publication_id,
    provider_listing_id,
    action,
    calculation_version,
    source_row_count,
    payload_row_count,
    candidate_completed_at
)
VALUES (
    '30000000-0000-4000-8000-000000000001',
    '00000000-0000-4000-8000-00000000c003',
    'REMOVE',
    'TECH_INDICATORS_V1',
    0,
    0,
    now()
);

DELETE FROM provider_listing
WHERE provider_listing_id = '00000000-0000-4000-8000-00000000c003';

SELECT pg_temp.assert_true(
    NOT EXISTS (
        SELECT 1 FROM tech_indicators_publication_listing
        WHERE provider_listing_id =
            '00000000-0000-4000-8000-00000000c003'
    ),
    'membership is deleted with its owning provider listing'
);

SELECT pg_temp.expect_failure(
    format(
        'INSERT INTO stonks.tech_indicators_publication_listing (publication_id, provider_listing_id, action, calculation_version, source_row_count, payload_row_count, candidate_completed_at) VALUES (%L, %L, %L, %L, 0, 0, now())',
        (SELECT publication_id FROM competing_publication),
        '00000000-0000-4000-8000-00000000c004',
        'INVALID',
        'TECH_INDICATORS_V1'
    ),
    '23514',
    NULL,
    'membership rejects an unknown action'
);

SELECT pg_temp.expect_failure(
    format(
        'INSERT INTO stonks.tech_indicators_publication_listing (publication_id, provider_listing_id, action, calculation_version, source_row_count, payload_row_count, candidate_completed_at) VALUES (%L, %L, %L, %L, 0, 0, now())',
        (SELECT publication_id FROM competing_publication),
        'ffffffff-ffff-4fff-8fff-ffffffffffff',
        'REMOVE',
        'TECH_INDICATORS_V1'
    ),
    '23503',
    'fk_tech_indicators_membership_listing',
    'membership requires an existing provider listing'
);

SELECT pg_temp.expect_failure(
    format(
        'INSERT INTO stonks.tech_indicators_publication_listing (publication_id, provider_listing_id, action, calculation_version, source_row_count, payload_row_count, candidate_completed_at, activated_at) VALUES (%L, %L, %L, %L, 0, 0, now(), now())',
        (SELECT publication_id FROM competing_publication),
        '00000000-0000-4000-8000-00000000c004',
        'REMOVE',
        'TECH_INDICATORS_V1'
    ),
    '23514',
    'ck_tech_indicators_membership_timestamps',
    'inactive membership rejects activation time without active state'
);

SELECT pg_temp.expect_failure(
    format(
        'UPDATE stonks.tech_indicators_publication SET expected_payload_row_count = expected_payload_row_count + 1 WHERE publication_id = %L',
        (SELECT publication_id FROM competing_publication)
    ),
    'P0001',
    NULL,
    'prepared publication count and cursor facts are immutable'
);

SELECT pg_temp.expect_failure(
    $sql$
        INSERT INTO tech_indicators_publication (
            publication_kind,
            status,
            calculation_version,
            benchmark_required,
            benchmark_provider_listing_id,
            benchmark_contract_version,
            benchmark_coverage_start_date,
            benchmark_coverage_end_date,
            benchmark_source_row_count
        ) VALUES (
            'BACKFILL',
            'BUILDING',
            'TECH_INDICATORS_V1',
            true,
            'ffffffff-ffff-4fff-8fff-ffffffffffff',
            'TECH_INDICATORS_SPX_V1',
            DATE '2024-01-01',
            DATE '2024-01-31',
            20
        )
    $sql$,
    '23503',
    'fk_tech_indicators_publication_benchmark',
    'publication requires an existing benchmark listing when supplied'
);

DO $tests$
DECLARE
    slot_name TEXT;
    relation_name TEXT;
    listing_id UUID;
BEGIN
    FOREACH slot_name IN ARRAY ARRAY['a', 'b']
    LOOP
        relation_name := 'ohlcv_daily_tech_indicators_' || slot_name;
        listing_id := CASE slot_name
            WHEN 'a' THEN '00000000-0000-4000-8000-00000000a001'::uuid
            ELSE '00000000-0000-4000-8000-00000000a002'::uuid
        END;
        PERFORM pg_temp.expect_failure(
            format(
                'UPDATE stonks.%I SET run_id = %L WHERE provider_listing_id = %L',
                relation_name,
                'ffffffff-ffff-4fff-8fff-ffffffffffff',
                listing_id
            ),
            '23503',
            'fk_tech_indicators_' || slot_name || '_run',
            'slot ' || slot_name || ' requires an existing Core run when supplied'
        );
    END LOOP;
END;
$tests$;

-- PREPARED may terminate as FAILED or ABANDONED without publication.
CREATE TEMP TABLE prepared_terminal_publication AS
SELECT pg_temp.create_prepared_publication() AS publication_id, 'FAILED' AS terminal_status
UNION ALL
SELECT pg_temp.create_prepared_publication(), 'ABANDONED';

UPDATE tech_indicators_publication AS publication
SET
    status = terminal.terminal_status,
    failed_at = CASE
        WHEN terminal.terminal_status = 'FAILED' THEN now()
        ELSE NULL
    END,
    abandoned_at = CASE
        WHEN terminal.terminal_status = 'ABANDONED' THEN now()
        ELSE NULL
    END,
    updated_at = now()
FROM prepared_terminal_publication AS terminal
WHERE publication.publication_id = terminal.publication_id;

SELECT pg_temp.assert_true(
    (
        SELECT count(*) = 2
        FROM tech_indicators_publication AS publication
        JOIN prepared_terminal_publication AS terminal
          ON terminal.publication_id = publication.publication_id
        WHERE publication.status = terminal.terminal_status
    ),
    'PREPARED may terminate as FAILED or ABANDONED'
);

-- Core run and report cleanup nulls non-owning evidence without row loss.
UPDATE ohlcv_daily_tech_indicators_a
SET run_id = '10000000-0000-4000-8000-000000000002'
WHERE provider_listing_id = '00000000-0000-4000-8000-00000000a001';

UPDATE ohlcv_daily_tech_indicators_b
SET run_id = '10000000-0000-4000-8000-000000000002'
WHERE provider_listing_id = '00000000-0000-4000-8000-00000000a002';

INSERT INTO tech_indicators_publication (
    publication_id,
    publication_kind,
    status,
    calculation_version,
    run_id,
    json_report_object_id,
    pdf_report_object_id
)
VALUES (
    '30000000-0000-4000-8000-000000000004',
    'BACKFILL',
    'BUILDING',
    'TECH_INDICATORS_V1',
    '10000000-0000-4000-8000-000000000002',
    '20000000-0000-4000-8000-000000000003',
    '20000000-0000-4000-8000-000000000004'
);

DELETE FROM core.stored_object
WHERE object_id IN (
    '20000000-0000-4000-8000-000000000003',
    '20000000-0000-4000-8000-000000000004'
);

SELECT pg_temp.assert_true(
    (
        SELECT json_report_object_id IS NULL
           AND pdf_report_object_id IS NULL
        FROM tech_indicators_publication
        WHERE publication_id =
            '30000000-0000-4000-8000-000000000004'
    ),
    'Core report cleanup nulls publication evidence'
);

DELETE FROM core.core_run
WHERE run_id = '10000000-0000-4000-8000-000000000002';

SELECT pg_temp.assert_true(
    (
        SELECT run_id IS NULL
        FROM tech_indicators_publication
        WHERE publication_id =
            '30000000-0000-4000-8000-000000000004'
    )
    AND NOT EXISTS (
        SELECT 1 FROM ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id =
            '00000000-0000-4000-8000-00000000a001'
          AND run_id IS NOT NULL
    )
    AND NOT EXISTS (
        SELECT 1 FROM ohlcv_daily_tech_indicators_b
        WHERE provider_listing_id =
            '00000000-0000-4000-8000-00000000a002'
          AND run_id IS NOT NULL
    ),
    'Core run cleanup nulls payload and publication lineage without deletion'
);

SELECT pg_temp.assert_true(
    (SELECT count(*) = 64 FROM tech_indicators_expected_failure),
    'all 64 expected constraint and trigger failures were observed'
);

ROLLBACK;

SELECT 'Tech-indicators schema contract tests passed (64 expected failures)'
    AS result;
