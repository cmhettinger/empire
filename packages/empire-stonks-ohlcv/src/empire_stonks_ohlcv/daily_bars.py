"""Transactional current-state persistence for provider-native daily bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any, Iterable
from uuid import UUID

from empire_stonks_ohlcv.exceptions import OHLCVPersistenceError
from empire_stonks_ohlcv.models import DailyBar
from empire_stonks_ohlcv.results import PersistenceCounts


_PRICE_SCALE = Decimal("0.0000000001")
_DERIVED_SCALE = Decimal("0.00000001")
_PRICE_INTEGER_DIGITS = 20
_VOLUME_INTEGER_DIGITS = 22


@dataclass(frozen=True)
class DailyBarWriteInput:
    """One validated provider bar associated with its resolved listing UUID."""

    provider_listing_id: UUID
    bar: DailyBar

    def __post_init__(self) -> None:
        if not isinstance(self.provider_listing_id, UUID):
            raise TypeError("provider_listing_id must be a UUID.")
        if not isinstance(self.bar, DailyBar):
            raise TypeError("bar must be a DailyBar.")


@dataclass(frozen=True)
class _SourceValues:
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None


@dataclass(frozen=True)
class _DerivedValues:
    change: Decimal | None
    changepct: Decimal | None
    typ: Decimal
    hl_range: Decimal
    oc_range: Decimal


@dataclass(frozen=True)
class _StoredDailyBar:
    source: _SourceValues
    derived: _DerivedValues


def upsert_daily_bars(
    *,
    cursor: Any,
    bars: Iterable[DailyBarWriteInput],
) -> PersistenceCounts:
    """Write current provider values and repair affected derived values.

    The caller owns the transaction and must roll it back if this helper raises.
    The helper locks provider listings in deterministic UUID order and never
    commits independently.
    """

    prepared = _prepare_inputs(bars)
    if not prepared:
        return PersistenceCounts()

    listing_ids = tuple(
        sorted({item.provider_listing_id for item in prepared}, key=str)
    )
    coverage = _lock_listings(cursor=cursor, provider_listing_ids=listing_ids)
    stored_by_listing = {
        provider_listing_id: _load_stored_bars(
            cursor=cursor,
            provider_listing_id=provider_listing_id,
        )
        for provider_listing_id in listing_ids
    }
    final_by_listing = {
        provider_listing_id: dict(stored)
        for provider_listing_id, stored in stored_by_listing.items()
    }

    classifications: dict[tuple[UUID, date], str] = {}
    for item in prepared:
        key = (item.provider_listing_id, item.bar.trading_date)
        source = _stored_source_values(item.bar)
        existing = stored_by_listing[item.provider_listing_id].get(
            item.bar.trading_date
        )
        classifications[key] = (
            "inserted"
            if existing is None
            else "unchanged"
            if existing.source == source
            else "updated"
        )
        final_by_listing[item.provider_listing_id][
            item.bar.trading_date
        ] = _StoredDailyBar(
            source=source,
            derived=(
                existing.derived
                if existing is not None
                else _empty_derived_values()
            ),
        )

    recalculate: dict[UUID, set[date]] = {
        provider_listing_id: set() for provider_listing_id in listing_ids
    }
    for item in prepared:
        provider_listing_id = item.provider_listing_id
        trading_date = item.bar.trading_date
        recalculate[provider_listing_id].add(trading_date)
        if classifications[(provider_listing_id, trading_date)] in {
            "inserted",
            "updated",
        }:
            successor = _successor_date(
                final_by_listing[provider_listing_id],
                trading_date,
            )
            if successor is not None:
                recalculate[provider_listing_id].add(successor)

    inserted = 0
    updated = 0
    unchanged = 0
    derived_updated = 0
    for provider_listing_id in listing_ids:
        final_series = final_by_listing[provider_listing_id]
        stored_series = stored_by_listing[provider_listing_id]
        for trading_date in sorted(recalculate[provider_listing_id]):
            final_bar = final_series[trading_date]
            derived = _derived_values(final_series, trading_date)
            final_series[trading_date] = _StoredDailyBar(
                source=final_bar.source,
                derived=derived,
            )
            key = (provider_listing_id, trading_date)
            classification = classifications.get(key)
            existing = stored_series.get(trading_date)
            if classification == "inserted":
                _insert_daily_bar(
                    cursor=cursor,
                    provider_listing_id=provider_listing_id,
                    trading_date=trading_date,
                    stored=final_series[trading_date],
                )
                inserted += 1
            elif classification == "updated":
                _update_daily_bar_source_and_derived(
                    cursor=cursor,
                    provider_listing_id=provider_listing_id,
                    trading_date=trading_date,
                    stored=final_series[trading_date],
                )
                updated += 1
            elif classification == "unchanged":
                unchanged += 1
                if existing is not None and existing.derived != derived:
                    _update_daily_bar_derived(
                        cursor=cursor,
                        provider_listing_id=provider_listing_id,
                        trading_date=trading_date,
                        derived=derived,
                    )
                    derived_updated += 1
            elif existing is not None and existing.derived != derived:
                _update_daily_bar_derived(
                    cursor=cursor,
                    provider_listing_id=provider_listing_id,
                    trading_date=trading_date,
                    derived=derived,
                )
                derived_updated += 1

        _update_listing_coverage(
            cursor=cursor,
            provider_listing_id=provider_listing_id,
            current_coverage=coverage[provider_listing_id],
            input_dates=[
                item.bar.trading_date
                for item in prepared
                if item.provider_listing_id == provider_listing_id
            ],
        )

    return PersistenceCounts(
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        derived_updated=derived_updated,
    )


def _prepare_inputs(
    bars: Iterable[DailyBarWriteInput],
) -> tuple[DailyBarWriteInput, ...]:
    prepared = tuple(bars)
    seen: set[tuple[UUID, date]] = set()
    for item in prepared:
        if not isinstance(item, DailyBarWriteInput):
            raise TypeError("bars must contain only DailyBarWriteInput records.")
        key = (item.provider_listing_id, item.bar.trading_date)
        if key in seen:
            raise OHLCVPersistenceError(
                "Duplicate daily-bar identity in one writer call: "
                f"{item.provider_listing_id}/{item.bar.trading_date.isoformat()}."
            )
        seen.add(key)
    return tuple(
        sorted(
            prepared,
            key=lambda item: (str(item.provider_listing_id), item.bar.trading_date),
        )
    )


def _lock_listings(
    *,
    cursor: Any,
    provider_listing_ids: Iterable[UUID],
) -> dict[UUID, tuple[date | None, date | None]]:
    locked: dict[UUID, tuple[date | None, date | None]] = {}
    for provider_listing_id in provider_listing_ids:
        cursor.execute(
            """
            SELECT provider_listing_id, first_seen, last_seen, status
            FROM stonks.provider_listing
            WHERE provider_listing_id = %s
            FOR UPDATE
            """,
            (provider_listing_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise OHLCVPersistenceError(
                "Provider listing does not exist and cannot be locked for daily bars."
            )
        if row[3] != "ACTIVE":
            raise OHLCVPersistenceError(
                "Provider listing is inactive and cannot accept daily bars: "
                f"{provider_listing_id}."
            )
        locked[row[0]] = (row[1], row[2])
    return locked


def _load_stored_bars(
    *,
    cursor: Any,
    provider_listing_id: UUID,
) -> dict[date, _StoredDailyBar]:
    cursor.execute(
        """
        SELECT
            trading_date,
            open,
            high,
            low,
            close,
            volume,
            change,
            changepct,
            typ,
            hl_range,
            oc_range
        FROM stonks.ohlcv_daily
        WHERE provider_listing_id = %s
        ORDER BY trading_date
        """,
        (provider_listing_id,),
    )
    return {
        row[0]: _StoredDailyBar(
            source=_SourceValues(
                open=row[1],
                high=row[2],
                low=row[3],
                close=row[4],
                volume=row[5],
            ),
            derived=_DerivedValues(
                change=row[6],
                changepct=row[7],
                typ=row[8],
                hl_range=row[9],
                oc_range=row[10],
            ),
        )
        for row in cursor.fetchall()
    }


def _stored_source_values(bar: DailyBar) -> _SourceValues:
    return _SourceValues(
        open=_to_database_scale(
            bar.open,
            scale=_PRICE_SCALE,
            integer_digits=_PRICE_INTEGER_DIGITS,
        ),
        high=_to_database_scale(
            bar.high,
            scale=_PRICE_SCALE,
            integer_digits=_PRICE_INTEGER_DIGITS,
        ),
        low=_to_database_scale(
            bar.low,
            scale=_PRICE_SCALE,
            integer_digits=_PRICE_INTEGER_DIGITS,
        ),
        close=_to_database_scale(
            bar.close,
            scale=_PRICE_SCALE,
            integer_digits=_PRICE_INTEGER_DIGITS,
        ),
        volume=(
            None
            if bar.volume is None
            else _to_database_scale(
                bar.volume,
                scale=_DERIVED_SCALE,
                integer_digits=_VOLUME_INTEGER_DIGITS,
            )
        ),
    )


def _to_database_scale(
    value: Decimal,
    *,
    scale: Decimal,
    integer_digits: int,
) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = 60
            rounded = value.quantize(scale, rounding=ROUND_HALF_UP)
    except InvalidOperation as error:
        raise OHLCVPersistenceError(
            "Daily-bar value cannot be rounded to database scale."
        ) from error
    if rounded and rounded.adjusted() >= integer_digits:
        raise OHLCVPersistenceError(
            "Daily-bar value exceeds database numeric precision."
        )
    return rounded


def _empty_derived_values() -> _DerivedValues:
    return _DerivedValues(
        change=None,
        changepct=None,
        typ=Decimal(0),
        hl_range=Decimal(0),
        oc_range=Decimal(0),
    )


def _successor_date(
    series: dict[date, _StoredDailyBar],
    trading_date: date,
) -> date | None:
    return next(
        (candidate for candidate in sorted(series) if candidate > trading_date),
        None,
    )


def _derived_values(
    series: dict[date, _StoredDailyBar],
    trading_date: date,
) -> _DerivedValues:
    current = series[trading_date].source
    predecessor = next(
        (
            series[candidate].source
            for candidate in sorted(series, reverse=True)
            if candidate < trading_date
        ),
        None,
    )
    raw_change = None if predecessor is None else current.close - predecessor.close
    return _DerivedValues(
        change=None if raw_change is None else _to_derived_scale(raw_change),
        changepct=(
            None
            if raw_change is None or predecessor.close == 0
            else _to_derived_scale(raw_change / predecessor.close)
        ),
        typ=_to_derived_scale(
            (current.high + current.low + current.close) / Decimal(3)
        ),
        hl_range=_to_derived_scale(current.high - current.low),
        oc_range=_to_derived_scale(current.close - current.open),
    )


def _to_derived_scale(value: Decimal) -> Decimal:
    return _to_database_scale(
        value,
        scale=_DERIVED_SCALE,
        integer_digits=_VOLUME_INTEGER_DIGITS,
    )


def _insert_daily_bar(
    *,
    cursor: Any,
    provider_listing_id: UUID,
    trading_date: date,
    stored: _StoredDailyBar,
) -> None:
    cursor.execute(
        """
        INSERT INTO stonks.ohlcv_daily (
            provider_listing_id,
            trading_date,
            open,
            high,
            low,
            close,
            volume,
            change,
            changepct,
            typ,
            hl_range,
            oc_range
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        _daily_bar_values(provider_listing_id, trading_date, stored),
    )


