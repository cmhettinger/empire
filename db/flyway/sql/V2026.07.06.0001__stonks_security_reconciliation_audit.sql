-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_security_reconciliation_audit
--
-- Purpose:
--   Add append-only audit tables for deterministic security identity
--   reconciliation evaluations, evidence links, and applied decisions.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Reconciliation evaluations
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS security_reconciliation_evaluation (
    evaluation_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    run_id                    UUID NOT NULL,
    security_id               UUID NOT NULL,

    issuer_id                 UUID,
    listing_id                UUID,
    related_security_id       UUID,
    related_listing_id        UUID,

    decision_type             VARCHAR(40) NOT NULL,
    rule_id                   VARCHAR(80) NOT NULL,
    rule_version              VARCHAR(32) NOT NULL,
    confidence_code           VARCHAR(16) NOT NULL,
    confidence_score          NUMERIC(6,5),

    previous_identity_status  VARCHAR(24) NOT NULL,
    evaluated_identity_status VARCHAR(24) NOT NULL,

    explanation               TEXT NOT NULL,
    reason_codes              TEXT[] NOT NULL DEFAULT '{}',
    details_json              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_sec_recon_eval_decision_type
        CHECK (decision_type IN (
            'PROMOTION_CANDIDATE',
            'PROMOTION_BLOCKED',
            'NO_ACTION',
            'DUPLICATE_CANDIDATE',
            'SUCCESSOR_LISTING_CANDIDATE',
            'MANUAL_REVIEW_REQUIRED'
        )),

    CONSTRAINT ck_sec_recon_eval_conf_score
        CHECK (confidence_score IS NULL OR (
            confidence_score >= 0
            AND confidence_score <= 1
        )),

    CONSTRAINT ck_sec_recon_eval_prev_status
        CHECK (previous_identity_status IN (
            'PROVISIONAL',
            'CONFIRMED'
        )),

    CONSTRAINT ck_sec_recon_eval_status
        CHECK (evaluated_identity_status IN (
            'PROVISIONAL',
            'CONFIRMED'
        )),

    CONSTRAINT ck_sec_recon_eval_target
        CHECK (security_id IS NOT NULL),

    CONSTRAINT fk_sec_recon_eval_run
        FOREIGN KEY (run_id)
        REFERENCES core.core_run(run_id),

    CONSTRAINT fk_sec_recon_eval_security
        FOREIGN KEY (security_id)
        REFERENCES security(security_id),

    CONSTRAINT fk_sec_recon_eval_issuer
        FOREIGN KEY (issuer_id)
        REFERENCES issuer(issuer_id),

    CONSTRAINT fk_sec_recon_eval_listing
        FOREIGN KEY (listing_id)
        REFERENCES listing(listing_id),

    CONSTRAINT fk_sec_recon_eval_related_security
        FOREIGN KEY (related_security_id)
        REFERENCES security(security_id),

    CONSTRAINT fk_sec_recon_eval_related_listing
        FOREIGN KEY (related_listing_id)
        REFERENCES listing(listing_id),

    CONSTRAINT fk_sec_recon_eval_confidence
        FOREIGN KEY (confidence_code)
        REFERENCES confidence_level(confidence_code)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_sec_recon_eval_run_target_rule
    ON security_reconciliation_evaluation (
        run_id,
        security_id,
        COALESCE(listing_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(related_security_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(related_listing_id, '00000000-0000-0000-0000-000000000000'::uuid),
        decision_type,
        rule_id,
        rule_version
    );

CREATE INDEX IF NOT EXISTS ix_sec_recon_eval_security_history
    ON security_reconciliation_evaluation (security_id, created_at DESC, evaluation_id);

CREATE INDEX IF NOT EXISTS ix_sec_recon_eval_run_report
    ON security_reconciliation_evaluation (run_id, decision_type, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_sec_recon_eval_candidate_scan
    ON security_reconciliation_evaluation (decision_type, confidence_code, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_sec_recon_eval_related_security
    ON security_reconciliation_evaluation (related_security_id)
    WHERE related_security_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_sec_recon_eval_related_listing
    ON security_reconciliation_evaluation (related_listing_id)
    WHERE related_listing_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- Evaluation evidence links
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS security_reconciliation_evaluation_evidence (
    evaluation_id        UUID NOT NULL,
    provider_evidence_id UUID NOT NULL,

    evidence_role        VARCHAR(24) NOT NULL DEFAULT 'SUPPORTS',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_sec_recon_eval_evidence_role
        CHECK (evidence_role IN (
            'SUPPORTS',
            'CONFLICTS',
            'BLOCKS',
            'CONTEXT'
        )),

    CONSTRAINT fk_sec_recon_eval_ev_eval
        FOREIGN KEY (evaluation_id)
        REFERENCES security_reconciliation_evaluation(evaluation_id),

    CONSTRAINT fk_sec_recon_eval_ev_provider
        FOREIGN KEY (provider_evidence_id)
        REFERENCES provider_evidence(provider_evidence_id),

    CONSTRAINT pk_sec_recon_eval_evidence
        PRIMARY KEY (evaluation_id, provider_evidence_id, evidence_role)
);

CREATE INDEX IF NOT EXISTS ix_sec_recon_eval_ev_provider
    ON security_reconciliation_evaluation_evidence (provider_evidence_id);

-- ---------------------------------------------------------------------
-- Applied reconciliation decisions
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS security_reconciliation_decision (
    decision_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    evaluation_id            UUID NOT NULL,
    run_id                   UUID NOT NULL,
    security_id              UUID NOT NULL,

    decision_type            VARCHAR(40) NOT NULL,
    previous_identity_status VARCHAR(24) NOT NULL,
    new_identity_status      VARCHAR(24) NOT NULL,

    applied_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by               TEXT,
    explanation              TEXT NOT NULL,
    details_json             JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT ck_sec_recon_decision_type
        CHECK (decision_type IN (
            'PROMOTE_TO_CONFIRMED'
        )),

    CONSTRAINT ck_sec_recon_decision_prev_status
        CHECK (previous_identity_status IN (
            'PROVISIONAL',
            'CONFIRMED'
        )),

    CONSTRAINT ck_sec_recon_decision_new_status
        CHECK (new_identity_status IN (
            'PROVISIONAL',
            'CONFIRMED'
        )),

    CONSTRAINT ck_sec_recon_decision_transition
        CHECK (
            previous_identity_status = 'PROVISIONAL'
            AND new_identity_status = 'CONFIRMED'
        ),

    CONSTRAINT fk_sec_recon_decision_eval
        FOREIGN KEY (evaluation_id)
        REFERENCES security_reconciliation_evaluation(evaluation_id),

    CONSTRAINT fk_sec_recon_decision_run
        FOREIGN KEY (run_id)
        REFERENCES core.core_run(run_id),

    CONSTRAINT fk_sec_recon_decision_security
        FOREIGN KEY (security_id)
        REFERENCES security(security_id),

    CONSTRAINT uq_sec_recon_decision_eval
        UNIQUE (evaluation_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_sec_recon_decision_promotion
    ON security_reconciliation_decision (security_id)
    WHERE decision_type = 'PROMOTE_TO_CONFIRMED';

CREATE INDEX IF NOT EXISTS ix_sec_recon_decision_security_history
    ON security_reconciliation_decision (security_id, applied_at DESC, decision_id);

CREATE INDEX IF NOT EXISTS ix_sec_recon_decision_run
    ON security_reconciliation_decision (run_id, applied_at DESC);
