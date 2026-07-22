"""Provider-native daily market analysis for persisted EODData equities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from empire_stonks_ohlcv.config import DEFAULT_EODDATA_EXCHANGES
from empire_stonks_ohlcv.daily_market_baskets import DAILY_MARKET_BASKETS
from empire_stonks_ohlcv.eoddata import EODDATA_PROVIDER_CODE


TOP_MOVER_LIMIT = 12
TOP_VOLUME_LIMIT = 12
PRICE_ANOMALY_LIMIT = 40
VOLUME_ANOMALY_LIMIT = 40
HIGH_VOLUME_LOW_MOVEMENT_LIMIT = 12
LOW_MOVEMENT_MAX_ABS_RETURN = Decimal("0.005")


@dataclass(frozen=True, slots=True)
class DailyMarketUniverse:
    """Counts describing the provider rows and reportable equity subset."""

    source_bar_count: int
    equity_bar_count: int
    non_equity_bar_count: int
    unclassified_bar_count: int


@dataclass(frozen=True, slots=True)
class MarketBreadth:
    """One exchange's daily equity direction and volume summary."""

    market: str
    equity_count: int
    comparable_count: int
    advancers: int
    decliners: int
    unchanged: int
    missing_comparison: int
    total_volume: Decimal
    average_return: Decimal | None


@dataclass(frozen=True, slots=True)
class MoveBucket:
    """One close-to-close return distribution bucket."""

    label: str
    nyse_count: int
    nasdaq_count: int
    amex_count: int

    @property
    def total_count(self) -> int:
        return self.nyse_count + self.nasdaq_count + self.amex_count


@dataclass(frozen=True, slots=True)
class DailyEquityRow:
    """Display-ready identity and daily values for one EODData equity."""

    market: str
    ticker: str
    name: str
    currency: str | None
    close: Decimal
    change: Decimal | None
    changepct: Decimal | None
    volume: Decimal | None


@dataclass(frozen=True, slots=True)
class HighVolumeLowMovementRow:
    """One heavily traded equity with a small close-to-close return."""

    market: str
    ticker: str
    name: str
    currency: str | None
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    change: Decimal
    changepct: Decimal
    volume: Decimal


@dataclass(frozen=True, slots=True)
class DailyMarketBasketSnapshot:
    """Available EODData rows for one configured report basket."""

    code: str
    title: str
    membership_version: str
    configured_count: int
    rows: tuple[DailyEquityRow, ...]
    missing_tickers: tuple[str, ...]

    @property
    def available_count(self) -> int:
        return len(self.rows)

    @property
    def comparable_count(self) -> int:
        return sum(row.changepct is not None for row in self.rows)


@dataclass(frozen=True, slots=True)
class PriceAnomaly:
    """One large close-to-close or intraday price movement."""

    market: str
    ticker: str
    name: str
    anomaly_type: str
    close: Decimal
    changepct: Decimal | None
    intraday_range_pct: Decimal | None
    volume: Decimal | None


@dataclass(frozen=True, slots=True)
class VolumeAnomaly:
    """One equity whose volume is unusually high versus its prior 20 bars."""

    market: str
    ticker: str
    name: str
    volume: Decimal
    average_volume_20d: Decimal
    volume_multiple: Decimal
    changepct: Decimal | None


@dataclass(frozen=True, slots=True)
class EODDataDailyMarketReport:
    """Complete data model for one provider-native daily market PDF."""

    trading_date: date
    generated_at: datetime
    universe: DailyMarketUniverse
    breadth: tuple[MarketBreadth, ...]
    move_buckets: tuple[MoveBucket, ...]
    winners: tuple[DailyEquityRow, ...]
    losers: tuple[DailyEquityRow, ...]
    volume_leaders: tuple[DailyEquityRow, ...]
    price_anomalies: tuple[PriceAnomaly, ...]
    volume_anomalies: tuple[VolumeAnomaly, ...]
    baskets: tuple[DailyMarketBasketSnapshot, ...] = ()
    high_volume_low_movement: tuple[HighVolumeLowMovementRow, ...] = ()

    def __post_init__(self) -> None:
        if type(self.trading_date) is not date:
            raise TypeError("trading_date must be a date.")
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware.")
        if tuple(item.market for item in self.breadth) != (
            DEFAULT_EODDATA_EXCHANGES
        ):
            raise ValueError("breadth must contain NYSE, NASDAQ, and AMEX in order.")
        if len({basket.code for basket in self.baskets}) != len(self.baskets):
            raise ValueError("basket codes must be unique.")

    def basket(self, code: str) -> DailyMarketBasketSnapshot | None:
        """Return one configured basket snapshot by code."""

        normalized = code.strip().upper()
        return next(
            (basket for basket in self.baskets if basket.code == normalized),
            None,
        )

    @property
    def comparable_count(self) -> int:
        return sum(item.comparable_count for item in self.breadth)

    @property
    def advancers(self) -> int:
        return sum(item.advancers for item in self.breadth)

    @property
    def decliners(self) -> int:
        return sum(item.decliners for item in self.breadth)

    @property
    def unchanged(self) -> int:
        return sum(item.unchanged for item in self.breadth)

    @property
    def missing_comparison(self) -> int:
        return sum(item.missing_comparison for item in self.breadth)

    @property
    def total_volume(self) -> Decimal:
        return sum((item.total_volume for item in self.breadth), Decimal(0))


