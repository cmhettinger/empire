-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_security_master_expand_instrument_taxonomy
--
-- Purpose:
--   Refine and expand security-master instrument types before historical
--   SEC backfill.
--
-- Notes:
--   - Existing instrument classes are intentionally unchanged.
--   - ETN is debt-like and belongs under DEBT, not FUND.
--   - Upserts preserve existing rows while adding missing taxonomy values.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Reclassify existing type
-- ---------------------------------------------------------------------

UPDATE instrument_type
SET
    class_code  = 'DEBT',
    type_name   = 'ETN',
    description = 'Exchange-traded note',
    is_active   = TRUE
WHERE type_code = 'ETN';

-- ---------------------------------------------------------------------
-- Expanded instrument types
-- ---------------------------------------------------------------------

INSERT INTO instrument_type (type_code, class_code, type_name, description)
VALUES
    ('LP_UNIT', 'EQUITY', 'LP Unit', 'Limited partnership unit'),
    ('TRACKING_STOCK', 'EQUITY', 'Tracking Stock', 'Equity security tracking a business unit or asset segment'),

    ('ETMF', 'FUND', 'ETMF', 'Exchange-traded managed fund'),
    ('MONEY_MARKET_FUND', 'FUND', 'Money Market Fund', 'Money market mutual fund'),
    ('UIT', 'FUND', 'UIT', 'Unit investment trust'),
    ('BDC', 'FUND', 'BDC', 'Business development company'),

    ('NET_TOTAL_RETURN_INDEX', 'INDEX', 'Net Total Return Index', 'Net total return benchmark index'),

    ('BABY_BOND', 'DEBT', 'Baby Bond', 'Exchange-traded debt security with a small par value'),
    ('CONVERTIBLE_NOTE', 'DEBT', 'Convertible Note', 'Debt note convertible into equity or another security'),
    ('TREASURY', 'DEBT', 'Treasury', 'U.S. Treasury debt security'),
    ('MUNICIPAL_BOND', 'DEBT', 'Municipal Bond', 'Municipal debt security'),
    ('CORPORATE_BOND', 'DEBT', 'Corporate Bond', 'Corporate debt security'),

    ('STRUCTURED_PRODUCT', 'DERIVATIVE', 'Structured Product', 'Structured investment product with derivative-like exposure'),

    ('SPAC_UNIT', 'OTHER', 'SPAC Unit', 'Special purpose acquisition company unit security')
ON CONFLICT (type_code) DO UPDATE
SET
    class_code  = EXCLUDED.class_code,
    type_name   = EXCLUDED.type_name,
    description = EXCLUDED.description,
    is_active   = TRUE;
