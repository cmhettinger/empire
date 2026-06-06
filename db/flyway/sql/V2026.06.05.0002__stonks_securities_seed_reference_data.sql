-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_securities_seed_reference_data
--
-- Purpose:
--   Seed reference data for the Empire security master.
--
-- Inputs:
--   /seed/iso3166_country.csv
--   /seed/iso4217_currency_codes.csv
--   /seed/iso10383_mic.csv
--
-- Notes:
--   - Versioned seed migration only.
--   - No repeatable R__ scripts.
--   - Uses staging tables + idempotent upserts.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- ISO 3166-1 countries
-- ---------------------------------------------------------------------

CREATE UNLOGGED TABLE IF NOT EXISTS stg_iso3166_country (
    name                      TEXT,
    alpha2                    TEXT,
    alpha3                    TEXT,
    country_code              TEXT,
    iso_3166_2                TEXT,
    region                    TEXT,
    sub_region                TEXT,
    intermediate_region       TEXT,
    region_code               TEXT,
    sub_region_code           TEXT,
    intermediate_region_code  TEXT
);

TRUNCATE TABLE stg_iso3166_country;

COPY stg_iso3166_country (
    name,
    alpha2,
    alpha3,
    country_code,
    iso_3166_2,
    region,
    sub_region,
    intermediate_region,
    region_code,
    sub_region_code,
    intermediate_region_code
)
FROM '/seed/iso3166_country.csv'
WITH (FORMAT csv, HEADER true);

INSERT INTO iso3166_country (alpha2, alpha3, numeric3, name)
SELECT
    UPPER(TRIM(alpha2)),
    UPPER(TRIM(alpha3)),
    LPAD(TRIM(country_code), 3, '0'),
    TRIM(name)
FROM stg_iso3166_country
WHERE
    NULLIF(TRIM(alpha2), '') IS NOT NULL
    AND NULLIF(TRIM(alpha3), '') IS NOT NULL
    AND NULLIF(TRIM(country_code), '') IS NOT NULL
    AND NULLIF(TRIM(name), '') IS NOT NULL
ON CONFLICT (alpha2) DO UPDATE
SET
    alpha3   = EXCLUDED.alpha3,
    numeric3 = EXCLUDED.numeric3,
    name     = EXCLUDED.name;

-- ---------------------------------------------------------------------
-- ISO 4217 currencies
-- ---------------------------------------------------------------------

CREATE UNLOGGED TABLE IF NOT EXISTS stg_iso4217_currency (
    entity           TEXT,
    currency         TEXT,
    alphabetic_code  TEXT,
    numeric_code     TEXT,
    minor_unit       TEXT,
    withdrawal_date  TEXT
);

TRUNCATE TABLE stg_iso4217_currency;

COPY stg_iso4217_currency (
    entity,
    currency,
    alphabetic_code,
    numeric_code,
    minor_unit,
    withdrawal_date
)
FROM '/seed/iso4217_currency_codes.csv'
WITH (FORMAT csv, HEADER true);

WITH cleaned AS (
    SELECT
        UPPER(TRIM(alphabetic_code)) AS code,
        LPAD(TRIM(numeric_code), 3, '0') AS numeric3,
        TRIM(currency) AS name,
        NULLIF(TRIM(withdrawal_date), '') AS withdrawal_date,
        CASE
            WHEN NULLIF(TRIM(minor_unit), '') IS NULL THEN NULL
            WHEN TRIM(minor_unit) = '-' THEN NULL
            ELSE TRIM(minor_unit)::SMALLINT
        END AS minor_unit
    FROM stg_iso4217_currency
    WHERE
        NULLIF(TRIM(alphabetic_code), '') IS NOT NULL
        AND NULLIF(TRIM(numeric_code), '') IS NOT NULL
        AND NULLIF(TRIM(currency), '') IS NOT NULL
        AND UPPER(TRIM(alphabetic_code)) NOT IN ('XXX', 'XTS')
),
deduped AS (
    SELECT DISTINCT ON (code)
        code,
        numeric3,
        name,
        minor_unit
    FROM cleaned
    ORDER BY
        code,
        (withdrawal_date IS NULL) DESC,
        (minor_unit IS NOT NULL) DESC,
        name ASC
)
INSERT INTO iso4217_currency (code, numeric3, name, minor_unit)
SELECT
    code,
    numeric3,
    name,
    minor_unit
FROM deduped
ON CONFLICT (code) DO UPDATE
SET
    numeric3   = EXCLUDED.numeric3,
    name       = EXCLUDED.name,
    minor_unit = EXCLUDED.minor_unit;

-- ---------------------------------------------------------------------
-- ISO 10383 MIC categories
-- ---------------------------------------------------------------------

