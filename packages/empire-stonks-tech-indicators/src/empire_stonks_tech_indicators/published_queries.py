"""Read-only published feature, ranking, and model-input queries."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from empire_stonks_tech_indicators.config import BenchmarkConfig
from empire_stonks_tech_indicators.models import (
    PYTHON_FEATURE_FIELDS,
    TechIndicatorsScope,
)
from empire_stonks_tech_indicators.queries import (
    EligibleListing,
    select_eligible_listings,
)
from empire_stonks_tech_indicators.readiness import decide_source_readiness
from empire_stonks_tech_indicators.state import iter_state_comparison_pages
from empire_stonks_tech_indicators.subject_policy import (
    is_spx_supported_subject,
)


BENCHMARK_CONTRACT_VERSION = "TECH_INDICATORS_SPX_V1"
MAX_MODEL_INPUT_ROWS = 25_000
MAX_RANKING_ROWS = 25_000

COPIED_SOURCE_FIELDS = ("open", "high", "low", "close", "volume")
GENERATED_FEATURE_FIELDS = (
    "dollar_volume",
    "intraday_return_1d_pct",
    "daily_range_pct",
    "close_location_1d",
    "pct_sma_20",
    "pct_sma_50",
    "pct_sma_200",
    "pct_ema_20",
    "pct_ema_50",
    "pct_sma_20_vs_50",
    "pct_sma_20_vs_200",
    "pct_sma_50_vs_200",
    "pct_hh_20",
    "pct_hh_50",
    "pct_hh_252",
    "pct_ll_20",
    "pct_ll_50",
    "atr_pct_14",
    "bollinger_percent_b_20_2",
    "bollinger_bandwidth_20_2",
    "volume_ratio_20",
    "macd_12_26_pct",
    "macd_histogram_12_26_9_pct",
)
PUBLISHED_MODEL_INPUT_FIELDS = (
    *COPIED_SOURCE_FIELDS,
    *PYTHON_FEATURE_FIELDS,
    *GENERATED_FEATURE_FIELDS,
)
PUBLISHED_RANKING_FIELDS = (
    *PYTHON_FEATURE_FIELDS,
    *GENERATED_FEATURE_FIELDS,
)

_MODEL_INPUT_FIELD_SET = frozenset(PUBLISHED_MODEL_INPUT_FIELDS)
_RANKING_FIELD_SET = frozenset(PUBLISHED_RANKING_FIELDS)
_READINESS_REASON_ORDER = (
    "NO_ACTIVE_PUBLICATION",
    "SCOPE_MISMATCH",
    "COVERAGE_INCOMPLETE",
    "VERSION_MISMATCH",
    "SOURCE_DRIFT",
    "PUBLICATION_NOT_READY",
    "BENCHMARK_UNAVAILABLE",
    "BENCHMARK_MISMATCH",
    "SPX_COVERAGE_INCOMPLETE",
)
_CALCULATION_VERSION_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


@dataclass(frozen=True)
class PublishedFeatureCoverage:
    """One eligible listing's source and published-view coverage facts."""

    provider_listing_id: UUID
    provider_code: str
    market: str
    ticker: str
    status: str
    source_first_trading_date: date | None
    source_last_trading_date: date | None
    source_row_count: int
    published_first_trading_date: date | None
    published_last_trading_date: date | None
    published_row_count: int
    latest_calculated_at: datetime | None
    latest_updated_at: datetime | None
    calculation_versions: tuple[str, ...]
    benchmark_provider_listing_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        _validate_identity(self)
        _validate_coverage(
            prefix="source",
            first_date=self.source_first_trading_date,
            last_date=self.source_last_trading_date,
            row_count=self.source_row_count,
        )
        _validate_coverage(
            prefix="published",
            first_date=self.published_first_trading_date,
            last_date=self.published_last_trading_date,
            row_count=self.published_row_count,
        )
        _validate_optional_aware_datetime(
            "latest_calculated_at",
            self.latest_calculated_at,
        )
        _validate_optional_aware_datetime(
            "latest_updated_at",
            self.latest_updated_at,
        )
        _validate_sorted_text_tuple(
            "calculation_versions",
            self.calculation_versions,
        )
        _validate_sorted_uuid_tuple(
            "benchmark_provider_listing_ids",
            self.benchmark_provider_listing_ids,
        )
        if self.published_row_count == 0 and (
            self.latest_calculated_at is not None
            or self.latest_updated_at is not None
            or self.calculation_versions
            or self.benchmark_provider_listing_ids
        ):
            raise ValueError("Empty published coverage cannot have payload facts.")
        if self.published_row_count > 0 and not self.calculation_versions:
            raise ValueError("Published coverage requires a calculation version.")

    @property
    def source_and_published_keys_match(self) -> bool:
        return (
            self.source_first_trading_date
            == self.published_first_trading_date
            and self.source_last_trading_date
            == self.published_last_trading_date
            and self.source_row_count == self.published_row_count
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "provider_code": self.provider_code,
            "market": self.market,
            "ticker": self.ticker,
            "status": self.status,
            "source_first_trading_date": _date_string(
                self.source_first_trading_date
            ),
            "source_last_trading_date": _date_string(
                self.source_last_trading_date
            ),
            "source_row_count": self.source_row_count,
            "published_first_trading_date": _date_string(
                self.published_first_trading_date
            ),
            "published_last_trading_date": _date_string(
                self.published_last_trading_date
            ),
            "published_row_count": self.published_row_count,
            "latest_calculated_at": _datetime_string(
                self.latest_calculated_at
            ),
            "latest_updated_at": _datetime_string(self.latest_updated_at),
            "calculation_versions": list(self.calculation_versions),
            "benchmark_provider_listing_ids": [
                str(value) for value in self.benchmark_provider_listing_ids
            ],
            "source_and_published_keys_match": (
                self.source_and_published_keys_match
            ),
        }