def build_eoddata_daily_market_report(
    *,
    cursor: Any,
    trading_date: date,
    generated_at: datetime | None = None,
) -> EODDataDailyMarketReport:
    """Query persisted EODData equities and build one date-scoped report model."""

    if type(trading_date) is not date:
        raise TypeError("trading_date must be a date.")
    generated = generated_at or datetime.now(UTC)
    if generated.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware.")

    return EODDataDailyMarketReport(
        trading_date=trading_date,
        generated_at=generated,
        universe=_select_universe(cursor=cursor, trading_date=trading_date),
        breadth=_select_breadth(cursor=cursor, trading_date=trading_date),
        move_buckets=_select_move_buckets(
            cursor=cursor,
            trading_date=trading_date,
        ),
        winners=_select_ranked_equities(
            cursor=cursor,
            trading_date=trading_date,
            direction="DESC",
            limit=TOP_MOVER_LIMIT,
        ),
        losers=_select_ranked_equities(
            cursor=cursor,
            trading_date=trading_date,
            direction="ASC",
            limit=TOP_MOVER_LIMIT,
        ),
        volume_leaders=_select_volume_leaders(
            cursor=cursor,
            trading_date=trading_date,
            limit=TOP_VOLUME_LIMIT,
        ),
        price_anomalies=_select_price_anomalies(
            cursor=cursor,
            trading_date=trading_date,
            limit=PRICE_ANOMALY_LIMIT,
        ),
        volume_anomalies=_select_volume_anomalies(
            cursor=cursor,
            trading_date=trading_date,
            limit=VOLUME_ANOMALY_LIMIT,
        ),
        baskets=tuple(
            _select_basket_snapshot(
                cursor=cursor,
                trading_date=trading_date,
                code=spec.code,
                title=spec.title,
                membership_version=spec.membership_version,
                tickers=spec.tickers,
                preferred_market=spec.preferred_market,
            )
            for spec in DAILY_MARKET_BASKETS
        ),
        high_volume_low_movement=_select_high_volume_low_movement(
            cursor=cursor,
            trading_date=trading_date,
            limit=HIGH_VOLUME_LOW_MOVEMENT_LIMIT,
            max_abs_return=LOW_MOVEMENT_MAX_ABS_RETURN,
        ),
    )


