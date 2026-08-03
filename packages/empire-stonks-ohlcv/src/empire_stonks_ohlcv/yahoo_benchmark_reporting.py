"""Date-scoped market reporting for active Yahoo benchmark listings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from empire_stonks_ohlcv.exceptions import OHLCVCalendarError
from empire_stonks_ohlcv.market_sessions import MarketSessionService
from empire_stonks_ohlcv.yahoo_benchmark_sections import (
    YAHOO_BENCHMARK_SECTIONS,
)
from empire_stonks_ohlcv.yahoo_listings import (
    SeededYahooListing,
    select_active_yahoo_listings,
)


class YahooBenchmarkStatus(StrEnum):
    """Display state for one active benchmark on the requested date."""

    REPORTED = "REPORTED"
    MARKET_CLOSED = "MARKET CLOSED"
    NOT_YET_ELIGIBLE = "NOT YET ELIGIBLE"
    NO_DATA = "NO DATA"


@dataclass(frozen=True, slots=True)
class YahooBenchmarkRow:
    """One active Yahoo listing and its exact-date observation state."""

    provider_listing_id: UUID
    ticker: str
    name: str
    instrument_type_code: str
    policy_code: str
    status: YahooBenchmarkStatus
    close: Decimal | None = None
    change: Decimal | None = None
    changepct: Decimal | None = None
    volume: Decimal | None = None
    previous_trading_date: date | None = None
    status_detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_listing_id, UUID):
            raise TypeError("provider_listing_id must be a UUID.")
        if not isinstance(self.status, YahooBenchmarkStatus):
            raise TypeError("status must be a YahooBenchmarkStatus.")
        if self.status is YahooBenchmarkStatus.REPORTED and self.close is None:
            raise ValueError("Reported benchmark rows require a close.")
        if self.status is not YahooBenchmarkStatus.REPORTED and any(
            value is not None
            for value in (self.close, self.change, self.changepct, self.volume)
        ):
            raise ValueError("Unavailable benchmark rows cannot contain bar values.")


@dataclass(frozen=True, slots=True)
class YahooBenchmarkSection:
    """One ordered report section containing active listings only."""

    code: str
    title: str
    membership_version: str
    rows: tuple[YahooBenchmarkRow, ...]

    @property
    def reported_count(self) -> int:
        return sum(row.status is YahooBenchmarkStatus.REPORTED for row in self.rows)

    @property
    def unavailable_count(self) -> int:
        return len(self.rows) - self.reported_count


@dataclass(frozen=True, slots=True)
class YahooDailyBenchmarkReport:
    """Complete active-listing benchmark report for one calendar date."""

    trading_date: date
    generated_at: datetime
    sections: tuple[YahooBenchmarkSection, ...]

    def __post_init__(self) -> None:
        if type(self.trading_date) is not date:
            raise TypeError("trading_date must be a date.")
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware.")
        rows = tuple(row for section in self.sections for row in section.rows)
        listing_ids = tuple(row.provider_listing_id for row in rows)
        if len(listing_ids) != len(set(listing_ids)):
            raise ValueError("Benchmark report listings must be unique.")

    @property
    def active_listing_count(self) -> int:
        return sum(len(section.rows) for section in self.sections)

    @property
    def reported_count(self) -> int:
        return sum(section.reported_count for section in self.sections)

    @property
    def market_closed_count(self) -> int:
        return self._status_count(YahooBenchmarkStatus.MARKET_CLOSED)

    @property
    def not_yet_eligible_count(self) -> int:
        return self._status_count(YahooBenchmarkStatus.NOT_YET_ELIGIBLE)

    @property
    def no_data_count(self) -> int:
        return self._status_count(YahooBenchmarkStatus.NO_DATA)

    def _status_count(self, status: YahooBenchmarkStatus) -> int:
        return sum(
            row.status is status
            for section in self.sections
            for row in section.rows
        )


def build_yahoo_daily_benchmark_report(
    *,
    cursor: Any,
    trading_date: date,
    generated_at: datetime | None = None,
    session_service: MarketSessionService | None = None,
) -> YahooDailyBenchmarkReport:
    """Build one exact-date report from active Yahoo listings and stored bars."""

    if type(trading_date) is not date:
        raise TypeError("trading_date must be a date.")
    generated = generated_at or datetime.now(UTC)
    if generated.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware.")
    generated = generated.astimezone(UTC)
    service = session_service or MarketSessionService()
    seeds = select_active_yahoo_listings(cursor=cursor)
    stored = _select_observations(
        cursor=cursor,
        listing_ids=tuple(seed.target.provider_listing_id for seed in seeds),
        trading_date=trading_date,
    )
    rows = {
        seed.target.ticker: _benchmark_row(
            seed=seed,
            observation=stored[seed.target.provider_listing_id],
            trading_date=trading_date,
            generated_at=generated,
            session_service=service,
        )
        for seed in seeds
    }
    sections: list[YahooBenchmarkSection] = []
    assigned: set[str] = set()
    for spec in YAHOO_BENCHMARK_SECTIONS:
        selected = tuple(rows[ticker] for ticker in spec.tickers if ticker in rows)
        if not selected:
            continue
        assigned.update(row.ticker for row in selected)
        sections.append(
            YahooBenchmarkSection(
                code=spec.code,
                title=spec.title,
                membership_version=spec.membership_version,
                rows=selected,
            )
        )
    unassigned = tuple(rows[ticker] for ticker in sorted(set(rows) - assigned))
    if unassigned:
        sections.append(
            YahooBenchmarkSection(
                code="ADDITIONAL_ACTIVE",
                title="Additional Active Yahoo Benchmarks",
                membership_version="dynamic-active",
                rows=unassigned,
            )
        )
    return YahooDailyBenchmarkReport(
        trading_date=trading_date,
        generated_at=generated,
        sections=tuple(sections),
    )


def _select_observations(
    *,
    cursor: Any,
    listing_ids: tuple[UUID, ...],
    trading_date: date,
) -> dict[UUID, tuple[object, ...]]:
    result = {listing_id: (None,) * 7 for listing_id in listing_ids}
    if not listing_ids:
        return result
    cursor.execute(
        """
        /* empire_yahoo_benchmark:observations */
        SELECT
            listing.provider_listing_id,
            current_bar.close,
            current_bar.volume,
            previous_bar.trading_date,
            previous_bar.close,
            current_bar.open,
            current_bar.high,
            current_bar.low
        FROM stonks.provider_listing AS listing
        LEFT JOIN stonks.ohlcv_daily AS current_bar
          ON current_bar.provider_listing_id = listing.provider_listing_id
         AND current_bar.trading_date = %s
        LEFT JOIN LATERAL (
            SELECT daily.trading_date, daily.close
            FROM stonks.ohlcv_daily AS daily
            WHERE daily.provider_listing_id = listing.provider_listing_id
              AND daily.trading_date < %s
            ORDER BY daily.trading_date DESC
            LIMIT 1
        ) AS previous_bar ON TRUE
        WHERE listing.provider_listing_id = ANY(%s)
          AND listing.provider_code = 'YAHOO'
          AND listing.status = 'ACTIVE'
        ORDER BY listing.ticker, listing.provider_listing_id
        """,
        (trading_date, trading_date, list(listing_ids)),
    )
    for row in cursor.fetchall():
        if not isinstance(row, (tuple, list)) or len(row) != 8:
            raise ValueError("Yahoo benchmark query returned an invalid row.")
        listing_id = row[0]
        if listing_id not in result:
            raise ValueError("Yahoo benchmark query returned an unknown listing.")
        result[listing_id] = tuple(row[1:])
    return result


def _benchmark_row(
    *,
    seed: SeededYahooListing,
    observation: tuple[object, ...],
    trading_date: date,
    generated_at: datetime,
    session_service: MarketSessionService,
) -> YahooBenchmarkRow:
    close_value, volume_value, previous_date, previous_close, *_ = observation
    common = {
        "provider_listing_id": seed.target.provider_listing_id,
        "ticker": seed.target.ticker,
        "name": seed.listing.name or seed.target.ticker,
        "instrument_type_code": seed.listing.instrument_type_code,
        "policy_code": seed.policy.code,
    }
    if close_value is not None:
        close = _decimal(close_value)
        prior = None if previous_close is None else _decimal(previous_close)
        change = None if prior is None else close - prior
        changepct = (
            None if prior in (None, Decimal(0)) else (close - prior) / prior
        )
        return YahooBenchmarkRow(
            **common,
            status=YahooBenchmarkStatus.REPORTED,
            close=close,
            change=change,
            changepct=changepct,
            volume=None if volume_value is None else _decimal(volume_value),
            previous_trading_date=(
                previous_date if type(previous_date) is date else None
            ),
        )

    try:
        if seed.policy.is_observed_only:
            candidate = session_service.observed_poll_candidate(
                policy=seed.policy,
                candidate_date=trading_date,
            )
            status = (
                YahooBenchmarkStatus.NO_DATA
                if candidate.is_eligible(generated_at)
                else YahooBenchmarkStatus.NOT_YET_ELIGIBLE
            )
            detail = (
                "Eligible provider date returned no stored bar."
                if status is YahooBenchmarkStatus.NO_DATA
                else "Provider publication cutoff has not passed."
            )
        else:
            expected = session_service.expected_sessions(
                policy=seed.policy,
                start_date=trading_date,
                end_date=trading_date,
            )
            if not expected:
                status = YahooBenchmarkStatus.MARKET_CLOSED
                detail = "The configured market calendar has no session."
            elif expected[0].is_eligible(generated_at):
                status = YahooBenchmarkStatus.NO_DATA
                detail = "An eligible session returned no stored Yahoo bar."
            else:
                status = YahooBenchmarkStatus.NOT_YET_ELIGIBLE
                detail = "The configured publication time has not passed."
    except OHLCVCalendarError:
        status = YahooBenchmarkStatus.NO_DATA
        detail = "The configured market calendar could not be resolved."
    return YahooBenchmarkRow(
        **common,
        status=status,
        status_detail=detail,
    )


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("Yahoo benchmark query returned an invalid numeric value.")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Yahoo benchmark query returned a non-finite value.")
    return result


__all__ = [
    "YahooBenchmarkRow",
    "YahooBenchmarkSection",
    "YahooBenchmarkStatus",
    "YahooDailyBenchmarkReport",
    "build_yahoo_daily_benchmark_report",
]
