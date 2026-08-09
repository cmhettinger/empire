-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_create_tech_indicators
--
-- Purpose:
--   Store versioned provider-native daily technical-indicator payloads
--   behind atomic per-listing publication membership.
--
-- Notes:
--   - Payload slots have identical signatures and independent constraints.
--   - The package is the supported writer; the published view is read-only.
--   - V1 stores no mathematical recurrence state.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Physical payload slot A
-- ---------------------------------------------------------------------

CREATE TABLE ohlcv_daily_tech_indicators_a (
    provider_listing_id UUID NOT NULL,
    trading_date DATE NOT NULL,
    relative_strength_benchmark_provider_listing_id UUID NULL,
    history_observation_count INTEGER NOT NULL,
    calculation_version VARCHAR(64) NOT NULL,
    run_id UUID NULL,
    calculated_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    open NUMERIC(30,10) NOT NULL,
    high NUMERIC(30,10) NOT NULL,
    low NUMERIC(30,10) NOT NULL,
    close NUMERIC(30,10) NOT NULL,
    volume NUMERIC(30,8) NULL,

    return_1d_pct DOUBLE PRECISION NULL,
    return_2d_pct DOUBLE PRECISION NULL,
    return_3d_pct DOUBLE PRECISION NULL,
    return_5d_pct DOUBLE PRECISION NULL,
    return_10d_pct DOUBLE PRECISION NULL,
    return_20d_pct DOUBLE PRECISION NULL,
    return_63d_pct DOUBLE PRECISION NULL,
    return_126d_pct DOUBLE PRECISION NULL,
    return_252d_pct DOUBLE PRECISION NULL,
    gap_1d_pct DOUBLE PRECISION NULL,
    sma_20 DOUBLE PRECISION NULL,
    sma_50 DOUBLE PRECISION NULL,
    sma_200 DOUBLE PRECISION NULL,
    ema_12 DOUBLE PRECISION NULL,
    ema_20 DOUBLE PRECISION NULL,
    ema_26 DOUBLE PRECISION NULL,
    ema_50 DOUBLE PRECISION NULL,
    sma_50_change_20d_pct DOUBLE PRECISION NULL,
    sma_200_change_20d_pct DOUBLE PRECISION NULL,
    hh_20 DOUBLE PRECISION NULL,
    hh_50 DOUBLE PRECISION NULL,
    hh_252 DOUBLE PRECISION NULL,
    ll_20 DOUBLE PRECISION NULL,
    ll_50 DOUBLE PRECISION NULL,
    rsi_14 DOUBLE PRECISION NULL,
    atr_14 DOUBLE PRECISION NULL,
    return_volatility_20d_pct DOUBLE PRECISION NULL,
    return_volatility_60d_pct DOUBLE PRECISION NULL,
    return_1d_zscore_20d DOUBLE PRECISION NULL,
    return_3d_zscore_20d DOUBLE PRECISION NULL,
    price_stddev_20 DOUBLE PRECISION NULL,
    plus_di_14 DOUBLE PRECISION NULL,
    minus_di_14 DOUBLE PRECISION NULL,
    adx_14 DOUBLE PRECISION NULL,
    macd_12_26 DOUBLE PRECISION NULL,
    macd_signal_12_26_9 DOUBLE PRECISION NULL,
    macd_histogram_12_26_9 DOUBLE PRECISION NULL,
    volume_avg_20 DOUBLE PRECISION NULL,
    volume_avg_60 DOUBLE PRECISION NULL,
    dollar_volume_avg_20 DOUBLE PRECISION NULL,
    consecutive_up_days INTEGER NOT NULL,
    consecutive_down_days INTEGER NOT NULL,
    rel_spx DOUBLE PRECISION NULL,
    pct_rel_spx_20 DOUBLE PRECISION NULL,
    pct_rel_spx_50 DOUBLE PRECISION NULL,
    relative_return_spx_20d_pct DOUBLE PRECISION NULL,
    relative_return_spx_63d_pct DOUBLE PRECISION NULL,
    relative_return_spx_126d_pct DOUBLE PRECISION NULL,
    relative_return_spx_252d_pct DOUBLE PRECISION NULL,
    spx_beta_60d DOUBLE PRECISION NULL,
    spx_beta_252d DOUBLE PRECISION NULL,
    spx_correlation_60d DOUBLE PRECISION NULL,
    spx_correlation_252d DOUBLE PRECISION NULL,

    dollar_volume DOUBLE PRECISION
        GENERATED ALWAYS AS (
            abs(close::DOUBLE PRECISION) * volume::DOUBLE PRECISION
        ) STORED,
    intraday_return_1d_pct DOUBLE PRECISION
        GENERATED ALWAYS AS (
            close::DOUBLE PRECISION
                / NULLIF(open::DOUBLE PRECISION, 0.0) - 1.0
        ) STORED,
    daily_range_pct DOUBLE PRECISION
        GENERATED ALWAYS AS (
            (high::DOUBLE PRECISION - low::DOUBLE PRECISION)
                / NULLIF(abs(close::DOUBLE PRECISION), 0.0)
        ) STORED,
    close_location_1d DOUBLE PRECISION
        GENERATED ALWAYS AS (
            (close::DOUBLE PRECISION - low::DOUBLE PRECISION)
                / NULLIF(
                    high::DOUBLE PRECISION - low::DOUBLE PRECISION,
                    0.0
                )
        ) STORED,
    pct_sma_20 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            close::DOUBLE PRECISION / NULLIF(sma_20, 0.0) - 1.0
        ) STORED,
    pct_sma_50 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            close::DOUBLE PRECISION / NULLIF(sma_50, 0.0) - 1.0
        ) STORED,
    pct_sma_200 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            close::DOUBLE PRECISION / NULLIF(sma_200, 0.0) - 1.0
        ) STORED,
    pct_ema_20 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            close::DOUBLE PRECISION / NULLIF(ema_20, 0.0) - 1.0
        ) STORED,
    pct_ema_50 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            close::DOUBLE PRECISION / NULLIF(ema_50, 0.0) - 1.0
        ) STORED,
    pct_sma_20_vs_50 DOUBLE PRECISION
        GENERATED ALWAYS AS (sma_20 / NULLIF(sma_50, 0.0) - 1.0) STORED,
    pct_sma_20_vs_200 DOUBLE PRECISION
        GENERATED ALWAYS AS (sma_20 / NULLIF(sma_200, 0.0) - 1.0) STORED,
    pct_sma_50_vs_200 DOUBLE PRECISION
        GENERATED ALWAYS AS (sma_50 / NULLIF(sma_200, 0.0) - 1.0) STORED,
    pct_hh_20 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            close::DOUBLE PRECISION / NULLIF(hh_20, 0.0) - 1.0
        ) STORED,
    pct_hh_50 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            close::DOUBLE PRECISION / NULLIF(hh_50, 0.0) - 1.0
        ) STORED,
    pct_hh_252 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            close::DOUBLE PRECISION / NULLIF(hh_252, 0.0) - 1.0
        ) STORED,
    pct_ll_20 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            close::DOUBLE PRECISION / NULLIF(ll_20, 0.0) - 1.0
        ) STORED,
    pct_ll_50 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            close::DOUBLE PRECISION / NULLIF(ll_50, 0.0) - 1.0
        ) STORED,
    atr_pct_14 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            atr_14 / NULLIF(abs(close::DOUBLE PRECISION), 0.0)
        ) STORED,
    bollinger_percent_b_20_2 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            (close::DOUBLE PRECISION - (sma_20 - 2.0 * price_stddev_20))
            / NULLIF(
                (sma_20 + 2.0 * price_stddev_20)
                    - (sma_20 - 2.0 * price_stddev_20),
                0.0
            )
        ) STORED,
    bollinger_bandwidth_20_2 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            (
                (sma_20 + 2.0 * price_stddev_20)
                    - (sma_20 - 2.0 * price_stddev_20)
            )
            / NULLIF(abs(sma_20), 0.0)
        ) STORED,
    volume_ratio_20 DOUBLE PRECISION
        GENERATED ALWAYS AS (
            volume::DOUBLE PRECISION / NULLIF(volume_avg_20, 0.0)
        ) STORED,
    macd_12_26_pct DOUBLE PRECISION
        GENERATED ALWAYS AS (
            macd_12_26 / NULLIF(abs(ema_26), 0.0)
        ) STORED,
    macd_histogram_12_26_9_pct DOUBLE PRECISION
        GENERATED ALWAYS AS (
            macd_histogram_12_26_9
                / NULLIF(abs(close::DOUBLE PRECISION), 0.0)
        ) STORED,

    CONSTRAINT pk_ohlcv_daily_tech_indicators_a
        PRIMARY KEY (provider_listing_id, trading_date),

    CONSTRAINT fk_tech_indicators_a_source_bar
        FOREIGN KEY (provider_listing_id, trading_date)
        REFERENCES stonks.ohlcv_daily(provider_listing_id, trading_date)
        ON DELETE CASCADE,

    CONSTRAINT fk_tech_indicators_a_benchmark_listing
        FOREIGN KEY (relative_strength_benchmark_provider_listing_id)
        REFERENCES stonks.provider_listing(provider_listing_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_tech_indicators_a_run
        FOREIGN KEY (run_id)
        REFERENCES core.core_run(run_id)
        ON DELETE SET NULL,

    CONSTRAINT ck_tech_indicators_a_calculation_version
        CHECK (
            calculation_version ~ '^[A-Z][A-Z0-9_]{0,63}$'
            AND calculation_version = btrim(calculation_version)
        ),

    CONSTRAINT ck_tech_indicators_a_history_count
        CHECK (history_observation_count > 0),

    CONSTRAINT ck_tech_indicators_a_source_numeric
        CHECK (
            open <> 'NaN'::numeric
            AND high <> 'NaN'::numeric
            AND low <> 'NaN'::numeric
            AND close <> 'NaN'::numeric
            AND (volume IS NULL OR volume <> 'NaN'::numeric)
        ),

    CONSTRAINT ck_tech_indicators_a_source_bar_shape
        CHECK (
            high >= low
            AND high >= open
            AND high >= close
            AND low <= open
            AND low <= close
            AND (volume IS NULL OR volume >= 0)
        ),

    CONSTRAINT ck_tech_indicators_a_streaks
        CHECK (
            consecutive_up_days >= 0
            AND consecutive_down_days >= 0
            AND NOT (
                consecutive_up_days > 0
                AND consecutive_down_days > 0
            )
        ),

    CONSTRAINT ck_tech_indicators_a_bounded_points
        CHECK (
            (rsi_14 IS NULL OR rsi_14 BETWEEN 0.0 AND 100.0)
            AND (plus_di_14 IS NULL OR plus_di_14 BETWEEN 0.0 AND 100.0)
            AND (minus_di_14 IS NULL OR minus_di_14 BETWEEN 0.0 AND 100.0)
            AND (adx_14 IS NULL OR adx_14 BETWEEN 0.0 AND 100.0)
            AND (
                close_location_1d IS NULL
                OR close_location_1d BETWEEN 0.0 AND 1.0
            )
            AND (
                spx_correlation_60d IS NULL
                OR spx_correlation_60d BETWEEN -1.0 AND 1.0
            )
            AND (
                spx_correlation_252d IS NULL
                OR spx_correlation_252d BETWEEN -1.0 AND 1.0
            )
        ),

    CONSTRAINT ck_tech_indicators_a_nonnegative_measures
        CHECK (
            (atr_14 IS NULL OR atr_14 >= 0.0)
            AND (
                return_volatility_20d_pct IS NULL
                OR return_volatility_20d_pct >= 0.0
            )
            AND (
                return_volatility_60d_pct IS NULL
                OR return_volatility_60d_pct >= 0.0
            )
            AND (price_stddev_20 IS NULL OR price_stddev_20 >= 0.0)
            AND (volume_avg_20 IS NULL OR volume_avg_20 >= 0.0)
            AND (volume_avg_60 IS NULL OR volume_avg_60 >= 0.0)
            AND (
                dollar_volume_avg_20 IS NULL
                OR dollar_volume_avg_20 >= 0.0
            )
            AND (dollar_volume IS NULL OR dollar_volume >= 0.0)
            AND (
                bollinger_bandwidth_20_2 IS NULL
                OR bollinger_bandwidth_20_2 >= 0.0
            )
        ),

    CONSTRAINT ck_tech_indicators_a_benchmark_shape
        CHECK (
            (
                relative_strength_benchmark_provider_listing_id IS NOT NULL
                AND relative_strength_benchmark_provider_listing_id
                    <> provider_listing_id
            )
            OR (
                relative_strength_benchmark_provider_listing_id IS NULL
                AND rel_spx IS NULL
                AND pct_rel_spx_20 IS NULL
                AND pct_rel_spx_50 IS NULL
                AND relative_return_spx_20d_pct IS NULL
                AND relative_return_spx_63d_pct IS NULL
                AND relative_return_spx_126d_pct IS NULL
                AND relative_return_spx_252d_pct IS NULL
                AND spx_beta_60d IS NULL
                AND spx_beta_252d IS NULL
                AND spx_correlation_60d IS NULL
                AND spx_correlation_252d IS NULL
            )
        ),

    CONSTRAINT ck_tech_indicators_a_timestamps
        CHECK (updated_at >= created_at)
);

