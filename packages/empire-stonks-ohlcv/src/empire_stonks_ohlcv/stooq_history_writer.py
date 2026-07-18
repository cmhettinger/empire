"""Bounded transactional persistence for Stooq historical parse chunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from empire_stonks_ohlcv.daily_bars import DailyBarWriteInput, upsert_daily_bars
from empire_stonks_ohlcv.exceptions import OHLCVPersistenceError, OHLCVWorkflowError
from empire_stonks_ohlcv.listings import (
    ProviderListingWriteResult,
    upsert_provider_listings,
)
from empire_stonks_ohlcv.models import ProviderListing
from empire_stonks_ohlcv.results import PersistenceCounts
from empire_stonks_ohlcv.stooq_history import (
    STOOQ_HISTORY_MARKETS,
    STOOQ_HISTORY_PROVIDER_CODE,
    StooqHistoryChunk,
)


@dataclass(frozen=True)
class StooqHistoryChunkWriteResult:
    """Disjoint persistence outcomes for one committed history chunk."""

    chunk_number: int
    listing_counts: PersistenceCounts
    bar_counts: PersistenceCounts
    skipped_inactive_bars: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.chunk_number, bool) or not isinstance(
            self.chunk_number, int
        ):
            raise TypeError("chunk_number must be an integer.")
        if self.chunk_number <= 0:
            raise ValueError("chunk_number must be greater than zero.")
        if not isinstance(self.listing_counts, PersistenceCounts):
            raise TypeError("listing_counts must be PersistenceCounts.")
        if not isinstance(self.bar_counts, PersistenceCounts):
            raise TypeError("bar_counts must be PersistenceCounts.")
        if isinstance(self.skipped_inactive_bars, bool) or not isinstance(
            self.skipped_inactive_bars, int
        ):
            raise TypeError("skipped_inactive_bars must be an integer.")
        if self.skipped_inactive_bars < 0:
            raise ValueError("skipped_inactive_bars must be non-negative.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_number": self.chunk_number,
            "listing_counts": self.listing_counts.to_dict(),
            "bar_counts": self.bar_counts.to_dict(),
            "skipped_inactive_bars": self.skipped_inactive_bars,
        }


@dataclass(frozen=True)
class StooqHistoryWriteSummary:
    """Bounded cumulative outcomes across attempted chunk transactions."""

    chunks_completed: int = 0
    chunks_failed: int = 0
    listing_counts: PersistenceCounts = PersistenceCounts()
    bar_counts: PersistenceCounts = PersistenceCounts()
    skipped_inactive_bars: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "chunks_completed",
            "chunks_failed",
            "skipped_inactive_bars",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative.")
        if not isinstance(self.listing_counts, PersistenceCounts):
            raise TypeError("listing_counts must be PersistenceCounts.")
        if not isinstance(self.bar_counts, PersistenceCounts):
            raise TypeError("bar_counts must be PersistenceCounts.")

    @property
    def chunks_attempted(self) -> int:
        return self.chunks_completed + self.chunks_failed

    @property
    def last_completed_chunk(self) -> int | None:
        return self.chunks_completed or None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunks_attempted": self.chunks_attempted,
            "chunks_completed": self.chunks_completed,
            "chunks_failed": self.chunks_failed,
            "last_completed_chunk": self.last_completed_chunk,
            "listing_counts": self.listing_counts.to_dict(),
            "bar_counts": self.bar_counts.to_dict(),
            "skipped_inactive_bars": self.skipped_inactive_bars,
        }


class StooqHistoryChunkWriter:
    """Write sequential history chunks in independent, rerunnable transactions."""

    def __init__(self, connection: Any) -> None:
        _validate_connection(connection)
        self.connection = connection
        self._chunks_completed = 0
        self._chunks_failed = 0
        self._listing_counts = PersistenceCounts()
        self._bar_counts = PersistenceCounts()
        self._skipped_inactive_bars = 0

    @property
    def summary(self) -> StooqHistoryWriteSummary:
        return StooqHistoryWriteSummary(
            chunks_completed=self._chunks_completed,
            chunks_failed=self._chunks_failed,
            listing_counts=self._listing_counts,
            bar_counts=self._bar_counts,
            skipped_inactive_bars=self._skipped_inactive_bars,
        )

    def write(self, chunk: StooqHistoryChunk) -> StooqHistoryChunkWriteResult:
        """Commit one expected chunk, or roll it back and leave it retryable."""

        expected_chunk_number = self._chunks_completed + 1
        listings = _prepare_chunk(
            chunk,
            expected_chunk_number=expected_chunk_number,
        )

        try:
            with self.connection.cursor() as cursor:
                listing_result = upsert_provider_listings(
                    cursor=cursor,
                    listings=listings,
                )
                if not isinstance(listing_result, ProviderListingWriteResult):
                    raise TypeError(
                        "listing writer must return ProviderListingWriteResult."
                    )

                active_bars: list[DailyBarWriteInput] = []
                skipped_inactive = 0
                for batch in chunk.batches:
                    if not listing_result.provider_listing_is_active(batch.listing):
                        skipped_inactive += len(batch.bars)
                        continue
                    provider_listing_id = listing_result.provider_listing_id_for(
                        batch.listing
                    )
                    active_bars.extend(
                        DailyBarWriteInput(
                            provider_listing_id=provider_listing_id,
                            bar=bar,
                        )
                        for bar in batch.bars
                    )

                bar_counts = upsert_daily_bars(
                    cursor=cursor,
                    bars=active_bars,
                )
                if not isinstance(bar_counts, PersistenceCounts):
                    raise TypeError("bar writer must return PersistenceCounts.")
            self.connection.commit()
        except Exception as exc:
            self.connection.rollback()
            self._chunks_failed += 1
            raise OHLCVWorkflowError(
                "persistence",
                source_code="stooq_history",
            ) from exc

        result = StooqHistoryChunkWriteResult(
            chunk_number=chunk.chunk_number,
            listing_counts=listing_result.counts,
            bar_counts=bar_counts,
            skipped_inactive_bars=skipped_inactive,
        )
        self._chunks_completed += 1
        self._listing_counts = _add_counts(
            self._listing_counts,
            result.listing_counts,
        )
        self._bar_counts = _add_counts(self._bar_counts, result.bar_counts)
        self._skipped_inactive_bars += result.skipped_inactive_bars
        return result


def _prepare_chunk(
    chunk: object,
    *,
    expected_chunk_number: int,
) -> tuple[ProviderListing, ...]:
    if not isinstance(chunk, StooqHistoryChunk):
        raise TypeError("chunk must be a StooqHistoryChunk.")
    if chunk.chunk_number != expected_chunk_number:
        raise ValueError(
            f"expected Stooq history chunk {expected_chunk_number}, "
            f"received {chunk.chunk_number}."
        )
    if chunk.bar_count <= 0:
        raise ValueError("Stooq history chunks must contain at least one bar.")

    by_identity: dict[tuple[str, str, str], ProviderListing] = {}
    for batch in chunk.batches:
        listing = batch.listing
        if listing.provider_code != STOOQ_HISTORY_PROVIDER_CODE:
            raise ValueError("history chunk listings must use provider STOOQ.")
        if listing.market not in STOOQ_HISTORY_MARKETS:
            raise ValueError("history chunk listings must use a supported market.")
        identity = (listing.provider_code, listing.market, listing.ticker)
        previous = by_identity.get(identity)
        if previous is not None and previous != listing:
            raise OHLCVPersistenceError(
                "Conflicting provider-listing values in one history chunk."
            )
        by_identity[identity] = listing
    return tuple(by_identity[key] for key in sorted(by_identity))


def _validate_connection(connection: Any) -> None:
    for method_name in ("cursor", "commit", "rollback"):
        if not callable(getattr(connection, method_name, None)):
            raise TypeError(
                "connection must provide cursor, commit, and rollback methods."
            )


def _add_counts(
    left: PersistenceCounts,
    right: PersistenceCounts,
) -> PersistenceCounts:
    return PersistenceCounts(
        inserted=left.inserted + right.inserted,
        updated=left.updated + right.updated,
        unchanged=left.unchanged + right.unchanged,
        derived_updated=left.derived_updated + right.derived_updated,
    )
