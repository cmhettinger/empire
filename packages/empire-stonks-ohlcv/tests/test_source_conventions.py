from dataclasses import FrozenInstanceError

import pytest

from empire_stonks_ohlcv import (
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
    STOOQ_DAILY_SOURCE,
    STOOQ_HISTORY_SOURCE,
    YAHOO_DAILY_SOURCE,
    ProviderSourceMetadata,
)


PROVIDER_SOURCES = {
    "EODDATA": (
        EODDATA_SYMBOL_LIST_SOURCE,
        EODDATA_DAILY_SOURCE,
    ),
    "STOOQ": (
        STOOQ_DAILY_SOURCE,
        STOOQ_HISTORY_SOURCE,
    ),
    "YAHOO": (YAHOO_DAILY_SOURCE,),
}


def test_production_source_identifiers_are_exact_and_stable() -> None:
    assert PROVIDER_SOURCES == {
        "EODDATA": (
            ProviderSourceMetadata("eoddata_symbol_list", "1.0.0"),
            ProviderSourceMetadata("eoddata_daily", "1.0.0"),
        ),
        "STOOQ": (
            ProviderSourceMetadata("stooq_daily", "1.0.0"),
            ProviderSourceMetadata("stooq_history", "1.0.0"),
        ),
        "YAHOO": (ProviderSourceMetadata("yahoo_daily", "1.0.0"),),
    }


def test_source_identifiers_are_unique_and_provider_prefixed() -> None:
    all_sources = [
        source
        for sources in PROVIDER_SOURCES.values()
        for source in sources
    ]

    assert len({source.source_code for source in all_sources}) == len(all_sources)
    for provider_code, sources in PROVIDER_SOURCES.items():
        assert all(
            source.source_code.startswith(f"{provider_code.lower()}_")
            for source in sources
        )


def test_source_convention_records_are_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        EODDATA_DAILY_SOURCE.parser_version = "2.0.0"  # type: ignore[misc]
