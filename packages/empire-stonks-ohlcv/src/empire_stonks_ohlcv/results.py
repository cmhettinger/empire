"""JSON-ready batch and result records for OHLCV provider workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from empire_stonks_ohlcv.models import DailyBar, ProviderListing


_SOURCE_CODE_PATTERN = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
_PARSER_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _validate_required_text(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value or not value.strip():
        raise ValueError(f"{field_name} is required.")
    if value != value.strip():
        raise ValueError(
            f"{field_name} must not contain leading or trailing whitespace."
        )


def _validate_nonnegative_int(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")


@dataclass(frozen=True)
class AcquiredObject:
    """Durable reference to one provider source object stored through Core."""

    source_code: str
    object_id: UUID
    object_key: str
    filename: str
    size_bytes: int
    checksum_sha256: str

    def __post_init__(self) -> None:
        _validate_required_text("source_code", self.source_code)
        if not isinstance(self.object_id, UUID):
            raise TypeError("object_id must be a UUID.")
        _validate_required_text("object_key", self.object_key)
        _validate_required_text("filename", self.filename)
        _validate_nonnegative_int("size_bytes", self.size_bytes)
        _validate_required_text("checksum_sha256", self.checksum_sha256)

    def to_dict(self) -> dict[str, str | int]:
        return {
            "source_code": self.source_code,
            "object_id": str(self.object_id),
            "object_key": self.object_key,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "checksum_sha256": self.checksum_sha256,
        }


@dataclass(frozen=True)
class ParsedListingBatch:
    """Parsed bars associated with one exact provider listing series."""

    listing: ProviderListing
    bars: tuple[DailyBar, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.listing, ProviderListing):
            raise TypeError("listing must be a ProviderListing.")
        if not isinstance(self.bars, tuple):
            raise TypeError("bars must be a tuple.")
        if any(not isinstance(bar, DailyBar) for bar in self.bars):
            raise TypeError("bars must contain only DailyBar records.")

    @property
    def bar_count(self) -> int:
        return len(self.bars)

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing": self.listing.to_dict(),
            "bar_count": self.bar_count,
            "bars": [bar.to_dict() for bar in self.bars],
        }


@dataclass(frozen=True)
class ProviderSourceMetadata:
    """Stable source identity needed to interpret and persist parsed output."""

    source_code: str
    parser_version: str

    def __post_init__(self) -> None:
        _validate_required_text("source_code", self.source_code)
        _validate_required_text("parser_version", self.parser_version)
        if len(self.source_code) > 64 or not _SOURCE_CODE_PATTERN.fullmatch(
            self.source_code
        ):
            raise ValueError("source_code must be a lowercase path-safe identifier.")
        if len(self.parser_version) > 64 or not _PARSER_VERSION_PATTERN.fullmatch(
            self.parser_version
        ):
            raise ValueError("parser_version must be a path-safe identifier.")

    def to_dict(self) -> dict[str, str]:
        return {
            "source_code": self.source_code,
            "parser_version": self.parser_version,
        }


@dataclass(frozen=True)
class ParsedProviderOutput:
    """Minimal provider parser output shared by every provider adapter."""

    sources: tuple[ProviderSourceMetadata, ...]
    batches: tuple[ParsedListingBatch, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.sources, tuple) or any(
            not isinstance(item, ProviderSourceMetadata) for item in self.sources
        ):
            raise TypeError(
                "sources must contain only ProviderSourceMetadata records."
            )
        if not self.sources:
            raise ValueError("sources must not be empty.")
        source_codes = [source.source_code for source in self.sources]
        if len(set(source_codes)) != len(source_codes):
            raise ValueError("sources must contain unique source_code values.")
        if not isinstance(self.batches, tuple) or any(
            not isinstance(item, ParsedListingBatch) for item in self.batches
        ):
            raise TypeError("batches must contain only ParsedListingBatch records.")

    @property
    def listing_count(self) -> int:
        return len(self.batches)

    @property
    def bar_count(self) -> int:
        return sum(batch.bar_count for batch in self.batches)

    def parser_version_for(self, source_code: str) -> str:
        for source in self.sources:
            if source.source_code == source_code:
                return source.parser_version
        raise KeyError(source_code)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": [source.to_dict() for source in self.sources],
            "listing_count": self.listing_count,
            "bar_count": self.bar_count,
            "batches": [batch.to_dict() for batch in self.batches],
        }


@dataclass(frozen=True)
class PersistenceCounts:
    """Disjoint current-state write outcomes for one accepted input set."""

    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    derived_updated: int = 0

    def __post_init__(self) -> None:
        _validate_nonnegative_int("inserted", self.inserted)
        _validate_nonnegative_int("updated", self.updated)
        _validate_nonnegative_int("unchanged", self.unchanged)
        _validate_nonnegative_int("derived_updated", self.derived_updated)

    @property
    def input_count(self) -> int:
        """Count accepted inputs, excluding derived-only maintenance."""

        return self.inserted + self.updated + self.unchanged

    def to_dict(self) -> dict[str, int]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "derived_updated": self.derived_updated,
        }


@dataclass(frozen=True)
class ImportIssue:
    """One structured failure or warning description."""

    code: str
    message: str
    source_code: str | None = None
    record_reference: str | None = None

    def __post_init__(self) -> None:
        _validate_required_text("code", self.code)
        _validate_required_text("message", self.message)
        if self.source_code is not None:
            _validate_required_text("source_code", self.source_code)
        if self.record_reference is not None:
            _validate_required_text("record_reference", self.record_reference)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "message": self.message,
            "source_code": self.source_code,
            "record_reference": self.record_reference,
        }


@dataclass(frozen=True)
class ProviderImportResult:
    """Compact provider import outcome suitable for reports and run summaries."""

    provider_code: str
    acquired_objects: tuple[AcquiredObject, ...] = ()
    listing_counts: PersistenceCounts = field(default_factory=PersistenceCounts)
    bar_counts: PersistenceCounts = field(default_factory=PersistenceCounts)
    rejected: int = 0
    failures: tuple[ImportIssue, ...] = ()
    warnings: tuple[ImportIssue, ...] = ()

    def __post_init__(self) -> None:
        _validate_required_text("provider_code", self.provider_code)
        if self.provider_code != self.provider_code.upper():
            raise ValueError("provider_code must be uppercase.")
        if not isinstance(self.acquired_objects, tuple) or any(
            not isinstance(item, AcquiredObject) for item in self.acquired_objects
        ):
            raise TypeError(
                "acquired_objects must contain only AcquiredObject records."
            )
        if not isinstance(self.listing_counts, PersistenceCounts):
            raise TypeError("listing_counts must be PersistenceCounts.")
        if not isinstance(self.bar_counts, PersistenceCounts):
            raise TypeError("bar_counts must be PersistenceCounts.")
        _validate_nonnegative_int("rejected", self.rejected)
        self._validate_issues("failures", self.failures)
        self._validate_issues("warnings", self.warnings)

    @staticmethod
    def _validate_issues(field_name: str, value: object) -> None:
        if not isinstance(value, tuple) or any(
            not isinstance(item, ImportIssue) for item in value
        ):
            raise TypeError(f"{field_name} must contain only ImportIssue records.")

    @property
    def accepted(self) -> int:
        return self.bar_counts.input_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_code": self.provider_code,
            "acquired_objects": [item.to_dict() for item in self.acquired_objects],
            "listing_counts": self.listing_counts.to_dict(),
            "bar_counts": self.bar_counts.to_dict(),
            "accepted": self.accepted,
            "rejected": self.rejected,
            "failure_count": len(self.failures),
            "warning_count": len(self.warnings),
            "failures": [issue.to_dict() for issue in self.failures],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }
