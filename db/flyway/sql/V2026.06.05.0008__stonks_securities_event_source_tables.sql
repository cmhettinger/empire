-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_securities_event_source_tables
--
-- Purpose:
--   Create lightweight event and source-evidence tables for the Empire
--   security master.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Security master events
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS security_event (
    event_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    issuer_id      UUID,
    security_id    UUID,
    listing_id     UUID,

    event_type     VARCHAR(32) NOT NULL,
    event_date     DATE,
    source_code    VARCHAR(32),
    confidence_code VARCHAR(16) NOT NULL DEFAULT 'HIGH',

    description    TEXT,
    details_json   JSONB,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_security_event_type
        CHECK (event_type IN (
            'ISSUER_NAME_CHANGE',
            'SECURITY_TITLE_CHANGE',
            'TICKER_CHANGE',
            'EXCHANGE_CHANGE',
            'LISTING_STARTED',
            'LISTING_ENDED',
            'DELISTING_NOTICE',
            'DELISTED',
            'MERGER',
            'ACQUISITION',
            'SPINOFF',
            'BANKRUPTCY',
            'MANUAL_CORRECTION',
            'OTHER'
        )),

    CONSTRAINT ck_security_event_source_upper
        CHECK (source_code IS NULL OR source_code = UPPER(source_code)),

    CONSTRAINT fk_security_event_issuer
        FOREIGN KEY (issuer_id)
        REFERENCES issuer(issuer_id),

    CONSTRAINT fk_security_event_security
        FOREIGN KEY (security_id)
        REFERENCES security(security_id),

    CONSTRAINT fk_security_event_listing
        FOREIGN KEY (listing_id)
        REFERENCES listing(listing_id),

    CONSTRAINT fk_security_event_confidence
        FOREIGN KEY (confidence_code)
        REFERENCES confidence_level(confidence_code),

    CONSTRAINT ck_security_event_target
        CHECK (
            issuer_id IS NOT NULL
            OR security_id IS NOT NULL
            OR listing_id IS NOT NULL
        )
);

CREATE INDEX IF NOT EXISTS ix_security_event_issuer
    ON security_event (issuer_id);

CREATE INDEX IF NOT EXISTS ix_security_event_security
    ON security_event (security_id);

CREATE INDEX IF NOT EXISTS ix_security_event_listing
    ON security_event (listing_id);

CREATE INDEX IF NOT EXISTS ix_security_event_type_date
    ON security_event (event_type, event_date);

-- ---------------------------------------------------------------------
-- Source observations
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS source_observation (
    source_obs_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    source_code      VARCHAR(32) NOT NULL,
    source_date      DATE,
    observed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    accession_no     TEXT,
    form_type        VARCHAR(16),
    filing_date      DATE,

    object_id        UUID,
    object_key       TEXT,
    source_url       TEXT,
    raw_key          TEXT,

    summary_json     JSONB,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_source_obs_source_upper
        CHECK (source_code = UPPER(source_code))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_source_obs_raw_key
    ON source_observation (source_code, raw_key)
    WHERE raw_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_source_obs_source_date
    ON source_observation (source_code, source_date);

CREATE INDEX IF NOT EXISTS ix_source_obs_accession
    ON source_observation (accession_no);

CREATE INDEX IF NOT EXISTS ix_source_obs_object
    ON source_observation (object_id);

-- ---------------------------------------------------------------------
-- Source evidence links
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS source_evidence (
    source_evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    source_obs_id      UUID NOT NULL,

    issuer_id          UUID,
    security_id        UUID,
    listing_id         UUID,
    event_id           UUID,

    evidence_role      VARCHAR(24) NOT NULL DEFAULT 'SUPPORTS',
    notes              TEXT,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_source_evidence_role
        CHECK (evidence_role IN (
            'SUPPORTS',
            'CONFLICTS',
            'CREATED_FROM',
            'UPDATED_FROM',
            'MANUAL_REVIEW'
        )),

    CONSTRAINT fk_source_evidence_obs
        FOREIGN KEY (source_obs_id)
        REFERENCES source_observation(source_obs_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_source_evidence_issuer
        FOREIGN KEY (issuer_id)
        REFERENCES issuer(issuer_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_source_evidence_security
        FOREIGN KEY (security_id)
        REFERENCES security(security_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_source_evidence_listing
        FOREIGN KEY (listing_id)
        REFERENCES listing(listing_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_source_evidence_event
        FOREIGN KEY (event_id)
        REFERENCES security_event(event_id)
        ON DELETE CASCADE,

    CONSTRAINT ck_source_evidence_target
        CHECK (
            issuer_id IS NOT NULL
            OR security_id IS NOT NULL
            OR listing_id IS NOT NULL
            OR event_id IS NOT NULL
        )
);

CREATE INDEX IF NOT EXISTS ix_source_evidence_obs
    ON source_evidence (source_obs_id);

CREATE INDEX IF NOT EXISTS ix_source_evidence_issuer
    ON source_evidence (issuer_id);

CREATE INDEX IF NOT EXISTS ix_source_evidence_security
    ON source_evidence (security_id);

CREATE INDEX IF NOT EXISTS ix_source_evidence_listing
    ON source_evidence (listing_id);

CREATE INDEX IF NOT EXISTS ix_source_evidence_event
    ON source_evidence (event_id);