def _update_daily_bar_source_and_derived(
    *,
    cursor: Any,
    provider_listing_id: UUID,
    trading_date: date,
    stored: _StoredDailyBar,
) -> None:
    cursor.execute(
        """
        UPDATE stonks.ohlcv_daily
        SET
            open = %s,
            high = %s,
            low = %s,
            close = %s,
            volume = %s,
            change = %s,
            changepct = %s,
            typ = %s,
            hl_range = %s,
            oc_range = %s,
            updated_at = now()
        WHERE provider_listing_id = %s
          AND trading_date = %s
        """,
        (*_source_and_derived_values(stored), provider_listing_id, trading_date),
    )


def _update_daily_bar_derived(
    *,
    cursor: Any,
    provider_listing_id: UUID,
    trading_date: date,
    derived: _DerivedValues,
) -> None:
    cursor.execute(
        """
        UPDATE stonks.ohlcv_daily
        SET
            change = %s,
            changepct = %s,
            typ = %s,
            hl_range = %s,
            oc_range = %s,
            updated_at = now()
        WHERE provider_listing_id = %s
          AND trading_date = %s
        """,
        (
            derived.change,
            derived.changepct,
            derived.typ,
            derived.hl_range,
            derived.oc_range,
            provider_listing_id,
            trading_date,
        ),
    )


