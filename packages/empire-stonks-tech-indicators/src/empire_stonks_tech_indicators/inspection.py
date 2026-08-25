"""Read-only operational inspection over published technical-indicator state."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any

from empire_stonks_tech_indicators.config import (
    BenchmarkConfig,
    DEFAULT_CALCULATION_VERSION,
    DEFAULT_SOURCE_READ_PAGE_SIZE,
    MAX_DIAGNOSTIC_SAMPLE_LIMIT,
    MAX_SOURCE_READ_PAGE_SIZE,
    MIN_SOURCE_READ_PAGE_SIZE,
)
from empire_stonks_tech_indicators.models import ReasonCount, TechIndicatorsScope
from empire_stonks_tech_indicators.published_queries import (
    PublishedFeatureCoverage,
    PublishedFeatureFreshness,
    select_published_feature_coverage,
    select_published_feature_freshness,
)
from empire_stonks_tech_indicators.readiness import (
    SourceReadinessDecision,
    decide_source_readiness,
)
from empire_stonks_tech_indicators.reporting_queries import (
    ReportDatabaseSummary,
    select_report_database_summary,
)
from empire_stonks_tech_indicators.state import (
    ListingStateComparison,
    iter_state_comparison_pages,
)


INSPECTION_SCHEMA_VERSION = 1
INSPECTION_DISCLOSURE = (
    "Operational inspection only; no strategy thresholds, ranks, target "
    "selection, or recommendations."
)
_DRIFT_FIELDS = (
    ("TAIL_APPEND", "tail_append_count"),
    ("MISSING_TECH_ROW", "missing_tech_row_count"),
    ("SOURCE_COPY_DRIFT", "source_copy_drift_count"),
    ("HISTORY_COUNT_DRIFT", "history_count_drift_count"),
    ("VERSION_DRIFT", "version_drift_count"),
)


@dataclass(frozen=True)
class InspectionDriftSummary:
    """Aggregate state-comparison facts plus bounded drifted listings."""

    listing_count: int
    equivalent_listing_count: int
    drifted_listing_count: int
    reason_listing_counts: tuple[ReasonCount, ...]
    reason_row_counts: tuple[ReasonCount, ...]
    earliest_recalculation_date: date | None
    samples: tuple[ListingStateComparison, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "listing_count": self.listing_count,
            "equivalent_listing_count": self.equivalent_listing_count,
            "drifted_listing_count": self.drifted_listing_count,
            "reason_listing_counts": [
                item.to_dict() for item in self.reason_listing_counts
            ],
            "reason_row_counts": [
                item.to_dict() for item in self.reason_row_counts
            ],
            "earliest_recalculation_date": (
                None
                if self.earliest_recalculation_date is None
                else self.earliest_recalculation_date.isoformat()
            ),
            "samples": [item.to_dict() for item in self.samples],
        }


@dataclass(frozen=True)
class TechIndicatorsInspection:
    """One bounded, threshold-free operational inspection snapshot."""

    scope: TechIndicatorsScope
    effective_date: date
    calculation_version: str
    sample_limit: int
    coverage: ReportDatabaseSummary
    coverage_listing_count: int
    coverage_key_mismatch_count: int
    coverage_samples: tuple[PublishedFeatureCoverage, ...]
    freshness_listing_count: int
    no_published_freshness_count: int
    freshness_samples: tuple[PublishedFeatureFreshness, ...]
    drift: InspectionDriftSummary
    spx_readiness: SourceReadinessDecision

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": INSPECTION_SCHEMA_VERSION,
            "scope": {
                **self.scope.to_dict(),
                "effective_date": self.effective_date.isoformat(),
                "calculation_version": self.calculation_version,
                "sample_limit": self.sample_limit,
            },
            "coverage": self.coverage.to_dict(),
            "coverage_listing_facts": {
                "listing_count": self.coverage_listing_count,
                "source_and_published_key_mismatch_count": (
                    self.coverage_key_mismatch_count
                ),
                "samples": [item.to_dict() for item in self.coverage_samples],
            },
            "freshness": {
                "as_of_date": self.effective_date.isoformat(),
                "listing_count": self.freshness_listing_count,
                "no_published_data_count": self.no_published_freshness_count,
                "samples": [item.to_dict() for item in self.freshness_samples],
            },
            "drift": self.drift.to_dict(),
            "spx_readiness": self.spx_readiness.to_dict(),
            "disclosure": INSPECTION_DISCLOSURE,
        }


def inspect_tech_indicators(
    *,
    connection: Any,
    scope: TechIndicatorsScope,
    effective_date: date,
    benchmark_config: BenchmarkConfig,
    calculation_version: str = DEFAULT_CALCULATION_VERSION,
    sample_limit: int = MAX_DIAGNOSTIC_SAMPLE_LIMIT,
    page_size: int = DEFAULT_SOURCE_READ_PAGE_SIZE,
) -> TechIndicatorsInspection:
    """Inspect one scope in a package-owned read-only repeatable-read snapshot."""

    _validate_inputs(
        connection=connection,
        scope=scope,
        effective_date=effective_date,
        benchmark_config=benchmark_config,
        calculation_version=calculation_version,
        sample_limit=sample_limit,
        page_size=page_size,
    )
    cursor = connection.cursor()
    try:
        cursor.execute(
            "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        )
        coverage = select_report_database_summary(
            cursor=cursor,
            scope=scope,
            effective_date=effective_date,
        )
        listing_coverage = select_published_feature_coverage(
            cursor=cursor,
            scope=scope,
        )
        freshness = select_published_feature_freshness(
            cursor=cursor,
            scope=scope,
            as_of_date=effective_date,
        )
        spx_readiness = decide_source_readiness(
            cursor=cursor,
            scope=_effective_date_scope(scope, effective_date),
            effective_date=effective_date,
            benchmark_config=benchmark_config,
        )
        drift = _summarize_drift(
            pages=iter_state_comparison_pages(
                cursor=cursor,
                scope=scope,
                calculation_version=calculation_version,
                page_size=page_size,
            ),
            sample_limit=sample_limit,
        )
        _validate_listing_counts(
            selected=coverage.selected_listing_count,
            coverage=len(listing_coverage),
            freshness=len(freshness),
            drift=drift.listing_count,
        )
        return TechIndicatorsInspection(
            scope=scope,
            effective_date=effective_date,
            calculation_version=calculation_version,
            sample_limit=sample_limit,
            coverage=coverage,
            coverage_listing_count=len(listing_coverage),
            coverage_key_mismatch_count=sum(
                not item.source_and_published_keys_match
                for item in listing_coverage
            ),
            coverage_samples=listing_coverage[:sample_limit],
            freshness_listing_count=len(freshness),
            no_published_freshness_count=sum(
                item.latest_trading_date is None for item in freshness
            ),
            freshness_samples=freshness[:sample_limit],
            drift=drift,
            spx_readiness=spx_readiness,
        )
    finally:
        try:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        finally:
            connection.rollback()


def _summarize_drift(
    *,
    pages: Any,
    sample_limit: int,
) -> InspectionDriftSummary:
    listing_count = 0
    equivalent_count = 0
    reason_listing_counts: Counter[str] = Counter()
    reason_row_counts: Counter[str] = Counter()
    earliest: date | None = None
    samples: list[ListingStateComparison] = []
    for page in pages:
        for item in page:
            listing_count += 1
            if item.is_equivalent:
                equivalent_count += 1
                continue
            for code, field_name in _DRIFT_FIELDS:
                count = getattr(item, field_name)
                if count:
                    reason_listing_counts[code] += 1
                    reason_row_counts[code] += count
            recalculation_date = item.earliest_recalculation_date
            if recalculation_date is not None and (
                earliest is None or recalculation_date < earliest
            ):
                earliest = recalculation_date
            if len(samples) < sample_limit:
                samples.append(item)
    return InspectionDriftSummary(
        listing_count=listing_count,
        equivalent_listing_count=equivalent_count,
        drifted_listing_count=listing_count - equivalent_count,
        reason_listing_counts=tuple(
            ReasonCount(code, reason_listing_counts[code])
            for code, _field_name in _DRIFT_FIELDS
            if reason_listing_counts[code]
        ),
        reason_row_counts=tuple(
            ReasonCount(code, reason_row_counts[code])
            for code, _field_name in _DRIFT_FIELDS
            if reason_row_counts[code]
        ),
        earliest_recalculation_date=earliest,
        samples=tuple(samples),
    )


def _effective_date_scope(
    scope: TechIndicatorsScope,
    effective_date: date,
) -> TechIndicatorsScope:
    return TechIndicatorsScope(
        provider_codes=scope.provider_codes,
        markets=scope.markets,
        provider_listing_ids=scope.provider_listing_ids,
        start_date=effective_date,
        end_date=effective_date,
        include_inactive=scope.include_inactive,
    )


def _validate_inputs(
    *,
    connection: Any,
    scope: object,
    effective_date: object,
    benchmark_config: object,
    calculation_version: object,
    sample_limit: object,
    page_size: object,
) -> None:
    if not callable(getattr(connection, "cursor", None)) or not callable(
        getattr(connection, "rollback", None)
    ):
        raise TypeError("connection must provide cursor() and rollback().")
    if not isinstance(scope, TechIndicatorsScope):
        raise TypeError("scope must be a TechIndicatorsScope.")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a date.")
    if scope.start_date is not None and not (
        scope.start_date <= effective_date <= scope.end_date
    ):
        raise ValueError("effective_date must be inside the scope date range.")
    if not isinstance(benchmark_config, BenchmarkConfig):
        raise TypeError("benchmark_config must be a BenchmarkConfig.")
    if calculation_version != DEFAULT_CALCULATION_VERSION:
        raise ValueError(
            f"calculation_version must be {DEFAULT_CALCULATION_VERSION}."
        )
    if type(sample_limit) is not int or not (
        1 <= sample_limit <= MAX_DIAGNOSTIC_SAMPLE_LIMIT
    ):
        raise ValueError(
            "sample_limit must be between 1 and "
            f"{MAX_DIAGNOSTIC_SAMPLE_LIMIT}."
        )
    if type(page_size) is not int or not (
        MIN_SOURCE_READ_PAGE_SIZE <= page_size <= MAX_SOURCE_READ_PAGE_SIZE
    ):
        raise ValueError(
            "page_size must be between "
            f"{MIN_SOURCE_READ_PAGE_SIZE} and {MAX_SOURCE_READ_PAGE_SIZE}."
        )


def _validate_listing_counts(
    *, selected: int, coverage: int, freshness: int, drift: int
) -> None:
    if len({selected, coverage, freshness, drift}) != 1:
        raise ValueError("Inspection listing counts do not reconcile.")


__all__ = [
    "INSPECTION_DISCLOSURE",
    "INSPECTION_SCHEMA_VERSION",
    "InspectionDriftSummary",
    "TechIndicatorsInspection",
    "inspect_tech_indicators",
]
