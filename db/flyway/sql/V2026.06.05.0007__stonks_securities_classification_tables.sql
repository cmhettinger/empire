-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_securities_classification_tables
--
-- Purpose:
--   Create lightweight classification tables for the Empire security
--   master.
--
-- Notes:
--   - Classification is mainly issuer-level for now.
--   - SEC SIC is the first expected classification system.
--   - NAICS or Empire-defined categories can be added later.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Classification codes
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS classification_code (
    class_code_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    class_system  VARCHAR(32) NOT NULL,
    code          VARCHAR(32) NOT NULL,
    label         TEXT        NOT NULL,
    description   TEXT,

    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,

    CONSTRAINT ck_classification_system_upper
        CHECK (class_system = UPPER(class_system)),

    CONSTRAINT uq_classification_code
        UNIQUE (class_system, code)
);

CREATE INDEX IF NOT EXISTS ix_classification_system
    ON classification_code (class_system);

CREATE INDEX IF NOT EXISTS ix_classification_code
    ON classification_code (code);

-- ---------------------------------------------------------------------
-- Issuer classifications
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS issuer_classification (
    issuer_class_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    issuer_id        UUID NOT NULL,
    class_code_id    UUID NOT NULL,

    valid_from       DATE,
    valid_to         DATE,

    source_code      VARCHAR(32),
    confidence_code  VARCHAR(16) NOT NULL DEFAULT 'HIGH',

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_issuer_class_source_upper
        CHECK (source_code IS NULL OR source_code = UPPER(source_code)),

    CONSTRAINT ck_issuer_class_dates
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),

    CONSTRAINT fk_issuer_class_issuer
        FOREIGN KEY (issuer_id)
        REFERENCES issuer(issuer_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_issuer_class_code
        FOREIGN KEY (class_code_id)
        REFERENCES classification_code(class_code_id),

    CONSTRAINT fk_issuer_class_confidence
        FOREIGN KEY (confidence_code)
        REFERENCES confidence_level(confidence_code),

    CONSTRAINT uq_issuer_class
        UNIQUE (issuer_id, class_code_id, valid_from)
);

CREATE INDEX IF NOT EXISTS ix_issuer_class_issuer
    ON issuer_classification (issuer_id);

CREATE INDEX IF NOT EXISTS ix_issuer_class_code
    ON issuer_classification (class_code_id);

CREATE INDEX IF NOT EXISTS ix_issuer_class_active
    ON issuer_classification (issuer_id, class_code_id)
    WHERE valid_to IS NULL;