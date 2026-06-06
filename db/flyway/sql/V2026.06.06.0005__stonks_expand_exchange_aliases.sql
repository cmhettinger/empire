-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_expand_exchange_aliases
--
-- Purpose:
--   Add SEC / EDGAR exchange aliases for historically common market names.
--
-- Notes:
--   - This migration adds aliases only; it does not create new exchanges.
--   - Aliases target existing canonical exchanges used by Empire.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- SEC / EDGAR historical exchange aliases
-- ---------------------------------------------------------------------

INSERT INTO exchange_alias (
    exchange_id,
    provider_code,
    raw_name,
    normalized_name,
    is_active
)
SELECT e.exchange_id, v.provider_code, v.raw_name, v.normalized_name, TRUE
FROM (
    VALUES
        ('NASDAQ',   'SEC', 'NASDAQ National Market', 'NASDAQ'),
        ('NASDAQ',   'SEC', 'Nasdaq National Market', 'NASDAQ'),
        ('NASDAQ',   'SEC', 'NASDAQ NMS', 'NASDAQ'),
        ('NASDAQ',   'SEC', 'Nasdaq NMS', 'NASDAQ'),
        ('NASDAQ',   'SEC', 'NASDAQ Global Market', 'NASDAQ'),
        ('NASDAQ',   'SEC', 'Nasdaq Global Market', 'NASDAQ'),
        ('NASDAQ',   'SEC', 'NASDAQ Global Select Market', 'NASDAQ'),
        ('NASDAQ',   'SEC', 'Nasdaq Global Select Market', 'NASDAQ'),
        ('NASDAQ',   'SEC', 'NASDAQ Capital Market', 'NASDAQ'),
        ('NASDAQ',   'SEC', 'Nasdaq Capital Market', 'NASDAQ'),

        ('NYSEAMER', 'SEC', 'American Stock Exchange', 'NYSEAMER'),
        ('NYSEAMER', 'SEC', 'AMEX', 'NYSEAMER'),
        ('NYSEAMER', 'SEC', 'NYSE Amex', 'NYSEAMER'),
        ('NYSEAMER', 'SEC', 'NYSE AMEX', 'NYSEAMER'),
        ('NYSEAMER', 'SEC', 'NYSE MKT LLC', 'NYSEAMER'),

        ('OTC',      'SEC', 'OTCBB', 'OTC'),
        ('OTC',      'SEC', 'OTC Bulletin Board', 'OTC'),
        ('OTC',      'SEC', 'OTCBB Market', 'OTC'),
        ('OTC',      'SEC', 'Pink Sheets', 'OTC'),
        ('OTC',      'SEC', 'Pink Open Market', 'OTC')
) AS v(exchange_code, provider_code, raw_name, normalized_name)
JOIN exchange e
  ON e.exchange_code = v.exchange_code
ON CONFLICT (provider_code, raw_name) DO NOTHING;