@dataclass(frozen=True)
class PublishedFeatureRankingRow:
    """One ordered latest-date feature value without a strategy threshold."""

    provider_listing_id: UUID
    provider_code: str
    market: str
    ticker: str
    trading_date: date
    feature_name: str
    feature_value: float | int | None

    def __post_init__(self) -> None:
        _validate_identity(self)
        if type(self.trading_date) is not date:
            raise TypeError("trading_date must be a date.")
        _validate_feature_names((self.feature_name,), ranking=True)
        _validate_feature_value(self.feature_value)

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "provider_code": self.provider_code,
            "market": self.market,
            "ticker": self.ticker,
            "trading_date": self.trading_date.isoformat(),
            "feature_name": self.feature_name,
            "feature_value": self.feature_value,
        }


@dataclass(frozen=True)
class PublishedFeatureFreshness:
    """One listing's threshold-free published freshness facts as of a date."""

    provider_listing_id: UUID
    provider_code: str
    market: str
    ticker: str
    as_of_date: date
    latest_trading_date: date | None
    calendar_age_days: int | None
    latest_calculated_at: datetime | None
    latest_updated_at: datetime | None
    calculation_versions: tuple[str, ...]
    benchmark_provider_listing_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        _validate_identity(self)
        if type(self.as_of_date) is not date:
            raise TypeError("as_of_date must be a date.")
        if self.latest_trading_date is not None and (
            type(self.latest_trading_date) is not date
            or self.latest_trading_date > self.as_of_date
        ):
            raise ValueError("latest_trading_date must not follow as_of_date.")
        if self.latest_trading_date is None:
            if self.calendar_age_days is not None:
                raise ValueError("No-data freshness must have null age.")
        elif self.calendar_age_days != (
            self.as_of_date - self.latest_trading_date
        ).days:
            raise ValueError("calendar_age_days does not match freshness dates.")
        _validate_optional_aware_datetime(
            "latest_calculated_at",
            self.latest_calculated_at,
        )
        _validate_optional_aware_datetime(
            "latest_updated_at",
            self.latest_updated_at,
        )
        _validate_sorted_text_tuple(
            "calculation_versions",
            self.calculation_versions,
        )
        _validate_sorted_uuid_tuple(
            "benchmark_provider_listing_ids",
            self.benchmark_provider_listing_ids,
        )
        if self.latest_trading_date is None and (
            self.latest_calculated_at is not None
            or self.latest_updated_at is not None
            or self.calculation_versions
            or self.benchmark_provider_listing_ids
        ):
            raise ValueError("No-data freshness cannot have payload facts.")

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "provider_code": self.provider_code,
            "market": self.market,
            "ticker": self.ticker,
            "as_of_date": self.as_of_date.isoformat(),
            "latest_trading_date": _date_string(self.latest_trading_date),
            "calendar_age_days": self.calendar_age_days,
            "latest_calculated_at": _datetime_string(
                self.latest_calculated_at
            ),
            "latest_updated_at": _datetime_string(self.latest_updated_at),
            "calculation_versions": list(self.calculation_versions),
            "benchmark_provider_listing_ids": [
                str(value) for value in self.benchmark_provider_listing_ids
            ],
        }


@dataclass(frozen=True)
class PublishedReadinessToken:
    """Transaction-local identity for one ready model-input snapshot."""

    value: str
    effective_date: date
    calculation_version: str
    benchmark_provider_listing_id: UUID | None
    listing_count: int
    model_row_count: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or len(self.value) != 64
            or any(character not in "0123456789abcdef" for character in self.value)
        ):
            raise ValueError("value must be a lowercase SHA-256 digest.")
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date.")
        _validate_calculation_version(self.calculation_version)
        _validate_optional_uuid(
            "benchmark_provider_listing_id",
            self.benchmark_provider_listing_id,
        )
        _validate_nonnegative_int("listing_count", self.listing_count)
        _validate_nonnegative_int("model_row_count", self.model_row_count)
        if self.model_row_count > self.listing_count:
            raise ValueError("model_row_count cannot exceed listing_count.")

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "effective_date": self.effective_date.isoformat(),
            "calculation_version": self.calculation_version,
            "benchmark_provider_listing_id": _uuid_string(
                self.benchmark_provider_listing_id
            ),
            "listing_count": self.listing_count,
            "model_row_count": self.model_row_count,
        }


@dataclass(frozen=True)
class PublishedModelInputRow:
    """One bounded projected row from the ready published-view snapshot."""

    provider_listing_id: UUID
    provider_code: str
    market: str
    ticker: str
    trading_date: date
    calculation_version: str
    benchmark_provider_listing_id: UUID | None
    values: tuple[tuple[str, Decimal | float | int | None], ...]

    def __post_init__(self) -> None:
        _validate_identity(self)
        if type(self.trading_date) is not date:
            raise TypeError("trading_date must be a date.")
        _validate_calculation_version(self.calculation_version)
        _validate_optional_uuid(
            "benchmark_provider_listing_id",
            self.benchmark_provider_listing_id,
        )
        if not isinstance(self.values, tuple) or any(
            not isinstance(item, tuple) or len(item) != 2 for item in self.values
        ):
            raise TypeError("values must contain two-item tuples.")
        names = tuple(item[0] for item in self.values)
        _validate_feature_names(names, ranking=False)
        for _name, value in self.values:
            _validate_feature_value(value, allow_decimal=True)

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "provider_code": self.provider_code,
            "market": self.market,
            "ticker": self.ticker,
            "trading_date": self.trading_date.isoformat(),
            "calculation_version": self.calculation_version,
            "benchmark_provider_listing_id": _uuid_string(
                self.benchmark_provider_listing_id
            ),
            "values": {
                name: _json_value(value) for name, value in self.values
            },
        }


