"""Streaming parser for operator-supplied Stooq historical ZIP archives."""

from __future__ import annotations

import csv
import stat
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile, ZipInfo

from empire_stonks_ohlcv.exceptions import OHLCVParseError
from empire_stonks_ohlcv.models import DailyBar, ProviderListing
from empire_stonks_ohlcv.results import ImportIssue, ParsedListingBatch
from empire_stonks_ohlcv.source_conventions import STOOQ_HISTORY_SOURCE
from empire_stonks_ohlcv.validation import MAX_ISSUE_SAMPLES


STOOQ_HISTORY_PROVIDER_CODE = "STOOQ"
STOOQ_HISTORY_ARCHIVE_NAME = "d_us_txt.zip"
STOOQ_HISTORY_CORE_ARCHIVE_NAME = "raw.zip"
STOOQ_HISTORY_MARKETS = ("nasdaq", "nyse", "nysemkt")
STOOQ_HISTORY_HEADER = (
    "<TICKER>",
    "<PER>",
    "<DATE>",
    "<TIME>",
    "<OPEN>",
    "<HIGH>",
    "<LOW>",
    "<CLOSE>",
    "<VOL>",
    "<OPENINT>",
)

MAX_ARCHIVE_BYTES = 4 * 1024**3
MAX_ARCHIVE_MEMBERS = 100_000
MAX_SELECTED_MEMBERS = 50_000
MAX_SELECTED_UNCOMPRESSED_BYTES = 20 * 1024**3
MAX_MEMBER_UNCOMPRESSED_BYTES = 256 * 1024**2
PROGRESS_FILE_INTERVAL = 100

_ARCHIVE_PREFIX = ("data", "daily", "us")


