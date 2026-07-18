"""Shared validation, issue-sampling, and scoped-count records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from empire_stonks_ohlcv.results import (
    ImportIssue,
    ParsedProviderOutput,
    PersistenceCounts,
)


MAX_ISSUE_SAMPLES = 100
_SOURCE_CODE_PATTERN = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
_RECORD_KINDS = frozenset({"listing", "bar"})


def _validate_text(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value or not value.strip() or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty and trimmed.")


def _validate_count(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")


@dataclass(frozen=True)
class BoundedIssueSummary:
    """A total issue count with at most the shared safe sample limit."""

    total_count: int = 0
    samples: tuple[ImportIssue, ...] = ()

    def __post_init__(self) -> None:
        _validate_count("total_count", self.total_count)
        if not isinstance(self.samples, tuple) or any(
            not isinstance(issue, ImportIssue) for issue in self.samples
        ):
            raise TypeError("samples must contain only ImportIssue records.")
        if len(self.samples) > MAX_ISSUE_SAMPLES:
            raise ValueError(
                f"samples must contain at most {MAX_ISSUE_SAMPLES} issues."
            )
        if len(self.samples) > self.total_count:
            raise ValueError("samples cannot exceed total_count.")

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def truncated(self) -> bool:
        return self.sample_count < self.total_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_count": self.total_count,
            "sample_count": self.sample_count,
            "truncated": self.truncated,
            "samples": [issue.to_dict() for issue in self.samples],
        }


@dataclass(frozen=True)
class RowRejectionSummary:
    """One market/source/reason bucket of safely rejected provider records."""

    source_code: str
    market: str
    code: str
    rejected_records: int
    rejected_rows: int
    samples: tuple[ImportIssue, ...] = ()

    def __post_init__(self) -> None:
        _validate_text("source_code", self.source_code)
        if not _SOURCE_CODE_PATTERN.fullmatch(self.source_code):
            raise ValueError("source_code must be lowercase and path-safe.")
        _validate_text("market", self.market)
        _validate_text("code", self.code)
        _validate_count("rejected_records", self.rejected_records)
        _validate_count("rejected_rows", self.rejected_rows)
        if self.rejected_records == 0 or self.rejected_rows == 0:
            raise ValueError("row rejection counts must be positive.")
        if not isinstance(self.samples, tuple) or any(
            not isinstance(issue, ImportIssue) for issue in self.samples
        ):
            raise TypeError("samples must contain only ImportIssue records.")
        if len(self.samples) > MAX_ISSUE_SAMPLES:
            raise ValueError(
                f"samples must contain at most {MAX_ISSUE_SAMPLES} issues."
            )
        if len(self.samples) > self.rejected_records:
            raise ValueError("samples cannot exceed rejected_records.")
        if any(
            issue.code != self.code or issue.source_code != self.source_code
            for issue in self.samples
        ):
            raise ValueError("samples must match the rejection code and source.")

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def truncated(self) -> bool:
        return self.sample_count < self.rejected_records

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_code": self.source_code,
            "market": self.market,
            "code": self.code,
            "rejected_records": self.rejected_records,
            "rejected_rows": self.rejected_rows,
            "sample_count": self.sample_count,
            "truncated": self.truncated,
            "samples": [issue.to_dict() for issue in self.samples],
        }


@dataclass(frozen=True)
class FeedOutcomeCounts:
    """Parse/validation outcomes for one source and market partition."""

    source_code: str
    market: str
    input_rows: int = 0
    accepted_records: int = 0
    rejected_records: int = 0
    duplicate_rows_collapsed: int = 0
    warning_count: int = 0

    def __post_init__(self) -> None:
        _validate_text("source_code", self.source_code)
        if not _SOURCE_CODE_PATTERN.fullmatch(self.source_code):
            raise ValueError("source_code must be lowercase and path-safe.")
        _validate_text("market", self.market)
        for field_name in (
            "input_rows",
            "accepted_records",
            "rejected_records",
            "duplicate_rows_collapsed",
            "warning_count",
        ):
            _validate_count(field_name, getattr(self, field_name))
        if self.accepted_records + self.rejected_records > self.input_rows:
            raise ValueError(
                "accepted_records plus rejected_records cannot exceed input_rows."
            )
        if self.duplicate_rows_collapsed > self.input_rows:
            raise ValueError(
                "duplicate_rows_collapsed cannot exceed input_rows."
            )

    def to_dict(self) -> dict[str, str | int]:
        return {
            "source_code": self.source_code,
            "market": self.market,
            "input_rows": self.input_rows,
            "accepted_records": self.accepted_records,
            "rejected_records": self.rejected_records,
            "duplicate_rows_collapsed": self.duplicate_rows_collapsed,
            "warning_count": self.warning_count,
        }


@dataclass(frozen=True)
class SourceMarketWriteCounts:
    """Persistence outcomes for one source, market, and record kind."""

    source_code: str
    market: str
    record_kind: str
    counts: PersistenceCounts
    skipped_inactive: int = 0

    def __post_init__(self) -> None:
        _validate_text("source_code", self.source_code)
        if not _SOURCE_CODE_PATTERN.fullmatch(self.source_code):
            raise ValueError("source_code must be lowercase and path-safe.")
        _validate_text("market", self.market)
        if self.record_kind not in _RECORD_KINDS:
            raise ValueError("record_kind must be listing or bar.")
        if not isinstance(self.counts, PersistenceCounts):
            raise TypeError("counts must be PersistenceCounts.")
        _validate_count("skipped_inactive", self.skipped_inactive)
        if self.record_kind == "listing" and self.skipped_inactive:
            raise ValueError(
                "skipped_inactive applies only to bar write counts."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_code": self.source_code,
            "market": self.market,
            "record_kind": self.record_kind,
            "counts": self.counts.to_dict(),
            "skipped_inactive": self.skipped_inactive,
        }


@dataclass(frozen=True)
class CrossFeedOutcomeCounts:
    """Reconciliation outcomes between listing discovery and bar feeds."""

    market: str
    listings_without_bars: int = 0
    bars_without_listings: int = 0

    def __post_init__(self) -> None:
        _validate_text("market", self.market)
        _validate_count("listings_without_bars", self.listings_without_bars)
        _validate_count("bars_without_listings", self.bars_without_listings)

    def to_dict(self) -> dict[str, str | int]:
        return {
            "market": self.market,
            "listings_without_bars": self.listings_without_bars,
            "bars_without_listings": self.bars_without_listings,
        }


@dataclass(frozen=True)
class ProviderValidationResult:
    """Accepted shared output plus scoped outcomes and bounded issues."""

    output: ParsedProviderOutput
    feed_counts: tuple[FeedOutcomeCounts, ...]
    row_rejections: tuple[RowRejectionSummary, ...] = ()
    failures: BoundedIssueSummary = BoundedIssueSummary()
    warnings: BoundedIssueSummary = BoundedIssueSummary()
    cross_feed_counts: CrossFeedOutcomeCounts | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.output, ParsedProviderOutput):
            raise TypeError("output must be a ParsedProviderOutput.")
        if not isinstance(self.feed_counts, tuple) or any(
            not isinstance(item, FeedOutcomeCounts) for item in self.feed_counts
        ):
            raise TypeError(
                "feed_counts must contain only FeedOutcomeCounts records."
            )
        if not self.feed_counts:
            raise ValueError("feed_counts must not be empty.")
        keys = [(item.source_code, item.market) for item in self.feed_counts]
        if len(set(keys)) != len(keys):
            raise ValueError("feed_counts must have unique source/market keys.")
        output_sources = {source.source_code for source in self.output.sources}
        count_sources = {item.source_code for item in self.feed_counts}
        if count_sources != output_sources:
            raise ValueError(
                "feed_counts sources must exactly match parsed output sources."
            )
        if not isinstance(self.failures, BoundedIssueSummary):
            raise TypeError("failures must be a BoundedIssueSummary.")
        if not isinstance(self.row_rejections, tuple) or any(
            not isinstance(item, RowRejectionSummary)
            for item in self.row_rejections
        ):
            raise TypeError(
                "row_rejections must contain only RowRejectionSummary records."
            )
        rejection_keys = [
            (item.source_code, item.market, item.code)
            for item in self.row_rejections
        ]
        if len(set(rejection_keys)) != len(rejection_keys):
            raise ValueError("row_rejections must have unique scope/reason keys.")
        if sum(item.rejected_records for item in self.row_rejections) != sum(
            item.rejected_records for item in self.feed_counts
        ):
            raise ValueError(
                "row_rejections must match feed rejected-record counts."
            )
        if not isinstance(self.warnings, BoundedIssueSummary):
            raise TypeError("warnings must be a BoundedIssueSummary.")
        if self.cross_feed_counts is not None and not isinstance(
            self.cross_feed_counts,
            CrossFeedOutcomeCounts,
        ):
            raise TypeError(
                "cross_feed_counts must be CrossFeedOutcomeCounts or None."
            )
        if self.cross_feed_counts is not None:
            markets = {item.market for item in self.feed_counts}
            if markets != {self.cross_feed_counts.market}:
                raise ValueError(
                    "cross_feed_counts market must match the feed-count market."
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": [source.to_dict() for source in self.output.sources],
            "listing_count": self.output.listing_count,
            "bar_count": self.output.bar_count,
            "feed_counts": [item.to_dict() for item in self.feed_counts],
            "row_rejections": [
                item.to_dict() for item in self.row_rejections
            ],
            "failures": self.failures.to_dict(),
            "warnings": self.warnings.to_dict(),
            "cross_feed_counts": (
                None
                if self.cross_feed_counts is None
                else self.cross_feed_counts.to_dict()
            ),
        }
