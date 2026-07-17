
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

CREATE SCHEMA stonks;

SET default_tablespace = '';

SET default_table_access_method = heap;

CREATE TABLE stonks.classification_code (
    class_code_id uuid DEFAULT gen_random_uuid() NOT NULL,
    class_system character varying(32) NOT NULL,
    code character varying(32) NOT NULL,
    label text NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT ck_classification_system_upper CHECK (((class_system)::text = upper((class_system)::text)))
);

CREATE TABLE stonks.classification_system (
    class_system character varying(32) NOT NULL,
    system_name text NOT NULL,
    provider_code character varying(32),
    description text,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT ck_classification_system_code_upper CHECK (((class_system)::text = upper((class_system)::text)))
);

CREATE TABLE stonks.confidence_level (
    confidence_code character varying(16) NOT NULL,
    rank smallint NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT ck_confidence_level_code CHECK (((confidence_code)::text = upper((confidence_code)::text)))
);

CREATE TABLE stonks.exchange (
    exchange_id uuid DEFAULT gen_random_uuid() NOT NULL,
    exchange_code character varying(16) NOT NULL,
    exchange_name text NOT NULL,
    mic character varying(4),
    country_alpha2 character varying(2),
    exchange_type character varying(24) DEFAULT 'EXCHANGE'::character varying NOT NULL,
    is_synthetic boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    notes text,
    CONSTRAINT ck_exchange_code_upper CHECK (((exchange_code)::text = upper((exchange_code)::text))),
    CONSTRAINT ck_exchange_type CHECK (((exchange_type)::text = ANY ((ARRAY['EXCHANGE'::character varying, 'ATS'::character varying, 'OTC'::character varying, 'INDEX'::character varying, 'SYNTHETIC'::character varying, 'UNKNOWN'::character varying])::text[])))
);

CREATE TABLE stonks.exchange_alias (
    exchange_alias_id uuid DEFAULT gen_random_uuid() NOT NULL,
    exchange_id uuid NOT NULL,
    provider_code character varying(32) NOT NULL,
    raw_name text NOT NULL,
    normalized_name text,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT ck_exchange_alias_provider_upper CHECK (((provider_code)::text = upper((provider_code)::text)))
);

CREATE TABLE stonks.identifier_type (
    id_type character varying(32) NOT NULL,
    id_name text NOT NULL,
    applies_to character varying(32) NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT ck_identifier_type_applies_to CHECK (((applies_to)::text = ANY ((ARRAY['ISSUER'::character varying, 'SECURITY'::character varying, 'LISTING'::character varying, 'FILING'::character varying, 'INTERNAL'::character varying])::text[]))),
    CONSTRAINT ck_identifier_type_code_upper CHECK (((id_type)::text = upper((id_type)::text)))
);

CREATE TABLE stonks.instrument_class (
    class_code character varying(32) NOT NULL,
    class_name text NOT NULL,
    description text,
    sort_order smallint DEFAULT 100 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT ck_instrument_class_code CHECK (((class_code)::text = upper((class_code)::text)))
);

CREATE TABLE stonks.instrument_type (
    type_code character varying(32) NOT NULL,
    class_code character varying(32) NOT NULL,
    type_name text NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT ck_instrument_type_code CHECK (((type_code)::text = upper((type_code)::text)))
);

CREATE TABLE stonks.iso10383_mic (
    mic character varying(4) NOT NULL,
    operating_mic character varying(4),
    mic_type character varying(4) NOT NULL,
    market_name text NOT NULL,
    legal_entity text,
    acronym text,
    city text,
    country_alpha2 character varying(2) NOT NULL,
    website text,
    market_category_code character varying(4),
    status text,
    created_date date,
    source text DEFAULT 'ISO'::text NOT NULL,
    CONSTRAINT ck_iso10383_mic_source CHECK ((source = ANY (ARRAY['ISO'::text, 'INTERNAL'::text]))),
    CONSTRAINT ck_iso10383_mic_type CHECK (((mic_type)::text = ANY ((ARRAY['OPRT'::character varying, 'SGMT'::character varying])::text[]))),
    CONSTRAINT ck_iso10383_mic_upper CHECK (((mic)::text = upper((mic)::text)))
);

CREATE TABLE stonks.iso10383_mic_cat (
    code character varying(4) NOT NULL,
    description text NOT NULL,
    CONSTRAINT ck_iso10383_mic_cat_code CHECK (((code)::text = upper((code)::text)))
);

CREATE TABLE stonks.iso3166_country (
    alpha2 character varying(2) NOT NULL,
    alpha3 character varying(3) NOT NULL,
    numeric3 character varying(3) NOT NULL,
    name text NOT NULL,
    CONSTRAINT ck_iso3166_alpha2_upper CHECK (((alpha2)::text = upper((alpha2)::text))),
    CONSTRAINT ck_iso3166_alpha3_upper CHECK (((alpha3)::text = upper((alpha3)::text))),
    CONSTRAINT ck_iso3166_numeric3 CHECK (((numeric3)::text ~ '^[0-9]{3}$'::text))
);

CREATE TABLE stonks.iso4217_currency (
    code character varying(3) NOT NULL,
    numeric3 character varying(3) NOT NULL,
    name text NOT NULL,
    minor_unit smallint,
    CONSTRAINT ck_iso4217_code_upper CHECK (((code)::text = upper((code)::text))),
    CONSTRAINT ck_iso4217_numeric3 CHECK (((numeric3)::text ~ '^[0-9]{3}$'::text))
);

CREATE TABLE stonks.issuer (
    issuer_id uuid DEFAULT gen_random_uuid() NOT NULL,
    cik character varying(10),
    issuer_type character varying(32) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    current_name text NOT NULL,
    country_alpha2 character varying(2),
    sic_code character varying(4),
    status character varying(24) DEFAULT 'ACTIVE'::character varying NOT NULL,
    first_seen date,
    last_seen date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_issuer_cik CHECK (((cik IS NULL) OR ((cik)::text ~ '^[0-9]{10}$'::text))),
    CONSTRAINT ck_issuer_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying, 'MERGED'::character varying, 'ACQUIRED'::character varying, 'LIQUIDATED'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT ck_issuer_type CHECK (((issuer_type)::text = ANY ((ARRAY['OPERATING_COMPANY'::character varying, 'FUND_SPONSOR'::character varying, 'FUND_REGISTRANT'::character varying, 'TRUST'::character varying, 'GOVERNMENT'::character varying, 'INDEX_PROVIDER'::character varying, 'UNKNOWN'::character varying])::text[])))
);

CREATE TABLE stonks.issuer_classification (
    issuer_class_id uuid DEFAULT gen_random_uuid() NOT NULL,
    issuer_id uuid NOT NULL,
    class_code_id uuid NOT NULL,
    valid_from date,
    valid_to date,
    provider_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_issuer_class_dates CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT ck_issuer_class_provider_upper CHECK (((provider_code IS NULL) OR ((provider_code)::text = upper((provider_code)::text))))
);

CREATE TABLE stonks.issuer_identifier (
    issuer_identifier_id uuid DEFAULT gen_random_uuid() NOT NULL,
    issuer_id uuid NOT NULL,
    id_type character varying(32) NOT NULL,
    id_value text NOT NULL,
    valid_from date,
    valid_to date,
    provider_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_issuer_identifier_dates CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT ck_issuer_identifier_provider_upper CHECK (((provider_code IS NULL) OR ((provider_code)::text = upper((provider_code)::text)))),
    CONSTRAINT ck_issuer_identifier_type_upper CHECK (((id_type)::text = upper((id_type)::text)))
);

CREATE TABLE stonks.issuer_name_history (
    issuer_name_id uuid DEFAULT gen_random_uuid() NOT NULL,
    issuer_id uuid NOT NULL,
    name text NOT NULL,
    valid_from date,
    valid_to date,
    provider_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_issuer_name_dates CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT ck_issuer_name_provider_upper CHECK (((provider_code IS NULL) OR ((provider_code)::text = upper((provider_code)::text))))
);

