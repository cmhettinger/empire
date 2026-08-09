"""Read-only source versus published technical-indicator state comparison."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from empire_stonks_tech_indicators.config import (
    DEFAULT_SOURCE_READ_PAGE_SIZE,
    MAX_SOURCE_READ_PAGE_SIZE,
    MIN_SOURCE_READ_PAGE_SIZE,
)
from empire_stonks_tech_indicators.models import TechIndicatorsScope
from empire_stonks_tech_indicators.queries import select_eligible_listings


_CALCULATION_VERSION_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


@dataclass(frozen=True)
class ListingStateComparison:
    """Bounded current-source versus published-state facts for one listing."""

    provider_listing_id: UUID
    provider_code: str
    market: str
    ticker: str
    first_source_date: date | None
    last_source_date: date | None
    source_observation_count: int
    last_technical_date: date | None
    tail_append_count: int
    missing_tech_row_count: int
    source_copy_drift_count: int
    history_count_drift_count: int
    version_drift_count: int
    earliest_tail_append_date: date | None
    earliest_missing_tech_date: date | None
    earliest_source_copy_drift_date: date | None
    earliest_history_count_drift_date: date | None
    earliest_version_drift_date: date | None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_listing_id, UUID):
            raise TypeError("provider_listing_id must be a UUID.")
        for field_name in ("provider_code", "market", "ticker"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string.")
            if not value or value != value.strip():
                raise ValueError(f"{field_name} must be non-empty and trimmed.")
        for field_name in (
            "first_source_date",
            "last_source_date",
            "last_technical_date",
            "earliest_tail_append_date",
            "earliest_missing_tech_date",
            "earliest_source_copy_drift_date",
            "earliest_history_count_drift_date",
            "earliest_version_drift_date",
        ):
            value = getattr(self, field_name)
            if value is not None and type(value) is not date:
                raise TypeError(f"{field_name} must be a date or None.")
        count_fields = (
            "source_observation_count",
            "tail_append_count",
            "missing_tech_row_count",
            "source_copy_drift_count",
            "history_count_drift_count",
            "version_drift_count",
        )
        for field_name in count_fields:
            value = getattr(self, field_name)
            if type(value) is not int:
                raise TypeError(f"{field_name} must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative.")

        empty_source = (
            self.first_source_date is None and self.last_source_date is None
        )
        if empty_source != (self.source_observation_count == 0):
            raise ValueError(
                "source dates must both be null exactly when source count is zero."
            )
        if (
            self.first_source_date is not None
            and self.last_source_date is not None
            and self.first_source_date > self.last_source_date
        ):
            raise ValueError("first_source_date must not be after last_source_date.")
        if self.source_observation_count == 0 and (
            self.last_technical_date is not None
            or any(getattr(self, field_name) for field_name in count_fields[1:])
        ):
            raise ValueError("empty source state cannot contain technical drift.")
        if (
            self.last_technical_date is not None
            and self.last_source_date is not None
            and self.last_technical_date > self.last_source_date
        ):
            raise ValueError("last_technical_date must not be after source history.")

        for count_name, date_name in (
            ("tail_append_count", "earliest_tail_append_date"),
            ("missing_tech_row_count", "earliest_missing_tech_date"),
            ("source_copy_drift_count", "earliest_source_copy_drift_date"),
            ("history_count_drift_count", "earliest_history_count_drift_date"),
            ("version_drift_count", "earliest_version_drift_date"),
        ):
            if (getattr(self, count_name) == 0) != (getattr(self, date_name) is None):
                raise ValueError(
                    f"{date_name} must be populated exactly when "
                    f"{count_name} is positive."
                )
            reason_date = getattr(self, date_name)
            if (
                reason_date is not None
                and self.first_source_date is not None
                and self.last_source_date is not None
                and not self.first_source_date <= reason_date <= self.last_source_date
            ):
                raise ValueError(f"{date_name} must be within source history.")

    @property
    def missing_row_count(self) -> int:
        return self.tail_append_count + self.missing_tech_row_count

    @property
    def earliest_recalculation_date(self) -> date | None:
        """Return P0.7's earliest listing-local uncertainty for this state."""

        if self.version_drift_count:
            return self.first_source_date
        candidates = (
            self.earliest_tail_append_date,
            self.earliest_missing_tech_date,
            self.earliest_source_copy_drift_date,
            self.earliest_history_count_drift_date,
        )
        populated = tuple(value for value in candidates if value is not None)
        return min(populated) if populated else None

    @property
    def reasons(self) -> tuple[str, ...]:
        names = (
            ("TAIL_APPEND", self.tail_append_count),
            ("MISSING_TECH_ROW", self.missing_tech_row_count),
            ("SOURCE_COPY_DRIFT", self.source_copy_drift_count),
            ("HISTORY_COUNT_DRIFT", self.history_count_drift_count),
            ("VERSION_DRIFT", self.version_drift_count),
        )
        return tuple(name for name, count in names if count)

    @property
    def is_equivalent(self) -> bool:
        return not self.reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "provider_code": self.provider_code,
            "market": self.market,
            "ticker": self.ticker,
            "first_source_date": _date_to_string(self.first_source_date),
            "last_source_date": _date_to_string(self.last_source_date),
            "source_observation_count": self.source_observation_count,
            "last_technical_date": _date_to_string(self.last_technical_date),
            "tail_append_count": self.tail_append_count,
            "missing_tech_row_count": self.missing_tech_row_count,
            "missing_row_count": self.missing_row_count,
            "source_copy_drift_count": self.source_copy_drift_count,
            "history_count_drift_count": self.history_count_drift_count,
            "version_drift_count": self.version_drift_count,
            "earliest_tail_append_date": _date_to_string(
                self.earliest_tail_append_date
            ),
            "earliest_missing_tech_date": _date_to_string(
                self.earliest_missing_tech_date
            ),
            "earliest_source_copy_drift_date": _date_to_string(
                self.earliest_source_copy_drift_date
            ),
            "earliest_history_count_drift_date": _date_to_string(
                self.earliest_history_count_drift_date
            ),
            "earliest_version_drift_date": _date_to_string(
                self.earliest_version_drift_date
            ),
            "earliest_recalculation_date": _date_to_string(
                self.earliest_recalculation_date
            ),
            "reasons": list(self.reasons),
            "is_equivalent": self.is_equivalent,
        }