@dataclass(frozen=True)
class PublishedModelInputSnapshot:
    """Ready token plus rows, or bounded reasons and no model rows."""

    effective_date: date
    calculation_version: str
    feature_names: tuple[str, ...]
    selected_listing_count: int
    effective_date_source_row_count: int
    token: PublishedReadinessToken | None
    rows: tuple[PublishedModelInputRow, ...]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date.")
        _validate_calculation_version(self.calculation_version)
        _validate_feature_names(self.feature_names, ranking=False)
        _validate_nonnegative_int(
            "selected_listing_count",
            self.selected_listing_count,
        )
        _validate_nonnegative_int(
            "effective_date_source_row_count",
            self.effective_date_source_row_count,
        )
        if not isinstance(self.rows, tuple) or any(
            not isinstance(row, PublishedModelInputRow) for row in self.rows
        ):
            raise TypeError("rows must contain PublishedModelInputRow values.")
        _validate_reasons(self.reasons)
        if self.reasons:
            if self.token is not None or self.rows:
                raise ValueError("A failed snapshot cannot return a token or rows.")
        else:
            if not isinstance(self.token, PublishedReadinessToken):
                raise ValueError("A ready snapshot requires a token.")
            if len(self.rows) != self.effective_date_source_row_count:
                raise ValueError(
                    "Ready model rows must match effective-date source rows."
                )

    @property
    def ready(self) -> bool:
        return not self.reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "effective_date": self.effective_date.isoformat(),
            "calculation_version": self.calculation_version,
            "feature_names": list(self.feature_names),
            "ready": self.ready,
            "selected_listing_count": self.selected_listing_count,
            "effective_date_source_row_count": (
                self.effective_date_source_row_count
            ),
            "token": None if self.token is None else self.token.to_dict(),
            "rows": [row.to_dict() for row in self.rows],
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class _ActiveMembership:
    provider_listing_id: UUID
    publication_id: UUID
    action: str
    target_slot: str | None
    calculation_version: str
    source_coverage_start_date: date | None
    source_coverage_end_date: date | None
    source_row_count: int
    payload_row_count: int
    benchmark_provider_listing_id: UUID | None
    publication_status: str
    publication_calculation_version: str
    benchmark_required: bool
    publication_benchmark_provider_listing_id: UUID | None
    benchmark_contract_version: str | None


def select_published_feature_coverage(
    *,
    cursor: Any,
    scope: TechIndicatorsScope,
) -> tuple[PublishedFeatureCoverage, ...]:
    """Return ordered source and published-view coverage/freshness facts."""

    _validate_cursor(cursor)
    if not isinstance(scope, TechIndicatorsScope):
        raise TypeError("scope must be a TechIndicatorsScope.")
    listings = select_eligible_listings(cursor=cursor, scope=scope)
    if not listings:
        return ()
    identifiers = [item.provider_listing_id for item in listings]
    conditions = ["provider_listing_id = ANY(%s::uuid[])"]
    parameters: list[object] = [identifiers]
    if scope.start_date is not None and scope.end_date is not None:
        conditions.append("trading_date BETWEEN %s AND %s")
        parameters.extend((scope.start_date, scope.end_date))
    cursor.execute(
        f"""
        SELECT
            provider_listing_id,
            min(trading_date),
            max(trading_date),
            count(*),
            max(calculated_at),
            max(updated_at),
            array_agg(DISTINCT calculation_version ORDER BY calculation_version),
            array_agg(
                DISTINCT relative_strength_benchmark_provider_listing_id
                ORDER BY relative_strength_benchmark_provider_listing_id
            ) FILTER (
                WHERE relative_strength_benchmark_provider_listing_id IS NOT NULL
            )
        FROM stonks.ohlcv_daily_tech_indicators
        WHERE {' AND '.join(conditions)}
        GROUP BY provider_listing_id
        ORDER BY provider_listing_id
        """,
        tuple(parameters),
    )
    published = _coverage_rows(cursor.fetchall(), identifiers=set(identifiers))
    return tuple(
        _coverage_model(listing, published.get(listing.provider_listing_id))
        for listing in listings
    )


def select_published_feature_ranking(
    *,
    cursor: Any,
    scope: TechIndicatorsScope,
    trading_date: date,
    feature_name: str,
    descending: bool = True,
    limit: int = MAX_RANKING_ROWS,
) -> tuple[PublishedFeatureRankingRow, ...]:
    """Return one threshold-free feature ordering for a published date slice."""

    _validate_cursor(cursor)
    if not isinstance(scope, TechIndicatorsScope):
        raise TypeError("scope must be a TechIndicatorsScope.")
    if type(trading_date) is not date:
        raise TypeError("trading_date must be a date.")
    _validate_feature_names((feature_name,), ranking=True)
    if type(descending) is not bool:
        raise TypeError("descending must be a boolean.")
    _validate_limit("limit", limit, maximum=MAX_RANKING_ROWS)
    if scope.start_date is not None and (
        scope.start_date != trading_date or scope.end_date != trading_date
    ):
        raise ValueError("scope dates must equal the ranking trading date.")
    listings = select_eligible_listings(
        cursor=cursor,
        scope=_scope_for_date(scope, trading_date),
    )
    if not listings:
        return ()
    identifiers = [item.provider_listing_id for item in listings]
    direction = "DESC" if descending else "ASC"
    cursor.execute(
        f"""
        SELECT
            listing.provider_listing_id,
            listing.provider_code,
            listing.market,
            listing.ticker,
            feature.trading_date,
            feature.{feature_name}
        FROM stonks.ohlcv_daily_tech_indicators AS feature
        INNER JOIN stonks.provider_listing AS listing
            ON listing.provider_listing_id = feature.provider_listing_id
        WHERE feature.provider_listing_id = ANY(%s::uuid[])
          AND feature.trading_date = %s
        ORDER BY
            feature.{feature_name} {direction} NULLS LAST,
            listing.provider_code,
            listing.market,
            listing.ticker,
            listing.provider_listing_id
        LIMIT %s
        """,
        (identifiers, trading_date, limit),
    )
    return _ranking_rows(
        cursor.fetchall(),
        feature_name=feature_name,
        trading_date=trading_date,
        identifiers=set(identifiers),
    )