CREATE TABLE stonks.listing (
    listing_id uuid DEFAULT gen_random_uuid() NOT NULL,
    security_id uuid NOT NULL,
    exchange_id uuid NOT NULL,
    current_ticker text,
    ticker_norm text,
    currency_code character varying(3),
    is_primary boolean DEFAULT true NOT NULL,
    status character varying(32) DEFAULT 'ACTIVE'::character varying NOT NULL,
    valid_from date,
    valid_to date,
    first_seen date,
    last_seen date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_listing_dates CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT ck_listing_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying, 'DELISTING_NOTICE'::character varying, 'DELISTED'::character varying, 'MERGED'::character varying, 'TRANSFERRED'::character varying, 'UNKNOWN'::character varying])::text[])))
);

CREATE TABLE stonks.listing_symbol_history (
    listing_symbol_id uuid DEFAULT gen_random_uuid() NOT NULL,
    listing_id uuid NOT NULL,
    ticker_raw text NOT NULL,
    ticker_norm text NOT NULL,
    ticker_display text,
    valid_from date,
    valid_to date,
    provider_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_listing_symbol_dates CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT ck_listing_symbol_provider_upper CHECK (((provider_code IS NULL) OR ((provider_code)::text = upper((provider_code)::text))))
);

CREATE TABLE stonks.ohlcv_daily (
    provider_listing_id uuid NOT NULL,
    trading_date date NOT NULL,
    open numeric(30,10) NOT NULL,
    high numeric(30,10) NOT NULL,
    low numeric(30,10) NOT NULL,
    close numeric(30,10) NOT NULL,
    volume numeric(30,8),
    change numeric(30,8),
    changepct numeric(30,8),
    typ numeric(30,8) NOT NULL,
    hl_range numeric(30,8) NOT NULL,
    oc_range numeric(30,8) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_ohlcv_daily_changepct_requires_change CHECK (((change IS NOT NULL) OR (changepct IS NULL))),
    CONSTRAINT ck_ohlcv_daily_high_bounds CHECK (((high >= open) AND (high >= close))),
    CONSTRAINT ck_ohlcv_daily_high_low CHECK ((high >= low)),
    CONSTRAINT ck_ohlcv_daily_hl_range CHECK ((hl_range = round((high - low), 8))),
    CONSTRAINT ck_ohlcv_daily_low_bounds CHECK (((low <= open) AND (low <= close))),
    CONSTRAINT ck_ohlcv_daily_numeric_not_nan CHECK (((open <> 'NaN'::numeric) AND (high <> 'NaN'::numeric) AND (low <> 'NaN'::numeric) AND (close <> 'NaN'::numeric) AND ((volume IS NULL) OR (volume <> 'NaN'::numeric)) AND ((change IS NULL) OR (change <> 'NaN'::numeric)) AND ((changepct IS NULL) OR (changepct <> 'NaN'::numeric)) AND (typ <> 'NaN'::numeric) AND (hl_range <> 'NaN'::numeric) AND (oc_range <> 'NaN'::numeric))),
    CONSTRAINT ck_ohlcv_daily_oc_range CHECK ((oc_range = round((close - open), 8))),
    CONSTRAINT ck_ohlcv_daily_typ CHECK ((typ = round((((high + low) + close) / (3)::numeric), 8))),
    CONSTRAINT ck_ohlcv_daily_volume_nonnegative CHECK (((volume IS NULL) OR (volume >= (0)::numeric)))
);

CREATE TABLE stonks.provider (
    provider_code character varying(32) NOT NULL,
    provider_name text NOT NULL,
    provider_type character varying(32) NOT NULL,
    website text,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT ck_provider_code_upper CHECK (((provider_code)::text = upper((provider_code)::text))),
    CONSTRAINT ck_provider_type_upper CHECK (((provider_type)::text = upper((provider_type)::text)))
);

CREATE TABLE stonks.provider_evidence (
    provider_evidence_id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider_observation_id uuid NOT NULL,
    issuer_id uuid,
    security_id uuid,
    listing_id uuid,
    event_id uuid,
    evidence_role character varying(24) DEFAULT 'SUPPORTS'::character varying NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_provider_evidence_role CHECK (((evidence_role)::text = ANY ((ARRAY['SUPPORTS'::character varying, 'CONFLICTS'::character varying, 'CREATED_FROM'::character varying, 'UPDATED_FROM'::character varying, 'MANUAL_REVIEW'::character varying])::text[]))),
    CONSTRAINT ck_provider_evidence_target CHECK (((issuer_id IS NOT NULL) OR (security_id IS NOT NULL) OR (listing_id IS NOT NULL) OR (event_id IS NOT NULL)))
);

CREATE TABLE stonks.provider_listing (
    provider_listing_id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider_code character varying(32) NOT NULL,
    market text NOT NULL,
    ticker text NOT NULL,
    name text,
    instrument_type_code character varying(32) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    first_seen date,
    last_seen date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    status character varying(32) DEFAULT 'ACTIVE'::character varying NOT NULL,
    metadata jsonb,
    CONSTRAINT ck_provider_listing_market CHECK (((market <> ''::text) AND (market = btrim(market)))),
    CONSTRAINT ck_provider_listing_seen_dates CHECK ((((first_seen IS NULL) AND (last_seen IS NULL)) OR ((first_seen IS NOT NULL) AND (last_seen IS NOT NULL) AND (last_seen >= first_seen)))),
    CONSTRAINT ck_provider_listing_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying])::text[]))),
    CONSTRAINT ck_provider_listing_ticker CHECK (((ticker <> ''::text) AND (ticker = btrim(ticker))))
);

CREATE TABLE stonks.provider_observation (
    provider_observation_id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider_code character varying(32) NOT NULL,
    provider_date date,
    observed_at timestamp with time zone DEFAULT now() NOT NULL,
    accession_no text,
    form_type character varying(16),
    filing_date date,
    object_id uuid,
    object_key text,
    source_url text,
    raw_key text,
    summary_json jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    source_snapshot_id uuid,
    CONSTRAINT ck_provider_observation_provider_upper CHECK (((provider_code)::text = upper((provider_code)::text)))
);

CREATE TABLE stonks.provider_source_snapshot (
    source_snapshot_id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider_code character varying(32) NOT NULL,
    source_code character varying(64) NOT NULL,
    content_sha256 character(64) NOT NULL,
    first_seen_object_id uuid,
    first_seen_run_id uuid,
    parser_version character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_provider_source_snapshot_content_sha256 CHECK ((content_sha256 ~ '^[a-fA-F0-9]{64}$'::text)),
    CONSTRAINT ck_provider_source_snapshot_provider_upper CHECK (((provider_code)::text = upper((provider_code)::text)))
);

CREATE TABLE stonks.provider_source_snapshot_object (
    source_snapshot_object_id uuid DEFAULT gen_random_uuid() CONSTRAINT provider_source_snapshot_obj_source_snapshot_object_id_not_null NOT NULL,
    source_snapshot_id uuid NOT NULL,
    object_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE stonks.security (
    security_id uuid DEFAULT gen_random_uuid() NOT NULL,
    issuer_id uuid,
    instrument_type_code character varying(32) NOT NULL,
    security_title text NOT NULL,
    share_class text,
    currency_code character varying(3),
    status character varying(24) DEFAULT 'ACTIVE'::character varying NOT NULL,
    first_seen date,
    last_seen date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    identity_status character varying(24) DEFAULT 'PROVISIONAL'::character varying NOT NULL,
    CONSTRAINT ck_security_identity_status CHECK (((identity_status)::text = ANY ((ARRAY['PROVISIONAL'::character varying, 'CONFIRMED'::character varying])::text[]))),
    CONSTRAINT ck_security_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying, 'RETIRED'::character varying, 'UNKNOWN'::character varying])::text[])))
);

