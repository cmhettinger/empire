```mermaid
flowchart LR
  instrument_type["instrument_type"]
  ohlcv_daily["ohlcv_daily"]
  provider["provider"]
  provider_listing["provider_listing"]

  provider_listing -->|fk_ohlcv_daily_provider_listing| ohlcv_daily
  instrument_type -->|fk_provider_listing_instrument_type| provider_listing
  provider -->|fk_provider_listing_provider| provider_listing
```
