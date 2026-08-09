"""Immutable base records for Empire stonks technical indicators."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from math import isfinite
from uuid import UUID

from empire_stonks_tech_indicators.config import (
    DEFAULT_BENCHMARK_INSTRUMENT_TYPE_CODE,
    DEFAULT_BENCHMARK_MARKET,
    DEFAULT_BENCHMARK_PROVIDER_CODE,
    DEFAULT_BENCHMARK_TICKER,
    DEFAULT_BENCHMARK_YAHOO_TICKER,
    DEFAULT_CALCULATION_VERSION,
    MAX_DIAGNOSTIC_SAMPLE_LIMIT,
)


_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_FIELD_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_ISSUE_MESSAGE_LENGTH = 500
_SPX_FEATURE_FIELDS = (
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
)
_NULLABLE_FLOAT_FEATURE_FIELDS = (
    "return_1d_pct",
    "return_2d_pct",
    "return_3d_pct",
    "return_5d_pct",
    "return_10d_pct",
    "return_20d_pct",
    "return_63d_pct",
    "return_126d_pct",
    "return_252d_pct",
    "gap_1d_pct",
    "sma_20",
    "sma_50",
    "sma_200",
    "ema_12",
    "ema_20",
    "ema_26",
    "ema_50",
    "sma_50_change_20d_pct",
    "sma_200_change_20d_pct",
    "hh_20",
    "hh_50",
    "hh_252",
    "ll_20",
    "ll_50",
    "rsi_14",
    "atr_14",
    "return_volatility_20d_pct",
    "return_volatility_60d_pct",
    "return_1d_zscore_20d",
    "return_3d_zscore_20d",
    "price_stddev_20",
    "plus_di_14",
    "minus_di_14",
    "adx_14",
    "macd_12_26",
    "macd_signal_12_26_9",
    "macd_histogram_12_26_9",
    "volume_avg_20",
    "volume_avg_60",
    "dollar_volume_avg_20",
    *_SPX_FEATURE_FIELDS,
)
PYTHON_FEATURE_FIELDS = (
    *_NULLABLE_FLOAT_FEATURE_FIELDS[:40],
    "consecutive_up_days",
    "consecutive_down_days",
    *_SPX_FEATURE_FIELDS,
)


def _validate_uuid(field_name: str, value: object, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, UUID):
        suffix = " or None" if nullable else ""
        raise TypeError(f"{field_name} must be a UUID{suffix}.")


def _validate_date(field_name: str, value: object, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if type(value) is not date:
        suffix = " or None" if nullable else ""
        raise TypeError(f"{field_name} must be a date{suffix}.")


def _validate_nonnegative_int(field_name: str, value: object) -> None:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")


def _validate_positive_int(field_name: str, value: object) -> None:
    _validate_nonnegative_int(field_name, value)
    if value == 0:
        raise ValueError(f"{field_name} must be positive.")


def _validate_required_text(
    field_name: str,
    value: object,
    *,
    maximum_length: int = 64,
) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty and trimmed.")
    if len(value) > maximum_length:
        raise ValueError(
            f"{field_name} must be at most {maximum_length} characters."
        )
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{field_name} must not contain control characters.")


def _validate_code(field_name: str, value: object) -> None:
    _validate_required_text(field_name, value)
    if not _CODE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be an uppercase identifier.")


def _validate_decimal(field_name: str, value: object) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal.")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite.")


def _validate_nullable_float(field_name: str, value: object) -> None:
    if value is None:
        return
    if type(value) is not float:
        raise TypeError(f"{field_name} must be a float or None.")
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite when populated.")


def _validate_calculation_version(value: object) -> None:
    _validate_code("calculation_version", value)
    if value != DEFAULT_CALCULATION_VERSION:
        raise ValueError(
            f"calculation_version must be {DEFAULT_CALCULATION_VERSION}."
        )


@dataclass(frozen=True)
class SourceBar:
    """One exact provider-listing source observation used for calculation."""

    provider_listing_id: UUID
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None

    def __post_init__(self) -> None:
        _validate_uuid("provider_listing_id", self.provider_listing_id)
        _validate_date("trading_date", self.trading_date)
        for field_name in ("open", "high", "low", "close"):
            _validate_decimal(field_name, getattr(self, field_name))
        if self.volume is not None:
            _validate_decimal("volume", self.volume)
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low.")
        if self.high < self.open or self.high < self.close:
            raise ValueError("high must be greater than or equal to open and close.")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be less than or equal to open and close.")
        if self.volume is not None and self.volume < 0:
            raise ValueError("volume must be non-negative.")

    def to_dict(self) -> dict[str, str | None]:
        """Return exact JSON-ready source values without Decimal precision loss."""

        return {
            "provider_listing_id": str(self.provider_listing_id),
            "trading_date": self.trading_date.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": None if self.volume is None else str(self.volume),
        }


@dataclass(frozen=True)
class FeatureRow:
    """One complete package-owned feature-row write payload."""

    source: SourceBar
    history_observation_count: int
    calculation_version: str
    calculated_at: datetime
    relative_strength_benchmark_provider_listing_id: UUID | None = None
    run_id: UUID | None = None
    return_1d_pct: float | None = None
    return_2d_pct: float | None = None
    return_3d_pct: float | None = None
    return_5d_pct: float | None = None
    return_10d_pct: float | None = None
    return_20d_pct: float | None = None
    return_63d_pct: float | None = None
    return_126d_pct: float | None = None
    return_252d_pct: float | None = None
    gap_1d_pct: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_12: float | None = None
    ema_20: float | None = None
    ema_26: float | None = None
    ema_50: float | None = None
    sma_50_change_20d_pct: float | None = None
    sma_200_change_20d_pct: float | None = None
    hh_20: float | None = None
    hh_50: float | None = None
    hh_252: float | None = None
    ll_20: float | None = None
    ll_50: float | None = None
    rsi_14: float | None = None
    atr_14: float | None = None
    return_volatility_20d_pct: float | None = None
    return_volatility_60d_pct: float | None = None
    return_1d_zscore_20d: float | None = None
    return_3d_zscore_20d: float | None = None
    price_stddev_20: float | None = None
    plus_di_14: float | None = None
    minus_di_14: float | None = None
    adx_14: float | None = None
    macd_12_26: float | None = None
    macd_signal_12_26_9: float | None = None
    macd_histogram_12_26_9: float | None = None
    volume_avg_20: float | None = None
    volume_avg_60: float | None = None
    dollar_volume_avg_20: float | None = None
    consecutive_up_days: int = 0
    consecutive_down_days: int = 0
    rel_spx: float | None = None
    pct_rel_spx_20: float | None = None
    pct_rel_spx_50: float | None = None
    relative_return_spx_20d_pct: float | None = None
    relative_return_spx_63d_pct: float | None = None
    relative_return_spx_126d_pct: float | None = None
    relative_return_spx_252d_pct: float | None = None
    spx_beta_60d: float | None = None
    spx_beta_252d: float | None = None
    spx_correlation_60d: float | None = None
    spx_correlation_252d: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceBar):
            raise TypeError("source must be a SourceBar.")
        _validate_positive_int(
            "history_observation_count",
            self.history_observation_count,
        )
        _validate_calculation_version(self.calculation_version)
        if not isinstance(self.calculated_at, datetime):
            raise TypeError("calculated_at must be a datetime.")
        if self.calculated_at.utcoffset() is None:
            raise ValueError("calculated_at must be timezone-aware.")
        _validate_uuid(
            "relative_strength_benchmark_provider_listing_id",
            self.relative_strength_benchmark_provider_listing_id,
            nullable=True,
        )
        _validate_uuid("run_id", self.run_id, nullable=True)
        for field_name in _NULLABLE_FLOAT_FEATURE_FIELDS:
            _validate_nullable_float(field_name, getattr(self, field_name))
        _validate_nonnegative_int("consecutive_up_days", self.consecutive_up_days)
        _validate_nonnegative_int(
            "consecutive_down_days",
            self.consecutive_down_days,
        )
        if (
            self.relative_strength_benchmark_provider_listing_id is None
            and any(getattr(self, name) is not None for name in _SPX_FEATURE_FIELDS)
        ):
            raise ValueError(
                "SPX feature values require a resolved benchmark listing ID."
            )

    def to_dict(self) -> dict[str, object]:
        """Return the fixed 65-column package write payload as JSON-ready data."""

        result: dict[str, object] = {
            **self.source.to_dict(),
            "relative_strength_benchmark_provider_listing_id": (
                None
                if self.relative_strength_benchmark_provider_listing_id is None
                else str(self.relative_strength_benchmark_provider_listing_id)
            ),
            "history_observation_count": self.history_observation_count,
            "calculation_version": self.calculation_version,
            "run_id": None if self.run_id is None else str(self.run_id),
            "calculated_at": self.calculated_at.isoformat(),
        }
        result.update(
            {
                field_name: getattr(self, field_name)
                for field_name in PYTHON_FEATURE_FIELDS
            }
        )
        return result


def _normalize_text_tuple(
    field_name: str,
    value: object,
    *,
    uppercase: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple.")
    for item in value:
        _validate_required_text(field_name, item)
        if uppercase and item != item.upper():
            raise ValueError(f"{field_name} values must be uppercase.")
    return tuple(sorted(set(value)))


def _normalize_uuid_tuple(field_name: str, value: object) -> tuple[UUID, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple.")
    for item in value:
        _validate_uuid(field_name, item)
    return tuple(sorted(set(value), key=str))


@dataclass(frozen=True)
class TechIndicatorsScope:
    """Provider/listing/date selection shared by later workflow scopes."""

    provider_codes: tuple[str, ...] = ()
    markets: tuple[str, ...] = ()
    provider_listing_ids: tuple[UUID, ...] = ()
    start_date: date | None = None
    end_date: date | None = None
    include_inactive: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_codes",
            _normalize_text_tuple(
                "provider_codes",
                self.provider_codes,
                uppercase=True,
            ),
        )
        object.__setattr__(
            self,
            "markets",
            _normalize_text_tuple("markets", self.markets),
        )
        object.__setattr__(
            self,
            "provider_listing_ids",
            _normalize_uuid_tuple(
                "provider_listing_ids",
                self.provider_listing_ids,
            ),
        )
        _validate_date("start_date", self.start_date, nullable=True)
        _validate_date("end_date", self.end_date, nullable=True)
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("start_date and end_date must be provided together.")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not be after end_date.")
        if type(self.include_inactive) is not bool:
            raise TypeError("include_inactive must be a bool.")
        if self.include_inactive and (
            not self.provider_listing_ids or self.provider_codes or self.markets
        ):
            raise ValueError(
                "include_inactive requires an explicit listing-only scope."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_codes": list(self.provider_codes),
            "markets": list(self.markets),
            "provider_listing_ids": [
                str(identifier) for identifier in self.provider_listing_ids
            ],
            "start_date": (
                None if self.start_date is None else self.start_date.isoformat()
            ),
            "end_date": None if self.end_date is None else self.end_date.isoformat(),
            "include_inactive": self.include_inactive,
        }


@dataclass(frozen=True)
class ResolvedBenchmark:
    """One database-resolved benchmark with all frozen identity facts."""

    provider_listing_id: UUID
    provider_code: str = DEFAULT_BENCHMARK_PROVIDER_CODE
    market: str = DEFAULT_BENCHMARK_MARKET
    ticker: str = DEFAULT_BENCHMARK_TICKER
    instrument_type_code: str = DEFAULT_BENCHMARK_INSTRUMENT_TYPE_CODE
    status: str = "ACTIVE"
    yahoo_ticker: str = DEFAULT_BENCHMARK_YAHOO_TICKER

    def __post_init__(self) -> None:
        _validate_uuid("provider_listing_id", self.provider_listing_id)
        expected = {
            "provider_code": DEFAULT_BENCHMARK_PROVIDER_CODE,
            "market": DEFAULT_BENCHMARK_MARKET,
            "ticker": DEFAULT_BENCHMARK_TICKER,
            "instrument_type_code": DEFAULT_BENCHMARK_INSTRUMENT_TYPE_CODE,
            "status": "ACTIVE",
            "yahoo_ticker": DEFAULT_BENCHMARK_YAHOO_TICKER,
        }
        for field_name, expected_value in expected.items():
            if getattr(self, field_name) != expected_value:
                raise ValueError(f"{field_name} must be {expected_value}.")

    def to_dict(self) -> dict[str, str]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "provider_code": self.provider_code,
            "market": self.market,
            "ticker": self.ticker,
            "instrument_type_code": self.instrument_type_code,
            "status": self.status,
            "yahoo_ticker": self.yahoo_ticker,
        }


@dataclass(frozen=True)
class TechIndicatorsIssue:
    """One bounded secret-safe calculation warning or failure sample."""

    code: str
    severity: str
    message: str
    provider_listing_id: UUID | None = None
    trading_date: date | None = None
    field_name: str | None = None

    def __post_init__(self) -> None:
        _validate_code("code", self.code)
        if self.severity not in {"WARNING", "ERROR"}:
            raise ValueError("severity must be WARNING or ERROR.")
        _validate_required_text(
            "message",
            self.message,
            maximum_length=_MAX_ISSUE_MESSAGE_LENGTH,
        )
        _validate_uuid(
            "provider_listing_id",
            self.provider_listing_id,
            nullable=True,
        )
        _validate_date("trading_date", self.trading_date, nullable=True)
        if self.field_name is not None:
            _validate_required_text("field_name", self.field_name)
            if not _FIELD_NAME_PATTERN.fullmatch(self.field_name):
                raise ValueError("field_name must be a lowercase identifier.")

    def to_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "provider_listing_id": (
                None
                if self.provider_listing_id is None
                else str(self.provider_listing_id)
            ),
            "trading_date": (
                None if self.trading_date is None else self.trading_date.isoformat()
            ),
            "field_name": self.field_name,
        }


@dataclass(frozen=True)
class ReasonCount:
    """One deterministic planning, exclusion, null, or outcome reason count."""

    code: str
    count: int

    def __post_init__(self) -> None:
        _validate_code("code", self.code)
        _validate_nonnegative_int("count", self.count)

    def to_dict(self) -> dict[str, str | int]:
        return {"code": self.code, "count": self.count}


@dataclass(frozen=True)
class FeatureCounts:
    """Bounded aggregate feature-work and persistence counts."""

    selected_listings: int = 0
    excluded_listings: int = 0
    evaluated_rows: int = 0
    inserted_rows: int = 0
    updated_rows: int = 0
    unchanged_rows: int = 0
    deleted_rows: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "selected_listings",
            "excluded_listings",
            "evaluated_rows",
            "inserted_rows",
            "updated_rows",
            "unchanged_rows",
            "deleted_rows",
        ):
            _validate_nonnegative_int(field_name, getattr(self, field_name))
        if self.compared_rows > self.evaluated_rows:
            raise ValueError(
                "inserted, updated, and unchanged rows cannot exceed evaluated rows."
            )

    @property
    def compared_rows(self) -> int:
        return self.inserted_rows + self.updated_rows + self.unchanged_rows

    @property
    def changed_rows(self) -> int:
        return self.inserted_rows + self.updated_rows + self.deleted_rows

    def to_dict(self) -> dict[str, int]:
        return {
            "selected_listings": self.selected_listings,
            "excluded_listings": self.excluded_listings,
            "evaluated_rows": self.evaluated_rows,
            "inserted_rows": self.inserted_rows,
            "updated_rows": self.updated_rows,
            "unchanged_rows": self.unchanged_rows,
            "deleted_rows": self.deleted_rows,
            "compared_rows": self.compared_rows,
            "changed_rows": self.changed_rows,
        }


@dataclass(frozen=True)
class TechIndicatorsSummary:
    """Compact aggregate outcome with bounded issue samples."""

    counts: FeatureCounts = field(default_factory=FeatureCounts)
    reason_counts: tuple[ReasonCount, ...] = ()
    total_issue_count: int = 0
    issues: tuple[TechIndicatorsIssue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.counts, FeatureCounts):
            raise TypeError("counts must be FeatureCounts.")
        if not isinstance(self.reason_counts, tuple) or any(
            not isinstance(item, ReasonCount) for item in self.reason_counts
        ):
            raise TypeError("reason_counts must contain only ReasonCount records.")
        reason_codes = [item.code for item in self.reason_counts]
        if len(reason_codes) != len(set(reason_codes)):
            raise ValueError("reason_counts codes must be unique.")
        object.__setattr__(
            self,
            "reason_counts",
            tuple(sorted(self.reason_counts, key=lambda item: item.code)),
        )
        _validate_nonnegative_int("total_issue_count", self.total_issue_count)
        if not isinstance(self.issues, tuple) or any(
            not isinstance(item, TechIndicatorsIssue) for item in self.issues
        ):
            raise TypeError("issues must contain only TechIndicatorsIssue records.")
        if len(self.issues) > MAX_DIAGNOSTIC_SAMPLE_LIMIT:
            raise ValueError(
                "issues cannot exceed the 100-sample diagnostic hard limit."
            )
        if len(self.issues) > self.total_issue_count:
            raise ValueError("issue samples cannot exceed total_issue_count.")

    @property
    def issue_sample_count(self) -> int:
        return len(self.issues)

    @property
    def issues_truncated(self) -> bool:
        return self.issue_sample_count < self.total_issue_count

    def to_dict(self) -> dict[str, object]:
        return {
            "counts": self.counts.to_dict(),
            "reason_counts": [item.to_dict() for item in self.reason_counts],
            "total_issue_count": self.total_issue_count,
            "issue_sample_count": self.issue_sample_count,
            "issues_truncated": self.issues_truncated,
            "issues": [item.to_dict() for item in self.issues],
        }


@dataclass(frozen=True)
class TechIndicatorsRunResult:
    """Compact JSON-ready result shared by later daily and backfill runners."""

    run_id: UUID
    status: str
    calculation_version: str
    scope: TechIndicatorsScope
    summary: TechIndicatorsSummary
    benchmark: ResolvedBenchmark | None = None

    def __post_init__(self) -> None:
        _validate_uuid("run_id", self.run_id)
        if self.status not in {"succeeded", "failed"}:
            raise ValueError("status must be succeeded or failed.")
        _validate_calculation_version(self.calculation_version)
        if not isinstance(self.scope, TechIndicatorsScope):
            raise TypeError("scope must be a TechIndicatorsScope.")
        if not isinstance(self.summary, TechIndicatorsSummary):
            raise TypeError("summary must be a TechIndicatorsSummary.")
        if self.benchmark is not None and not isinstance(
            self.benchmark,
            ResolvedBenchmark,
        ):
            raise TypeError("benchmark must be a ResolvedBenchmark or None.")

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": str(self.run_id),
            "status": self.status,
            "calculation_version": self.calculation_version,
            "scope": self.scope.to_dict(),
            "benchmark": (
                None if self.benchmark is None else self.benchmark.to_dict()
            ),
            "summary": self.summary.to_dict(),
        }


__all__ = [
    "FeatureCounts",
    "FeatureRow",
    "ReasonCount",
    "ResolvedBenchmark",
    "SourceBar",
    "TechIndicatorsIssue",
    "TechIndicatorsRunResult",
    "TechIndicatorsScope",
    "TechIndicatorsSummary",
]
