-- Canonical provider source content identity for stonks ingestion.
--
-- core.core_run owns execution context.
-- core.stored_object owns physical artifacts, object keys, checksums, and metadata.
-- These stonks tables only add provider-source semantics: which stored objects
-- represent the same canonical provider source content, and which observations
-- were parsed from that content.

CREATE TABLE IF NOT EXISTS stonks.provider_source_snapshot (
    source_snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    provider_code VARCHAR(32) NOT NULL
        REFERENCES stonks.provider(provider_code),
    source_code VARCHAR(64) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,

    first_seen_object_id UUID NULL
        REFERENCES core.stored_object(object_id),
    first_seen_run_id UUID NULL
        REFERENCES core.core_run(run_id),

    parser_version VARCHAR(64) NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_provider_source_snapshot_provider_upper
        CHECK (provider_code = UPPER(provider_code)),

    CONSTRAINT ck_provider_source_snapshot_content_sha256
        CHECK (content_sha256 ~ '^[a-fA-F0-9]{64}$'),

    CONSTRAINT uq_provider_source_snapshot_identity
        UNIQUE (provider_code, source_code, content_sha256)
);

CREATE INDEX IF NOT EXISTS ix_provider_source_snapshot_source
    ON stonks.provider_source_snapshot (source_code, created_at DESC);

CREATE TABLE IF NOT EXISTS stonks.provider_source_snapshot_object (
    source_snapshot_object_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    source_snapshot_id UUID NOT NULL
        REFERENCES stonks.provider_source_snapshot(source_snapshot_id),
    object_id UUID NOT NULL
        REFERENCES core.stored_object(object_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_provider_source_snapshot_object_object
        UNIQUE (object_id),

    CONSTRAINT uq_provider_source_snapshot_object_pair
        UNIQUE (source_snapshot_id, object_id)
);

CREATE INDEX IF NOT EXISTS ix_provider_source_snapshot_object_snapshot
    ON stonks.provider_source_snapshot_object (source_snapshot_id);

ALTER TABLE stonks.provider_observation
    ADD COLUMN IF NOT EXISTS source_snapshot_id UUID NULL
        REFERENCES stonks.provider_source_snapshot(source_snapshot_id);

CREATE INDEX IF NOT EXISTS ix_provider_observation_source_snapshot
    ON stonks.provider_observation (source_snapshot_id);