def iter_state_comparison_pages(
    *,
    cursor: Any,
    scope: TechIndicatorsScope,
    calculation_version: str,
    page_size: int = DEFAULT_SOURCE_READ_PAGE_SIZE,
) -> Iterator[tuple[ListingStateComparison, ...]]:
    """Yield set-based source/published-state comparisons in bounded pages.

    The query reads the atomic published view, uses exact null-safe copied-value
    comparisons, and derives chronological counts from the full source prefix.
    Optional scope dates bound only comparison rows; they never reset history
    counts. The caller owns the cursor, transaction, and snapshot.
    """

    _validate_paged_cursor(cursor)
    if not isinstance(scope, TechIndicatorsScope):
        raise TypeError("scope must be a TechIndicatorsScope.")
    _validate_calculation_version(calculation_version)
    _validate_page_size(page_size)

    listings = select_eligible_listings(cursor=cursor, scope=scope)
    if not listings:
        return
    listing_ids = [item.provider_listing_id for item in listings]
    listing_identity = {
        item.provider_listing_id: (item.provider_code, item.market, item.ticker)
        for item in listings
    }
    date_condition = ""
    parameters: list[object] = [listing_ids, calculation_version]
    if scope.start_date is not None and scope.end_date is not None:
        date_condition = "WHERE source_state.trading_date BETWEEN %s AND %s"
        parameters.extend((scope.start_date, scope.end_date))

    cursor.execute(
        _state_comparison_sql(date_condition),
        tuple(parameters),
    )
    previous: tuple[str, str, str, UUID] | None = None
    while True:
        rows = cursor.fetchmany(page_size)
        if len(rows) > page_size:
            raise ValueError("State-comparison query returned more than one page.")
        if not rows:
            return
        comparisons: list[ListingStateComparison] = []
        for row in rows:
            comparison = _listing_state_comparison(row)
            identity = (
                comparison.provider_code,
                comparison.market,
                comparison.ticker,
                comparison.provider_listing_id,
            )
            if listing_identity.get(comparison.provider_listing_id) != identity[:3]:
                raise ValueError("State-comparison query returned identity drift.")
            if previous is not None and identity <= previous:
                raise ValueError("State-comparison query returned unordered rows.")
            comparisons.append(comparison)
            previous = identity
        yield tuple(comparisons)