def _daily_bar_values(
    provider_listing_id: UUID,
    trading_date: date,
    stored: _StoredDailyBar,
) -> tuple[object, ...]:
    return (provider_listing_id, trading_date, *_source_and_derived_values(stored))


def _source_and_derived_values(stored: _StoredDailyBar) -> tuple[object, ...]:
    return (
        stored.source.open,
        stored.source.high,
        stored.source.low,
        stored.source.close,
        stored.source.volume,
        stored.derived.change,
        stored.derived.changepct,
        stored.derived.typ,
        stored.derived.hl_range,
        stored.derived.oc_range,
    )


def _update_listing_coverage(
    *,
    cursor: Any,
    provider_listing_id: UUID,
    current_coverage: tuple[date | None, date | None],
    input_dates: list[date],
) -> None:
    first_seen, last_seen = current_coverage
    input_first_seen = min(input_dates)
    input_last_seen = max(input_dates)
    next_first_seen = (
        input_first_seen
        if first_seen is None
        else min(first_seen, input_first_seen)
    )
    next_last_seen = (
        input_last_seen
        if last_seen is None
        else max(last_seen, input_last_seen)
    )
    if (next_first_seen, next_last_seen) == current_coverage:
        return
    cursor.execute(
        """
        UPDATE stonks.provider_listing
        SET
            first_seen = %s,
            last_seen = %s,
            updated_at = now()
        WHERE provider_listing_id = %s
        """,
        (next_first_seen, next_last_seen, provider_listing_id),
    )
