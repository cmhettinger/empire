-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_securities_exchange_tables
--
-- Purpose:
--   Create exchange / venue tables for the Empire security master.
--
-- Notes:
--   - ISO MIC rows stay pure in iso10383_mic.
--   - Synthetic/internal venues live here, not in iso10383_mic.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Exchanges / venues
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS exchange (
    exchange_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    exchange_code  VARCHAR(16) NOT NULL UNIQUE,
    exchange_name  TEXT        NOT NULL,

    mic            VARCHAR(4),
    country_alpha2 VARCHAR(2),

    exchange_type  VARCHAR(24) NOT NULL DEFAULT 'EXCHANGE',
    is_synthetic   BOOLEAN     NOT NULL DEFAULT FALSE,
    is_active      BOOLEAN     NOT NULL DEFAULT TRUE,

    notes          TEXT,

    CONSTRAINT ck_exchange_code_upper
        CHECK (exchange_code = UPPER(exchange_code)),

    CONSTRAINT ck_exchange_type
        CHECK (exchange_type IN (
            'EXCHANGE',
            'ATS',
            'OTC',
            'INDEX',
            'SYNTHETIC',
            'UNKNOWN'
        )),

    CONSTRAINT fk_exchange_mic
        FOREIGN KEY (mic)
        REFERENCES iso10383_mic(mic),

    CONSTRAINT fk_exchange_country
        FOREIGN KEY (country_alpha2)
        REFERENCES iso3166_country(alpha2)
);

CREATE INDEX IF NOT EXISTS ix_exchange_mic
    ON exchange (mic);

CREATE INDEX IF NOT EXISTS ix_exchange_country
    ON exchange (country_alpha2);

CREATE INDEX IF NOT EXISTS ix_exchange_type
    ON exchange (exchange_type);

-- ---------------------------------------------------------------------
-- Exchange aliases
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS exchange_alias (
    exchange_alias_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    exchange_id       UUID NOT NULL,
    source_code       VARCHAR(32) NOT NULL,
    raw_name          TEXT NOT NULL,
    normalized_name   TEXT,

    is_active         BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_exchange_alias_exchange
        FOREIGN KEY (exchange_id)
        REFERENCES exchange(exchange_id)
        ON DELETE CASCADE,

    CONSTRAINT ck_exchange_alias_source_upper
        CHECK (source_code = UPPER(source_code)),

    CONSTRAINT uq_exchange_alias_source_raw
        UNIQUE (source_code, raw_name)
);

CREATE INDEX IF NOT EXISTS ix_exchange_alias_exchange
    ON exchange_alias (exchange_id);

CREATE INDEX IF NOT EXISTS ix_exchange_alias_source
    ON exchange_alias (source_code);