def _nonnegative_int(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")


@dataclass(frozen=True)
class StooqHistoryScope:
    """Explicit archive acquisition date and optional historical filters."""

    effective_date: date
    start_date: date | None = None
    end_date: date | None = None
    markets: tuple[str, ...] = STOOQ_HISTORY_MARKETS
    tickers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date.")
        if self.start_date is not None and type(self.start_date) is not date:
            raise TypeError("start_date must be a date or None.")
        if self.end_date is not None and type(self.end_date) is not date:
            raise TypeError("end_date must be a date or None.")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not be later than end_date.")
        if not isinstance(self.markets, tuple) or not self.markets:
            raise TypeError("markets must be a non-empty tuple.")
        if len(set(self.markets)) != len(self.markets):
            raise ValueError("markets must not contain duplicates.")
        if any(market not in STOOQ_HISTORY_MARKETS for market in self.markets):
            raise ValueError(
                "markets must contain only nasdaq, nyse, and nysemkt."
            )
        ordered_markets = tuple(
            market for market in STOOQ_HISTORY_MARKETS if market in self.markets
        )
        object.__setattr__(self, "markets", ordered_markets)

        if not isinstance(self.tickers, tuple):
            raise TypeError("tickers must be a tuple.")
        if len(set(self.tickers)) != len(self.tickers):
            raise ValueError("tickers must not contain duplicates.")
        for ticker in self.tickers:
            if (
                not isinstance(ticker, str)
                or not ticker
                or ticker != ticker.strip()
                or ticker != ticker.upper()
                or not ticker.endswith(".US")
            ):
                raise ValueError(
                    "tickers must be exact uppercase Stooq values ending in .US."
                )
        object.__setattr__(self, "tickers", tuple(sorted(self.tickers)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_date": self.effective_date.isoformat(),
            "start_date": (
                self.start_date.isoformat() if self.start_date is not None else None
            ),
            "end_date": (
                self.end_date.isoformat() if self.end_date is not None else None
            ),
            "markets": list(self.markets),
            "tickers": list(self.tickers),
        }


@dataclass(frozen=True)
class StooqHistoryMember:
    """One selected stock-series member in the Stooq archive."""

    member_path: str
    market: str
    ticker: str
    uncompressed_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.member_path, str) or not self.member_path:
            raise ValueError("member_path is required.")
        if self.market not in STOOQ_HISTORY_MARKETS:
            raise ValueError("market is not supported.")
        if not isinstance(self.ticker, str) or not self.ticker:
            raise ValueError("ticker is required.")
        _nonnegative_int("uncompressed_bytes", self.uncompressed_bytes)


@dataclass(frozen=True)
class StooqHistoryDiscovery:
    """Bounded central-directory inspection result."""

    archive_size_bytes: int
    archive_member_count: int
    selected_uncompressed_bytes: int
    members: tuple[StooqHistoryMember, ...]
    empty_files_skipped: int = 0

    def __post_init__(self) -> None:
        _nonnegative_int("archive_size_bytes", self.archive_size_bytes)
        _nonnegative_int("archive_member_count", self.archive_member_count)
        _nonnegative_int(
            "selected_uncompressed_bytes",
            self.selected_uncompressed_bytes,
        )
        _nonnegative_int("empty_files_skipped", self.empty_files_skipped)
        if not isinstance(self.members, tuple) or any(
            not isinstance(member, StooqHistoryMember) for member in self.members
        ):
            raise TypeError("members must contain StooqHistoryMember records.")
        if not self.members:
            raise ValueError("members must not be empty.")

    @property
    def selected_member_count(self) -> int:
        return len(self.members)


@dataclass(frozen=True)
class StooqHistoryMarketParseCounts:
    """Streaming parse counts for one exact Stooq provider market."""

    market: str
    files_completed: int = 0
    input_rows: int = 0
    date_filtered_rows: int = 0
    accepted_records: int = 0
    rejected_records: int = 0
    rejected_rows: int = 0
    duplicate_rows_collapsed: int = 0

    def __post_init__(self) -> None:
        if self.market not in STOOQ_HISTORY_MARKETS:
            raise ValueError("market is not supported.")
        for field_name in (
            "files_completed",
            "input_rows",
            "date_filtered_rows",
            "accepted_records",
            "rejected_records",
            "rejected_rows",
            "duplicate_rows_collapsed",
        ):
            _nonnegative_int(field_name, getattr(self, field_name))
        accounted_rows = (
            self.date_filtered_rows
            + self.accepted_records
            + self.rejected_rows
            + self.duplicate_rows_collapsed
        )
        if accounted_rows != self.input_rows:
            raise ValueError("market parse counts must account for every input row.")

    def to_dict(self) -> dict[str, int | str]:
        return {
            "market": self.market,
            "files_completed": self.files_completed,
            "input_rows": self.input_rows,
            "date_filtered_rows": self.date_filtered_rows,
            "accepted_records": self.accepted_records,
            "rejected_records": self.rejected_records,
            "rejected_rows": self.rejected_rows,
            "duplicate_rows_collapsed": self.duplicate_rows_collapsed,
        }


@dataclass(frozen=True)
class StooqHistoryParseProgress:
    """Current bounded parser progress at a safe streaming boundary."""

    files_discovered: int
    files_completed: int = 0
    chunks_emitted: int = 0
    input_rows: int = 0
    date_filtered_rows: int = 0
    accepted_records: int = 0
    rejected_records: int = 0
    rejected_rows: int = 0
    duplicate_rows_collapsed: int = 0
    current_member: str | None = None
    empty_files_skipped: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "files_discovered",
            "files_completed",
            "chunks_emitted",
            "input_rows",
            "date_filtered_rows",
            "accepted_records",
            "rejected_records",
            "rejected_rows",
            "duplicate_rows_collapsed",
            "empty_files_skipped",
        ):
            _nonnegative_int(field_name, getattr(self, field_name))
        if self.files_completed > self.files_discovered:
            raise ValueError("files_completed must not exceed files_discovered.")
        if self.current_member is not None and (
            not isinstance(self.current_member, str) or not self.current_member
        ):
            raise ValueError("current_member must be non-empty or None.")

    def to_dict(self) -> dict[str, int | str | None]:
        return {
            "files_discovered": self.files_discovered,
            "files_completed": self.files_completed,
            "chunks_emitted": self.chunks_emitted,
            "input_rows": self.input_rows,
            "date_filtered_rows": self.date_filtered_rows,
            "accepted_records": self.accepted_records,
            "rejected_records": self.rejected_records,
            "rejected_rows": self.rejected_rows,
            "duplicate_rows_collapsed": self.duplicate_rows_collapsed,
            "current_member": self.current_member,
            "empty_files_skipped": self.empty_files_skipped,
        }


