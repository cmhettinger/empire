-- =====================================================================
-- Flyway Versioned Migration
--
-- Purpose:
--   Record verified successor relationships between securities and their
--   exchange listings. Reconciliation uses these relationships to preserve
--   provider evidence without reopening a predecessor's ended listing.
-- =====================================================================

SET search_path TO stonks, public;

CREATE TABLE IF NOT EXISTS security_successor_relationship (
    relationship_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    predecessor_issuer_id   UUID NOT NULL,
    successor_issuer_id     UUID NOT NULL,
    predecessor_security_id UUID NOT NULL,
    successor_security_id   UUID NOT NULL,
    predecessor_listing_id  UUID NOT NULL,
    successor_listing_id    UUID NOT NULL,

    relationship_type       VARCHAR(40) NOT NULL,
    effective_date          DATE NOT NULL,
    exchange_ratio          NUMERIC(18,8) NOT NULL DEFAULT 1,
    source_url              TEXT NOT NULL,
    details_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_security_successor_relationship_type
        CHECK (relationship_type IN (
            'REDOMICILIATION_SUCCESSOR',
            'MERGER_SUCCESSOR',
            'SHARE_EXCHANGE_SUCCESSOR'
        )),

    CONSTRAINT ck_security_successor_relationship_distinct_security
        CHECK (predecessor_security_id <> successor_security_id),

    CONSTRAINT ck_security_successor_relationship_exchange_ratio
        CHECK (exchange_ratio > 0),

    CONSTRAINT fk_security_successor_predecessor_issuer
        FOREIGN KEY (predecessor_issuer_id)
        REFERENCES issuer(issuer_id),

    CONSTRAINT fk_security_successor_successor_issuer
        FOREIGN KEY (successor_issuer_id)
        REFERENCES issuer(issuer_id),

    CONSTRAINT fk_security_successor_predecessor_security
        FOREIGN KEY (predecessor_security_id)
        REFERENCES security(security_id),

    CONSTRAINT fk_security_successor_successor_security
        FOREIGN KEY (successor_security_id)
        REFERENCES security(security_id),

    CONSTRAINT fk_security_successor_predecessor_listing
        FOREIGN KEY (predecessor_listing_id)
        REFERENCES listing(listing_id),

    CONSTRAINT fk_security_successor_successor_listing
        FOREIGN KEY (successor_listing_id)
        REFERENCES listing(listing_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_security_successor_relationship
    ON security_successor_relationship (
        predecessor_listing_id,
        successor_listing_id,
        relationship_type,
        effective_date
    );

CREATE INDEX IF NOT EXISTS ix_security_successor_predecessor_lookup
    ON security_successor_relationship (
        predecessor_security_id,
        effective_date,
        predecessor_listing_id
    );

CREATE INDEX IF NOT EXISTS ix_security_successor_successor_lookup
    ON security_successor_relationship (
        successor_security_id,
        effective_date,
        successor_listing_id
    );
