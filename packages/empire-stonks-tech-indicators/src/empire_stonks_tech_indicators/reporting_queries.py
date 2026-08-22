"""Set-based database summaries for technical-indicator run reports."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from empire_stonks_tech_indicators.models import TechIndicatorsScope
from empire_stonks_tech_indicators.published_queries import (
    PUBLISHED_RANKING_FIELDS,
)
from empire_stonks_tech_indicators.queries import (
    EligibleListing,
    select_eligible_listings,
)
from empire_stonks_tech_indicators.subject_policy import (
    is_spx_supported_subject,
)


REPORT_FEATURE_FIELDS = PUBLISHED_RANKING_FIELDS

_SPX_FIELDS = frozenset(
    {
        "rel_spx",
        "pct_rel_spx_20",
        "pct_rel_spx_50",
        "relative_return_spx_20d_pct",
        "relative_return_spx_63d_pct",
        "relative_return_spx_126d_pct",
        "relative_return_spx_252d_pct",
        "spx_beta_60d",
        "spx_beta_252d",
        "spx_correlation_60d",
        "spx_correlation_252d",
    }
)

_GUARANTEED_AFTER_WARMUP = frozenset(
    {
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_12",
        "ema_20",
        "ema_26",
        "ema_50",
        "hh_20",
        "hh_50",
        "hh_252",
        "ll_20",
        "ll_50",
        "rsi_14",
        "atr_14",
        "price_stddev_20",
        "plus_di_14",
        "minus_di_14",
        "adx_14",
        "macd_12_26",
        "macd_signal_12_26_9",
        "macd_histogram_12_26_9",
        "consecutive_up_days",
        "consecutive_down_days",
    }
)

_MINIMUM_OBSERVATIONS = {
    "return_1d_pct": 2,
    "return_2d_pct": 3,
    "return_3d_pct": 4,
    "return_5d_pct": 6,
    "return_10d_pct": 11,
    "return_20d_pct": 21,
    "return_63d_pct": 64,
    "return_126d_pct": 127,
    "return_252d_pct": 253,
    "gap_1d_pct": 2,
    "sma_20": 20,
    "sma_50": 50,
    "sma_200": 200,
    "ema_12": 12,
    "ema_20": 20,
    "ema_26": 26,
    "ema_50": 50,
    "sma_50_change_20d_pct": 70,
    "sma_200_change_20d_pct": 220,
    "hh_20": 20,
    "hh_50": 50,
    "hh_252": 252,
    "ll_20": 20,
    "ll_50": 50,
    "rsi_14": 15,
    "atr_14": 15,
    "return_volatility_20d_pct": 21,
    "return_volatility_60d_pct": 61,
    "return_1d_zscore_20d": 22,
    "return_3d_zscore_20d": 24,
    "price_stddev_20": 20,
    "plus_di_14": 15,
    "minus_di_14": 15,
    "adx_14": 28,
    "macd_12_26": 34,
    "macd_signal_12_26_9": 34,
    "macd_histogram_12_26_9": 34,
    "volume_avg_20": 20,
    "volume_avg_60": 60,
    "dollar_volume_avg_20": 20,
    "consecutive_up_days": 1,
    "consecutive_down_days": 1,
    "rel_spx": 1,
    "pct_rel_spx_20": 20,
    "pct_rel_spx_50": 50,
    "relative_return_spx_20d_pct": 21,
    "relative_return_spx_63d_pct": 64,
    "relative_return_spx_126d_pct": 127,
    "relative_return_spx_252d_pct": 253,
    "spx_beta_60d": 61,
    "spx_beta_252d": 253,
    "spx_correlation_60d": 61,
    "spx_correlation_252d": 253,
    "dollar_volume": 1,
    "intraday_return_1d_pct": 1,
    "daily_range_pct": 1,
    "close_location_1d": 1,
    "pct_sma_20": 20,
    "pct_sma_50": 50,
    "pct_sma_200": 200,
    "pct_ema_20": 20,
    "pct_ema_50": 50,
    "pct_sma_20_vs_50": 50,
    "pct_sma_20_vs_200": 200,
    "pct_sma_50_vs_200": 200,
    "pct_hh_20": 20,
    "pct_hh_50": 50,
    "pct_hh_252": 252,
    "pct_ll_20": 20,
    "pct_ll_50": 50,
    "atr_pct_14": 15,
    "bollinger_percent_b_20_2": 20,
    "bollinger_bandwidth_20_2": 20,
    "volume_ratio_20": 20,
    "macd_12_26_pct": 34,
    "macd_histogram_12_26_9_pct": 34,
}

if set(_MINIMUM_OBSERVATIONS) != set(REPORT_FEATURE_FIELDS):
    raise RuntimeError("Report feature warm-up inventory is incomplete.")

_WARMUP_THRESHOLDS = tuple(sorted(set(_MINIMUM_OBSERVATIONS.values())))


@dataclass(frozen=True)
class ReportDimensionCoverage:
    """One provider, market, or instrument-type aggregate."""

    code: str
    listing_count: int
    source_row_count: int
    payload_row_count: int
    published_row_count: int

    def __post_init__(self) -> None:
        _validate_code("code", self.code)
        for name in (
            "listing_count",
            "source_row_count",
            "payload_row_count",
            "published_row_count",
        ):
            _validate_nonnegative_int(name, getattr(self, name))

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "listing_count": self.listing_count,
            "source_row_count": self.source_row_count,
            "payload_row_count": self.payload_row_count,
            "published_row_count": self.published_row_count,
        }


@dataclass(frozen=True)
class ReportDateCoverage:
    """Source, selected payload, and published date coverage."""

    source_first_date: date | None
    source_last_date: date | None
    payload_first_date: date | None
    payload_last_date: date | None
    effective_date_source_rows: int
    effective_date_payload_rows: int
    effective_date_published_rows: int

    def __post_init__(self) -> None:
        _validate_date_range(
            "source", self.source_first_date, self.source_last_date
        )
        _validate_date_range(
            "payload", self.payload_first_date, self.payload_last_date
        )
        for name in (
            "effective_date_source_rows",
            "effective_date_payload_rows",
            "effective_date_published_rows",
        ):
            _validate_nonnegative_int(name, getattr(self, name))

    def to_dict(self) -> dict[str, object]:
        return {
            "source_first_date": _date_text(self.source_first_date),
            "source_last_date": _date_text(self.source_last_date),
            "payload_first_date": _date_text(self.payload_first_date),
            "payload_last_date": _date_text(self.payload_last_date),
            "effective_date_source_rows": self.effective_date_source_rows,
            "effective_date_payload_rows": self.effective_date_payload_rows,
            "effective_date_published_rows": self.effective_date_published_rows,
        }


@dataclass(frozen=True)
class ReportVersionCoverage:
    """One calculation version's selected-payload coverage."""

    calculation_version: str
    listing_count: int
    row_count: int

    def __post_init__(self) -> None:
        _validate_code("calculation_version", self.calculation_version)
        _validate_nonnegative_int("listing_count", self.listing_count)
        _validate_nonnegative_int("row_count", self.row_count)

    def to_dict(self) -> dict[str, object]:
        return {
            "calculation_version": self.calculation_version,
            "listing_count": self.listing_count,
            "row_count": self.row_count,
        }


