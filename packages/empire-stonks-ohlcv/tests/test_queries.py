from datetime import date
from uuid import uuid4

import pytest

from empire_stonks_ohlcv import (
    DailyBarDateRange,
    ProviderListingCoverage,
    select_daily_bar_date_range,
    select_latest_trading_date,
    select_provider_latest_trading_date,
    select_provider_listing_coverage,
)


def test_query_result_records_are_json_ready() -> None:
    provider_listing_id = uuid4()
    assert DailyBarDateRange(
        provider_listing_id=provider_listing_id,
        first_trading_date=date(2026, 1, 2),
        last_trading_date=date(2026, 1, 5),
        bar_count=2,
    ).to_dict() == {
        "provider_listing_id": str(provider_listing_id),
        "first_trading_date": "2026-01-02",
        "last_trading_date": "2026-01-05",
        "bar_count": 2,
    }
    assert ProviderListingCoverage(
        provider_listing_id=provider_listing_id,
        provider_code="EODDATA",
        market="NASDAQ",
        ticker="AAPL",
        first_seen=None,
        last_seen=None,
        first_trading_date=None,
        last_trading_date=None,
        bar_count=0,
    ).to_dict() == {
        "provider_listing_id": str(provider_listing_id),
        "provider_code": "EODDATA",
        "market": "NASDAQ",
        "ticker": "AAPL",
        "first_seen": None,
        "last_seen": None,
        "first_trading_date": None,
        "last_trading_date": None,
        "bar_count": 0,
    }


@pytest.mark.parametrize(
    ("query", "kwargs", "exception", "message"),
    (
        (
            select_latest_trading_date,
            {"provider_listing_id": "not-a-uuid"},
            TypeError,
            "provider_listing_id",
        ),
        (
            select_daily_bar_date_range,
            {"provider_listing_id": "not-a-uuid"},
            TypeError,
            "provider_listing_id",
        ),
        (
            select_provider_latest_trading_date,
            {"provider_code": " EODDATA"},
            ValueError,
            "trimmed",
        ),
        (
            select_provider_listing_coverage,
            {"provider_code": ""},
            ValueError,
            "non-empty",
        ),
    ),
)
def test_query_helpers_reject_invalid_inputs_before_querying(
    query: object,
    kwargs: dict[str, object],
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        query(cursor=object(), **kwargs)  # type: ignore[operator]