def select_published_feature_freshness(
    *,
    cursor: Any,
    scope: TechIndicatorsScope,
    as_of_date: date,
) -> tuple[PublishedFeatureFreshness, ...]:
    """Return raw published freshness facts without a stale threshold."""

    _validate_cursor(cursor)
    if not isinstance(scope, TechIndicatorsScope):
        raise TypeError("scope must be a TechIndicatorsScope.")
    if type(as_of_date) is not date:
        raise TypeError("as_of_date must be a date.")
    if scope.start_date is not None and not (
        scope.start_date <= as_of_date <= scope.end_date
    ):
        raise ValueError("as_of_date must be inside the scope date range.")
    listings = select_eligible_listings(
        cursor=cursor,
        scope=_scope_without_dates(scope),
    )
    if not listings:
        return ()
    identifiers = [item.provider_listing_id for item in listings]
    cursor.execute(
        """
        SELECT
            provider_listing_id,
            max(trading_date),
            max(calculated_at),
            max(updated_at),
            array_agg(DISTINCT calculation_version ORDER BY calculation_version),
            array_agg(
                DISTINCT relative_strength_benchmark_provider_listing_id
                ORDER BY relative_strength_benchmark_provider_listing_id
            ) FILTER (
                WHERE relative_strength_benchmark_provider_listing_id IS NOT NULL
            )
        FROM stonks.ohlcv_daily_tech_indicators
        WHERE provider_listing_id = ANY(%s::uuid[])
          AND trading_date <= %s
        GROUP BY provider_listing_id
        ORDER BY provider_listing_id
        """,
        (identifiers, as_of_date),
    )
    facts = _freshness_rows(cursor.fetchall(), identifiers=set(identifiers))
    return tuple(
        _freshness_model(
            listing,
            as_of_date=as_of_date,
            row=facts.get(listing.provider_listing_id),
        )
        for listing in listings
    )


