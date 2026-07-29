-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_add_yahoo_instrument_taxonomy
--
-- Purpose:
--   Add the index and continuous-futures instrument types required by the
--   bounded Yahoo OHLCV provider-listing universe.
--
-- Notes:
--   - Existing INDEX and DERIVATIVE instrument classes are reused.
--   - Upserts keep the reference data deterministic and reactivate the
--     reviewed taxonomy values if they already exist.
-- =====================================================================

SET search_path TO stonks, public;

INSERT INTO instrument_type (type_code, class_code, type_name, description)
VALUES
    (
        'YIELD_INDEX',
        'INDEX',
        'Yield Index',
        'Interest rate or yield index'
    ),
    (
        'EQUITY_INDEX',
        'INDEX',
        'Equity Index',
        'Equity market benchmark index'
    ),
    (
        'COMMODITY_INDEX',
        'INDEX',
        'Commodity Index',
        'Commodity market benchmark index'
    ),
    (
        'CURRENCY_INDEX',
        'INDEX',
        'Currency Index',
        'Currency market benchmark index'
    ),
    (
        'CONTINUOUS_FUTURE_COMMODITY',
        'DERIVATIVE',
        'Commodity Continuous Future',
        'Rolling commodity futures series spanning multiple contracts'
    ),
    (
        'CONTINUOUS_FUTURE_EQUITY',
        'DERIVATIVE',
        'Equity Continuous Future',
        'Rolling equity-index futures series spanning multiple contracts'
    )
ON CONFLICT (type_code) DO UPDATE
SET
    class_code  = EXCLUDED.class_code,
    type_name   = EXCLUDED.type_name,
    description = EXCLUDED.description,
    is_active   = TRUE;
