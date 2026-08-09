"""Read-only source-selection queries for technical-indicator inputs."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from empire_stonks_tech_indicators.config import (
    BenchmarkConfig,
    DEFAULT_SOURCE_READ_PAGE_SIZE,
    MAX_SOURCE_READ_PAGE_SIZE,
    MIN_SOURCE_READ_PAGE_SIZE,
)
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsValidationError,
)
from empire_stonks_tech_indicators.models import (
    ResolvedBenchmark,
    SourceBar,
    TechIndicatorsScope,
)


@dataclass(frozen=True)
class EligibleListing:
    """One P0.6-eligible provider listing and its scoped source coverage."""

    provider_listing_id: UUID
    provider_code: str
    market: str
    ticker: str
    instrument_type_code: str
    status: str
    first_trading_date: date | None
    last_trading_date: date | None
    source_observation_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.provider_listing_id, UUID):
            raise TypeError("provider_listing_id must be a UUID.")
        for field_name in (
            "provider_code",
            "market",
            "ticker",
            "instrument_type_code",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string.")
            if not value or value != value.strip():
                raise ValueError(f"{field_name} must be non-empty and trimmed.")
        if self.status not in {"ACTIVE", "INACTIVE"}:
            raise ValueError("status must be ACTIVE or INACTIVE.")
        for field_name in ("first_trading_date", "last_trading_date"):
            value = getattr(self, field_name)
            if value is not None and type(value) is not date:
                raise TypeError(f"{field_name} must be a date or None.")
        if type(self.source_observation_count) is not int:
            raise TypeError("source_observation_count must be an integer.")
        if self.source_observation_count < 0:
            raise ValueError("source_observation_count must be non-negative.")
        empty_range = (
            self.first_trading_date is None and self.last_trading_date is None
        )
        if empty_range != (self.source_observation_count == 0):
            raise ValueError(
                "source dates must both be null exactly when observation count is zero."
            )
        if (
            self.first_trading_date is not None
            and self.last_trading_date is not None
            and self.first_trading_date > self.last_trading_date
        ):
            raise ValueError("first_trading_date must not be after last_trading_date.")

    def has_minimum_history(self, minimum_observations: int) -> bool:
        """Return whether scoped source history meets an explicit minimum."""

        if type(minimum_observations) is not int:
            raise TypeError("minimum_observations must be an integer.")
        if minimum_observations < 1:
            raise ValueError("minimum_observations must be positive.")
        return self.source_observation_count >= minimum_observations

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "provider_code": self.provider_code,
            "market": self.market,
            "ticker": self.ticker,
            "instrument_type_code": self.instrument_type_code,
            "status": self.status,
            "first_trading_date": _date_to_string(self.first_trading_date),
            "last_trading_date": _date_to_string(self.last_trading_date),
            "source_observation_count": self.source_observation_count,
        }


@dataclass(frozen=True)
class BenchmarkHistory:
    """One resolved benchmark and its exact-date chronological source bars."""

    benchmark: ResolvedBenchmark
    bars: tuple[SourceBar, ...]
    _trading_dates: tuple[date, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.benchmark, ResolvedBenchmark):
            raise TypeError("benchmark must be a ResolvedBenchmark.")
        if not isinstance(self.bars, tuple) or any(
            not isinstance(bar, SourceBar) for bar in self.bars
        ):
            raise TypeError("bars must contain only SourceBar records.")
        previous_date: date | None = None
        for bar in self.bars:
            if bar.provider_listing_id != self.benchmark.provider_listing_id:
                raise ValueError("benchmark bars must use the resolved listing ID.")
            if previous_date is not None and bar.trading_date <= previous_date:
                raise ValueError("benchmark bars must be strictly chronological.")
            previous_date = bar.trading_date
        object.__setattr__(
            self,
            "_trading_dates",
            tuple(bar.trading_date for bar in self.bars),
        )

    @property
    def observation_count(self) -> int:
        return len(self.bars)

    @property
    def first_trading_date(self) -> date | None:
        return None if not self.bars else self.bars[0].trading_date

    @property
    def last_trading_date(self) -> date | None:
        return None if not self.bars else self.bars[-1].trading_date

    def bar_on(self, trading_date: date) -> SourceBar | None:
        """Return only an exact-date bar; never fill or select a nearby date."""

        if type(trading_date) is not date:
            raise TypeError("trading_date must be a date.")
        index = bisect_left(self._trading_dates, trading_date)
        if index == len(self.bars) or self.bars[index].trading_date != trading_date:
            return None
        return self.bars[index]

    def close_by_date(self) -> dict[date, Decimal]:
        """Return a new exact-date close lookup without forward-filled keys."""

        return {bar.trading_date: bar.close for bar in self.bars}

    def to_dict(self) -> dict[str, object]:
        """Return bounded history facts without serializing source payloads."""

        return {
            "benchmark": self.benchmark.to_dict(),
            "observation_count": self.observation_count,
            "first_trading_date": _date_to_string(self.first_trading_date),
            "last_trading_date": _date_to_string(self.last_trading_date),
        }


def select_eligible_listings(
    *,
    cursor: Any,
    scope: TechIndicatorsScope,
) -> tuple[EligibleListing, ...]:
    """Return P0.6-eligible listings with inclusive scoped source coverage.

    Source-value eligibility is independent of listing status and source
    history. The default scope returns active listings, including rows with no
    matching source observations. Inactive rows require the model's explicit
    listing-ID-only opt-in. Date bounds limit the coverage facts without
    changing source-value eligibility.

    The caller owns the cursor and transaction. This function performs one
    set-based read and never mutates provider listings or OHLCV.
    """

    _validate_cursor(cursor)
    if not isinstance(scope, TechIndicatorsScope):
        raise TypeError("scope must be a TechIndicatorsScope.")

    join_conditions = [
        "daily.provider_listing_id = listing.provider_listing_id",
    ]
    parameters: list[object] = []
    if scope.start_date is not None and scope.end_date is not None:
        join_conditions.append("daily.trading_date BETWEEN %s AND %s")
        parameters.extend((scope.start_date, scope.end_date))

    where_conditions = [
        _SOURCE_VALUE_ELIGIBILITY_SQL,
        "listing.status IN ('ACTIVE', 'INACTIVE')"
        if scope.include_inactive
        else "listing.status = 'ACTIVE'",
    ]
    if scope.provider_codes:
        where_conditions.append("listing.provider_code = ANY(%s::text[])")
        parameters.append(list(scope.provider_codes))
    if scope.markets:
        where_conditions.append("listing.market = ANY(%s::text[])")
        parameters.append(list(scope.markets))
    if scope.provider_listing_ids:
        where_conditions.append("listing.provider_listing_id = ANY(%s::uuid[])")
        parameters.append(list(scope.provider_listing_ids))

    cursor.execute(
        f"""
        SELECT
            listing.provider_listing_id,
            listing.provider_code,
            listing.market,
            listing.ticker,
            listing.instrument_type_code,
            listing.status,
            min(daily.trading_date) AS first_trading_date,
            max(daily.trading_date) AS last_trading_date,
            count(daily.trading_date) AS source_observation_count
        FROM stonks.provider_listing AS listing
        LEFT JOIN stonks.ohlcv_daily AS daily
          ON {' AND '.join(join_conditions)}
        WHERE {' AND '.join(where_conditions)}
        GROUP BY
            listing.provider_listing_id,
            listing.provider_code,
            listing.market,
            listing.ticker,
            listing.instrument_type_code,
            listing.status
        ORDER BY
            listing.provider_code,
            listing.market,
            listing.ticker,
            listing.provider_listing_id
        """,
        tuple(parameters),
    )
    return tuple(_eligible_listing(row) for row in cursor.fetchall())


def iter_source_bar_pages(
    *,
    cursor: Any,
    scope: TechIndicatorsScope,
    page_size: int = DEFAULT_SOURCE_READ_PAGE_SIZE,
) -> Iterator[tuple[SourceBar, ...]]:
    """Yield exact OHLCV pages in provider-listing/date natural-key order.

    Eligible listings are resolved once through :func:`select_eligible_listings`.
    Each bounded SQL query advances with a strict composite keyset, so neither
    this reader nor its caller must materialize the full source universe. The
    caller owns transaction isolation, cancellation, commit, rollback, and
    cursor lifetime.
    """

    _validate_cursor(cursor)
    if not isinstance(scope, TechIndicatorsScope):
        raise TypeError("scope must be a TechIndicatorsScope.")
    _validate_page_size(page_size)

    listings = select_eligible_listings(cursor=cursor, scope=scope)
    if not listings:
        return

    listing_ids = [item.provider_listing_id for item in listings]
    listing_identity = {
        item.provider_listing_id: (item.provider_code, item.market, item.ticker)
        for item in listings
    }
    after: tuple[UUID, date] | None = None

    while True:
        where_conditions = [
            "daily.provider_listing_id = ANY(%s::uuid[])",
        ]
        parameters: list[object] = [listing_ids]
        if scope.start_date is not None and scope.end_date is not None:
            where_conditions.append("daily.trading_date BETWEEN %s AND %s")
            parameters.extend((scope.start_date, scope.end_date))
        if after is not None:
            where_conditions.append(
                """ROW(daily.provider_listing_id, daily.trading_date)
                    > ROW(%s, %s)"""
            )
            parameters.extend(after)
        parameters.append(page_size)

        cursor.execute(
            f"""
            SELECT
                listing.provider_code,
                listing.market,
                listing.ticker,
                listing.provider_listing_id,
                daily.trading_date,
                daily.open,
                daily.high,
                daily.low,
                daily.close,
                daily.volume
            FROM stonks.ohlcv_daily AS daily
            JOIN stonks.provider_listing AS listing
              ON listing.provider_listing_id = daily.provider_listing_id
            WHERE {' AND '.join(where_conditions)}
            ORDER BY
                daily.provider_listing_id,
                daily.trading_date
            LIMIT %s
            """,
            tuple(parameters),
        )
        rows = cursor.fetchall()
        if len(rows) > page_size:
            raise ValueError("Source-bar query returned more than one page.")
        if not rows:
            return

        bars, after = _source_bar_page(
            rows,
            listing_identity=listing_identity,
            after=after,
        )
        yield bars
        if len(rows) < page_size:
            return


def resolve_spx_benchmark(
    *,
    cursor: Any,
    config: BenchmarkConfig,
) -> ResolvedBenchmark:
    """Resolve and validate the one frozen V1 Yahoo SPX benchmark row."""

    _validate_cursor(cursor)
    if not isinstance(config, BenchmarkConfig):
        raise TypeError("config must be a BenchmarkConfig.")

    cursor.execute(
        """
        SELECT
            provider_listing_id,
            provider_code,
            market,
            ticker,
            instrument_type_code,
            status,
            metadata
        FROM stonks.provider_listing
        WHERE provider_code = %s
          AND market = %s
          AND ticker = %s
        ORDER BY provider_listing_id
        LIMIT 2
        """,
        (config.provider_code, config.market, config.ticker),
    )
    rows = cursor.fetchall()
    if not rows:
        raise TechIndicatorsValidationError("SPX benchmark listing is missing.")
    if len(rows) != 1:
        raise TechIndicatorsValidationError("SPX benchmark listing is duplicated.")
    return _resolved_spx_benchmark(rows[0], config=config)


def load_spx_benchmark_history(
    *,
    cursor: Any,
    config: BenchmarkConfig,
    start_date: date | None = None,
    end_date: date | None = None,
    page_size: int = DEFAULT_SOURCE_READ_PAGE_SIZE,
) -> BenchmarkHistory:
    """Resolve SPX and load its exact stored OHLCV history through pages."""

    _validate_optional_date_range(start_date=start_date, end_date=end_date)
    benchmark = resolve_spx_benchmark(cursor=cursor, config=config)
    scope = TechIndicatorsScope(
        provider_listing_ids=(benchmark.provider_listing_id,),
        start_date=start_date,
        end_date=end_date,
    )
    bars = tuple(
        bar
        for page in iter_source_bar_pages(
            cursor=cursor,
            scope=scope,
            page_size=page_size,
        )
        for bar in page
    )
    return BenchmarkHistory(benchmark=benchmark, bars=bars)


_SOURCE_VALUE_ELIGIBILITY_SQL = """(
    (
        listing.provider_code = 'EODDATA'
        AND listing.market IN ('NYSE', 'NASDAQ', 'AMEX')
        AND jsonb_typeof(listing.metadata) = 'object'
        AND jsonb_typeof(listing.metadata -> 'type') = 'string'
        AND upper(btrim(listing.metadata ->> 'type')) = 'EQUITY'
    )
    OR (
        listing.provider_code = 'STOOQ'
        AND listing.market IN ('nasdaq', 'nyse', 'nysemkt')
    )
    OR (
        listing.provider_code = 'YAHOO'
        AND listing.market = 'XIDX'
        AND listing.ticker = 'SPX'
        AND listing.instrument_type_code = 'EQUITY_INDEX'
        AND jsonb_typeof(listing.metadata) = 'object'
        AND jsonb_typeof(listing.metadata -> 'YahooTicker') = 'string'
        AND listing.metadata ->> 'YahooTicker' = '^GSPC'
    )
)"""


def _eligible_listing(row: object) -> EligibleListing:
    if not isinstance(row, (tuple, list)) or len(row) != 9:
        raise ValueError("Eligible-listing query returned an invalid row.")
    try:
        return EligibleListing(
            provider_listing_id=row[0],
            provider_code=row[1],
            market=row[2],
            ticker=row[3],
            instrument_type_code=row[4],
            status=row[5],
            first_trading_date=row[6],
            last_trading_date=row[7],
            source_observation_count=row[8],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Eligible-listing query returned invalid contract data."
        ) from exc


def _source_bar_page(
    rows: object,
    *,
    listing_identity: dict[UUID, tuple[str, str, str]],
    after: tuple[UUID, date] | None,
) -> tuple[tuple[SourceBar, ...], tuple[UUID, date]]:
    if not isinstance(rows, list):
        raise ValueError("Source-bar query returned an invalid page.")

    bars: list[SourceBar] = []
    previous = after
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 10:
            raise ValueError("Source-bar query returned an invalid row.")
        provider_code, market, ticker, provider_listing_id, trading_date = row[:5]
        key = (provider_listing_id, trading_date)
        if (
            not isinstance(provider_listing_id, UUID)
            or listing_identity.get(provider_listing_id)
            != (provider_code, market, ticker)
            or type(trading_date) is not date
        ):
            raise ValueError("Source-bar query returned identity drift.")
        if previous is not None and key <= previous:
            raise ValueError("Source-bar query returned unordered rows.")
        try:
            bars.append(
                SourceBar(
                    provider_listing_id=provider_listing_id,
                    trading_date=trading_date,
                    open=row[5],
                    high=row[6],
                    low=row[7],
                    close=row[8],
                    volume=row[9],
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Source-bar query returned invalid OHLCV contract data."
            ) from exc
        previous = key

    if previous is None:
        raise ValueError("Source-bar query returned an empty page.")
    return tuple(bars), previous


def _resolved_spx_benchmark(
    row: object,
    *,
    config: BenchmarkConfig,
) -> ResolvedBenchmark:
    if not isinstance(row, (tuple, list)) or len(row) != 7:
        raise TechIndicatorsValidationError(
            "SPX benchmark query returned an invalid row."
        )
    (
        provider_listing_id,
        provider_code,
        market,
        ticker,
        instrument_type_code,
        status,
        metadata,
    ) = row
    if status != "ACTIVE":
        raise TechIndicatorsValidationError(
            "SPX benchmark listing must be ACTIVE."
        )
    if instrument_type_code != config.instrument_type_code:
        raise TechIndicatorsValidationError(
            "SPX benchmark instrument type has drifted."
        )
    if (
        not isinstance(metadata, dict)
        or not isinstance(metadata.get("YahooTicker"), str)
        or metadata["YahooTicker"] != config.yahoo_ticker
    ):
        raise TechIndicatorsValidationError(
            "SPX benchmark YahooTicker metadata has drifted."
        )
    try:
        return ResolvedBenchmark(
            provider_listing_id=provider_listing_id,
            provider_code=provider_code,
            market=market,
            ticker=ticker,
            instrument_type_code=instrument_type_code,
            status=status,
            yahoo_ticker=metadata["YahooTicker"],
        )
    except (TypeError, ValueError) as exc:
        raise TechIndicatorsValidationError(
            "SPX benchmark query returned invalid contract data."
        ) from exc


def _validate_cursor(cursor: Any) -> None:
    if not callable(getattr(cursor, "execute", None)) or not callable(
        getattr(cursor, "fetchall", None)
    ):
        raise TypeError("cursor must provide execute and fetchall methods.")


def _validate_page_size(page_size: object) -> None:
    if type(page_size) is not int:
        raise TypeError("page_size must be an integer.")
    if not MIN_SOURCE_READ_PAGE_SIZE <= page_size <= MAX_SOURCE_READ_PAGE_SIZE:
        raise ValueError(
            "page_size must be between "
            f"{MIN_SOURCE_READ_PAGE_SIZE} and {MAX_SOURCE_READ_PAGE_SIZE}."
        )


def _validate_optional_date_range(
    *,
    start_date: object,
    end_date: object,
) -> None:
    if (start_date is None) != (end_date is None):
        raise ValueError("start_date and end_date must be provided together.")
    if start_date is None and end_date is None:
        return
    if type(start_date) is not date or type(end_date) is not date:
        raise TypeError("start_date and end_date must be dates or None.")
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date.")


def _date_to_string(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


__all__ = [
    "BenchmarkHistory",
    "EligibleListing",
    "iter_source_bar_pages",
    "load_spx_benchmark_history",
    "resolve_spx_benchmark",
    "select_eligible_listings",
]
