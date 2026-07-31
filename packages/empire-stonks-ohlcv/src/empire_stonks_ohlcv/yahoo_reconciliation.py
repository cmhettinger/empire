"""Recent-session reconciliation planning and Yahoo correction diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from empire_stonks_ohlcv.config import MAX_YAHOO_RECONCILIATION_SESSIONS
from empire_stonks_ohlcv.daily_bars import (
    DailyBarComparison,
    DailyBarComparisonStatus,
)
from empire_stonks_ohlcv.market_sessions import MarketSessionService
from empire_stonks_ohlcv.yahoo import (
    YahooAcquisitionRequest,
    YahooListingTarget,
    YahooRequestMode,
)
from empire_stonks_ohlcv.yahoo_completeness import (
    YahooCompletenessStatus,
    YahooDailyCompletenessPlan,
    YahooDailyPull,
    YahooPlanningFailureReason,
    YahooPullReason,
    plan_yahoo_daily_completeness,
)
from empire_stonks_ohlcv.yahoo_parser import YahooChartParseResult


@dataclass(frozen=True)
class YahooAdjustedCloseComparison:
    """Current response adjusted close compared with its native close."""

    trading_date: date
    native_close: Decimal
    adjusted_close: Decimal | None

    def __post_init__(self) -> None:
        if type(self.trading_date) is not date:
            raise TypeError("trading_date must be a date.")
        if (
            not isinstance(self.native_close, Decimal)
            or not self.native_close.is_finite()
        ):
            raise ValueError("native_close must be a finite Decimal.")
        if self.adjusted_close is not None and (
            not isinstance(self.adjusted_close, Decimal)
            or not self.adjusted_close.is_finite()
        ):
            raise ValueError("adjusted_close must be finite or None.")

    @property
    def difference_from_native(self) -> Decimal | None:
        if self.adjusted_close is None:
            return None
        return self.adjusted_close - self.native_close

    def to_dict(self) -> dict[str, str | None]:
        return {
            "trading_date": self.trading_date.isoformat(),
            "native_close": str(self.native_close),
            "adjusted_close": (
                None if self.adjusted_close is None else str(self.adjusted_close)
            ),
            "difference_from_native": (
                None
                if self.difference_from_native is None
                else str(self.difference_from_native)
            ),
        }


@dataclass(frozen=True)
class YahooReconciliationSummary:
    """Pre-upsert corrections and native adjustment semantics for one pull."""

    comparisons: tuple[DailyBarComparison, ...]
    adjusted_close_present: bool
    adjusted_close_comparisons: tuple[YahooAdjustedCloseComparison, ...]
    invalid_adjusted_close_rows: int

    def __post_init__(self) -> None:
        if not isinstance(self.comparisons, tuple) or any(
            not isinstance(item, DailyBarComparison)
            for item in self.comparisons
        ):
            raise TypeError("comparisons must contain DailyBarComparison values.")
        if not isinstance(self.adjusted_close_present, bool):
            raise TypeError("adjusted_close_present must be a boolean.")
        if not isinstance(self.adjusted_close_comparisons, tuple) or any(
            not isinstance(item, YahooAdjustedCloseComparison)
            for item in self.adjusted_close_comparisons
        ):
            raise TypeError(
                "adjusted_close_comparisons contains an invalid value."
            )
        _nonnegative_integer(
            "invalid_adjusted_close_rows",
            self.invalid_adjusted_close_rows,
        )
        dates = tuple(item.trading_date for item in self.comparisons)
        _ordered_dates(dates)
        adjusted_dates = tuple(
            item.trading_date for item in self.adjusted_close_comparisons
        )
        _ordered_dates(adjusted_dates)
        if self.adjusted_close_present:
            if adjusted_dates != dates:
                raise ValueError(
                    "Adjusted-close comparisons must align with parsed bars."
                )
        elif self.adjusted_close_comparisons or self.invalid_adjusted_close_rows:
            raise ValueError(
                "Adjusted-close details require an adjusted-close array."
            )

    @property
    def inserted_bar_count(self) -> int:
        return sum(
            item.status is DailyBarComparisonStatus.INSERTED
            for item in self.comparisons
        )

    @property
    def corrected_bar_count(self) -> int:
        return sum(
            item.status is DailyBarComparisonStatus.CORRECTED
            for item in self.comparisons
        )

    @property
    def unchanged_bar_count(self) -> int:
        return sum(
            item.status is DailyBarComparisonStatus.UNCHANGED
            for item in self.comparisons
        )

    @property
    def field_difference_counts(self) -> dict[str, int]:
        counts = {item: 0 for item in ("open", "high", "low", "close", "volume")}
        for comparison in self.comparisons:
            for difference in comparison.differences:
                counts[difference.field_name] += 1
        return counts

    def to_dict(self) -> dict[str, object]:
        return {
            "input_bar_count": len(self.comparisons),
            "inserted_bar_count": self.inserted_bar_count,
            "corrected_bar_count": self.corrected_bar_count,
            "unchanged_bar_count": self.unchanged_bar_count,
            "field_difference_counts": self.field_difference_counts,
            "comparisons": [item.to_dict() for item in self.comparisons],
            "native_close_persisted": True,
            "adjusted_close_present": self.adjusted_close_present,
            "adjusted_close_persisted": False,
            "adjusted_close_comparisons": [
                item.to_dict() for item in self.adjusted_close_comparisons
            ],
            "invalid_adjusted_close_rows": self.invalid_adjusted_close_rows,
        }


def build_yahoo_reconciliation_summary(
    *,
    parse_result: YahooChartParseResult,
    comparisons: tuple[DailyBarComparison, ...],
) -> YahooReconciliationSummary:
    """Combine normalized stored-value differences with parse diagnostics."""

    if not isinstance(parse_result, YahooChartParseResult):
        raise TypeError("parse_result must be a YahooChartParseResult.")
    if not isinstance(comparisons, tuple) or any(
        not isinstance(item, DailyBarComparison) for item in comparisons
    ):
        raise TypeError("comparisons must contain DailyBarComparison values.")
    bars = parse_result.batch.bars
    expected_identity = tuple(
        (
            parse_result.request.listing.provider_listing_id,
            item.trading_date,
        )
        for item in bars
    )
    comparison_identity = tuple(
        (item.provider_listing_id, item.trading_date) for item in comparisons
    )
    if comparison_identity != expected_identity:
        raise ValueError("comparisons must align with parsed Yahoo bars.")
    bars_by_date = {item.trading_date: item for item in bars}
    adjusted = (
        tuple(
            YahooAdjustedCloseComparison(
                trading_date=item.trading_date,
                native_close=bars_by_date[item.trading_date].close,
                adjusted_close=item.adjusted_close,
            )
            for item in parse_result.adjusted_closes
        )
        if parse_result.adjusted_close_present
        else ()
    )
    return YahooReconciliationSummary(
        comparisons=comparisons,
        adjusted_close_present=parse_result.adjusted_close_present,
        adjusted_close_comparisons=adjusted,
        invalid_adjusted_close_rows=parse_result.invalid_adjusted_close_rows,
    )


@dataclass(frozen=True)
class YahooListingReconciliationPlan:
    """Recent provider dates selected for one active Yahoo listing."""

    listing: YahooListingTarget
    policy_code: str
    status: YahooCompletenessStatus
    selected_dates: tuple[date, ...]
    pulls: tuple[YahooDailyPull, ...]
    observed_only: bool
    failure_reason: YahooPlanningFailureReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.listing, YahooListingTarget):
            raise TypeError("listing must be a YahooListingTarget.")
        if not isinstance(self.policy_code, str) or not self.policy_code:
            raise ValueError("policy_code is required.")
        if not isinstance(self.status, YahooCompletenessStatus):
            raise TypeError("status must be a YahooCompletenessStatus.")
        _ordered_dates(self.selected_dates)
        if not isinstance(self.pulls, tuple) or any(
            not isinstance(item, YahooDailyPull) for item in self.pulls
        ):
            raise TypeError("pulls must contain YahooDailyPull values.")
        if not isinstance(self.observed_only, bool):
            raise TypeError("observed_only must be a boolean.")
        if any(
            item.request.listing != self.listing
            or item.reason is not YahooPullReason.RECENT_RECONCILIATION
            for item in self.pulls
        ):
            raise ValueError("Reconciliation pulls must match the listing.")
        pull_dates = tuple(
            item for pull in self.pulls for item in pull.planned_dates
        )
        if pull_dates != self.selected_dates:
            raise ValueError("Pulls must cover every selected date exactly once.")
        if self.status is YahooCompletenessStatus.FAILED:
            if self.failure_reason is None or self.selected_dates or self.pulls:
                raise ValueError("FAILED requires a reason and forbids work.")
        elif self.failure_reason is not None:
            raise ValueError("PLANNED forbids failure_reason.")

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "provider_listing_id": str(self.listing.provider_listing_id),
            "ticker": self.listing.ticker,
            "policy_code": self.policy_code,
            "status": self.status.value,
            "observed_only": self.observed_only,
            "selected_dates": [item.isoformat() for item in self.selected_dates],
            "pulls": [item.to_safe_dict() for item in self.pulls],
            "failure_reason": (
                None
                if self.failure_reason is None
                else self.failure_reason.value
            ),
        }


@dataclass(frozen=True)
class YahooReconciliationPlan:
    """Bounded recent-session plan for the selected Yahoo universe."""

    completeness_plan: YahooDailyCompletenessPlan
    session_count: int
    listings: tuple[YahooListingReconciliationPlan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.completeness_plan, YahooDailyCompletenessPlan):
            raise TypeError("completeness_plan must be a YahooDailyCompletenessPlan.")
        _session_count(self.session_count)
        if not isinstance(self.listings, tuple) or any(
            not isinstance(item, YahooListingReconciliationPlan)
            for item in self.listings
        ):
            raise TypeError(
                "listings must contain YahooListingReconciliationPlan values."
            )
        if tuple(item.listing for item in self.listings) != tuple(
            item.listing for item in self.completeness_plan.listings
        ):
            raise ValueError("Reconciliation listings must match completeness.")

    @property
    def pulls(self) -> tuple[YahooDailyPull, ...]:
        return tuple(pull for item in self.listings for pull in item.pulls)

    @property
    def requests(self) -> tuple[YahooAcquisitionRequest, ...]:
        return tuple(item.request for item in self.pulls)

    @property
    def failed_listing_count(self) -> int:
        return sum(
            item.status is YahooCompletenessStatus.FAILED
            for item in self.listings
        )

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "start_date": self.completeness_plan.start_date.isoformat(),
            "end_date": self.completeness_plan.end_date.isoformat(),
            "planned_at": self.completeness_plan.planned_at.isoformat(),
            "session_count": self.session_count,
            "listing_count": len(self.listings),
            "failed_listing_count": self.failed_listing_count,
            "pull_count": len(self.pulls),
            "listings": [item.to_safe_dict() for item in self.listings],
        }


def plan_yahoo_recent_reconciliation(
    *,
    cursor: Any,
    start_date: date,
    end_date: date,
    now: datetime,
    session_count: int,
    max_request_days: int,
    tickers: tuple[str, ...] = (),
    session_service: MarketSessionService | None = None,
) -> YahooReconciliationPlan:
    """Read bounded completeness state and select the latest sessions."""

    completeness = plan_yahoo_daily_completeness(
        cursor=cursor,
        start_date=start_date,
        end_date=end_date,
        now=now,
        max_request_days=max_request_days,
        tickers=tickers,
        session_service=session_service,
    )
    return build_yahoo_recent_reconciliation_plan(
        completeness_plan=completeness,
        session_count=session_count,
        max_request_days=max_request_days,
    )


def build_yahoo_recent_reconciliation_plan(
    *,
    completeness_plan: YahooDailyCompletenessPlan,
    session_count: int,
    max_request_days: int,
) -> YahooReconciliationPlan:
    """Select recent authoritative sessions or observed provider dates."""

    if not isinstance(completeness_plan, YahooDailyCompletenessPlan):
        raise TypeError("completeness_plan must be a YahooDailyCompletenessPlan.")
    _session_count(session_count)
    _positive_integer("max_request_days", max_request_days)
    results: list[YahooListingReconciliationPlan] = []
    for item in completeness_plan.listings:
        if item.status is YahooCompletenessStatus.FAILED:
            results.append(
                YahooListingReconciliationPlan(
                    listing=item.listing,
                    policy_code=item.policy_code,
                    status=item.status,
                    selected_dates=(),
                    pulls=(),
                    observed_only=item.observed_only,
                    failure_reason=item.failure_reason,
                )
            )
            continue

        observed_only = item.observed_only
        if observed_only:
            selected = list(item.stored_session_dates[-session_count:])
            if item.observed_poll_candidates:
                selected.append(item.observed_poll_candidates[-1].candidate_date)
            selected_dates = tuple(sorted(set(selected)))
        else:
            selected_dates = tuple(
                session.session_date
                for session in item.eligible_sessions[-session_count:]
            )
        results.append(
            YahooListingReconciliationPlan(
                listing=item.listing,
                policy_code=item.policy_code,
                status=YahooCompletenessStatus.PLANNED,
                selected_dates=selected_dates,
                pulls=_reconciliation_pulls(
                    listing=item.listing,
                    selected_dates=selected_dates,
                    max_request_days=max_request_days,
                ),
                observed_only=observed_only,
            )
        )
    return YahooReconciliationPlan(
        completeness_plan=completeness_plan,
        session_count=session_count,
        listings=tuple(results),
    )


def _reconciliation_pulls(
    *,
    listing: YahooListingTarget,
    selected_dates: tuple[date, ...],
    max_request_days: int,
) -> tuple[YahooDailyPull, ...]:
    if not selected_dates:
        return ()
    groups: list[list[date]] = []
    current: list[date] = []
    for item in selected_dates:
        if current and (
            item + timedelta(days=1) - current[0]
        ).days > max_request_days:
            groups.append(current)
            current = []
        current.append(item)
    groups.append(current)
    return tuple(
        YahooDailyPull(
            request=YahooAcquisitionRequest(
                listing=listing,
                start_date=group[0],
                end_date_exclusive=group[-1] + timedelta(days=1),
                mode=YahooRequestMode.DAILY,
            ),
            reason=YahooPullReason.RECENT_RECONCILIATION,
            planned_dates=tuple(group),
        )
        for group in groups
    )


def _ordered_dates(values: object) -> None:
    if not isinstance(values, tuple) or any(type(item) is not date for item in values):
        raise TypeError("selected_dates must contain date values.")
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError("selected_dates must be unique and ordered.")


def _positive_integer(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")


def _session_count(value: object) -> None:
    _positive_integer("session_count", value)
    assert isinstance(value, int)
    if value > MAX_YAHOO_RECONCILIATION_SESSIONS:
        raise ValueError(
            "session_count exceeds the configured reconciliation safety bound."
        )


def _nonnegative_integer(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
