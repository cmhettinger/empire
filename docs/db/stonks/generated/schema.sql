
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
    source_code character varying(32) NOT NULL,
    raw_name text NOT NULL,
    normalized_name text,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT ck_exchange_alias_source_upper CHECK (((source_code)::text = upper((source_code)::text)))
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
    source_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_issuer_class_dates CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT ck_issuer_class_source_upper CHECK (((source_code IS NULL) OR ((source_code)::text = upper((source_code)::text))))
);

CREATE TABLE stonks.issuer_identifier (
    issuer_identifier_id uuid DEFAULT gen_random_uuid() NOT NULL,
    issuer_id uuid NOT NULL,
    id_type character varying(32) NOT NULL,
    id_value text NOT NULL,
    valid_from date,
    valid_to date,
    source_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_issuer_identifier_dates CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT ck_issuer_identifier_source_upper CHECK (((source_code IS NULL) OR ((source_code)::text = upper((source_code)::text)))),
    CONSTRAINT ck_issuer_identifier_type_upper CHECK (((id_type)::text = upper((id_type)::text)))
);

CREATE TABLE stonks.issuer_name_history (
    issuer_name_id uuid DEFAULT gen_random_uuid() NOT NULL,
    issuer_id uuid NOT NULL,
    name text NOT NULL,
    valid_from date,
    valid_to date,
    source_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_issuer_name_dates CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT ck_issuer_name_source_upper CHECK (((source_code IS NULL) OR ((source_code)::text = upper((source_code)::text))))
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
    source_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_listing_symbol_dates CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT ck_listing_symbol_source_upper CHECK (((source_code IS NULL) OR ((source_code)::text = upper((source_code)::text))))
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
    CONSTRAINT ck_security_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying, 'RETIRED'::character varying, 'UNKNOWN'::character varying])::text[])))
);