def _select_high_volume_low_movement(
    *,
    cursor: Any,
    trading_date: date,
    limit: int,
    max_abs_return: Decimal,
) -> tuple[HighVolumeLowMovementRow, ...]:
    cursor.execute(
        """
        /* empire_daily_market:high_volume_low_movement */
        WITH ranked AS (
            SELECT
                listing.market,
                listing.ticker,
                coalesce(nullif(btrim(listing.name), ''), listing.ticker) AS name,
                listing.metadata ->> 'currency' AS currency,
                daily.open,
                daily.high,
                daily.low,
                daily.close,
                daily.change,
                daily.changepct,
                daily.volume,
                row_number() OVER (
                    PARTITION BY listing.market
                    ORDER BY
                        daily.volume DESC,
                        abs(daily.changepct),
                        listing.ticker
                ) AS market_rank
            FROM stonks.ohlcv_daily AS daily
            JOIN stonks.provider_listing AS listing
              USING (provider_listing_id)
            WHERE listing.provider_code = %s
              AND daily.trading_date = %s
              AND daily.close > 0
              AND daily.volume IS NOT NULL
              AND daily.changepct IS NOT NULL
              AND abs(daily.changepct) <= %s
              AND upper(coalesce(listing.metadata ->> 'type', '')) = 'EQUITY'
        )
        SELECT
            market,
            ticker,
            name,
            currency,
            open,
            high,
            low,
            close,
            change,
            changepct,
            volume
        FROM ranked
        WHERE market_rank <= %s
        ORDER BY array_position(%s::text[], market), market_rank
        """,
        (
            EODDATA_PROVIDER_CODE,
            trading_date,
            max_abs_return,
            limit,
            list(DEFAULT_EODDATA_EXCHANGES),
        ),
    )
    return tuple(
        HighVolumeLowMovementRow(
            market=str(row[0]),
            ticker=str(row[1]),
            name=str(row[2]),
            currency=None if row[3] is None else str(row[3]),
            open=_decimal(row[4]),
            high=_decimal(row[5]),
            low=_decimal(row[6]),
            close=_decimal(row[7]),
            change=_decimal(row[8]),
            changepct=_decimal(row[9]),
            volume=_decimal(row[10]),
        )
        for row in cursor.fetchall()
    )


def _select_basket_snapshot(
    *,
    cursor: Any,
    trading_date: date,
    code: str,
    title: str,
    membership_version: str,
    tickers: tuple[str, ...],
    preferred_market: str | None,
) -> DailyMarketBasketSnapshot:
    cursor.execute(
        """
        /* empire_daily_market:basket */
        WITH configured AS (
            SELECT ticker, ordinality
            FROM unnest(%s::text[]) WITH ORDINALITY AS item(ticker, ordinality)
        )
        SELECT
            selected.market,
            configured.ticker,
            selected.name,
            selected.currency,
            selected.close,
            selected.change,
            selected.changepct,
            selected.volume
        FROM configured
        JOIN LATERAL (
            SELECT
                listing.market,
                coalesce(nullif(btrim(listing.name), ''), listing.ticker) AS name,
                listing.metadata ->> 'currency' AS currency,
                daily.close,
                daily.change,
                daily.changepct,
                daily.volume
            FROM stonks.provider_listing AS listing
            JOIN stonks.ohlcv_daily AS daily
              USING (provider_listing_id)
            WHERE listing.provider_code = %s
              AND listing.ticker = configured.ticker
              AND daily.trading_date = %s
              AND upper(coalesce(listing.metadata ->> 'type', '')) = 'EQUITY'
            ORDER BY
                CASE WHEN listing.market = %s THEN 0 ELSE 1 END,
                listing.provider_listing_id
            LIMIT 1
        ) AS selected ON TRUE
        ORDER BY configured.ordinality
        """,
        (list(tickers), EODDATA_PROVIDER_CODE, trading_date, preferred_market),
    )
    rows = tuple(_daily_equity_row(row) for row in cursor.fetchall())
    available = {row.ticker for row in rows}
    return DailyMarketBasketSnapshot(
        code=code,
        title=title,
        membership_version=membership_version,
        configured_count=len(tickers),
        rows=rows,
        missing_tickers=tuple(ticker for ticker in tickers if ticker not in available),
    )


