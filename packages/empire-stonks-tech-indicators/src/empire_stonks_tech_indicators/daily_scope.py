"""Canonical J9.2 daily workflow scope and source-readiness resolution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Final
from uuid import UUID

from empire_stonks_tech_indicators.config import (
    DEFAULT_CALCULATION_VERSION,
    BenchmarkConfig,
)
from empire_stonks_tech_indicators.core_lifecycle import (
    TECH_INDICATORS_DEFAULT_SUBJECT_KEY,
)
from empire_stonks_tech_indicators.models import TechIndicatorsScope
from empire_stonks_tech_indicators.queries import (
    EligibleListing,
    select_eligible_listings,
)
from empire_stonks_tech_indicators.readiness import (
    SourceReadinessDecision,
    decide_source_readiness,
)
from empire_stonks_tech_indicators.reports import ReportScope


TECH_INDICATORS_SCOPE_SCHEMA_VERSION: Final = 1
TECH_INDICATORS_SCOPED_SUBJECT_PREFIX: Final = "scope:"


@dataclass(frozen=True)
class TechIndicatorsDailyScope:
    """Validated operator inputs for one exact-date daily workflow.

    Provider and market selectors form one dimension-filter scope. Exact
    listing IDs form a separate scope mode and cannot be mixed with dimension
    selectors. ``force`` requests P0.7 explicit rebuild work; it never bypasses
    source readiness, validation, publication, or locking.
    """

    effective_date: date
    provider_codes: tuple[str, ...] = ()
    markets: tuple[str, ...] = ()
    provider_listing_ids: tuple[UUID, ...] = ()
    calculation_version: str = DEFAULT_CALCULATION_VERSION
    dry_run: bool = False
    force: bool = False

    def __post_init__(self) -> None:
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date.")
        base_scope = TechIndicatorsScope(
            provider_codes=self.provider_codes,
            markets=self.markets,
            provider_listing_ids=self.provider_listing_ids,
            start_date=self.effective_date,
            end_date=self.effective_date,
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
        if self.calculation_version != DEFAULT_CALCULATION_VERSION:
            raise ValueError(
                "calculation_version must be "
                f"{DEFAULT_CALCULATION_VERSION}."
            )
        for field_name in ("dry_run", "force"):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a bool.")

    @property
    def is_filtered(self) -> bool:
        return bool(
            self.provider_codes
            or self.markets
            or self.provider_listing_ids
        )

    @property
    def selection_scope(self) -> TechIndicatorsScope:
        """Return the exact-date P0.6 selection/readiness scope."""

        return TechIndicatorsScope(
            provider_codes=self.provider_codes,
            markets=self.markets,
            provider_listing_ids=self.provider_listing_ids,
            start_date=self.effective_date,
            end_date=self.effective_date,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "effective_date": self.effective_date.isoformat(),
            "provider_codes": list(self.provider_codes),
            "markets": list(self.markets),
            "provider_listing_ids": [
                str(identifier) for identifier in self.provider_listing_ids
            ],
            "calculation_version": self.calculation_version,
            "dry_run": self.dry_run,
            "force": self.force,
        }


@dataclass(frozen=True)
class ResolvedTechIndicatorsDailyScope:
    """Concrete P0.10 daily identity plus unchanged I3.6 readiness facts."""

    request: TechIndicatorsDailyScope
    listings: tuple[EligibleListing, ...]
    readiness: SourceReadinessDecision
    canonical_json: bytes
    scope_hash: str
    subject_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.request, TechIndicatorsDailyScope):
            raise TypeError("request must be a TechIndicatorsDailyScope.")
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
        if not isinstance(self.readiness, SourceReadinessDecision):
            raise TypeError("readiness must be a SourceReadinessDecision.")
        if self.readiness.effective_date != self.request.effective_date:
            raise ValueError("readiness must match the requested effective date.")
        if self.readiness.selected_listing_count != len(self.listings):
            raise ValueError("readiness and resolved listing counts must match.")
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

    @property
    def ready(self) -> bool:
        return self.readiness.ready

    @property
    def explicit_rebuild_listing_ids(self) -> tuple[UUID, ...]:
        """Return the exact P0.7 rebuild input implied by ``force``."""

        if not self.request.force:
            return ()
        return tuple(item.provider_listing_id for item in self.listings)

    def to_report_scope(self) -> ReportScope:
        """Project the canonical scope into R8.1's bounded display facts."""

        return ReportScope(
            scope_hash=self.scope_hash,
            effective_date=self.request.effective_date,
            start_date=None,
            end_date=None,
            provider_codes=self.request.provider_codes,
            markets=self.request.markets,
            instrument_type_codes=tuple(
                sorted({item.instrument_type_code for item in self.listings})
            ),
            requested_listing_count=len(
                self.request.provider_listing_ids
            ),
            resolved_listing_count=len(self.listings),
            include_inactive=False,
            dry_run=self.request.dry_run,
            force=self.request.force,
            rebuild=self.request.force,
        )

    def to_dict(self) -> dict[str, object]:
        """Return bounded identity/readiness facts without listing payloads."""

        return {
            "scope_hash": self.scope_hash,
            "subject_key": self.subject_key,
            "resolved_listing_count": len(self.listings),
            "ready": self.ready,
            "readiness_reasons": list(self.readiness.reasons),
            "explicit_rebuild_listing_count": len(
                self.explicit_rebuild_listing_ids
            ),
            "request": {
                "effective_date": self.request.effective_date.isoformat(),
                "provider_codes": list(self.request.provider_codes),
                "markets": list(self.request.markets),
                "requested_listing_count": len(
                    self.request.provider_listing_ids
                ),
                "calculation_version": self.request.calculation_version,
                "dry_run": self.request.dry_run,
                "force": self.request.force,
            },
        }