CREATE TABLE stonks.security_event (
    event_id uuid DEFAULT gen_random_uuid() NOT NULL,
    issuer_id uuid,
    security_id uuid,
    listing_id uuid,
    event_type character varying(32) NOT NULL,
    event_date date,
    provider_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    description text,
    details_json jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_security_event_provider_upper CHECK (((provider_code IS NULL) OR ((provider_code)::text = upper((provider_code)::text)))),
    CONSTRAINT ck_security_event_target CHECK (((issuer_id IS NOT NULL) OR (security_id IS NOT NULL) OR (listing_id IS NOT NULL))),
    CONSTRAINT ck_security_event_type CHECK (((event_type)::text = ANY ((ARRAY['ISSUER_NAME_CHANGE'::character varying, 'SECURITY_TITLE_CHANGE'::character varying, 'TICKER_CHANGE'::character varying, 'EXCHANGE_CHANGE'::character varying, 'LISTING_STARTED'::character varying, 'LISTING_ENDED'::character varying, 'DELISTING_NOTICE'::character varying, 'DELISTED'::character varying, 'MERGER'::character varying, 'ACQUISITION'::character varying, 'SPINOFF'::character varying, 'BANKRUPTCY'::character varying, 'MANUAL_CORRECTION'::character varying, 'OTHER'::character varying])::text[])))
);

CREATE TABLE stonks.security_identifier (
    security_identifier_id uuid DEFAULT gen_random_uuid() NOT NULL,
    security_id uuid NOT NULL,
    id_type character varying(32) NOT NULL,
    id_value text NOT NULL,
    valid_from date,
    valid_to date,
    provider_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_security_identifier_dates CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT ck_security_identifier_provider_upper CHECK (((provider_code IS NULL) OR ((provider_code)::text = upper((provider_code)::text)))),
    CONSTRAINT ck_security_identifier_type_upper CHECK (((id_type)::text = upper((id_type)::text)))
);

CREATE TABLE stonks.security_reconciliation_decision (
    decision_id uuid DEFAULT gen_random_uuid() NOT NULL,
    evaluation_id uuid NOT NULL,
    run_id uuid NOT NULL,
    security_id uuid NOT NULL,
    decision_type character varying(40) NOT NULL,
    previous_identity_status character varying(24) CONSTRAINT security_reconciliation_decis_previous_identity_status_not_null NOT NULL,
    new_identity_status character varying(24) NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL,
    applied_by text,
    explanation text NOT NULL,
    details_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ck_sec_recon_decision_new_status CHECK (((new_identity_status)::text = ANY ((ARRAY['PROVISIONAL'::character varying, 'CONFIRMED'::character varying])::text[]))),
    CONSTRAINT ck_sec_recon_decision_prev_status CHECK (((previous_identity_status)::text = ANY ((ARRAY['PROVISIONAL'::character varying, 'CONFIRMED'::character varying])::text[]))),
    CONSTRAINT ck_sec_recon_decision_transition CHECK ((((previous_identity_status)::text = 'PROVISIONAL'::text) AND ((new_identity_status)::text = 'CONFIRMED'::text))),
    CONSTRAINT ck_sec_recon_decision_type CHECK (((decision_type)::text = 'PROMOTE_TO_CONFIRMED'::text))
);

CREATE TABLE stonks.security_reconciliation_evaluation (
    evaluation_id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id uuid NOT NULL,
    security_id uuid NOT NULL,
    issuer_id uuid,
    listing_id uuid,
    related_security_id uuid,
    related_listing_id uuid,
    decision_type character varying(40) NOT NULL,
    rule_id character varying(80) NOT NULL,
    rule_version character varying(32) NOT NULL,
    confidence_code character varying(16) NOT NULL,
    confidence_score numeric(6,5),
    previous_identity_status character varying(24) CONSTRAINT security_reconciliation_evalu_previous_identity_status_not_null NOT NULL,
    evaluated_identity_status character varying(24) CONSTRAINT security_reconciliation_eval_evaluated_identity_status_not_null NOT NULL,
    explanation text NOT NULL,
    reason_codes text[] DEFAULT '{}'::text[] NOT NULL,
    details_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sec_recon_eval_conf_score CHECK (((confidence_score IS NULL) OR ((confidence_score >= (0)::numeric) AND (confidence_score <= (1)::numeric)))),
    CONSTRAINT ck_sec_recon_eval_decision_type CHECK (((decision_type)::text = ANY ((ARRAY['PROMOTION_CANDIDATE'::character varying, 'PROMOTION_BLOCKED'::character varying, 'NO_ACTION'::character varying, 'DUPLICATE_CANDIDATE'::character varying, 'SUCCESSOR_LISTING_CANDIDATE'::character varying, 'MANUAL_REVIEW_REQUIRED'::character varying])::text[]))),
    CONSTRAINT ck_sec_recon_eval_prev_status CHECK (((previous_identity_status)::text = ANY ((ARRAY['PROVISIONAL'::character varying, 'CONFIRMED'::character varying])::text[]))),
    CONSTRAINT ck_sec_recon_eval_status CHECK (((evaluated_identity_status)::text = ANY ((ARRAY['PROVISIONAL'::character varying, 'CONFIRMED'::character varying])::text[]))),
    CONSTRAINT ck_sec_recon_eval_target CHECK ((security_id IS NOT NULL))
);

CREATE TABLE stonks.security_reconciliation_evaluation_evidence (
    evaluation_id uuid CONSTRAINT security_reconciliation_evaluation_evide_evaluation_id_not_null NOT NULL,
    provider_evidence_id uuid CONSTRAINT security_reconciliation_evaluatio_provider_evidence_id_not_null NOT NULL,
    evidence_role character varying(24) DEFAULT 'SUPPORTS'::character varying CONSTRAINT security_reconciliation_evaluation_evide_evidence_role_not_null NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sec_recon_eval_evidence_role CHECK (((evidence_role)::text = ANY ((ARRAY['SUPPORTS'::character varying, 'CONFLICTS'::character varying, 'BLOCKS'::character varying, 'CONTEXT'::character varying])::text[])))
);

CREATE TABLE stonks.security_reconciliation_evaluation_reconciliation_evidence (
    evaluation_id uuid CONSTRAINT security_reconciliation_evaluation_recon_evaluation_id_not_null NOT NULL,
    reconciliation_evidence_id uuid CONSTRAINT security_reconciliation_eva_reconciliation_evidence_id_not_null NOT NULL,
    evidence_role character varying(24) DEFAULT 'SUPPORTS'::character varying CONSTRAINT security_reconciliation_evaluation_recon_evidence_role_not_null NOT NULL,
    created_at timestamp with time zone DEFAULT now() CONSTRAINT security_reconciliation_evaluation_reconcil_created_at_not_null NOT NULL,
    CONSTRAINT ck_sec_recon_eval_recon_evidence_role CHECK (((evidence_role)::text = ANY ((ARRAY['SUPPORTS'::character varying, 'CONFLICTS'::character varying, 'BLOCKS'::character varying, 'CONTEXT'::character varying])::text[])))
);

CREATE TABLE stonks.security_reconciliation_evidence (
    reconciliation_evidence_id uuid DEFAULT gen_random_uuid() CONSTRAINT security_reconciliation_evi_reconciliation_evidence_id_not_null NOT NULL,
    security_id uuid NOT NULL,
    issuer_id uuid,
    listing_id uuid,
    evidence_type character varying(64) NOT NULL,
    evidence_role character varying(24) NOT NULL,
    evidence_key character(64) NOT NULL,
    summary_json jsonb NOT NULL,
    collector_version character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_sec_recon_evidence_key CHECK ((evidence_key ~ '^[a-fA-F0-9]{64}$'::text)),
    CONSTRAINT ck_sec_recon_evidence_role CHECK (((evidence_role)::text = ANY ((ARRAY['SUPPORTS'::character varying, 'CONFLICTS'::character varying, 'BLOCKS'::character varying, 'CONTEXT'::character varying])::text[]))),
    CONSTRAINT ck_sec_recon_evidence_type CHECK (((evidence_type)::text = ANY ((ARRAY['SEC_ISSUER_SECURITY_MATCH'::character varying, 'SEC_TICKER_EXCHANGE_STABILITY'::character varying, 'SEC_SOURCE_SNAPSHOT_CONTINUITY'::character varying, 'SEC_SERIES_CLASS_IDENTIFIER'::character varying])::text[])))
);

