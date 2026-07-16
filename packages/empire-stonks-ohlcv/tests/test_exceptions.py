from empire_stonks_ohlcv import (
    EmpireStonksOHLCVError,
    OHLCVAcquisitionError,
    OHLCVConfigError,
    OHLCVParseError,
    OHLCVPersistenceError,
)


def test_public_exception_hierarchy() -> None:
    exception_types = (
        OHLCVAcquisitionError,
        OHLCVConfigError,
        OHLCVParseError,
        OHLCVPersistenceError,
    )

    assert all(
        issubclass(error_type, EmpireStonksOHLCVError)
        for error_type in exception_types
    )


def test_public_exports_are_explicit() -> None:
    import empire_stonks_ohlcv

    assert empire_stonks_ohlcv.__all__ == [
        "AcquiredObject",
        "DailyBarDateRange",
        "DailyBarWriteInput",
        "EODDataCredentials",
        "DailyBar",
        "EmpireStonksOHLCVError",
        "ImportIssue",
        "OHLCVAcquisitionError",
        "OHLCVConfig",
        "OHLCVConfigError",
        "OHLCVParseError",
        "OHLCVPersistenceError",
        "ParsedListingBatch",
        "PersistenceCounts",
        "ProviderListing",
        "ProviderListingCoverage",
        "ProviderListingWriteResult",
        "ProviderImportResult",
        "RAW_SOURCE_OBJECT_KIND",
        "ResolvedProviderListing",
        "SourceSnapshotRegistration",
        "build_raw_filename",
        "build_raw_object_key",
        "upsert_provider_listings",
        "upsert_daily_bars",
        "upsert_provider_source_snapshot",
        "select_daily_bar_date_range",
        "select_latest_trading_date",
        "select_provider_latest_trading_date",
        "select_provider_listing_coverage",
        "store_raw_bytes",
        "store_raw_file",
    ]
