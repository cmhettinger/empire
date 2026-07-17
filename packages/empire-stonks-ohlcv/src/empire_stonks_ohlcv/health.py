"""Provider-scoped OHLCV coverage, freshness, and gap query inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from uuid import UUID

from empire_stonks_ohlcv.validation import MAX_ISSUE_SAMPLES


ProviderListingStatus = Literal["ACTIVE", "INACTIVE"]


@dataclass(frozen=True)
class ProviderMarketHealth:
    """Persisted coverage summary for one exact provider market."""

    provider_code: str
    market: str
    active_listing_count: int
    inactive_listing_count: int
    active_listings_with_bars: int
    active_listings_without_bars: int
    inactive_listings_with_bars: int
    inactive_listings_without_bars: int
    active_bar_count: int
    inactive_bar_count: int
    first_trading_date: date | None
    last_trading_date: date | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_code": self.provider_code,
            "market": self.market,
            "active_listing_count": self.active_listing_count,
            "inactive_listing_count": self.inactive_listing_count,
            "active_listings_with_bars": self.active_listings_with_bars,
            "active_listings_without_bars": self.active_listings_without_bars,
            "inactive_listings_with_bars": self.inactive_listings_with_bars,
            "inactive_listings_without_bars": (
                self.inactive_listings_without_bars
            ),
            "active_bar_count": self.active_bar_count,
            "inactive_bar_count": self.inactive_bar_count,
            "first_trading_date": _date_to_string(self.first_trading_date),
            "last_trading_date": _date_to_string(self.last_trading_date),
        }


@dataclass(frozen=True)
class ProviderSeriesHealth:
    """Coverage and freshness inputs for one provider-native series."""

    provider_listing_id: UUID
    provider_code: str
    market: str
    ticker: str
    status: ProviderListingStatus
    first_seen: date | None
    last_seen: date | None
    first_trading_date: date | None
    last_trading_date: date | None
    bar_count: int

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "provider_code": self.provider_code,
            "market": self.market,
            "ticker": self.ticker,
            "status": self.status,
            "first_seen": _date_to_string(self.first_seen),
            "last_seen": _date_to_string(self.last_seen),
            "first_trading_date": _date_to_string(self.first_trading_date),
            "last_trading_date": _date_to_string(self.last_trading_date),
            "bar_count": self.bar_count,
        }


@dataclass(frozen=True)
class WeekdayGapCandidate:
    """One non-calendar-authoritative missing weekday between stored bars."""

    provider_listing_id: UUID
    market: str
    ticker: str
    previous_trading_date: date
    missing_weekday: date
    next_trading_date: date

    def to_dict(self) -> dict[str, str]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "market": self.market,
            "ticker": self.ticker,
            "previous_trading_date": self.previous_trading_date.isoformat(),
            "missing_weekday": self.missing_weekday.isoformat(),
            "next_trading_date": self.next_trading_date.isoformat(),
        }


@dataclass(frozen=True)
class ProviderWeekdayGapResult:
    """Complete gap total with deterministic bounded active-series samples."""

    provider_code: str
    total_count: int
    samples: tuple[WeekdayGapCandidate, ...]

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def truncated(self) -> bool:
        return self.sample_count < self.total_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_code": self.provider_code,
            "total_count": self.total_count,
            "sample_count": self.sample_count,
            "truncated": self.truncated,
            "calendar_authoritative": False,
            "samples": [sample.to_dict() for sample in self.samples],
        }


_SERIES_HEALTH_SQL = """
    SELECT
        listing.provider_listing_id,
        listing.provider_code,
        listing.market,
        listing.ticker,
        listing.status,
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
        listing.status,
        listing.first_seen,
        listing.last_seen
    ORDER BY listing.market, listing.ticker, listing.provider_listing_id
"""


_MARKET_HEALTH_SQL = """
    WITH series AS (
        SELECT
            listing.provider_code,
            listing.market,
            listing.status,
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
            listing.status
    )
    SELECT
        provider_code,
        market,
        count(*) FILTER (WHERE status = 'ACTIVE') AS active_listing_count,
        count(*) FILTER (WHERE status = 'INACTIVE') AS inactive_listing_count,
        count(*) FILTER (
            WHERE status = 'ACTIVE' AND bar_count > 0
        ) AS active_listings_with_bars,
        count(*) FILTER (
            WHERE status = 'ACTIVE' AND bar_count = 0
        ) AS active_listings_without_bars,
        count(*) FILTER (
            WHERE status = 'INACTIVE' AND bar_count > 0
        ) AS inactive_listings_with_bars,
        count(*) FILTER (
            WHERE status = 'INACTIVE' AND bar_count = 0
        ) AS inactive_listings_without_bars,
        coalesce(sum(bar_count) FILTER (WHERE status = 'ACTIVE'), 0),
        coalesce(sum(bar_count) FILTER (WHERE status = 'INACTIVE'), 0),
        min(first_trading_date) FILTER (WHERE status = 'ACTIVE'),
        max(last_trading_date) FILTER (WHERE status = 'ACTIVE')
    FROM series
    GROUP BY provider_code, market
    ORDER BY market