CREATE TABLE stonks.security_reconciliation_evidence_provider_evidence (
    reconciliation_evidence_id uuid CONSTRAINT security_reconciliation_ev_reconciliation_evidence_id_not_null1 NOT NULL,
    provider_evidence_id uuid CONSTRAINT security_reconciliation_evidence__provider_evidence_id_not_null NOT NULL
);

CREATE TABLE stonks.security_reconciliation_evidence_source_snapshot (
    reconciliation_evidence_id uuid CONSTRAINT security_reconciliation_ev_reconciliation_evidence_id_not_null2 NOT NULL,
    source_snapshot_id uuid CONSTRAINT security_reconciliation_evidence_so_source_snapshot_id_not_null NOT NULL
);

CREATE TABLE stonks.security_successor_relationship (
    relationship_id uuid DEFAULT gen_random_uuid() NOT NULL,
    predecessor_issuer_id uuid NOT NULL,
    successor_issuer_id uuid NOT NULL,
    predecessor_security_id uuid CONSTRAINT security_successor_relationshi_predecessor_security_id_not_null NOT NULL,
    successor_security_id uuid NOT NULL,
    predecessor_listing_id uuid NOT NULL,
    successor_listing_id uuid NOT NULL,
    relationship_type character varying(40) NOT NULL,
    effective_date date NOT NULL,
    exchange_ratio numeric(18,8) DEFAULT 1 NOT NULL,
    source_url text NOT NULL,
    details_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_security_successor_relationship_distinct_security CHECK ((predecessor_security_id <> successor_security_id)),
    CONSTRAINT ck_security_successor_relationship_exchange_ratio CHECK ((exchange_ratio > (0)::numeric)),
    CONSTRAINT ck_security_successor_relationship_type CHECK (((relationship_type)::text = ANY ((ARRAY['REDOMICILIATION_SUCCESSOR'::character varying, 'MERGER_SUCCESSOR'::character varying, 'SHARE_EXCHANGE_SUCCESSOR'::character varying])::text[])))
);

CREATE UNLOGGED TABLE stonks.stg_iso10383_mic (
    mic text,
    operating_mic text,
    oprt_sgmt text,
    market_name text,
    legal_entity_name text,
    lei text,
    market_category_code text,
    acronym text,
    iso_country_code text,
    city text,
    website text,
    status text,
    creation_date text,
    last_update_date text,
    last_validation_date text,
    expiry_date text,
    comments text
);

CREATE UNLOGGED TABLE stonks.stg_iso3166_country (
    name text,
    alpha2 text,
    alpha3 text,
    country_code text,
    iso_3166_2 text,
    region text,
    sub_region text,
    intermediate_region text,
    region_code text,
    sub_region_code text,
    intermediate_region_code text
);

CREATE UNLOGGED TABLE stonks.stg_iso4217_currency (
    entity text,
    currency text,
    alphabetic_code text,
    numeric_code text,
    minor_unit text,
    withdrawal_date text
);

CREATE UNLOGGED TABLE stonks.stg_sec_sic_classification_code (
    sic_code text,
    office text,
    industry_title text
);

ALTER TABLE ONLY stonks.classification_code
    ADD CONSTRAINT classification_code_pkey PRIMARY KEY (class_code_id);

ALTER TABLE ONLY stonks.classification_system
    ADD CONSTRAINT classification_system_pkey PRIMARY KEY (class_system);

ALTER TABLE ONLY stonks.confidence_level
    ADD CONSTRAINT confidence_level_pkey PRIMARY KEY (confidence_code);

ALTER TABLE ONLY stonks.exchange_alias
    ADD CONSTRAINT exchange_alias_pkey PRIMARY KEY (exchange_alias_id);

ALTER TABLE ONLY stonks.exchange
    ADD CONSTRAINT exchange_exchange_code_key UNIQUE (exchange_code);

ALTER TABLE ONLY stonks.exchange
    ADD CONSTRAINT exchange_pkey PRIMARY KEY (exchange_id);

ALTER TABLE ONLY stonks.identifier_type
    ADD CONSTRAINT identifier_type_pkey PRIMARY KEY (id_type);

ALTER TABLE ONLY stonks.instrument_class
    ADD CONSTRAINT instrument_class_pkey PRIMARY KEY (class_code);

ALTER TABLE ONLY stonks.instrument_type
    ADD CONSTRAINT instrument_type_pkey PRIMARY KEY (type_code);

ALTER TABLE ONLY stonks.iso10383_mic_cat
    ADD CONSTRAINT iso10383_mic_cat_pkey PRIMARY KEY (code);

ALTER TABLE ONLY stonks.iso10383_mic
    ADD CONSTRAINT iso10383_mic_pkey PRIMARY KEY (mic);

ALTER TABLE ONLY stonks.iso3166_country
    ADD CONSTRAINT iso3166_country_alpha3_key UNIQUE (alpha3);

ALTER TABLE ONLY stonks.iso3166_country
    ADD CONSTRAINT iso3166_country_numeric3_key UNIQUE (numeric3);

ALTER TABLE ONLY stonks.iso3166_country
    ADD CONSTRAINT iso3166_country_pkey PRIMARY KEY (alpha2);

ALTER TABLE ONLY stonks.iso4217_currency
    ADD CONSTRAINT iso4217_currency_pkey PRIMARY KEY (code);

ALTER TABLE ONLY stonks.issuer_classification
    ADD CONSTRAINT issuer_classification_pkey PRIMARY KEY (issuer_class_id);

ALTER TABLE ONLY stonks.issuer_identifier
    ADD CONSTRAINT issuer_identifier_pkey PRIMARY KEY (issuer_identifier_id);

ALTER TABLE ONLY stonks.issuer_name_history
    ADD CONSTRAINT issuer_name_history_pkey PRIMARY KEY (issuer_name_id);

ALTER TABLE ONLY stonks.issuer
    ADD CONSTRAINT issuer_pkey PRIMARY KEY (issuer_id);

ALTER TABLE ONLY stonks.listing
    ADD CONSTRAINT listing_pkey PRIMARY KEY (listing_id);

ALTER TABLE ONLY stonks.listing_symbol_history
    ADD CONSTRAINT listing_symbol_history_pkey PRIMARY KEY (listing_symbol_id);

ALTER TABLE ONLY stonks.ohlcv_daily
    ADD CONSTRAINT pk_ohlcv_daily PRIMARY KEY (provider_listing_id, trading_date);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation_evidence
    ADD CONSTRAINT pk_sec_recon_eval_evidence PRIMARY KEY (evaluation_id, provider_evidence_id, evidence_role);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation_reconciliation_evidence
    ADD CONSTRAINT pk_sec_recon_eval_recon_evidence PRIMARY KEY (evaluation_id, reconciliation_evidence_id, evidence_role);

ALTER TABLE ONLY stonks.security_reconciliation_evidence_provider_evidence
    ADD CONSTRAINT pk_sec_recon_evidence_provider PRIMARY KEY (reconciliation_evidence_id, provider_evidence_id);

ALTER TABLE ONLY stonks.security_reconciliation_evidence_source_snapshot
    ADD CONSTRAINT pk_sec_recon_evidence_snapshot PRIMARY KEY (reconciliation_evidence_id, source_snapshot_id);

