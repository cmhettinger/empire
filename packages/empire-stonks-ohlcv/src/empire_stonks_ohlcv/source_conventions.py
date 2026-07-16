"""Stable production source identities for provider-native OHLCV inputs."""

from empire_stonks_ohlcv.results import ProviderSourceMetadata


EODDATA_SYMBOL_LIST_SOURCE = ProviderSourceMetadata(
    source_code="eoddata_symbol_list",
    parser_version="1.0.0",
)
EODDATA_DAILY_SOURCE = ProviderSourceMetadata(
    source_code="eoddata_daily",
    parser_version="1.0.0",
)
STOOQ_DAILY_SOURCE = ProviderSourceMetadata(
    source_code="stooq_daily",
    parser_version="1.0.0",
)
STOOQ_HISTORY_SOURCE = ProviderSourceMetadata(
    source_code="stooq_history",
    parser_version="1.0.0",
)
YAHOO_DAILY_SOURCE = ProviderSourceMetadata(
    source_code="yahoo_daily",
    parser_version="1.0.0",
)
