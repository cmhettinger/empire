"""Read-only provider-native OHLCV queries for incremental import and reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class DailyBarDateRange:
    """The stored date range and row count for one provider-native series."""

    provider_listing_id: UUID
    first_trading_date: date
    last_trading_date: date
    bar_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "first_trading_date": self.first_trading_date.isoformat(),
            "last_trading_date": self.last_trading_date.isoformat(),
            "bar_count": self.bar_count,
        }


@dataclass(frozen=True)
class ProviderListingCoverage:
    """One provider listing's persisted coverage and freshness inputs."""

    provider_listing_id: UUID
    provider_code: str
    market: str
    ticker: str
    first_seen: date | None
    last_seen: date | None
    first_trading_date: date | None
    last_trading_date: date | None
    bar_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "provider_code": self.provider_code,
            "market": self.market,
            "ticker": self.ticker,
            "first_seen": _date_to_string(self.first_seen),
            "last_seen": _date_to_string(self.last_seen),
            "first_trading_date": _date_to_string(self.first_trading_date),
            "last_trading_date": _date_to_string(self.last_trading_date),
            "bar_count": self.bar_count,
        }


def select_latest_trading_date(*, cursor: Any, provider_listing_id: UUID) -> date | None:
    """Return one series' incremental cutoff, or ``None`` when it has no bars.

    The caller owns the transaction. This helper only reads provider-native data.
    """

    _validate_provider_listing_id(provider_listing_id)
    cursor.execute(
        """
        SELECT max(trading_date)
        FROM stonks.ohlcv_daily
        WHERE provider_listing_id = %s
        """,
        (provider_listing_id,),
    )
    row = cursor.fetchone()
    return None if row is None else row[0]


def select_daily_bar_date_range(
    *,
    cursor: Any,
    provider_listing_id: UUID,
) -> DailyBarDateRange | None:
    """Return one series' persisted date range, or ``None`` when it has no bars."""

    _validate_provider_listing_id(provider_listing_id)
    cursor.execute(
        """
        SELECT min(trading_date), max(trading_date), count(*)
        FROM stonks.ohlcv_daily
        WHERE provider_listing_id = %s
        """,
        (provider_listing_id,),
    )
    row = cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return DailyBarDateRange(
        provider_listing_id=provider_listing_id,
        first_trading_date=row[0],
        last_trading_date=row[1],
        bar_count=row[2],
    )


def select_provider_latest_trading_date(
    *,
    cursor: Any,
    provider_code: str,
) -> date | None:
    """Return a provider's latest stored trading date for report freshness."""

    _validate_provider_code(provider_code)
    cursor.execute(
        """
        SELECT max(daily.trading_date)
        FROM stonks.provider_listing AS listing
        JOIN stonks.ohlcv_daily AS daily
          ON daily.provider_listing_id = listing.provider_listing_id
        WHERE listing.provider_code = %s
        """,
        (provider_code,),
    )
    row = cursor.fetchone()
    return None if row is None else row[0]


def select_provider_listing_coverage(
    *,
    cursor: Any,
    provider_code: str,
) -> tuple[ProviderListingCoverage, ...]:
    """Return ordered provider-scoped coverage rows, including listings with no bars.

    Rows sort by exact native market, then ticker, then durable listing ID. The
    latest trading date is the input for downstream freshness and stale-series
    reporting; age thresholds are deliberately left to that report contract.
    """

    _validate_provider_code(provider_code)
    cursor.execute(
        """
        SELECT
            listing.provider_listing_id,
            listing.provider_code,
            listing.market,
            listing.ticker,
            listing.first_seen,
            listing.last_seen,
            min(daily.trading_date) AS first_trading_date,
            max(daily.trading_date) AS last_trading_date,
            count(daily.trading_date) AS bar_count
        FROM stonks.provider_listing AS listing
        LEFT JOIN stonks.ohlcv_daily AS daily
          ON daily.provider_listing_id = listing.provider_listing_id
        WHERE listing.provider_code = %s
        GROUP BY
            listing.provider_listing_id,
            listing.provider_code,
            listing.market,
            listing.ticker,
            listing.first_seen,
            listing.last_seen
        ORDER BY listing.market, listing.ticker, listing.provider_listing_id
        """,
        (provider_code,),
    )
    return tuple(
        ProviderListingCoverage(
            provider_listing_id=row[0],
            provider_code=row[1],
            market=row[2],
            ticker=row[3],
            first_seen=row[4],
            last_seen=row[5],
            first_trading_date=row[6],
            last_trading_date=row[7],
            bar_count=row[8],
        )
        for row in cursor.fetchall()
    )


def _validate_provider_listing_id(provider_listing_id: UUID) -> None:
    if not isinstance(provider_listing_id, UUID):
        raise TypeError("provider_listing_id must be a UUID.")


def _validate_provider_code(provider_code: str) -> None:
    if not isinstance(provider_code, str):
        raise TypeError("provider_code must be a string.")
    if not provider_code or provider_code != provider_code.strip():
        raise ValueError("provider_code must be non-empty and trimmed.")
    if len(provider_code) > 32:
        raise ValueError("provider_code must contain at most 32 characters.")


def _date_to_string(value: date | None) -> str | None:
    return None if value is None else value.isoformat()