@dataclass(frozen=True)
class ReportFeatureCoverage:
    """Count-only quality coverage for one analytical field."""

    feature_name: str
    eligible_row_count: int
    populated_count: int
    null_count: int
    warmup_null_count: int
    dependency_null_count: int
    unsupported_null_count: int
    unexpected_null_count: int

    def __post_init__(self) -> None:
        if self.feature_name not in REPORT_FEATURE_FIELDS:
            raise ValueError("feature_name is not in the V1 report inventory.")
        for name in (
            "eligible_row_count",
            "populated_count",
            "null_count",
            "warmup_null_count",
            "dependency_null_count",
            "unsupported_null_count",
            "unexpected_null_count",
        ):
            _validate_nonnegative_int(name, getattr(self, name))
        if self.populated_count + self.null_count != self.eligible_row_count:
            raise ValueError("Feature populated and null counts do not reconcile.")
        if (
            self.warmup_null_count
            + self.dependency_null_count
            + self.unsupported_null_count
            + self.unexpected_null_count
            != self.null_count
        ):
            raise ValueError("Feature null reason counts do not reconcile.")

    def to_dict(self) -> dict[str, object]:
        return {
            "feature_name": self.feature_name,
            "eligible_row_count": self.eligible_row_count,
            "populated_count": self.populated_count,
            "null_count": self.null_count,
            "warmup_null_count": self.warmup_null_count,
            "dependency_null_count": self.dependency_null_count,
            "unsupported_null_count": self.unsupported_null_count,
            "unexpected_null_count": self.unexpected_null_count,
        }


