"""Canonical J9.5 historical backfill scope and resume resolution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from empire_stonks_tech_indicators.config import (
    DEFAULT_CALCULATION_VERSION,
    DEFAULT_WRITE_BATCH_SIZE,
    MAX_WRITE_BATCH_SIZE,
    MIN_WRITE_BATCH_SIZE,
)
from empire_stonks_tech_indicators.core_lifecycle import (
    TECH_INDICATORS_DEFAULT_SUBJECT_KEY,
)
from empire_stonks_tech_indicators.daily_scope import (
    TECH_INDICATORS_SCOPED_SUBJECT_PREFIX,
    TECH_INDICATORS_SCOPE_SCHEMA_VERSION,
)
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsValidationError,
)
from empire_stonks_tech_indicators.models import TechIndicatorsScope
from empire_stonks_tech_indicators.queries import (
    EligibleListing,
    select_eligible_listings,
)
from empire_stonks_tech_indicators.reports import ReportCursor, ReportScope


BACKFILL_CONFIRMATION_MAX_LISTINGS = 100
BACKFILL_CONFIRMATION_MAX_SOURCE_ROWS = 1_000_000


@dataclass(frozen=True)
class TechIndicatorsBackfillCursor:
    """Exclusive latest committed staged-batch boundary.

    The cursor is workflow progress only. It is deliberately absent from the
    normalized scope hash and cannot redefine a publication unit.
    """

    provider_listing_id: UUID
    trading_date: date | None
    batch_number: int

    def __post_init__(self) -> None:
        if not isinstance(self.provider_listing_id, UUID):
            raise TypeError("provider_listing_id must be a UUID.")
        if self.trading_date is not None and type(self.trading_date) is not date:
            raise TypeError("trading_date must be a date or None.")
        if type(self.batch_number) is not int:
            raise TypeError("batch_number must be an integer.")
        if self.batch_number < 1:
            raise ValueError("batch_number must be positive.")

    def to_report_cursor(self) -> ReportCursor:
        return ReportCursor(
            provider_listing_id=self.provider_listing_id,
            trading_date=self.trading_date,
            batch_number=self.batch_number,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "trading_date": (
                None if self.trading_date is None else self.trading_date.isoformat()
            ),
            "batch_number": self.batch_number,
        }


@dataclass(frozen=True)
class TechIndicatorsBackfillScope:
    """Validated operator inputs for one bounded historical publication unit.

    Dimension selectors and exact listing IDs are separate scope modes.
    Provider/market/unfiltered cohort work is broad and requires an explicit
    confirmation even for a dry run. Inactive rows remain listing-only opt-in.
    """

    effective_date: date
    start_date: date
    end_date: date
    provider_codes: tuple[str, ...] = ()
    markets: tuple[str, ...] = ()
    provider_listing_ids: tuple[UUID, ...] = ()
    include_inactive: bool = False
    batch_size: int = DEFAULT_WRITE_BATCH_SIZE
    resume_cursor: TechIndicatorsBackfillCursor | None = None
    calculation_version: str = DEFAULT_CALCULATION_VERSION
    rebuild: bool = False
    dry_run: bool = False
    confirm_broad_scope: bool = False

    def __post_init__(self) -> None:
        for field_name in ("effective_date", "start_date", "end_date"):
            if type(getattr(self, field_name)) is not date:
                raise TypeError(f"{field_name} must be a date.")
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date.")
        if self.end_date > self.effective_date:
            raise ValueError("end_date must not be after effective_date.")
        base_scope = TechIndicatorsScope(
            provider_codes=self.provider_codes,
            markets=self.markets,
            provider_listing_ids=self.provider_listing_ids,
            start_date=self.start_date,
            end_date=self.end_date,
            include_inactive=self.include_inactive,
        )
        object.__setattr__(self, "provider_codes", base_scope.provider_codes)
        object.__setattr__(self, "markets", base_scope.markets)
        object.__setattr__(
            self,
            "provider_listing_ids",
            base_scope.provider_listing_ids,
        )
        if self.provider_listing_ids and (
            self.provider_codes or self.markets
        ):
            raise ValueError(
                "provider_listing_ids cannot be combined with provider or "
                "market filters."
            )
        if type(self.batch_size) is not int:
            raise TypeError("batch_size must be an integer.")
        if not MIN_WRITE_BATCH_SIZE <= self.batch_size <= MAX_WRITE_BATCH_SIZE:
            raise ValueError(
                "batch_size must be between "
                f"{MIN_WRITE_BATCH_SIZE} and {MAX_WRITE_BATCH_SIZE}."
            )
        if self.resume_cursor is not None and not isinstance(
            self.resume_cursor,
            TechIndicatorsBackfillCursor,
        ):
            raise TypeError(
                "resume_cursor must be a TechIndicatorsBackfillCursor or None."
            )
        if self.calculation_version != DEFAULT_CALCULATION_VERSION:
            raise ValueError(
                "calculation_version must be "
                f"{DEFAULT_CALCULATION_VERSION}."
            )
        for field_name in (
            "include_inactive",
            "rebuild",
            "dry_run",
            "confirm_broad_scope",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a bool.")
        if self.is_broad_scope and not self.confirm_broad_scope:
            raise ValueError(
                "Broad provider, market, unfiltered, or over-100-listing "
                "backfills require confirm_broad_scope=True."
            )

    @property
    def is_filtered(self) -> bool:
        return bool(
            self.provider_codes or self.markets or self.provider_listing_ids
        )

    @property
    def is_broad_scope(self) -> bool:
        return (
            not self.provider_listing_ids
            or len(self.provider_listing_ids) > BACKFILL_CONFIRMATION_MAX_LISTINGS
        )

    @property
    def selection_scope(self) -> TechIndicatorsScope:
        return TechIndicatorsScope(
            provider_codes=self.provider_codes,
            markets=self.markets,
            provider_listing_ids=self.provider_listing_ids,
            start_date=self.start_date,
            end_date=self.end_date,
            include_inactive=self.include_inactive,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "effective_date": self.effective_date.isoformat(),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "provider_codes": list(self.provider_codes),
            "markets": list(self.markets),
            "provider_listing_ids": [
                str(identifier) for identifier in self.provider_listing_ids
            ],
            "include_inactive": self.include_inactive,
            "batch_size": self.batch_size,
            "resume_cursor": (
                None if self.resume_cursor is None else self.resume_cursor.to_dict()
            ),
            "calculation_version": self.calculation_version,
            "rebuild": self.rebuild,
            "dry_run": self.dry_run,
            "confirm_broad_scope": self.confirm_broad_scope,
        }


@dataclass(frozen=True)
class ResolvedTechIndicatorsBackfillScope:
    """Concrete P0.10 backfill identity and validated resume boundary."""

    request: TechIndicatorsBackfillScope
    listings: tuple[EligibleListing, ...]
    canonical_json: bytes
    scope_hash: str
    subject_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.request, TechIndicatorsBackfillScope):
            raise TypeError("request must be a TechIndicatorsBackfillScope.")
        if not isinstance(self.listings, tuple) or any(
            not isinstance(item, EligibleListing) for item in self.listings
        ):
            raise TypeError("listings must contain only EligibleListing records.")
        identities = tuple(_listing_identity(item) for item in self.listings)
        if identities != tuple(sorted(identities)):
            raise ValueError("listings must use deterministic identity order.")
        listing_ids = tuple(item.provider_listing_id for item in self.listings)
        if len(set(listing_ids)) != len(listing_ids):
            raise ValueError("listings must contain unique provider listing IDs.")
        expected_json = _canonical_scope_json(
            request=self.request,
            provider_listing_ids=listing_ids,
        )
        if self.canonical_json != expected_json:
            raise ValueError("canonical_json does not match the resolved scope.")
        expected_hash = hashlib.sha256(expected_json).hexdigest()
        if self.scope_hash != expected_hash:
            raise ValueError("scope_hash does not match canonical_json.")
        expected_subject = (
            f"{TECH_INDICATORS_SCOPED_SUBJECT_PREFIX}{expected_hash}"
            if self.request.is_filtered
            else TECH_INDICATORS_DEFAULT_SUBJECT_KEY
        )
        if self.subject_key != expected_subject:
            raise ValueError("subject_key does not match the requested scope.")
        _validate_resume_cursor(self.request, self.listings)
        _validate_resolved_confirmation(self.request, self.listings)

    @property
    def source_observation_count(self) -> int:
        return sum(item.source_observation_count for item in self.listings)

    @property
    def explicit_rebuild_listing_ids(self) -> tuple[UUID, ...]:
        if not self.request.rebuild:
            return ()
        return tuple(item.provider_listing_id for item in self.listings)

    @property
    def resumed_from_cursor(self) -> ReportCursor | None:
        if self.request.resume_cursor is None:
            return None
        return self.request.resume_cursor.to_report_cursor()

    def to_report_scope(self) -> ReportScope:
        return ReportScope(
            scope_hash=self.scope_hash,
            effective_date=None,
            start_date=self.request.start_date,
            end_date=self.request.end_date,
            provider_codes=self.request.provider_codes,
            markets=self.request.markets,
            instrument_type_codes=tuple(
                sorted({item.instrument_type_code for item in self.listings})
            ),
            requested_listing_count=len(self.request.provider_listing_ids),
            resolved_listing_count=len(self.listings),
            include_inactive=self.request.include_inactive,
            dry_run=self.request.dry_run,
            force=False,
            rebuild=self.request.rebuild,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "scope_hash": self.scope_hash,
            "subject_key": self.subject_key,
            "resolved_listing_count": len(self.listings),
            "source_observation_count": self.source_observation_count,
            "explicit_rebuild_listing_count": len(
                self.explicit_rebuild_listing_ids
            ),
            "request": {
                "effective_date": self.request.effective_date.isoformat(),
                "start_date": self.request.start_date.isoformat(),
                "end_date": self.request.end_date.isoformat(),
                "provider_codes": list(self.request.provider_codes),
                "markets": list(self.request.markets),
                "requested_listing_count": len(
                    self.request.provider_listing_ids
                ),
                "include_inactive": self.request.include_inactive,
                "batch_size": self.request.batch_size,
                "resume_cursor": (
                    None
                    if self.request.resume_cursor is None
                    else self.request.resume_cursor.to_dict()
                ),
                "calculation_version": self.request.calculation_version,
                "rebuild": self.request.rebuild,
                "dry_run": self.request.dry_run,
                "broad_scope_confirmed": self.request.confirm_broad_scope,
            },
        }


def resolve_tech_indicators_backfill_scope(
    *,
    cursor: Any,
    scope: TechIndicatorsBackfillScope,
) -> ResolvedTechIndicatorsBackfillScope:
    """Resolve an exact P0.6 listing set in the caller's transaction."""

    if not hasattr(cursor, "execute") or not callable(cursor.execute):
        raise TypeError("cursor must provide execute().")
    if not isinstance(scope, TechIndicatorsBackfillScope):
        raise TypeError("scope must be a TechIndicatorsBackfillScope.")
    listings = select_eligible_listings(cursor=cursor, scope=scope.selection_scope)
    if not listings:
        raise TechIndicatorsValidationError(
            "Backfill scope resolved no eligible provider listings."
        )
    if scope.provider_listing_ids:
        resolved_ids = {item.provider_listing_id for item in listings}
        missing_ids = set(scope.provider_listing_ids) - resolved_ids
        if missing_ids:
            raise TechIndicatorsValidationError(
                "Exact backfill scope contains an ineligible or missing listing."
            )
    _validate_resume_cursor(scope, listings)
    if (
        scope.resume_cursor is not None
        and scope.resume_cursor.trading_date is not None
        and not _resume_source_key_exists(cursor, scope.resume_cursor)
    ):
        raise TechIndicatorsValidationError(
            "Resume cursor does not reference a current source row."
        )
    _validate_resolved_confirmation(scope, listings)
    canonical_json = _canonical_scope_json(
        request=scope,
        provider_listing_ids=tuple(
            item.provider_listing_id for item in listings
        ),
    )
    scope_hash = hashlib.sha256(canonical_json).hexdigest()
    return ResolvedTechIndicatorsBackfillScope(
        request=scope,
        listings=listings,
        canonical_json=canonical_json,
        scope_hash=scope_hash,
        subject_key=(
            f"{TECH_INDICATORS_SCOPED_SUBJECT_PREFIX}{scope_hash}"
            if scope.is_filtered
            else TECH_INDICATORS_DEFAULT_SUBJECT_KEY
        ),
    )