INSERT INTO iso10383_mic_cat (code, description)
VALUES
    ('ATSS', 'Alternative Trading System'),
    ('APPA', 'Approved Publication Arrangement'),
    ('ARMS', 'Approved Reporting Mechanism'),
    ('CTPS', 'Consolidated Tape Provider'),
    ('CASP', 'Crypto Asset Services Provider'),
    ('DCMS', 'Designated Contract Market'),
    ('IDQS', 'Inter-Dealer Quotation System'),
    ('MLTF', 'Multilateral Trading Facility'),
    ('NSPD', 'Not Specified'),
    ('OTFS', 'Organised Trading Facility'),
    ('OTHR', 'Other'),
    ('RMOS', 'Recognised Market Operator'),
    ('RMKT', 'Regulated Market'),
    ('SEFS', 'Swap Execution Facility'),
    ('SINT', 'Systematic Internaliser'),
    ('TRFS', 'Trade Reporting Facility')
ON CONFLICT (code) DO UPDATE
SET
    description = EXCLUDED.description;

-- ---------------------------------------------------------------------
-- ISO 10383 MIC registry
-- ---------------------------------------------------------------------

CREATE UNLOGGED TABLE IF NOT EXISTS stg_iso10383_mic (
    mic                  TEXT,
    operating_mic        TEXT,
    oprt_sgmt            TEXT,
    market_name          TEXT,
    legal_entity_name    TEXT,
    lei                  TEXT,
    market_category_code TEXT,
    acronym              TEXT,
    iso_country_code     TEXT,
    city                 TEXT,
    website              TEXT,
    status               TEXT,
    creation_date        TEXT,
    last_update_date     TEXT,
    last_validation_date TEXT,
    expiry_date          TEXT,
    comments             TEXT
);

TRUNCATE TABLE stg_iso10383_mic;

COPY stg_iso10383_mic (
    mic,
    operating_mic,
    oprt_sgmt,
    market_name,
    legal_entity_name,
    lei,
    market_category_code,
    acronym,
    iso_country_code,
    city,
    website,
    status,
    creation_date,
    last_update_date,
    last_validation_date,
    expiry_date,
    comments
)
FROM '/seed/iso10383_mic.csv'
WITH (FORMAT csv, HEADER true, QUOTE '"');

WITH cleaned AS (
    SELECT
        UPPER(TRIM(mic)) AS mic,
        NULLIF(UPPER(TRIM(operating_mic)), '') AS operating_mic,
        UPPER(TRIM(oprt_sgmt)) AS mic_type,
        TRIM(market_name) AS market_name,
        NULLIF(TRIM(legal_entity_name), '') AS legal_entity,
        NULLIF(TRIM(acronym), '') AS acronym,
        NULLIF(TRIM(city), '') AS city,
        NULLIF(UPPER(TRIM(iso_country_code)), '') AS country_alpha2,
        NULLIF(TRIM(website), '') AS website,
        NULLIF(UPPER(TRIM(market_category_code)), '') AS market_category_code,
        NULLIF(UPPER(TRIM(status)), '') AS status,
        CASE
            WHEN NULLIF(TRIM(creation_date), '') IS NULL THEN NULL
            ELSE TO_DATE(TRIM(creation_date), 'YYYYMMDD')
        END AS created_date,
        CASE
            WHEN NULLIF(TRIM(last_update_date), '') IS NULL THEN NULL
            ELSE TO_DATE(TRIM(last_update_date), 'YYYYMMDD')
        END AS last_update_dt,
        CASE
            WHEN NULLIF(TRIM(expiry_date), '') IS NULL THEN NULL
            ELSE TO_DATE(TRIM(expiry_date), 'YYYYMMDD')
        END AS expiry_dt
    FROM stg_iso10383_mic
    WHERE NULLIF(TRIM(mic), '') IS NOT NULL
),
filtered AS (
    SELECT *
    FROM cleaned c
    WHERE
        c.mic_type IN ('OPRT', 'SGMT')
        AND NULLIF(c.market_name, '') IS NOT NULL
        AND c.country_alpha2 IS NOT NULL
        AND EXISTS (
            SELECT 1
            FROM iso3166_country cc
            WHERE cc.alpha2 = c.country_alpha2
        )
),
deduped AS (
    SELECT DISTINCT ON (mic)
        mic,
        operating_mic,
        mic_type,
        market_name,
        legal_entity,
        acronym,
        city,
        country_alpha2,
        website,
        market_category_code,
        status,
        created_date
    FROM filtered
    ORDER BY
        mic,
        (status = 'ACTIVE') DESC,
        last_update_dt DESC NULLS LAST,
        (expiry_dt IS NULL) DESC
)
INSERT INTO iso10383_mic (
    mic,
    operating_mic,
    mic_type,
    market_name,
    legal_entity,
    acronym,
    city,
    country_alpha2,
    website,
    market_category_code,
    status,
    created_date,
    source
)
SELECT
    mic,
    operating_mic,
    mic_type,
    market_name,
    legal_entity,
    acronym,
    city,
    country_alpha2,
    website,
    market_category_code,
    status,
    created_date,
    'ISO'