def read_published_model_inputs(
    *,
    connection: Any,
    scope: TechIndicatorsScope,
    effective_date: date,
    calculation_version: str,
    benchmark_config: BenchmarkConfig,
    feature_names: tuple[str, ...],
    max_rows: int = MAX_MODEL_INPUT_ROWS,
) -> PublishedModelInputSnapshot:
    """Read readiness and model rows in one owned read-only MVCC snapshot.

    ``connection`` must be dedicated and idle. The package starts a
    ``REPEATABLE READ READ ONLY`` transaction and always rolls it back after
    constructing the immutable result; the readiness token is descriptive of
    that completed read and is not accepted by any later transaction.
    """

    _validate_connection(connection)
    if not isinstance(scope, TechIndicatorsScope):
        raise TypeError("scope must be a TechIndicatorsScope.")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a date.")
    _validate_calculation_version(calculation_version)
    if not isinstance(benchmark_config, BenchmarkConfig):
        raise TypeError("benchmark_config must be a BenchmarkConfig.")
    _validate_feature_names(feature_names, ranking=False)
    _validate_limit("max_rows", max_rows, maximum=MAX_MODEL_INPUT_ROWS)
    if scope.start_date is not None and (
        scope.start_date != effective_date or scope.end_date != effective_date
    ):
        raise ValueError("scope dates must equal the model effective date.")

    cursor = connection.cursor()
    try:
        cursor.execute(
            "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        )
        return _read_model_input_snapshot(
            cursor=cursor,
            scope=scope,
            effective_date=effective_date,
            calculation_version=calculation_version,
            benchmark_config=benchmark_config,
            feature_names=feature_names,
            max_rows=max_rows,
        )
    finally:
        try:
            connection.rollback()
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()


def _read_model_input_snapshot(
    *,
    cursor: Any,
    scope: TechIndicatorsScope,
    effective_date: date,
    calculation_version: str,
    benchmark_config: BenchmarkConfig,
    feature_names: tuple[str, ...],
    max_rows: int,
) -> PublishedModelInputSnapshot:
    selection_scope = _scope_without_dates(scope)
    listings = select_eligible_listings(cursor=cursor, scope=selection_scope)
    listing_by_id = {item.provider_listing_id: item for item in listings}
    identifiers = set(listing_by_id)
    reasons: set[str] = set()
    if not listings:
        reasons.add("SCOPE_MISMATCH")
        return _failed_snapshot(
            effective_date=effective_date,
            calculation_version=calculation_version,
            feature_names=feature_names,
            selected_listing_count=0,
            effective_date_source_row_count=0,
            reasons=reasons,
        )

    source_readiness = decide_source_readiness(
        cursor=cursor,
        scope=_scope_for_date(scope, effective_date),
        effective_date=effective_date,
        benchmark_config=benchmark_config,
    )
    reasons.update(_source_readiness_reasons(source_readiness.reasons))
    benchmark_id = source_readiness.benchmark_provider_listing_id
    source_ids = _effective_date_source_ids(
        cursor=cursor,
        identifiers=identifiers,
        effective_date=effective_date,
    )
    if len(source_ids) > max_rows:
        reasons.add("COVERAGE_INCOMPLETE")

    dependency_listings = _benchmark_dependency_listings(
        cursor=cursor,
        benchmark_id=benchmark_id,
        selected=listing_by_id,
    )
    dependency_by_id = {
        item.provider_listing_id: item for item in dependency_listings
    }
    dependency_ids = set(dependency_by_id)
    membership = _active_memberships(
        cursor=cursor,
        identifiers=dependency_ids,
    )
    _assess_memberships(
        listings=listings,
        source_ids=source_ids,
        memberships=membership,
        calculation_version=calculation_version,
        benchmark_id=benchmark_id,
        effective_date=effective_date,
        reasons=reasons,
    )
    _assess_benchmark_dependency(
        benchmark_id=benchmark_id,
        dependency_by_id=dependency_by_id,
        memberships=membership,
        calculation_version=calculation_version,
        reasons=reasons,
    )
    comparisons = tuple(
        item
        for page in iter_state_comparison_pages(
            cursor=cursor,
            scope=TechIndicatorsScope(
                provider_listing_ids=tuple(
                    sorted(dependency_ids, key=str)
                ),
                include_inactive=scope.include_inactive,
            ),
            calculation_version=calculation_version,
        )
        for item in page
    )
    comparison_ids = {item.provider_listing_id for item in comparisons}
    if not identifiers <= comparison_ids or not comparison_ids <= dependency_ids:
        reasons.add("SCOPE_MISMATCH")
    if benchmark_id is not None and benchmark_id not in comparison_ids:
        reasons.add("BENCHMARK_MISMATCH")
    for comparison in comparisons:
        if comparison.is_equivalent:
            continue
        reasons.add(
            "BENCHMARK_MISMATCH"
            if comparison.provider_listing_id == benchmark_id
            else "SOURCE_DRIFT"
        )

    if reasons:
        return _failed_snapshot(
            effective_date=effective_date,
            calculation_version=calculation_version,
            feature_names=feature_names,
            selected_listing_count=len(listings),
            effective_date_source_row_count=len(source_ids),
            reasons=reasons,
        )

    rows = _select_model_rows(
        cursor=cursor,
        listing_by_id=listing_by_id,
        effective_date=effective_date,
        calculation_version=calculation_version,
        benchmark_id=benchmark_id,
        feature_names=feature_names,
        max_rows=max_rows,
    )
    if {row.provider_listing_id for row in rows} != source_ids:
        reasons.add("COVERAGE_INCOMPLETE")
    if any(
        row.benchmark_provider_listing_id
        != (
            benchmark_id
            if is_spx_supported_subject(listing_by_id[row.provider_listing_id])
            else None
        )
        for row in rows
    ):
        reasons.add("BENCHMARK_MISMATCH")
    if reasons:
        return _failed_snapshot(
            effective_date=effective_date,
            calculation_version=calculation_version,
            feature_names=feature_names,
            selected_listing_count=len(listings),
            effective_date_source_row_count=len(source_ids),
            reasons=reasons,
        )

    token = _readiness_token(
        scope=scope,
        effective_date=effective_date,
        calculation_version=calculation_version,
        benchmark_id=benchmark_id,
        memberships=membership,
        listing_count=len(listings),
        model_row_count=len(rows),
    )
    return PublishedModelInputSnapshot(
        effective_date=effective_date,
        calculation_version=calculation_version,
        feature_names=feature_names,
        selected_listing_count=len(listings),
        effective_date_source_row_count=len(source_ids),
        token=token,
        rows=rows,
        reasons=(),
    )


def _coverage_rows(
    rows: object,
    *,
    identifiers: set[UUID],
) -> dict[UUID, tuple[object, ...]]:
    if not isinstance(rows, list):
        raise ValueError("Published coverage query returned invalid rows.")
    result: dict[UUID, tuple[object, ...]] = {}
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 8:
            raise ValueError("Published coverage query returned an invalid row.")
        provider_listing_id = row[0]
        if (
            not isinstance(provider_listing_id, UUID)
            or provider_listing_id not in identifiers
            or provider_listing_id in result
        ):
            raise ValueError("Published coverage query returned identity drift.")
        result[provider_listing_id] = tuple(row[1:])
    return result


def _coverage_model(
    listing: EligibleListing,
    row: tuple[object, ...] | None,
) -> PublishedFeatureCoverage:
    values = (None, None, 0, None, None, [], []) if row is None else row
    try:
        versions = tuple(values[5])
        benchmark_ids = tuple(values[6] or ())
        return PublishedFeatureCoverage(
            provider_listing_id=listing.provider_listing_id,
            provider_code=listing.provider_code,
            market=listing.market,
            ticker=listing.ticker,
            status=listing.status,
            source_first_trading_date=listing.first_trading_date,
            source_last_trading_date=listing.last_trading_date,
            source_row_count=listing.source_observation_count,
            published_first_trading_date=values[0],
            published_last_trading_date=values[1],
            published_row_count=values[2],
            latest_calculated_at=values[3],
            latest_updated_at=values[4],
            calculation_versions=versions,
            benchmark_provider_listing_ids=benchmark_ids,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Published coverage query returned invalid contract data."
        ) from exc


def _ranking_rows(
    rows: object,
    *,
    feature_name: str,
    trading_date: date,
    identifiers: set[UUID],
) -> tuple[PublishedFeatureRankingRow, ...]:
    if not isinstance(rows, list):
        raise ValueError("Published ranking query returned invalid rows.")
    result: list[PublishedFeatureRankingRow] = []
    seen: set[UUID] = set()
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 6:
            raise ValueError("Published ranking query returned an invalid row.")
        if (
            row[0] not in identifiers
            or row[0] in seen
            or row[4] != trading_date
        ):
            raise ValueError("Published ranking query returned identity drift.")
        try:
            result.append(
                PublishedFeatureRankingRow(
                    provider_listing_id=row[0],
                    provider_code=row[1],
                    market=row[2],
                    ticker=row[3],
                    trading_date=row[4],
                    feature_name=feature_name,
                    feature_value=row[5],
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Published ranking query returned invalid contract data."
            ) from exc
        seen.add(row[0])
    return tuple(result)


def _freshness_rows(
    rows: object,
    *,
    identifiers: set[UUID],
) -> dict[UUID, tuple[object, ...]]:
    if not isinstance(rows, list):
        raise ValueError("Published freshness query returned invalid rows.")
    result: dict[UUID, tuple[object, ...]] = {}
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 6:
            raise ValueError("Published freshness query returned an invalid row.")
        if row[0] not in identifiers or row[0] in result:
            raise ValueError("Published freshness query returned identity drift.")
        result[row[0]] = tuple(row[1:])
    return result


def _freshness_model(
    listing: EligibleListing,
    *,
    as_of_date: date,
    row: tuple[object, ...] | None,
) -> PublishedFeatureFreshness:
    values = (None, None, None, [], []) if row is None else row
    latest_date = values[0]
    try:
        return PublishedFeatureFreshness(
            provider_listing_id=listing.provider_listing_id,
            provider_code=listing.provider_code,
            market=listing.market,
            ticker=listing.ticker,
            as_of_date=as_of_date,
            latest_trading_date=latest_date,
            calendar_age_days=(
                None if latest_date is None else (as_of_date - latest_date).days
            ),
            latest_calculated_at=values[1],
            latest_updated_at=values[2],
            calculation_versions=tuple(values[3]),
            benchmark_provider_listing_ids=tuple(values[4] or ()),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Published freshness query returned invalid contract data."
        ) from exc


def _effective_date_source_ids(
    *,
    cursor: Any,
    identifiers: set[UUID],
    effective_date: date,
) -> set[UUID]:
    cursor.execute(
        """
        SELECT provider_listing_id
        FROM stonks.ohlcv_daily
        WHERE provider_listing_id = ANY(%s::uuid[])
          AND trading_date = %s
        ORDER BY provider_listing_id
        """,
        (sorted(identifiers, key=str), effective_date),
    )
    result: set[UUID] = set()
    for row in cursor.fetchall():
        if (
            not isinstance(row, (tuple, list))
            or len(row) != 1
            or row[0] not in identifiers
            or row[0] in result
        ):
            raise ValueError("Model source-date query returned identity drift.")
        result.add(row[0])
    return result


def _active_memberships(
    *,
    cursor: Any,
    identifiers: set[UUID],
) -> dict[UUID, _ActiveMembership]:
    cursor.execute(
        """
        SELECT
            membership.provider_listing_id,
            membership.publication_id,
            membership.action,
            membership.target_slot,
            membership.calculation_version,
            membership.source_coverage_start_date,
            membership.source_coverage_end_date,
            membership.source_row_count,
            membership.payload_row_count,
            membership.benchmark_provider_listing_id,
            publication.status,
            publication.calculation_version,
            publication.benchmark_required,
            publication.benchmark_provider_listing_id,
            publication.benchmark_contract_version
        FROM stonks.tech_indicators_publication_listing AS membership
        INNER JOIN stonks.tech_indicators_publication AS publication
            ON publication.publication_id = membership.publication_id
        WHERE membership.is_active
          AND membership.provider_listing_id = ANY(%s::uuid[])
        ORDER BY membership.provider_listing_id
        """,
        (sorted(identifiers, key=str),),
    )
    result: dict[UUID, _ActiveMembership] = {}
    for row in cursor.fetchall():
        if not isinstance(row, (tuple, list)) or len(row) != 15:
            raise ValueError("Active-membership query returned an invalid row.")
        if row[0] not in identifiers or row[0] in result:
            raise ValueError("Active-membership query returned identity drift.")
        try:
            membership = _ActiveMembership(*row)
        except TypeError as exc:
            raise ValueError(
                "Active-membership query returned invalid contract data."
            ) from exc
        result[membership.provider_listing_id] = membership
    return result


def _benchmark_dependency_listings(
    *,
    cursor: Any,
    benchmark_id: UUID | None,
    selected: dict[UUID, EligibleListing],
) -> tuple[EligibleListing, ...]:
    if benchmark_id is None or benchmark_id in selected:
        return tuple(selected.values())
    benchmark = select_eligible_listings(
        cursor=cursor,
        scope=TechIndicatorsScope(provider_listing_ids=(benchmark_id,)),
    )
    if len(benchmark) != 1 or benchmark[0].provider_listing_id != benchmark_id:
        return tuple(selected.values())
    return (*selected.values(), benchmark[0])


def _assess_memberships(
    *,
    listings: tuple[EligibleListing, ...],
    source_ids: set[UUID],
    memberships: dict[UUID, _ActiveMembership],
    calculation_version: str,
    benchmark_id: UUID | None,
    effective_date: date,
    reasons: set[str],
) -> None:
    expected_ids = {item.provider_listing_id for item in listings}
    if not expected_ids <= memberships.keys():
        reasons.add("NO_ACTIVE_PUBLICATION")
    for listing in listings:
        membership = memberships.get(listing.provider_listing_id)
        if membership is None:
            continue
        if (
            membership.action != "PRESENT"
            or membership.target_slot not in {"A", "B"}
            or membership.publication_status != "PUBLISHED"
        ):
            reasons.add("PUBLICATION_NOT_READY")
        if (
            membership.calculation_version != calculation_version
            or membership.publication_calculation_version
            != calculation_version
        ):
            reasons.add("VERSION_MISMATCH")
        if (
            membership.source_row_count != listing.source_observation_count
            or membership.payload_row_count != listing.source_observation_count
            or membership.source_coverage_start_date
            != listing.first_trading_date
            or membership.source_coverage_end_date != listing.last_trading_date
        ):
            reasons.add("COVERAGE_INCOMPLETE")
        if listing.provider_listing_id in source_ids and (
            membership.source_coverage_start_date is None
            or membership.source_coverage_end_date is None
            or not membership.source_coverage_start_date
            <= effective_date
            <= membership.source_coverage_end_date
        ):
            reasons.add("COVERAGE_INCOMPLETE")
        if is_spx_supported_subject(listing):
            if benchmark_id is None:
                reasons.add("BENCHMARK_UNAVAILABLE")
            if (
                membership.benchmark_provider_listing_id != benchmark_id
                or membership.publication_benchmark_provider_listing_id
                != benchmark_id
                or membership.benchmark_required is not True
                or membership.benchmark_contract_version
                != BENCHMARK_CONTRACT_VERSION
            ):
                reasons.add("BENCHMARK_MISMATCH")
        elif membership.benchmark_provider_listing_id is not None:
            reasons.add("BENCHMARK_MISMATCH")


def _assess_benchmark_dependency(
    *,
    benchmark_id: UUID | None,
    dependency_by_id: dict[UUID, EligibleListing],
    memberships: dict[UUID, _ActiveMembership],
    calculation_version: str,
    reasons: set[str],
) -> None:
    if benchmark_id is None:
        return
    benchmark = dependency_by_id.get(benchmark_id)
    membership = memberships.get(benchmark_id)
    if benchmark is None or membership is None:
        reasons.add("BENCHMARK_MISMATCH")
        return
    if (
        membership.action != "PRESENT"
        or membership.target_slot not in {"A", "B"}
        or membership.publication_status != "PUBLISHED"
        or membership.calculation_version != calculation_version
        or membership.publication_calculation_version != calculation_version
        or membership.source_row_count != benchmark.source_observation_count
        or membership.payload_row_count != benchmark.source_observation_count
        or membership.source_coverage_start_date != benchmark.first_trading_date
        or membership.source_coverage_end_date != benchmark.last_trading_date
        or membership.benchmark_provider_listing_id is not None
    ):
        reasons.add("BENCHMARK_MISMATCH")


def _select_model_rows(
    *,
    cursor: Any,
    listing_by_id: dict[UUID, EligibleListing],
    effective_date: date,
    calculation_version: str,
    benchmark_id: UUID | None,
    feature_names: tuple[str, ...],
    max_rows: int,
) -> tuple[PublishedModelInputRow, ...]:
    identifiers = sorted(listing_by_id, key=str)
    projection = ",\n            ".join(
        f"feature.{field_name}" for field_name in feature_names
    )
    cursor.execute(
        f"""
        SELECT
            feature.provider_listing_id,
            feature.trading_date,
            feature.calculation_version,
            feature.relative_strength_benchmark_provider_listing_id,
            {projection}
        FROM stonks.ohlcv_daily_tech_indicators AS feature
        WHERE feature.provider_listing_id = ANY(%s::uuid[])
          AND feature.trading_date = %s
          AND feature.calculation_version = %s
        ORDER BY feature.provider_listing_id
        LIMIT %s
        """,
        (identifiers, effective_date, calculation_version, max_rows + 1),
    )
    raw_rows = cursor.fetchall()
    if len(raw_rows) > max_rows:
        return ()
    result: list[PublishedModelInputRow] = []
    seen: set[UUID] = set()
    for row in raw_rows:
        if not isinstance(row, (tuple, list)) or len(row) != 4 + len(feature_names):
            raise ValueError("Model-input query returned an invalid row.")
        provider_listing_id = row[0]
        listing = listing_by_id.get(provider_listing_id)
        if (
            listing is None
            or provider_listing_id in seen
            or row[1] != effective_date
            or row[2] != calculation_version
        ):
            raise ValueError("Model-input query returned identity drift.")
        try:
            result.append(
                PublishedModelInputRow(
                    provider_listing_id=provider_listing_id,
                    provider_code=listing.provider_code,
                    market=listing.market,
                    ticker=listing.ticker,
                    trading_date=row[1],
                    calculation_version=row[2],
                    benchmark_provider_listing_id=row[3],
                    values=tuple(zip(feature_names, row[4:], strict=True)),
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Model-input query returned invalid contract data."
            ) from exc
        seen.add(provider_listing_id)
    return tuple(result)


def _readiness_token(
    *,
    scope: TechIndicatorsScope,
    effective_date: date,
    calculation_version: str,
    benchmark_id: UUID | None,
    memberships: dict[UUID, _ActiveMembership],
    listing_count: int,
    model_row_count: int,
) -> PublishedReadinessToken:
    token_facts = {
        "scope": scope.to_dict(),
        "effective_date": effective_date.isoformat(),
        "calculation_version": calculation_version,
        "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
        "benchmark_provider_listing_id": _uuid_string(benchmark_id),
        "memberships": [
            [
                str(item.provider_listing_id),
                str(item.publication_id),
                item.target_slot,
            ]
            for item in sorted(
                memberships.values(),
                key=lambda value: str(value.provider_listing_id),
            )
        ],
    }
    value = hashlib.sha256(
        json.dumps(
            token_facts,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return PublishedReadinessToken(
        value=value,
        effective_date=effective_date,
        calculation_version=calculation_version,
        benchmark_provider_listing_id=benchmark_id,
        listing_count=listing_count,
        model_row_count=model_row_count,
    )


def _failed_snapshot(
    *,
    effective_date: date,
    calculation_version: str,
    feature_names: tuple[str, ...],
    selected_listing_count: int,
    effective_date_source_row_count: int,
    reasons: set[str],
) -> PublishedModelInputSnapshot:
    return PublishedModelInputSnapshot(
        effective_date=effective_date,
        calculation_version=calculation_version,
        feature_names=feature_names,
        selected_listing_count=selected_listing_count,
        effective_date_source_row_count=effective_date_source_row_count,
        token=None,
        rows=(),
        reasons=tuple(
            reason for reason in _READINESS_REASON_ORDER if reason in reasons
        ),
    )


def _source_readiness_reasons(reasons: tuple[str, ...]) -> set[str]:
    result: set[str] = set()
    for reason in reasons:
        if reason == "NO_ELIGIBLE_LISTINGS":
            result.add("SCOPE_MISMATCH")
        elif reason == "BENCHMARK_UNAVAILABLE":
            result.add("BENCHMARK_UNAVAILABLE")
        elif reason == "SPX_COVERAGE_INCOMPLETE":
            result.add("SPX_COVERAGE_INCOMPLETE")
        else:
            result.add("SOURCE_DRIFT")
    return result


def _scope_without_dates(scope: TechIndicatorsScope) -> TechIndicatorsScope:
    return TechIndicatorsScope(
        provider_codes=scope.provider_codes,
        markets=scope.markets,
        provider_listing_ids=scope.provider_listing_ids,
        include_inactive=scope.include_inactive,
    )


def _scope_for_date(
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


def _validate_feature_names(
    values: tuple[str, ...],
    *,
    ranking: bool,
) -> None:
    if not isinstance(values, tuple):
        raise TypeError("feature names must be a tuple.")
    if not values:
        raise ValueError("feature names must not be empty.")
    allowed = _RANKING_FIELD_SET if ranking else _MODEL_INPUT_FIELD_SET
    if any(not isinstance(value, str) for value in values):
        raise TypeError("feature names must contain strings.")
    if any(value not in allowed for value in values):
        raise ValueError("feature names must use the published V1 allowlist.")
    if len(values) != len(set(values)):
        raise ValueError("feature names must be unique.")


def _validate_identity(value: object) -> None:
    if not isinstance(getattr(value, "provider_listing_id", None), UUID):
        raise TypeError("provider_listing_id must be a UUID.")
    for field_name in ("provider_code", "market", "ticker"):
        field_value = getattr(value, field_name, None)
        if not isinstance(field_value, str):
            raise TypeError(f"{field_name} must be a string.")
        if not field_value or field_value != field_value.strip():
            raise ValueError(f"{field_name} must be non-empty and trimmed.")
    status = getattr(value, "status", None)
    if status is not None and status not in {"ACTIVE", "INACTIVE"}:
        raise ValueError("status must be ACTIVE or INACTIVE.")


def _validate_coverage(
    *,
    prefix: str,
    first_date: object,
    last_date: object,
    row_count: object,
) -> None:
    _validate_nonnegative_int(f"{prefix}_row_count", row_count)
    for field_name, value in (
        (f"{prefix}_first_trading_date", first_date),
        (f"{prefix}_last_trading_date", last_date),
    ):
        if value is not None and type(value) is not date:
            raise TypeError(f"{field_name} must be a date or None.")
    if (first_date is None or last_date is None) != (row_count == 0):
        raise ValueError(f"{prefix} dates must be null exactly for zero rows.")
    if first_date is not None and last_date is not None and first_date > last_date:
        raise ValueError(f"{prefix} first date must not follow its last date.")


def _validate_feature_value(
    value: object,
    *,
    allow_decimal: bool = False,
) -> None:
    allowed_types = (float, int, Decimal) if allow_decimal else (float, int)
    if value is None:
        return
    if type(value) not in allowed_types:
        raise TypeError("feature values must be numeric or None.")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("feature values must be finite.")
    elif not math.isfinite(float(value)):
        raise ValueError("feature values must be finite.")


def _validate_calculation_version(value: object) -> None:
    if not isinstance(value, str):
        raise TypeError("calculation_version must be a string.")
    if value != value.strip() or _CALCULATION_VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("calculation_version must use the database contract.")


def _validate_reasons(values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError("reasons must be a tuple.")
    expected = tuple(
        reason for reason in _READINESS_REASON_ORDER if reason in values
    )
    if values != expected or len(values) != len(set(values)):
        raise ValueError("reasons must be unique and contract ordered.")


def _validate_sorted_text_tuple(field_name: str, values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) or not value for value in values
    ):
        raise TypeError(f"{field_name} must contain non-empty strings.")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must be unique and sorted.")


def _validate_sorted_uuid_tuple(field_name: str, values: tuple[UUID, ...]) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(value, UUID) for value in values
    ):
        raise TypeError(f"{field_name} must contain UUID values.")
    if values != tuple(sorted(set(values), key=str)):
        raise ValueError(f"{field_name} must be unique and sorted.")


def _validate_optional_uuid(field_name: str, value: object) -> None:
    if value is not None and not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID or None.")


def _validate_optional_aware_datetime(field_name: str, value: object) -> None:
    if value is None:
        return
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None.")
    if value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _validate_nonnegative_int(field_name: str, value: object) -> None:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")


def _validate_limit(field_name: str, value: object, *, maximum: int) -> None:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    if not 1 <= value <= maximum:
        raise ValueError(f"{field_name} must be between 1 and {maximum}.")


def _validate_cursor(cursor: Any) -> None:
    if not callable(getattr(cursor, "execute", None)) or not callable(
        getattr(cursor, "fetchall", None)
    ):
        raise TypeError("cursor must provide execute and fetchall methods.")


def _validate_connection(connection: Any) -> None:
    if not callable(getattr(connection, "cursor", None)) or not callable(
        getattr(connection, "rollback", None)
    ):
        raise TypeError("connection must provide cursor and rollback methods.")


def _date_string(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _datetime_string(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _uuid_string(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def _json_value(value: Decimal | float | int | None) -> str | float | int | None:
    return str(value) if isinstance(value, Decimal) else value


__all__ = [
    "BENCHMARK_CONTRACT_VERSION",
    "GENERATED_FEATURE_FIELDS",
    "MAX_MODEL_INPUT_ROWS",
    "MAX_RANKING_ROWS",
    "PUBLISHED_MODEL_INPUT_FIELDS",
    "PUBLISHED_RANKING_FIELDS",
    "PublishedFeatureCoverage",
    "PublishedFeatureFreshness",
    "PublishedFeatureRankingRow",
    "PublishedModelInputRow",
    "PublishedModelInputSnapshot",
    "PublishedReadinessToken",
    "read_published_model_inputs",
    "select_published_feature_coverage",
    "select_published_feature_freshness",
    "select_published_feature_ranking",
]