ALTER TABLE ONLY stonks.provider_evidence
    ADD CONSTRAINT provider_evidence_pkey PRIMARY KEY (provider_evidence_id);

ALTER TABLE ONLY stonks.provider_listing
    ADD CONSTRAINT provider_listing_pkey PRIMARY KEY (provider_listing_id);

ALTER TABLE ONLY stonks.provider_observation
    ADD CONSTRAINT provider_observation_pkey PRIMARY KEY (provider_observation_id);

ALTER TABLE ONLY stonks.provider
    ADD CONSTRAINT provider_pkey PRIMARY KEY (provider_code);

ALTER TABLE ONLY stonks.provider_source_snapshot_object
    ADD CONSTRAINT provider_source_snapshot_object_pkey PRIMARY KEY (source_snapshot_object_id);

ALTER TABLE ONLY stonks.provider_source_snapshot
    ADD CONSTRAINT provider_source_snapshot_pkey PRIMARY KEY (source_snapshot_id);

ALTER TABLE ONLY stonks.security_event
    ADD CONSTRAINT security_event_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY stonks.security_identifier
    ADD CONSTRAINT security_identifier_pkey PRIMARY KEY (security_identifier_id);

ALTER TABLE ONLY stonks.security
    ADD CONSTRAINT security_pkey PRIMARY KEY (security_id);

ALTER TABLE ONLY stonks.security_reconciliation_decision
    ADD CONSTRAINT security_reconciliation_decision_pkey PRIMARY KEY (decision_id);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation
    ADD CONSTRAINT security_reconciliation_evaluation_pkey PRIMARY KEY (evaluation_id);

ALTER TABLE ONLY stonks.security_reconciliation_evidence
    ADD CONSTRAINT security_reconciliation_evidence_pkey PRIMARY KEY (reconciliation_evidence_id);

ALTER TABLE ONLY stonks.security_successor_relationship
    ADD CONSTRAINT security_successor_relationship_pkey PRIMARY KEY (relationship_id);

ALTER TABLE ONLY stonks.classification_code
    ADD CONSTRAINT uq_classification_code UNIQUE (class_system, code);

ALTER TABLE ONLY stonks.confidence_level
    ADD CONSTRAINT uq_confidence_level_rank UNIQUE (rank);

ALTER TABLE ONLY stonks.exchange_alias
    ADD CONSTRAINT uq_exchange_alias_provider_raw UNIQUE (provider_code, raw_name);

ALTER TABLE ONLY stonks.issuer_classification
    ADD CONSTRAINT uq_issuer_class UNIQUE (issuer_id, class_code_id, valid_from);

ALTER TABLE ONLY stonks.issuer_identifier
    ADD CONSTRAINT uq_issuer_identifier UNIQUE (id_type, id_value, issuer_id);

ALTER TABLE ONLY stonks.issuer_name_history
    ADD CONSTRAINT uq_issuer_name_history UNIQUE (issuer_id, name, valid_from);

ALTER TABLE ONLY stonks.listing_symbol_history
    ADD CONSTRAINT uq_listing_symbol_history UNIQUE (listing_id, ticker_norm, valid_from);

ALTER TABLE ONLY stonks.provider_listing
    ADD CONSTRAINT uq_provider_listing_identity UNIQUE (provider_code, market, ticker);

ALTER TABLE ONLY stonks.provider_source_snapshot
    ADD CONSTRAINT uq_provider_source_snapshot_identity UNIQUE (provider_code, source_code, content_sha256);

ALTER TABLE ONLY stonks.provider_source_snapshot_object
    ADD CONSTRAINT uq_provider_source_snapshot_object_object UNIQUE (object_id);

ALTER TABLE ONLY stonks.provider_source_snapshot_object
    ADD CONSTRAINT uq_provider_source_snapshot_object_pair UNIQUE (source_snapshot_id, object_id);

ALTER TABLE ONLY stonks.security_reconciliation_decision
    ADD CONSTRAINT uq_sec_recon_decision_eval UNIQUE (evaluation_id);

ALTER TABLE ONLY stonks.security_reconciliation_evidence
    ADD CONSTRAINT uq_sec_recon_evidence_identity UNIQUE (security_id, evidence_type, evidence_key);

ALTER TABLE ONLY stonks.security_identifier
    ADD CONSTRAINT uq_security_identifier UNIQUE (id_type, id_value, security_id);

CREATE INDEX ix_classification_code ON stonks.classification_code USING btree (code);

CREATE INDEX ix_classification_system ON stonks.classification_code USING btree (class_system);

CREATE INDEX ix_classification_system_provider ON stonks.classification_system USING btree (provider_code);

CREATE INDEX ix_exchange_alias_exchange ON stonks.exchange_alias USING btree (exchange_id);

CREATE INDEX ix_exchange_alias_provider ON stonks.exchange_alias USING btree (provider_code);

CREATE INDEX ix_exchange_country ON stonks.exchange USING btree (country_alpha2);

CREATE INDEX ix_exchange_mic ON stonks.exchange USING btree (mic);

CREATE INDEX ix_exchange_type ON stonks.exchange USING btree (exchange_type);

CREATE INDEX ix_instrument_type_class ON stonks.instrument_type USING btree (class_code);

CREATE INDEX ix_iso10383_mic_category ON stonks.iso10383_mic USING btree (market_category_code);

CREATE INDEX ix_iso10383_mic_country ON stonks.iso10383_mic USING btree (country_alpha2);

CREATE INDEX ix_iso10383_mic_operating ON stonks.iso10383_mic USING btree (operating_mic);

CREATE INDEX ix_iso10383_mic_source ON stonks.iso10383_mic USING btree (source);

CREATE INDEX ix_iso4217_numeric3 ON stonks.iso4217_currency USING btree (numeric3);

CREATE INDEX ix_issuer_class_active ON stonks.issuer_classification USING btree (issuer_id, class_code_id) WHERE (valid_to IS NULL);

CREATE INDEX ix_issuer_class_code ON stonks.issuer_classification USING btree (class_code_id);

CREATE INDEX ix_issuer_class_issuer ON stonks.issuer_classification USING btree (issuer_id);

CREATE INDEX ix_issuer_class_provider ON stonks.issuer_classification USING btree (provider_code);

CREATE INDEX ix_issuer_country ON stonks.issuer USING btree (country_alpha2);

CREATE INDEX ix_issuer_identifier_issuer ON stonks.issuer_identifier USING btree (issuer_id);

CREATE INDEX ix_issuer_identifier_lookup ON stonks.issuer_identifier USING btree (id_type, id_value);

CREATE INDEX ix_issuer_identifier_provider ON stonks.issuer_identifier USING btree (provider_code);

CREATE INDEX ix_issuer_name ON stonks.issuer USING btree (current_name);

CREATE INDEX ix_issuer_name_history_issuer ON stonks.issuer_name_history USING btree (issuer_id);

CREATE INDEX ix_issuer_name_history_name ON stonks.issuer_name_history USING btree (name);

CREATE INDEX ix_issuer_name_history_provider ON stonks.issuer_name_history USING btree (provider_code);

CREATE INDEX ix_issuer_status ON stonks.issuer USING btree (status);

CREATE INDEX ix_issuer_type ON stonks.issuer USING btree (issuer_type);

CREATE INDEX ix_listing_active_exchange_ticker ON stonks.listing USING btree (exchange_id, ticker_norm) WHERE ((valid_to IS NULL) AND (ticker_norm IS NOT NULL));

CREATE INDEX ix_listing_currency ON stonks.listing USING btree (currency_code);

CREATE INDEX ix_listing_exchange ON stonks.listing USING btree (exchange_id);

CREATE INDEX ix_listing_security ON stonks.listing USING btree (security_id);

CREATE INDEX ix_listing_status ON stonks.listing USING btree (status);

CREATE INDEX ix_listing_symbol_active ON stonks.listing_symbol_history USING btree (ticker_norm) WHERE (valid_to IS NULL);

