"""Reusable provider-native OHLCV ingestion utilities for Empire stonks."""

from empire_stonks_ohlcv.config import EODDataCredentials, OHLCVConfig
from empire_stonks_ohlcv.eoddata import (
    EODDATA_CONTENT_TYPE,
    EODDATA_PROVIDER_CODE,
    EODDataHTTPResponse,
    EODDataHTTPTransport,
    acquire_eoddata_objects,
)
from empire_stonks_ohlcv.exceptions import (
    EmpireStonksOHLCVError,
    OHLCVAcquisitionError,
    OHLCVConfigError,
    OHLCVParseError,
    OHLCVPersistenceError,
    OHLCVWorkflowError,
)
from empire_stonks_ohlcv.import_boundary import execute_import_boundary
from empire_stonks_ohlcv.models import DailyBar, ProviderListing
from empire_stonks_ohlcv.object_store import (
    RAW_SOURCE_OBJECT_KIND,
    build_raw_filename,
    build_raw_object_key,
    store_raw_bytes,
    store_raw_file,
)
from empire_stonks_ohlcv.listings import (
    ProviderListingWriteResult,
    ResolvedProviderListing,
    upsert_provider_listings,
)
from empire_stonks_ohlcv.daily_bars import DailyBarWriteInput, upsert_daily_bars
from empire_stonks_ohlcv.queries import (
    DailyBarDateRange,
    ProviderListingCoverage,
    select_daily_bar_date_range,
    select_latest_trading_date,
    select_provider_latest_trading_date,
    select_provider_listing_coverage,
)
from empire_stonks_ohlcv.provider_contract import (
    AcquireProviderObjects,
    ParseProviderObjects,
)
from empire_stonks_ohlcv.results import (
    AcquiredObject,
    ImportIssue,
    ParsedListingBatch,
    ParsedProviderOutput,
    PersistenceCounts,
    ProviderImportResult,
    ProviderSourceMetadata,
)
from empire_stonks_ohlcv.runner import (
    JOB_PROVIDER_CODES,
    SAFE_FAILURE_MESSAGE,
    OHLCVRunResult,
    build_run_summary,
    run_provider_import,
    run_provider_pipeline,
)
from empire_stonks_ohlcv.source_snapshots import (
    SourceSnapshotRegistration,
    upsert_provider_source_snapshot,
)
from empire_stonks_ohlcv.source_conventions import (
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
    STOOQ_DAILY_SOURCE,
    STOOQ_HISTORY_SOURCE,
    YAHOO_DAILY_SOURCE,
)

__all__ = [
    "AcquiredObject",
    "AcquireProviderObjects",
    "DailyBarDateRange",
    "DailyBarWriteInput",
    "EODDATA_CONTENT_TYPE",
    "EODDATA_DAILY_SOURCE",
    "EODDATA_PROVIDER_CODE",
    "EODDATA_SYMBOL_LIST_SOURCE",
    "EODDataCredentials",
    "EODDataHTTPResponse",
    "EODDataHTTPTransport",
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
    "acquire_eoddata_objects",
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
    "run_provider_pipeline",
    "store_raw_bytes",
    "store_raw_file",
]