@dataclass(frozen=True)
class ReportBenchmarkCoverage:
    """Selected-payload benchmark lineage and populated-field counts."""

    supported_listing_count: int
    unsupported_listing_count: int
    benchmark_linked_row_count: int
    benchmark_unlinked_row_count: int
    aligned_row_count: int
    effective_date_aligned_count: int
    complete_20_count: int
    complete_50_count: int
    complete_60_count: int
    complete_63_count: int
    complete_126_count: int
    complete_252_count: int

    def __post_init__(self) -> None:
        for name in (
            "supported_listing_count",
            "unsupported_listing_count",
            "benchmark_linked_row_count",
            "benchmark_unlinked_row_count",
            "aligned_row_count",
            "effective_date_aligned_count",
            "complete_20_count",
            "complete_50_count",
            "complete_60_count",
            "complete_63_count",
            "complete_126_count",
            "complete_252_count",
        ):
            _validate_nonnegative_int(name, getattr(self, name))

    def to_dict(self) -> dict[str, object]:
        return {
            "supported_listing_count": self.supported_listing_count,
            "unsupported_listing_count": self.unsupported_listing_count,
            "benchmark_linked_row_count": self.benchmark_linked_row_count,
            "benchmark_unlinked_row_count": self.benchmark_unlinked_row_count,
            "aligned_row_count": self.aligned_row_count,
            "effective_date_aligned_count": self.effective_date_aligned_count,
            "complete_20_count": self.complete_20_count,
            "complete_50_count": self.complete_50_count,
            "complete_60_count": self.complete_60_count,
            "complete_63_count": self.complete_63_count,
            "complete_126_count": self.complete_126_count,
            "complete_252_count": self.complete_252_count,
        }


@dataclass(frozen=True)
class ReportDatabaseSummary:
    """Immutable count-only database facts for one report scope."""

    selected_listing_count: int
    source_listing_count: int
    source_row_count: int
    payload_listing_count: int
    payload_row_count: int
    published_listing_count: int
    published_row_count: int
    providers: tuple[ReportDimensionCoverage, ...]
    markets: tuple[ReportDimensionCoverage, ...]
    instrument_types: tuple[ReportDimensionCoverage, ...]
    dates: ReportDateCoverage
    versions: tuple[ReportVersionCoverage, ...]
    features: tuple[ReportFeatureCoverage, ...]
    benchmark: ReportBenchmarkCoverage

    def __post_init__(self) -> None:
        for name in (
            "selected_listing_count",
            "source_listing_count",
            "source_row_count",
            "payload_listing_count",
            "payload_row_count",
            "published_listing_count",
            "published_row_count",
        ):
            _validate_nonnegative_int(name, getattr(self, name))
        _validate_dimension_rows("providers", self.providers)
        _validate_dimension_rows("markets", self.markets)
        _validate_dimension_rows("instrument_types", self.instrument_types)
        for values in (self.providers, self.markets, self.instrument_types):
            if (
                sum(item.listing_count for item in values)
                != self.selected_listing_count
            ):
                raise ValueError("Dimension listing counts do not reconcile.")
            if sum(item.source_row_count for item in values) != self.source_row_count:
                raise ValueError("Dimension source rows do not reconcile.")
            if sum(item.payload_row_count for item in values) != self.payload_row_count:
                raise ValueError("Dimension payload rows do not reconcile.")
            if (
                sum(item.published_row_count for item in values)
                != self.published_row_count
            ):
                raise ValueError("Dimension published rows do not reconcile.")
        if tuple(item.feature_name for item in self.features) != REPORT_FEATURE_FIELDS:
            raise ValueError("Report feature coverage order is invalid.")
        if tuple(item.calculation_version for item in self.versions) != tuple(
            sorted(item.calculation_version for item in self.versions)
        ):
            raise ValueError("Report versions must be sorted.")
        if sum(item.row_count for item in self.versions) != self.payload_row_count:
            raise ValueError("Version rows do not reconcile with payload rows.")
        if self.source_listing_count > self.selected_listing_count:
            raise ValueError("Source listing count exceeds selected listings.")
        if self.payload_listing_count > self.selected_listing_count:
            raise ValueError("Payload listing count exceeds selected listings.")
        if self.published_listing_count > self.selected_listing_count:
            raise ValueError("Published listing count exceeds selected listings.")
        if self.dates.effective_date_source_rows > self.source_row_count:
            raise ValueError("Effective-date source rows exceed source rows.")
        if self.dates.effective_date_payload_rows > self.payload_row_count:
            raise ValueError("Effective-date payload rows exceed payload rows.")
        if self.dates.effective_date_published_rows > self.published_row_count:
            raise ValueError("Effective-date published rows exceed published rows.")
        if (
            self.benchmark.supported_listing_count
            + self.benchmark.unsupported_listing_count
            != self.selected_listing_count
        ):
            raise ValueError("Benchmark listing counts do not reconcile.")
        if (
            self.benchmark.benchmark_linked_row_count
            + self.benchmark.benchmark_unlinked_row_count
            != self.payload_row_count
        ):
            raise ValueError("Benchmark lineage rows do not reconcile.")
        if self.benchmark.aligned_row_count > self.benchmark.benchmark_linked_row_count:
            raise ValueError("Aligned rows exceed benchmark-linked rows.")
        if (
            self.benchmark.effective_date_aligned_count
            > self.dates.effective_date_payload_rows
        ):
            raise ValueError("Effective-date aligned rows exceed payload rows.")
        if any(
            value > self.benchmark.aligned_row_count
            for value in (
                self.benchmark.complete_20_count,
                self.benchmark.complete_50_count,
                self.benchmark.complete_60_count,
                self.benchmark.complete_63_count,
                self.benchmark.complete_126_count,
                self.benchmark.complete_252_count,
            )
        ):
            raise ValueError("Benchmark complete-window rows exceed aligned rows.")

    def to_dict(self) -> dict[str, object]:
        return {
            "selected_listing_count": self.selected_listing_count,
            "source_listing_count": self.source_listing_count,
            "source_row_count": self.source_row_count,
            "payload_listing_count": self.payload_listing_count,
            "payload_row_count": self.payload_row_count,
            "published_listing_count": self.published_listing_count,
            "published_row_count": self.published_row_count,
            "providers": [item.to_dict() for item in self.providers],
            "markets": [item.to_dict() for item in self.markets],
            "instrument_types": [
                item.to_dict() for item in self.instrument_types
            ],
            "dates": self.dates.to_dict(),
            "versions": [item.to_dict() for item in self.versions],
            "features": [item.to_dict() for item in self.features],
            "benchmark": self.benchmark.to_dict(),
        }