def _canonical_scope_json(
    *,
    request: TechIndicatorsBackfillScope,
    provider_listing_ids: tuple[UUID, ...],
) -> bytes:
    payload = {
        "calculation_version": request.calculation_version,
        "dry_run": request.dry_run,
        "effective_date": None,
        "end_date": request.end_date.isoformat(),
        "include_inactive": request.include_inactive,
        "provider_listing_ids": sorted(
            {str(identifier) for identifier in provider_listing_ids}
        ),
        "rebuild": request.rebuild,
        "scope_schema_version": TECH_INDICATORS_SCOPE_SCHEMA_VERSION,
        "start_date": request.start_date.isoformat(),
        "workflow_kind": "BACKFILL",
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _validate_resume_cursor(
    request: TechIndicatorsBackfillScope,
    listings: tuple[EligibleListing, ...],
) -> None:
    resume = request.resume_cursor
    if resume is None:
        return
    listing = next(
        (
            item
            for item in listings
            if item.provider_listing_id == resume.provider_listing_id
        ),
        None,
    )
    if listing is None:
        raise TechIndicatorsValidationError(
            "Resume cursor listing does not belong to the resolved scope."
        )
    if resume.trading_date is None:
        if listing.source_observation_count != 0:
            raise TechIndicatorsValidationError(
                "A null-date resume cursor is valid only for an empty listing."
            )
        return
    if not request.start_date <= resume.trading_date <= request.end_date:
        raise TechIndicatorsValidationError(
            "Resume cursor date is outside the requested backfill range."
        )
    if (
        listing.first_trading_date is None
        or listing.last_trading_date is None
        or not listing.first_trading_date
        <= resume.trading_date
        <= listing.last_trading_date
    ):
        raise TechIndicatorsValidationError(
            "Resume cursor date is outside the listing's scoped source coverage."
        )


def _validate_resolved_confirmation(
    request: TechIndicatorsBackfillScope,
    listings: tuple[EligibleListing, ...],
) -> None:
    source_rows = sum(item.source_observation_count for item in listings)
    if (
        len(listings) > BACKFILL_CONFIRMATION_MAX_LISTINGS
        or source_rows > BACKFILL_CONFIRMATION_MAX_SOURCE_ROWS
    ) and not request.confirm_broad_scope:
        raise TechIndicatorsValidationError(
            "Resolved backfill exceeds the 100-listing or 1,000,000-row pilot "
            "envelope; set confirm_broad_scope=True."
        )


def _resume_source_key_exists(
    cursor: Any,
    resume: TechIndicatorsBackfillCursor,
) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM stonks.ohlcv_daily
            WHERE provider_listing_id = %s
              AND trading_date = %s
        )
        """,
        (resume.provider_listing_id, resume.trading_date),
    )
    row = cursor.fetchone()
    if row is None or len(row) != 1 or type(row[0]) is not bool:
        raise TechIndicatorsValidationError(
            "Resume source-key validation returned an invalid row."
        )
    return row[0]


def _listing_identity(item: EligibleListing) -> tuple[str, str, str, str]:
    return (
        item.provider_code,
        item.market,
        item.ticker,
        str(item.provider_listing_id),
    )


__all__ = [
    "BACKFILL_CONFIRMATION_MAX_LISTINGS",
    "BACKFILL_CONFIRMATION_MAX_SOURCE_ROWS",
    "ResolvedTechIndicatorsBackfillScope",
    "TechIndicatorsBackfillCursor",
    "TechIndicatorsBackfillScope",
    "resolve_tech_indicators_backfill_scope",
]
