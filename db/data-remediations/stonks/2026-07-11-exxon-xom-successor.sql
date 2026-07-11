-- =====================================================================
-- Data remediation: XOM redomiciliation successor listing
--
-- Scope: Existing Empire databases that ingested both sides of the July 2026
-- ExxonMobil redomiciliation before successor handling existed.
--
-- Evidence:
-- https://www.sec.gov/Archives/edgar/data/2115436/000119312526291990/d71068d8k12b.htm
-- The SEC filing states that ExxonMobil Holdings Corporation (CIK 0002115436)
-- became the successor registrant on 2026-07-01, and its common stock began
-- NYSE trading as XOM on 2026-07-02. The predecessor, Exxon Mobil Corporation
-- (CIK 0000034088), remains a real subsidiary and must not be merged away.
--
-- This script is deliberately outside db/flyway/sql. Run it only through
-- bin/run-data-remediation against an affected existing database.
-- Apply Flyway migration V2026.07.11.0001 before running this script.
-- =====================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $$
<<remediation>>
DECLARE
    predecessor_listing_id UUID;
    successor_listing_id UUID;
    predecessor_security_id UUID;
    successor_security_id UUID;
    predecessor_issuer_id UUID;
    successor_issuer_id UUID;
    predecessor_symbol_count INTEGER;
    successor_symbol_count INTEGER;
    predecessor_listing_count INTEGER;
    successor_listing_count INTEGER;
    already_remediated BOOLEAN := FALSE;
