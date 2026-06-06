-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_securities_provider_identifier_classification_refs
--
-- Purpose:
--   Add provider, identifier type, and classification system reference
--   tables for the Empire security master.
--
-- Notes:
--   - Existing source_code columns are retained for now.
--   - Provider-backed source_code foreign keys do not cascade deletes.
--   - Seed data uses idempotent upserts.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Providers / data sources
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS provider (
    provider_code VARCHAR(32) PRIMARY KEY,
    provider_name TEXT NOT NULL,
    provider_type VARCHAR(32) NOT NULL,
    website       TEXT,
    description   TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT ck_provider_code_upper
        CHECK (provider_code = UPPER(provider_code)),

    CONSTRAINT ck_provider_type_upper
        CHECK (provider_type = UPPER(provider_type))
);

INSERT INTO provider (
    provider_code,
    provider_name,
    provider_type,
    website,
    description
)
VALUES
    ('SEC', 'U.S. Securities and Exchange Commission', 'REGULATOR', 'https://www.sec.gov/', 'U.S. securities filings and regulatory reference data'),
    ('ISO', 'International Organization for Standardization', 'STANDARDS_BODY', 'https://www.iso.org/', 'International standards reference data'),
    ('INTERNAL', 'Empire Internal', 'INTERNAL', NULL, 'Empire-owned derived or curated reference data'),
    ('MANUAL', 'Manual Review', 'MANUAL', NULL, 'Human-reviewed corrections and overrides'),
    ('CENSUS', 'U.S. Census Bureau', 'GOVERNMENT', 'https://www.census.gov/', 'U.S. Census Bureau reference data'),
    ('OTC_MARKETS', 'OTC Markets Group', 'MARKET_OPERATOR', 'https://www.otcmarkets.com/', 'OTC market and issuer reference data'),
    ('NASDAQ', 'Nasdaq', 'MARKET_OPERATOR', 'https://www.nasdaq.com/', 'Nasdaq exchange and listing reference data'),
    ('NYSE', 'New York Stock Exchange', 'MARKET_OPERATOR', 'https://www.nyse.com/', 'NYSE exchange and listing reference data'),
    ('CBOE', 'Cboe Global Markets', 'MARKET_OPERATOR', 'https://www.cboe.com/', 'Cboe exchange and listing reference data'),
    ('IEX', 'Investors Exchange', 'MARKET_OPERATOR', 'https://www.iexexchange.io/', 'IEX exchange and listing reference data')
ON CONFLICT (provider_code) DO UPDATE
SET
    provider_name = EXCLUDED.provider_name,
    provider_type = EXCLUDED.provider_type,
    website       = EXCLUDED.website,
    description   = EXCLUDED.description,
    is_active     = TRUE;

-- ---------------------------------------------------------------------
-- Identifier types
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS identifier_type (
    id_type     VARCHAR(32) PRIMARY KEY,
    id_name     TEXT NOT NULL,
    applies_to  VARCHAR(32) NOT NULL,
    description TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT ck_identifier_type_code_upper
        CHECK (id_type = UPPER(id_type)),

    CONSTRAINT ck_identifier_type_applies_to
        CHECK (applies_to IN ('ISSUER', 'SECURITY', 'LISTING', 'FILING', 'INTERNAL'))
);

INSERT INTO identifier_type (
    id_type,
    id_name,
    applies_to,
    description
)
VALUES
    ('CIK', 'Central Index Key', 'ISSUER', 'SEC registrant identifier'),
    ('CUSIP', 'CUSIP', 'SECURITY', 'CUSIP security identifier'),
    ('ISIN', 'International Securities Identification Number', 'SECURITY', 'ISO 6166 security identifier'),
    ('SEDOL', 'SEDOL', 'SECURITY', 'Stock Exchange Daily Official List identifier'),
    ('FIGI', 'Financial Instrument Global Identifier', 'SECURITY', 'OpenFIGI instrument identifier'),
    ('LEI', 'Legal Entity Identifier', 'ISSUER', 'ISO 17442 legal entity identifier'),
    ('EIN', 'Employer Identification Number', 'ISSUER', 'U.S. tax entity identifier'),
    ('SERIES_ID', 'SEC Series Identifier', 'SECURITY', 'SEC investment company series identifier'),
    ('CLASS_ID', 'SEC Class Identifier', 'SECURITY', 'SEC investment company class identifier'),
    ('TICKER', 'Ticker Symbol', 'LISTING', 'Exchange or venue ticker symbol'),
    ('ACCESSION_NO', 'SEC Accession Number', 'FILING', 'SEC filing accession number'),
    ('RSSD', 'RSSD ID', 'ISSUER', 'Federal Reserve financial institution identifier'),
    ('CIK_SERIES', 'CIK Series Composite', 'SECURITY', 'Composite SEC CIK and series identifier'),
    ('CIK_CLASS', 'CIK Class Composite', 'SECURITY', 'Composite SEC CIK and class identifier'),
    ('INTERNAL_ID', 'Empire Internal Identifier', 'INTERNAL', 'Empire-owned internal identifier')