def _state_comparison_sql(date_condition: str) -> str:
    return f"""
        WITH eligible_listing AS (
            SELECT
                listing.provider_listing_id,
                listing.provider_code,
                listing.market,
                listing.ticker
            FROM stonks.provider_listing AS listing
            WHERE listing.provider_listing_id = ANY(%s::uuid[])
        ),
        source_ranked AS (
            SELECT
                eligible.provider_listing_id,
                daily.trading_date,
                daily.open,
                daily.high,
                daily.low,
                daily.close,
                daily.volume,
                row_number() OVER (
                    PARTITION BY daily.provider_listing_id
                    ORDER BY daily.trading_date
                ) AS history_observation_count
            FROM eligible_listing AS eligible
            INNER JOIN stonks.ohlcv_daily AS daily
                ON daily.provider_listing_id = eligible.provider_listing_id
        ),
        source_coverage AS (
            SELECT
                source_state.provider_listing_id,
                min(source_state.trading_date) AS first_source_date,
                max(source_state.trading_date) AS last_source_date,
                count(*) AS source_observation_count
            FROM source_ranked AS source_state
            GROUP BY source_state.provider_listing_id
        ),
        technical_tail AS (
            SELECT
                technical.provider_listing_id,
                max(technical.trading_date) AS last_technical_date
            FROM stonks.ohlcv_daily_tech_indicators AS technical
            INNER JOIN eligible_listing AS eligible
                ON eligible.provider_listing_id = technical.provider_listing_id
            GROUP BY technical.provider_listing_id
        ),
        compared AS (
            SELECT
                source_state.provider_listing_id,
                source_state.trading_date,
                technical.provider_listing_id IS NULL AS is_missing,
                technical.provider_listing_id IS NULL
                    AND (
                        technical_tail.last_technical_date IS NULL
                        OR source_state.trading_date
                            > technical_tail.last_technical_date
                    ) AS is_tail_append,
                technical.provider_listing_id IS NOT NULL
                    AND ROW(
                        technical.open,
                        technical.high,
                        technical.low,
                        technical.close,
                        technical.volume
                    ) IS DISTINCT FROM ROW(
                        source_state.open,
                        source_state.high,
                        source_state.low,
                        source_state.close,
                        source_state.volume
                    ) AS has_source_copy_drift,
                technical.provider_listing_id IS NOT NULL
                    AND technical.history_observation_count
                        IS DISTINCT FROM source_state.history_observation_count
                    AS has_history_count_drift,
                technical.provider_listing_id IS NOT NULL
                    AND technical.calculation_version IS DISTINCT FROM %s
                    AS has_version_drift
            FROM source_ranked AS source_state
            LEFT JOIN stonks.ohlcv_daily_tech_indicators AS technical
                ON technical.provider_listing_id
                    = source_state.provider_listing_id
               AND technical.trading_date = source_state.trading_date
            LEFT JOIN technical_tail
                ON technical_tail.provider_listing_id
                    = source_state.provider_listing_id
            {date_condition}
        ),
        comparison_summary AS (
            SELECT
                compared.provider_listing_id,
                count(*) FILTER (
                    WHERE compared.is_missing AND compared.is_tail_append
                ) AS tail_append_count,
                count(*) FILTER (
                    WHERE compared.is_missing AND NOT compared.is_tail_append
                ) AS missing_tech_row_count,
                count(*) FILTER (
                    WHERE compared.has_source_copy_drift
                ) AS source_copy_drift_count,
                count(*) FILTER (
                    WHERE compared.has_history_count_drift
                ) AS history_count_drift_count,
                count(*) FILTER (
                    WHERE compared.has_version_drift
                ) AS version_drift_count,
                min(compared.trading_date) FILTER (
                    WHERE compared.is_missing AND compared.is_tail_append
                ) AS earliest_tail_append_date,
                min(compared.trading_date) FILTER (
                    WHERE compared.is_missing AND NOT compared.is_tail_append
                ) AS earliest_missing_tech_date,
                min(compared.trading_date) FILTER (
                    WHERE compared.has_source_copy_drift
                ) AS earliest_source_copy_drift_date,
                min(compared.trading_date) FILTER (
                    WHERE compared.has_history_count_drift
                ) AS earliest_history_count_drift_date,
                min(compared.trading_date) FILTER (
                    WHERE compared.has_version_drift
                ) AS earliest_version_drift_date
            FROM compared
            GROUP BY compared.provider_listing_id
        )
        SELECT
            eligible.provider_listing_id,
            eligible.provider_code,
            eligible.market,
            eligible.ticker,
            source_coverage.first_source_date,
            source_coverage.last_source_date,
            coalesce(source_coverage.source_observation_count, 0),
            technical_tail.last_technical_date,
            coalesce(comparison.tail_append_count, 0),
            coalesce(comparison.missing_tech_row_count, 0),
            coalesce(comparison.source_copy_drift_count, 0),
            coalesce(comparison.history_count_drift_count, 0),
            coalesce(comparison.version_drift_count, 0),
            comparison.earliest_tail_append_date,
            comparison.earliest_missing_tech_date,
            comparison.earliest_source_copy_drift_date,
            comparison.earliest_history_count_drift_date,
            comparison.earliest_version_drift_date
        FROM eligible_listing AS eligible
        LEFT JOIN source_coverage
            ON source_coverage.provider_listing_id
                = eligible.provider_listing_id
        LEFT JOIN technical_tail
            ON technical_tail.provider_listing_id
                = eligible.provider_listing_id
        LEFT JOIN comparison_summary AS comparison
            ON comparison.provider_listing_id = eligible.provider_listing_id
        ORDER BY
            eligible.provider_code,
            eligible.market,
            eligible.ticker,
            eligible.provider_listing_id
    """


