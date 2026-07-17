import pytest

from empire_stonks_ohlcv import (
    EmpireStonksOHLCVError,
    OHLCVAcquisitionError,
    OHLCVConfigError,
    OHLCVParseError,
    OHLCVPersistenceError,
    OHLCVWorkflowError,
)


def test_public_exception_hierarchy() -> None:
    exception_types = (
        OHLCVAcquisitionError,
        OHLCVConfigError,
        OHLCVParseError,
        OHLCVPersistenceError,
        OHLCVWorkflowError,
    )

    assert all(
        issubclass(error_type, EmpireStonksOHLCVError)
        for error_type in exception_types
    )


def test_workflow_error_rejects_unknown_stage_text() -> None:
    with pytest.raises(ValueError, match="persistence, or reporting"):
        OHLCVWorkflowError("secret provider detail")


def test_workflow_error_accepts_reporting_stage() -> None:
    error = OHLCVWorkflowError("reporting")

    assert error.stage == "reporting"
    assert str(error) == "OHLCV provider workflow failed during reporting."


def test_public_exports_are_explicit() -> None:
    import empire_stonks_ohlcv

    assert empire_stonks_ohlcv.__all__ == [
        "AcquiredObject",
        "AcquireProviderObjects",
        "BoundedIssueSummary",
        "CrossFeedOutcomeCounts",
        "DailyBarDateRange",
        "DailyBarWriteInput",
        "EODDATA_CONTENT_TYPE",
        "EODDATA_DAILY_SOURCE",
        "EODDATA_DAILY_JOB_NAME",
        "EODDATA_PROVIDER_CODE",
        "EODDATA_SYMBOL_LIST_SOURCE",
        "EODDataCredentials",
        "EODDataDailyRunResult",
        "EODDataHTTPResponse",
        "EODDataHTTPTransport",
        "EODDataImportResult",
        "EODDataQuoteListParseResult",
        "EODDataSymbolListParseResult",
        "FeedOutcomeCounts",
        "DailyBar",
        "EmpireStonksOHLCVError",
        "ImportIssue",
        "JOB_PROVIDER_CODES",
        "MAX_ISSUE_SAMPLES",
        "OHLCVAcquisitionError",
        "OHLCVConfig",
        "OHLCVConfigError",
        "OHLCVParseError",
        "OHLCVPersistenceError",
        "OHLCVWorkflowError",
        "OHLCVRunResult",
        "ParsedListingBatch",
        "ParsedProviderOutput",
        "ParseProviderObjects",
        "PersistenceCounts",
        "ProviderListing",
        "ProviderListingCoverage",
        "ProviderListingWriteResult",
        "ProviderMarketHealth",
        "ProviderImportResult",
        "ProviderSourceMetadata",
        "ProviderSeriesHealth",
        "ProviderValidationResult",
        "ProviderWeekdayGapResult",
        "RAW_SOURCE_OBJECT_KIND",
        "REPORT_OBJECT_KIND",
        "REPORT_SCHEMA_VERSION",
        "ResolvedProviderListing",
        "SAFE_FAILURE_MESSAGE",
        "SourceSnapshotRegistration",
        "SourceMarketWriteCounts",
        "STOOQ_DAILY_SOURCE",
        "STOOQ_HISTORY_SOURCE",
        "YAHOO_DAILY_SOURCE",
        "WeekdayGapCandidate",
        "acquire_eoddata_objects",
        "build_raw_filename",
        "build_raw_object_key",
        "build_eoddata_report",
        "build_report_object_key",
        "eoddata_report_to_json",
        "build_run_summary",
        "execute_import_boundary",
        "import_eoddata_daily",
        "parse_eoddata_quote_list",
        "parse_eoddata_symbol_list",
        "upsert_provider_listings",
        "upsert_daily_bars",
        "upsert_provider_source_snapshot",
        "select_daily_bar_date_range",
        "select_latest_trading_date",
        "select_provider_latest_trading_date",
        "select_provider_listing_coverage",
        "select_provider_market_health",
        "select_provider_series_health",
        "select_provider_weekday_gaps",
        "run_provider_import",
        "run_provider_pipeline",
        "run_eoddata_daily",
        "store_raw_bytes",
        "store_eoddata_report",
        "store_raw_file",
    ]