CREATE INDEX ix_listing_symbol_listing ON stonks.listing_symbol_history USING btree (listing_id);

CREATE INDEX ix_listing_symbol_provider ON stonks.listing_symbol_history USING btree (provider_code);

CREATE INDEX ix_listing_symbol_ticker ON stonks.listing_symbol_history USING btree (ticker_norm);

CREATE INDEX ix_listing_ticker_norm ON stonks.listing USING btree (ticker_norm);

CREATE INDEX ix_ohlcv_daily_trading_date ON stonks.ohlcv_daily USING btree (trading_date DESC, provider_listing_id);

CREATE INDEX ix_provider_evidence_event ON stonks.provider_evidence USING btree (event_id);

CREATE INDEX ix_provider_evidence_issuer ON stonks.provider_evidence USING btree (issuer_id);

CREATE INDEX ix_provider_evidence_listing ON stonks.provider_evidence USING btree (listing_id);

CREATE INDEX ix_provider_evidence_observation ON stonks.provider_evidence USING btree (provider_observation_id);

CREATE INDEX ix_provider_evidence_security ON stonks.provider_evidence USING btree (security_id);

CREATE INDEX ix_provider_listing_provider_last_seen ON stonks.provider_listing USING btree (provider_code, last_seen DESC) WHERE (last_seen IS NOT NULL);

CREATE INDEX ix_provider_observation_accession ON stonks.provider_observation USING btree (accession_no);

CREATE INDEX ix_provider_observation_object ON stonks.provider_observation USING btree (object_id);

CREATE INDEX ix_provider_observation_provider_date ON stonks.provider_observation USING btree (provider_code, provider_date);

CREATE INDEX ix_provider_observation_source_snapshot ON stonks.provider_observation USING btree (source_snapshot_id);

CREATE INDEX ix_provider_source_snapshot_object_snapshot ON stonks.provider_source_snapshot_object USING btree (source_snapshot_id);

CREATE INDEX ix_provider_source_snapshot_source ON stonks.provider_source_snapshot USING btree (source_code, created_at DESC);

CREATE INDEX ix_sec_recon_decision_run ON stonks.security_reconciliation_decision USING btree (run_id, applied_at DESC);

CREATE INDEX ix_sec_recon_decision_security_history ON stonks.security_reconciliation_decision USING btree (security_id, applied_at DESC, decision_id);

CREATE INDEX ix_sec_recon_eval_candidate_scan ON stonks.security_reconciliation_evaluation USING btree (decision_type, confidence_code, created_at DESC);

CREATE INDEX ix_sec_recon_eval_ev_provider ON stonks.security_reconciliation_evaluation_evidence USING btree (provider_evidence_id);

CREATE INDEX ix_sec_recon_eval_recon_evidence_evidence ON stonks.security_reconciliation_evaluation_reconciliation_evidence USING btree (reconciliation_evidence_id);

CREATE INDEX ix_sec_recon_eval_related_listing ON stonks.security_reconciliation_evaluation USING btree (related_listing_id) WHERE (related_listing_id IS NOT NULL);

CREATE INDEX ix_sec_recon_eval_related_security ON stonks.security_reconciliation_evaluation USING btree (related_security_id) WHERE (related_security_id IS NOT NULL);

CREATE INDEX ix_sec_recon_eval_run_report ON stonks.security_reconciliation_evaluation USING btree (run_id, decision_type, created_at DESC);

CREATE INDEX ix_sec_recon_eval_security_history ON stonks.security_reconciliation_evaluation USING btree (security_id, created_at DESC, evaluation_id);

CREATE INDEX ix_sec_recon_evidence_issuer ON stonks.security_reconciliation_evidence USING btree (issuer_id) WHERE (issuer_id IS NOT NULL);

CREATE INDEX ix_sec_recon_evidence_listing ON stonks.security_reconciliation_evidence USING btree (listing_id) WHERE (listing_id IS NOT NULL);

CREATE INDEX ix_sec_recon_evidence_provider_evidence ON stonks.security_reconciliation_evidence_provider_evidence USING btree (provider_evidence_id);

CREATE INDEX ix_sec_recon_evidence_security_type_created ON stonks.security_reconciliation_evidence USING btree (security_id, evidence_type, created_at DESC);

CREATE INDEX ix_sec_recon_evidence_snapshot_source ON stonks.security_reconciliation_evidence_source_snapshot USING btree (source_snapshot_id);

CREATE INDEX ix_sec_recon_evidence_type_role_created ON stonks.security_reconciliation_evidence USING btree (evidence_type, evidence_role, created_at DESC);

CREATE INDEX ix_security_currency ON stonks.security USING btree (currency_code);

CREATE INDEX ix_security_event_issuer ON stonks.security_event USING btree (issuer_id);

CREATE INDEX ix_security_event_listing ON stonks.security_event USING btree (listing_id);

CREATE INDEX ix_security_event_provider ON stonks.security_event USING btree (provider_code);

CREATE INDEX ix_security_event_security ON stonks.security_event USING btree (security_id);

CREATE INDEX ix_security_event_type_date ON stonks.security_event USING btree (event_type, event_date);

CREATE INDEX ix_security_identifier_lookup ON stonks.security_identifier USING btree (id_type, id_value);

CREATE INDEX ix_security_identifier_provider ON stonks.security_identifier USING btree (provider_code);

CREATE INDEX ix_security_identifier_security ON stonks.security_identifier USING btree (security_id);

CREATE INDEX ix_security_identity_status ON stonks.security USING btree (identity_status);

CREATE INDEX ix_security_issuer ON stonks.security USING btree (issuer_id);

CREATE INDEX ix_security_provisional_issuer ON stonks.security USING btree (issuer_id, last_seen DESC, security_id) WHERE ((identity_status)::text = 'PROVISIONAL'::text);

CREATE INDEX ix_security_status ON stonks.security USING btree (status);

CREATE INDEX ix_security_successor_predecessor_lookup ON stonks.security_successor_relationship USING btree (predecessor_security_id, effective_date, predecessor_listing_id);

CREATE INDEX ix_security_successor_successor_lookup ON stonks.security_successor_relationship USING btree (successor_security_id, effective_date, successor_listing_id);

CREATE INDEX ix_security_title ON stonks.security USING btree (security_title);

CREATE INDEX ix_security_type ON stonks.security USING btree (instrument_type_code);

CREATE UNIQUE INDEX ux_issuer_cik ON stonks.issuer USING btree (cik) WHERE (cik IS NOT NULL);

CREATE UNIQUE INDEX ux_listing_one_active_per_security_exchange ON stonks.listing USING btree (security_id, exchange_id) WHERE ((valid_to IS NULL) AND ((status)::text = 'ACTIVE'::text));

CREATE UNIQUE INDEX ux_listing_symbol_one_active_per_listing ON stonks.listing_symbol_history USING btree (listing_id) WHERE (valid_to IS NULL);

CREATE UNIQUE INDEX ux_provider_observation_raw_key ON stonks.provider_observation USING btree (provider_code, raw_key) WHERE (raw_key IS NOT NULL);

CREATE UNIQUE INDEX ux_sec_recon_decision_promotion ON stonks.security_reconciliation_decision USING btree (security_id) WHERE ((decision_type)::text = 'PROMOTE_TO_CONFIRMED'::text);

CREATE UNIQUE INDEX ux_sec_recon_eval_run_target_rule ON stonks.security_reconciliation_evaluation USING btree (run_id, security_id, COALESCE(listing_id, '00000000-0000-0000-0000-000000000000'::uuid), COALESCE(related_security_id, '00000000-0000-0000-0000-000000000000'::uuid), COALESCE(related_listing_id, '00000000-0000-0000-0000-000000000000'::uuid), decision_type, rule_id, rule_version);

