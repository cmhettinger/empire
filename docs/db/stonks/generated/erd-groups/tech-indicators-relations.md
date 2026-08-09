```mermaid
flowchart LR
  instrument_type["instrument_type"]
  ohlcv_daily["ohlcv_daily"]
  ohlcv_daily_tech_indicators_a["ohlcv_daily_tech_indicators_a"]
  ohlcv_daily_tech_indicators_b["ohlcv_daily_tech_indicators_b"]
  ohlcv_session_policy["ohlcv_session_policy"]
  provider["provider"]
  provider_listing["provider_listing"]
  tech_indicators_publication["tech_indicators_publication"]
  tech_indicators_publication_listing["tech_indicators_publication_listing"]

  provider_listing -->|fk_ohlcv_daily_provider_listing| ohlcv_daily
  provider_listing -->|fk_tech_indicators_a_benchmark_listing| ohlcv_daily_tech_indicators_a
  ohlcv_daily -->|fk_tech_indicators_a_source_bar| ohlcv_daily_tech_indicators_a
  provider_listing -->|fk_tech_indicators_b_benchmark_listing| ohlcv_daily_tech_indicators_b
  ohlcv_daily -->|fk_tech_indicators_b_source_bar| ohlcv_daily_tech_indicators_b
  instrument_type -->|fk_provider_listing_instrument_type| provider_listing
  provider -->|fk_provider_listing_provider| provider_listing
  ohlcv_session_policy -->|fk_provider_listing_session_policy| provider_listing
  provider_listing -->|fk_tech_indicators_publication_benchmark| tech_indicators_publication
  provider_listing -->|fk_tech_indicators_membership_benchmark| tech_indicators_publication_listing
  provider_listing -->|fk_tech_indicators_membership_listing| tech_indicators_publication_listing
  tech_indicators_publication -->|fk_tech_indicators_membership_publication| tech_indicators_publication_listing
```