CREATE INDEX ix_ohlcv_daily_tech_indicators_a_trading_date
    ON ohlcv_daily_tech_indicators_a (
        trading_date DESC,
        provider_listing_id
    );

-- ---------------------------------------------------------------------
-- Physical payload slot B
-- ---------------------------------------------------------------------

CREATE TABLE ohlcv_daily_tech_indicators_b (
    LIKE ohlcv_daily_tech_indicators_a
        INCLUDING DEFAULTS
        INCLUDING GENERATED
        INCLUDING STORAGE
        INCLUDING COMPRESSION
);

ALTER TABLE ohlcv_daily_tech_indicators_b
    ADD CONSTRAINT pk_ohlcv_daily_tech_indicators_b
        PRIMARY KEY (provider_listing_id, trading_date),
    ADD CONSTRAINT fk_tech_indicators_b_source_bar
        FOREIGN KEY (provider_listing_id, trading_date)
        REFERENCES stonks.ohlcv_daily(provider_listing_id, trading_date)
        ON DELETE CASCADE,
    ADD CONSTRAINT fk_tech_indicators_b_benchmark_listing
        FOREIGN KEY (relative_strength_benchmark_provider_listing_id)
        REFERENCES stonks.provider_listing(provider_listing_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT fk_tech_indicators_b_run
        FOREIGN KEY (run_id)
        REFERENCES core.core_run(run_id)
        ON DELETE SET NULL,
    ADD CONSTRAINT ck_tech_indicators_b_calculation_version
        CHECK (
            calculation_version ~ '^[A-Z][A-Z0-9_]{0,63}$'
            AND calculation_version = btrim(calculation_version)
        ),
    ADD CONSTRAINT ck_tech_indicators_b_history_count
        CHECK (history_observation_count > 0),
    ADD CONSTRAINT ck_tech_indicators_b_source_numeric
        CHECK (
            open <> 'NaN'::numeric
            AND high <> 'NaN'::numeric
            AND low <> 'NaN'::numeric
            AND close <> 'NaN'::numeric
            AND (volume IS NULL OR volume <> 'NaN'::numeric)
        ),
    ADD CONSTRAINT ck_tech_indicators_b_source_bar_shape
        CHECK (
            high >= low
            AND high >= open
            AND high >= close
            AND low <= open
            AND low <= close
            AND (volume IS NULL OR volume >= 0)
        ),
    ADD CONSTRAINT ck_tech_indicators_b_streaks
        CHECK (
            consecutive_up_days >= 0
            AND consecutive_down_days >= 0
            AND NOT (
                consecutive_up_days > 0
                AND consecutive_down_days > 0
            )
        ),
    ADD CONSTRAINT ck_tech_indicators_b_bounded_points
        CHECK (
            (rsi_14 IS NULL OR rsi_14 BETWEEN 0.0 AND 100.0)
            AND (plus_di_14 IS NULL OR plus_di_14 BETWEEN 0.0 AND 100.0)
            AND (minus_di_14 IS NULL OR minus_di_14 BETWEEN 0.0 AND 100.0)
            AND (adx_14 IS NULL OR adx_14 BETWEEN 0.0 AND 100.0)
            AND (
                close_location_1d IS NULL
                OR close_location_1d BETWEEN 0.0 AND 1.0
            )
            AND (
                spx_correlation_60d IS NULL
                OR spx_correlation_60d BETWEEN -1.0 AND 1.0
            )
            AND (
                spx_correlation_252d IS NULL
                OR spx_correlation_252d BETWEEN -1.0 AND 1.0
            )
        ),
    ADD CONSTRAINT ck_tech_indicators_b_nonnegative_measures
        CHECK (
            (atr_14 IS NULL OR atr_14 >= 0.0)
            AND (
                return_volatility_20d_pct IS NULL
                OR return_volatility_20d_pct >= 0.0
            )
            AND (
                return_volatility_60d_pct IS NULL
                OR return_volatility_60d_pct >= 0.0
            )
            AND (price_stddev_20 IS NULL OR price_stddev_20 >= 0.0)
            AND (volume_avg_20 IS NULL OR volume_avg_20 >= 0.0)
            AND (volume_avg_60 IS NULL OR volume_avg_60 >= 0.0)
            AND (
                dollar_volume_avg_20 IS NULL
                OR dollar_volume_avg_20 >= 0.0
            )
            AND (dollar_volume IS NULL OR dollar_volume >= 0.0)
            AND (
                bollinger_bandwidth_20_2 IS NULL
                OR bollinger_bandwidth_20_2 >= 0.0
            )
        ),
    ADD CONSTRAINT ck_tech_indicators_b_benchmark_shape
        CHECK (
            (
                relative_strength_benchmark_provider_listing_id IS NOT NULL
                AND relative_strength_benchmark_provider_listing_id
                    <> provider_listing_id
            )
            OR (
                relative_strength_benchmark_provider_listing_id IS NULL
                AND rel_spx IS NULL
                AND pct_rel_spx_20 IS NULL
                AND pct_rel_spx_50 IS NULL
                AND relative_return_spx_20d_pct IS NULL
                AND relative_return_spx_63d_pct IS NULL
                AND relative_return_spx_126d_pct IS NULL
                AND relative_return_spx_252d_pct IS NULL
                AND spx_beta_60d IS NULL
                AND spx_beta_252d IS NULL
                AND spx_correlation_60d IS NULL
                AND spx_correlation_252d IS NULL
            )
        ),
    ADD CONSTRAINT ck_tech_indicators_b_timestamps
        CHECK (updated_at >= created_at);

CREATE INDEX ix_ohlcv_daily_tech_indicators_b_trading_date
    ON ohlcv_daily_tech_indicators_b (
        trading_date DESC,
        provider_listing_id
    );

-- ---------------------------------------------------------------------
-- Publication lifecycle
-- ---------------------------------------------------------------------

CREATE TABLE tech_indicators_publication (
    publication_id UUID NOT NULL DEFAULT gen_random_uuid(),
    publication_kind VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    calculation_version VARCHAR(64) NOT NULL,
    publication_method VARCHAR(16) NULL,
    scope_schema_version SMALLINT NULL,
    scope_hash CHAR(64) NULL,
    effective_date DATE NULL,
    requested_start_date DATE NULL,
    requested_end_date DATE NULL,
    run_id UUID NULL,
    benchmark_required BOOLEAN NULL,
    benchmark_provider_listing_id UUID NULL,
    benchmark_contract_version VARCHAR(64) NULL,
    benchmark_coverage_start_date DATE NULL,
    benchmark_coverage_end_date DATE NULL,
    benchmark_source_row_count BIGINT NULL,
    expected_listing_count INTEGER NULL,
    expected_source_row_count BIGINT NULL,
    expected_payload_row_count BIGINT NULL,
    inserted_row_count BIGINT NULL,
    updated_row_count BIGINT NULL,
    deleted_row_count BIGINT NULL,
    equivalent_row_count BIGINT NULL,
    warning_count INTEGER NULL,
    failure_count INTEGER NULL,
    completed_batch_count INTEGER NULL,
    staged_payload_row_count BIGINT NULL,
    resume_provider_listing_id UUID NULL,
    resume_trading_date DATE NULL,
    resume_cursor_updated_at TIMESTAMPTZ NULL,
    json_report_object_id UUID NULL,
    pdf_report_object_id UUID NULL,
    source_validated_at TIMESTAMPTZ NULL,
    prepared_at TIMESTAMPTZ NULL,
    published_at TIMESTAMPTZ NULL,
    failed_at TIMESTAMPTZ NULL,
    abandoned_at TIMESTAMPTZ NULL,
    retired_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_tech_indicators_publication
        PRIMARY KEY (publication_id),

    CONSTRAINT fk_tech_indicators_publication_run
        FOREIGN KEY (run_id)
        REFERENCES core.core_run(run_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_tech_indicators_publication_benchmark
        FOREIGN KEY (benchmark_provider_listing_id)
        REFERENCES stonks.provider_listing(provider_listing_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_tech_indicators_publication_json_report
        FOREIGN KEY (json_report_object_id)
        REFERENCES core.stored_object(object_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_tech_indicators_publication_pdf_report
        FOREIGN KEY (pdf_report_object_id)
        REFERENCES core.stored_object(object_id)
        ON DELETE SET NULL,

    CONSTRAINT ck_tech_indicators_publication_kind
        CHECK (
            publication_kind IN (
                'DAILY',
                'CORRECTION',
                'VERSION_REBUILD',
                'BACKFILL',
                'ELIGIBILITY_REMOVAL'
            )
        ),

    CONSTRAINT ck_tech_indicators_publication_status
        CHECK (
            status IN (
                'BUILDING', 'PREPARED', 'PUBLISHED',
                'FAILED', 'ABANDONED', 'RETIRED'
            )
        ),

    CONSTRAINT ck_tech_indicators_publication_version
        CHECK (
            calculation_version ~ '^[A-Z][A-Z0-9_]{0,63}$'
            AND calculation_version = btrim(calculation_version)
        ),

    CONSTRAINT ck_tech_indicators_publication_method
        CHECK (
            publication_method IS NULL
            OR publication_method IN (
                'IN_PLACE', 'STAGED', 'MEMBERSHIP_ONLY'
            )
        ),

    CONSTRAINT ck_tech_indicators_publication_method_kind
        CHECK (
            publication_method IS NULL
            OR (
                publication_kind = 'ELIGIBILITY_REMOVAL'
                AND publication_method = 'MEMBERSHIP_ONLY'
            )
            OR (
                publication_kind IN ('VERSION_REBUILD', 'BACKFILL')
                AND publication_method = 'STAGED'
            )
            OR (
                publication_kind IN ('DAILY', 'CORRECTION')
                AND publication_method IN ('IN_PLACE', 'STAGED')
            )
        ),

    CONSTRAINT ck_tech_indicators_publication_scope
        CHECK (
            (scope_schema_version IS NULL AND scope_hash IS NULL)
            OR (
                scope_schema_version = 1
                AND scope_hash ~ '^[a-f0-9]{64}$'
            )
        ),

    CONSTRAINT ck_tech_indicators_publication_dates
        CHECK (
            requested_start_date IS NULL
            OR requested_end_date IS NULL
            OR requested_end_date >= requested_start_date
        ),

    CONSTRAINT ck_tech_indicators_publication_benchmark
        CHECK (
            (
                benchmark_required IS NULL
                AND benchmark_provider_listing_id IS NULL
                AND benchmark_contract_version IS NULL
                AND benchmark_coverage_start_date IS NULL
                AND benchmark_coverage_end_date IS NULL
                AND benchmark_source_row_count IS NULL
            )
            OR (
                benchmark_required
                AND benchmark_provider_listing_id IS NOT NULL
                AND benchmark_contract_version = 'TECH_INDICATORS_SPX_V1'
                AND benchmark_coverage_start_date IS NOT NULL
                AND benchmark_coverage_end_date IS NOT NULL
                AND benchmark_coverage_end_date
                    >= benchmark_coverage_start_date
                AND benchmark_source_row_count > 0
            )
            OR (
                NOT benchmark_required
                AND benchmark_provider_listing_id IS NULL
                AND benchmark_contract_version IS NULL
                AND benchmark_coverage_start_date IS NULL
                AND benchmark_coverage_end_date IS NULL
                AND benchmark_source_row_count IS NULL
            )
        ),

    CONSTRAINT ck_tech_indicators_publication_counts
        CHECK (
            (expected_listing_count IS NULL OR expected_listing_count >= 0)
            AND (
                expected_source_row_count IS NULL
                OR expected_source_row_count >= 0
            )
            AND (
                expected_payload_row_count IS NULL
                OR expected_payload_row_count >= 0
            )
            AND (inserted_row_count IS NULL OR inserted_row_count >= 0)
            AND (updated_row_count IS NULL OR updated_row_count >= 0)
            AND (deleted_row_count IS NULL OR deleted_row_count >= 0)
            AND (equivalent_row_count IS NULL OR equivalent_row_count >= 0)
            AND (warning_count IS NULL OR warning_count >= 0)
            AND (failure_count IS NULL OR failure_count >= 0)
            AND (
                completed_batch_count IS NULL
                OR completed_batch_count >= 0
            )
            AND (
                staged_payload_row_count IS NULL
                OR staged_payload_row_count >= 0
            )
        ),

    CONSTRAINT ck_tech_indicators_publication_cursor
        CHECK (
            (
                completed_batch_count IS NULL
                AND staged_payload_row_count IS NULL
                AND resume_provider_listing_id IS NULL
                AND resume_trading_date IS NULL
                AND resume_cursor_updated_at IS NULL
            )
            OR (
                completed_batch_count IS NOT NULL
                AND staged_payload_row_count IS NOT NULL
                AND (
                    (
                        completed_batch_count = 0
                        AND resume_provider_listing_id IS NULL
                        AND resume_trading_date IS NULL
                        AND resume_cursor_updated_at IS NULL
                    )
                    OR (
                        completed_batch_count > 0
                        AND resume_provider_listing_id IS NOT NULL
                        AND resume_trading_date IS NOT NULL
                        AND resume_cursor_updated_at IS NOT NULL
                    )
                )
            )
        ),

    CONSTRAINT ck_tech_indicators_publication_prepared_shape
        CHECK (
            status NOT IN ('PREPARED', 'PUBLISHED', 'RETIRED')
            OR (
                publication_method IS NOT NULL
                AND scope_schema_version = 1
                AND scope_hash IS NOT NULL
                AND benchmark_required IS NOT NULL
                AND expected_listing_count IS NOT NULL
                AND expected_source_row_count IS NOT NULL
                AND expected_payload_row_count IS NOT NULL
                AND inserted_row_count IS NOT NULL
                AND updated_row_count IS NOT NULL
                AND deleted_row_count IS NOT NULL
                AND equivalent_row_count IS NOT NULL
                AND warning_count IS NOT NULL
                AND failure_count IS NOT NULL
                AND completed_batch_count IS NOT NULL
                AND staged_payload_row_count IS NOT NULL
                AND source_validated_at IS NOT NULL
                AND prepared_at IS NOT NULL
                AND (
                    status <> 'PREPARED'
                    OR (
                        run_id IS NOT NULL
                        AND json_report_object_id IS NOT NULL
                        AND pdf_report_object_id IS NOT NULL
                        AND json_report_object_id <> pdf_report_object_id
                    )
                )
            )
        ),

    CONSTRAINT ck_tech_indicators_publication_method_cursor
        CHECK (
            publication_method = 'STAGED'
            OR (
                COALESCE(completed_batch_count, 0) = 0
                AND COALESCE(staged_payload_row_count, 0) = 0
                AND resume_provider_listing_id IS NULL
                AND resume_trading_date IS NULL
                AND resume_cursor_updated_at IS NULL
            )
        ),

    CONSTRAINT ck_tech_indicators_publication_timestamps
        CHECK (
            updated_at >= created_at
            AND (
                (
                    status = 'BUILDING'
                    AND prepared_at IS NULL
                    AND published_at IS NULL
                    AND failed_at IS NULL
                    AND abandoned_at IS NULL
                    AND retired_at IS NULL
                )
                OR (
                    status = 'PREPARED'
                    AND prepared_at IS NOT NULL
                    AND published_at IS NULL
                    AND prepared_at >= created_at
                    AND failed_at IS NULL
                    AND abandoned_at IS NULL
                    AND retired_at IS NULL
                )
                OR (
                    status = 'PUBLISHED'
                    AND prepared_at IS NOT NULL
                    AND published_at IS NOT NULL
                    AND prepared_at >= created_at
                    AND published_at >= prepared_at
                    AND failed_at IS NULL
                    AND abandoned_at IS NULL
                    AND retired_at IS NULL
                )
                OR (
                    status = 'FAILED'
                    AND failed_at IS NOT NULL
                    AND published_at IS NULL
                    AND failed_at >= created_at
                    AND (prepared_at IS NULL OR failed_at >= prepared_at)
                    AND abandoned_at IS NULL
                    AND retired_at IS NULL
                )
                OR (
                    status = 'ABANDONED'
                    AND abandoned_at IS NOT NULL
                    AND published_at IS NULL
                    AND abandoned_at >= created_at
                    AND (prepared_at IS NULL OR abandoned_at >= prepared_at)
                    AND failed_at IS NULL
                    AND retired_at IS NULL
                )
                OR (
                    status = 'RETIRED'
                    AND prepared_at IS NOT NULL
                    AND published_at IS NOT NULL
                    AND retired_at IS NOT NULL
                    AND prepared_at >= created_at
                    AND published_at >= prepared_at
                    AND retired_at >= published_at
                    AND failed_at IS NULL
                    AND abandoned_at IS NULL
                )
            )
        )
);

-- ---------------------------------------------------------------------
-- Per-listing publication membership
-- ---------------------------------------------------------------------

CREATE TABLE tech_indicators_publication_listing (
    publication_id UUID NOT NULL,
    provider_listing_id UUID NOT NULL,
    action VARCHAR(16) NOT NULL,
    target_slot CHAR(1) NULL,
    calculation_version VARCHAR(64) NOT NULL,
    source_coverage_start_date DATE NULL,
    source_coverage_end_date DATE NULL,
    source_row_count BIGINT NOT NULL,
    payload_row_count BIGINT NOT NULL,
    benchmark_provider_listing_id UUID NULL,
    candidate_completed_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,
    activated_at TIMESTAMPTZ NULL,
    deactivated_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_tech_indicators_publication_listing
        PRIMARY KEY (publication_id, provider_listing_id),

    CONSTRAINT fk_tech_indicators_membership_publication
        FOREIGN KEY (publication_id)
        REFERENCES stonks.tech_indicators_publication(publication_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_tech_indicators_membership_listing
        FOREIGN KEY (provider_listing_id)
        REFERENCES stonks.provider_listing(provider_listing_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_tech_indicators_membership_benchmark
        FOREIGN KEY (benchmark_provider_listing_id)
        REFERENCES stonks.provider_listing(provider_listing_id)
        ON DELETE RESTRICT,

    CONSTRAINT ck_tech_indicators_membership_version
        CHECK (
            calculation_version ~ '^[A-Z][A-Z0-9_]{0,63}$'
            AND calculation_version = btrim(calculation_version)
        ),

    CONSTRAINT ck_tech_indicators_membership_action
        CHECK (action IN ('PRESENT', 'REMOVE')),

    CONSTRAINT ck_tech_indicators_membership_image
        CHECK (
            source_row_count >= 0
            AND payload_row_count >= 0
            AND (
                (
                    action = 'REMOVE'
                    AND target_slot IS NULL
                    AND source_coverage_start_date IS NULL
                    AND source_coverage_end_date IS NULL
                    AND source_row_count = 0
                    AND payload_row_count = 0
                    AND benchmark_provider_listing_id IS NULL
                )
                OR (
                    action = 'PRESENT'
                    AND target_slot IN ('A', 'B')
                    AND payload_row_count = source_row_count
                    AND (
                        (
                            source_row_count = 0
                            AND source_coverage_start_date IS NULL
                            AND source_coverage_end_date IS NULL
                        )
                        OR (
                            source_row_count > 0
                            AND source_coverage_start_date IS NOT NULL
                            AND source_coverage_end_date IS NOT NULL
                            AND source_coverage_end_date
                                >= source_coverage_start_date
                        )
                    )
                )
            )
        ),

    CONSTRAINT ck_tech_indicators_membership_timestamps
        CHECK (
            updated_at >= created_at
            AND (
                (
                    is_active
                    AND activated_at IS NOT NULL
                    AND deactivated_at IS NULL
                )
                OR (
                    NOT is_active
                    AND activated_at IS NULL
                    AND deactivated_at IS NULL
                )
                OR (
                    NOT is_active
                    AND activated_at IS NOT NULL
                    AND deactivated_at IS NOT NULL
                    AND deactivated_at >= activated_at
                )
            )
        )
);

CREATE UNIQUE INDEX uq_tech_indicators_membership_active_listing
    ON tech_indicators_publication_listing (provider_listing_id)
    WHERE is_active;

-- ---------------------------------------------------------------------
-- Lifecycle and cross-relation integrity
-- ---------------------------------------------------------------------

CREATE FUNCTION stonks.enforce_tech_indicators_publication_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'BUILDING' THEN
            RAISE EXCEPTION
                'tech-indicators publication must start BUILDING';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.publication_id IS DISTINCT FROM OLD.publication_id
       OR NEW.publication_kind IS DISTINCT FROM OLD.publication_kind
       OR NEW.calculation_version IS DISTINCT FROM OLD.calculation_version THEN
        RAISE EXCEPTION
            'tech-indicators publication identity is immutable';
    END IF;

    IF OLD.publication_method IS NOT NULL
       AND NEW.publication_method IS DISTINCT FROM OLD.publication_method THEN
        RAISE EXCEPTION
            'tech-indicators publication method is immutable';
    END IF;

    IF OLD.scope_hash IS NOT NULL
       AND (
           NEW.scope_hash IS DISTINCT FROM OLD.scope_hash
           OR NEW.scope_schema_version
                IS DISTINCT FROM OLD.scope_schema_version
       ) THEN
        RAISE EXCEPTION 'tech-indicators publication scope is immutable';
    END IF;

    IF OLD.effective_date IS NOT NULL
       AND NEW.effective_date IS DISTINCT FROM OLD.effective_date THEN
        RAISE EXCEPTION 'tech-indicators effective date is immutable';
    END IF;

    IF OLD.requested_start_date IS NOT NULL
       AND NEW.requested_start_date
            IS DISTINCT FROM OLD.requested_start_date THEN
        RAISE EXCEPTION 'tech-indicators start date is immutable';
    END IF;

    IF OLD.requested_end_date IS NOT NULL
       AND NEW.requested_end_date IS DISTINCT FROM OLD.requested_end_date THEN
        RAISE EXCEPTION 'tech-indicators end date is immutable';
    END IF;

    IF OLD.benchmark_required IS NOT NULL
       AND (
           NEW.benchmark_required,
           NEW.benchmark_provider_listing_id,
           NEW.benchmark_contract_version,
           NEW.benchmark_coverage_start_date,
           NEW.benchmark_coverage_end_date,
           NEW.benchmark_source_row_count
       ) IS DISTINCT FROM (
           OLD.benchmark_required,
           OLD.benchmark_provider_listing_id,
           OLD.benchmark_contract_version,
           OLD.benchmark_coverage_start_date,
           OLD.benchmark_coverage_end_date,
           OLD.benchmark_source_row_count
       ) THEN
        RAISE EXCEPTION
            'tech-indicators benchmark facts are immutable';
    END IF;

    IF OLD.prepared_at IS NOT NULL
       AND (
           NEW.expected_listing_count,
           NEW.expected_source_row_count,
           NEW.expected_payload_row_count,
           NEW.inserted_row_count,
           NEW.updated_row_count,
           NEW.deleted_row_count,
           NEW.equivalent_row_count,
           NEW.warning_count,
           NEW.failure_count,
           NEW.completed_batch_count,
           NEW.staged_payload_row_count,
           NEW.resume_provider_listing_id,
           NEW.resume_trading_date,
           NEW.resume_cursor_updated_at,
           NEW.source_validated_at,
           NEW.prepared_at
       ) IS DISTINCT FROM (
           OLD.expected_listing_count,
           OLD.expected_source_row_count,
           OLD.expected_payload_row_count,
           OLD.inserted_row_count,
           OLD.updated_row_count,
           OLD.deleted_row_count,
           OLD.equivalent_row_count,
           OLD.warning_count,
           OLD.failure_count,
           OLD.completed_batch_count,
           OLD.staged_payload_row_count,
           OLD.resume_provider_listing_id,
           OLD.resume_trading_date,
           OLD.resume_cursor_updated_at,
           OLD.source_validated_at,
           OLD.prepared_at
       ) THEN
        RAISE EXCEPTION
            'prepared tech-indicators publication facts are immutable';
    END IF;

    IF OLD.prepared_at IS NOT NULL THEN
        IF OLD.run_id IS NOT NULL
           AND NEW.run_id IS DISTINCT FROM OLD.run_id
           AND NEW.run_id IS NOT NULL THEN
            RAISE EXCEPTION
                'tech-indicators run evidence cannot be replaced';
        END IF;
        IF OLD.json_report_object_id IS NOT NULL
           AND NEW.json_report_object_id
                IS DISTINCT FROM OLD.json_report_object_id
           AND NEW.json_report_object_id IS NOT NULL THEN
            RAISE EXCEPTION
                'tech-indicators JSON report evidence cannot be replaced';
        END IF;
        IF OLD.pdf_report_object_id IS NOT NULL
           AND NEW.pdf_report_object_id
                IS DISTINCT FROM OLD.pdf_report_object_id
           AND NEW.pdf_report_object_id IS NOT NULL THEN
            RAISE EXCEPTION
                'tech-indicators PDF report evidence cannot be replaced';
        END IF;
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status
       AND NOT (
           (
               OLD.status = 'BUILDING'
               AND NEW.status IN ('PREPARED', 'FAILED', 'ABANDONED')
           )
           OR (
               OLD.status = 'PREPARED'
               AND NEW.status IN ('PUBLISHED', 'FAILED', 'ABANDONED')
           )
           OR (
               OLD.status = 'PUBLISHED'
               AND NEW.status = 'RETIRED'
           )
       ) THEN
        RAISE EXCEPTION
            'invalid tech-indicators publication status transition';
    END IF;

    IF NEW.status = 'RETIRED'
       AND OLD.status IS DISTINCT FROM 'RETIRED'
       AND EXISTS (
           SELECT 1
           FROM stonks.tech_indicators_publication_listing AS membership
           WHERE membership.publication_id = OLD.publication_id
             AND membership.is_active
       ) THEN
        RAISE EXCEPTION
            'active tech-indicators publication cannot be retired';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tech_indicators_publication_transition
BEFORE INSERT OR UPDATE ON stonks.tech_indicators_publication
FOR EACH ROW
EXECUTE FUNCTION stonks.enforce_tech_indicators_publication_transition();

CREATE FUNCTION stonks.enforce_tech_indicators_membership_integrity()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    parent_status VARCHAR(16);
    parent_version VARCHAR(64);
    parent_benchmark_required BOOLEAN;
    parent_benchmark_provider_listing_id UUID;
BEGIN
    SELECT
        publication.status,
        publication.calculation_version,
        publication.benchmark_required,
        publication.benchmark_provider_listing_id
    INTO STRICT
        parent_status,
        parent_version,
        parent_benchmark_required,
        parent_benchmark_provider_listing_id
    FROM stonks.tech_indicators_publication AS publication
    WHERE publication.publication_id = NEW.publication_id
    FOR KEY SHARE;

    IF NEW.calculation_version IS DISTINCT FROM parent_version THEN
        RAISE EXCEPTION
            'membership calculation version does not match publication';
    END IF;

    IF NEW.benchmark_provider_listing_id IS NOT NULL
       AND (
           parent_benchmark_required IS DISTINCT FROM true
           OR NEW.benchmark_provider_listing_id
                IS DISTINCT FROM parent_benchmark_provider_listing_id
       ) THEN
        RAISE EXCEPTION
            'membership benchmark does not match publication';
    END IF;

    IF NEW.is_active AND parent_status <> 'PUBLISHED' THEN
        RAISE EXCEPTION
            'active membership requires a published parent';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF (
            NEW.publication_id,
            NEW.provider_listing_id,
            NEW.action,
            NEW.target_slot,
            NEW.calculation_version,
            NEW.source_coverage_start_date,
            NEW.source_coverage_end_date,
            NEW.source_row_count,
            NEW.payload_row_count,
            NEW.benchmark_provider_listing_id,
            NEW.candidate_completed_at
        ) IS DISTINCT FROM (
            OLD.publication_id,
            OLD.provider_listing_id,
            OLD.action,
            OLD.target_slot,
            OLD.calculation_version,
            OLD.source_coverage_start_date,
            OLD.source_coverage_end_date,
            OLD.source_row_count,
            OLD.payload_row_count,
            OLD.benchmark_provider_listing_id,
            OLD.candidate_completed_at
        ) THEN
            RAISE EXCEPTION
                'tech-indicators membership candidate facts are immutable';
        END IF;

        IF NOT OLD.is_active
           AND NEW.is_active
           AND OLD.deactivated_at IS NOT NULL THEN
            RAISE EXCEPTION
                'historical tech-indicators membership cannot reactivate';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tech_indicators_membership_integrity
BEFORE INSERT OR UPDATE ON stonks.tech_indicators_publication_listing
FOR EACH ROW
EXECUTE FUNCTION stonks.enforce_tech_indicators_membership_integrity();

-- ---------------------------------------------------------------------
-- Published consumer view
-- ---------------------------------------------------------------------

CREATE VIEW stonks.ohlcv_daily_tech_indicators AS
WITH active_membership AS (
    SELECT membership.provider_listing_id, membership.target_slot
    FROM stonks.tech_indicators_publication_listing AS membership
    INNER JOIN stonks.tech_indicators_publication AS publication
        ON publication.publication_id = membership.publication_id
    WHERE membership.is_active
      AND membership.action = 'PRESENT'
      AND publication.status = 'PUBLISHED'
)
SELECT
    payload_a.provider_listing_id,
    payload_a.trading_date,
    payload_a.relative_strength_benchmark_provider_listing_id,
    payload_a.history_observation_count,
    payload_a.calculation_version,
    payload_a.run_id,
    payload_a.calculated_at,
    payload_a.created_at,
    payload_a.updated_at,
    payload_a.open,
    payload_a.high,
    payload_a.low,
    payload_a.close,
    payload_a.volume,
    payload_a.return_1d_pct,
    payload_a.return_2d_pct,
    payload_a.return_3d_pct,
    payload_a.return_5d_pct,
    payload_a.return_10d_pct,
    payload_a.return_20d_pct,
    payload_a.return_63d_pct,
    payload_a.return_126d_pct,
    payload_a.return_252d_pct,
    payload_a.gap_1d_pct,
    payload_a.sma_20,
    payload_a.sma_50,
    payload_a.sma_200,
    payload_a.ema_12,
    payload_a.ema_20,
    payload_a.ema_26,
    payload_a.ema_50,
    payload_a.sma_50_change_20d_pct,
    payload_a.sma_200_change_20d_pct,
    payload_a.hh_20,
    payload_a.hh_50,
    payload_a.hh_252,
    payload_a.ll_20,
    payload_a.ll_50,
    payload_a.rsi_14,
    payload_a.atr_14,
    payload_a.return_volatility_20d_pct,
    payload_a.return_volatility_60d_pct,
    payload_a.return_1d_zscore_20d,
    payload_a.return_3d_zscore_20d,
    payload_a.price_stddev_20,
    payload_a.plus_di_14,
    payload_a.minus_di_14,
    payload_a.adx_14,
    payload_a.macd_12_26,
    payload_a.macd_signal_12_26_9,
    payload_a.macd_histogram_12_26_9,
    payload_a.volume_avg_20,
    payload_a.volume_avg_60,
    payload_a.dollar_volume_avg_20,
    payload_a.consecutive_up_days,
    payload_a.consecutive_down_days,
    payload_a.rel_spx,
    payload_a.pct_rel_spx_20,
    payload_a.pct_rel_spx_50,
    payload_a.relative_return_spx_20d_pct,
    payload_a.relative_return_spx_63d_pct,
    payload_a.relative_return_spx_126d_pct,
    payload_a.relative_return_spx_252d_pct,
    payload_a.spx_beta_60d,
    payload_a.spx_beta_252d,
    payload_a.spx_correlation_60d,
    payload_a.spx_correlation_252d,
    payload_a.dollar_volume,
    payload_a.intraday_return_1d_pct,
    payload_a.daily_range_pct,
    payload_a.close_location_1d,
    payload_a.pct_sma_20,
    payload_a.pct_sma_50,
    payload_a.pct_sma_200,
    payload_a.pct_ema_20,
    payload_a.pct_ema_50,
    payload_a.pct_sma_20_vs_50,
    payload_a.pct_sma_20_vs_200,
    payload_a.pct_sma_50_vs_200,
    payload_a.pct_hh_20,
    payload_a.pct_hh_50,
    payload_a.pct_hh_252,
    payload_a.pct_ll_20,
    payload_a.pct_ll_50,
    payload_a.atr_pct_14,
    payload_a.bollinger_percent_b_20_2,
    payload_a.bollinger_bandwidth_20_2,
    payload_a.volume_ratio_20,
    payload_a.macd_12_26_pct,
    payload_a.macd_histogram_12_26_9_pct
FROM stonks.ohlcv_daily_tech_indicators_a AS payload_a
INNER JOIN active_membership
    ON active_membership.provider_listing_id = payload_a.provider_listing_id
   AND active_membership.target_slot = 'A'
UNION ALL
SELECT
    payload_b.provider_listing_id,
    payload_b.trading_date,
    payload_b.relative_strength_benchmark_provider_listing_id,
    payload_b.history_observation_count,
    payload_b.calculation_version,
    payload_b.run_id,
    payload_b.calculated_at,
    payload_b.created_at,
    payload_b.updated_at,
    payload_b.open,
    payload_b.high,
    payload_b.low,
    payload_b.close,
    payload_b.volume,
    payload_b.return_1d_pct,
    payload_b.return_2d_pct,
    payload_b.return_3d_pct,
    payload_b.return_5d_pct,
    payload_b.return_10d_pct,
    payload_b.return_20d_pct,
    payload_b.return_63d_pct,
    payload_b.return_126d_pct,
    payload_b.return_252d_pct,
    payload_b.gap_1d_pct,
    payload_b.sma_20,
    payload_b.sma_50,
    payload_b.sma_200,
    payload_b.ema_12,
    payload_b.ema_20,
    payload_b.ema_26,
    payload_b.ema_50,
    payload_b.sma_50_change_20d_pct,
    payload_b.sma_200_change_20d_pct,
    payload_b.hh_20,
    payload_b.hh_50,
    payload_b.hh_252,
    payload_b.ll_20,
    payload_b.ll_50,
    payload_b.rsi_14,
    payload_b.atr_14,
    payload_b.return_volatility_20d_pct,
    payload_b.return_volatility_60d_pct,
    payload_b.return_1d_zscore_20d,
    payload_b.return_3d_zscore_20d,
    payload_b.price_stddev_20,
    payload_b.plus_di_14,
    payload_b.minus_di_14,
    payload_b.adx_14,
    payload_b.macd_12_26,
    payload_b.macd_signal_12_26_9,
    payload_b.macd_histogram_12_26_9,
    payload_b.volume_avg_20,
    payload_b.volume_avg_60,
    payload_b.dollar_volume_avg_20,
    payload_b.consecutive_up_days,
    payload_b.consecutive_down_days,
    payload_b.rel_spx,
    payload_b.pct_rel_spx_20,
    payload_b.pct_rel_spx_50,
    payload_b.relative_return_spx_20d_pct,
    payload_b.relative_return_spx_63d_pct,
    payload_b.relative_return_spx_126d_pct,
    payload_b.relative_return_spx_252d_pct,
    payload_b.spx_beta_60d,
    payload_b.spx_beta_252d,
    payload_b.spx_correlation_60d,
    payload_b.spx_correlation_252d,
    payload_b.dollar_volume,
    payload_b.intraday_return_1d_pct,
    payload_b.daily_range_pct,
    payload_b.close_location_1d,
    payload_b.pct_sma_20,
    payload_b.pct_sma_50,
    payload_b.pct_sma_200,
    payload_b.pct_ema_20,
    payload_b.pct_ema_50,
    payload_b.pct_sma_20_vs_50,
    payload_b.pct_sma_20_vs_200,
    payload_b.pct_sma_50_vs_200,
    payload_b.pct_hh_20,
    payload_b.pct_hh_50,
    payload_b.pct_hh_252,
    payload_b.pct_ll_20,
    payload_b.pct_ll_50,
    payload_b.atr_pct_14,
    payload_b.bollinger_percent_b_20_2,
    payload_b.bollinger_bandwidth_20_2,
    payload_b.volume_ratio_20,
    payload_b.macd_12_26_pct,
    payload_b.macd_histogram_12_26_9_pct
FROM stonks.ohlcv_daily_tech_indicators_b AS payload_b
INNER JOIN active_membership
    ON active_membership.provider_listing_id = payload_b.provider_listing_id
   AND active_membership.target_slot = 'B';

-- ---------------------------------------------------------------------
-- Relation and column documentation
-- ---------------------------------------------------------------------

COMMENT ON TABLE stonks.ohlcv_daily_tech_indicators_a IS
    'Physical provider-native daily tech-indicator payload slot; package-written, current-state data selected through stonks.ohlcv_daily_tech_indicators.';
COMMENT ON TABLE stonks.ohlcv_daily_tech_indicators_b IS
    'Physical provider-native daily tech-indicator payload slot; package-written, current-state data selected through stonks.ohlcv_daily_tech_indicators.';
COMMENT ON TABLE stonks.tech_indicators_publication IS
    'Candidate and published lifecycle facts for atomic provider-native tech-indicator publication units.';
COMMENT ON TABLE stonks.tech_indicators_publication_listing IS
    'Per-publication provider-listing action, complete slot image, and active published membership facts.';
COMMENT ON VIEW stonks.ohlcv_daily_tech_indicators IS
    'Read-only published provider-native daily tech-indicator rows selected by active complete per-listing publication membership.';

DO $tech_comments$
DECLARE
    target_table TEXT;
    comment_column_name TEXT;
    item RECORD;
BEGIN
    FOR item IN
        SELECT columns, description
        FROM (
            VALUES
                (ARRAY['provider_listing_id'], 'Subject provider-listing UUID; source-row identity and ownership key.'),
                (ARRAY['trading_date'], 'Provider trading date; source-row identity and observation date.'),
                (ARRAY['relative_strength_benchmark_provider_listing_id'], 'Resolved SPX provider-listing UUID for supported subjects; null for unsupported subjects.'),
                (ARRAY['history_observation_count'], 'Positive chronological subject-observation count through this row.'),
                (ARRAY['calculation_version'], 'Immutable formula-profile identifier used to calculate this row.'),
                (ARRAY['run_id'], 'Nullable Core run UUID for the last calculation write; non-owning lineage.'),
                (ARRAY['calculated_at'], 'Time at which this row''s feature values were calculated.'),
                (ARRAY['created_at'], 'Time at which this physical payload row was created.'),
                (ARRAY['updated_at'], 'Time at which this physical payload row last changed equivalently significant state.'),
                (ARRAY['open', 'high', 'low', 'close'], 'Exact provider-native source price copied from the owning OHLCV row.'),
                (ARRAY['volume'], 'Nullable provider-native source volume copied from the owning OHLCV row.'),
                (ARRAY['return_1d_pct', 'return_2d_pct', 'return_3d_pct', 'return_5d_pct', 'return_10d_pct', 'return_20d_pct', 'return_63d_pct', 'return_126d_pct', 'return_252d_pct', 'gap_1d_pct'], 'Python-calculated decimal return ratio; 0.05 means five percent.'),
                (ARRAY['sma_20', 'sma_50', 'sma_200', 'ema_12', 'ema_20', 'ema_26', 'ema_50', 'hh_20', 'hh_50', 'hh_252', 'll_20', 'll_50'], 'Python-calculated provider-native price-level feature.'),
                (ARRAY['sma_50_change_20d_pct', 'sma_200_change_20d_pct'], 'Python-calculated 20-observation moving-average change ratio.'),
                (ARRAY['rsi_14', 'plus_di_14', 'minus_di_14', 'adx_14'], 'Python-calculated pinned TA-Lib point-scale feature.'),
                (ARRAY['atr_14', 'price_stddev_20', 'macd_12_26', 'macd_signal_12_26_9', 'macd_histogram_12_26_9'], 'Python-calculated provider-native price-distance feature.'),
                (ARRAY['return_volatility_20d_pct', 'return_volatility_60d_pct'], 'Python-calculated non-annualized sample standard deviation of decimal returns.'),
                (ARRAY['return_1d_zscore_20d', 'return_3d_zscore_20d'], 'Python-calculated signed standard-deviation units against the prior 20 returns.'),
                (ARRAY['volume_avg_20', 'volume_avg_60'], 'Python-calculated complete-window provider-native volume average.'),
                (ARRAY['dollar_volume_avg_20'], 'Python-calculated nominal provider-native price-times-volume average; not necessarily USD.'),
                (ARRAY['consecutive_up_days', 'consecutive_down_days'], 'Python-calculated nonnegative current observation streak count.'),
                (ARRAY['rel_spx'], 'Python-calculated exact-date aligned subject-close to SPX-close ratio.'),
                (ARRAY['pct_rel_spx_20', 'pct_rel_spx_50'], 'Python-calculated aligned SPX price-ratio trend distance.'),
                (ARRAY['relative_return_spx_20d_pct', 'relative_return_spx_63d_pct', 'relative_return_spx_126d_pct', 'relative_return_spx_252d_pct'], 'Python-calculated compounded exact-date aligned subject-versus-SPX return ratio.'),
                (ARRAY['spx_beta_60d', 'spx_beta_252d'], 'Python-calculated sample-covariance beta over complete aligned returns.'),
                (ARRAY['spx_correlation_60d', 'spx_correlation_252d'], 'Python-calculated Pearson correlation over complete aligned returns.'),
                (ARRAY['dollar_volume'], 'PostgreSQL-generated absolute close times volume; nominal provider-native units, not necessarily USD.'),
                (ARRAY['intraday_return_1d_pct', 'daily_range_pct', 'pct_sma_20', 'pct_sma_50', 'pct_sma_200', 'pct_ema_20', 'pct_ema_50', 'pct_sma_20_vs_50', 'pct_sma_20_vs_200', 'pct_sma_50_vs_200', 'pct_hh_20', 'pct_hh_50', 'pct_hh_252', 'pct_ll_20', 'pct_ll_50', 'atr_pct_14', 'macd_12_26_pct', 'macd_histogram_12_26_9_pct'], 'PostgreSQL-generated decimal ratio using exact-zero denominator nulling.'),
                (ARRAY['close_location_1d'], 'PostgreSQL-generated close location within the same-row high-low range.'),
                (ARRAY['bollinger_percent_b_20_2'], 'PostgreSQL-generated location within reconstructed 20-observation, two-standard-deviation bands.'),
                (ARRAY['bollinger_bandwidth_20_2'], 'PostgreSQL-generated reconstructed band width divided by absolute SMA 20.'),
                (ARRAY['volume_ratio_20'], 'PostgreSQL-generated current volume divided by 20-observation average volume.')
        ) AS payload_comments(columns, description)
    LOOP
        FOREACH target_table IN ARRAY ARRAY[
            'ohlcv_daily_tech_indicators_a',
            'ohlcv_daily_tech_indicators_b'
        ]
        LOOP
            FOREACH comment_column_name IN ARRAY item.columns
            LOOP
                EXECUTE format(
                    'COMMENT ON COLUMN stonks.%I.%I IS %L',
                    target_table,
                    comment_column_name,
                    item.description
                );
            END LOOP;
        END LOOP;
    END LOOP;

    FOR item IN
        SELECT publication_comments.column_name,
               publication_comments.description
        FROM (
            VALUES
                ('publication_id', 'Publication UUID and lifecycle identity.'),
                ('publication_kind', 'Exact DAILY, CORRECTION, VERSION_REBUILD, BACKFILL, or ELIGIBILITY_REMOVAL unit kind.'),
                ('status', 'One-way BUILDING, PREPARED, PUBLISHED, FAILED, ABANDONED, or RETIRED lifecycle status.'),
                ('calculation_version', 'Immutable formula-profile identifier for the publication unit.'),
                ('publication_method', 'Resolved IN_PLACE, STAGED, or MEMBERSHIP_ONLY publication method.'),
                ('scope_schema_version', 'Canonical resolved-scope schema version; V1 is 1.'),
                ('scope_hash', 'Lowercase SHA-256 of canonical resolved-scope JSON.'),
                ('effective_date', 'Effective trading date for DAILY or date-scoped CORRECTION work.'),
                ('requested_start_date', 'Inclusive requested start date; null when not applicable.'),
                ('requested_end_date', 'Inclusive requested end date; null when not applicable.'),
                ('run_id', 'Nullable cleanup-safe Core run evidence for this publication.'),
                ('benchmark_required', 'Whether the complete publication scope requires reviewed SPX benchmark data.'),
                ('benchmark_provider_listing_id', 'Resolved reviewed SPX provider-listing UUID for this publication.'),
                ('benchmark_contract_version', 'Benchmark contract identity; V1 is TECH_INDICATORS_SPX_V1.'),
                ('benchmark_coverage_start_date', 'First exact SPX source date used by the complete candidate.'),
                ('benchmark_coverage_end_date', 'Last exact SPX source date used by the complete candidate.'),
                ('benchmark_source_row_count', 'Complete SPX source-row count used by the candidate.'),
                ('expected_listing_count', 'Expected complete provider-listing count for the prepared unit.'),
                ('expected_source_row_count', 'Expected complete source-row count for the prepared unit.'),
                ('expected_payload_row_count', 'Expected complete payload-row count for the prepared unit.'),
                ('inserted_row_count', 'Known count of payload rows inserted by the publication.'),
                ('updated_row_count', 'Known count of payload rows updated by the publication.'),
                ('deleted_row_count', 'Known count of payload rows deleted by the publication.'),
                ('equivalent_row_count', 'Known count of validated equivalent payload rows.'),
                ('warning_count', 'Known bounded warning count for the publication.'),
                ('failure_count', 'Known failure count for the publication.'),
                ('completed_batch_count', 'Cumulative count of committed staged batches.'),
                ('staged_payload_row_count', 'Cumulative count of payload rows committed to inactive slots.'),
                ('resume_provider_listing_id', 'Immutable provider-listing component of the latest committed staged cursor.'),
                ('resume_trading_date', 'Trading-date component of the latest committed staged cursor.'),
                ('resume_cursor_updated_at', 'Time the latest committed staged cursor was recorded.'),
                ('json_report_object_id', 'Nullable cleanup-safe Core JSON report object evidence.'),
                ('pdf_report_object_id', 'Nullable cleanup-safe Core PDF report object evidence.'),
                ('source_validated_at', 'Time complete candidate/source comparison succeeded.'),
                ('prepared_at', 'Time the publication entered PREPARED.'),
                ('published_at', 'Time the publication entered PUBLISHED.'),
                ('failed_at', 'Time the publication entered FAILED.'),
                ('abandoned_at', 'Time the publication entered ABANDONED.'),
                ('retired_at', 'Time the publication entered RETIRED.'),
                ('created_at', 'Time the BUILDING publication row was created.'),
                ('updated_at', 'Time the publication lifecycle facts last changed.')
        ) AS publication_comments(column_name, description)
    LOOP
        EXECUTE format(
            'COMMENT ON COLUMN stonks.tech_indicators_publication.%I IS %L',
            item.column_name,
            item.description
        );
    END LOOP;

    FOR item IN
        SELECT membership_comments.column_name,
               membership_comments.description
        FROM (
            VALUES
                ('publication_id', 'Owning publication UUID for this provider-listing candidate membership.'),
                ('provider_listing_id', 'Provider-listing UUID whose complete image or removal is described.'),
                ('action', 'PRESENT selects a complete slot image; REMOVE suppresses older published payload.'),
                ('target_slot', 'Physical payload slot A or B for PRESENT; null for REMOVE.'),
                ('calculation_version', 'Formula-profile identifier matching the owning publication.'),
                ('source_coverage_start_date', 'First source date in the complete listing image.'),
                ('source_coverage_end_date', 'Last source date in the complete listing image.'),
                ('source_row_count', 'Complete source-row count for the listing image.'),
                ('payload_row_count', 'Complete payload-row count for the listing image.'),
                ('benchmark_provider_listing_id', 'Resolved SPX provider-listing UUID for a supported subject image.'),
                ('candidate_completed_at', 'Time complete candidate facts for this listing were validated.'),
                ('is_active', 'Whether this is the one active published membership for the provider listing.'),
                ('activated_at', 'Time this membership became active.'),
                ('deactivated_at', 'Time this historical membership became inactive.'),
                ('created_at', 'Time the candidate membership row was created.'),
                ('updated_at', 'Time activation or deactivation facts last changed.')
        ) AS membership_comments(column_name, description)
    LOOP
        EXECUTE format(
            'COMMENT ON COLUMN stonks.tech_indicators_publication_listing.%I IS %L',
            item.column_name,
            item.description
        );
    END LOOP;
END;
$tech_comments$;
