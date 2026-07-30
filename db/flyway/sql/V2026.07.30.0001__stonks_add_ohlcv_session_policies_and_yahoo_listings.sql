-- =====================================================================
-- Flyway Versioned Migration
--
-- Name:
--   stonks_add_ohlcv_session_policies_and_yahoo_listings
--
-- Purpose:
--   Persist reusable OHLCV session policies and seed the bounded Yahoo
--   benchmark universe with explicit policy assignments.
--
-- Notes:
--   - All objects remain in the existing stonks schema.
--   - provider_listing.ticker stores the stable Empire symbol.
--   - provider_listing.metadata.YahooTicker stores the exact Yahoo request
--     symbol; no Yahoo-specific relational ticker column is added.
--   - Calendar names were resolved against pandas_market_calendars 5.4.0.
--   - Unsupported or publisher-defined calendars use explicit observed-only
--     LOCAL_CUTOFF policies rather than inferred weekday calendars.
-- =====================================================================

SET search_path TO stonks, public;

-- ---------------------------------------------------------------------
-- Shared session-policy schema
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ohlcv_session_policy (
    session_policy_code        VARCHAR(32) PRIMARY KEY,
    calendar_name              TEXT NULL,
    timezone_name              TEXT NOT NULL,
    eligibility_rule           VARCHAR(32) NOT NULL,
    cutoff_local_time          TIME WITHOUT TIME ZONE NULL,
    availability_delay_minutes INTEGER NOT NULL,
    session_date_rule          VARCHAR(32) NOT NULL,
    description                TEXT NOT NULL,

    CONSTRAINT ck_ohlcv_session_policy_code
        CHECK (
            session_policy_code <> ''
            AND session_policy_code = btrim(session_policy_code)
            AND session_policy_code = upper(session_policy_code)
        ),

    CONSTRAINT ck_ohlcv_session_policy_calendar
        CHECK (
            calendar_name IS NULL
            OR (
                calendar_name <> ''
                AND calendar_name = btrim(calendar_name)
            )
        ),

    CONSTRAINT ck_ohlcv_session_policy_timezone
        CHECK (
            timezone_name <> ''
            AND timezone_name = btrim(timezone_name)
        ),

    CONSTRAINT ck_ohlcv_session_policy_eligibility_rule
        CHECK (eligibility_rule IN ('SESSION_CLOSE', 'LOCAL_CUTOFF')),

    CONSTRAINT ck_ohlcv_session_policy_delay
        CHECK (
            availability_delay_minutes >= 0
            AND availability_delay_minutes <= 10080
        ),

    CONSTRAINT ck_ohlcv_session_policy_session_date_rule
        CHECK (
            session_date_rule IN (
                'CALENDAR_SESSION',
                'PROVIDER_LOCAL_DATE',
                'PROVIDER_DAILY_SETTLEMENT'
            )
        ),

    CONSTRAINT ck_ohlcv_session_policy_description
        CHECK (
            description <> ''
            AND description = btrim(description)
        ),

    CONSTRAINT ck_ohlcv_session_policy_shape
        CHECK (
            (
                eligibility_rule = 'SESSION_CLOSE'
                AND calendar_name IS NOT NULL
                AND cutoff_local_time IS NULL
                AND session_date_rule = 'CALENDAR_SESSION'
            )
            OR
            (
                eligibility_rule = 'LOCAL_CUTOFF'
                AND cutoff_local_time IS NOT NULL
                AND session_date_rule IN (
                    'PROVIDER_LOCAL_DATE',
                    'PROVIDER_DAILY_SETTLEMENT'
                )
            )
        )
);

ALTER TABLE provider_listing
    ADD COLUMN IF NOT EXISTS session_policy_code VARCHAR(32) NULL;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_provider_listing_session_policy'
          AND conrelid = 'stonks.provider_listing'::regclass
    ) THEN
        ALTER TABLE stonks.provider_listing
            ADD CONSTRAINT fk_provider_listing_session_policy
            FOREIGN KEY (session_policy_code)
            REFERENCES stonks.ohlcv_session_policy(session_policy_code);
    END IF;