def _select_universe(*, cursor: Any, trading_date: date) -> DailyMarketUniverse:
    cursor.execute(
        """
        /* empire_daily_market:universe */
        SELECT
            count(*) AS source_bar_count,
            count(*) FILTER (
                WHERE upper(coalesce(listing.metadata ->> 'type', '')) = 'EQUITY'
            ) AS equity_bar_count,
            count(*) FILTER (
                WHERE coalesce(listing.metadata ->> 'type', '') <> ''
                  AND upper(listing.metadata ->> 'type') <> 'EQUITY'
            ) AS non_equity_bar_count,
            count(*) FILTER (
                WHERE coalesce(listing.metadata ->> 'type', '') = ''
            ) AS unclassified_bar_count
        FROM stonks.ohlcv_daily AS daily
        JOIN stonks.provider_listing AS listing
          USING (provider_listing_id)
        WHERE listing.provider_code = %s
          AND daily.trading_date = %s
        """,
        (EODDATA_PROVIDER_CODE, trading_date),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Daily market universe query returned no aggregate row.")
    return DailyMarketUniverse(*(int(value or 0) for value in row))


def _select_breadth(
    *,
    cursor: Any,
    trading_date: date,
) -> tuple[MarketBreadth, ...]:
    cursor.execute(
        """
        /* empire_daily_market:breadth */
        SELECT
            listing.market,
            count(*) AS equity_count,
            count(daily.changepct) AS comparable_count,
            count(*) FILTER (WHERE daily.changepct > 0) AS advancers,
            count(*) FILTER (WHERE daily.changepct < 0) AS decliners,
            count(*) FILTER (WHERE daily.changepct = 0) AS unchanged,
            count(*) FILTER (WHERE daily.changepct IS NULL) AS missing_comparison,
            coalesce(sum(daily.volume), 0) AS total_volume,
            avg(daily.changepct) AS average_return
        FROM stonks.ohlcv_daily AS daily
        JOIN stonks.provider_listing AS listing
          USING (provider_listing_id)
        WHERE listing.provider_code = %s
          AND daily.trading_date = %s
          AND upper(coalesce(listing.metadata ->> 'type', '')) = 'EQUITY'
        GROUP BY listing.market
        ORDER BY array_position(%s::text[], listing.market)
        """,
        (EODDATA_PROVIDER_CODE, trading_date, list(DEFAULT_EODDATA_EXCHANGES)),
    )
    by_market = {
        str(row[0]): MarketBreadth(
            market=str(row[0]),
            equity_count=int(row[1] or 0),
            comparable_count=int(row[2] or 0),
            advancers=int(row[3] or 0),
            decliners=int(row[4] or 0),
            unchanged=int(row[5] or 0),
            missing_comparison=int(row[6] or 0),
            total_volume=_decimal(row[7]),
            average_return=None if row[8] is None else _decimal(row[8]),
        )
        for row in cursor.fetchall()
    }
    return tuple(
        by_market.get(
            market,
            MarketBreadth(
                market=market,
                equity_count=0,
                comparable_count=0,
                advancers=0,
                decliners=0,
                unchanged=0,
                missing_comparison=0,
                total_volume=Decimal(0),
                average_return=None,
            ),
        )
        for market in DEFAULT_EODDATA_EXCHANGES
    )


def _select_move_buckets(
    *,
    cursor: Any,
    trading_date: date,
) -> tuple[MoveBucket, ...]:
    cursor.execute(
        """
        /* empire_daily_market:move_buckets */
        WITH bucketed AS (
            SELECT
                listing.market,
                CASE
                    WHEN daily.changepct <= -0.10 THEN 'Down 10%%+'
                    WHEN daily.changepct <= -0.05 THEN 'Down 5-10%%'
                    WHEN daily.changepct <= -0.02 THEN 'Down 2-5%%'
                    WHEN daily.changepct < 0 THEN 'Down 0-2%%'
                    WHEN daily.changepct = 0 THEN 'Unchanged'
                    WHEN daily.changepct < 0.02 THEN 'Up 0-2%%'
                    WHEN daily.changepct < 0.05 THEN 'Up 2-5%%'
                    WHEN daily.changepct < 0.10 THEN 'Up 5-10%%'
                    ELSE 'Up 10%%+'
                END AS bucket_label,
                CASE
                    WHEN daily.changepct <= -0.10 THEN 1
                    WHEN daily.changepct <= -0.05 THEN 2
                    WHEN daily.changepct <= -0.02 THEN 3
                    WHEN daily.changepct < 0 THEN 4
                    WHEN daily.changepct = 0 THEN 5
                    WHEN daily.changepct < 0.02 THEN 6
                    WHEN daily.changepct < 0.05 THEN 7
                    WHEN daily.changepct < 0.10 THEN 8
                    ELSE 9
                END AS bucket_order
            FROM stonks.ohlcv_daily AS daily
            JOIN stonks.provider_listing AS listing
              USING (provider_listing_id)
            WHERE listing.provider_code = %s
              AND daily.trading_date = %s
              AND daily.changepct IS NOT NULL
              AND upper(coalesce(listing.metadata ->> 'type', '')) = 'EQUITY'
        )
        SELECT
            bucket_label,
            count(*) FILTER (WHERE market = 'NYSE') AS nyse_count,
            count(*) FILTER (WHERE market = 'NASDAQ') AS nasdaq_count,
            count(*) FILTER (WHERE market = 'AMEX') AS amex_count
        FROM bucketed
        GROUP BY bucket_label, bucket_order
        ORDER BY bucket_order
        """,
        (EODDATA_PROVIDER_CODE, trading_date),
    )
    return tuple(
        MoveBucket(
            label=str(row[0]),
            nyse_count=int(row[1] or 0),
            nasdaq_count=int(row[2] or 0),
            amex_count=int(row[3] or 0),
        )
        for row in cursor.fetchall()
    )


def _select_ranked_equities(
    *,
    cursor: Any,
    trading_date: date,
    direction: str,
    limit: int,
) -> tuple[DailyEquityRow, ...]:
    if direction not in {"ASC", "DESC"}:
        raise ValueError("direction must be ASC or DESC.")
    comparison = ">" if direction == "DESC" else "<"
    cursor.execute(
        f"""
        /* empire_daily_market:movers_{direction.lower()} */
        WITH ranked AS (
            SELECT
                listing.market,
                listing.ticker,
                coalesce(nullif(btrim(listing.name), ''), listing.ticker) AS name,
                listing.metadata ->> 'currency' AS currency,
                daily.close,
                daily.change,
                daily.changepct,
                daily.volume,
                row_number() OVER (
                    PARTITION BY listing.market
                    ORDER BY daily.changepct {direction}, listing.ticker
                ) AS market_rank
            FROM stonks.ohlcv_daily AS daily
            JOIN stonks.provider_listing AS listing
              USING (provider_listing_id)
            WHERE listing.provider_code = %s
              AND daily.trading_date = %s
              AND daily.changepct IS NOT NULL
              AND daily.changepct {comparison} 0
              AND upper(coalesce(listing.metadata ->> 'type', '')) = 'EQUITY'
        )
        SELECT market, ticker, name, currency, close, change, changepct, volume
        FROM ranked
        WHERE market_rank <= %s
        ORDER BY array_position(%s::text[], market), market_rank
        """,
        (
            EODDATA_PROVIDER_CODE,
            trading_date,
            limit,
            list(DEFAULT_EODDATA_EXCHANGES),
        ),
    )
    return tuple(_daily_equity_row(row) for row in cursor.fetchall())


def _select_volume_leaders(
    *,
    cursor: Any,
    trading_date: date,
    limit: int,
) -> tuple[DailyEquityRow, ...]:
    cursor.execute(
        """
        /* empire_daily_market:volume_leaders */
        WITH ranked AS (
            SELECT
                listing.market,
                listing.ticker,
                coalesce(nullif(btrim(listing.name), ''), listing.ticker) AS name,
                listing.metadata ->> 'currency' AS currency,
                daily.close,
                daily.change,
                daily.changepct,
                daily.volume,
                row_number() OVER (
                    PARTITION BY listing.market
                    ORDER BY daily.volume DESC NULLS LAST, listing.ticker
                ) AS market_rank
            FROM stonks.ohlcv_daily AS daily
            JOIN stonks.provider_listing AS listing
              USING (provider_listing_id)
            WHERE listing.provider_code = %s
              AND daily.trading_date = %s
              AND daily.volume IS NOT NULL
              AND upper(coalesce(listing.metadata ->> 'type', '')) = 'EQUITY'
        )
        SELECT market, ticker, name, currency, close, change, changepct, volume
        FROM ranked
        WHERE market_rank <= %s
        ORDER BY array_position(%s::text[], market), market_rank
        """,
        (
            EODDATA_PROVIDER_CODE,
            trading_date,
            limit,
            list(DEFAULT_EODDATA_EXCHANGES),
        ),
    )
    return tuple(_daily_equity_row(row) for row in cursor.fetchall())


def _select_price_anomalies(
    *,
    cursor: Any,
    trading_date: date,
    limit: int,
) -> tuple[PriceAnomaly, ...]:
    cursor.execute(
        """
        /* empire_daily_market:price_anomalies */
        WITH candidates AS (
            SELECT
                listing.market,
                listing.ticker,
                coalesce(nullif(btrim(listing.name), ''), listing.ticker) AS name,
                daily.close,
                daily.changepct,
                CASE
                    WHEN daily.low = 0 THEN NULL
                    ELSE (daily.high - daily.low) / daily.low
                END AS intraday_range_pct,
                daily.volume
            FROM stonks.ohlcv_daily AS daily
            JOIN stonks.provider_listing AS listing
              USING (provider_listing_id)
            WHERE listing.provider_code = %s
              AND daily.trading_date = %s
              AND upper(coalesce(listing.metadata ->> 'type', '')) = 'EQUITY'
        ), flagged AS (
            SELECT
                *,
                CASE
                    WHEN abs(changepct) > 1.00 THEN 'POSSIBLE CORPORATE ACTION'
                    WHEN changepct > 0.30 THEN 'EXTREME UP MOVE'
                    WHEN changepct < -0.30 THEN 'EXTREME DOWN MOVE'
                    WHEN intraday_range_pct > 0.50 THEN 'UNUSUAL TRADING RANGE'
                    ELSE NULL
                END AS anomaly_type,
                greatest(
                    coalesce(abs(changepct), 0),
                    coalesce(intraday_range_pct, 0)
                ) AS severity
            FROM candidates
        )
        SELECT
            market,
            ticker,
            name,
            anomaly_type,
            close,
            changepct,
            intraday_range_pct,
            volume
        FROM flagged
        WHERE anomaly_type IS NOT NULL
        ORDER BY severity DESC, market, ticker
        LIMIT %s
        """,
        (EODDATA_PROVIDER_CODE, trading_date, limit),
    )
    return tuple(
        PriceAnomaly(
            market=str(row[0]),
            ticker=str(row[1]),
            name=str(row[2]),
            anomaly_type=str(row[3]),
            close=_decimal(row[4]),
            changepct=None if row[5] is None else _decimal(row[5]),
            intraday_range_pct=None if row[6] is None else _decimal(row[6]),
            volume=None if row[7] is None else _decimal(row[7]),
        )
        for row in cursor.fetchall()
    )


def _select_volume_anomalies(
    *,
    cursor: Any,
    trading_date: date,
    limit: int,
) -> tuple[VolumeAnomaly, ...]:
    cursor.execute(
        """
        /* empire_daily_market:volume_anomalies */
        WITH history AS (
            SELECT
                listing.provider_listing_id,
                listing.market,
                listing.ticker,
                coalesce(nullif(btrim(listing.name), ''), listing.ticker) AS name,
                daily.trading_date,
                daily.volume,
                daily.changepct,
                count(daily.volume) OVER (
                    PARTITION BY listing.provider_listing_id
                    ORDER BY daily.trading_date
                    ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                ) AS lookback_count,
                avg(daily.volume) OVER (
                    PARTITION BY listing.provider_listing_id
                    ORDER BY daily.trading_date
                    ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                ) AS average_volume_20d
            FROM stonks.ohlcv_daily AS daily
            JOIN stonks.provider_listing AS listing
              USING (provider_listing_id)
            WHERE listing.provider_code = %s
              AND daily.trading_date <= %s
              AND upper(coalesce(listing.metadata ->> 'type', '')) = 'EQUITY'
        ), candidates AS (
            SELECT
                *,
                volume / nullif(average_volume_20d, 0) AS volume_multiple
            FROM history
            WHERE trading_date = %s
              AND volume IS NOT NULL
              AND lookback_count >= 20
        )
        SELECT
            market,
            ticker,
            name,
            volume,
            average_volume_20d,
            volume_multiple,
            changepct
        FROM candidates
        WHERE volume_multiple >= 5
          AND (volume_multiple > 10 OR volume >= 1000000)
        ORDER BY volume_multiple DESC, market, ticker
        LIMIT %s
        """,
        (EODDATA_PROVIDER_CODE, trading_date, trading_date, limit),
    )
    return tuple(
        VolumeAnomaly(
            market=str(row[0]),
            ticker=str(row[1]),
            name=str(row[2]),
            volume=_decimal(row[3]),
            average_volume_20d=_decimal(row[4]),
            volume_multiple=_decimal(row[5]),
            changepct=None if row[6] is None else _decimal(row[6]),
        )
        for row in cursor.fetchall()
    )


def _daily_equity_row(row: tuple[Any, ...]) -> DailyEquityRow:
    return DailyEquityRow(
        market=str(row[0]),
        ticker=str(row[1]),
        name=str(row[2]),
        currency=None if row[3] is None else str(row[3]),
        close=_decimal(row[4]),
        change=None if row[5] is None else _decimal(row[5]),
        changepct=None if row[6] is None else _decimal(row[6]),
        volume=None if row[7] is None else _decimal(row[7]),
    )


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))
