-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_securities_reference_tables
--
-- Purpose:
--   Create reference tables used by the Empire security master.
--
-- Notes:
--   - DDL only.
--   - Seed data is loaded in a later versioned migration.
--   - No repeatable migrations (R__).
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS stonks;

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- ISO 3166-1 Countries
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS iso3166_country (
    alpha2   VARCHAR(2) PRIMARY KEY,
    alpha3   VARCHAR(3) NOT NULL UNIQUE,
    numeric3 VARCHAR(3) NOT NULL UNIQUE,
    name      TEXT NOT NULL,

    CONSTRAINT ck_iso3166_alpha2_upper
        CHECK (alpha2 = UPPER(alpha2)),

    CONSTRAINT ck_iso3166_alpha3_upper
        CHECK (alpha3 = UPPER(alpha3)),

    CONSTRAINT ck_iso3166_numeric3
        CHECK (numeric3 ~ '^[0-9]{3}$')
);

-- ---------------------------------------------------------------------
-- ISO 4217 Currencies
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS iso4217_currency (
    code       VARCHAR(3) PRIMARY KEY,
    numeric3   VARCHAR(3) NOT NULL,
    name        TEXT NOT NULL,
    minor_unit SMALLINT,

    CONSTRAINT ck_iso4217_code_upper
        CHECK (code = UPPER(code)),

    CONSTRAINT ck_iso4217_numeric3
        CHECK (numeric3 ~ '^[0-9]{3}$')
);

CREATE INDEX IF NOT EXISTS ix_iso4217_numeric3
    ON iso4217_currency (numeric3);

-- ---------------------------------------------------------------------
-- ISO 10383 MIC Categories
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS iso10383_mic_cat (
    code        VARCHAR(4) PRIMARY KEY,
    description TEXT NOT NULL,

    CONSTRAINT ck_iso10383_mic_cat_code
        CHECK (code = UPPER(code))
);

-- ---------------------------------------------------------------------
-- ISO 10383 MIC Registry
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS iso10383_mic (
    mic                  VARCHAR(4) PRIMARY KEY,
    operating_mic        VARCHAR(4),
    mic_type             VARCHAR(4) NOT NULL,

    market_name          TEXT NOT NULL,
    legal_entity         TEXT,
    acronym              TEXT,
    city                 TEXT,

    country_alpha2       VARCHAR(2) NOT NULL,
    website              TEXT,

    market_category_code VARCHAR(4),
    status               TEXT,
    created_date         DATE,

    source               TEXT NOT NULL DEFAULT 'ISO',

    CONSTRAINT ck_iso10383_mic_upper
        CHECK (mic = UPPER(mic)),

    CONSTRAINT ck_iso10383_mic_type
        CHECK (mic_type IN ('OPRT', 'SGMT')),

    CONSTRAINT ck_iso10383_mic_source
        CHECK (source IN ('ISO', 'INTERNAL')),

    CONSTRAINT fk_iso10383_mic_country
        FOREIGN KEY (country_alpha2)
        REFERENCES iso3166_country(alpha2),

    CONSTRAINT fk_iso10383_mic_operating
        FOREIGN KEY (operating_mic)
        REFERENCES iso10383_mic(mic)
        DEFERRABLE INITIALLY DEFERRED,

    CONSTRAINT fk_iso10383_mic_category
        FOREIGN KEY (market_category_code)
        REFERENCES iso10383_mic_cat(code)
);

CREATE INDEX IF NOT EXISTS ix_iso10383_mic_operating
    ON iso10383_mic (operating_mic);

CREATE INDEX IF NOT EXISTS ix_iso10383_mic_country
    ON iso10383_mic (country_alpha2);

CREATE INDEX IF NOT EXISTS ix_iso10383_mic_category
    ON iso10383_mic (market_category_code);

CREATE INDEX IF NOT EXISTS ix_iso10383_mic_source
    ON iso10383_mic (source);

-- ---------------------------------------------------------------------
-- Instrument Classes
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS instrument_class (
    class_code  VARCHAR(32) PRIMARY KEY,
    class_name  TEXT NOT NULL,
    description TEXT,
    sort_order  SMALLINT NOT NULL DEFAULT 100,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT ck_instrument_class_code
        CHECK (class_code = UPPER(class_code))
);

-- ---------------------------------------------------------------------
-- Instrument Types
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS instrument_type (
    type_code   VARCHAR(32) PRIMARY KEY,
    class_code  VARCHAR(32) NOT NULL,
    type_name   TEXT NOT NULL,
    description TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT ck_instrument_type_code
        CHECK (type_code = UPPER(type_code)),

    CONSTRAINT fk_instrument_type_class
        FOREIGN KEY (class_code)
        REFERENCES instrument_class(class_code)
);

CREATE INDEX IF NOT EXISTS ix_instrument_type_class
    ON instrument_type (class_code);

-- ---------------------------------------------------------------------
-- Confidence Levels
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS confidence_level (
    confidence_code VARCHAR(16) PRIMARY KEY,
    rank            SMALLINT NOT NULL,
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT ck_confidence_level_code
        CHECK (confidence_code = UPPER(confidence_code)),

    CONSTRAINT uq_confidence_level_rank
        UNIQUE (rank)
);