@dataclass(frozen=True)
class StooqHistoryParseSummary:
    """Final counts available after a parser session is fully consumed."""

    files_discovered: int
    chunks_emitted: int
    market_counts: tuple[StooqHistoryMarketParseCounts, ...]
    issue_samples: tuple[ImportIssue, ...] = ()
    empty_files_skipped: int = 0

    def __post_init__(self) -> None:
        _nonnegative_int("files_discovered", self.files_discovered)
        _nonnegative_int("chunks_emitted", self.chunks_emitted)
        _nonnegative_int("empty_files_skipped", self.empty_files_skipped)
        if not isinstance(self.market_counts, tuple) or any(
            not isinstance(item, StooqHistoryMarketParseCounts)
            for item in self.market_counts
        ):
            raise TypeError(
                "market_counts must contain StooqHistoryMarketParseCounts records."
            )
        if not self.market_counts:
            raise ValueError("market_counts must not be empty.")
        if not isinstance(self.issue_samples, tuple) or any(
            not isinstance(issue, ImportIssue) for issue in self.issue_samples
        ):
            raise TypeError("issue_samples must contain ImportIssue records.")
        if len(self.issue_samples) > MAX_ISSUE_SAMPLES:
            raise ValueError(
                f"issue_samples must contain at most {MAX_ISSUE_SAMPLES} issues."
            )

    @property
    def files_completed(self) -> int:
        return sum(item.files_completed for item in self.market_counts)

    @property
    def input_rows(self) -> int:
        return sum(item.input_rows for item in self.market_counts)

    @property
    def date_filtered_rows(self) -> int:
        return sum(item.date_filtered_rows for item in self.market_counts)

    @property
    def accepted_records(self) -> int:
        return sum(item.accepted_records for item in self.market_counts)

    @property
    def rejected_records(self) -> int:
        return sum(item.rejected_records for item in self.market_counts)

    @property
    def rejected_rows(self) -> int:
        return sum(item.rejected_rows for item in self.market_counts)

    @property
    def duplicate_rows_collapsed(self) -> int:
        return sum(
            item.duplicate_rows_collapsed for item in self.market_counts
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_discovered": self.files_discovered,
            "files_completed": self.files_completed,
            "chunks_emitted": self.chunks_emitted,
            "input_rows": self.input_rows,
            "date_filtered_rows": self.date_filtered_rows,
            "accepted_records": self.accepted_records,
            "rejected_records": self.rejected_records,
            "rejected_rows": self.rejected_rows,
            "duplicate_rows_collapsed": self.duplicate_rows_collapsed,
            "empty_files_skipped": self.empty_files_skipped,
            "market_counts": [item.to_dict() for item in self.market_counts],
            "issue_samples": [item.to_dict() for item in self.issue_samples],
        }


@dataclass(frozen=True)
class StooqHistoryChunk:
    """One bounded, deterministic collection of shared listing batches."""

    chunk_number: int
    batches: tuple[ParsedListingBatch, ...]

    def __post_init__(self) -> None:
        if isinstance(self.chunk_number, bool) or not isinstance(
            self.chunk_number, int
        ):
            raise TypeError("chunk_number must be an integer.")
        if self.chunk_number <= 0:
            raise ValueError("chunk_number must be greater than zero.")
        if not isinstance(self.batches, tuple) or any(
            not isinstance(batch, ParsedListingBatch) for batch in self.batches
        ):
            raise TypeError("batches must contain ParsedListingBatch records.")
        if not self.batches:
            raise ValueError("batches must not be empty.")

    @property
    def bar_count(self) -> int:
        return sum(batch.bar_count for batch in self.batches)


@dataclass
class _MutableMarketCounts:
    files_completed: int = 0
    input_rows: int = 0
    date_filtered_rows: int = 0
    accepted_records: int = 0
    rejected_records: int = 0
    rejected_rows: int = 0
    duplicate_rows_collapsed: int = 0


@dataclass
class _DateGroup:
    first_bar: DailyBar
    row_count: int = 1
    conflicting: bool = False


