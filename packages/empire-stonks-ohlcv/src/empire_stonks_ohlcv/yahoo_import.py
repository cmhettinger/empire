"""Seed-only, failure-isolated Yahoo snapshot and daily-bar persistence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable
from uuid import UUID

from empire_stonks_ohlcv.daily_bars import DailyBarWriteInput, upsert_daily_bars
from empire_stonks_ohlcv.results import (
    ImportIssue,
    PersistenceCounts,
)
from empire_stonks_ohlcv.source_conventions import YAHOO_DAILY_SOURCE
from empire_stonks_ohlcv.source_snapshots import (
    SourceSnapshotRegistration,
    upsert_provider_source_snapshot,
)
from empire_stonks_ohlcv.yahoo import (
    YAHOO_MARKET,
    YAHOO_PROVIDER_CODE,
    YahooAcquisitionOutcome,
    YahooAcquisitionStatus,
)
from empire_stonks_ohlcv.yahoo_parser import YahooChartParseResult


class YahooImportStatus(StrEnum):
    """Persistence disposition for one acquired request chunk."""

    IMPORTED = "imported"
    MISSING = "missing"
    FAILED = "failed"


class YahooImportFailureCode(StrEnum):
    """Secret-safe reason that one chunk did not import."""

    ACQUISITION_FAILED = "acquisition_failed"
    PARSE_UNAVAILABLE = "parse_unavailable"
    UNSEEDED_LISTING = "unseeded_listing"
    INACTIVE_LISTING = "inactive_listing"
    LISTING_IDENTITY_MISMATCH = "listing_identity_mismatch"
    PERSISTENCE_FAILED = "persistence_failed"


@dataclass(frozen=True)
class YahooImportInput:
    """One acquisition outcome and its optional validated parse result."""

    acquisition: YahooAcquisitionOutcome
    parse_result: YahooChartParseResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.acquisition, YahooAcquisitionOutcome):
            raise TypeError("acquisition must be a YahooAcquisitionOutcome.")
        if self.parse_result is not None and not isinstance(
            self.parse_result,
            YahooChartParseResult,
        ):
            raise TypeError(
                "parse_result must be a YahooChartParseResult or None."
            )
        if self.parse_result is not None:
            if self.acquisition.status is not YahooAcquisitionStatus.STORED:
                raise ValueError(
                    "parse_result requires a STORED acquisition outcome."
                )
            if self.parse_result.request != self.acquisition.request:
                raise ValueError(
                    "parse_result request must match the acquisition request."
                )


@dataclass(frozen=True)
class YahooChunkImportResult:
    """Safe lineage, parse, and write result for one request chunk."""

    acquisition: YahooAcquisitionOutcome
    status: YahooImportStatus
    source_snapshot: SourceSnapshotRegistration | None
    bar_counts: PersistenceCounts
    accepted_rows: int
    rejected_rows: int
    parse_issue_count: int
    parse_issues: tuple[ImportIssue, ...]
    failure_code: YahooImportFailureCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.acquisition, YahooAcquisitionOutcome):
            raise TypeError("acquisition must be a YahooAcquisitionOutcome.")
        if not isinstance(self.status, YahooImportStatus):
            raise TypeError("status must be a YahooImportStatus.")
        if self.source_snapshot is not None and not isinstance(
            self.source_snapshot,
            SourceSnapshotRegistration,
        ):
            raise TypeError(
                "source_snapshot must be a SourceSnapshotRegistration or None."
            )
        if not isinstance(self.bar_counts, PersistenceCounts):
            raise TypeError("bar_counts must be PersistenceCounts.")
        for field_name in (
            "accepted_rows",
            "rejected_rows",
            "parse_issue_count",
        ):
            _nonnegative_int(field_name, getattr(self, field_name))
        if not isinstance(self.parse_issues, tuple) or any(
            not isinstance(item, ImportIssue) for item in self.parse_issues
        ):
            raise TypeError("parse_issues must contain ImportIssue values.")
        if len(self.parse_issues) > self.parse_issue_count:
            raise ValueError("parse_issues cannot exceed parse_issue_count.")
        if self.failure_code is not None and not isinstance(
            self.failure_code,
            YahooImportFailureCode,
        ):
            raise TypeError(
                "failure_code must be a YahooImportFailureCode or None."
            )
        if self.status is YahooImportStatus.FAILED:
            if self.failure_code is None:
                raise ValueError("FAILED requires failure_code.")
            if self.bar_counts.input_count:
                raise ValueError("FAILED cannot report written input bars.")
        elif self.failure_code is not None:
            raise ValueError("Non-failed imports forbid failure_code.")
        if self.status is YahooImportStatus.MISSING and (
            self.accepted_rows
            or self.rejected_rows
            or self.parse_issue_count
            or self.bar_counts.input_count
        ):
            raise ValueError("MISSING cannot contain parsed or written rows.")

    @property
    def provider_listing_id(self) -> UUID:
        return self.acquisition.request.listing.provider_listing_id

    @property
    def ticker(self) -> str:
        return self.acquisition.request.listing.ticker

    def to_dict(self) -> dict[str, Any]:
        return {
            "acquisition": self.acquisition.to_safe_dict(),
            "status": self.status.value,
            "source_snapshot": (
                None
                if self.source_snapshot is None
                else self.source_snapshot.to_dict()
            ),
            "bar_counts": self.bar_counts.to_dict(),
            "accepted_rows": self.accepted_rows,
            "rejected_rows": self.rejected_rows,
            "parse_issue_count": self.parse_issue_count,
            "parse_issues": [item.to_dict() for item in self.parse_issues],
            "failure_code": (
                None if self.failure_code is None else self.failure_code.value
            ),
        }


@dataclass(frozen=True)
class YahooListingImportSummary:
    """All independently committed chunk outcomes for one seeded listing."""

    provider_listing_id: UUID
    ticker: str
    chunks: tuple[YahooChunkImportResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.provider_listing_id, UUID):
            raise TypeError("provider_listing_id must be a UUID.")
        _required_text("ticker", self.ticker)
        if not isinstance(self.chunks, tuple) or not self.chunks:
            raise ValueError("chunks must be a non-empty tuple.")
        if any(
            not isinstance(item, YahooChunkImportResult)
            for item in self.chunks
        ):
            raise TypeError(
                "chunks must contain YahooChunkImportResult values."
            )
        if any(
            item.provider_listing_id != self.provider_listing_id
            or item.ticker != self.ticker
            for item in self.chunks
        ):
            raise ValueError("chunks must match the listing summary identity.")

    @property
    def imported_chunks(self) -> int:
        return sum(
            item.status is YahooImportStatus.IMPORTED for item in self.chunks
        )

    @property
    def missing_chunks(self) -> int:
        return sum(
            item.status is YahooImportStatus.MISSING for item in self.chunks
        )

    @property
    def failed_chunks(self) -> int:
        return sum(
            item.status is YahooImportStatus.FAILED for item in self.chunks
        )

    @property
    def source_snapshot_count(self) -> int:
        return sum(item.source_snapshot is not None for item in self.chunks)

    @property
    def bar_counts(self) -> PersistenceCounts:
        return _sum_counts(item.bar_counts for item in self.chunks)

    @property
    def accepted_rows(self) -> int:
        return sum(item.accepted_rows for item in self.chunks)

    @property
    def rejected_rows(self) -> int:
        return sum(item.rejected_rows for item in self.chunks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "ticker": self.ticker,
            "chunk_count": len(self.chunks),
            "imported_chunks": self.imported_chunks,
            "missing_chunks": self.missing_chunks,
            "failed_chunks": self.failed_chunks,
            "source_snapshot_count": self.source_snapshot_count,
            "accepted_rows": self.accepted_rows,
            "rejected_rows": self.rejected_rows,
            "bar_counts": self.bar_counts.to_dict(),
            "chunks": [item.to_dict() for item in self.chunks],
        }


@dataclass(frozen=True)
class YahooImportResult:
    """Ordered per-listing summaries for one Yahoo import service call."""

    listings: tuple[YahooListingImportSummary, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.listings, tuple) or any(
            not isinstance(item, YahooListingImportSummary)
            for item in self.listings
        ):
            raise TypeError(
                "listings must contain YahooListingImportSummary values."
            )
        identities = [
            (item.provider_listing_id, item.ticker) for item in self.listings
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("listings must have unique identities.")

    @property
    def chunk_count(self) -> int:
        return sum(len(item.chunks) for item in self.listings)

    @property
    def imported_chunks(self) -> int:
        return sum(item.imported_chunks for item in self.listings)

    @property
    def missing_chunks(self) -> int:
        return sum(item.missing_chunks for item in self.listings)

    @property
    def failed_chunks(self) -> int:
        return sum(item.failed_chunks for item in self.listings)

    @property
    def source_snapshot_count(self) -> int:
        return sum(item.source_snapshot_count for item in self.listings)

    @property
    def bar_counts(self) -> PersistenceCounts:
        return _sum_counts(item.bar_counts for item in self.listings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_code": YAHOO_PROVIDER_CODE,
            "listing_count": len(self.listings),
            "chunk_count": self.chunk_count,
            "imported_chunks": self.imported_chunks,
            "missing_chunks": self.missing_chunks,
            "failed_chunks": self.failed_chunks,
            "source_snapshot_count": self.source_snapshot_count,
            "seeded_listing_writes": 0,
            "bar_counts": self.bar_counts.to_dict(),
            "listings": [item.to_dict() for item in self.listings],
        }


class _SeedResolutionError(Exception):
    def __init__(self, code: YahooImportFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


def import_yahoo_ranges(
    *,
    connection: Any,
    inputs: Iterable[YahooImportInput],
) -> YahooImportResult:
    """Persist Yahoo chunks independently without creating provider listings."""

    _validate_connection(connection)
    prepared = _prepare_inputs(inputs)
    chunk_results = tuple(
        _import_chunk(connection=connection, item=item) for item in prepared
    )
    grouped: dict[tuple[UUID, str], list[YahooChunkImportResult]] = {}
    for result in chunk_results:
        key = (result.provider_listing_id, result.ticker)
        grouped.setdefault(key, []).append(result)
    return YahooImportResult(
        listings=tuple(
            YahooListingImportSummary(
                provider_listing_id=provider_listing_id,
                ticker=ticker,
                chunks=tuple(grouped[(provider_listing_id, ticker)]),
            )
            for provider_listing_id, ticker in sorted(
                grouped,
                key=lambda item: (item[1], str(item[0])),
            )
        )
    )


def _import_chunk(
    *,
    connection: Any,
    item: YahooImportInput,
) -> YahooChunkImportResult:
    acquisition = item.acquisition
    acquired_object = acquisition.acquired_object
    if acquired_object is None:
        return _chunk_result(
            item=item,
            status=YahooImportStatus.FAILED,
            failure_code=YahooImportFailureCode.ACQUISITION_FAILED,
        )

    try:
        with connection.cursor() as cursor:
            _resolve_seeded_listing(cursor=cursor, item=item)
            registration = upsert_provider_source_snapshot(
                cursor=cursor,
                provider_code=YAHOO_PROVIDER_CODE,
                acquired_object=acquired_object,
                parser_version=YAHOO_DAILY_SOURCE.parser_version,
            )
            if not isinstance(registration, SourceSnapshotRegistration):
                raise TypeError(
                    "snapshot writer must return SourceSnapshotRegistration."
                )

            if acquisition.status is YahooAcquisitionStatus.FAILED:
                result = _chunk_result(
                    item=item,
                    status=YahooImportStatus.FAILED,
                    source_snapshot=registration,
                    failure_code=YahooImportFailureCode.ACQUISITION_FAILED,
                )
            elif acquisition.status is YahooAcquisitionStatus.MISSING:
                result = _chunk_result(
                    item=item,
                    status=YahooImportStatus.MISSING,
                    source_snapshot=registration,
                )
            elif item.parse_result is None:
                result = _chunk_result(
                    item=item,
                    status=YahooImportStatus.FAILED,
                    source_snapshot=registration,
                    failure_code=YahooImportFailureCode.PARSE_UNAVAILABLE,
                )
            else:
                bar_counts = upsert_daily_bars(
                    cursor=cursor,
                    bars=(
                        DailyBarWriteInput(
                            provider_listing_id=(
                                acquisition.request.listing.provider_listing_id
                            ),
                            bar=bar,
                        )
                        for bar in item.parse_result.batch.bars
                    ),
                )
                if not isinstance(bar_counts, PersistenceCounts):
                    raise TypeError(
                        "bar writer must return PersistenceCounts."
                    )
                result = _chunk_result(
                    item=item,
                    status=YahooImportStatus.IMPORTED,
                    source_snapshot=registration,
                    bar_counts=bar_counts,
                )
        connection.commit()
        return result
    except _SeedResolutionError as exc:
        connection.rollback()
        return _chunk_result(
            item=item,
            status=YahooImportStatus.FAILED,
            failure_code=exc.code,
        )
    except Exception:
        connection.rollback()
        return _chunk_result(
            item=item,
            status=YahooImportStatus.FAILED,
            failure_code=YahooImportFailureCode.PERSISTENCE_FAILED,
        )


def _resolve_seeded_listing(*, cursor: Any, item: YahooImportInput) -> None:
    target = item.acquisition.request.listing
    cursor.execute(
        """
        SELECT
            provider_code,
            market,
            ticker,
            name,
            instrument_type_code,
            metadata,
            status,
            session_policy_code
        FROM stonks.provider_listing
        WHERE provider_listing_id = %s
        FOR UPDATE
        """,
        (target.provider_listing_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise _SeedResolutionError(
            YahooImportFailureCode.UNSEEDED_LISTING
        )
    (
        provider_code,
        market,
        ticker,
        name,
        instrument_type_code,
        metadata,
        status,
        session_policy_code,
    ) = row
    if status != "ACTIVE":
        raise _SeedResolutionError(
            YahooImportFailureCode.INACTIVE_LISTING
        )
    if (
        provider_code != YAHOO_PROVIDER_CODE
        or market != YAHOO_MARKET
        or ticker != target.ticker
        or not isinstance(metadata, dict)
        or metadata.get("YahooTicker") != target.yahoo_ticker
        or not isinstance(session_policy_code, str)
        or not session_policy_code
    ):
        raise _SeedResolutionError(
            YahooImportFailureCode.LISTING_IDENTITY_MISMATCH
        )

    parsed = item.parse_result
    if parsed is None:
        return
    listing = parsed.batch.listing
    if (
        listing.provider_code != provider_code
        or listing.market != market
        or listing.ticker != ticker
        or listing.name != name
        or listing.instrument_type_code != instrument_type_code
        or listing.metadata != metadata
        or parsed.session_policy_code != session_policy_code
    ):
        raise _SeedResolutionError(
            YahooImportFailureCode.LISTING_IDENTITY_MISMATCH
        )


def _chunk_result(
    *,
    item: YahooImportInput,
    status: YahooImportStatus,
    source_snapshot: SourceSnapshotRegistration | None = None,
    bar_counts: PersistenceCounts | None = None,
    failure_code: YahooImportFailureCode | None = None,
) -> YahooChunkImportResult:
    parsed = item.parse_result
    return YahooChunkImportResult(
        acquisition=item.acquisition,
        status=status,
        source_snapshot=source_snapshot,
        bar_counts=(
            PersistenceCounts() if bar_counts is None else bar_counts
        ),
        accepted_rows=0 if parsed is None else parsed.accepted_rows,
        rejected_rows=0 if parsed is None else parsed.rejected_rows,
        parse_issue_count=0 if parsed is None else parsed.issue_count,
        parse_issues=() if parsed is None else parsed.issues,
        failure_code=failure_code,
    )


def _prepare_inputs(
    inputs: Iterable[YahooImportInput],
) -> tuple[YahooImportInput, ...]:
    if isinstance(inputs, (str, bytes)):
        raise TypeError("inputs must be an iterable of YahooImportInput values.")
    try:
        prepared = tuple(inputs)
    except TypeError as exc:
        raise TypeError(
            "inputs must be an iterable of YahooImportInput values."
        ) from exc
    if any(not isinstance(item, YahooImportInput) for item in prepared):
        raise TypeError("inputs must contain YahooImportInput values.")
    chunk_identities: set[tuple[UUID, object, object]] = set()
    object_ids: set[UUID] = set()
    for item in prepared:
        request = item.acquisition.request
        chunk_identity = (
            request.listing.provider_listing_id,
            request.start_date,
            request.end_date_exclusive,
        )
        if chunk_identity in chunk_identities:
            raise ValueError("inputs contain a duplicate Yahoo request chunk.")
        chunk_identities.add(chunk_identity)
        acquired = item.acquisition.acquired_object
        if acquired is not None:
            if acquired.source_code != YAHOO_DAILY_SOURCE.source_code:
                raise ValueError(
                    "Yahoo acquired objects must use yahoo_daily."
                )
            if acquired.object_id in object_ids:
                raise ValueError("inputs contain a duplicate Core object ID.")
            object_ids.add(acquired.object_id)
    return tuple(
        sorted(
            prepared,
            key=lambda item: (
                item.acquisition.request.listing.ticker,
                str(
                    item.acquisition.request.listing.provider_listing_id
                ),
                item.acquisition.request.start_date,
                item.acquisition.request.end_date_exclusive,
            ),
        )
    )


def _validate_connection(connection: Any) -> None:
    for method_name in ("cursor", "commit", "rollback"):
        if not callable(getattr(connection, method_name, None)):
            raise TypeError(
                "connection must provide cursor, commit, and rollback methods."
            )


def _sum_counts(values: Iterable[PersistenceCounts]) -> PersistenceCounts:
    prepared = tuple(values)
    return PersistenceCounts(
        inserted=sum(item.inserted for item in prepared),
        updated=sum(item.updated for item in prepared),
        unchanged=sum(item.unchanged for item in prepared),
        derived_updated=sum(item.derived_updated for item in prepared),
    )


def _required_text(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty and trimmed.")


def _nonnegative_int(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
