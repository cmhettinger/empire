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
    with pytest.raises(ValueError, match="acquisition, parsing, or persistence"):
        OHLCVWorkflowError("secret provider detail")


def test_public_exports_are_explicit() -> None:
    import empire_stonks_ohlcv

    assert empire_stonks_ohlcv.__all__ == [
        "AcquiredObject",
        "AcquireProviderObjects",
        "DailyBarDateRange",
        "DailyBarWriteInput",
        "EODDATA_DAILY_SOURCE",
        "EODDATA_SYMBOL_LIST_SOURCE",
        "EODDataCredentials",
        "DailyBar",
        "EmpireStonksOHLCVError",
        "ImportIssue",
        "JOB_PROVIDER_CODES",
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
        "ProviderImportResult",
        "ProviderSourceMetadata",
        "RAW_SOURCE_OBJECT_KIND",
        "ResolvedProviderListing",
        "SAFE_FAILURE_MESSAGE",
        "SourceSnapshotRegistration",
        "STOOQ_DAILY_SOURCE",
        "STOOQ_HISTORY_SOURCE",
        "YAHOO_DAILY_SOURCE",
        "build_raw_filename",
        "build_raw_object_key",
        "build_run_summary",
        "execute_import_boundary",
        "upsert_provider_listings",
        "upsert_daily_bars",
        "upsert_provider_source_snapshot",
        "select_daily_bar_date_range",
        "select_latest_trading_date",
        "select_provider_latest_trading_date",
        "select_provider_listing_coverage",
        "run_provider_import",
        "store_raw_bytes",
        "store_raw_file",
    ]
