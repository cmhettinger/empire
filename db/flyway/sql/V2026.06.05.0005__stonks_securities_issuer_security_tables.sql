-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_securities_issuer_security_tables
--
-- Purpose:
--   Create canonical issuer and security tables for the Empire security
--   master.
--
-- Notes:
--   - Issuer = legal/reporting entity.
--   - Security = financial instrument issued by an issuer.
--   - Listings are created in a later migration.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Issuers
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS issuer (
    issuer_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    cik            VARCHAR(10),
    issuer_type    VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
    current_name   TEXT NOT NULL,

    country_alpha2 VARCHAR(2),
    sic_code       VARCHAR(4),

    status         VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
    first_seen     DATE,
    last_seen      DATE,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_issuer_cik
        CHECK (cik IS NULL OR cik ~ '^[0-9]{10}$'),

    CONSTRAINT ck_issuer_type
        CHECK (issuer_type IN (
            'OPERATING_COMPANY',
            'FUND_SPONSOR',
            'FUND_REGISTRANT',
            'TRUST',
            'GOVERNMENT',
            'INDEX_PROVIDER',
            'UNKNOWN'
        )),

    CONSTRAINT ck_issuer_status
        CHECK (status IN (
            'ACTIVE',
            'INACTIVE',
            'MERGED',
            'ACQUIRED',
            'LIQUIDATED',
            'UNKNOWN'
        )),

    CONSTRAINT fk_issuer_country
        FOREIGN KEY (country_alpha2)
        REFERENCES iso3166_country(alpha2)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_issuer_cik
    ON issuer (cik)
    WHERE cik IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_issuer_name
    ON issuer (current_name);

CREATE INDEX IF NOT EXISTS ix_issuer_country
    ON issuer (country_alpha2);

CREATE INDEX IF NOT EXISTS ix_issuer_type
    ON issuer (issuer_type);

CREATE INDEX IF NOT EXISTS ix_issuer_status
    ON issuer (status);

-- ---------------------------------------------------------------------
-- Issuer identifiers
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS issuer_identifier (
    issuer_identifier_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    issuer_id        UUID NOT NULL,
    id_type          VARCHAR(32) NOT NULL,
    id_value         TEXT NOT NULL,

    valid_from       DATE,
    valid_to         DATE,
    source_code      VARCHAR(32),
    confidence_code  VARCHAR(16) NOT NULL DEFAULT 'HIGH',

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_issuer_identifier_type_upper
        CHECK (id_type = UPPER(id_type)),

    CONSTRAINT ck_issuer_identifier_source_upper
        CHECK (source_code IS NULL OR source_code = UPPER(source_code)),

    CONSTRAINT ck_issuer_identifier_dates
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),

    CONSTRAINT fk_issuer_identifier_issuer
        FOREIGN KEY (issuer_id)
        REFERENCES issuer(issuer_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_issuer_identifier_confidence
        FOREIGN KEY (confidence_code)
        REFERENCES confidence_level(confidence_code),

    CONSTRAINT uq_issuer_identifier
        UNIQUE (id_type, id_value, issuer_id)
);

CREATE INDEX IF NOT EXISTS ix_issuer_identifier_issuer
    ON issuer_identifier (issuer_id);

CREATE INDEX IF NOT EXISTS ix_issuer_identifier_lookup
    ON issuer_identifier (id_type, id_value);

-- ---------------------------------------------------------------------
-- Issuer name history
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS issuer_name_history (
    issuer_name_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    issuer_id       UUID NOT NULL,
    name            TEXT NOT NULL,

    valid_from      DATE,
    valid_to        DATE,
    source_code     VARCHAR(32),
    confidence_code VARCHAR(16) NOT NULL DEFAULT 'HIGH',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_issuer_name_source_upper
        CHECK (source_code IS NULL OR source_code = UPPER(source_code)),

    CONSTRAINT ck_issuer_name_dates
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),

    CONSTRAINT fk_issuer_name_issuer
        FOREIGN KEY (issuer_id)
        REFERENCES issuer(issuer_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_issuer_name_confidence
        FOREIGN KEY (confidence_code)
        REFERENCES confidence_level(confidence_code),

    CONSTRAINT uq_issuer_name_history
        UNIQUE (issuer_id, name, valid_from)
);

CREATE INDEX IF NOT EXISTS ix_issuer_name_history_issuer
    ON issuer_name_history (issuer_id);

CREATE INDEX IF NOT EXISTS ix_issuer_name_history_name
    ON issuer_name_history (name);

-- ---------------------------------------------------------------------
-- Securities
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS security (
    security_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    issuer_id            UUID,
    instrument_type_code VARCHAR(32) NOT NULL,

    security_title       TEXT NOT NULL,
    share_class          TEXT,
    currency_code        VARCHAR(3),

    status               VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
    first_seen           DATE,
    last_seen            DATE,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_security_status
        CHECK (status IN (
            'ACTIVE',
            'INACTIVE',
            'RETIRED',
            'UNKNOWN'
        )),

    CONSTRAINT fk_security_issuer
        FOREIGN KEY (issuer_id)
        REFERENCES issuer(issuer_id),

    CONSTRAINT fk_security_type
        FOREIGN KEY (instrument_type_code)
        REFERENCES instrument_type(type_code),

    CONSTRAINT fk_security_currency
        FOREIGN KEY (currency_code)
        REFERENCES iso4217_currency(code)
);

CREATE INDEX IF NOT EXISTS ix_security_issuer
    ON security (issuer_id);

CREATE INDEX IF NOT EXISTS ix_security_type
    ON security (instrument_type_code);

CREATE INDEX IF NOT EXISTS ix_security_currency
    ON security (currency_code);

CREATE INDEX IF NOT EXISTS ix_security_title
    ON security (security_title);

CREATE INDEX IF NOT EXISTS ix_security_status
    ON security (status);

-- ---------------------------------------------------------------------
-- Security identifiers
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS security_identifier (
    security_identifier_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    security_id      UUID NOT NULL,
    id_type          VARCHAR(32) NOT NULL,
    id_value         TEXT NOT NULL,

    valid_from       DATE,
    valid_to         DATE,
    source_code      VARCHAR(32),
    confidence_code  VARCHAR(16) NOT NULL DEFAULT 'HIGH',

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_security_identifier_type_upper
        CHECK (id_type = UPPER(id_type)),

    CONSTRAINT ck_security_identifier_source_upper
        CHECK (source_code IS NULL OR source_code = UPPER(source_code)),

    CONSTRAINT ck_security_identifier_dates
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),

    CONSTRAINT fk_security_identifier_security
        FOREIGN KEY (security_id)
        REFERENCES security(security_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_security_identifier_confidence
        FOREIGN KEY (confidence_code)
        REFERENCES confidence_level(confidence_code),

    CONSTRAINT uq_security_identifier
        UNIQUE (id_type, id_value, security_id)
);

CREATE INDEX IF NOT EXISTS ix_security_identifier_security
    ON security_identifier (security_id);

CREATE INDEX IF NOT EXISTS ix_security_identifier_lookup
    ON security_identifier (id_type, id_value);
