"""Deterministic P0.7 affected-range planning for technical indicators."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Iterable
from uuid import UUID

from empire_stonks_tech_indicators.models import ReasonCount
from empire_stonks_tech_indicators.queries import EligibleListing
from empire_stonks_tech_indicators.state import ListingStateComparison
from empire_stonks_tech_indicators.subject_policy import (
    is_spx_supported_subject,
)


class AffectedRangeReason(StrEnum):
    """Frozen P0.7 reasons that create calculated feature-row work."""

    TAIL_APPEND = "TAIL_APPEND"
    MISSING_TECH_ROW = "MISSING_TECH_ROW"
    SOURCE_COPY_DRIFT = "SOURCE_COPY_DRIFT"
    HISTORY_COUNT_DRIFT = "HISTORY_COUNT_DRIFT"
    BENCHMARK_DRIFT = "BENCHMARK_DRIFT"
    VERSION_DRIFT = "VERSION_DRIFT"
    EXPLICIT_REBUILD = "EXPLICIT_REBUILD"


_REASON_ORDER = tuple(AffectedRangeReason)
_REASON_INDEX = {reason: index for index, reason in enumerate(_REASON_ORDER)}


@dataclass(frozen=True)
class AffectedRange:
    """One collapsed listing suffix plus its required full-prefix context."""

    provider_listing_id: UUID
    provider_code: str
    market: str
    ticker: str
    status: str
    calculation_start_date: date
    write_start_date: date
    write_end_date: date
    requested_end_date: date
    reasons: tuple[AffectedRangeReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.provider_listing_id, UUID):
            raise TypeError("provider_listing_id must be a UUID.")
        for field_name in ("provider_code", "market", "ticker"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string.")
            if not value or value != value.strip():
                raise ValueError(f"{field_name} must be non-empty and trimmed.")
        if self.status not in {"ACTIVE", "INACTIVE"}:
            raise ValueError("status must be ACTIVE or INACTIVE.")
        for field_name in (
            "calculation_start_date",
            "write_start_date",
            "write_end_date",
            "requested_end_date",
        ):
            if type(getattr(self, field_name)) is not date:
                raise TypeError(f"{field_name} must be a date.")
        if not (
            self.calculation_start_date
            <= self.write_start_date
            <= self.write_end_date
        ):
            raise ValueError(
                "calculation and write dates must form an ordered range."
            )
        if not isinstance(self.reasons, tuple) or not self.reasons:
            raise ValueError("reasons must be a non-empty tuple.")
        if any(
            not isinstance(reason, AffectedRangeReason)
            for reason in self.reasons
        ):
            raise TypeError("reasons must contain only AffectedRangeReason values.")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("reasons must be unique.")
        if self.reasons != tuple(
            sorted(self.reasons, key=_REASON_INDEX.__getitem__)
        ):
            raise ValueError("reasons must use deterministic contract order.")
        if (
            AffectedRangeReason.VERSION_DRIFT in self.reasons
            and self.write_start_date != self.calculation_start_date
        ):
            raise ValueError("Version drift must write from the first source row.")

    @property
    def expanded_beyond_requested_horizon(self) -> bool:
        return self.write_end_date > self.requested_end_date

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "provider_code": self.provider_code,
            "market": self.market,
            "ticker": self.ticker,
            "status": self.status,
            "calculation_start_date": self.calculation_start_date.isoformat(),
            "write_start_date": self.write_start_date.isoformat(),
            "write_end_date": self.write_end_date.isoformat(),
            "requested_end_date": self.requested_end_date.isoformat(),
            "expanded_beyond_requested_horizon": (
                self.expanded_beyond_requested_horizon
            ),
            "reasons": [reason.value for reason in self.reasons],
        }


@dataclass(frozen=True)
class AffectedRangePlan:
    """Bounded summary plus deterministic per-listing affected ranges."""

    requested_start_date: date | None
    requested_end_date: date
    benchmark_drift_start_date: date | None
    selected_listing_count: int
    ranges: tuple[AffectedRange, ...]

    def __post_init__(self) -> None:
        _optional_date("requested_start_date", self.requested_start_date)
        _required_date("requested_end_date", self.requested_end_date)
        _optional_date(
            "benchmark_drift_start_date",
            self.benchmark_drift_start_date,
        )
        if (
            self.requested_start_date is not None
            and self.requested_start_date > self.requested_end_date
        ):
            raise ValueError("requested_start_date must not follow requested_end_date.")
        if type(self.selected_listing_count) is not int:
            raise TypeError("selected_listing_count must be an integer.")
        if self.selected_listing_count < 0:
            raise ValueError("selected_listing_count must be non-negative.")
        if not isinstance(self.ranges, tuple) or any(
            not isinstance(item, AffectedRange) for item in self.ranges
        ):
            raise TypeError("ranges must contain only AffectedRange records.")
        if len(self.ranges) > self.selected_listing_count:
            raise ValueError("ranges cannot exceed selected listings.")
        identities = tuple(_range_identity(item) for item in self.ranges)
        if identities != tuple(sorted(identities)):
            raise ValueError("ranges must use deterministic listing order.")
        if len({item.provider_listing_id for item in self.ranges}) != len(
            self.ranges
        ):
            raise ValueError("ranges must contain unique provider listings.")
        if any(
            item.requested_end_date != self.requested_end_date
            for item in self.ranges
        ):
            raise ValueError("Every range must match the requested end date.")

    @property
    def is_noop(self) -> bool:
        return not self.ranges

    @property
    def expanded_range_count(self) -> int:
        return sum(
            item.expanded_beyond_requested_horizon for item in self.ranges
        )

    @property
    def reason_counts(self) -> tuple[ReasonCount, ...]:
        return tuple(
            ReasonCount(
                reason.value,
                sum(reason in item.reasons for item in self.ranges),
            )
            for reason in _REASON_ORDER
            if any(reason in item.reasons for item in self.ranges)
        )

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "requested_start_date": _date_string(self.requested_start_date),
            "requested_end_date": self.requested_end_date.isoformat(),
            "benchmark_drift_start_date": _date_string(
                self.benchmark_drift_start_date
            ),
            "selected_listing_count": self.selected_listing_count,
            "work_range_count": len(self.ranges),
            "expanded_range_count": self.expanded_range_count,
            "is_noop": self.is_noop,
            "reason_counts": [item.to_dict() for item in self.reason_counts],
        }


def plan_affected_ranges(
    *,
    listings: Iterable[EligibleListing],
    comparisons: Iterable[ListingStateComparison],
    requested_end_date: date,
    requested_start_date: date | None = None,
    benchmark_drift_start_date: date | None = None,
    explicit_rebuild_listing_ids: tuple[UUID, ...] = (),
) -> AffectedRangePlan:
    """Collapse local and benchmark uncertainty into one suffix per listing.

    Comparisons own local current-state drift. ``benchmark_drift_start_date``
    is the earliest changed SPX date from benchmark drift detection. All work
    calculates from the listing's first source observation, but writes only the
    conservative affected suffix. Existing downstream technical rows expand a
    narrowed requested horizon rather than being left stale.
    """

    _required_date("requested_end_date", requested_end_date)
    _optional_date("requested_start_date", requested_start_date)
    _optional_date("benchmark_drift_start_date", benchmark_drift_start_date)
    if (
        requested_start_date is not None
        and requested_start_date > requested_end_date
    ):
        raise ValueError("requested_start_date must not follow requested_end_date.")
    rebuild_ids = _validate_rebuild_ids(explicit_rebuild_listing_ids)
    prepared_listings = _prepare_unique(listings, EligibleListing, "listings")
    prepared_comparisons = _prepare_unique(
        comparisons,
        ListingStateComparison,
        "comparisons",
    )
    listing_by_id = {
        listing.provider_listing_id: listing for listing in prepared_listings
    }
    comparison_by_id = {
        comparison.provider_listing_id: comparison
        for comparison in prepared_comparisons
    }
    if listing_by_id.keys() != comparison_by_id.keys():
        raise ValueError("listings and comparisons must contain the same IDs.")
    if not rebuild_ids <= listing_by_id.keys():
        raise ValueError("explicit rebuild IDs must belong to selected listings.")

    ranges: list[AffectedRange] = []
    for listing in sorted(prepared_listings, key=_listing_identity):
        comparison = comparison_by_id[listing.provider_listing_id]
        _validate_identity(listing, comparison)
        affected = _plan_listing_range(
            listing=listing,
            comparison=comparison,
            requested_start_date=requested_start_date,
            requested_end_date=requested_end_date,
            benchmark_drift_start_date=benchmark_drift_start_date,
            explicit_rebuild=listing.provider_listing_id in rebuild_ids,
        )
        if affected is not None:
            ranges.append(affected)

    return AffectedRangePlan(
        requested_start_date=requested_start_date,
        requested_end_date=requested_end_date,
        benchmark_drift_start_date=benchmark_drift_start_date,
        selected_listing_count=len(prepared_listings),
        ranges=tuple(ranges),
    )


def _plan_listing_range(
    *,
    listing: EligibleListing,
    comparison: ListingStateComparison,
    requested_start_date: date | None,
    requested_end_date: date,
    benchmark_drift_start_date: date | None,
    explicit_rebuild: bool,
) -> AffectedRange | None:
    first_source = comparison.first_source_date
    last_source = comparison.last_source_date
    if first_source is None or last_source is None:
        return None
    requested_horizon = min(requested_end_date, last_source)
    if requested_horizon < first_source:
        return None

    reason_dates: dict[AffectedRangeReason, date] = {}
    local_facts = (
        (
            AffectedRangeReason.TAIL_APPEND,
            comparison.tail_append_count,
            comparison.earliest_tail_append_date,
        ),
        (
            AffectedRangeReason.MISSING_TECH_ROW,
            comparison.missing_tech_row_count,
            comparison.earliest_missing_tech_date,
        ),
        (
            AffectedRangeReason.SOURCE_COPY_DRIFT,
            comparison.source_copy_drift_count,
            comparison.earliest_source_copy_drift_date,
        ),
        (
            AffectedRangeReason.HISTORY_COUNT_DRIFT,
            comparison.history_count_drift_count,
            comparison.earliest_history_count_drift_date,
        ),
    )
    for reason, count, uncertainty_date in local_facts:
        if (
            count
            and uncertainty_date is not None
            and uncertainty_date <= requested_horizon
        ):
            reason_dates[reason] = uncertainty_date

    if (
        comparison.version_drift_count
        and comparison.earliest_version_drift_date is not None
    ):
        reason_dates[AffectedRangeReason.VERSION_DRIFT] = first_source

    if explicit_rebuild:
        rebuild_start = max(first_source, requested_start_date or first_source)
        if rebuild_start <= requested_horizon:
            reason_dates[AffectedRangeReason.EXPLICIT_REBUILD] = rebuild_start

    benchmark_horizon: date | None = requested_horizon
    if listing.status == "INACTIVE" and not reason_dates:
        benchmark_horizon = (
            None
            if comparison.last_technical_date is None
            else min(
                requested_horizon,
                comparison.last_technical_date,
            )
        )
    if (
        benchmark_drift_start_date is not None
        and is_spx_supported_subject(listing)
        and benchmark_horizon is not None
        and first_source <= benchmark_drift_start_date
    ):
        benchmark_start = benchmark_drift_start_date
        if benchmark_start <= benchmark_horizon:
            reason_dates[AffectedRangeReason.BENCHMARK_DRIFT] = benchmark_start

    if not reason_dates:
        return None
    write_start = min(reason_dates.values())
    write_end = requested_horizon
    if (
        listing.status == "INACTIVE"
        and set(reason_dates) == {AffectedRangeReason.BENCHMARK_DRIFT}
        and comparison.last_technical_date is not None
    ):
        write_end = min(write_end, comparison.last_technical_date)
    if (
        comparison.last_technical_date is not None
        and write_start <= comparison.last_technical_date
    ):
        write_end = max(write_end, comparison.last_technical_date)
    write_end = min(write_end, last_source)
    if write_start > write_end:
        return None

    reasons = tuple(sorted(reason_dates, key=_REASON_INDEX.__getitem__))
    return AffectedRange(
        provider_listing_id=listing.provider_listing_id,
        provider_code=listing.provider_code,
        market=listing.market,
        ticker=listing.ticker,
        status=listing.status,
        calculation_start_date=first_source,
        write_start_date=write_start,
        write_end_date=write_end,
        requested_end_date=requested_end_date,
        reasons=reasons,
    )


def _prepare_unique(
    values: Iterable[object],
    expected_type: type,
    field_name: str,
) -> tuple[object, ...]:
    prepared = tuple(values)
    if any(not isinstance(value, expected_type) for value in prepared):
        raise TypeError(
            f"{field_name} must contain only "
            f"{expected_type.__name__} records."
        )
    identifiers = [value.provider_listing_id for value in prepared]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{field_name} must contain unique provider listings.")
    return prepared


def _validate_rebuild_ids(values: tuple[UUID, ...]) -> frozenset[UUID]:
    if not isinstance(values, tuple):
        raise TypeError("explicit_rebuild_listing_ids must be a tuple.")
    if any(not isinstance(value, UUID) for value in values):
        raise TypeError("explicit_rebuild_listing_ids must contain UUID values.")
    if len(values) != len(set(values)):
        raise ValueError("explicit_rebuild_listing_ids must be unique.")
    return frozenset(values)


def _validate_identity(
    listing: EligibleListing,
    comparison: ListingStateComparison,
) -> None:
    if (
        listing.provider_code,
        listing.market,
        listing.ticker,
    ) != (
        comparison.provider_code,
        comparison.market,
        comparison.ticker,
    ):
        raise ValueError("Listing and comparison identity facts must match.")


def _listing_identity(listing: EligibleListing) -> tuple[str, str, str, UUID]:
    return (
        listing.provider_code,
        listing.market,
        listing.ticker,
        listing.provider_listing_id,
    )


def _range_identity(item: AffectedRange) -> tuple[str, str, str, UUID]:
    return (item.provider_code, item.market, item.ticker, item.provider_listing_id)


def _required_date(field_name: str, value: object) -> None:
    if type(value) is not date:
        raise TypeError(f"{field_name} must be a date.")


def _optional_date(field_name: str, value: object) -> None:
    if value is not None:
        _required_date(field_name, value)


def _date_string(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


__all__ = [
    "AffectedRange",
    "AffectedRangePlan",
    "AffectedRangeReason",
    "plan_affected_ranges",
]
