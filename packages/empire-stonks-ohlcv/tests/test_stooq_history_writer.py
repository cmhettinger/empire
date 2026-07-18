from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

import empire_stonks_ohlcv.stooq_history_writer as stooq_writer
from empire_stonks_ohlcv import (
    DailyBar,
    OHLCVWorkflowError,
    ParsedListingBatch,
    PersistenceCounts,
    ProviderListing,
    ProviderListingWriteResult,
    ResolvedProviderListing,
    StooqHistoryChunk,
    StooqHistoryChunkWriter,
)


class FakeCursor:
    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_value = FakeCursor()
        self.cursor_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self) -> FakeCursor:
        self.cursor_calls += 1
        return self.cursor_value

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


def _listing(ticker: str = "AAA.US", *, market: str = "nasdaq") -> ProviderListing:
    return ProviderListing(
        provider_code="STOOQ",
        market=market,
        ticker=ticker,
    )


def _bar(day: int, *, close: str = "10") -> DailyBar:
    value = Decimal(close)
    return DailyBar(
        trading_date=date(2026, 1, day),
        open=value,
        high=value + 1,
        low=value - 1,
        close=value,
        volume=Decimal("100"),
    )


def _chunk(
    chunk_number: int,
    *batches: tuple[ProviderListing, tuple[DailyBar, ...]],
) -> StooqHistoryChunk:
    return StooqHistoryChunk(
        chunk_number=chunk_number,
        batches=tuple(
            ParsedListingBatch(listing=listing, bars=bars)
            for listing, bars in batches
        ),
    )


def _listing_result(
    listings: tuple[ProviderListing, ...],
    *,
    outcome: str = "inserted",
    inactive_ticker: str | None = None,
) -> ProviderListingWriteResult:
    return ProviderListingWriteResult(
        resolved=tuple(
            ResolvedProviderListing(
                listing=listing,
                provider_listing_id=UUID(int=index + 1),
                outcome=outcome,  # type: ignore[arg-type]
                status=(
                    "INACTIVE"
                    if listing.ticker == inactive_ticker
                    else "ACTIVE"
                ),
            )
            for index, listing in enumerate(listings)
        )
    )


def test_writer_commits_each_chunk_and_accumulates_disjoint_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    first_listing = _listing()
    second_listing = _listing("BBB.US", market="nyse")
    listing_calls: list[tuple[ProviderListing, ...]] = []
    bar_call_sizes: list[int] = []
    listing_outcomes = iter(("inserted", "unchanged"))
    bar_counts = iter(
        (
            PersistenceCounts(inserted=3),
            PersistenceCounts(updated=1, unchanged=1, derived_updated=2),
        )
    )

    def write_listings(**values: object) -> ProviderListingWriteResult:
        listings = tuple(values["listings"])  # type: ignore[arg-type]
        listing_calls.append(listings)
        return _listing_result(listings, outcome=next(listing_outcomes))

    def write_bars(**values: object) -> PersistenceCounts:
        bars = tuple(values["bars"])  # type: ignore[arg-type]
        bar_call_sizes.append(len(bars))
        return next(bar_counts)

    monkeypatch.setattr(stooq_writer, "upsert_provider_listings", write_listings)
    monkeypatch.setattr(stooq_writer, "upsert_daily_bars", write_bars)
    writer = StooqHistoryChunkWriter(connection)

    first = writer.write(
        _chunk(
            1,
            (first_listing, (_bar(2), _bar(3))),
            (first_listing, (_bar(4),)),
        )
    )
    second = writer.write(
        _chunk(2, (second_listing, (_bar(5), _bar(6))))
    )

    assert listing_calls == [(first_listing,), (second_listing,)]
    assert bar_call_sizes == [3, 2]
    assert first.listing_counts == PersistenceCounts(inserted=1)
    assert first.bar_counts == PersistenceCounts(inserted=3)
    assert second.bar_counts == PersistenceCounts(
        updated=1,
        unchanged=1,
        derived_updated=2,
    )
    assert connection.cursor_calls == 2
    assert connection.commit_calls == 2
    assert connection.rollback_calls == 0
    assert writer.summary.listing_counts == PersistenceCounts(
        inserted=1,
        unchanged=1,
    )
    assert writer.summary.bar_counts == PersistenceCounts(
        inserted=3,
        updated=1,
        unchanged=1,
        derived_updated=2,
    )
    assert writer.summary.chunks_attempted == 2
    assert writer.summary.last_completed_chunk == 2
    json.dumps(first.to_dict())
    json.dumps(writer.summary.to_dict())