class StooqHistoryParser:
    """One-shot iterable that streams deterministic, bounded parse chunks."""

    def __init__(
        self,
        archive_path: str | Path,
        *,
        scope: StooqHistoryScope,
        chunk_size: int,
        progress_callback: Callable[[StooqHistoryParseProgress], None] | None = None,
    ) -> None:
        if not isinstance(scope, StooqHistoryScope):
            raise TypeError("scope must be a StooqHistoryScope.")
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
            raise TypeError("chunk_size must be an integer.")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero.")
        if progress_callback is not None and not callable(progress_callback):
            raise TypeError("progress_callback must be callable or None.")
        self.archive_path = _validated_archive_path(archive_path)
        self.scope = scope
        self.chunk_size = chunk_size
        self.discovery = inspect_stooq_history_archive(
            self.archive_path,
            scope=scope,
        )
        self.progress_callback = progress_callback
        self._started = False
        self._summary: StooqHistoryParseSummary | None = None
        self._progress = StooqHistoryParseProgress(
            files_discovered=self.discovery.selected_member_count,
            empty_files_skipped=self.discovery.empty_files_skipped,
        )

    @property
    def progress(self) -> StooqHistoryParseProgress:
        return self._progress

    @property
    def summary(self) -> StooqHistoryParseSummary:
        if self._summary is None:
            raise RuntimeError(
                "summary is available only after complete parser consumption."
            )
        return self._summary

    def __iter__(self) -> Iterator[StooqHistoryChunk]:
        if self._started:
            raise RuntimeError("StooqHistoryParser is a one-shot iterable.")
        self._started = True
        return self._iter_chunks()

    def _iter_chunks(self) -> Iterator[StooqHistoryChunk]:
        counts = {
            market: _MutableMarketCounts() for market in self.scope.markets
        }
        issues: list[ImportIssue] = []
        pending: list[ParsedListingBatch] = []
        pending_bars = 0
        chunk_number = 0

        try:
            with ZipFile(self.archive_path) as archive:
                for member in self.discovery.members:
                    listing, bars = _parse_member(
                        archive,
                        member=member,
                        scope=self.scope,
                        counts=counts[member.market],
                        issues=issues,
                    )
                    counts[member.market].files_completed += 1
                    self._progress = _parse_progress(
                        files_discovered=self.discovery.selected_member_count,
                        counts=counts,
                        chunks_emitted=chunk_number,
                        current_member=member.member_path,
                        empty_files_skipped=(
                            self.discovery.empty_files_skipped
                        ),
                    )
                    if (
                        self.progress_callback is not None
                        and self._progress.files_completed
                        % PROGRESS_FILE_INTERVAL
                        == 0
                    ):
                        self.progress_callback(self._progress)

                    offset = 0
                    while offset < len(bars):
                        available = self.chunk_size - pending_bars
                        selected = bars[offset : offset + available]
                        pending.append(
                            ParsedListingBatch(
                                listing=listing,
                                bars=selected,
                            )
                        )
                        pending_bars += len(selected)
                        offset += len(selected)
                        if pending_bars == self.chunk_size:
                            chunk_number += 1
                            self._progress = _parse_progress(
                                files_discovered=(
                                    self.discovery.selected_member_count
                                ),
                                counts=counts,
                                chunks_emitted=chunk_number,
                                current_member=member.member_path,
                                empty_files_skipped=(
                                    self.discovery.empty_files_skipped
                                ),
                            )
                            yield StooqHistoryChunk(
                                chunk_number=chunk_number,
                                batches=tuple(pending),
                            )
                            pending = []
                            pending_bars = 0

                if pending:
                    chunk_number += 1
                    self._progress = _parse_progress(
                        files_discovered=self.discovery.selected_member_count,
                        counts=counts,
                        chunks_emitted=chunk_number,
                        current_member=(
                            self.discovery.members[-1].member_path
                        ),
                        empty_files_skipped=(
                            self.discovery.empty_files_skipped
                        ),
                    )
                    yield StooqHistoryChunk(
                        chunk_number=chunk_number,
                        batches=tuple(pending),
                    )

        except OHLCVParseError:
            raise
        except (BadZipFile, OSError, RuntimeError, UnicodeError) as exc:
            raise OHLCVParseError(
                "Stooq history archive could not be read safely."
            ) from exc

        market_counts = tuple(
            StooqHistoryMarketParseCounts(
                market=market,
                files_completed=value.files_completed,
                input_rows=value.input_rows,
                date_filtered_rows=value.date_filtered_rows,
                accepted_records=value.accepted_records,
                rejected_records=value.rejected_records,
                rejected_rows=value.rejected_rows,
                duplicate_rows_collapsed=value.duplicate_rows_collapsed,
            )
            for market, value in counts.items()
        )
        summary = StooqHistoryParseSummary(
            files_discovered=self.discovery.selected_member_count,
            chunks_emitted=chunk_number,
            market_counts=market_counts,
            issue_samples=tuple(issues),
            empty_files_skipped=self.discovery.empty_files_skipped,
        )
        if summary.accepted_records == 0:
            raise OHLCVParseError(
                "Stooq history scope did not contain any accepted bars."
            )
        self._summary = summary
        self._progress = StooqHistoryParseProgress(
            files_discovered=summary.files_discovered,
            files_completed=summary.files_completed,
            chunks_emitted=summary.chunks_emitted,
            input_rows=summary.input_rows,
            date_filtered_rows=summary.date_filtered_rows,
            accepted_records=summary.accepted_records,
            rejected_records=summary.rejected_records,
            rejected_rows=summary.rejected_rows,
            duplicate_rows_collapsed=summary.duplicate_rows_collapsed,
            current_member=self.discovery.members[-1].member_path,
            empty_files_skipped=summary.empty_files_skipped,
        )