END;
$migration$;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_provider_listing_yahoo_metadata'
          AND conrelid = 'stonks.provider_listing'::regclass
    ) THEN
        ALTER TABLE stonks.provider_listing
            ADD CONSTRAINT ck_provider_listing_yahoo_metadata
            CHECK (
                provider_code <> 'YAHOO'
                OR (
                    metadata IS NOT NULL
                    AND jsonb_typeof(metadata) = 'object'
                    AND jsonb_typeof(metadata -> 'YahooTicker') = 'string'
                    AND metadata ->> 'YahooTicker' <> ''
                    AND metadata ->> 'YahooTicker'
                        = btrim(metadata ->> 'YahooTicker')
                )
            );
    END IF;
END;
$migration$;

CREATE INDEX IF NOT EXISTS ix_provider_listing_session_policy
    ON provider_listing (session_policy_code)
    WHERE session_policy_code IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_provider_listing_yahoo_ticker
    ON provider_listing ((metadata ->> 'YahooTicker'))
    WHERE provider_code = 'YAHOO'
      AND metadata ? 'YahooTicker';

-- ---------------------------------------------------------------------
-- Reviewed Yahoo policy catalog
-- ---------------------------------------------------------------------

INSERT INTO ohlcv_session_policy (
    session_policy_code,
    calendar_name,
    timezone_name,
    eligibility_rule,
    cutoff_local_time,
    availability_delay_minutes,
    session_date_rule,
    description
)
VALUES
    ('YH_XNYS_CLOSE_90M', 'XNYS', 'America/New_York',
     'SESSION_CLOSE', NULL, 90, 'CALENDAR_SESSION',
     'Yahoo U.S. cash index after the NYSE session close'),
    ('YH_XNAS_CLOSE_90M', 'NASDAQ', 'America/New_York',
     'SESSION_CLOSE', NULL, 90, 'CALENDAR_SESSION',
     'Yahoo Nasdaq cash index after the Nasdaq session close'),
    ('YH_CBOE_CLOSE_120M', 'CBOE_Index_Options', 'America/Chicago',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo Cboe-published index after the index-options session close'),
    ('YH_US_PUBLISHER_120M', NULL, 'America/New_York',
     'LOCAL_CUTOFF', TIME '18:00', 120, 'PROVIDER_LOCAL_DATE',
     'Observed-only Yahoo U.S. publisher index after an evening cutoff'),
    ('YH_XLON_CLOSE_120M', 'XLON', 'Europe/London',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo U.K. cash index after the London session close'),
    ('YH_XETR_CLOSE_120M', 'XETR', 'Europe/Berlin',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo German cash index after the Xetra session close'),
    ('YH_XPAR_CLOSE_120M', 'XPAR', 'Europe/Paris',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo French cash index after the Paris session close'),
    ('YH_EU_PUBLISHER_240M', NULL, 'Europe/Berlin',
     'LOCAL_CUTOFF', TIME '18:00', 240, 'PROVIDER_LOCAL_DATE',
     'Observed-only Yahoo pan-European publisher index cutoff'),
    ('YH_XMAD_CLOSE_120M', 'XMAD', 'Europe/Madrid',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo Spanish cash index after the Madrid session close'),
    ('YH_XAMS_CLOSE_120M', 'XAMS', 'Europe/Amsterdam',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo Dutch cash index after the Amsterdam session close'),
    ('YH_XSWX_CLOSE_120M', 'XSWX', 'Europe/Zurich',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo Swiss cash index after the SIX session close'),
    ('YH_XMIL_CLOSE_120M', 'XMIL', 'Europe/Rome',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo Italian cash index after the Milan session close'),
    ('YH_XSTO_CLOSE_120M', 'XSTO', 'Europe/Stockholm',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo Swedish cash index after the Stockholm session close'),
    ('YH_XBRU_CLOSE_120M', 'XBRU', 'Europe/Brussels',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo Belgian cash index after the Brussels session close'),
    ('YH_XLIS_CLOSE_120M', 'XLIS', 'Europe/Lisbon',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo Portuguese cash index after the Lisbon session close'),
    ('YH_XDUB_CLOSE_120M', 'XDUB', 'Europe/Dublin',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo Irish cash index after the Dublin session close'),
    ('YH_XTKS_CLOSE_180M', 'XTKS', 'Asia/Tokyo',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Japanese cash index after the Tokyo session close'),
    ('YH_XHKG_CLOSE_180M', 'XHKG', 'Asia/Hong_Kong',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Hong Kong cash index after the HKEX session close'),
    ('YH_XKRX_CLOSE_180M', 'XKRX', 'Asia/Seoul',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Korean cash index after the Korea Exchange session close'),
    ('YH_XSHG_CLOSE_180M', 'XSHG', 'Asia/Shanghai',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Shanghai cash index after the SSE session close'),
    ('YH_CN_PUBLISHER_180M', NULL, 'Asia/Shanghai',
     'LOCAL_CUTOFF', TIME '16:00', 180, 'PROVIDER_LOCAL_DATE',
     'Observed-only Yahoo China index without a supported exact calendar'),
    ('YH_XTAI_CLOSE_180M', 'XTAI', 'Asia/Taipei',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Taiwan cash index after the Taiwan session close'),
    ('YH_XSES_CLOSE_180M', 'XSES', 'Asia/Singapore',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Singapore cash index after the SGX session close'),
    ('YH_XBKK_CLOSE_180M', 'XBKK', 'Asia/Bangkok',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Thai cash index after the Bangkok session close'),
    ('YH_XIDX_CLOSE_180M', 'XIDX', 'Asia/Jakarta',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Indonesian cash index after the Jakarta session close'),
    ('YH_XKLS_CLOSE_180M', 'XKLS', 'Asia/Kuala_Lumpur',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Malaysian cash index after the Bursa Malaysia session close'),
    ('YH_XPHS_CLOSE_180M', 'XPHS', 'Asia/Manila',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Philippine cash index after the Manila session close'),
    ('YH_XNSE_CLOSE_180M', 'XNSE', 'Asia/Calcutta',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Indian cash index after the NSE session close'),
    ('YH_XBOM_CLOSE_180M', 'XBOM', 'Asia/Calcutta',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Indian cash index after the BSE session close'),
    ('YH_XASX_CLOSE_180M', 'XASX', 'Australia/Sydney',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Australian cash index after the ASX session close'),
    ('YH_XTSE_CLOSE_120M', 'XTSE', 'America/Toronto',
     'SESSION_CLOSE', NULL, 120, 'CALENDAR_SESSION',
     'Yahoo Canadian cash index after the Toronto session close'),
    ('YH_BVMF_CLOSE_180M', 'BVMF', 'America/Sao_Paulo',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Brazilian cash index after the B3 session close'),
    ('YH_XMEX_CLOSE_180M', 'XMEX', 'America/Mexico_City',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Mexican cash index after the Mexico session close'),
    ('YH_XBUE_CLOSE_180M', 'XBUE', 'America/Argentina/Buenos_Aires',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Argentine cash index after the Buenos Aires session close'),
    ('YH_CL_PUBLISHER_180M', NULL, 'America/Santiago',
     'LOCAL_CUTOFF', TIME '17:00', 180, 'PROVIDER_LOCAL_DATE',
     'Observed-only Yahoo Chilean index without a usable close calendar'),
    ('YH_XJSE_CLOSE_180M', 'XJSE', 'Africa/Johannesburg',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo South African cash index after the Johannesburg session close'),
    ('YH_XIST_CLOSE_180M', 'XIST', 'Europe/Istanbul',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Turkish cash index after the Istanbul session close'),
    ('YH_XTAE_CLOSE_180M', 'XTAE', 'Asia/Tel_Aviv',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Israeli cash index after the Tel Aviv session close'),
    ('YH_XSAU_CLOSE_180M', 'XSAU', 'Asia/Riyadh',
     'SESSION_CLOSE', NULL, 180, 'CALENDAR_SESSION',
     'Yahoo Saudi cash index after the Saudi Exchange session close'),
    ('YH_MSCI_PUBLISHER_240M', NULL, 'America/New_York',
     'LOCAL_CUTOFF', TIME '20:00', 240, 'PROVIDER_LOCAL_DATE',
     'Observed-only Yahoo MSCI publisher index cutoff'),
    ('YH_DXY_CUTOFF_120M', NULL, 'America/New_York',
     'LOCAL_CUTOFF', TIME '17:00', 120, 'PROVIDER_LOCAL_DATE',
     'Observed-only Yahoo DXY provider-day cutoff'),
    ('YH_CME_EQUITY_2200', 'CME_Equity', 'America/New_York',
     'LOCAL_CUTOFF', TIME '22:00', 0, 'PROVIDER_DAILY_SETTLEMENT',
     'Yahoo CME equity continuous future after provider daily rollover'),
    ('YH_CME_ENERGY_2200', 'CMEGlobex_EnergyAndMetals',
     'America/New_York', 'LOCAL_CUTOFF', TIME '22:00', 0,
     'PROVIDER_DAILY_SETTLEMENT',
     'Yahoo CME energy continuous future after provider daily rollover'),
    ('YH_BRENT_OBSERVED_2200', NULL, 'America/New_York',
     'LOCAL_CUTOFF', TIME '22:00', 0, 'PROVIDER_DAILY_SETTLEMENT',
     'Observed-only Yahoo Brent continuous future daily rollover'),
    ('YH_CME_METALS_2200', 'CMEGlobex_EnergyAndMetals',
     'America/New_York', 'LOCAL_CUTOFF', TIME '22:00', 0,
     'PROVIDER_DAILY_SETTLEMENT',
     'Yahoo CME metals continuous future after provider daily rollover'),
    ('YH_CME_GRAINS_2200', 'CMEGlobex_Grains', 'America/New_York',
     'LOCAL_CUTOFF', TIME '22:00', 0, 'PROVIDER_DAILY_SETTLEMENT',
     'Yahoo CME grain continuous future after provider daily rollover'),
    ('YH_CME_OILSEEDS_2200', 'CMEGlobex_Oilseeds', 'America/New_York',
     'LOCAL_CUTOFF', TIME '22:00', 0, 'PROVIDER_DAILY_SETTLEMENT',
     'Yahoo CME oilseed continuous future after provider daily rollover'),
    ('YH_ICE_SOFTS_2200', 'ICEUS', 'America/New_York',
     'LOCAL_CUTOFF', TIME '22:00', 0, 'PROVIDER_DAILY_SETTLEMENT',
     'Yahoo ICE U.S. soft-commodity future after provider daily rollover'),
    ('YH_CME_LIVESTOCK_2200', 'CMEGlobex_Live_Cattle',
     'America/New_York', 'LOCAL_CUTOFF', TIME '22:00', 0,
     'PROVIDER_DAILY_SETTLEMENT',
     'Yahoo CME livestock continuous future after provider daily rollover')
ON CONFLICT (session_policy_code) DO UPDATE
SET
    calendar_name              = EXCLUDED.calendar_name,
    timezone_name              = EXCLUDED.timezone_name,
    eligibility_rule           = EXCLUDED.eligibility_rule,
    cutoff_local_time          = EXCLUDED.cutoff_local_time,
    availability_delay_minutes = EXCLUDED.availability_delay_minutes,
    session_date_rule          = EXCLUDED.session_date_rule,
    description                = EXCLUDED.description;

-- ---------------------------------------------------------------------
-- Controlled Yahoo provider-listing universe
-- ---------------------------------------------------------------------

WITH yahoo_listing (
    empire_ticker,
    yahoo_ticker,
    listing_name,
    instrument_type_code,
    session_policy_code
) AS (
    VALUES
        ('SPX', '^GSPC', 'S&P 500 Index', 'EQUITY_INDEX',
         'YH_XNYS_CLOSE_90M'),
        ('DJI', '^DJI', 'Dow Jones Industrial Average', 'EQUITY_INDEX',
         'YH_XNYS_CLOSE_90M'),
        ('DJT', '^DJT', 'Dow Jones Transportation Average', 'EQUITY_INDEX',
         'YH_XNYS_CLOSE_90M'),
        ('DJU', '^DJU', 'Dow Jones Utility Average', 'EQUITY_INDEX',
         'YH_XNYS_CLOSE_90M'),
        ('NDX', '^NDX', 'Nasdaq-100 Index', 'EQUITY_INDEX',
         'YH_XNAS_CLOSE_90M'),
        ('IXIC', '^IXIC', 'Nasdaq Composite Index', 'EQUITY_INDEX',
         'YH_XNAS_CLOSE_90M'),
        ('NYA', '^NYA', 'NYSE Composite Index', 'EQUITY_INDEX',
         'YH_XNYS_CLOSE_90M'),
        ('RUT', '^RUT', 'Russell 2000 Index', 'EQUITY_INDEX',
         'YH_XNYS_CLOSE_90M'),
        ('RUA', '^RUA', 'Russell 3000 Index', 'EQUITY_INDEX',
         'YH_XNYS_CLOSE_90M'),
        ('W5000', '^W5000', 'Wilshire 5000 Total Market Index',
         'EQUITY_INDEX', 'YH_XNYS_CLOSE_90M'),
        ('OEX', '^OEX', 'S&P 100 Index', 'EQUITY_INDEX',
         'YH_XNYS_CLOSE_90M'),
        ('SP400', '^SP400', 'S&P MidCap 400 Index', 'EQUITY_INDEX',
         'YH_XNYS_CLOSE_90M'),
        ('SP600', '^SP600', 'S&P SmallCap 600 Index', 'EQUITY_INDEX',
         'YH_XNYS_CLOSE_90M'),
        ('SOX', '^SOX', 'PHLX Semiconductor Index', 'EQUITY_INDEX',
         'YH_XNAS_CLOSE_90M'),
        ('NYFANG', '^NYFANG', 'NYSE FANG+ Index', 'EQUITY_INDEX',
         'YH_XNYS_CLOSE_90M'),
        ('VIX', '^VIX', 'CBOE Volatility Index', 'VOLATILITY_INDEX',
         'YH_CBOE_CLOSE_120M'),
        ('VXN', '^VXN', 'CBOE Nasdaq-100 Volatility Index',
         'VOLATILITY_INDEX', 'YH_CBOE_CLOSE_120M'),
        ('RVX', '^RVX', 'CBOE Russell 2000 Volatility Index',
         'VOLATILITY_INDEX', 'YH_CBOE_CLOSE_120M'),
        ('VVIX', '^VVIX', 'CBOE VIX Volatility Index',
         'VOLATILITY_INDEX', 'YH_CBOE_CLOSE_120M'),
        ('SKEW', '^SKEW', 'CBOE SKEW Index', 'VOLATILITY_INDEX',
         'YH_CBOE_CLOSE_120M'),
        ('MOVE', '^MOVE', 'ICE BofA MOVE Bond Volatility Index',
         'VOLATILITY_INDEX', 'YH_US_PUBLISHER_120M'),
        ('UST5Y', '^FVX', 'U.S. Treasury 5-Year Yield Index',
         'YIELD_INDEX', 'YH_US_PUBLISHER_120M'),
        ('UST10Y', '^TNX', 'U.S. Treasury 10-Year Yield Index',
         'YIELD_INDEX', 'YH_US_PUBLISHER_120M'),
        ('UST30Y', '^TYX', 'U.S. Treasury 30-Year Yield Index',
         'YIELD_INDEX', 'YH_US_PUBLISHER_120M'),
        ('FTSE', '^FTSE', 'FTSE 100 Index', 'EQUITY_INDEX',
         'YH_XLON_CLOSE_120M'),
        ('DAX', '^GDAXI', 'DAX 40 Index', 'EQUITY_INDEX',
         'YH_XETR_CLOSE_120M'),
        ('CAC', '^FCHI', 'CAC 40 Index', 'EQUITY_INDEX',
         'YH_XPAR_CLOSE_120M'),
        ('STOXX50E', '^STOXX50E', 'EURO STOXX 50 Index', 'EQUITY_INDEX',
         'YH_EU_PUBLISHER_240M'),
        ('STOXX600', '^STOXX', 'STOXX Europe 600 Index', 'EQUITY_INDEX',
         'YH_EU_PUBLISHER_240M'),
        ('IBEX', '^IBEX', 'IBEX 35 Index', 'EQUITY_INDEX',
         'YH_XMAD_CLOSE_120M'),
        ('AEX', '^AEX', 'AEX Netherlands Index', 'EQUITY_INDEX',
         'YH_XAMS_CLOSE_120M'),
        ('SMI', '^SSMI', 'Swiss Market Index', 'EQUITY_INDEX',
         'YH_XSWX_CLOSE_120M'),
        ('FTSEMIB', 'FTSEMIB.MI', 'FTSE MIB Index', 'EQUITY_INDEX',
         'YH_XMIL_CLOSE_120M'),
        ('OMXSTO30', '^OMX', 'OMX Stockholm 30 Index', 'EQUITY_INDEX',
         'YH_XSTO_CLOSE_120M'),
        ('BEL20', '^BFX', 'BEL 20 Index', 'EQUITY_INDEX',
         'YH_XBRU_CLOSE_120M'),
        ('PSI20', 'PSI20.LS', 'PSI 20 Index', 'EQUITY_INDEX',
         'YH_XLIS_CLOSE_120M'),
        ('ISEQ', '^ISEQ', 'ISEQ Overall Index', 'EQUITY_INDEX',
         'YH_XDUB_CLOSE_120M'),
        ('N225', '^N225', 'Nikkei 225 Index', 'EQUITY_INDEX',
         'YH_XTKS_CLOSE_180M'),
        ('HSI', '^HSI', 'Hang Seng Index', 'EQUITY_INDEX',
         'YH_XHKG_CLOSE_180M'),
        ('HSCEI', '^HSCE', 'Hang Seng China Enterprises Index',
         'EQUITY_INDEX', 'YH_XHKG_CLOSE_180M'),
        ('KOSPI', '^KS11', 'KOSPI Composite Index', 'EQUITY_INDEX',
         'YH_XKRX_CLOSE_180M'),
        ('SHCOMP', '000001.SS', 'Shanghai Composite Index',
         'EQUITY_INDEX', 'YH_XSHG_CLOSE_180M'),
        ('CSI300', '000300.SS', 'CSI 300 Index', 'EQUITY_INDEX',
         'YH_XSHG_CLOSE_180M'),
        ('SZCOMPONENT', '399001.SZ', 'Shenzhen Component Index',
         'EQUITY_INDEX', 'YH_CN_PUBLISHER_180M'),
        ('TWSE', '^TWII', 'Taiwan Weighted Index', 'EQUITY_INDEX',
         'YH_XTAI_CLOSE_180M'),
        ('STI', '^STI', 'Straits Times Index', 'EQUITY_INDEX',
         'YH_XSES_CLOSE_180M'),
        ('SET', '^SET', 'Stock Exchange of Thailand SET Index',
         'EQUITY_INDEX', 'YH_XBKK_CLOSE_180M'),
        ('JCI', '^JKSE', 'Jakarta Composite Index', 'EQUITY_INDEX',
         'YH_XIDX_CLOSE_180M'),
        ('KLCI', '^KLSE', 'FTSE Bursa Malaysia KLCI Index',
         'EQUITY_INDEX', 'YH_XKLS_CLOSE_180M'),
        ('PSEI', 'PSEI.PS', 'Philippine Stock Exchange PSEi Index',
         'EQUITY_INDEX', 'YH_XPHS_CLOSE_180M'),
        ('NIFTY50', '^NSEI', 'Nifty 50 Index', 'EQUITY_INDEX',
         'YH_XNSE_CLOSE_180M'),
        ('SENSEX', '^BSESN', 'BSE Sensex Index', 'EQUITY_INDEX',
         'YH_XBOM_CLOSE_180M'),
        ('ASX200', '^AXJO', 'S&P/ASX 200 Index', 'EQUITY_INDEX',
         'YH_XASX_CLOSE_180M'),
        ('TSXCOMP', '^GSPTSE', 'S&P/TSX Composite Index',
         'EQUITY_INDEX', 'YH_XTSE_CLOSE_120M'),
        ('BOVESPA', '^BVSP', 'Bovespa Index', 'EQUITY_INDEX',
         'YH_BVMF_CLOSE_180M'),
        ('MEXIPC', '^MXX', 'S&P/BMV IPC Index', 'EQUITY_INDEX',
         'YH_XMEX_CLOSE_180M'),
        ('MERVAL', '^MERV', 'S&P MERVAL Index', 'EQUITY_INDEX',
         'YH_XBUE_CLOSE_180M'),
        ('IPSA', '^IPSA', 'S&P IPSA Index', 'EQUITY_INDEX',
         'YH_CL_PUBLISHER_180M'),
        ('JTOPI', '^JA0R.JO', 'FTSE/JSE Top 40 Index', 'EQUITY_INDEX',
         'YH_XJSE_CLOSE_180M'),
        ('XU100', 'XU100.IS', 'BIST 100 Index', 'EQUITY_INDEX',
         'YH_XIST_CLOSE_180M'),
        ('TA125', '^TA125.TA', 'TA-125 Index', 'EQUITY_INDEX',
         'YH_XTAE_CLOSE_180M'),
        ('TASI', '^TASI.SR', 'Tadawul All Share Index', 'EQUITY_INDEX',
         'YH_XSAU_CLOSE_180M'),
        ('MSCIWORLD', '^990100-USD-STRD', 'MSCI World Index',
         'EQUITY_INDEX', 'YH_MSCI_PUBLISHER_240M'),
        ('MSCIEM', '^891800-USD-STRD', 'MSCI Emerging Markets Index',
         'EQUITY_INDEX', 'YH_MSCI_PUBLISHER_240M'),
        ('MSCIACWI', '^892400-USD-STRD', 'MSCI All Country World Index',
         'EQUITY_INDEX', 'YH_MSCI_PUBLISHER_240M'),
        ('GSCI', '^SPGSCI', 'S&P GSCI Commodity Index',
         'COMMODITY_INDEX', 'YH_US_PUBLISHER_120M'),
        ('BCOM', '^BCOM', 'Bloomberg Commodity Index',
         'COMMODITY_INDEX', 'YH_US_PUBLISHER_120M'),
        ('DXY', 'DX-Y.NYB', 'ICE U.S. Dollar Index', 'CURRENCY_INDEX',
         'YH_DXY_CUTOFF_120M'),
        ('ES', 'ES=F', 'E-mini S&P 500 Futures',
         'CONTINUOUS_FUTURE_EQUITY', 'YH_CME_EQUITY_2200'),
        ('NQ', 'NQ=F', 'E-mini Nasdaq-100 Futures',
         'CONTINUOUS_FUTURE_EQUITY', 'YH_CME_EQUITY_2200'),
        ('YM', 'YM=F', 'E-mini Dow Jones Industrial Average Futures',
         'CONTINUOUS_FUTURE_EQUITY', 'YH_CME_EQUITY_2200'),
        ('RTY', 'RTY=F', 'E-mini Russell 2000 Futures',
         'CONTINUOUS_FUTURE_EQUITY', 'YH_CME_EQUITY_2200'),
        ('WTI', 'CL=F', 'WTI Crude Oil Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_ENERGY_2200'),
        ('BRENT', 'BZ=F', 'Brent Crude Oil Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_BRENT_OBSERVED_2200'),
        ('NATGAS', 'NG=F', 'Henry Hub Natural Gas Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_ENERGY_2200'),
        ('HEATOIL', 'HO=F', 'New York Harbor ULSD Heating Oil Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_ENERGY_2200'),
        ('RBOB', 'RB=F', 'RBOB Gasoline Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_ENERGY_2200'),
        ('GOLD', 'GC=F', 'Gold Futures', 'CONTINUOUS_FUTURE_COMMODITY',
         'YH_CME_METALS_2200'),
        ('SILVER', 'SI=F', 'Silver Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_METALS_2200'),
        ('COPPER', 'HG=F', 'Copper Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_METALS_2200'),
        ('PLATINUM', 'PL=F', 'Platinum Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_METALS_2200'),
        ('PALLADIUM', 'PA=F', 'Palladium Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_METALS_2200'),
        ('CORN', 'ZC=F', 'Corn Futures', 'CONTINUOUS_FUTURE_COMMODITY',
         'YH_CME_GRAINS_2200'),
        ('WHEAT', 'ZW=F', 'Chicago SRW Wheat Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_GRAINS_2200'),
        ('SOYBEANS', 'ZS=F', 'Soybean Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_OILSEEDS_2200'),
        ('SOYMEAL', 'ZM=F', 'Soybean Meal Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_OILSEEDS_2200'),
        ('SOYOIL', 'ZL=F', 'Soybean Oil Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_OILSEEDS_2200'),
        ('COFFEE', 'KC=F', 'Coffee C Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_ICE_SOFTS_2200'),
        ('SUGAR', 'SB=F', 'Sugar No. 11 Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_ICE_SOFTS_2200'),
        ('COCOA', 'CC=F', 'Cocoa Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_ICE_SOFTS_2200'),
        ('COTTON', 'CT=F', 'Cotton No. 2 Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_ICE_SOFTS_2200'),
        ('LIVECATTLE', 'LE=F', 'Live Cattle Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_LIVESTOCK_2200'),
        ('LEANHOGS', 'HE=F', 'Lean Hogs Futures',
         'CONTINUOUS_FUTURE_COMMODITY', 'YH_CME_LIVESTOCK_2200')
)
INSERT INTO provider_listing (
    provider_code,
    market,
    ticker,
    name,
    instrument_type_code,
    status,
    metadata,
    session_policy_code
)
SELECT
    'YAHOO',
    'XIDX',
    empire_ticker,
    listing_name,
    instrument_type_code,
    'ACTIVE',
    jsonb_build_object('YahooTicker', yahoo_ticker),
    session_policy_code
FROM yahoo_listing
ON CONFLICT (provider_code, market, ticker) DO UPDATE
SET
    name                 = EXCLUDED.name,
    instrument_type_code = EXCLUDED.instrument_type_code,
    status               = 'ACTIVE',
    metadata             = coalesce(provider_listing.metadata, '{}'::jsonb)
                           || EXCLUDED.metadata,
    session_policy_code  = EXCLUDED.session_policy_code,
    updated_at           = now();

-- ---------------------------------------------------------------------
-- Migration assertions
-- ---------------------------------------------------------------------

DO $migration$
DECLARE
    yahoo_listing_count INTEGER;
BEGIN
    SELECT count(*)
    INTO yahoo_listing_count
    FROM stonks.provider_listing
    WHERE provider_code = 'YAHOO'
      AND market = 'XIDX'
      AND status = 'ACTIVE';

    IF yahoo_listing_count <> 93 THEN
        RAISE EXCEPTION
            'expected 93 active Yahoo XIDX listings, found %',
            yahoo_listing_count;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND (
              ticker <> upper(ticker)
              OR ticker !~ '^[A-Z0-9]+$'
          )
    ) THEN
        RAISE EXCEPTION
            'Yahoo provider listings must use stable Empire ticker codes';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND (
              session_policy_code IS NULL
              OR metadata ->> 'YahooTicker' IS NULL
          )
    ) THEN
        RAISE EXCEPTION
            'every Yahoo provider listing requires a policy and YahooTicker';
    END IF;

    IF (
        SELECT count(DISTINCT metadata ->> 'YahooTicker')
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
    ) <> 93 THEN
        RAISE EXCEPTION 'YahooTicker values must be unique across the seed';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM stonks.provider_listing
        WHERE provider_code = 'YAHOO'
          AND market = 'XIDX'
          AND instrument_type_code NOT IN (
              'YIELD_INDEX',
              'EQUITY_INDEX',
              'COMMODITY_INDEX',
              'CURRENCY_INDEX',
              'VOLATILITY_INDEX',
              'CONTINUOUS_FUTURE_COMMODITY',
              'CONTINUOUS_FUTURE_EQUITY'
          )
    ) THEN
        RAISE EXCEPTION
            'Yahoo seed contains an unsupported or ordinary-equity type';
    END IF;
END;
$migration$;