def test_writer_skips_bars_for_inactive_listings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    active = _listing()
    inactive = _listing("OLD.US")

    def write_listings(**values: object) -> ProviderListingWriteResult:
        listings = tuple(values["listings"])  # type: ignore[arg-type]
        return _listing_result(listings, inactive_ticker="OLD.US")

    def write_bars(**values: object) -> PersistenceCounts:
        bars = tuple(values["bars"])  # type: ignore[arg-type]
        assert len(bars) == 1
        assert bars[0].bar.trading_date == date(2026, 1, 2)
        return PersistenceCounts(inserted=1)

    monkeypatch.setattr(stooq_writer, "upsert_provider_listings", write_listings)
    monkeypatch.setattr(stooq_writer, "upsert_daily_bars", write_bars)

    writer = StooqHistoryChunkWriter(connection)
    result = writer.write(
        _chunk(
            1,
            (active, (_bar(2),)),
            (inactive, (_bar(3), _bar(4))),
        )
    )

    assert result.skipped_inactive_bars == 2
    assert writer.summary.skipped_inactive_bars == 2


def test_failed_chunk_rolls_back_counts_failure_and_can_be_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    listing = _listing()
    fail = True

    def write_listings(**values: object) -> ProviderListingWriteResult:
        listings = tuple(values["listings"])  # type: ignore[arg-type]
        return _listing_result(listings)

    def write_bars(**values: object) -> PersistenceCounts:
        nonlocal fail
        if fail:
            fail = False
            raise RuntimeError("database password=must-not-leak")
        bars = tuple(values["bars"])  # type: ignore[arg-type]
        return PersistenceCounts(inserted=len(bars))

    monkeypatch.setattr(stooq_writer, "upsert_provider_listings", write_listings)
    monkeypatch.setattr(stooq_writer, "upsert_daily_bars", write_bars)
    writer = StooqHistoryChunkWriter(connection)
    chunk = _chunk(1, (listing, (_bar(2),)))

    with pytest.raises(OHLCVWorkflowError) as raised:
        writer.write(chunk)

    assert str(raised.value) == "OHLCV provider workflow failed during persistence."
    assert raised.value.source_code == "stooq_history"
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 1
    assert writer.summary.chunks_failed == 1
    assert writer.summary.chunks_completed == 0
    assert writer.summary.last_completed_chunk is None
    assert writer.summary.bar_counts == PersistenceCounts()

    result = writer.write(chunk)

    assert result.bar_counts == PersistenceCounts(inserted=1)
    assert connection.commit_calls == 1
    assert connection.rollback_calls == 1
    assert writer.summary.chunks_attempted == 2
    assert writer.summary.chunks_completed == 1
    assert writer.summary.chunks_failed == 1


def test_writer_rejects_out_of_sequence_or_non_stooq_chunks_before_transaction(
) -> None:
    connection = FakeConnection()
    writer = StooqHistoryChunkWriter(connection)

    with pytest.raises(ValueError, match="expected Stooq history chunk 1"):
        writer.write(_chunk(2, (_listing(), (_bar(2),))))
    with pytest.raises(ValueError, match="provider STOOQ"):
        writer.write(
            _chunk(
                1,
                (
                    ProviderListing(
                        provider_code="EODDATA",
                        market="nasdaq",
                        ticker="AAA.US",
                    ),
                    (_bar(2),),
                ),
            )
        )

    assert connection.cursor_calls == 0
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0
    assert writer.summary.chunks_attempted == 0


@pytest.mark.parametrize("bad_connection", [None, object()])
def test_writer_requires_transaction_connection(bad_connection: object) -> None:
    with pytest.raises(TypeError, match="cursor, commit, and rollback"):
        StooqHistoryChunkWriter(bad_connection)