def _parse_progress(
    *,
    files_discovered: int,
    counts: dict[str, _MutableMarketCounts],
    chunks_emitted: int,
    current_member: str,
    empty_files_skipped: int,
) -> StooqHistoryParseProgress:
    values = tuple(counts.values())
    return StooqHistoryParseProgress(
        files_discovered=files_discovered,
        files_completed=sum(item.files_completed for item in values),
        chunks_emitted=chunks_emitted,
        input_rows=sum(item.input_rows for item in values),
        date_filtered_rows=sum(item.date_filtered_rows for item in values),
        accepted_records=sum(item.accepted_records for item in values),
        rejected_records=sum(item.rejected_records for item in values),
        rejected_rows=sum(item.rejected_rows for item in values),
        duplicate_rows_collapsed=sum(
            item.duplicate_rows_collapsed for item in values
        ),
        current_member=current_member,
        empty_files_skipped=empty_files_skipped,
    )


def inspect_stooq_history_archive(
    archive_path: str | Path,
    *,
    scope: StooqHistoryScope,
) -> StooqHistoryDiscovery:
    """Inspect and select archive members without decompressing their rows."""

    if not isinstance(scope, StooqHistoryScope):
        raise TypeError("scope must be a StooqHistoryScope.")
    path = _validated_archive_path(archive_path)
    archive_size = path.stat().st_size
    if archive_size > MAX_ARCHIVE_BYTES:
        raise OHLCVParseError("Stooq history archive exceeds the size limit.")

    try:
        with ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_MEMBERS:
                raise OHLCVParseError(
                    "Stooq history archive exceeds the member limit."
                )
            selected, empty_files_skipped = _select_members(infos, scope=scope)
    except OHLCVParseError:
        raise
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise OHLCVParseError(
            "Stooq history archive could not be inspected safely."
        ) from exc

    selected_bytes = sum(member.uncompressed_bytes for member in selected)
    if len(selected) > MAX_SELECTED_MEMBERS:
        raise OHLCVParseError(
            "Stooq history scope exceeds the selected-member limit."
        )
    if selected_bytes > MAX_SELECTED_UNCOMPRESSED_BYTES:
        raise OHLCVParseError(
            "Stooq history scope exceeds the uncompressed-size limit."
        )
    if not selected:
        raise OHLCVParseError(
            "Stooq history filters did not select any stock members."
        )
    return StooqHistoryDiscovery(
        archive_size_bytes=archive_size,
        archive_member_count=len(infos),
        selected_uncompressed_bytes=selected_bytes,
        members=tuple(selected),
        empty_files_skipped=empty_files_skipped,
    )


def _validated_archive_path(archive_path: str | Path) -> Path:
    if not isinstance(archive_path, (str, Path)):
        raise TypeError("archive_path must be a string or Path.")
    path = Path(archive_path).expanduser().resolve()
    if not path.is_file():
        raise OHLCVParseError(
            "Stooq history archive must be an existing regular file."
        )
    if path.name not in {
        STOOQ_HISTORY_ARCHIVE_NAME,
        STOOQ_HISTORY_CORE_ARCHIVE_NAME,
    }:
        raise OHLCVParseError(
            f"Stooq history archive must be named {STOOQ_HISTORY_ARCHIVE_NAME} "
            f"(operator) or {STOOQ_HISTORY_CORE_ARCHIVE_NAME} (Core)."
        )
    return path


