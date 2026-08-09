```mermaid
erDiagram
  classification_code {
    UUID class_code_id PK
    VARCHAR class_system FK
    VARCHAR code
    TEXT label
    TEXT description
    BOOL is_active
  }

  classification_system {
    VARCHAR class_system PK
    TEXT system_name
    VARCHAR provider_code FK
    TEXT description
    BOOL is_active
  }

  confidence_level {
    VARCHAR confidence_code PK
    SMALLINT rank
    TEXT description
    BOOL is_active
  }

  exchange {
    UUID exchange_id PK
    VARCHAR exchange_code
    TEXT exchange_name
    VARCHAR mic FK
    VARCHAR country_alpha2 FK
    VARCHAR exchange_type
    BOOL is_synthetic
    BOOL is_active
    TEXT notes
  }

  exchange_alias {
    UUID exchange_alias_id PK
    UUID exchange_id FK
    VARCHAR provider_code FK
    TEXT raw_name
    TEXT normalized_name
    BOOL is_active
  }

  identifier_type {
    VARCHAR id_type PK
    TEXT id_name
    VARCHAR applies_to
    TEXT description
    BOOL is_active
  }

  instrument_class {
    VARCHAR class_code PK
    TEXT class_name
    TEXT description
    SMALLINT sort_order
    BOOL is_active
  }

  instrument_type {
    VARCHAR type_code PK
    VARCHAR class_code FK
    TEXT type_name
    TEXT description
    BOOL is_active
  }

  iso10383_mic {
    VARCHAR mic PK
    VARCHAR operating_mic FK
    VARCHAR mic_type
    TEXT market_name
    TEXT legal_entity
    TEXT acronym
    TEXT city
    VARCHAR country_alpha2 FK
    TEXT website
    VARCHAR market_category_code FK
    TEXT status
    DATE created_date
    TEXT source
  }

  iso10383_mic_cat {
    VARCHAR code PK
    TEXT description
  }

  iso3166_country {
    VARCHAR alpha2 PK
    VARCHAR alpha3
    VARCHAR numeric3
    TEXT name
  }

  iso4217_currency {
    VARCHAR code PK
    VARCHAR numeric3
    TEXT name
    SMALLINT minor_unit
  }

  issuer {
    UUID issuer_id PK
    VARCHAR cik
    VARCHAR issuer_type
    TEXT current_name
    VARCHAR country_alpha2 FK
    VARCHAR sic_code
    VARCHAR status
    DATE first_seen
    DATE last_seen
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
  }

  issuer_classification {
    UUID issuer_class_id PK
    UUID issuer_id FK
    UUID class_code_id FK
    DATE valid_from
    DATE valid_to
    VARCHAR provider_code FK
    VARCHAR confidence_code FK
    TIMESTAMPTZ created_at
  }

  issuer_identifier {
    UUID issuer_identifier_id PK
    UUID issuer_id FK
    VARCHAR id_type FK
    TEXT id_value
    DATE valid_from
    DATE valid_to
    VARCHAR provider_code FK
    VARCHAR confidence_code FK
    TIMESTAMPTZ created_at
  }

  issuer_name_history {
    UUID issuer_name_id PK
    UUID issuer_id FK
    TEXT name
    DATE valid_from
    DATE valid_to
    VARCHAR provider_code FK
    VARCHAR confidence_code FK
    TIMESTAMPTZ created_at
  }

  listing {
    UUID listing_id PK
    UUID security_id FK
    UUID exchange_id FK
    TEXT current_ticker
    TEXT ticker_norm
    VARCHAR currency_code FK
    BOOL is_primary
    VARCHAR status
    DATE valid_from
    DATE valid_to
    DATE first_seen
    DATE last_seen
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
  }

  listing_symbol_history {
    UUID listing_symbol_id PK
    UUID listing_id FK
    TEXT ticker_raw
    TEXT ticker_norm
    TEXT ticker_display
    DATE valid_from
    DATE valid_to
    VARCHAR provider_code FK
    VARCHAR confidence_code FK
    TIMESTAMPTZ created_at
  }

  ohlcv_daily {
    UUID provider_listing_id PK
    DATE trading_date PK
    NUMERIC open
    NUMERIC high
    NUMERIC low
    NUMERIC close
    NUMERIC volume
    NUMERIC change
    NUMERIC changepct
    NUMERIC typ
    NUMERIC hl_range
    NUMERIC oc_range
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
  }

  ohlcv_daily_tech_indicators_a {
    UUID provider_listing_id PK
    DATE trading_date PK
    UUID relative_strength_benchmark_provider_listing_id FK
    INT history_observation_count
    VARCHAR calculation_version
    UUID run_id
    TIMESTAMPTZ calculated_at
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
    NUMERIC open
    NUMERIC high
    NUMERIC low
    NUMERIC close
    NUMERIC volume
    DOUBLE return_1d_pct
    DOUBLE return_2d_pct
    DOUBLE return_3d_pct
    DOUBLE return_5d_pct
    DOUBLE return_10d_pct
    DOUBLE return_20d_pct
    DOUBLE return_63d_pct
    DOUBLE return_126d_pct
    DOUBLE return_252d_pct
    DOUBLE gap_1d_pct
    DOUBLE sma_20
    DOUBLE sma_50
    DOUBLE sma_200
    DOUBLE ema_12
    DOUBLE ema_20
    DOUBLE ema_26
    DOUBLE ema_50
    DOUBLE sma_50_change_20d_pct
    DOUBLE sma_200_change_20d_pct
    DOUBLE hh_20
    DOUBLE hh_50
    DOUBLE hh_252
    DOUBLE ll_20
    DOUBLE ll_50
    DOUBLE rsi_14
    DOUBLE atr_14
    DOUBLE return_volatility_20d_pct
    DOUBLE return_volatility_60d_pct
    DOUBLE return_1d_zscore_20d
    DOUBLE return_3d_zscore_20d
    DOUBLE price_stddev_20
    DOUBLE plus_di_14
    DOUBLE minus_di_14
    DOUBLE adx_14
    DOUBLE macd_12_26
    DOUBLE macd_signal_12_26_9
    DOUBLE macd_histogram_12_26_9
    DOUBLE volume_avg_20
    DOUBLE volume_avg_60
    DOUBLE dollar_volume_avg_20
    INT consecutive_up_days
    INT consecutive_down_days
    DOUBLE rel_spx
    DOUBLE pct_rel_spx_20
    DOUBLE pct_rel_spx_50
    DOUBLE relative_return_spx_20d_pct
    DOUBLE relative_return_spx_63d_pct
    DOUBLE relative_return_spx_126d_pct
    DOUBLE relative_return_spx_252d_pct
    DOUBLE spx_beta_60d
    DOUBLE spx_beta_252d
    DOUBLE spx_correlation_60d
    DOUBLE spx_correlation_252d
    DOUBLE dollar_volume
    DOUBLE intraday_return_1d_pct
    DOUBLE daily_range_pct
    DOUBLE close_location_1d
    DOUBLE pct_sma_20
    DOUBLE pct_sma_50
    DOUBLE pct_sma_200
    DOUBLE pct_ema_20
    DOUBLE pct_ema_50
    DOUBLE pct_sma_20_vs_50
    DOUBLE pct_sma_20_vs_200
    DOUBLE pct_sma_50_vs_200
    DOUBLE pct_hh_20
    DOUBLE pct_hh_50
    DOUBLE pct_hh_252
    DOUBLE pct_ll_20
    DOUBLE pct_ll_50
    DOUBLE atr_pct_14
    DOUBLE bollinger_percent_b_20_2
    DOUBLE bollinger_bandwidth_20_2
    DOUBLE volume_ratio_20
    DOUBLE macd_12_26_pct
    DOUBLE macd_histogram_12_26_9_pct
  }

  ohlcv_daily_tech_indicators_b {
    UUID provider_listing_id PK
    DATE trading_date PK
    UUID relative_strength_benchmark_provider_listing_id FK
    INT history_observation_count
    VARCHAR calculation_version
    UUID run_id
    TIMESTAMPTZ calculated_at
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
    NUMERIC open
    NUMERIC high
    NUMERIC low
    NUMERIC close
    NUMERIC volume
    DOUBLE return_1d_pct
    DOUBLE return_2d_pct
    DOUBLE return_3d_pct
    DOUBLE return_5d_pct
    DOUBLE return_10d_pct
    DOUBLE return_20d_pct
    DOUBLE return_63d_pct
    DOUBLE return_126d_pct
    DOUBLE return_252d_pct
    DOUBLE gap_1d_pct
    DOUBLE sma_20
    DOUBLE sma_50
    DOUBLE sma_200
    DOUBLE ema_12
    DOUBLE ema_20
    DOUBLE ema_26
    DOUBLE ema_50
    DOUBLE sma_50_change_20d_pct
    DOUBLE sma_200_change_20d_pct
    DOUBLE hh_20
    DOUBLE hh_50
    DOUBLE hh_252
    DOUBLE ll_20
    DOUBLE ll_50
    DOUBLE rsi_14
    DOUBLE atr_14
    DOUBLE return_volatility_20d_pct
    DOUBLE return_volatility_60d_pct
    DOUBLE return_1d_zscore_20d
    DOUBLE return_3d_zscore_20d
    DOUBLE price_stddev_20
    DOUBLE plus_di_14
    DOUBLE minus_di_14
    DOUBLE adx_14
    DOUBLE macd_12_26
    DOUBLE macd_signal_12_26_9
    DOUBLE macd_histogram_12_26_9
    DOUBLE volume_avg_20
    DOUBLE volume_avg_60
    DOUBLE dollar_volume_avg_20
    INT consecutive_up_days
    INT consecutive_down_days
    DOUBLE rel_spx
    DOUBLE pct_rel_spx_20
    DOUBLE pct_rel_spx_50
    DOUBLE relative_return_spx_20d_pct
    DOUBLE relative_return_spx_63d_pct
    DOUBLE relative_return_spx_126d_pct
    DOUBLE relative_return_spx_252d_pct
    DOUBLE spx_beta_60d
    DOUBLE spx_beta_252d
    DOUBLE spx_correlation_60d
    DOUBLE spx_correlation_252d
    DOUBLE dollar_volume
    DOUBLE intraday_return_1d_pct
    DOUBLE daily_range_pct
    DOUBLE close_location_1d
    DOUBLE pct_sma_20
    DOUBLE pct_sma_50
    DOUBLE pct_sma_200
    DOUBLE pct_ema_20
    DOUBLE pct_ema_50
    DOUBLE pct_sma_20_vs_50
    DOUBLE pct_sma_20_vs_200
    DOUBLE pct_sma_50_vs_200
    DOUBLE pct_hh_20
    DOUBLE pct_hh_50
    DOUBLE pct_hh_252
    DOUBLE pct_ll_20
    DOUBLE pct_ll_50
    DOUBLE atr_pct_14
    DOUBLE bollinger_percent_b_20_2
    DOUBLE bollinger_bandwidth_20_2
    DOUBLE volume_ratio_20
    DOUBLE macd_12_26_pct
    DOUBLE macd_histogram_12_26_9_pct
  }

  ohlcv_session_policy {
    VARCHAR session_policy_code PK
    TEXT calendar_name
    TEXT timezone_name
    VARCHAR eligibility_rule
    TIME_WITHOUT_TIME_ZONE cutoff_local_time
    INT availability_delay_minutes
    VARCHAR session_date_rule
    TEXT description
  }

  provider {
    VARCHAR provider_code PK
    TEXT provider_name
    VARCHAR provider_type
    TEXT website
    TEXT description
    BOOL is_active
  }

  provider_evidence {
    UUID provider_evidence_id PK
    UUID provider_observation_id FK
    UUID issuer_id FK
    UUID security_id FK
    UUID listing_id FK
    UUID event_id FK
    VARCHAR evidence_role
    TEXT notes
    TIMESTAMPTZ created_at
  }

  provider_listing {
    UUID provider_listing_id PK
    VARCHAR provider_code FK
    TEXT market
    TEXT ticker
    TEXT name
    VARCHAR instrument_type_code FK
    DATE first_seen
    DATE last_seen
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
    VARCHAR status
    JSONB metadata
    VARCHAR session_policy_code FK
  }

  provider_observation {
    UUID provider_observation_id PK
    VARCHAR provider_code FK
    DATE provider_date
    TIMESTAMPTZ observed_at
    TEXT accession_no
    VARCHAR form_type
    DATE filing_date
    UUID object_id
    TEXT object_key
    TEXT source_url
    TEXT raw_key
    JSONB summary_json
    TIMESTAMPTZ created_at
    UUID source_snapshot_id FK
  }

  provider_source_snapshot {
    UUID source_snapshot_id PK
    VARCHAR provider_code FK
    VARCHAR source_code
    CHAR content_sha256
    UUID first_seen_object_id
    UUID first_seen_run_id
    VARCHAR parser_version
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
  }

  provider_source_snapshot_object {
    UUID source_snapshot_object_id PK
    UUID source_snapshot_id FK
    UUID object_id
    TIMESTAMPTZ created_at
  }

  security {
    UUID security_id PK
    UUID issuer_id FK
    VARCHAR instrument_type_code FK
    TEXT security_title
    TEXT share_class
    VARCHAR currency_code FK
    VARCHAR status
    DATE first_seen
    DATE last_seen
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
    VARCHAR identity_status
  }

  security_event {
    UUID event_id PK
    UUID issuer_id FK
    UUID security_id FK
    UUID listing_id FK
    VARCHAR event_type
    DATE event_date
    VARCHAR provider_code FK
    VARCHAR confidence_code FK
    TEXT description
    JSONB details_json
    TIMESTAMPTZ created_at
  }

  security_identifier {
    UUID security_identifier_id PK
    UUID security_id FK
    VARCHAR id_type FK
    TEXT id_value
    DATE valid_from
    DATE valid_to
    VARCHAR provider_code FK
    VARCHAR confidence_code FK
    TIMESTAMPTZ created_at
  }

  security_reconciliation_decision {
    UUID decision_id PK
    UUID evaluation_id FK
    UUID run_id
    UUID security_id FK
    VARCHAR decision_type
    VARCHAR previous_identity_status
    VARCHAR new_identity_status
    TIMESTAMPTZ applied_at
    TEXT applied_by
    TEXT explanation
    JSONB details_json
  }

  security_reconciliation_evaluation {
    UUID evaluation_id PK
    UUID run_id
    UUID security_id FK
    UUID issuer_id FK
    UUID listing_id FK
    UUID related_security_id FK
    UUID related_listing_id FK
    VARCHAR decision_type
    VARCHAR rule_id
    VARCHAR rule_version
    VARCHAR confidence_code FK
    NUMERIC confidence_score
    VARCHAR previous_identity_status
    VARCHAR evaluated_identity_status
    TEXT explanation
    ARRAY reason_codes
    JSONB details_json
    TIMESTAMPTZ created_at
  }

  security_reconciliation_evaluation_evidence {
    UUID evaluation_id PK
    UUID provider_evidence_id PK
    VARCHAR evidence_role PK
    TIMESTAMPTZ created_at
  }

  security_reconciliation_evaluation_reconciliation_evidence {
    UUID evaluation_id PK
    UUID reconciliation_evidence_id PK
    VARCHAR evidence_role PK
    TIMESTAMPTZ created_at
  }

  security_reconciliation_evidence {
    UUID reconciliation_evidence_id PK
    UUID security_id FK
    UUID issuer_id FK
    UUID listing_id FK
    VARCHAR evidence_type
    VARCHAR evidence_role
    CHAR evidence_key
    JSONB summary_json
    VARCHAR collector_version
    TIMESTAMPTZ created_at
  }

  security_reconciliation_evidence_provider_evidence {
    UUID reconciliation_evidence_id PK
    UUID provider_evidence_id PK
  }

  security_reconciliation_evidence_source_snapshot {
    UUID reconciliation_evidence_id PK
    UUID source_snapshot_id PK
  }

  security_successor_relationship {
    UUID relationship_id PK
    UUID predecessor_issuer_id FK
    UUID successor_issuer_id FK
    UUID predecessor_security_id FK
    UUID successor_security_id FK
    UUID predecessor_listing_id FK
    UUID successor_listing_id FK
    VARCHAR relationship_type
    DATE effective_date
    NUMERIC exchange_ratio
    TEXT source_url
    JSONB details_json
    TIMESTAMPTZ created_at
  }

  stg_iso10383_mic {
    TEXT mic
    TEXT operating_mic
    TEXT oprt_sgmt
    TEXT market_name
    TEXT legal_entity_name
    TEXT lei
    TEXT market_category_code
    TEXT acronym
    TEXT iso_country_code
    TEXT city
    TEXT website
    TEXT status
    TEXT creation_date
    TEXT last_update_date
    TEXT last_validation_date
    TEXT expiry_date
    TEXT comments
  }

  stg_iso3166_country {
    TEXT name
    TEXT alpha2
    TEXT alpha3
    TEXT country_code
    TEXT iso_3166_2
    TEXT region
    TEXT sub_region
    TEXT intermediate_region
    TEXT region_code
    TEXT sub_region_code
    TEXT intermediate_region_code
  }

  stg_iso4217_currency {
    TEXT entity
    TEXT currency
    TEXT alphabetic_code
    TEXT numeric_code
    TEXT minor_unit
    TEXT withdrawal_date
  }

  stg_sec_sic_classification_code {
    TEXT sic_code
    TEXT office
    TEXT industry_title
  }

  tech_indicators_publication {
    UUID publication_id PK
    VARCHAR publication_kind
    VARCHAR status
    VARCHAR calculation_version
    VARCHAR publication_method
    SMALLINT scope_schema_version
    CHAR scope_hash
    DATE effective_date
    DATE requested_start_date
    DATE requested_end_date
    UUID run_id
    BOOL benchmark_required
    UUID benchmark_provider_listing_id FK
    VARCHAR benchmark_contract_version
    DATE benchmark_coverage_start_date
    DATE benchmark_coverage_end_date
    BIGINT benchmark_source_row_count
    INT expected_listing_count
    BIGINT expected_source_row_count
    BIGINT expected_payload_row_count
    BIGINT inserted_row_count
    BIGINT updated_row_count
    BIGINT deleted_row_count
    BIGINT equivalent_row_count
    INT warning_count
    INT failure_count
    INT completed_batch_count
    BIGINT staged_payload_row_count
    UUID resume_provider_listing_id
    DATE resume_trading_date
    TIMESTAMPTZ resume_cursor_updated_at
    UUID json_report_object_id
    UUID pdf_report_object_id
    TIMESTAMPTZ source_validated_at
    TIMESTAMPTZ prepared_at
    TIMESTAMPTZ published_at
    TIMESTAMPTZ failed_at
    TIMESTAMPTZ abandoned_at
    TIMESTAMPTZ retired_at
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
  }

  tech_indicators_publication_listing {
    UUID publication_id PK
    UUID provider_listing_id PK
    VARCHAR action
    CHAR target_slot
    VARCHAR calculation_version
    DATE source_coverage_start_date
    DATE source_coverage_end_date
    BIGINT source_row_count
    BIGINT payload_row_count
    UUID benchmark_provider_listing_id FK
    TIMESTAMPTZ candidate_completed_at
    BOOL is_active
    TIMESTAMPTZ activated_at
    TIMESTAMPTZ deactivated_at
    TIMESTAMPTZ created_at
    TIMESTAMPTZ updated_at
  }

  classification_system ||--o{ classification_code : "fk_classification_code_system"
  provider ||--o{ classification_system : "fk_classification_system_provider"
  iso3166_country ||--o{ exchange : "fk_exchange_country"
  iso10383_mic ||--o{ exchange : "fk_exchange_mic"
  exchange ||--o{ exchange_alias : "fk_exchange_alias_exchange"
  provider ||--o{ exchange_alias : "fk_exchange_alias_provider"
  instrument_class ||--o{ instrument_type : "fk_instrument_type_class"
  iso10383_mic_cat ||--o{ iso10383_mic : "fk_iso10383_mic_category"
  iso3166_country ||--o{ iso10383_mic : "fk_iso10383_mic_country"
  iso10383_mic ||--o{ iso10383_mic : "fk_iso10383_mic_operating"
  iso3166_country ||--o{ issuer : "fk_issuer_country"
  classification_code ||--o{ issuer_classification : "fk_issuer_class_code"
  confidence_level ||--o{ issuer_classification : "fk_issuer_class_confidence"
  issuer ||--o{ issuer_classification : "fk_issuer_class_issuer"
  provider ||--o{ issuer_classification : "fk_issuer_class_provider"
  confidence_level ||--o{ issuer_identifier : "fk_issuer_identifier_confidence"
  issuer ||--o{ issuer_identifier : "fk_issuer_identifier_issuer"
  provider ||--o{ issuer_identifier : "fk_issuer_identifier_provider"
  identifier_type ||--o{ issuer_identifier : "fk_issuer_identifier_type"
  confidence_level ||--o{ issuer_name_history : "fk_issuer_name_confidence"
  issuer ||--o{ issuer_name_history : "fk_issuer_name_issuer"
  provider ||--o{ issuer_name_history : "fk_issuer_name_provider"
  iso4217_currency ||--o{ listing : "fk_listing_currency"
  exchange ||--o{ listing : "fk_listing_exchange"
  security ||--o{ listing : "fk_listing_security"
  confidence_level ||--o{ listing_symbol_history : "fk_listing_symbol_confidence"
  listing ||--o{ listing_symbol_history : "fk_listing_symbol_listing"
  provider ||--o{ listing_symbol_history : "fk_listing_symbol_provider"
  provider_listing ||--o{ ohlcv_daily : "fk_ohlcv_daily_provider_listing"
  provider_listing ||--o{ ohlcv_daily_tech_indicators_a : "fk_tech_indicators_a_benchmark_listing"
  ohlcv_daily ||--o{ ohlcv_daily_tech_indicators_a : "fk_tech_indicators_a_source_bar"
  provider_listing ||--o{ ohlcv_daily_tech_indicators_b : "fk_tech_indicators_b_benchmark_listing"
  ohlcv_daily ||--o{ ohlcv_daily_tech_indicators_b : "fk_tech_indicators_b_source_bar"
  security_event ||--o{ provider_evidence : "fk_provider_evidence_event"
  issuer ||--o{ provider_evidence : "fk_provider_evidence_issuer"
  listing ||--o{ provider_evidence : "fk_provider_evidence_listing"
  provider_observation ||--o{ provider_evidence : "fk_provider_evidence_observation"
  security ||--o{ provider_evidence : "fk_provider_evidence_security"
  instrument_type ||--o{ provider_listing : "fk_provider_listing_instrument_type"
  provider ||--o{ provider_listing : "fk_provider_listing_provider"
  ohlcv_session_policy ||--o{ provider_listing : "fk_provider_listing_session_policy"
  provider ||--o{ provider_observation : "fk_provider_observation_provider"
  provider_source_snapshot ||--o{ provider_observation : "provider_observation_source_snapshot_id_fkey"
  provider ||--o{ provider_source_snapshot : "provider_source_snapshot_provider_code_fkey"
  provider_source_snapshot ||--o{ provider_source_snapshot_object : "provider_source_snapshot_object_source_snapshot_id_fkey"
  iso4217_currency ||--o{ security : "fk_security_currency"
  issuer ||--o{ security : "fk_security_issuer"
  instrument_type ||--o{ security : "fk_security_type"
  confidence_level ||--o{ security_event : "fk_security_event_confidence"
  issuer ||--o{ security_event : "fk_security_event_issuer"
  listing ||--o{ security_event : "fk_security_event_listing"
  provider ||--o{ security_event : "fk_security_event_provider"
  security ||--o{ security_event : "fk_security_event_security"
  confidence_level ||--o{ security_identifier : "fk_security_identifier_confidence"
  provider ||--o{ security_identifier : "fk_security_identifier_provider"
  security ||--o{ security_identifier : "fk_security_identifier_security"
  identifier_type ||--o{ security_identifier : "fk_security_identifier_type"
  security_reconciliation_evaluation ||--|| security_reconciliation_decision : "fk_sec_recon_decision_eval"
  security ||--o{ security_reconciliation_decision : "fk_sec_recon_decision_security"
  confidence_level ||--o{ security_reconciliation_evaluation : "fk_sec_recon_eval_confidence"
  issuer ||--o{ security_reconciliation_evaluation : "fk_sec_recon_eval_issuer"
  listing ||--o{ security_reconciliation_evaluation : "fk_sec_recon_eval_listing"
  listing ||--o{ security_reconciliation_evaluation : "fk_sec_recon_eval_related_listing"
  security ||--o{ security_reconciliation_evaluation : "fk_sec_recon_eval_related_security"
  security ||--o{ security_reconciliation_evaluation : "fk_sec_recon_eval_security"
  security_reconciliation_evaluation ||--o{ security_reconciliation_evaluation_evidence : "fk_sec_recon_eval_ev_eval"
  provider_evidence ||--o{ security_reconciliation_evaluation_evidence : "fk_sec_recon_eval_ev_provider"
  security_reconciliation_evaluation ||--o{ security_reconciliation_evaluation_reconciliation_evidence : "fk_sec_recon_eval_recon_evidence_evaluation"
  security_reconciliation_evidence ||--o{ security_reconciliation_evaluation_reconciliation_evidence : "fk_sec_recon_eval_recon_evidence_evidence"
  issuer ||--o{ security_reconciliation_evidence : "fk_sec_recon_evidence_issuer"
  listing ||--o{ security_reconciliation_evidence : "fk_sec_recon_evidence_listing"
  security ||--o{ security_reconciliation_evidence : "fk_sec_recon_evidence_security"
  security_reconciliation_evidence ||--o{ security_reconciliation_evidence_provider_evidence : "fk_sec_recon_evidence_provider_evidence"
  provider_evidence ||--o{ security_reconciliation_evidence_provider_evidence : "fk_sec_recon_evidence_provider_source"
  security_reconciliation_evidence ||--o{ security_reconciliation_evidence_source_snapshot : "fk_sec_recon_evidence_snapshot_evidence"
  provider_source_snapshot ||--o{ security_reconciliation_evidence_source_snapshot : "fk_sec_recon_evidence_snapshot_source"
  issuer ||--o{ security_successor_relationship : "fk_security_successor_predecessor_issuer"
  listing ||--o{ security_successor_relationship : "fk_security_successor_predecessor_listing"
  security ||--o{ security_successor_relationship : "fk_security_successor_predecessor_security"
  issuer ||--o{ security_successor_relationship : "fk_security_successor_successor_issuer"
  listing ||--o{ security_successor_relationship : "fk_security_successor_successor_listing"
  security ||--o{ security_successor_relationship : "fk_security_successor_successor_security"
  provider_listing ||--o{ tech_indicators_publication : "fk_tech_indicators_publication_benchmark"
  provider_listing ||--o{ tech_indicators_publication_listing : "fk_tech_indicators_membership_benchmark"
  provider_listing ||--o{ tech_indicators_publication_listing : "fk_tech_indicators_membership_listing"
  tech_indicators_publication ||--o{ tech_indicators_publication_listing : "fk_tech_indicators_membership_publication"
```