BEGIN
    SELECT COUNT(*) INTO predecessor_listing_count
      FROM stonks.listing l
      JOIN stonks.security s ON s.security_id = l.security_id
      JOIN stonks.issuer i ON i.issuer_id = s.issuer_id
      JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
     WHERE i.cik = '0000034088'
       AND e.exchange_code = 'NYSE'
       AND l.ticker_norm = 'XOM';

    SELECT COUNT(*) INTO successor_listing_count
      FROM stonks.listing l
      JOIN stonks.security s ON s.security_id = l.security_id
      JOIN stonks.issuer i ON i.issuer_id = s.issuer_id
      JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
     WHERE i.cik = '0002115436'
       AND e.exchange_code = 'NYSE'
       AND l.ticker_norm = 'XOM';

    IF predecessor_listing_count <> 1 OR successor_listing_count <> 1 THEN
        RAISE EXCEPTION
            'Expected exactly one NYSE/XOM listing for each Exxon CIK; predecessor count=% successor count=%',
            predecessor_listing_count, successor_listing_count;
    END IF;

    SELECT l.listing_id, l.security_id, s.issuer_id
      INTO predecessor_listing_id, predecessor_security_id, predecessor_issuer_id
      FROM stonks.listing l
      JOIN stonks.security s ON s.security_id = l.security_id
      JOIN stonks.issuer i ON i.issuer_id = s.issuer_id
      JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
     WHERE i.cik = '0000034088'
       AND e.exchange_code = 'NYSE'
       AND l.ticker_norm = 'XOM';

    SELECT l.listing_id, l.security_id, s.issuer_id
      INTO successor_listing_id, successor_security_id, successor_issuer_id
      FROM stonks.listing l
      JOIN stonks.security s ON s.security_id = l.security_id
      JOIN stonks.issuer i ON i.issuer_id = s.issuer_id
      JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
     WHERE i.cik = '0002115436'
       AND e.exchange_code = 'NYSE'
       AND l.ticker_norm = 'XOM';

    SELECT COUNT(*) INTO predecessor_symbol_count
      FROM stonks.listing_symbol_history
     WHERE listing_id = predecessor_listing_id
       AND ticker_norm = 'XOM'
       AND valid_to IS NULL;
    SELECT COUNT(*) INTO successor_symbol_count
      FROM stonks.listing_symbol_history
     WHERE listing_id = successor_listing_id
       AND ticker_norm = 'XOM'
       AND valid_to IS NULL;

    INSERT INTO stonks.security_successor_relationship (
        predecessor_issuer_id,
        successor_issuer_id,
        predecessor_security_id,
        successor_security_id,
        predecessor_listing_id,
        successor_listing_id,
        relationship_type,
        effective_date,
        exchange_ratio,
        source_url,
        details_json
    )
    SELECT
        remediation.predecessor_issuer_id,
        remediation.successor_issuer_id,
        remediation.predecessor_security_id,
        remediation.successor_security_id,
        remediation.predecessor_listing_id,
        remediation.successor_listing_id,
        'REDOMICILIATION_SUCCESSOR',
        DATE '2026-07-01',
        1,
        'https://www.sec.gov/Archives/edgar/data/2115436/000119312526291990/d71068d8k12b.htm',
        jsonb_build_object(
            'exchange_ratio', '1:1',
            'predecessor_cik', '0000034088',
            'successor_cik', '0002115436'
        )
    WHERE NOT EXISTS (
        SELECT 1
        FROM stonks.security_successor_relationship relationship
        WHERE relationship.predecessor_listing_id = remediation.predecessor_listing_id
          AND relationship.successor_listing_id = remediation.successor_listing_id
          AND relationship.relationship_type = 'REDOMICILIATION_SUCCESSOR'
          AND relationship.effective_date = DATE '2026-07-01'
    );

    SELECT l.status = 'MERGED'
           AND l.valid_to = DATE '2026-07-01'
           AND successor_l.status = 'ACTIVE'
           AND successor_l.valid_from = DATE '2026-07-02'
      INTO already_remediated
      FROM stonks.listing l
      JOIN stonks.listing successor_l ON successor_l.listing_id = successor_listing_id
     WHERE l.listing_id = predecessor_listing_id;

    IF already_remediated THEN
        RAISE NOTICE 'XOM successor remediation is already applied.';
        RETURN;
    END IF;

    IF predecessor_symbol_count <> 1 OR successor_symbol_count <> 1 THEN
        RAISE EXCEPTION
            'Expected exactly one open XOM symbol history per listing; predecessor=% successor=%',
            predecessor_symbol_count, successor_symbol_count;
    END IF;

    UPDATE stonks.listing
       SET status = 'MERGED', valid_to = DATE '2026-07-01', updated_at = now()
     WHERE listing_id = predecessor_listing_id
       AND status = 'ACTIVE'
       AND valid_to IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Predecessor listing was not an open ACTIVE listing.';
    END IF;

    UPDATE stonks.listing_symbol_history
       SET valid_to = DATE '2026-07-01'
     WHERE listing_id = predecessor_listing_id
       AND ticker_norm = 'XOM'
       AND valid_to IS NULL;

    UPDATE stonks.security
       SET status = 'INACTIVE', updated_at = now()
     WHERE security_id = predecessor_security_id
       AND status = 'ACTIVE';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Predecessor security was not ACTIVE.';
    END IF;

    UPDATE stonks.listing
       SET valid_from = DATE '2026-07-02', updated_at = now()
     WHERE listing_id = successor_listing_id
       AND status = 'ACTIVE'
       AND valid_to IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Successor listing is not an open ACTIVE listing.';
    END IF;

    UPDATE stonks.listing_symbol_history
       SET valid_from = DATE '2026-07-02'
     WHERE listing_id = successor_listing_id
       AND ticker_norm = 'XOM'
       AND valid_to IS NULL;

    INSERT INTO stonks.security_event (
        issuer_id, security_id, listing_id, event_type, event_date, provider_code,
        confidence_code, description, details_json
    )
    SELECT predecessor_issuer_id, predecessor_security_id, predecessor_listing_id,
           'MERGER', DATE '2026-07-01', 'SEC_COMPANY_TICKERS_EXCHANGE', 'HIGH',
           'Redomiciliation successor: ExxonMobil Holdings Corporation replaced Exxon Mobil Corporation as the public parent.',
           jsonb_build_object(
               'relationship_type', 'REDOMICILIATION_SUCCESSOR',
               'successor_issuer_id', successor_issuer_id,
               'successor_security_id', successor_security_id,
               'successor_listing_id', successor_listing_id,
               'exchange_ratio', '1:1',
               'source_url', 'https://www.sec.gov/Archives/edgar/data/2115436/000119312526291990/d71068d8k12b.htm'
           )
     WHERE NOT EXISTS (
         SELECT 1 FROM stonks.security_event
          WHERE listing_id = predecessor_listing_id
            AND event_type = 'MERGER'
            AND event_date = DATE '2026-07-01'
     );

    INSERT INTO stonks.security_event (
        issuer_id, security_id, listing_id, event_type, event_date, provider_code,
        confidence_code, description, details_json
    )
    SELECT predecessor_issuer_id, predecessor_security_id, predecessor_listing_id,
           'LISTING_ENDED', DATE '2026-07-01', 'SEC_COMPANY_TICKERS_EXCHANGE', 'HIGH',
           'NYSE XOM listing ended when the predecessor public common stock was exchanged.',
           jsonb_build_object('successor_listing_id', successor_listing_id)
     WHERE NOT EXISTS (
         SELECT 1 FROM stonks.security_event
          WHERE listing_id = predecessor_listing_id
            AND event_type = 'LISTING_ENDED'
            AND event_date = DATE '2026-07-01'
     );

    INSERT INTO stonks.security_event (
        issuer_id, security_id, listing_id, event_type, event_date, provider_code,
        confidence_code, description, details_json
    )
    SELECT successor_issuer_id, successor_security_id, successor_listing_id,
           'LISTING_STARTED', DATE '2026-07-02', 'SEC_COMPANY_TICKERS_EXCHANGE', 'HIGH',
           'ExxonMobil Holdings Corporation began NYSE trading as XOM as successor registrant.',
           jsonb_build_object('predecessor_listing_id', predecessor_listing_id)
     WHERE NOT EXISTS (
         SELECT 1 FROM stonks.security_event
          WHERE listing_id = successor_listing_id
            AND event_type = 'LISTING_STARTED'
            AND event_date = DATE '2026-07-02'
     );
END $$;

COMMIT;

-- Post-application verification: this must return only the successor listing.
SELECT i.cik, i.current_name, e.exchange_code, l.current_ticker, l.status,
       l.valid_from, l.valid_to, s.status AS security_status
  FROM stonks.listing l
  JOIN stonks.security s ON s.security_id = l.security_id
  JOIN stonks.issuer i ON i.issuer_id = s.issuer_id
  JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
 WHERE e.exchange_code = 'NYSE'
   AND l.ticker_norm = 'XOM'
   AND l.status = 'ACTIVE'
   AND l.valid_to IS NULL;