def _select_members(
    infos: list[ZipInfo],
    *,
    scope: StooqHistoryScope,
) -> tuple[list[StooqHistoryMember], int]:
    seen_paths: set[str] = set()
    seen_identities: set[tuple[str, str]] = set()
    selected: list[StooqHistoryMember] = []
    empty_files_skipped = 0
    selected_markets = set(scope.markets)
    selected_tickers = set(scope.tickers)
    stock_members_by_market = {
        market: 0 for market in STOOQ_HISTORY_MARKETS
    }

    for info in infos:
        member_path = _validated_member_path(info)
        if member_path in seen_paths:
            raise OHLCVParseError(
                "Stooq history archive contains duplicate member paths."
            )
        seen_paths.add(member_path)

        identity = _selected_member_identity(member_path)
        if identity is None:
            continue
        market, ticker = identity
        stock_members_by_market[market] += 1
        if market not in selected_markets:
            continue
        if selected_tickers and ticker not in selected_tickers:
            continue
        if info.file_size <= 0:
            empty_files_skipped += 1
            continue
        if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
            raise OHLCVParseError(
                "Stooq history archive contains an oversized selected member."
            )
        key = (market, ticker)
        if key in seen_identities:
            raise OHLCVParseError(
                "Stooq history archive contains duplicate series members."
            )
        seen_identities.add(key)
        selected.append(
            StooqHistoryMember(
                member_path=member_path,
                market=market,
                ticker=ticker,
                uncompressed_bytes=info.file_size,
            )
        )

    if any(count == 0 for count in stock_members_by_market.values()):
        raise OHLCVParseError(
            "Stooq history archive is missing a required stock market directory."
        )
    return (
        sorted(selected, key=lambda member: member.member_path),
        empty_files_skipped,
    )


def _validated_member_path(info: ZipInfo) -> str:
    name = info.filename
    if not name or "\\" in name or name.startswith("/"):
        raise OHLCVParseError(
            "Stooq history archive contains an unsafe member path."
        )
    raw_parts = name.rstrip("/").split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        raise OHLCVParseError(
            "Stooq history archive contains an unsafe member path."
        )
    path = PurePosixPath(name)
    if info.flag_bits & 0x1:
        raise OHLCVParseError(
            "Stooq history archive contains an encrypted member."
        )
    unix_mode = info.external_attr >> 16
    file_type = stat.S_IFMT(unix_mode)
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise OHLCVParseError(
            "Stooq history archive contains a special-file member."
        )
    return path.as_posix()


def _market_directory(member_path: str) -> str | None:
    parts = PurePosixPath(member_path).parts
    if len(parts) < 4 or parts[:3] != _ARCHIVE_PREFIX:
        return None
    directory = parts[3]
    for market in STOOQ_HISTORY_MARKETS:
        if directory == f"{market} stocks":
            return market
    return None


def _selected_member_identity(member_path: str) -> tuple[str, str] | None:
    path = PurePosixPath(member_path)
    market = _market_directory(member_path)
    if market is None or path.suffix != ".txt" or len(path.parts) < 5:
        return None
    intermediate = path.parts[4:-1]
    if any(not part.isdigit() for part in intermediate):
        return None
    stem = path.name.removesuffix(".txt")
    if not stem or not stem.lower().endswith(".us"):
        return None
    ticker = stem.upper()
    return market, ticker


