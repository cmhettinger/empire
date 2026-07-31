from __future__ import annotations

from datetime import time
from uuid import UUID

import pytest

from empire_stonks_ohlcv import (
    EligibilityRule,
    SessionDateRule,
    select_active_yahoo_listings,
)


class FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.query = ""
        self.params: tuple[object, ...] = ()

    def execute(
        self,
        query: str,
        params: tuple[object, ...],
    ) -> None:
        self.query = query
        self.params = params

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


def _row(
    index: int,
    *,
    ticker: str,
    yahoo_ticker: str,
    policy_code: str = "YH_XNYS_CLOSE_90M",
    calendar_name: str | None = "XNYS",
    eligibility_rule: str = "SESSION_CLOSE",
    cutoff: time | None = None,
    date_rule: str = "CALENDAR_SESSION",
) -> tuple[object, ...]:
    return (
        UUID(int=index),
        ticker,
        f"{ticker} Name",
        "EQUITY_INDEX",
        {"YahooTicker": yahoo_ticker},
        policy_code,
        calendar_name,
        "America/New_York",
        eligibility_rule,
        cutoff,
        90,
        date_rule,
    )


def test_selects_all_active_seed_contracts_in_ticker_order() -> None:
    cursor = FakeCursor(
        [
            _row(1, ticker="DOW", yahoo_ticker="^DJI"),
            _row(
                2,
                ticker="DXY",
                yahoo_ticker="DX-Y.NYB",
                policy_code="YH_DXY_2200",
                calendar_name=None,
                eligibility_rule="LOCAL_CUTOFF",
                cutoff=time(22),
                date_rule="PROVIDER_LOCAL_DATE",
            ),
            _row(3, ticker="SPX", yahoo_ticker="^GSPC"),
        ]
    )

    result = select_active_yahoo_listings(cursor=cursor)

    assert cursor.params == ("YAHOO", "XIDX")
    assert "listing.status = 'ACTIVE'" in cursor.query
    assert "ORDER BY listing.ticker" in cursor.query
    assert [item.target.ticker for item in result] == ["DOW", "DXY", "SPX"]
    assert result[0].listing.metadata == {"YahooTicker": "^DJI"}
    assert result[0].policy.eligibility_rule is (
        EligibilityRule.SESSION_CLOSE
    )
    assert result[1].policy.session_date_rule is (
        SessionDateRule.PROVIDER_LOCAL_DATE
    )
    assert result[1].policy.cutoff_local_time == time(22)


@pytest.mark.parametrize(
    "rows, message",
    [
        (
            [
                _row(1, ticker="DOW", yahoo_ticker="^DJI"),
                _row(2, ticker="DOW", yahoo_ticker="^DJI2"),
            ],
            "unique",
        ),
        (
            [
                _row(1, ticker="SPX", yahoo_ticker="^GSPC"),
                _row(2, ticker="DOW", yahoo_ticker="^DJI"),
            ],
            "unordered",
        ),
        (
            [
                (
                    *_row(
                        1,
                        ticker="SPX",
                        yahoo_ticker="^GSPC",
                    )[:4],
                    {},
                    *_row(
                        1,
                        ticker="SPX",
                        yahoo_ticker="^GSPC",
                    )[5:],
                )
            ],
            "YahooTicker",
        ),
    ],
)
def test_rejects_ambiguous_or_invalid_seed_rows(
    rows: list[tuple[object, ...]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        select_active_yahoo_listings(cursor=FakeCursor(rows))
