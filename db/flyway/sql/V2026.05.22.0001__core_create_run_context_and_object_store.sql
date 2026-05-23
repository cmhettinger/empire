
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE core.core_run (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    domain VARCHAR(64) NOT NULL,
    job_name VARCHAR(128) NOT NULL,
    subject_key VARCHAR(255) NULL,
    effective_date DATE NULL,

    run_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,

    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ NULL,

    heartbeat_timeout_seconds INT NULL,
    last_heartbeat_at TIMESTAMPTZ NULL,
    stale_after TIMESTAMPTZ NULL,

    runner VARCHAR(32) NOT NULL,
    runner_ref JSONB NOT NULL DEFAULT '{}'::jsonb,

    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,

    error_message TEXT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_core_run_status
        CHECK (status IN ('started', 'succeeded', 'failed', 'cancelled', 'abandoned')),

    CONSTRAINT ck_core_run_run_type
        CHECK (run_type IN ('airflow', 'cli', 'api', 'manual', 'agent')),

    CONSTRAINT ck_core_run_heartbeat_timeout_positive
        CHECK (heartbeat_timeout_seconds IS NULL OR heartbeat_timeout_seconds > 0)
);

CREATE INDEX ix_core_run_domain_job_date
    ON core.core_run (domain, job_name, effective_date DESC);

CREATE INDEX ix_core_run_subject
    ON core.core_run (domain, subject_key);

CREATE INDEX ix_core_run_status
    ON core.core_run (status);

CREATE INDEX ix_core_run_started_at
    ON core.core_run (started_at DESC);

CREATE INDEX ix_core_run_completed_at
    ON core.core_run (completed_at DESC);

CREATE INDEX ix_core_run_stale
    ON core.core_run (stale_after)
    WHERE status = 'started'
      AND stale_after IS NOT NULL;

CREATE TABLE core.storage_root (
    storage_root_id BIGSERIAL PRIMARY KEY,

    root_name VARCHAR(64) NOT NULL UNIQUE,
    backend_type VARCHAR(32) NOT NULL,
    base_uri VARCHAR(1024) NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT true,

    config JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_storage_root_backend_type
        CHECK (backend_type IN ('filesystem'))
);

CREATE INDEX ix_storage_root_active
    ON core.storage_root (is_active);

CREATE TABLE core.stored_object (
    object_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    run_id UUID NULL REFERENCES core.core_run(run_id),

    storage_root_id BIGINT NOT NULL
        REFERENCES core.storage_root(storage_root_id),

    object_key VARCHAR(1024) NOT NULL,
    filename VARCHAR(255) NOT NULL,

    object_scope VARCHAR(32) NOT NULL DEFAULT 'run',
    domain VARCHAR(64) NULL,
    logical_name VARCHAR(255) NULL,

    content_type VARCHAR(128) NULL,
    object_kind VARCHAR(64) NULL,

    size_bytes BIGINT NULL,
    checksum_sha256 CHAR(64) NULL,

    expires_at TIMESTAMPTZ NULL,
    deleted_at TIMESTAMPTZ NULL,
    purge_after TIMESTAMPTZ NULL,

    delete_attempts INT NOT NULL DEFAULT 0,
    last_delete_error TEXT NULL,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_stored_object_path
        UNIQUE (storage_root_id, object_key, filename),

    CONSTRAINT ck_stored_object_scope
        CHECK (object_scope IN ('run', 'reference', 'audit', 'manual')),

    CONSTRAINT ck_stored_object_size_nonnegative
        CHECK (size_bytes IS NULL OR size_bytes >= 0),

    CONSTRAINT ck_stored_object_delete_attempts_nonnegative
        CHECK (delete_attempts >= 0),

    CONSTRAINT ck_stored_object_reference_requires_no_run
        CHECK (object_scope <> 'reference' OR run_id IS NULL),

    CONSTRAINT ck_stored_object_run_scope_requires_run
        CHECK (object_scope <> 'run' OR run_id IS NOT NULL),

    CONSTRAINT ck_stored_object_checksum_sha256_length
        CHECK (
            checksum_sha256 IS NULL
            OR checksum_sha256 ~ '^[a-fA-F0-9]{64}$'
        )
);

CREATE INDEX ix_stored_object_run
    ON core.stored_object (run_id)
    WHERE deleted_at IS NULL;

CREATE INDEX ix_stored_object_key
    ON core.stored_object (storage_root_id, object_key);

CREATE INDEX ix_stored_object_kind
    ON core.stored_object (object_kind)
    WHERE deleted_at IS NULL;

CREATE INDEX ix_stored_object_scope_domain
    ON core.stored_object (object_scope, domain)
    WHERE deleted_at IS NULL;

CREATE INDEX ix_stored_object_logical_name
    ON core.stored_object (domain, logical_name)
    WHERE logical_name IS NOT NULL
      AND deleted_at IS NULL;

CREATE INDEX ix_stored_object_expired
    ON core.stored_object (expires_at)
    WHERE deleted_at IS NULL
      AND expires_at IS NOT NULL;

CREATE INDEX ix_stored_object_purge
    ON core.stored_object (purge_after)
    WHERE deleted_at IS NOT NULL
      AND purge_after IS NOT NULL;

-- INSERT INTO core.storage_root (
--     root_name,
--     backend_type,
--     base_uri,
--     config
-- )
-- VALUES
--     ('local_output', 'filesystem', '/mnt/empire-output', '{}'::jsonb),
--     ('nas_weather',  'filesystem', '/mnt/empire-nas1/weather', '{}'::jsonb),
--     ('nas_reports',  'filesystem', '/mnt/empire-nas2/reports', '{}'::jsonb)
-- ON CONFLICT (root_name) DO NOTHING;
