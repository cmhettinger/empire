
SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

CREATE SCHEMA core;

SET default_tablespace = '';

SET default_table_access_method = heap;

CREATE TABLE core.core_run (
    run_id uuid DEFAULT gen_random_uuid() NOT NULL,
    domain character varying(64) NOT NULL,
    job_name character varying(128) NOT NULL,
    subject_key character varying(255),
    effective_date date,
    run_type character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    heartbeat_timeout_seconds integer,
    last_heartbeat_at timestamp with time zone,
    stale_after timestamp with time zone,
    runner character varying(32) NOT NULL,
    runner_ref jsonb DEFAULT '{}'::jsonb NOT NULL,
    params jsonb DEFAULT '{}'::jsonb NOT NULL,
    summary jsonb DEFAULT '{}'::jsonb NOT NULL,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_core_run_heartbeat_timeout_positive CHECK (((heartbeat_timeout_seconds IS NULL) OR (heartbeat_timeout_seconds > 0))),
    CONSTRAINT ck_core_run_run_type CHECK (((run_type)::text = ANY ((ARRAY['airflow'::character varying, 'cli'::character varying, 'api'::character varying, 'manual'::character varying, 'agent'::character varying])::text[]))),
    CONSTRAINT ck_core_run_status CHECK (((status)::text = ANY ((ARRAY['started'::character varying, 'succeeded'::character varying, 'failed'::character varying, 'cancelled'::character varying, 'abandoned'::character varying])::text[])))
);

CREATE TABLE core.flyway_schema_history (
    installed_rank integer NOT NULL,
    version character varying(50),
    description character varying(200) NOT NULL,
    type character varying(20) NOT NULL,
    script character varying(1000) NOT NULL,
    checksum integer,
    installed_by character varying(100) NOT NULL,
    installed_on timestamp without time zone DEFAULT now() NOT NULL,
    execution_time integer NOT NULL,
    success boolean NOT NULL
);

CREATE TABLE core.storage_root (
    storage_root_id bigint NOT NULL,
    root_name character varying(64) NOT NULL,
    backend_type character varying(32) NOT NULL,
    base_uri character varying(1024) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_storage_root_backend_type CHECK (((backend_type)::text = 'filesystem'::text))
);

CREATE SEQUENCE core.storage_root_storage_root_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE core.storage_root_storage_root_id_seq OWNED BY core.storage_root.storage_root_id;

CREATE TABLE core.stored_object (
    object_id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id uuid,
    storage_root_id bigint NOT NULL,
    object_key character varying(1024) NOT NULL,
    filename character varying(255) NOT NULL,
    object_scope character varying(32) DEFAULT 'run'::character varying NOT NULL,
    domain character varying(64),
    logical_name character varying(255),
    content_type character varying(128),
    object_kind character varying(64),
    size_bytes bigint,
    checksum_sha256 character(64),
    expires_at timestamp with time zone,
    deleted_at timestamp with time zone,
    purge_after timestamp with time zone,
    delete_attempts integer DEFAULT 0 NOT NULL,
    last_delete_error text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_stored_object_checksum_sha256_length CHECK (((checksum_sha256 IS NULL) OR (checksum_sha256 ~ '^[a-fA-F0-9]{64}$'::text))),
    CONSTRAINT ck_stored_object_delete_attempts_nonnegative CHECK ((delete_attempts >= 0)),
    CONSTRAINT ck_stored_object_reference_requires_no_run CHECK ((((object_scope)::text <> 'reference'::text) OR (run_id IS NULL))),
    CONSTRAINT ck_stored_object_run_scope_requires_run CHECK ((((object_scope)::text <> 'run'::text) OR (run_id IS NOT NULL))),
    CONSTRAINT ck_stored_object_scope CHECK (((object_scope)::text = ANY ((ARRAY['run'::character varying, 'reference'::character varying, 'audit'::character varying, 'manual'::character varying])::text[]))),
    CONSTRAINT ck_stored_object_size_nonnegative CHECK (((size_bytes IS NULL) OR (size_bytes >= 0)))
);

ALTER TABLE ONLY core.storage_root ALTER COLUMN storage_root_id SET DEFAULT nextval('core.storage_root_storage_root_id_seq'::regclass);

ALTER TABLE ONLY core.core_run
    ADD CONSTRAINT core_run_pkey PRIMARY KEY (run_id);

ALTER TABLE ONLY core.flyway_schema_history
    ADD CONSTRAINT flyway_schema_history_pk PRIMARY KEY (installed_rank);

ALTER TABLE ONLY core.storage_root
    ADD CONSTRAINT storage_root_pkey PRIMARY KEY (storage_root_id);

ALTER TABLE ONLY core.storage_root
    ADD CONSTRAINT storage_root_root_name_key UNIQUE (root_name);

ALTER TABLE ONLY core.stored_object
    ADD CONSTRAINT stored_object_pkey PRIMARY KEY (object_id);

ALTER TABLE ONLY core.stored_object
    ADD CONSTRAINT uq_stored_object_path UNIQUE (storage_root_id, object_key, filename);

CREATE INDEX flyway_schema_history_s_idx ON core.flyway_schema_history USING btree (success);

CREATE INDEX ix_core_run_completed_at ON core.core_run USING btree (completed_at DESC);

CREATE INDEX ix_core_run_domain_job_date ON core.core_run USING btree (domain, job_name, effective_date DESC);

CREATE INDEX ix_core_run_stale ON core.core_run USING btree (stale_after) WHERE (((status)::text = 'started'::text) AND (stale_after IS NOT NULL));

CREATE INDEX ix_core_run_started_at ON core.core_run USING btree (started_at DESC);

CREATE INDEX ix_core_run_status ON core.core_run USING btree (status);

CREATE INDEX ix_core_run_subject ON core.core_run USING btree (domain, subject_key);

CREATE INDEX ix_storage_root_active ON core.storage_root USING btree (is_active);

CREATE INDEX ix_stored_object_expired ON core.stored_object USING btree (expires_at) WHERE ((deleted_at IS NULL) AND (expires_at IS NOT NULL));

CREATE INDEX ix_stored_object_key ON core.stored_object USING btree (storage_root_id, object_key);

CREATE INDEX ix_stored_object_kind ON core.stored_object USING btree (object_kind) WHERE (deleted_at IS NULL);

CREATE INDEX ix_stored_object_logical_name ON core.stored_object USING btree (domain, logical_name) WHERE ((logical_name IS NOT NULL) AND (deleted_at IS NULL));

CREATE INDEX ix_stored_object_purge ON core.stored_object USING btree (purge_after) WHERE ((deleted_at IS NOT NULL) AND (purge_after IS NOT NULL));

CREATE INDEX ix_stored_object_run ON core.stored_object USING btree (run_id) WHERE (deleted_at IS NULL);

CREATE INDEX ix_stored_object_scope_domain ON core.stored_object USING btree (object_scope, domain) WHERE (deleted_at IS NULL);

ALTER TABLE ONLY core.stored_object
    ADD CONSTRAINT stored_object_run_id_fkey FOREIGN KEY (run_id) REFERENCES core.core_run(run_id);

ALTER TABLE ONLY core.stored_object
    ADD CONSTRAINT stored_object_storage_root_id_fkey FOREIGN KEY (storage_root_id) REFERENCES core.storage_root(storage_root_id);
