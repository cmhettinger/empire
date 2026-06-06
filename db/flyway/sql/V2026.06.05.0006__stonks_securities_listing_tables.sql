-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_securities_listing_tables
--
-- Purpose:
--   Create canonical listing and listing symbol history tables for the
--   Empire security master.
--
-- Notes:
--   - Listing = a security traded on a venue/exchange.
--   - Ticker is not identity; ticker history is tracked separately.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Listings
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS listing (
    listing_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    security_id     UUID NOT NULL,
    exchange_id     UUID NOT NULL,

    current_ticker  TEXT,
    ticker_norm     TEXT,

    currency_code   VARCHAR(3),
    is_primary      BOOLEAN NOT NULL DEFAULT TRUE,

    status          VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    valid_from      DATE,
    valid_to        DATE,

    first_seen      DATE,
    last_seen       DATE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_listing_status
        CHECK (status IN (
            'ACTIVE',
            'INACTIVE',
            'DELISTING_NOTICE',
            'DELISTED',
            'MERGED',
            'TRANSFERRED',
            'UNKNOWN'
        )),

    CONSTRAINT ck_listing_dates
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),

    CONSTRAINT fk_listing_security
        FOREIGN KEY (security_id)
        REFERENCES security(security_id),

    CONSTRAINT fk_listing_exchange
        FOREIGN KEY (exchange_id)
        REFERENCES exchange(exchange_id),

    CONSTRAINT fk_listing_currency
        FOREIGN KEY (currency_code)
        REFERENCES iso4217_currency(code)
);

CREATE INDEX IF NOT EXISTS ix_listing_security
    ON listing (security_id);

CREATE INDEX IF NOT EXISTS ix_listing_exchange
    ON listing (exchange_id);

CREATE INDEX IF NOT EXISTS ix_listing_currency
    ON listing (currency_code);

CREATE INDEX IF NOT EXISTS ix_listing_ticker_norm
    ON listing (ticker_norm);

CREATE INDEX IF NOT EXISTS ix_listing_status
    ON listing (status);

CREATE UNIQUE INDEX IF NOT EXISTS ux_listing_active_lookup
    ON listing (exchange_id, ticker_norm)
    WHERE valid_to IS NULL
      AND ticker_norm IS NOT NULL;

-- ---------------------------------------------------------------------
-- Listing symbol history
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS listing_symbol_history (
    listing_symbol_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    listing_id        UUID NOT NULL,

    ticker_raw        TEXT NOT NULL,
    ticker_norm       TEXT NOT NULL,
    ticker_display    TEXT,

    valid_from        DATE,
    valid_to          DATE,

    source_code       VARCHAR(32),
    confidence_code   VARCHAR(16) NOT NULL DEFAULT 'HIGH',

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_listing_symbol_source_upper
        CHECK (source_code IS NULL OR source_code = UPPER(source_code)),

    CONSTRAINT ck_listing_symbol_dates
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),

    CONSTRAINT fk_listing_symbol_listing
        FOREIGN KEY (listing_id)
        REFERENCES listing(listing_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_listing_symbol_confidence
        FOREIGN KEY (confidence_code)
        REFERENCES confidence_level(confidence_code),

    CONSTRAINT uq_listing_symbol_history
        UNIQUE (listing_id, ticker_norm, valid_from)
);

CREATE INDEX IF NOT EXISTS ix_listing_symbol_listing
    ON listing_symbol_history (listing_id);

CREATE INDEX IF NOT EXISTS ix_listing_symbol_ticker
    ON listing_symbol_history (ticker_norm);

CREATE INDEX IF NOT EXISTS ix_listing_symbol_active
    ON listing_symbol_history (ticker_norm)
    WHERE valid_to IS NULL;
