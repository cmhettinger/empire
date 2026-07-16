"""Reusable provider-native OHLCV ingestion utilities for Empire stonks."""

from empire_stonks_ohlcv.config import EODDataCredentials, OHLCVConfig
from empire_stonks_ohlcv.exceptions import (
    EmpireStonksOHLCVError,
    OHLCVAcquisitionError,
    OHLCVConfigError,
    OHLCVParseError,
    OHLCVPersistenceError,
)
from empire_stonks_ohlcv.models import DailyBar, ProviderListing
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
from empire_stonks_ohlcv.results import (
    AcquiredObject,
    ImportIssue,
    ParsedListingBatch,
    PersistenceCounts,
    ProviderImportResult,
)

__all__ = [
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
    "ResolvedProviderListing",
    "upsert_provider_listings",
    "upsert_daily_bars",
    "select_daily_bar_date_range",
    "select_latest_trading_date",
    "select_provider_latest_trading_date",
    "select_provider_listing_coverage",
]
