from __future__ import annotations

import json
from datetime import date
from uuid import UUID

import pytest

from empire_stonks_ohlcv import (
    MAX_ISSUE_SAMPLES,
    ProviderMarketHealth,
    ProviderSeriesHealth,
    ProviderWeekdayGapResult,
    WeekdayGapCandidate,
    select_provider_market_health,
    select_provider_series_health,
    select_provider_weekday_gaps,
)


LISTING_ID = UUID("10000000-0000-4000-8000-000000000001")


class HealthCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.executions.append((query, params))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


def test_health_result_records_are_json_ready_and_status_aware() -> None:
    market = ProviderMarketHealth(
        provider_code="EODDATA",
        market="NYSE",
        active_listing_count=8,
        inactive_listing_count=2,
        active_listings_with_bars=7,
        active_listings_without_bars=1,
        inactive_listings_with_bars=1,
        inactive_listings_without_bars=1,
        active_bar_count=70,
        inactive_bar_count=4,
        first_trading_date=date(2026, 1, 2),
        last_trading_date=date(2026, 1, 30),
    )
    series = ProviderSeriesHealth(
        provider_listing_id=LISTING_ID,
        provider_code="EODDATA",
        market="NYSE",
        ticker="EMP.A",
        status="INACTIVE",
        first_seen=date(2026, 1, 2),
        last_seen=date(2026, 1, 30),
        first_trading_date=date(2026, 1, 2),
        last_trading_date=date(2026, 1, 30),
        bar_count=20,
    )

    assert market.to_dict() == {
        "provider_code": "EODDATA",
        "market": "NYSE",
        "active_listing_count": 8,
        "inactive_listing_count": 2,
        "active_listings_with_bars": 7,
        "active_listings_without_bars": 1,
        "inactive_listings_with_bars": 1,
        "inactive_listings_without_bars": 1,
        "active_bar_count": 70,
        "inactive_bar_count": 4,
        "first_trading_date": "2026-01-02",
        "last_trading_date": "2026-01-30",
    }
    assert series.is_active is False
    assert series.to_dict()["status"] == "INACTIVE"
    json.dumps(market.to_dict())
    json.dumps(series.to_dict())


def test_market_health_query_is_provider_scoped_and_order_preserving() -> None:
    rows = [
        (
            "EODDATA",
            "AMEX",
            3,
            1,
            2,
            1,
            1,
            0,
            10,
            2,
            date(2026, 1, 2),
            date(2026, 1, 30),
        ),
        (
            "EODDATA",
            "NYSE",
            5,
            0,
            5,
            0,
            0,
            0,
            25,
            0,
            date(2026, 1, 2),
            date(2026, 2, 2),
        ),
    ]
    cursor = HealthCursor(rows)

    result = select_provider_market_health(
        cursor=cursor,
        provider_code="EODDATA",
    )

    assert tuple(item.market for item in result) == ("AMEX", "NYSE")
    assert result[0].inactive_listing_count == 1
    assert cursor.executions[0][1] == ("EODDATA",)
    assert "listing.status" in cursor.executions[0][0]


def test_series_health_query_returns_active_inactive_and_empty_series() -> None:
    active_id = LISTING_ID
    inactive_id = UUID("20000000-0000-4000-8000-000000000002")
    cursor = HealthCursor(
        [
            (
                active_id,
                "EODDATA",
                "NASDAQ",
                "ACTIVE.ONE",
                "ACTIVE",
                date(2026, 1, 2),
                date(2026, 1, 30),
                date(2026, 1, 2),
                date(2026, 1, 30),
                20,
            ),
            (
                inactive_id,
                "EODDATA",
                "NASDAQ",
                "INACTIVE.EMPTY",
                "INACTIVE",
                None,
                None,
                None,
                None,
                0,
            ),
        ]
    )

    result = select_provider_series_health(
        cursor=cursor,
        provider_code="EODDATA",
    )

    assert result[0].is_active is True
    assert result[1].is_active is False
    assert result[1].last_trading_date is None
    assert result[1].to_dict()["bar_count"] == 0
    assert cursor.executions[0][1] == ("EODDATA",)
    assert "ORDER BY listing.market, listing.ticker" in cursor.executions[0][0]


def test_weekday_gap_query_has_complete_total_and_bounded_samples() -> None:
    rows = [
        (
            LISTING_ID,
            "NYSE",
            "EMP.A",
            date(2026, 1, 9),
            date(2026, 1, 12),
            date(2026, 1, 13),
            125,
        ),
    ]
    cursor = HealthCursor(rows)

    result = select_provider_weekday_gaps(
        cursor=cursor,
        provider_code="EODDATA",
        sample_limit=1,
    )

    assert isinstance(result, ProviderWeekdayGapResult)
    assert result.total_count == 125
    assert result.sample_count == 1
    assert result.truncated is True
    assert result.to_dict() == {
        "provider_code": "EODDATA",
        "total_count": 125,
        "sample_count": 1,
        "truncated": True,
        "calendar_authoritative": False,
        "samples": [
            WeekdayGapCandidate(
                provider_listing_id=LISTING_ID,
                market="NYSE",
                ticker="EMP.A",
                previous_trading_date=date(2026, 1, 9),
                missing_weekday=date(2026, 1, 12),
                next_trading_date=date(2026, 1, 13),
            ).to_dict()
        ],
    }
    assert cursor.executions[0][1] == ("EODDATA", 1)
    assert "listing.status = 'ACTIVE'" in cursor.executions[0][0]
    assert "extract(isodow FROM missing_day) <= 5" in cursor.executions[0][0]


def test_weekday_gap_query_returns_explicit_empty_result() -> None:
    result = select_provider_weekday_gaps(
        cursor=HealthCursor([]),
        provider_code="EODDATA",
    )

    assert result.to_dict() == {
        "provider_code": "EODDATA",
        "total_count": 0,
        "sample_count": 0,
        "truncated": False,
        "calendar_authoritative": False,
        "samples": [],
    }


@pytest.mark.parametrize(
    ("query_name", "provider_code", "sample_limit", "message"),
    (
        ("market", " eoddata", None, "trimmed"),
        ("series", "eoddata", None, "uppercase"),
        ("gaps", "EODDATA", 0, "between"),
        ("gaps", "EODDATA", MAX_ISSUE_SAMPLES + 1, "between"),
        ("gaps", "EODDATA", True, "integer"),
    ),
)
def test_health_queries_reject_invalid_scope_before_execution(
    query_name: str,
    provider_code: str,
    sample_limit: object,
    message: str,
) -> None:
    cursor = HealthCursor([])

    with pytest.raises((TypeError, ValueError), match=message):
        if query_name == "market":
            select_provider_market_health(
                cursor=cursor,
                provider_code=provider_code,
            )
        elif query_name == "series":
            select_provider_series_health(
                cursor=cursor,
                provider_code=provider_code,
            )
        else:
            select_provider_weekday_gaps(
                cursor=cursor,
                provider_code=provider_code,
                sample_limit=sample_limit,  # type: ignore[arg-type]
            )

    assert cursor.executions == []
