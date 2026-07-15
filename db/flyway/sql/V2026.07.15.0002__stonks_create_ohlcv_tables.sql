-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_create_ohlcv_tables
--
-- Purpose:
--   Store provider-native listing series and their current daily OHLCV
--   values without asserting canonical listing identity.
--
-- Notes:
--   - Provider listing identity is exact and case-sensitive.
--   - Daily bars retain current provider values, not revision history.
--   - Core runs and source snapshots are intentionally not linked per row.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Provider-native listing series
-- ---------------------------------------------------------------------

CREATE TABLE provider_listing (
    provider_listing_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    provider_code        VARCHAR(32) NOT NULL,
    market               TEXT NOT NULL,
    ticker               TEXT NOT NULL,
    name                 TEXT NULL,
    instrument_type_code VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',

    first_seen           DATE NULL,
    last_seen            DATE NULL,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_provider_listing_market
        CHECK (market <> '' AND market = btrim(market)),

    CONSTRAINT ck_provider_listing_ticker
        CHECK (ticker <> '' AND ticker = btrim(ticker)),

    CONSTRAINT ck_provider_listing_seen_dates
        CHECK (
            (first_seen IS NULL AND last_seen IS NULL)
            OR (
                first_seen IS NOT NULL
                AND last_seen IS NOT NULL
                AND last_seen >= first_seen
            )
        ),

    CONSTRAINT fk_provider_listing_provider
        FOREIGN KEY (provider_code)
        REFERENCES stonks.provider(provider_code),

    CONSTRAINT fk_provider_listing_instrument_type
        FOREIGN KEY (instrument_type_code)
        REFERENCES stonks.instrument_type(type_code),

    CONSTRAINT uq_provider_listing_identity
        UNIQUE (provider_code, market, ticker)
);

CREATE INDEX ix_provider_listing_provider_last_seen
    ON provider_listing (provider_code, last_seen DESC)
    WHERE last_seen IS NOT NULL;

-- ---------------------------------------------------------------------
-- Current provider-native daily bars
-- ---------------------------------------------------------------------

CREATE TABLE ohlcv_daily (
    provider_listing_id UUID NOT NULL,
    trading_date        DATE NOT NULL,

    open                NUMERIC(30,10) NOT NULL,
    high                NUMERIC(30,10) NOT NULL,
    low                 NUMERIC(30,10) NOT NULL,
    close               NUMERIC(30,10) NOT NULL,
    volume              NUMERIC(30,8) NULL,

    change              NUMERIC(30,8) NULL,
    changepct           NUMERIC(30,8) NULL,
    typ                 NUMERIC(30,8) NOT NULL,
    hl_range            NUMERIC(30,8) NOT NULL,
    oc_range            NUMERIC(30,8) NOT NULL,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_ohlcv_daily
        PRIMARY KEY (provider_listing_id, trading_date),

    CONSTRAINT ck_ohlcv_daily_numeric_not_nan
        CHECK (
            open <> 'NaN'::numeric
            AND high <> 'NaN'::numeric
            AND low <> 'NaN'::numeric
            AND close <> 'NaN'::numeric
            AND (volume IS NULL OR volume <> 'NaN'::numeric)
            AND (change IS NULL OR change <> 'NaN'::numeric)
            AND (changepct IS NULL OR changepct <> 'NaN'::numeric)
            AND typ <> 'NaN'::numeric
            AND hl_range <> 'NaN'::numeric
            AND oc_range <> 'NaN'::numeric
        ),

    CONSTRAINT ck_ohlcv_daily_high_low
        CHECK (high >= low),

    CONSTRAINT ck_ohlcv_daily_high_bounds
        CHECK (high >= open AND high >= close),

    CONSTRAINT ck_ohlcv_daily_low_bounds
        CHECK (low <= open AND low <= close),

    CONSTRAINT ck_ohlcv_daily_volume_nonnegative
        CHECK (volume IS NULL OR volume >= 0),

    CONSTRAINT ck_ohlcv_daily_changepct_requires_change
        CHECK (change IS NOT NULL OR changepct IS NULL),

    CONSTRAINT ck_ohlcv_daily_typ
        CHECK (typ = round((high + low + close) / 3, 8)),

    CONSTRAINT ck_ohlcv_daily_hl_range
        CHECK (hl_range = round(high - low, 8)),

    CONSTRAINT ck_ohlcv_daily_oc_range
        CHECK (oc_range = round(close - open, 8)),

    CONSTRAINT fk_ohlcv_daily_provider_listing
        FOREIGN KEY (provider_listing_id)
        REFERENCES stonks.provider_listing(provider_listing_id)
        ON DELETE CASCADE
);

CREATE INDEX ix_ohlcv_daily_trading_date
    ON ohlcv_daily (trading_date DESC, provider_listing_id);
