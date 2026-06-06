-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_securities_seed_exchanges
--
-- Purpose:
--   Seed curated exchanges / venues used by the Empire security master.
--
-- Notes:
--   - ISO MIC registry remains pure in iso10383_mic.
--   - This table contains practical canonical venues used by Empire.
--   - Synthetic/internal venues are allowed here.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Canonical exchanges / venues
-- ---------------------------------------------------------------------

INSERT INTO exchange (
    exchange_code,
    exchange_name,
    mic,
    country_alpha2,
    exchange_type,
    is_synthetic,
    is_active,
    notes
)
VALUES
    ('NYSE', 'New York Stock Exchange', 'XNYS', 'US', 'EXCHANGE', FALSE, TRUE, NULL),
    ('NASDAQ', 'Nasdaq Stock Market', 'XNAS', 'US', 'EXCHANGE', FALSE, TRUE, NULL),
    ('NYSEARCA', 'NYSE Arca', 'ARCX', 'US', 'EXCHANGE', FALSE, TRUE, NULL),
    ('NYSEAMER', 'NYSE American', 'XASE', 'US', 'EXCHANGE', FALSE, TRUE, NULL),
    ('CBOEBZX', 'Cboe BZX Exchange', 'BATS', 'US', 'EXCHANGE', FALSE, TRUE, NULL),
    ('IEX', 'Investors Exchange', 'IEXG', 'US', 'EXCHANGE', FALSE, TRUE, NULL),

    ('OTC', 'Over-the-Counter Markets', NULL, 'US', 'OTC', FALSE, TRUE,
        'Generic OTC venue used when no specific MIC-backed venue is available.'),

    ('XIDX', 'Synthetic Index Venue', NULL, NULL, 'SYNTHETIC', TRUE, TRUE,
        'Internal Empire venue for indexes and benchmark proxies.')
ON CONFLICT (exchange_code) DO UPDATE
SET
    exchange_name  = EXCLUDED.exchange_name,
    mic            = EXCLUDED.mic,
    country_alpha2 = EXCLUDED.country_alpha2,
    exchange_type  = EXCLUDED.exchange_type,
    is_synthetic   = EXCLUDED.is_synthetic,
    is_active      = EXCLUDED.is_active,
    notes          = EXCLUDED.notes;

-- ---------------------------------------------------------------------
-- SEC / EDGAR / XBRL exchange aliases
-- ---------------------------------------------------------------------

INSERT INTO exchange_alias (
    exchange_id,
    source_code,
    raw_name,
    normalized_name,
    is_active
)
SELECT e.exchange_id, v.source_code, v.raw_name, v.normalized_name, TRUE
FROM (
    VALUES
        ('NYSE',     'SEC', 'NYSE', 'NYSE'),
        ('NYSE',     'SEC', 'New York Stock Exchange', 'NYSE'),

        ('NASDAQ',   'SEC', 'NASDAQ', 'NASDAQ'),
        ('NASDAQ',   'SEC', 'Nasdaq', 'NASDAQ'),
        ('NASDAQ',   'SEC', 'The Nasdaq Stock Market LLC', 'NASDAQ'),

        ('NYSEARCA', 'SEC', 'NYSEArca', 'NYSEARCA'),
        ('NYSEARCA', 'SEC', 'NYSE Arca', 'NYSEARCA'),
        ('NYSEARCA', 'SEC', 'NYSE ARCA', 'NYSEARCA'),

        ('NYSEAMER', 'SEC', 'NYSEAMER', 'NYSEAMER'),
        ('NYSEAMER', 'SEC', 'NYSE American', 'NYSEAMER'),
        ('NYSEAMER', 'SEC', 'NYSE MKT', 'NYSEAMER'),

        ('CBOEBZX',  'SEC', 'CboeBZX', 'CBOEBZX'),
        ('CBOEBZX',  'SEC', 'Cboe BZX', 'CBOEBZX'),
        ('CBOEBZX',  'SEC', 'BATS', 'CBOEBZX'),

        ('IEX',      'SEC', 'IEX', 'IEX'),

        ('OTC',      'SEC', 'OTC', 'OTC'),
        ('OTC',      'SEC', 'OTCQB', 'OTC'),
        ('OTC',      'SEC', 'OTCQX', 'OTC'),
        ('OTC',      'SEC', 'Pink', 'OTC'),
        ('OTC',      'SEC', 'NONE', 'OTC'),

        ('XIDX',     'INTERNAL', 'XIDX', 'XIDX')
) AS v(exchange_code, source_code, raw_name, normalized_name)
JOIN exchange e
  ON e.exchange_code = v.exchange_code
ON CONFLICT (source_code, raw_name) DO UPDATE
SET
    exchange_id      = EXCLUDED.exchange_id,
    normalized_name  = EXCLUDED.normalized_name,
    is_active        = TRUE;