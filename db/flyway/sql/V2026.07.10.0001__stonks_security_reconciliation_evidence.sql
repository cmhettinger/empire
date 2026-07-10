-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_security_reconciliation_evidence
--
-- Purpose:
--   Add immutable, security-level derived reconciliation evidence while
--   preserving the provider evidence and source snapshot lineage that
--   supports every summary.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Derived security reconciliation evidence
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS security_reconciliation_evidence (
    reconciliation_evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    security_id                UUID NOT NULL,
    issuer_id                  UUID,
    listing_id                 UUID,

    evidence_type              VARCHAR(64) NOT NULL,
    evidence_role              VARCHAR(24) NOT NULL,
    evidence_key               CHAR(64) NOT NULL,
    summary_json               JSONB NOT NULL,
    collector_version          VARCHAR(32) NOT NULL,

    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_sec_recon_evidence_type
        CHECK (evidence_type IN (
            'SEC_ISSUER_SECURITY_MATCH',
            'SEC_TICKER_EXCHANGE_STABILITY',
            'SEC_SOURCE_SNAPSHOT_CONTINUITY',
            'SEC_SERIES_CLASS_IDENTIFIER'
        )),

    CONSTRAINT ck_sec_recon_evidence_role
        CHECK (evidence_role IN (
            'SUPPORTS',
            'CONFLICTS',
            'BLOCKS',
            'CONTEXT'
        )),

    CONSTRAINT ck_sec_recon_evidence_key
        CHECK (evidence_key ~ '^[a-fA-F0-9]{64}$'),

    CONSTRAINT fk_sec_recon_evidence_security
        FOREIGN KEY (security_id)
        REFERENCES security(security_id),

    CONSTRAINT fk_sec_recon_evidence_issuer
        FOREIGN KEY (issuer_id)
        REFERENCES issuer(issuer_id),

    CONSTRAINT fk_sec_recon_evidence_listing
        FOREIGN KEY (listing_id)
        REFERENCES listing(listing_id),

    CONSTRAINT uq_sec_recon_evidence_identity
        UNIQUE (security_id, evidence_type, evidence_key)
);

CREATE INDEX IF NOT EXISTS ix_sec_recon_evidence_security_type_created
    ON security_reconciliation_evidence (
        security_id,
        evidence_type,
        created_at DESC
    );

CREATE INDEX IF NOT EXISTS ix_sec_recon_evidence_type_role_created
    ON security_reconciliation_evidence (
        evidence_type,
        evidence_role,
        created_at DESC
    );

CREATE INDEX IF NOT EXISTS ix_sec_recon_evidence_issuer
    ON security_reconciliation_evidence (issuer_id)
    WHERE issuer_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_sec_recon_evidence_listing
    ON security_reconciliation_evidence (listing_id)
    WHERE listing_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- Derived-evidence lineage bridges
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS security_reconciliation_evidence_provider_evidence (
    reconciliation_evidence_id UUID NOT NULL,
    provider_evidence_id       UUID NOT NULL,

    CONSTRAINT pk_sec_recon_evidence_provider
        PRIMARY KEY (reconciliation_evidence_id, provider_evidence_id),

    CONSTRAINT fk_sec_recon_evidence_provider_evidence
        FOREIGN KEY (reconciliation_evidence_id)
        REFERENCES security_reconciliation_evidence(reconciliation_evidence_id),

    CONSTRAINT fk_sec_recon_evidence_provider_source
        FOREIGN KEY (provider_evidence_id)
        REFERENCES provider_evidence(provider_evidence_id)
);

CREATE INDEX IF NOT EXISTS ix_sec_recon_evidence_provider_evidence
    ON security_reconciliation_evidence_provider_evidence (provider_evidence_id);

CREATE TABLE IF NOT EXISTS security_reconciliation_evidence_source_snapshot (
    reconciliation_evidence_id UUID NOT NULL,
    source_snapshot_id         UUID NOT NULL,

    CONSTRAINT pk_sec_recon_evidence_snapshot
        PRIMARY KEY (reconciliation_evidence_id, source_snapshot_id),

    CONSTRAINT fk_sec_recon_evidence_snapshot_evidence
        FOREIGN KEY (reconciliation_evidence_id)
        REFERENCES security_reconciliation_evidence(reconciliation_evidence_id),

    CONSTRAINT fk_sec_recon_evidence_snapshot_source
        FOREIGN KEY (source_snapshot_id)
        REFERENCES provider_source_snapshot(source_snapshot_id)
);

CREATE INDEX IF NOT EXISTS ix_sec_recon_evidence_snapshot_source
    ON security_reconciliation_evidence_source_snapshot (source_snapshot_id);

-- ---------------------------------------------------------------------
-- Evaluation-to-derived-evidence bridge
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS security_reconciliation_evaluation_reconciliation_evidence (
    evaluation_id              UUID NOT NULL,
    reconciliation_evidence_id UUID NOT NULL,

    evidence_role              VARCHAR(24) NOT NULL DEFAULT 'SUPPORTS',
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_sec_recon_eval_recon_evidence_role
        CHECK (evidence_role IN (
            'SUPPORTS',
            'CONFLICTS',
            'BLOCKS',
            'CONTEXT'
        )),

    CONSTRAINT pk_sec_recon_eval_recon_evidence
        PRIMARY KEY (evaluation_id, reconciliation_evidence_id, evidence_role),

    CONSTRAINT fk_sec_recon_eval_recon_evidence_evaluation
        FOREIGN KEY (evaluation_id)
        REFERENCES security_reconciliation_evaluation(evaluation_id),

    CONSTRAINT fk_sec_recon_eval_recon_evidence_evidence
        FOREIGN KEY (reconciliation_evidence_id)
        REFERENCES security_reconciliation_evidence(reconciliation_evidence_id)
);

CREATE INDEX IF NOT EXISTS ix_sec_recon_eval_recon_evidence_evidence
    ON security_reconciliation_evaluation_reconciliation_evidence (
        reconciliation_evidence_id
    );
