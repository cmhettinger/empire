"""Atomic persistence service for one validated EODData daily run."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from empire_stonks_ohlcv.config import DEFAULT_EODDATA_EXCHANGES
from empire_stonks_ohlcv.daily_bars import DailyBarWriteInput, upsert_daily_bars
from empire_stonks_ohlcv.eoddata import EODDATA_PROVIDER_CODE
from empire_stonks_ohlcv.exceptions import OHLCVWorkflowError
from empire_stonks_ohlcv.listings import (
    ProviderListingWriteResult,
    upsert_provider_listings,
)
from empire_stonks_ohlcv.results import AcquiredObject, ImportIssue, PersistenceCounts
from empire_stonks_ohlcv.source_conventions import (
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
)
from empire_stonks_ohlcv.source_snapshots import (
    SourceSnapshotRegistration,
    upsert_provider_source_snapshot,
)
from empire_stonks_ohlcv.validation import (
    MAX_ISSUE_SAMPLES,
    BoundedIssueSummary,
    CrossFeedOutcomeCounts,
    FeedOutcomeCounts,
    ProviderValidationResult,
    RowRejectionSummary,
    SourceMarketWriteCounts,
)


_SOURCES = (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE)
_EXPECTED_OBJECT_KEYS = tuple(
    (source.source_code, market)
    for source in _SOURCES
    for market in DEFAULT_EODDATA_EXCHANGES
)


@dataclass(frozen=True)
class EODDataImportResult:
    """Compact lineage, validation, and persistence outcome for one run."""

    effective_date: date
    acquired_objects: tuple[AcquiredObject, ...]
    source_snapshots: tuple[SourceSnapshotRegistration, ...]
    feed_counts: tuple[FeedOutcomeCounts, ...]
    write_counts: tuple[SourceMarketWriteCounts, ...]
    row_rejections: tuple[RowRejectionSummary, ...]
    failures: BoundedIssueSummary
    warnings: BoundedIssueSummary
    cross_feed_counts: tuple[CrossFeedOutcomeCounts, ...]

    def __post_init__(self) -> None:
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date.")
        if not isinstance(self.acquired_objects, tuple) or any(
            not isinstance(item, AcquiredObject) for item in self.acquired_objects
        ):
            raise TypeError(
                "acquired_objects must contain only AcquiredObject records."
            )
        if len(self.acquired_objects) != len(_EXPECTED_OBJECT_KEYS):
            raise ValueError("acquired_objects must contain six records.")
        if not isinstance(self.source_snapshots, tuple) or any(
            not isinstance(item, SourceSnapshotRegistration)
            for item in self.source_snapshots
        ):
            raise TypeError(
                "source_snapshots must contain SourceSnapshotRegistration records."
            )
        if len(self.source_snapshots) != len(_EXPECTED_OBJECT_KEYS):
            raise ValueError("source_snapshots must contain six records.")
        if not isinstance(self.feed_counts, tuple) or any(
            not isinstance(item, FeedOutcomeCounts) for item in self.feed_counts
        ):
            raise TypeError(
                "feed_counts must contain only FeedOutcomeCounts records."
            )
        if not isinstance(self.write_counts, tuple) or any(
            not isinstance(item, SourceMarketWriteCounts)
            for item in self.write_counts
        ):
            raise TypeError(
                "write_counts must contain SourceMarketWriteCounts records."
            )
        if len(self.feed_counts) != 6 or len(self.write_counts) != 6:
            raise ValueError("feed_counts and write_counts must contain six records.")
        if not isinstance(self.failures, BoundedIssueSummary):
            raise TypeError("failures must be a BoundedIssueSummary.")
        if not isinstance(self.row_rejections, tuple) or any(
            not isinstance(item, RowRejectionSummary)
            for item in self.row_rejections
        ):
            raise TypeError(
                "row_rejections must contain only RowRejectionSummary records."
            )
        rejection_counts = {
            (source_code, market): sum(
                item.rejected_records
                for item in self.row_rejections
                if item.source_code == source_code and item.market == market
            )
            for source_code, market in _EXPECTED_OBJECT_KEYS
        }
        if any(
            item.rejected_records
            != rejection_counts[(item.source_code, item.market)]
            for item in self.feed_counts
        ):
            raise ValueError(
                "row_rejections must match feed rejected-record counts."
            )
        if not isinstance(self.warnings, BoundedIssueSummary):
            raise TypeError("warnings must be a BoundedIssueSummary.")
        if not isinstance(self.cross_feed_counts, tuple) or any(
            not isinstance(item, CrossFeedOutcomeCounts)
            for item in self.cross_feed_counts
        ):
            raise TypeError(
                "cross_feed_counts must contain CrossFeedOutcomeCounts records."
            )
        if len(self.cross_feed_counts) != len(DEFAULT_EODDATA_EXCHANGES):
            raise ValueError("cross_feed_counts must contain three records.")
        if tuple(item.market for item in self.cross_feed_counts) != (
            DEFAULT_EODDATA_EXCHANGES
        ):
            raise ValueError(
                "cross_feed_counts must use configured EODData market order."
            )

    @property
    def listing_counts(self) -> PersistenceCounts:
        return _sum_persistence_counts(
            item.counts
            for item in self.write_counts
            if item.record_kind == "listing"
        )

    @property
    def bar_counts(self) -> PersistenceCounts:
        return _sum_persistence_counts(
            item.counts
            for item in self.write_counts
            if item.record_kind == "bar"
        )

    @property
    def skipped_inactive_bars(self) -> int:
        return sum(item.skipped_inactive for item in self.write_counts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_code": EODDATA_PROVIDER_CODE,
            "effective_date": self.effective_date.isoformat(),
            "acquired_object_count": len(self.acquired_objects),
            "source_snapshot_count": len(self.source_snapshots),
            "feed_counts": [item.to_dict() for item in self.feed_counts],
            "write_counts": [item.to_dict() for item in self.write_counts],
            "listing_counts": self.listing_counts.to_dict(),
            "bar_counts": self.bar_counts.to_dict(),
            "skipped_inactive_bars": self.skipped_inactive_bars,
            "row_rejections": [
                item.to_dict() for item in self.row_rejections
            ],
            "failures": self.failures.to_dict(),
            "warnings": self.warnings.to_dict(),
            "cross_feed_counts": [
                item.to_dict() for item in self.cross_feed_counts
            ],
        }


def import_eoddata_daily(
    *,
    connection: Any,
    effective_date: date,
    acquired_objects: tuple[AcquiredObject, ...],
    validation_results: tuple[ProviderValidationResult, ...],
) -> EODDataImportResult:
    """Atomically register all six sources, listings, and accepted active bars."""

    _validate_connection(connection)
    acquired_by_key = _validate_acquired_objects(acquired_objects)
    validated_by_market = _validate_results(
        validation_results,
        effective_date=effective_date,
    )
    ordered_objects = tuple(
        acquired_by_key[key] for key in _EXPECTED_OBJECT_KEYS
    )
    ordered_results = tuple(
        validated_by_market[market] for market in DEFAULT_EODDATA_EXCHANGES
    )

    try:
        registrations: list[SourceSnapshotRegistration] = []
        write_counts: list[SourceMarketWriteCounts] = []
        with connection.cursor() as cursor:
            for acquired_object in ordered_objects:
                registration = upsert_provider_source_snapshot(
                    cursor=cursor,
                    provider_code=EODDATA_PROVIDER_CODE,
                    acquired_object=acquired_object,
                    parser_version=_parser_version_for(
                        acquired_object.source_code
                    ),
                )
                if not isinstance(registration, SourceSnapshotRegistration):
                    raise TypeError(
                        "snapshot writer must return SourceSnapshotRegistration."
                    )
                registrations.append(registration)

            for market in DEFAULT_EODDATA_EXCHANGES:
                validation = validated_by_market[market]
                listing_result = upsert_provider_listings(
                    cursor=cursor,
                    listings=(
                        batch.listing for batch in validation.output.batches
                    ),
                )
                if not isinstance(listing_result, ProviderListingWriteResult):
                    raise TypeError(
                        "listing writer must return ProviderListingWriteResult."
                    )
                write_counts.append(
                    SourceMarketWriteCounts(
                        source_code=EODDATA_SYMBOL_LIST_SOURCE.source_code,
                        market=market,
                        record_kind="listing",
                        counts=listing_result.counts,
                    )
                )

                active_bars: list[DailyBarWriteInput] = []
                skipped_inactive = 0
                for batch in validation.output.batches:
                    if not batch.bars:
                        continue
                    if not listing_result.provider_listing_is_active(
                        batch.listing
                    ):
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
                    raise TypeError(
                        "bar writer must return PersistenceCounts."
                    )
                write_counts.append(
                    SourceMarketWriteCounts(
                        source_code=EODDATA_DAILY_SOURCE.source_code,
                        market=market,
                        record_kind="bar",
                        counts=bar_counts,
                        skipped_inactive=skipped_inactive,
                    )
                )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        raise OHLCVWorkflowError("persistence") from exc

    feed_counts = tuple(
        next(
            item
            for item in validated_by_market[market].feed_counts
            if item.source_code == source.source_code
        )
        for source in _SOURCES
        for market in DEFAULT_EODDATA_EXCHANGES
    )
    return EODDataImportResult(
        effective_date=effective_date,
        acquired_objects=ordered_objects,
        source_snapshots=tuple(registrations),
        feed_counts=feed_counts,
        write_counts=tuple(
            next(
                item
                for item in write_counts
                if item.source_code == source.source_code
                and item.market == market
            )
            for source in _SOURCES
            for market in DEFAULT_EODDATA_EXCHANGES
        ),
        row_rejections=tuple(
            rejection
            for result in ordered_results
            for rejection in result.row_rejections
        ),
        failures=_combine_issue_summaries(
            tuple(result.failures for result in ordered_results)
        ),
        warnings=_combine_issue_summaries(
            tuple(result.warnings for result in ordered_results)
        ),
        cross_feed_counts=tuple(
            validated_by_market[market].cross_feed_counts
            for market in DEFAULT_EODDATA_EXCHANGES
            if validated_by_market[market].cross_feed_counts is not None
        ),
    )


def _validate_connection(connection: Any) -> None:
    for method_name in ("cursor", "commit", "rollback"):
        if not callable(getattr(connection, method_name, None)):
            raise TypeError(
                "connection must provide cursor, commit, and rollback methods."
            )


def _validate_acquired_objects(
    acquired_objects: object,
) -> dict[tuple[str, str], AcquiredObject]:
    if not isinstance(acquired_objects, tuple) or any(
        not isinstance(item, AcquiredObject) for item in acquired_objects
    ):
        raise TypeError(
            "acquired_objects must contain only AcquiredObject records."
        )
    if len(acquired_objects) != len(_EXPECTED_OBJECT_KEYS):
        raise ValueError("EODData import requires exactly six acquired objects.")
    object_ids = [item.object_id for item in acquired_objects]
    if len(set(object_ids)) != len(object_ids):
        raise ValueError("acquired_objects must contain unique Core object IDs.")
    keyed: dict[tuple[str, str], AcquiredObject] = {}
    for item in acquired_objects:
        market = _market_from_filename(item.filename)
        key = (item.source_code, market)
        if key in keyed:
            raise ValueError(
                "acquired_objects must have unique source/market partitions."
            )
        keyed[key] = item
    if set(keyed) != set(_EXPECTED_OBJECT_KEYS):
        raise ValueError(
            "acquired_objects must cover both EODData sources for all markets."
        )
    return keyed


def _market_from_filename(filename: str) -> str:
    for market in DEFAULT_EODDATA_EXCHANGES:
        if filename == f"raw-{market.lower()}.json":
            return market
    raise ValueError("EODData raw filename does not identify a supported market.")


def _validate_results(
    validation_results: object,
    *,
    effective_date: date,
) -> dict[str, ProviderValidationResult]:
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a date.")
    if not isinstance(validation_results, tuple) or any(
        not isinstance(item, ProviderValidationResult)
        for item in validation_results
    ):
        raise TypeError(
            "validation_results must contain ProviderValidationResult records."
        )
    if len(validation_results) != len(DEFAULT_EODDATA_EXCHANGES):
        raise ValueError("EODData import requires one validation result per market.")

    by_market: dict[str, ProviderValidationResult] = {}
    listing_identities: set[tuple[str, str, str]] = set()
    for result in validation_results:
        sources = tuple(result.output.sources)
        if sources != _SOURCES:
            raise ValueError(
                "validation output must use the production EODData sources."
            )
        markets = {item.market for item in result.feed_counts}
        if len(markets) != 1:
            raise ValueError(
                "each validation result must contain exactly one market."
            )
        market = next(iter(markets))
        if result.cross_feed_counts is None:
            raise ValueError(
                "EODData validation result must contain cross-feed counts."
            )
        if market not in DEFAULT_EODDATA_EXCHANGES or market in by_market:
            raise ValueError(
                "validation_results must contain unique supported markets."
            )
        expected_feed_keys = {
            (source.source_code, market) for source in _SOURCES
        }
        if {
            (item.source_code, item.market) for item in result.feed_counts
        } != expected_feed_keys:
            raise ValueError(
                "validation result must contain both EODData feed counts."
            )
        feed_by_source = {
            item.source_code: item for item in result.feed_counts
        }
        if (
            feed_by_source[EODDATA_SYMBOL_LIST_SOURCE.source_code]
            .accepted_records
            != result.output.listing_count
            or feed_by_source[EODDATA_DAILY_SOURCE.source_code].accepted_records
            != result.output.bar_count
        ):
            raise ValueError(
                "validation feed counts must match accepted shared output."
            )
        if sum(item.rejected_records for item in result.feed_counts) != sum(
            item.rejected_records for item in result.row_rejections
        ):
            raise ValueError(
                "validation rejected records must match row-rejection totals."
            )
        if sum(item.warning_count for item in result.feed_counts) != (
            result.warnings.total_count
        ):
            raise ValueError(
                "validation warning counts must match warning totals."
            )
        for batch in result.output.batches:
            listing = batch.listing
            if (
                listing.provider_code != EODDATA_PROVIDER_CODE
                or listing.market != market
            ):
                raise ValueError(
                    "validation output listings must match EODData and market."
                )
            identity = (
                listing.provider_code,
                listing.market,
                listing.ticker,
            )
            if identity in listing_identities:
                raise ValueError(
                    "validation output contains a duplicate listing identity."
                )
            listing_identities.add(identity)
            if len(batch.bars) > 1:
                raise ValueError(
                    "daily validation batches may contain at most one bar."
                )
            if any(
                bar.trading_date != effective_date for bar in batch.bars
            ):
                raise ValueError(
                    "validated bars must match the import effective_date."
                )
        by_market[market] = result

    if set(by_market) != set(DEFAULT_EODDATA_EXCHANGES):
        raise ValueError(
            "validation_results must cover NYSE, NASDAQ, and AMEX."
        )
    return by_market


def _parser_version_for(source_code: str) -> str:
    for source in _SOURCES:
        if source.source_code == source_code:
            return source.parser_version
    raise KeyError(source_code)


def _combine_issue_summaries(
    summaries: tuple[BoundedIssueSummary, ...],
) -> BoundedIssueSummary:
    samples: list[ImportIssue] = []
    for summary in summaries:
        samples.extend(summary.samples)
    source_order = {
        source.source_code: index for index, source in enumerate(_SOURCES)
    }
    market_order = {
        market: index for index, market in enumerate(DEFAULT_EODDATA_EXCHANGES)
    }

    def issue_key(issue: ImportIssue) -> tuple[int, int, str, str]:
        reference = issue.record_reference or ""
        market = reference.partition(":")[0]
        return (
            source_order.get(issue.source_code or "", len(source_order)),
            market_order.get(market, len(market_order)),
            reference,
            issue.code,
        )

    ordered_samples = tuple(sorted(samples, key=issue_key))[
        :MAX_ISSUE_SAMPLES
    ]
    return BoundedIssueSummary(
        total_count=sum(summary.total_count for summary in summaries),
        samples=ordered_samples,
    )


def _sum_persistence_counts(
    counts: Iterable[PersistenceCounts],
) -> PersistenceCounts:
    values = tuple(counts)
    return PersistenceCounts(
        inserted=sum(item.inserted for item in values),
        updated=sum(item.updated for item in values),
        unchanged=sum(item.unchanged for item in values),
        derived_updated=sum(item.derived_updated for item in values),
    )