@dataclass(frozen=True)
class _PayloadVersionRow:
    provider_listing_id: UUID
    calculation_version: str
    first_date: date
    last_date: date
    row_count: int
    effective_date_row_count: int
    benchmark_linked_row_count: int
    aligned_row_count: int
    effective_date_aligned_count: int
    complete_20_count: int
    complete_50_count: int
    complete_60_count: int
    complete_63_count: int
    complete_126_count: int
    complete_252_count: int


@dataclass(frozen=True)
class _PublishedListingRow:
    provider_listing_id: UUID
    row_count: int
    effective_date_row_count: int


def select_report_database_summary(
    *,
    cursor: Any,
    scope: TechIndicatorsScope,
    effective_date: date | None = None,
    publication_id: UUID | None = None,
) -> ReportDatabaseSummary:
    """Return set-based count and quality facts without feature payloads.

    A publication ID selects its normalized candidate A/B membership image,
    including unpublished `BUILDING` or `PREPARED` work. With no publication
    ID, the selected payload is the current published view. The caller owns the
    cursor and transaction; this function never mutates or changes isolation.
    """

    _validate_cursor(cursor)
    if not isinstance(scope, TechIndicatorsScope):
        raise TypeError("scope must be a TechIndicatorsScope.")
    if effective_date is not None and type(effective_date) is not date:
        raise TypeError("effective_date must be a date or None.")
    if publication_id is not None and not isinstance(publication_id, UUID):
        raise TypeError("publication_id must be a UUID or None.")
    if effective_date is not None and scope.start_date is not None and not (
        scope.start_date <= effective_date <= scope.end_date
    ):
        raise ValueError("effective_date must be inside the scope date range.")

    listings = select_eligible_listings(cursor=cursor, scope=scope)
    if not listings:
        return _empty_summary()
    identifiers = tuple(item.provider_listing_id for item in listings)
    payload_rows = _select_payload_version_rows(
        cursor=cursor,
        identifiers=identifiers,
        scope=scope,
        effective_date=effective_date,
        publication_id=publication_id,
    )
    if publication_id is None:
        published_rows = _published_rows_from_payload(payload_rows)
    else:
        published_rows = _select_published_listing_rows(
            cursor=cursor,
            identifiers=identifiers,
            scope=scope,
            effective_date=effective_date,
        )
    feature_rows = _select_feature_coverage(
        cursor=cursor,
        identifiers=identifiers,
        supported_identifiers=tuple(
            item.provider_listing_id
            for item in listings
            if is_spx_supported_subject(item)
        ),
        scope=scope,
        publication_id=publication_id,
    )
    source_effective_date_rows = _select_effective_date_source_count(
        cursor=cursor,
        identifiers=identifiers,
        effective_date=effective_date,
    )
    return _build_summary(
        listings=listings,
        payload_rows=payload_rows,
        published_rows=published_rows,
        feature_rows=feature_rows,
        source_effective_date_rows=source_effective_date_rows,
    )