"""


_WEEKDAY_GAPS_SQL = """
    WITH ordered_bars AS (
        SELECT
            listing.provider_listing_id,
            listing.market,
            listing.ticker,
            daily.trading_date,
            lag(daily.trading_date) OVER (
                PARTITION BY listing.provider_listing_id
                ORDER BY daily.trading_date
            ) AS previous_trading_date
        FROM stonks.provider_listing AS listing
        JOIN stonks.ohlcv_daily AS daily
          ON daily.provider_listing_id = listing.provider_listing_id
        WHERE listing.provider_code = %s
          AND listing.status = 'ACTIVE'
    ), gaps AS (
        SELECT
            provider_listing_id,
            market,
            ticker,
            previous_trading_date,
            missing_day::date AS missing_weekday,
            trading_date AS next_trading_date
        FROM ordered_bars
        CROSS JOIN LATERAL generate_series(
            previous_trading_date + 1,
            trading_date - 1,
            interval '1 day'
        ) AS missing_day
        WHERE previous_trading_date IS NOT NULL
          AND extract(isodow FROM missing_day) <= 5
    ), counted AS (
        SELECT gaps.*, count(*) OVER () AS total_count
        FROM gaps
    )
    SELECT
        provider_listing_id,
        market,
        ticker,
        previous_trading_date,
        missing_weekday,
        next_trading_date,
        total_count
    FROM counted
    ORDER BY market, ticker, provider_listing_id, missing_weekday
    LIMIT %s
"""


def select_provider_market_health(
    *,
    cursor: Any,
    provider_code: str,
) -> tuple[ProviderMarketHealth, ...]:
    """Return ordered active/inactive market coverage for one provider."""

    _validate_provider_code(provider_code)
    cursor.execute(_MARKET_HEALTH_SQL, (provider_code,))
    return tuple(ProviderMarketHealth(*row) for row in cursor.fetchall())


def select_provider_series_health(
    *,
    cursor: Any,
    provider_code: str,
) -> tuple[ProviderSeriesHealth, ...]:
    """Return deterministic series-level freshness inputs for one provider."""

    _validate_provider_code(provider_code)
    cursor.execute(_SERIES_HEALTH_SQL, (provider_code,))
    return tuple(ProviderSeriesHealth(*row) for row in cursor.fetchall())


def select_provider_weekday_gaps(
    *,
    cursor: Any,
    provider_code: str,
    sample_limit: int = MAX_ISSUE_SAMPLES,
) -> ProviderWeekdayGapResult:
    """Return active-series weekday-shaped gaps with a complete total."""

    _validate_provider_code(provider_code)
    if isinstance(sample_limit, bool) or not isinstance(sample_limit, int):
        raise TypeError("sample_limit must be an integer.")
    if not 1 <= sample_limit <= MAX_ISSUE_SAMPLES:
        raise ValueError(
            f"sample_limit must be between 1 and {MAX_ISSUE_SAMPLES}."
        )
    cursor.execute(_WEEKDAY_GAPS_SQL, (provider_code, sample_limit))
    rows = cursor.fetchall()
    return ProviderWeekdayGapResult(
        provider_code=provider_code,
        total_count=0 if not rows else rows[0][6],
        samples=tuple(WeekdayGapCandidate(*row[:6]) for row in rows),
    )


def _validate_provider_code(provider_code: object) -> None:
    if not isinstance(provider_code, str):
        raise TypeError("provider_code must be a string.")
    if not provider_code or provider_code != provider_code.strip():
        raise ValueError("provider_code must be non-empty and trimmed.")
    if len(provider_code) > 32 or provider_code != provider_code.upper():
        raise ValueError("provider_code must be uppercase and at most 32 characters.")


def _date_to_string(value: date | None) -> str | None:
    return None if value is None else value.isoformat()