ON CONFLICT (id_type) DO UPDATE
SET
    id_name     = EXCLUDED.id_name,
    applies_to  = EXCLUDED.applies_to,
    description = EXCLUDED.description,
    is_active   = TRUE;

-- ---------------------------------------------------------------------
-- Classification systems
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS classification_system (
    class_system VARCHAR(32) PRIMARY KEY,
    system_name  TEXT NOT NULL,
    provider_code VARCHAR(32),
    description  TEXT,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT ck_classification_system_code_upper
        CHECK (class_system = UPPER(class_system)),

    CONSTRAINT fk_classification_system_provider
        FOREIGN KEY (provider_code)
        REFERENCES provider(provider_code)
        ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_classification_system_provider
    ON classification_system (provider_code);

INSERT INTO classification_system (
    class_system,
    system_name,
    provider_code,
    description
)
VALUES
    ('SIC', 'Standard Industrial Classification', 'SEC', 'SEC industry classification codes'),
    ('NAICS', 'North American Industry Classification System', 'CENSUS', 'North American industry classification codes'),
    ('GICS', 'Global Industry Classification Standard', NULL, 'Global industry taxonomy for companies and securities'),
    ('ICB', 'Industry Classification Benchmark', NULL, 'Industry taxonomy for companies and securities'),
    ('SEC_FUND', 'SEC Fund Classification', 'SEC', 'SEC fund classification system'),
    ('INTERNAL', 'Empire Internal Classification', 'INTERNAL', 'Empire-owned classification system')
ON CONFLICT (class_system) DO UPDATE
SET
    system_name   = EXCLUDED.system_name,
    provider_code = EXCLUDED.provider_code,
    description   = EXCLUDED.description,
    is_active     = TRUE;

-- ---------------------------------------------------------------------
-- Identifier and classification foreign keys
-- ---------------------------------------------------------------------

ALTER TABLE classification_code
    ADD CONSTRAINT fk_classification_code_system
    FOREIGN KEY (class_system)
    REFERENCES classification_system(class_system)
    ON UPDATE CASCADE;

ALTER TABLE issuer_identifier
    ADD CONSTRAINT fk_issuer_identifier_type
    FOREIGN KEY (id_type)
    REFERENCES identifier_type(id_type)
    ON UPDATE CASCADE;

ALTER TABLE security_identifier
    ADD CONSTRAINT fk_security_identifier_type
    FOREIGN KEY (id_type)
    REFERENCES identifier_type(id_type)
    ON UPDATE CASCADE;

-- ---------------------------------------------------------------------
-- Provider-backed source_code foreign keys
-- ---------------------------------------------------------------------

ALTER TABLE issuer_classification
    ADD CONSTRAINT fk_issuer_class_provider
    FOREIGN KEY (source_code)
    REFERENCES provider(provider_code)
    ON UPDATE CASCADE;

ALTER TABLE issuer_identifier
    ADD CONSTRAINT fk_issuer_identifier_provider
    FOREIGN KEY (source_code)
    REFERENCES provider(provider_code)
    ON UPDATE CASCADE;

ALTER TABLE issuer_name_history
    ADD CONSTRAINT fk_issuer_name_provider
    FOREIGN KEY (source_code)
    REFERENCES provider(provider_code)
    ON UPDATE CASCADE;

ALTER TABLE listing_symbol_history
    ADD CONSTRAINT fk_listing_symbol_provider
    FOREIGN KEY (source_code)
    REFERENCES provider(provider_code)
    ON UPDATE CASCADE;

ALTER TABLE security_event
    ADD CONSTRAINT fk_security_event_provider
    FOREIGN KEY (source_code)
    REFERENCES provider(provider_code)
    ON UPDATE CASCADE;

ALTER TABLE security_identifier
    ADD CONSTRAINT fk_security_identifier_provider
    FOREIGN KEY (source_code)
    REFERENCES provider(provider_code)
    ON UPDATE CASCADE;

ALTER TABLE source_observation
    ADD CONSTRAINT fk_source_obs_provider
    FOREIGN KEY (source_code)
    REFERENCES provider(provider_code)
    ON UPDATE CASCADE;

ALTER TABLE exchange_alias
    ADD CONSTRAINT fk_exchange_alias_provider
    FOREIGN KEY (source_code)
    REFERENCES provider(provider_code)
    ON UPDATE CASCADE;

CREATE INDEX IF NOT EXISTS ix_issuer_class_source
    ON issuer_classification (source_code);

CREATE INDEX IF NOT EXISTS ix_issuer_identifier_source
    ON issuer_identifier (source_code);

CREATE INDEX IF NOT EXISTS ix_issuer_name_history_source
    ON issuer_name_history (source_code);

CREATE INDEX IF NOT EXISTS ix_listing_symbol_source
    ON listing_symbol_history (source_code);

CREATE INDEX IF NOT EXISTS ix_security_event_source
    ON security_event (source_code);

CREATE INDEX IF NOT EXISTS ix_security_identifier_source
    ON security_identifier (source_code);
