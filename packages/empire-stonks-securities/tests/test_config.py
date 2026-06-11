from __future__ import annotations

import pytest

from empire_stonks_securities.config import StonksSecuritiesConfig
from empire_stonks_securities.exceptions import StonksSecuritiesConfigError


CONFIG = {
    "stonks_securities": {
        "name": "stonks_securities",
        "version": 1,
        "sec": {
            "user_agent": "Empire Stonks Securities/0.1 (test@example.com)",
            "base_url": "https://www.sec.gov",
            "archives_url": "https://www.sec.gov/Archives",
        },
        "timeout_seconds": 60,
        "max_retries": 5,
        "retry_backoff_seconds": 5,
        "respect_rate_limits": True,
        "rate_limit": {
            "requests_per_second": 5,
            "burst_size": 10,
            "throttle_on_429": True,
            "retry_after_header": True,
        },
        "storage": {
            "store_raw_files": True,
            "delete_processed_files_after_processing": True,
            "retention_days_raw": 5,
            "retention_days_processed": 5,
        },
        "download": {
            "checksum_validation": True,
            "resume_partial_downloads": True,
            "overwrite_existing": False,
            "quarterly_master_index": {
                "start_year": 1995,
                "end_year": None,
                "quarters": [1, 2, 3, 4],
            },
        },
        "providers": {
            "sec_company_tickers": {
                "provider_code": "SEC_COMPANY_TICKERS",
                "enabled": True,
                "url": "https://www.sec.gov/files/company_tickers.json",
                "expected_format": "json",
                "description": "SEC company-to-ticker mapping with CIK identifiers.",
            },
            "sec_quarterly_master_index": {
                "provider_code": "SEC_MASTER_INDEX",
                "enabled": True,
                "url_template": "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx",
                "expected_format": "idx",
                "description": "Historical EDGAR filing index.",
            },
        },
        "processing": {
            "historical_backfill": {
                "start_date": "1995-01-01",
                "end_date": "current",
            },
            "daily_refresh": {"enabled": True},
            "validation": {
                "verify_content_type": True,
                "verify_non_empty_file": True,
            },
        },
    }
}


def test_config_from_mapping():
    config = StonksSecuritiesConfig.from_mapping(CONFIG)

    assert config.name == "stonks_securities"
    assert config.version == 1
    assert config.sec.user_agent == "Empire Stonks Securities/0.1 (test@example.com)"
    assert config.timeout_seconds == 60
    assert config.rate_limit.requests_per_second == 5
    assert config.storage.store_raw_files is True
    assert config.download.checksum_validation is True
    assert config.download.overwrite_existing is False
    assert len(config.providers) == 2
    assert len(config.enabled_providers) == 2
    assert config.providers[0].provider_code == "SEC_COMPANY_TICKERS"
    assert config.providers[1].url_template is not None
    assert config.download.quarterly_master_index.start_year == 1995
    assert config.download.quarterly_master_index.quarters == (1, 2, 3, 4)
    assert config.processing.historical_backfill.start_date == "1995-01-01"
    assert config.processing.daily_refresh.enabled is True
    assert config.processing.validation.verify_non_empty_file is True


def test_seed_config_file_parses():
    config = StonksSecuritiesConfig.from_file(
        "object-store/config/stonks-securities/config.yml"
    )

    assert config.name == "stonks_securities"
    assert [provider.provider_code for provider in config.providers] == [
        "SEC_COMPANY_TICKERS_EXCHANGE",
        "SEC_COMPANY_TICKERS",
        "SEC_SUBMISSIONS_ZIP",
        "SEC_MASTER_INDEX_QUARTERLY",
        "SEC_MASTER_INDEX_DAILY",
        "SEC_FILING_HEADER",
    ]
    assert config.rate_limit.burst_size == 5
    assert config.download.resume_partial_downloads is True
    assert config.download.quarterly_master_index.end_year is None
    assert config.providers[3].url_template.endswith("/master.zip")
    assert config.processing.historical_backfill.end_date is None


def test_historical_backfill_end_date_can_be_null():
    config_data = {"stonks_securities": dict(CONFIG["stonks_securities"])}
    processing = dict(CONFIG["stonks_securities"]["processing"])
    historical_backfill = dict(processing["historical_backfill"])
    historical_backfill["end_date"] = None
    processing["historical_backfill"] = historical_backfill
    config_data["stonks_securities"]["processing"] = processing

    config = StonksSecuritiesConfig.from_mapping(config_data)

    assert config.processing.historical_backfill.end_date is None


def test_download_config_defaults_when_omitted():
    config_data = {"stonks_securities": dict(CONFIG["stonks_securities"])}
    del config_data["stonks_securities"]["download"]

    config = StonksSecuritiesConfig.from_mapping(config_data)

    assert config.download.checksum_validation is True
    assert config.download.resume_partial_downloads is True
    assert config.download.overwrite_existing is False


def test_provider_code_is_required():
    config_data = {"stonks_securities": dict(CONFIG["stonks_securities"])}
    providers = dict(CONFIG["stonks_securities"]["providers"])
    providers["sec_company_tickers"] = dict(providers["sec_company_tickers"])
    del providers["sec_company_tickers"]["provider_code"]
    config_data["stonks_securities"]["providers"] = providers

    with pytest.raises(StonksSecuritiesConfigError, match="provider_code"):
        StonksSecuritiesConfig.from_mapping(config_data)


def test_sgml_provider_format_is_supported():
    config_data = {"stonks_securities": dict(CONFIG["stonks_securities"])}
    providers = dict(CONFIG["stonks_securities"]["providers"])
    providers["sec_filing_header"] = {
        "provider_code": "SEC_FILING_HEADER",
        "enabled": False,
        "url_template": "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{accession_number}.hdr.sgml",
        "expected_format": "sgml",
        "description": "On-demand EDGAR filing header.",
    }
    config_data["stonks_securities"]["providers"] = providers

    config = StonksSecuritiesConfig.from_mapping(config_data)

    assert config.providers[-1].provider_code == "SEC_FILING_HEADER"
    assert config.providers[-1].expected_format == "sgml"


def test_provider_codes_must_be_unique():
    config_data = {"stonks_securities": dict(CONFIG["stonks_securities"])}
    providers = dict(CONFIG["stonks_securities"]["providers"])
    providers["duplicate"] = {
        **providers["sec_company_tickers"],
        "url": "https://www.sec.gov/files/company_tickers_exchange.json",
    }
    config_data["stonks_securities"]["providers"] = providers

    with pytest.raises(StonksSecuritiesConfigError, match="unique"):
        StonksSecuritiesConfig.from_mapping(config_data)


def test_provider_must_define_url_or_template():
    config_data = {"stonks_securities": dict(CONFIG["stonks_securities"])}
    providers = dict(CONFIG["stonks_securities"]["providers"])
    providers["sec_company_tickers"] = dict(providers["sec_company_tickers"])
    del providers["sec_company_tickers"]["url"]
    config_data["stonks_securities"]["providers"] = providers

    with pytest.raises(StonksSecuritiesConfigError, match="url or url_template"):
        StonksSecuritiesConfig.from_mapping(config_data)
