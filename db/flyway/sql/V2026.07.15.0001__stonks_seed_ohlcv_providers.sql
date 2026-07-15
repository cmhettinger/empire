-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_seed_ohlcv_providers
--
-- Purpose:
--   Register the provider-native market data sources used by the initial
--   Empire Stonks OHLCV package.
--
-- Notes:
--   - Seed data uses the existing idempotent provider upsert convention.
--   - This migration registers providers only; OHLCV tables are added later.
-- =====================================================================

SET search_path TO stonks, public;

INSERT INTO provider (
    provider_code,
    provider_name,
    provider_type,
    website,
    description
)
VALUES
    (
        'EODDATA',
        'EODData',
        'DATA_SOURCE',
        'https://www.eoddata.com/',
        'End-of-day and historical market data provider'
    ),
    (
        'STOOQ',
        'Stooq',
        'DATA_SOURCE',
        'https://stooq.com/',
        'Market data and historical price data provider'
    ),
    (
        'YAHOO',
        'Yahoo Finance',
        'DATA_SOURCE',
        'https://finance.yahoo.com/',
        'Financial market data provider'
    )
ON CONFLICT (provider_code) DO UPDATE
SET
    provider_name = EXCLUDED.provider_name,
    provider_type = EXCLUDED.provider_type,
    website = EXCLUDED.website,
    description = EXCLUDED.description,
    is_active = TRUE;