FROM deduped
ON CONFLICT (mic) DO UPDATE
SET
    operating_mic        = EXCLUDED.operating_mic,
    mic_type             = EXCLUDED.mic_type,
    market_name          = EXCLUDED.market_name,
    legal_entity         = EXCLUDED.legal_entity,
    acronym              = EXCLUDED.acronym,
    city                 = EXCLUDED.city,
    country_alpha2       = EXCLUDED.country_alpha2,
    website              = EXCLUDED.website,
    market_category_code = EXCLUDED.market_category_code,
    status               = EXCLUDED.status,
    created_date         = EXCLUDED.created_date,
    source               = 'ISO';

-- ---------------------------------------------------------------------
-- Instrument classes
-- ---------------------------------------------------------------------

INSERT INTO instrument_class (class_code, class_name, description, sort_order)
VALUES
    ('EQUITY', 'Equity', 'Equity securities and equity-like instruments', 10),
    ('FUND', 'Fund', 'Pooled vehicles such as ETFs, mutual funds, and closed-end funds', 20),
    ('INDEX', 'Index', 'Benchmarks and market indices', 30),
    ('DEBT', 'Debt', 'Debt securities such as notes and bonds', 40),
    ('DERIVATIVE', 'Derivative', 'Warrants, rights, options, futures, and similar instruments', 50),
    ('OTHER', 'Other', 'Other or uncategorized instruments', 90)
ON CONFLICT (class_code) DO UPDATE
SET
    class_name  = EXCLUDED.class_name,
    description = EXCLUDED.description,
    sort_order  = EXCLUDED.sort_order,
    is_active   = TRUE;

-- ---------------------------------------------------------------------
-- Instrument types
-- ---------------------------------------------------------------------

INSERT INTO instrument_type (type_code, class_code, type_name, description)
VALUES
    ('COMMON_STOCK', 'EQUITY', 'Common Stock', 'Ordinary common equity shares'),
    ('PREFERRED_STOCK', 'EQUITY', 'Preferred Stock', 'Preferred equity shares'),
    ('ADR', 'EQUITY', 'ADR', 'American Depositary Receipt'),
    ('ADS', 'EQUITY', 'ADS', 'American Depositary Share'),
    ('REIT', 'EQUITY', 'REIT', 'Real Estate Investment Trust equity'),
    ('UNIT', 'EQUITY', 'Unit', 'Unit security, often containing multiple components'),

    ('ETF', 'FUND', 'ETF', 'Exchange-traded fund'),
    ('MUTUAL_FUND', 'FUND', 'Mutual Fund', 'Open-end mutual fund'),
    ('CLOSED_END_FUND', 'FUND', 'Closed-End Fund', 'Closed-end fund'),
    ('ETN', 'FUND', 'ETN', 'Exchange-traded note'),

    ('PRICE_INDEX', 'INDEX', 'Price Index', 'Price-only benchmark index'),
    ('TOTAL_RETURN_INDEX', 'INDEX', 'Total Return Index', 'Total return benchmark index'),
    ('VOLATILITY_INDEX', 'INDEX', 'Volatility Index', 'Volatility benchmark index'),

    ('NOTE', 'DEBT', 'Note', 'Debt note'),
    ('BOND', 'DEBT', 'Bond', 'Bond security'),

    ('WARRANT', 'DERIVATIVE', 'Warrant', 'Equity warrant'),
    ('RIGHT', 'DERIVATIVE', 'Right', 'Subscription right'),
    ('OPTION', 'DERIVATIVE', 'Option', 'Option contract'),
    ('FUTURE', 'DERIVATIVE', 'Future', 'Futures contract'),

    ('UNKNOWN', 'OTHER', 'Unknown', 'Unknown instrument type'),
    ('OTHER', 'OTHER', 'Other', 'Other or uncategorized instrument type')
ON CONFLICT (type_code) DO UPDATE
SET
    class_code  = EXCLUDED.class_code,
    type_name   = EXCLUDED.type_name,
    description = EXCLUDED.description,
    is_active   = TRUE;

-- ---------------------------------------------------------------------
-- Confidence levels
-- ---------------------------------------------------------------------

INSERT INTO confidence_level (confidence_code, rank, description)
VALUES
    ('HIGH', 300, 'High confidence'),
    ('MEDIUM', 200, 'Medium confidence'),
    ('LOW', 100, 'Low confidence'),
    ('TRACE', 50, 'Trace or weak signal'),
    ('MANUAL', 400, 'Manual review or override'),
    ('CONFLICT', 10, 'Conflicting evidence')
ON CONFLICT (confidence_code) DO UPDATE
SET
    rank        = EXCLUDED.rank,
    description = EXCLUDED.description,
    is_active   = TRUE;