def _listing_state_comparison(row: object) -> ListingStateComparison:
    if not isinstance(row, (tuple, list)) or len(row) != 18:
        raise ValueError("State-comparison query returned an invalid row.")
    try:
        return ListingStateComparison(*row)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "State-comparison query returned invalid contract data."
        ) from exc


def _validate_paged_cursor(cursor: Any) -> None:
    if not callable(getattr(cursor, "execute", None)) or not callable(
        getattr(cursor, "fetchall", None)
    ):
        raise TypeError("cursor must provide execute and fetchall methods.")
    if not callable(getattr(cursor, "fetchmany", None)):
        raise TypeError("cursor must provide a fetchmany method for paged reads.")


def _validate_calculation_version(value: object) -> None:
    if not isinstance(value, str):
        raise TypeError("calculation_version must be a string.")
    if not _CALCULATION_VERSION_PATTERN.fullmatch(value):
        raise ValueError("calculation_version must be an uppercase identifier.")


def _validate_page_size(page_size: object) -> None:
    if type(page_size) is not int:
        raise TypeError("page_size must be an integer.")
    if not MIN_SOURCE_READ_PAGE_SIZE <= page_size <= MAX_SOURCE_READ_PAGE_SIZE:
        raise ValueError(
            "page_size must be between "
            f"{MIN_SOURCE_READ_PAGE_SIZE} and {MAX_SOURCE_READ_PAGE_SIZE}."
        )


def _date_to_string(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


__all__ = [
    "ListingStateComparison",
    "iter_state_comparison_pages",
]