def _select_payload_version_rows(
    *,
    cursor: Any,
    identifiers: tuple[UUID, ...],
    scope: TechIndicatorsScope,
    effective_date: date | None,
    publication_id: UUID | None,
) -> tuple[_PayloadVersionRow, ...]:
    cte, parameters = _payload_cte(
        identifiers=identifiers,
        scope=scope,
        publication_id=publication_id,
    )
    parameters.extend((effective_date, effective_date))
    cursor.execute(
        f"""
        {cte}
        SELECT
            provider_listing_id,
            calculation_version,
            min(trading_date),
            max(trading_date),
            count(*),
            count(*) FILTER (WHERE trading_date = %s),
            count(*) FILTER (
                WHERE relative_strength_benchmark_provider_listing_id IS NOT NULL
            ),
            count(rel_spx),
            count(rel_spx) FILTER (WHERE trading_date = %s),
            count(*) FILTER (
                WHERE pct_rel_spx_20 IS NOT NULL
                  AND relative_return_spx_20d_pct IS NOT NULL
            ),
            count(pct_rel_spx_50),
            count(*) FILTER (
                WHERE spx_beta_60d IS NOT NULL
                  AND spx_correlation_60d IS NOT NULL
            ),
            count(relative_return_spx_63d_pct),
            count(relative_return_spx_126d_pct),
            count(*) FILTER (
                WHERE relative_return_spx_252d_pct IS NOT NULL
                  AND spx_beta_252d IS NOT NULL
                  AND spx_correlation_252d IS NOT NULL
            )
        FROM report_payload
        GROUP BY provider_listing_id, calculation_version
        """,
        tuple(parameters),
    )
    rows = cursor.fetchall()
    if not isinstance(rows, list):
        raise ValueError("Report payload coverage query returned invalid rows.")
    result: list[_PayloadVersionRow] = []
    seen: set[tuple[UUID, str]] = set()
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 15:
            raise ValueError("Report payload coverage query returned invalid rows.")
        key = (row[0], row[1])
        if row[0] not in identifiers or key in seen:
            raise ValueError("Report payload coverage query returned identity drift.")
        try:
            model = _PayloadVersionRow(*row)
            _validate_payload_version_row(model)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Report payload coverage query returned invalid contract data."
            ) from exc
        result.append(model)
        seen.add(key)
    return tuple(result)


def _select_published_listing_rows(
    *,
    cursor: Any,
    identifiers: tuple[UUID, ...],
    scope: TechIndicatorsScope,
    effective_date: date | None,
) -> tuple[_PublishedListingRow, ...]:
    conditions = ["provider_listing_id = ANY(%s::uuid[])"]
    where_parameters: list[object] = [list(identifiers)]
    _append_date_condition(conditions, where_parameters, scope=scope)
    parameters = [effective_date, *where_parameters]
    cursor.execute(
        f"""
        SELECT
            provider_listing_id,
            count(*),
            count(*) FILTER (WHERE trading_date = %s)
        FROM stonks.ohlcv_daily_tech_indicators
        WHERE {' AND '.join(conditions)}
        GROUP BY provider_listing_id
        ORDER BY provider_listing_id
        """,
        tuple(parameters),
    )
    rows = cursor.fetchall()
    if not isinstance(rows, list):
        raise ValueError("Report published coverage query returned invalid rows.")
    result: list[_PublishedListingRow] = []
    seen: set[UUID] = set()
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 3:
            raise ValueError("Report published coverage query returned invalid rows.")
        if row[0] not in identifiers or row[0] in seen:
            raise ValueError("Report published coverage query returned identity drift.")
        model = _PublishedListingRow(*row)
        _validate_nonnegative_int("published_row_count", model.row_count)
        _validate_nonnegative_int(
            "published_effective_date_row_count",
            model.effective_date_row_count,
        )
        result.append(model)
        seen.add(row[0])
    return tuple(result)


def _published_rows_from_payload(
    payload_rows: tuple[_PayloadVersionRow, ...],
) -> tuple[_PublishedListingRow, ...]:
    counts: dict[UUID, list[int]] = defaultdict(lambda: [0, 0])
    for row in payload_rows:
        values = counts[row.provider_listing_id]
        values[0] += row.row_count
        values[1] += row.effective_date_row_count
    return tuple(
        _PublishedListingRow(provider_listing_id, *counts[provider_listing_id])
        for provider_listing_id in sorted(counts)
    )