CREATE UNIQUE INDEX ux_security_successor_relationship ON stonks.security_successor_relationship USING btree (predecessor_listing_id, successor_listing_id, relationship_type, effective_date);

ALTER TABLE ONLY stonks.classification_code
    ADD CONSTRAINT fk_classification_code_system FOREIGN KEY (class_system) REFERENCES stonks.classification_system(class_system) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.classification_system
    ADD CONSTRAINT fk_classification_system_provider FOREIGN KEY (provider_code) REFERENCES stonks.provider(provider_code) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.exchange_alias
    ADD CONSTRAINT fk_exchange_alias_exchange FOREIGN KEY (exchange_id) REFERENCES stonks.exchange(exchange_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.exchange_alias
    ADD CONSTRAINT fk_exchange_alias_provider FOREIGN KEY (provider_code) REFERENCES stonks.provider(provider_code) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.exchange
    ADD CONSTRAINT fk_exchange_country FOREIGN KEY (country_alpha2) REFERENCES stonks.iso3166_country(alpha2);

ALTER TABLE ONLY stonks.exchange
    ADD CONSTRAINT fk_exchange_mic FOREIGN KEY (mic) REFERENCES stonks.iso10383_mic(mic);

ALTER TABLE ONLY stonks.instrument_type
    ADD CONSTRAINT fk_instrument_type_class FOREIGN KEY (class_code) REFERENCES stonks.instrument_class(class_code);

ALTER TABLE ONLY stonks.iso10383_mic
    ADD CONSTRAINT fk_iso10383_mic_category FOREIGN KEY (market_category_code) REFERENCES stonks.iso10383_mic_cat(code);

ALTER TABLE ONLY stonks.iso10383_mic
    ADD CONSTRAINT fk_iso10383_mic_country FOREIGN KEY (country_alpha2) REFERENCES stonks.iso3166_country(alpha2);

ALTER TABLE ONLY stonks.iso10383_mic
    ADD CONSTRAINT fk_iso10383_mic_operating FOREIGN KEY (operating_mic) REFERENCES stonks.iso10383_mic(mic) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY stonks.issuer_classification
    ADD CONSTRAINT fk_issuer_class_code FOREIGN KEY (class_code_id) REFERENCES stonks.classification_code(class_code_id);

ALTER TABLE ONLY stonks.issuer_classification
    ADD CONSTRAINT fk_issuer_class_confidence FOREIGN KEY (confidence_code) REFERENCES stonks.confidence_level(confidence_code);

ALTER TABLE ONLY stonks.issuer_classification
    ADD CONSTRAINT fk_issuer_class_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.issuer_classification
    ADD CONSTRAINT fk_issuer_class_provider FOREIGN KEY (provider_code) REFERENCES stonks.provider(provider_code) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.issuer
    ADD CONSTRAINT fk_issuer_country FOREIGN KEY (country_alpha2) REFERENCES stonks.iso3166_country(alpha2);

ALTER TABLE ONLY stonks.issuer_identifier
    ADD CONSTRAINT fk_issuer_identifier_confidence FOREIGN KEY (confidence_code) REFERENCES stonks.confidence_level(confidence_code);

ALTER TABLE ONLY stonks.issuer_identifier
    ADD CONSTRAINT fk_issuer_identifier_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.issuer_identifier
    ADD CONSTRAINT fk_issuer_identifier_provider FOREIGN KEY (provider_code) REFERENCES stonks.provider(provider_code) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.issuer_identifier
    ADD CONSTRAINT fk_issuer_identifier_type FOREIGN KEY (id_type) REFERENCES stonks.identifier_type(id_type) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.issuer_name_history
    ADD CONSTRAINT fk_issuer_name_confidence FOREIGN KEY (confidence_code) REFERENCES stonks.confidence_level(confidence_code);

ALTER TABLE ONLY stonks.issuer_name_history
    ADD CONSTRAINT fk_issuer_name_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.issuer_name_history
    ADD CONSTRAINT fk_issuer_name_provider FOREIGN KEY (provider_code) REFERENCES stonks.provider(provider_code) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.listing
    ADD CONSTRAINT fk_listing_currency FOREIGN KEY (currency_code) REFERENCES stonks.iso4217_currency(code);

ALTER TABLE ONLY stonks.listing
    ADD CONSTRAINT fk_listing_exchange FOREIGN KEY (exchange_id) REFERENCES stonks.exchange(exchange_id);

ALTER TABLE ONLY stonks.listing
    ADD CONSTRAINT fk_listing_security FOREIGN KEY (security_id) REFERENCES stonks.security(security_id);

ALTER TABLE ONLY stonks.listing_symbol_history
    ADD CONSTRAINT fk_listing_symbol_confidence FOREIGN KEY (confidence_code) REFERENCES stonks.confidence_level(confidence_code);

ALTER TABLE ONLY stonks.listing_symbol_history
    ADD CONSTRAINT fk_listing_symbol_listing FOREIGN KEY (listing_id) REFERENCES stonks.listing(listing_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.listing_symbol_history
    ADD CONSTRAINT fk_listing_symbol_provider FOREIGN KEY (provider_code) REFERENCES stonks.provider(provider_code) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.ohlcv_daily
    ADD CONSTRAINT fk_ohlcv_daily_provider_listing FOREIGN KEY (provider_listing_id) REFERENCES stonks.provider_listing(provider_listing_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.provider_evidence
    ADD CONSTRAINT fk_provider_evidence_event FOREIGN KEY (event_id) REFERENCES stonks.security_event(event_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.provider_evidence
    ADD CONSTRAINT fk_provider_evidence_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.provider_evidence
    ADD CONSTRAINT fk_provider_evidence_listing FOREIGN KEY (listing_id) REFERENCES stonks.listing(listing_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.provider_evidence
    ADD CONSTRAINT fk_provider_evidence_observation FOREIGN KEY (provider_observation_id) REFERENCES stonks.provider_observation(provider_observation_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.provider_evidence
    ADD CONSTRAINT fk_provider_evidence_security FOREIGN KEY (security_id) REFERENCES stonks.security(security_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.provider_listing
    ADD CONSTRAINT fk_provider_listing_instrument_type FOREIGN KEY (instrument_type_code) REFERENCES stonks.instrument_type(type_code);

ALTER TABLE ONLY stonks.provider_listing
    ADD CONSTRAINT fk_provider_listing_provider FOREIGN KEY (provider_code) REFERENCES stonks.provider(provider_code);

ALTER TABLE ONLY stonks.provider_observation
    ADD CONSTRAINT fk_provider_observation_provider FOREIGN KEY (provider_code) REFERENCES stonks.provider(provider_code) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.provider_source_snapshot
    ADD CONSTRAINT fk_provider_source_snapshot_first_seen_object FOREIGN KEY (first_seen_object_id) REFERENCES core.stored_object(object_id) ON DELETE SET NULL;

ALTER TABLE ONLY stonks.provider_source_snapshot
    ADD CONSTRAINT fk_provider_source_snapshot_first_seen_run FOREIGN KEY (first_seen_run_id) REFERENCES core.core_run(run_id) ON DELETE SET NULL;

ALTER TABLE ONLY stonks.provider_source_snapshot_object
    ADD CONSTRAINT fk_provider_source_snapshot_object_object FOREIGN KEY (object_id) REFERENCES core.stored_object(object_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.security_reconciliation_decision
    ADD CONSTRAINT fk_sec_recon_decision_eval FOREIGN KEY (evaluation_id) REFERENCES stonks.security_reconciliation_evaluation(evaluation_id);

ALTER TABLE ONLY stonks.security_reconciliation_decision
    ADD CONSTRAINT fk_sec_recon_decision_run FOREIGN KEY (run_id) REFERENCES core.core_run(run_id);

ALTER TABLE ONLY stonks.security_reconciliation_decision
    ADD CONSTRAINT fk_sec_recon_decision_security FOREIGN KEY (security_id) REFERENCES stonks.security(security_id);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation
    ADD CONSTRAINT fk_sec_recon_eval_confidence FOREIGN KEY (confidence_code) REFERENCES stonks.confidence_level(confidence_code);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation_evidence
    ADD CONSTRAINT fk_sec_recon_eval_ev_eval FOREIGN KEY (evaluation_id) REFERENCES stonks.security_reconciliation_evaluation(evaluation_id);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation_evidence
    ADD CONSTRAINT fk_sec_recon_eval_ev_provider FOREIGN KEY (provider_evidence_id) REFERENCES stonks.provider_evidence(provider_evidence_id);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation
    ADD CONSTRAINT fk_sec_recon_eval_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation
    ADD CONSTRAINT fk_sec_recon_eval_listing FOREIGN KEY (listing_id) REFERENCES stonks.listing(listing_id);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation_reconciliation_evidence
    ADD CONSTRAINT fk_sec_recon_eval_recon_evidence_evaluation FOREIGN KEY (evaluation_id) REFERENCES stonks.security_reconciliation_evaluation(evaluation_id);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation_reconciliation_evidence
    ADD CONSTRAINT fk_sec_recon_eval_recon_evidence_evidence FOREIGN KEY (reconciliation_evidence_id) REFERENCES stonks.security_reconciliation_evidence(reconciliation_evidence_id);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation
    ADD CONSTRAINT fk_sec_recon_eval_related_listing FOREIGN KEY (related_listing_id) REFERENCES stonks.listing(listing_id);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation
    ADD CONSTRAINT fk_sec_recon_eval_related_security FOREIGN KEY (related_security_id) REFERENCES stonks.security(security_id);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation
    ADD CONSTRAINT fk_sec_recon_eval_run FOREIGN KEY (run_id) REFERENCES core.core_run(run_id);

ALTER TABLE ONLY stonks.security_reconciliation_evaluation
    ADD CONSTRAINT fk_sec_recon_eval_security FOREIGN KEY (security_id) REFERENCES stonks.security(security_id);

ALTER TABLE ONLY stonks.security_reconciliation_evidence
    ADD CONSTRAINT fk_sec_recon_evidence_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id);

ALTER TABLE ONLY stonks.security_reconciliation_evidence
    ADD CONSTRAINT fk_sec_recon_evidence_listing FOREIGN KEY (listing_id) REFERENCES stonks.listing(listing_id);

ALTER TABLE ONLY stonks.security_reconciliation_evidence_provider_evidence
    ADD CONSTRAINT fk_sec_recon_evidence_provider_evidence FOREIGN KEY (reconciliation_evidence_id) REFERENCES stonks.security_reconciliation_evidence(reconciliation_evidence_id);

ALTER TABLE ONLY stonks.security_reconciliation_evidence_provider_evidence
    ADD CONSTRAINT fk_sec_recon_evidence_provider_source FOREIGN KEY (provider_evidence_id) REFERENCES stonks.provider_evidence(provider_evidence_id);

ALTER TABLE ONLY stonks.security_reconciliation_evidence
    ADD CONSTRAINT fk_sec_recon_evidence_security FOREIGN KEY (security_id) REFERENCES stonks.security(security_id);

ALTER TABLE ONLY stonks.security_reconciliation_evidence_source_snapshot
    ADD CONSTRAINT fk_sec_recon_evidence_snapshot_evidence FOREIGN KEY (reconciliation_evidence_id) REFERENCES stonks.security_reconciliation_evidence(reconciliation_evidence_id);

ALTER TABLE ONLY stonks.security_reconciliation_evidence_source_snapshot
    ADD CONSTRAINT fk_sec_recon_evidence_snapshot_source FOREIGN KEY (source_snapshot_id) REFERENCES stonks.provider_source_snapshot(source_snapshot_id);

ALTER TABLE ONLY stonks.security
    ADD CONSTRAINT fk_security_currency FOREIGN KEY (currency_code) REFERENCES stonks.iso4217_currency(code);

ALTER TABLE ONLY stonks.security_event
    ADD CONSTRAINT fk_security_event_confidence FOREIGN KEY (confidence_code) REFERENCES stonks.confidence_level(confidence_code);

ALTER TABLE ONLY stonks.security_event
    ADD CONSTRAINT fk_security_event_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id);

ALTER TABLE ONLY stonks.security_event
    ADD CONSTRAINT fk_security_event_listing FOREIGN KEY (listing_id) REFERENCES stonks.listing(listing_id);

ALTER TABLE ONLY stonks.security_event
    ADD CONSTRAINT fk_security_event_provider FOREIGN KEY (provider_code) REFERENCES stonks.provider(provider_code) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.security_event
    ADD CONSTRAINT fk_security_event_security FOREIGN KEY (security_id) REFERENCES stonks.security(security_id);

ALTER TABLE ONLY stonks.security_identifier
    ADD CONSTRAINT fk_security_identifier_confidence FOREIGN KEY (confidence_code) REFERENCES stonks.confidence_level(confidence_code);

ALTER TABLE ONLY stonks.security_identifier
    ADD CONSTRAINT fk_security_identifier_provider FOREIGN KEY (provider_code) REFERENCES stonks.provider(provider_code) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.security_identifier
    ADD CONSTRAINT fk_security_identifier_security FOREIGN KEY (security_id) REFERENCES stonks.security(security_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.security_identifier
    ADD CONSTRAINT fk_security_identifier_type FOREIGN KEY (id_type) REFERENCES stonks.identifier_type(id_type) ON UPDATE CASCADE;

ALTER TABLE ONLY stonks.security
    ADD CONSTRAINT fk_security_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id);

ALTER TABLE ONLY stonks.security_successor_relationship
    ADD CONSTRAINT fk_security_successor_predecessor_issuer FOREIGN KEY (predecessor_issuer_id) REFERENCES stonks.issuer(issuer_id);

ALTER TABLE ONLY stonks.security_successor_relationship
    ADD CONSTRAINT fk_security_successor_predecessor_listing FOREIGN KEY (predecessor_listing_id) REFERENCES stonks.listing(listing_id);

ALTER TABLE ONLY stonks.security_successor_relationship
    ADD CONSTRAINT fk_security_successor_predecessor_security FOREIGN KEY (predecessor_security_id) REFERENCES stonks.security(security_id);

ALTER TABLE ONLY stonks.security_successor_relationship
    ADD CONSTRAINT fk_security_successor_successor_issuer FOREIGN KEY (successor_issuer_id) REFERENCES stonks.issuer(issuer_id);

ALTER TABLE ONLY stonks.security_successor_relationship
    ADD CONSTRAINT fk_security_successor_successor_listing FOREIGN KEY (successor_listing_id) REFERENCES stonks.listing(listing_id);

ALTER TABLE ONLY stonks.security_successor_relationship
    ADD CONSTRAINT fk_security_successor_successor_security FOREIGN KEY (successor_security_id) REFERENCES stonks.security(security_id);

ALTER TABLE ONLY stonks.security
    ADD CONSTRAINT fk_security_type FOREIGN KEY (instrument_type_code) REFERENCES stonks.instrument_type(type_code);

ALTER TABLE ONLY stonks.provider_observation
    ADD CONSTRAINT provider_observation_source_snapshot_id_fkey FOREIGN KEY (source_snapshot_id) REFERENCES stonks.provider_source_snapshot(source_snapshot_id);

ALTER TABLE ONLY stonks.provider_source_snapshot_object
    ADD CONSTRAINT provider_source_snapshot_object_source_snapshot_id_fkey FOREIGN KEY (source_snapshot_id) REFERENCES stonks.provider_source_snapshot(source_snapshot_id);

ALTER TABLE ONLY stonks.provider_source_snapshot
    ADD CONSTRAINT provider_source_snapshot_provider_code_fkey FOREIGN KEY (provider_code) REFERENCES stonks.provider(provider_code);
