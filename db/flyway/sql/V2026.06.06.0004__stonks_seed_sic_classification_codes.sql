-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_seed_sic_classification_codes
--
-- Purpose:
--   Seed SEC Standard Industrial Classification (SIC) codes into the
--   Empire security-master classification reference table.
--
-- Inputs:
--   /seed/sec_sic_codes.csv
--
-- Source:
--   SEC Standard Industrial Classification (SIC) Code List
--   https://www.sec.gov/search-filings/standard-industrial-classification-sic-code-list
--
-- Notes:
--   - Seeds only class_system = 'SIC'.
--   - SIC codes are preserved exactly as published by the SEC list.
--   - SEC Corp Fin office assignment is retained in description.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- SEC SIC codes
-- ---------------------------------------------------------------------

CREATE UNLOGGED TABLE IF NOT EXISTS stg_sec_sic_classification_code (
    sic_code       TEXT,
    office         TEXT,
    industry_title TEXT
);

TRUNCATE TABLE stg_sec_sic_classification_code;

COPY stg_sec_sic_classification_code (
    sic_code,
    office,
    industry_title
)
FROM '/seed/sec_sic_codes.csv'
WITH (FORMAT csv, HEADER true);

WITH cleaned AS (
    SELECT
        TRIM(sic_code) AS code,
        NULLIF(TRIM(office), '') AS office,
        TRIM(industry_title) AS label
    FROM stg_sec_sic_classification_code
    WHERE
        NULLIF(TRIM(sic_code), '') IS NOT NULL
        AND TRIM(sic_code) ~ '^[0-9]+$'
        AND NULLIF(TRIM(industry_title), '') IS NOT NULL
),
deduped AS (
    SELECT DISTINCT ON (code)
        code,
        label,
        office
    FROM cleaned
    ORDER BY code, label
)
INSERT INTO classification_code (
    class_system,
    code,
    label,
    description,
    is_active
)
SELECT
    'SIC',
    code,
    label,
    CASE
        WHEN office IS NULL THEN 'SEC SIC industry title: ' || label
        ELSE 'SEC SIC industry title: ' || label || '; SEC Corp Fin office: ' || office
    END,
    TRUE
FROM deduped
ON CONFLICT (class_system, code) DO UPDATE
SET
    label       = EXCLUDED.label,
    description = EXCLUDED.description,
    is_active   = TRUE;