def _select_feature_coverage(
    *,
    cursor: Any,
    identifiers: tuple[UUID, ...],
    supported_identifiers: tuple[UUID, ...],
    scope: TechIndicatorsScope,
    publication_id: UUID | None,
) -> tuple[ReportFeatureCoverage, ...]:
    history_rows = _select_history_coverage(
        cursor=cursor,
        identifiers=identifiers,
        supported_identifiers=supported_identifiers,
        scope=scope,
        publication_id=publication_id,
    )
    cte, parameters = _payload_cte(
        identifiers=identifiers,
        scope=scope,
        publication_id=publication_id,
    )
    expressions = _feature_coverage_expressions()
    cursor.execute(
        f"""
        {cte}
        SELECT {', '.join(expressions)}
        FROM report_payload
        """,
        tuple(parameters),
    )
    row = cursor.fetchone()
    expected_length = 1 + len(REPORT_FEATURE_FIELDS) + len(
        _GUARANTEED_AFTER_WARMUP
    )
    if not isinstance(row, (tuple, list)) or len(row) != expected_length:
        raise ValueError("Report feature coverage query returned invalid data.")
    total = row[0]
    _validate_nonnegative_int("feature_eligible_row_count", total)
    if sum(count for _observations, count, _supported in history_rows) != total:
        raise ValueError("History rows do not reconcile with feature rows.")
    result: list[ReportFeatureCoverage] = []
    offset = 1
    unsupported_total = sum(
        count - supported for _observations, count, supported in history_rows
    )
    for field in REPORT_FEATURE_FIELDS:
        populated = row[offset]
        offset += 1
        nulls = total - populated
        minimum = _MINIMUM_OBSERVATIONS[field]
        warmup = sum(
            (supported if field in _SPX_FIELDS else count)
            for observations, count, supported in history_rows
            if observations < minimum
        )
        unsupported = unsupported_total if field in _SPX_FIELDS else 0
        unexpected = row[offset] if field in _GUARANTEED_AFTER_WARMUP else 0
        if field in _GUARANTEED_AFTER_WARMUP:
            offset += 1
        dependency = nulls - warmup - unsupported - unexpected
        try:
            result.append(
                ReportFeatureCoverage(
                    feature_name=field,
                    eligible_row_count=total,
                    populated_count=populated,
                    null_count=nulls,
                    warmup_null_count=warmup,
                    dependency_null_count=dependency,
                    unsupported_null_count=unsupported,
                    unexpected_null_count=unexpected,
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Report feature coverage query returned invalid contract data."
            ) from exc
    return tuple(result)


def _feature_coverage_expressions() -> tuple[str, ...]:
    expressions: list[str] = ["count(*)"]
    for field in REPORT_FEATURE_FIELDS:
        minimum = _MINIMUM_OBSERVATIONS[field]
        expressions.append(f"count({field})")
        if field in _GUARANTEED_AFTER_WARMUP:
            expressions.append(
                f"count(*) FILTER (WHERE {field} IS NULL "
                f"AND history_observation_count >= {minimum})"
            )
    return tuple(expressions)


def _select_history_coverage(
    *,
    cursor: Any,
    identifiers: tuple[UUID, ...],
    supported_identifiers: tuple[UUID, ...],
    scope: TechIndicatorsScope,
    publication_id: UUID | None,
) -> tuple[tuple[int, int, int], ...]:
    cte, parameters = _payload_cte(
        identifiers=identifiers,
        scope=scope,
        publication_id=publication_id,
    )
    parameters.append(list(supported_identifiers))
    cursor.execute(
        f"""
        {cte}
        SELECT
            history_observation_count,
            count(*),
            count(*) FILTER (WHERE provider_listing_id = ANY(%s::uuid[]))
        FROM report_payload
        GROUP BY history_observation_count
        """,
        tuple(parameters),
    )
    rows = cursor.fetchall()
    if not isinstance(rows, list):
        raise ValueError("Report history coverage query returned invalid rows.")
    result: list[tuple[int, int, int]] = []
    seen: set[int] = set()
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 3:
            raise ValueError("Report history coverage query returned invalid data.")
        observations, count, supported = row
        if type(observations) is not int or observations <= 0 or observations in seen:
            raise ValueError("Report history coverage identity is invalid.")
        _validate_nonnegative_int("history_row_count", count)
        _validate_nonnegative_int("supported_history_row_count", supported)
        if supported > count:
            raise ValueError("Supported history rows exceed total rows.")
        result.append((observations, count, supported))
        seen.add(observations)
    return tuple(result)


def _payload_cte(
    *,
    identifiers: tuple[UUID, ...],
    scope: TechIndicatorsScope,
    publication_id: UUID | None,
) -> tuple[str, list[object]]:
    if publication_id is None:
        conditions = ["provider_listing_id = ANY(%s::uuid[])"]
        parameters = [list(identifiers)]
        _append_date_condition(conditions, parameters, scope=scope)
        return (
            "WITH report_payload AS ("
            " SELECT * FROM stonks.ohlcv_daily_tech_indicators"
            f" WHERE {' AND '.join(conditions)}"
            ")",
            parameters,
        )
    where_a = where_b = ""
    parameters: list[object] = [publication_id, list(identifiers)]
    if scope.start_date is not None:
        where_a = " AND payload.trading_date BETWEEN %s AND %s"
        parameters.extend((scope.start_date, scope.end_date))
    parameters.extend((publication_id, list(identifiers)))
    if scope.start_date is not None:
        where_b = " AND payload.trading_date BETWEEN %s AND %s"
        parameters.extend((scope.start_date, scope.end_date))
    return (
        """
        WITH report_payload AS (
            SELECT payload.*
            FROM stonks.tech_indicators_publication_listing AS membership
            INNER JOIN stonks.ohlcv_daily_tech_indicators_a AS payload
                ON payload.provider_listing_id = membership.provider_listing_id
            WHERE membership.publication_id = %s
              AND membership.provider_listing_id = ANY(%s::uuid[])
              AND membership.action = 'PRESENT'
              AND membership.target_slot = 'A'
        """
        + where_a
        + """
            UNION ALL
            SELECT payload.*
            FROM stonks.tech_indicators_publication_listing AS membership
            INNER JOIN stonks.ohlcv_daily_tech_indicators_b AS payload
                ON payload.provider_listing_id = membership.provider_listing_id
            WHERE membership.publication_id = %s
              AND membership.provider_listing_id = ANY(%s::uuid[])
              AND membership.action = 'PRESENT'
              AND membership.target_slot = 'B'
        """
        + where_b
        + ")",
        parameters,
    )


def _select_effective_date_source_count(
    *,
    cursor: Any,
    identifiers: tuple[UUID, ...],
    effective_date: date | None,
) -> int:
    if effective_date is None:
        return 0
    cursor.execute(
        """
        SELECT count(*)
        FROM stonks.ohlcv_daily
        WHERE provider_listing_id = ANY(%s::uuid[])
          AND trading_date = %s
        """,
        (list(identifiers), effective_date),
    )
    row = cursor.fetchone()
    if not isinstance(row, (tuple, list)) or len(row) != 1:
        raise ValueError("Report source-date coverage query returned invalid data.")
    _validate_nonnegative_int("effective_date_source_rows", row[0])
    return row[0]


def _build_summary(
    *,
    listings: tuple[EligibleListing, ...],
    payload_rows: tuple[_PayloadVersionRow, ...],
    published_rows: tuple[_PublishedListingRow, ...],
    feature_rows: tuple[ReportFeatureCoverage, ...],
    source_effective_date_rows: int,
) -> ReportDatabaseSummary:
    payload_by_listing: dict[UUID, int] = defaultdict(int)
    published_by_listing = {item.provider_listing_id: item for item in published_rows}
    versions: dict[str, tuple[set[UUID], int]] = {}
    payload_first: date | None = None
    payload_last: date | None = None
    payload_effective = 0
    benchmark_counts = [0] * 8
    for row in payload_rows:
        payload_by_listing[row.provider_listing_id] += row.row_count
        listing_ids, count = versions.setdefault(
            row.calculation_version, (set(), 0)
        )
        listing_ids.add(row.provider_listing_id)
        versions[row.calculation_version] = (listing_ids, count + row.row_count)
        payload_first = row.first_date if payload_first is None else min(
            payload_first, row.first_date
        )
        payload_last = row.last_date if payload_last is None else max(
            payload_last, row.last_date
        )
        payload_effective += row.effective_date_row_count
        for index, value in enumerate(
            (
                row.benchmark_linked_row_count,
                row.aligned_row_count,
                row.effective_date_aligned_count,
                row.complete_20_count,
                row.complete_50_count,
                row.complete_60_count,
                row.complete_63_count,
                row.complete_126_count,
                row.complete_252_count,
            )
        ):
            if index == 0:
                continue
            benchmark_counts[index - 1] += value
    linked = sum(row.benchmark_linked_row_count for row in payload_rows)
    source_first = min(
        (item.first_trading_date for item in listings if item.first_trading_date),
        default=None,
    )
    source_last = max(
        (item.last_trading_date for item in listings if item.last_trading_date),
        default=None,
    )
    published_effective = sum(
        item.effective_date_row_count for item in published_rows
    )
    payload_total = sum(payload_by_listing.values())
    published_total = sum(item.row_count for item in published_rows)
    if any(item.eligible_row_count != payload_total for item in feature_rows):
        raise ValueError("Feature rows do not reconcile with payload rows.")
    supported = sum(is_spx_supported_subject(item) for item in listings)
    return ReportDatabaseSummary(
        selected_listing_count=len(listings),
        source_listing_count=sum(
            item.source_observation_count > 0 for item in listings
        ),
        source_row_count=sum(item.source_observation_count for item in listings),
        payload_listing_count=sum(count > 0 for count in payload_by_listing.values()),
        payload_row_count=payload_total,
        published_listing_count=len(published_rows),
        published_row_count=published_total,
        providers=_dimension_rows(
            listings, payload_by_listing, published_by_listing, "provider_code"
        ),
        markets=_dimension_rows(
            listings, payload_by_listing, published_by_listing, "market"
        ),
        instrument_types=_dimension_rows(
            listings,
            payload_by_listing,
            published_by_listing,
            "instrument_type_code",
        ),
        dates=ReportDateCoverage(
            source_first_date=source_first,
            source_last_date=source_last,
            payload_first_date=payload_first,
            payload_last_date=payload_last,
            effective_date_source_rows=source_effective_date_rows,
            effective_date_payload_rows=payload_effective,
            effective_date_published_rows=published_effective,
        ),
        versions=tuple(
            ReportVersionCoverage(
                calculation_version=version,
                listing_count=len(values[0]),
                row_count=values[1],
            )
            for version, values in sorted(versions.items())
        ),
        features=feature_rows,
        benchmark=ReportBenchmarkCoverage(
            supported_listing_count=supported,
            unsupported_listing_count=len(listings) - supported,
            benchmark_linked_row_count=linked,
            benchmark_unlinked_row_count=payload_total - linked,
            aligned_row_count=benchmark_counts[0],
            effective_date_aligned_count=benchmark_counts[1],
            complete_20_count=benchmark_counts[2],
            complete_50_count=benchmark_counts[3],
            complete_60_count=benchmark_counts[4],
            complete_63_count=benchmark_counts[5],
            complete_126_count=benchmark_counts[6],
            complete_252_count=benchmark_counts[7],
        ),
    )


def _dimension_rows(
    listings: tuple[EligibleListing, ...],
    payload: dict[UUID, int],
    published: dict[UUID, _PublishedListingRow],
    attribute: str,
) -> tuple[ReportDimensionCoverage, ...]:
    groups: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for listing in listings:
        values = groups[getattr(listing, attribute)]
        values[0] += 1
        values[1] += listing.source_observation_count
        values[2] += payload.get(listing.provider_listing_id, 0)
        row = published.get(listing.provider_listing_id)
        values[3] += 0 if row is None else row.row_count
    return tuple(
        ReportDimensionCoverage(code, *values)
        for code, values in sorted(groups.items())
    )


def _empty_summary() -> ReportDatabaseSummary:
    features = tuple(
        ReportFeatureCoverage(field, 0, 0, 0, 0, 0, 0, 0)
        for field in REPORT_FEATURE_FIELDS
    )
    return ReportDatabaseSummary(
        selected_listing_count=0,
        source_listing_count=0,
        source_row_count=0,
        payload_listing_count=0,
        payload_row_count=0,
        published_listing_count=0,
        published_row_count=0,
        providers=(),
        markets=(),
        instrument_types=(),
        dates=ReportDateCoverage(None, None, None, None, 0, 0, 0),
        versions=(),
        features=features,
        benchmark=ReportBenchmarkCoverage(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
        ),
    )


def _append_date_condition(
    conditions: list[str],
    parameters: list[object],
    *,
    scope: TechIndicatorsScope,
) -> None:
    if scope.start_date is not None:
        conditions.append("trading_date BETWEEN %s AND %s")
        parameters.extend((scope.start_date, scope.end_date))


def _validate_payload_version_row(row: _PayloadVersionRow) -> None:
    if not isinstance(row.provider_listing_id, UUID):
        raise TypeError("provider_listing_id must be a UUID.")
    _validate_code("calculation_version", row.calculation_version)
    _validate_date_range("payload", row.first_date, row.last_date)
    for name in (
        "row_count",
        "effective_date_row_count",
        "benchmark_linked_row_count",
        "aligned_row_count",
        "effective_date_aligned_count",
        "complete_20_count",
        "complete_50_count",
        "complete_60_count",
        "complete_63_count",
        "complete_126_count",
        "complete_252_count",
    ):
        _validate_nonnegative_int(name, getattr(row, name))
    if row.row_count == 0:
        raise ValueError("Grouped payload coverage cannot be empty.")


def _validate_dimension_rows(
    field_name: str,
    values: tuple[ReportDimensionCoverage, ...],
) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(item, ReportDimensionCoverage) for item in values
    ):
        raise TypeError(f"{field_name} must contain dimension rows.")
    codes = tuple(item.code for item in values)
    if codes != tuple(sorted(set(codes))):
        raise ValueError(f"{field_name} must have sorted unique codes.")


def _validate_date_range(
    prefix: str,
    first_date: date | None,
    last_date: date | None,
) -> None:
    if (first_date is None) != (last_date is None):
        raise ValueError(f"{prefix} dates must both be null or populated.")
    if first_date is not None and (
        type(first_date) is not date
        or type(last_date) is not date
        or first_date > last_date
    ):
        raise ValueError(f"{prefix} date range is invalid.")


def _validate_nonnegative_int(field_name: str, value: object) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")


def _validate_code(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty and trimmed.")


def _validate_cursor(cursor: Any) -> None:
    if cursor is None or not callable(getattr(cursor, "execute", None)):
        raise TypeError("cursor must provide execute().")
    if not callable(getattr(cursor, "fetchall", None)):
        raise TypeError("cursor must provide fetchall().")
    if not callable(getattr(cursor, "fetchone", None)):
        raise TypeError("cursor must provide fetchone().")


def _date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


__all__ = [
    "REPORT_FEATURE_FIELDS",
    "ReportBenchmarkCoverage",
    "ReportDatabaseSummary",
    "ReportDateCoverage",
    "ReportDimensionCoverage",
    "ReportFeatureCoverage",
    "ReportVersionCoverage",
    "select_report_database_summary",
]