CREATE TABLE stonks.security_event (
    event_id uuid DEFAULT gen_random_uuid() NOT NULL,
    issuer_id uuid,
    security_id uuid,
    listing_id uuid,
    event_type character varying(32) NOT NULL,
    event_date date,
    source_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    description text,
    details_json jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_security_event_source_upper CHECK (((source_code IS NULL) OR ((source_code)::text = upper((source_code)::text)))),
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
    source_code character varying(32),
    confidence_code character varying(16) DEFAULT 'HIGH'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_security_identifier_dates CHECK (((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT ck_security_identifier_source_upper CHECK (((source_code IS NULL) OR ((source_code)::text = upper((source_code)::text)))),
    CONSTRAINT ck_security_identifier_type_upper CHECK (((id_type)::text = upper((id_type)::text)))
);

CREATE TABLE stonks.source_evidence (
    source_evidence_id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_obs_id uuid NOT NULL,
    issuer_id uuid,
    security_id uuid,
    listing_id uuid,
    event_id uuid,
    evidence_role character varying(24) DEFAULT 'SUPPORTS'::character varying NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_source_evidence_role CHECK (((evidence_role)::text = ANY ((ARRAY['SUPPORTS'::character varying, 'CONFLICTS'::character varying, 'CREATED_FROM'::character varying, 'UPDATED_FROM'::character varying, 'MANUAL_REVIEW'::character varying])::text[]))),
    CONSTRAINT ck_source_evidence_target CHECK (((issuer_id IS NOT NULL) OR (security_id IS NOT NULL) OR (listing_id IS NOT NULL) OR (event_id IS NOT NULL)))
);

CREATE TABLE stonks.source_observation (
    source_obs_id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_code character varying(32) NOT NULL,
    source_date date,
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
    CONSTRAINT ck_source_obs_source_upper CHECK (((source_code)::text = upper((source_code)::text)))
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

ALTER TABLE ONLY stonks.classification_code
    ADD CONSTRAINT classification_code_pkey PRIMARY KEY (class_code_id);

ALTER TABLE ONLY stonks.confidence_level
    ADD CONSTRAINT confidence_level_pkey PRIMARY KEY (confidence_code);

ALTER TABLE ONLY stonks.exchange_alias
    ADD CONSTRAINT exchange_alias_pkey PRIMARY KEY (exchange_alias_id);

ALTER TABLE ONLY stonks.exchange
    ADD CONSTRAINT exchange_exchange_code_key UNIQUE (exchange_code);

ALTER TABLE ONLY stonks.exchange
    ADD CONSTRAINT exchange_pkey PRIMARY KEY (exchange_id);

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

ALTER TABLE ONLY stonks.security_event
    ADD CONSTRAINT security_event_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY stonks.security_identifier
    ADD CONSTRAINT security_identifier_pkey PRIMARY KEY (security_identifier_id);

ALTER TABLE ONLY stonks.security
    ADD CONSTRAINT security_pkey PRIMARY KEY (security_id);

ALTER TABLE ONLY stonks.source_evidence
    ADD CONSTRAINT source_evidence_pkey PRIMARY KEY (source_evidence_id);

ALTER TABLE ONLY stonks.source_observation
    ADD CONSTRAINT source_observation_pkey PRIMARY KEY (source_obs_id);

ALTER TABLE ONLY stonks.classification_code
    ADD CONSTRAINT uq_classification_code UNIQUE (class_system, code);

ALTER TABLE ONLY stonks.confidence_level
    ADD CONSTRAINT uq_confidence_level_rank UNIQUE (rank);

ALTER TABLE ONLY stonks.exchange_alias
    ADD CONSTRAINT uq_exchange_alias_source_raw UNIQUE (source_code, raw_name);

ALTER TABLE ONLY stonks.issuer_classification
    ADD CONSTRAINT uq_issuer_class UNIQUE (issuer_id, class_code_id, valid_from);

ALTER TABLE ONLY stonks.issuer_identifier
    ADD CONSTRAINT uq_issuer_identifier UNIQUE (id_type, id_value, issuer_id);

ALTER TABLE ONLY stonks.issuer_name_history
    ADD CONSTRAINT uq_issuer_name_history UNIQUE (issuer_id, name, valid_from);

ALTER TABLE ONLY stonks.listing_symbol_history
    ADD CONSTRAINT uq_listing_symbol_history UNIQUE (listing_id, ticker_norm, valid_from);

ALTER TABLE ONLY stonks.security_identifier
    ADD CONSTRAINT uq_security_identifier UNIQUE (id_type, id_value, security_id);

CREATE INDEX ix_classification_code ON stonks.classification_code USING btree (code);

CREATE INDEX ix_classification_system ON stonks.classification_code USING btree (class_system);

CREATE INDEX ix_exchange_alias_exchange ON stonks.exchange_alias USING btree (exchange_id);

CREATE INDEX ix_exchange_alias_source ON stonks.exchange_alias USING btree (source_code);

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

CREATE INDEX ix_issuer_country ON stonks.issuer USING btree (country_alpha2);

CREATE INDEX ix_issuer_identifier_issuer ON stonks.issuer_identifier USING btree (issuer_id);

CREATE INDEX ix_issuer_identifier_lookup ON stonks.issuer_identifier USING btree (id_type, id_value);

CREATE INDEX ix_issuer_name ON stonks.issuer USING btree (current_name);

CREATE INDEX ix_issuer_name_history_issuer ON stonks.issuer_name_history USING btree (issuer_id);

CREATE INDEX ix_issuer_name_history_name ON stonks.issuer_name_history USING btree (name);

CREATE INDEX ix_issuer_status ON stonks.issuer USING btree (status);

CREATE INDEX ix_issuer_type ON stonks.issuer USING btree (issuer_type);

CREATE INDEX ix_listing_currency ON stonks.listing USING btree (currency_code);

CREATE INDEX ix_listing_exchange ON stonks.listing USING btree (exchange_id);

CREATE INDEX ix_listing_security ON stonks.listing USING btree (security_id);

CREATE INDEX ix_listing_status ON stonks.listing USING btree (status);

CREATE INDEX ix_listing_symbol_active ON stonks.listing_symbol_history USING btree (ticker_norm) WHERE (valid_to IS NULL);

CREATE INDEX ix_listing_symbol_listing ON stonks.listing_symbol_history USING btree (listing_id);

CREATE INDEX ix_listing_symbol_ticker ON stonks.listing_symbol_history USING btree (ticker_norm);

CREATE INDEX ix_listing_ticker_norm ON stonks.listing USING btree (ticker_norm);

CREATE INDEX ix_security_currency ON stonks.security USING btree (currency_code);

CREATE INDEX ix_security_event_issuer ON stonks.security_event USING btree (issuer_id);

CREATE INDEX ix_security_event_listing ON stonks.security_event USING btree (listing_id);

CREATE INDEX ix_security_event_security ON stonks.security_event USING btree (security_id);

CREATE INDEX ix_security_event_type_date ON stonks.security_event USING btree (event_type, event_date);

CREATE INDEX ix_security_identifier_lookup ON stonks.security_identifier USING btree (id_type, id_value);

CREATE INDEX ix_security_identifier_security ON stonks.security_identifier USING btree (security_id);

CREATE INDEX ix_security_issuer ON stonks.security USING btree (issuer_id);

CREATE INDEX ix_security_status ON stonks.security USING btree (status);

CREATE INDEX ix_security_title ON stonks.security USING btree (security_title);

CREATE INDEX ix_security_type ON stonks.security USING btree (instrument_type_code);

CREATE INDEX ix_source_evidence_event ON stonks.source_evidence USING btree (event_id);

CREATE INDEX ix_source_evidence_issuer ON stonks.source_evidence USING btree (issuer_id);

CREATE INDEX ix_source_evidence_listing ON stonks.source_evidence USING btree (listing_id);

CREATE INDEX ix_source_evidence_obs ON stonks.source_evidence USING btree (source_obs_id);

CREATE INDEX ix_source_evidence_security ON stonks.source_evidence USING btree (security_id);

CREATE INDEX ix_source_obs_accession ON stonks.source_observation USING btree (accession_no);

CREATE INDEX ix_source_obs_object ON stonks.source_observation USING btree (object_id);

CREATE INDEX ix_source_obs_source_date ON stonks.source_observation USING btree (source_code, source_date);

CREATE UNIQUE INDEX ux_issuer_cik ON stonks.issuer USING btree (cik) WHERE (cik IS NOT NULL);

CREATE UNIQUE INDEX ux_listing_active_lookup ON stonks.listing USING btree (exchange_id, ticker_norm) WHERE ((valid_to IS NULL) AND (ticker_norm IS NOT NULL));

CREATE UNIQUE INDEX ux_source_obs_raw_key ON stonks.source_observation USING btree (source_code, raw_key) WHERE (raw_key IS NOT NULL);

ALTER TABLE ONLY stonks.exchange_alias
    ADD CONSTRAINT fk_exchange_alias_exchange FOREIGN KEY (exchange_id) REFERENCES stonks.exchange(exchange_id) ON DELETE CASCADE;

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

ALTER TABLE ONLY stonks.issuer
    ADD CONSTRAINT fk_issuer_country FOREIGN KEY (country_alpha2) REFERENCES stonks.iso3166_country(alpha2);

ALTER TABLE ONLY stonks.issuer_identifier
    ADD CONSTRAINT fk_issuer_identifier_confidence FOREIGN KEY (confidence_code) REFERENCES stonks.confidence_level(confidence_code);

ALTER TABLE ONLY stonks.issuer_identifier
    ADD CONSTRAINT fk_issuer_identifier_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.issuer_name_history
    ADD CONSTRAINT fk_issuer_name_confidence FOREIGN KEY (confidence_code) REFERENCES stonks.confidence_level(confidence_code);

ALTER TABLE ONLY stonks.issuer_name_history
    ADD CONSTRAINT fk_issuer_name_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id) ON DELETE CASCADE;

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

ALTER TABLE ONLY stonks.security
    ADD CONSTRAINT fk_security_currency FOREIGN KEY (currency_code) REFERENCES stonks.iso4217_currency(code);

ALTER TABLE ONLY stonks.security_event
    ADD CONSTRAINT fk_security_event_confidence FOREIGN KEY (confidence_code) REFERENCES stonks.confidence_level(confidence_code);

ALTER TABLE ONLY stonks.security_event
    ADD CONSTRAINT fk_security_event_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id);

ALTER TABLE ONLY stonks.security_event
    ADD CONSTRAINT fk_security_event_listing FOREIGN KEY (listing_id) REFERENCES stonks.listing(listing_id);

ALTER TABLE ONLY stonks.security_event
    ADD CONSTRAINT fk_security_event_security FOREIGN KEY (security_id) REFERENCES stonks.security(security_id);

ALTER TABLE ONLY stonks.security_identifier
    ADD CONSTRAINT fk_security_identifier_confidence FOREIGN KEY (confidence_code) REFERENCES stonks.confidence_level(confidence_code);

ALTER TABLE ONLY stonks.security_identifier
    ADD CONSTRAINT fk_security_identifier_security FOREIGN KEY (security_id) REFERENCES stonks.security(security_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.security
    ADD CONSTRAINT fk_security_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id);

ALTER TABLE ONLY stonks.security
    ADD CONSTRAINT fk_security_type FOREIGN KEY (instrument_type_code) REFERENCES stonks.instrument_type(type_code);

ALTER TABLE ONLY stonks.source_evidence
    ADD CONSTRAINT fk_source_evidence_event FOREIGN KEY (event_id) REFERENCES stonks.security_event(event_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.source_evidence
    ADD CONSTRAINT fk_source_evidence_issuer FOREIGN KEY (issuer_id) REFERENCES stonks.issuer(issuer_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.source_evidence
    ADD CONSTRAINT fk_source_evidence_listing FOREIGN KEY (listing_id) REFERENCES stonks.listing(listing_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.source_evidence
    ADD CONSTRAINT fk_source_evidence_obs FOREIGN KEY (source_obs_id) REFERENCES stonks.source_observation(source_obs_id) ON DELETE CASCADE;

ALTER TABLE ONLY stonks.source_evidence
    ADD CONSTRAINT fk_source_evidence_security FOREIGN KEY (security_id) REFERENCES stonks.security(security_id) ON DELETE CASCADE;