def _parse_member(
    archive: ZipFile,
    *,
    member: StooqHistoryMember,
    scope: StooqHistoryScope,
    counts: _MutableMarketCounts,
    issues: list[ImportIssue],
) -> tuple[ProviderListing, tuple[DailyBar, ...]]:
    listing = ProviderListing(
        provider_code=STOOQ_HISTORY_PROVIDER_CODE,
        market=member.market,
        ticker=member.ticker,
    )
    groups: dict[date, _DateGroup] = {}
    invalid_records = 0
    invalid_rows = 0
    member_rows = 0

    try:
        with archive.open(member.member_path) as raw:
            lines = (line.decode("utf-8") for line in raw)
            reader = csv.reader(lines)
            header = next(reader, None)
            if tuple(header or ()) != STOOQ_HISTORY_HEADER:
                raise OHLCVParseError(
                    "Stooq history member has an invalid CSV header."
                )
            for line_number, row in enumerate(reader, start=2):
                member_rows += 1
                counts.input_rows += 1
                parsed = _parse_row(
                    row,
                    expected_ticker=member.ticker,
                    effective_date=scope.effective_date,
                )
                if isinstance(parsed, str):
                    if parsed == "stooq_invalid_ticker":
                        raise OHLCVParseError(
                            "Stooq history member ticker does not match its filename."
                        )
                    invalid_records += 1
                    invalid_rows += 1
                    _sample_issue(
                        issues,
                        code=parsed,
                        market=member.market,
                        ticker=member.ticker,
                        line_number=line_number,
                    )
                    continue
                if (
                    scope.start_date is not None
                    and parsed.trading_date < scope.start_date
                    or scope.end_date is not None
                    and parsed.trading_date > scope.end_date
                ):
                    counts.date_filtered_rows += 1
                    continue
                group = groups.get(parsed.trading_date)
                if group is None:
                    groups[parsed.trading_date] = _DateGroup(first_bar=parsed)
                    continue
                group.row_count += 1
                if parsed != group.first_bar:
                    group.conflicting = True
    except OHLCVParseError:
        raise
    except (OSError, RuntimeError, UnicodeError, csv.Error) as exc:
        raise OHLCVParseError(
            "Stooq history member could not be read safely."
        ) from exc

    if member_rows == 0:
        raise OHLCVParseError(
            "Stooq history member does not contain any data rows."
        )

    bars: list[DailyBar] = []
    for trading_date in sorted(groups):
        group = groups[trading_date]
        if group.conflicting:
            counts.rejected_records += 1
            counts.rejected_rows += group.row_count
            _sample_issue(
                issues,
                code="stooq_conflicting_duplicate",
                market=member.market,
                ticker=member.ticker,
                trading_date=trading_date,
            )
        else:
            bars.append(group.first_bar)
            counts.accepted_records += 1
            counts.duplicate_rows_collapsed += group.row_count - 1

    counts.rejected_records += invalid_records
    counts.rejected_rows += invalid_rows
    return listing, tuple(bars)


def _parse_row(
    row: list[str],
    *,
    expected_ticker: str,
    effective_date: date,
) -> DailyBar | str:
    if len(row) != len(STOOQ_HISTORY_HEADER):
        return "stooq_invalid_column_count"
    (
        ticker,
        period,
        date_text,
        _time,
        open_text,
        high_text,
        low_text,
        close_text,
        volume_text,
        _open_interest,
    ) = row
    if ticker != expected_ticker:
        return "stooq_invalid_ticker"
    if period != "D":
        return "stooq_invalid_period"
    if len(date_text) != 8 or not date_text.isascii() or not date_text.isdigit():
        return "stooq_invalid_date"
    numeric_texts = (open_text, high_text, low_text, close_text, volume_text)
    if any(not value or value != value.strip() for value in numeric_texts):
        return "stooq_invalid_number"
    try:
        trading_date = date(
            int(date_text[0:4]),
            int(date_text[4:6]),
            int(date_text[6:8]),
        )
        if trading_date > effective_date:
            return "stooq_future_date"
        bar = DailyBar(
            trading_date=trading_date,
            open=Decimal(open_text),
            high=Decimal(high_text),
            low=Decimal(low_text),
            close=Decimal(close_text),
            volume=Decimal(volume_text),
        )
    except (InvalidOperation, TypeError, ValueError):
        return "stooq_invalid_ohlcv"
    return bar


def _sample_issue(
    issues: list[ImportIssue],
    *,
    code: str,
    market: str,
    ticker: str,
    line_number: int | None = None,
    trading_date: date | None = None,
) -> None:
    if len(issues) >= MAX_ISSUE_SAMPLES:
        return
    if line_number is not None:
        reference = f"{market}:{ticker}:line:{line_number}"
    else:
        assert trading_date is not None
        reference = f"{market}:{ticker}:{trading_date.isoformat()}"
    issues.append(
        ImportIssue(
            code=code,
            message="Stooq historical row was rejected.",
            source_code=STOOQ_HISTORY_SOURCE.source_code,
            record_reference=reference,
        )
    )