def resolve_tech_indicators_daily_scope(
    *,
    cursor: Any,
    scope: TechIndicatorsDailyScope,
    benchmark_config: BenchmarkConfig,
) -> ResolvedTechIndicatorsDailyScope:
    """Resolve exact P0.6 IDs and decide I3.6 readiness in one snapshot.

    The caller owns the cursor and transaction. J9.9 will acquire the global
    writer lock before calling this function from mutating runner paths.
    """

    if not hasattr(cursor, "execute") or not callable(cursor.execute):
        raise TypeError("cursor must provide execute().")
    if not isinstance(scope, TechIndicatorsDailyScope):
        raise TypeError("scope must be a TechIndicatorsDailyScope.")
    if not isinstance(benchmark_config, BenchmarkConfig):
        raise TypeError("benchmark_config must be a BenchmarkConfig.")

    listings = select_eligible_listings(
        cursor=cursor,
        scope=scope.selection_scope,
    )
    readiness = decide_source_readiness(
        cursor=cursor,
        scope=scope.selection_scope,
        effective_date=scope.effective_date,
        benchmark_config=benchmark_config,
        resolved_listings=listings,
    )
    canonical_json = _canonical_scope_json(
        request=scope,
        provider_listing_ids=tuple(
            item.provider_listing_id for item in listings
        ),
    )
    scope_hash = hashlib.sha256(canonical_json).hexdigest()
    return ResolvedTechIndicatorsDailyScope(
        request=scope,
        listings=listings,
        readiness=readiness,
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
    request: TechIndicatorsDailyScope,
    provider_listing_ids: tuple[UUID, ...],
) -> bytes:
    identifiers = sorted({str(identifier) for identifier in provider_listing_ids})
    payload = {
        "calculation_version": request.calculation_version,
        "dry_run": request.dry_run,
        "effective_date": request.effective_date.isoformat(),
        "end_date": None,
        "include_inactive": False,
        "provider_listing_ids": identifiers,
        "rebuild": request.force,
        "scope_schema_version": TECH_INDICATORS_SCOPE_SCHEMA_VERSION,
        "start_date": None,
        "workflow_kind": "DAILY",
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _listing_identity(item: EligibleListing) -> tuple[str, str, str, str]:
    return (
        item.provider_code,
        item.market,
        item.ticker,
        str(item.provider_listing_id),
    )


__all__ = [
    "TECH_INDICATORS_SCOPED_SUBJECT_PREFIX",
    "TECH_INDICATORS_SCOPE_SCHEMA_VERSION",
    "ResolvedTechIndicatorsDailyScope",
    "TechIndicatorsDailyScope",
    "resolve_tech_indicators_daily_scope",
]
