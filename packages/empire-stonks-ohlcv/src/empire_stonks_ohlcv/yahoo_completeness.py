"""Bounded Yahoo daily completeness planning."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from empire_stonks_ohlcv.exceptions import (
    OHLCVCalendarError,
    OHLCVConfigError,
)
from empire_stonks_ohlcv.market_sessions import (
    ExpectedSession,
    MarketSessionService,
    ObservedPollCandidate,
    SessionPolicy,
)
from empire_stonks_ohlcv.yahoo import (
    YahooAcquisitionRequest,
    YahooListingTarget,
    YahooRequestMode,
)
from empire_stonks_ohlcv.yahoo_listings import (
    SeededYahooListing,
    select_active_yahoo_listings,
)


class YahooCompletenessStatus(StrEnum):
    """Safe result of planning one active Yahoo listing."""

    PLANNED = "planned"
    FAILED = "failed"


class YahooPullReason(StrEnum):
    """Why one bounded Yahoo daily pull belongs in the plan."""

    ELIGIBLE_MISSING_SESSION = "eligible_missing_session"
    DUE_OBSERVED_POLL = "due_observed_poll"


class YahooPlanningFailureReason(StrEnum):
    """Stable, secret-safe per-listing planning failure reasons."""

    CALENDAR_POLICY = "calendar_policy"


@dataclass(frozen=True)
class YahooDailyPull:
    """One source-bounded request and the exact dates that justify it."""

    request: YahooAcquisitionRequest
    reason: YahooPullReason
    planned_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.request, YahooAcquisitionRequest):
            raise TypeError("request must be a YahooAcquisitionRequest.")
        if self.request.mode is not YahooRequestMode.DAILY:
            raise ValueError("Yahoo completeness pulls must use DAILY mode.")
        if not isinstance(self.reason, YahooPullReason):
            raise TypeError("reason must be a YahooPullReason.")
        dates = _validated_dates("planned_dates", self.planned_dates)
        if not dates:
            raise ValueError("planned_dates must not be empty.")
        if any(
            not self.request.start_date
            <= item
            < self.request.end_date_exclusive
            for item in dates
        ):
            raise ValueError("planned_dates must be inside the request range.")
        if (
            self.request.start_date != dates[0]
            or self.request.end_date_exclusive != dates[-1] + timedelta(days=1)
        ):
            raise ValueError("The request must be tightly bounded to planned_dates.")

    def to_safe_dict(self) -> dict[str, object]:
        """Return request identity and dates without provider URL details."""

        return {
            "ticker": self.request.listing.ticker,
            "reason": self.reason.value,
            "start_date": self.request.start_date.isoformat(),
            "end_date_exclusive": (
                self.request.end_date_exclusive.isoformat()
            ),
            "planned_dates": [item.isoformat() for item in self.planned_dates],
        }


@dataclass(frozen=True)
class YahooListingCompletenessPlan:
    """Completeness decision for one active seeded Yahoo listing."""

    listing: YahooListingTarget
    policy_code: str
    status: YahooCompletenessStatus
    stored_session_dates: tuple[date, ...]
    expected_sessions: tuple[ExpectedSession, ...] = ()
    eligible_sessions: tuple[ExpectedSession, ...] = ()
    missing_sessions: tuple[ExpectedSession, ...] = ()
    observed_poll_candidates: tuple[ObservedPollCandidate, ...] = ()
    pulls: tuple[YahooDailyPull, ...] = ()
    failure_reason: YahooPlanningFailureReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.listing, YahooListingTarget):
            raise TypeError("listing must be a YahooListingTarget.")
        _required_text("policy_code", self.policy_code)
        if not isinstance(self.status, YahooCompletenessStatus):
            raise TypeError("status must be a YahooCompletenessStatus.")
        _validated_dates("stored_session_dates", self.stored_session_dates)
        _validated_values(
            "expected_sessions",
            self.expected_sessions,
            ExpectedSession,
        )
        _validated_values(
            "eligible_sessions",
            self.eligible_sessions,
            ExpectedSession,
        )
        _validated_values(
            "missing_sessions",
            self.missing_sessions,
            ExpectedSession,
        )
        _validated_values(
            "observed_poll_candidates",
            self.observed_poll_candidates,
            ObservedPollCandidate,
        )
        _validated_values("pulls", self.pulls, YahooDailyPull)
        if self.failure_reason is not None and not isinstance(
            self.failure_reason,
            YahooPlanningFailureReason,
        ):
            raise TypeError(
                "failure_reason must be a YahooPlanningFailureReason or None."
            )
        if any(item.request.listing != self.listing for item in self.pulls):
            raise ValueError("Every pull must target this listing.")
        expected_dates = _session_dates(self.expected_sessions)
        eligible_dates = _session_dates(self.eligible_sessions)
        missing_dates = _session_dates(self.missing_sessions)
        observed_dates = tuple(
            item.candidate_date for item in self.observed_poll_candidates
        )
        if not set(eligible_dates) <= set(expected_dates):
            raise ValueError("eligible_sessions must be expected sessions.")
        if not set(missing_dates) <= set(eligible_dates):
            raise ValueError("missing_sessions must be eligible sessions.")
        if expected_dates and observed_dates:
            raise ValueError(
                "Authoritative sessions and observed candidates cannot mix."
            )
        planned_dates = tuple(
            item for pull in self.pulls for item in pull.planned_dates
        )
        justified_dates = missing_dates or observed_dates
        if planned_dates != justified_dates:
            raise ValueError("Pull dates must exactly match planned work dates.")
        if self.status is YahooCompletenessStatus.FAILED:
            if (
                self.failure_reason is None
                or self.expected_sessions
                or self.eligible_sessions
                or self.missing_sessions
                or self.observed_poll_candidates
                or self.pulls
            ):
                raise ValueError(
                    "FAILED requires a reason and forbids planned work."
                )
        elif self.failure_reason is not None:
            raise ValueError("PLANNED forbids failure_reason.")

    @property
    def ineligible_session_count(self) -> int:
        """Return expected sessions whose publication time has not passed."""

        return len(self.expected_sessions) - len(self.eligible_sessions)

    def to_safe_dict(self) -> dict[str, object]:
        """Return bounded planning counts and acquisition ranges."""

        return {
            "provider_listing_id": str(self.listing.provider_listing_id),
            "ticker": self.listing.ticker,
            "policy_code": self.policy_code,
            "status": self.status.value,
            "stored_session_count": len(self.stored_session_dates),
            "expected_session_count": len(self.expected_sessions),
            "eligible_session_count": len(self.eligible_sessions),
            "ineligible_session_count": self.ineligible_session_count,
            "missing_session_count": len(self.missing_sessions),
            "observed_poll_candidate_count": len(
                self.observed_poll_candidates
            ),
            "pulls": [item.to_safe_dict() for item in self.pulls],
            "failure_reason": (
                None
                if self.failure_reason is None
                else self.failure_reason.value
            ),
        }


@dataclass(frozen=True)
class YahooDailyCompletenessPlan:
    """Deterministic bounded plan across active Yahoo listings."""

    start_date: date
    end_date: date
    planned_at: datetime
    enumerated_listing_count: int
    listings: tuple[YahooListingCompletenessPlan, ...]

    def __post_init__(self) -> None:
        _date_range(self.start_date, self.end_date)
        object.__setattr__(self, "planned_at", _aware_utc(self.planned_at))
        _validated_values(
            "listings",
            self.listings,
            YahooListingCompletenessPlan,
        )
        if (
            isinstance(self.enumerated_listing_count, bool)
            or not isinstance(self.enumerated_listing_count, int)
            or self.enumerated_listing_count < len(self.listings)
        ):
            raise ValueError(
                "enumerated_listing_count must cover selected listings."
            )
        tickers = tuple(item.listing.ticker for item in self.listings)
        if tickers != tuple(sorted(tickers)) or len(tickers) != len(
            set(tickers)
        ):
            raise ValueError("listings must have unique ordered tickers.")

    @property
    def pulls(self) -> tuple[YahooDailyPull, ...]:
        """Return all per-listing pulls in deterministic order."""

        return tuple(pull for item in self.listings for pull in item.pulls)

    @property
    def requests(self) -> tuple[YahooAcquisitionRequest, ...]:
        """Return the acquisition requests consumed by the later daily runner."""

        return tuple(item.request for item in self.pulls)

    @property
    def failed_listing_count(self) -> int:
        return sum(
            item.status is YahooCompletenessStatus.FAILED
            for item in self.listings
        )

    def to_safe_dict(self) -> dict[str, object]:
        """Return a machine-readable plan without provider request URLs."""

        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "planned_at": self.planned_at.isoformat(),
            "enumerated_listing_count": self.enumerated_listing_count,
            "selected_listing_count": len(self.listings),
            "failed_listing_count": self.failed_listing_count,
            "pull_count": len(self.pulls),
            "listings": [item.to_safe_dict() for item in self.listings],
        }


def plan_yahoo_daily_completeness(
    *,
    cursor: Any,
    start_date: date,
    end_date: date,
    now: datetime,
    max_request_days: int,
    tickers: tuple[str, ...] = (),
    session_service: MarketSessionService | None = None,
) -> YahooDailyCompletenessPlan:
    """Read active seeds and stored bars, then build a bounded daily plan."""

    _date_range(start_date, end_date)
    current = _aware_utc(now)
    _positive_integer("max_request_days", max_request_days)
    selected_tickers = _validated_tickers(tickers)
    enumerated = select_active_yahoo_listings(cursor=cursor)
    selected = _select_listings(enumerated, selected_tickers)
    stored = select_yahoo_stored_session_dates(
        cursor=cursor,
        provider_listing_ids=tuple(
            item.target.provider_listing_id for item in selected
        ),
        start_date=start_date,
        end_date=end_date,
    )
    return build_yahoo_daily_completeness_plan(
        listings=selected,
        stored_session_dates=stored,
        start_date=start_date,
        end_date=end_date,
        now=current,
        max_request_days=max_request_days,
        session_service=session_service,
        enumerated_listing_count=len(enumerated),
    )


def select_yahoo_stored_session_dates(
    *,
    cursor: Any,
    provider_listing_ids: tuple[UUID, ...],
    start_date: date,
    end_date: date,
) -> dict[UUID, tuple[date, ...]]:
    """Read in-scope current bar dates for exact provider-listing UUIDs."""

    if not callable(getattr(cursor, "execute", None)) or not callable(
        getattr(cursor, "fetchall", None)
    ):
        raise TypeError("cursor must provide execute and fetchall methods.")
    _date_range(start_date, end_date)
    if not isinstance(provider_listing_ids, tuple):
        raise TypeError("provider_listing_ids must be a tuple.")
    if any(not isinstance(item, UUID) for item in provider_listing_ids):
        raise TypeError("provider_listing_ids must contain UUID values.")
    if len(provider_listing_ids) != len(set(provider_listing_ids)):
        raise ValueError("provider_listing_ids must be unique.")
    result: dict[UUID, list[date]] = {
        item: [] for item in provider_listing_ids
    }
    if not provider_listing_ids:
        return {}
    cursor.execute(
        """
        SELECT provider_listing_id, trading_date
        FROM stonks.ohlcv_daily
        WHERE provider_listing_id = ANY(%s)
          AND trading_date BETWEEN %s AND %s
        ORDER BY provider_listing_id, trading_date
        """,
        (list(provider_listing_ids), start_date, end_date),
    )
    for row in cursor.fetchall():
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise ValueError("Yahoo stored-date query returned an invalid row.")
        listing_id, trading_date = row
        if listing_id not in result or type(trading_date) is not date:
            raise ValueError("Yahoo stored-date query returned invalid data.")
        if not start_date <= trading_date <= end_date:
            raise ValueError("Yahoo stored-date query returned an out-of-range date.")
        result[listing_id].append(trading_date)
    return {
        listing_id: _validated_dates("stored_session_dates", tuple(values))
        for listing_id, values in result.items()
    }


def build_yahoo_daily_completeness_plan(
    *,
    listings: tuple[SeededYahooListing, ...],
    stored_session_dates: Mapping[UUID, Iterable[date]],
    start_date: date,
    end_date: date,
    now: datetime,
    max_request_days: int,
    session_service: MarketSessionService | None = None,
    enumerated_listing_count: int | None = None,
) -> YahooDailyCompletenessPlan:
    """Build a pure completeness plan from resolved seeds and stored dates."""

    _date_range(start_date, end_date)
    current = _aware_utc(now)
    _positive_integer("max_request_days", max_request_days)
    if not isinstance(listings, tuple) or any(
        not isinstance(item, SeededYahooListing) for item in listings
    ):
        raise TypeError("listings must contain SeededYahooListing values.")
    tickers = tuple(item.target.ticker for item in listings)
    if tickers != tuple(sorted(tickers)) or len(tickers) != len(set(tickers)):
        raise ValueError("listings must have unique ordered tickers.")
    if not isinstance(stored_session_dates, Mapping):
        raise TypeError("stored_session_dates must be a mapping.")
    listing_ids = {item.target.provider_listing_id for item in listings}
    if set(stored_session_dates) - listing_ids:
        raise ValueError("stored_session_dates contains an unknown listing UUID.")
    stored = {
        listing_id: _validated_dates(
            "stored_session_dates",
            tuple(stored_session_dates.get(listing_id, ())),
        )
        for listing_id in listing_ids
    }
    if any(
        item < start_date or item > end_date
        for values in stored.values()
        for item in values
    ):
        raise ValueError("stored_session_dates must be inside the plan range.")

    service = session_service or MarketSessionService()
    expected_cache: dict[SessionPolicy, tuple[ExpectedSession, ...] | None] = {}
    observed_cache: dict[
        SessionPolicy,
        tuple[ObservedPollCandidate, ...] | None,
    ] = {}
    plans = tuple(
        _plan_listing(
            seeded=item,
            stored_dates=stored[item.target.provider_listing_id],
            start_date=start_date,
            end_date=end_date,
            now=current,
            max_request_days=max_request_days,
            session_service=service,
            expected_cache=expected_cache,
            observed_cache=observed_cache,
        )
        for item in listings
    )
    count = (
        len(listings)
        if enumerated_listing_count is None
        else enumerated_listing_count
    )
    return YahooDailyCompletenessPlan(
        start_date=start_date,
        end_date=end_date,
        planned_at=current,
        enumerated_listing_count=count,
        listings=plans,
    )


def _plan_listing(
    *,
    seeded: SeededYahooListing,
    stored_dates: tuple[date, ...],
    start_date: date,
    end_date: date,
    now: datetime,
    max_request_days: int,
    session_service: MarketSessionService,
    expected_cache: dict[SessionPolicy, tuple[ExpectedSession, ...] | None],
    observed_cache: dict[
        SessionPolicy,
        tuple[ObservedPollCandidate, ...] | None,
    ],
) -> YahooListingCompletenessPlan:
    policy = seeded.policy
    if policy.calendar_name is None:
        candidates = observed_cache.get(policy)
        if policy not in observed_cache:
            try:
                candidates = tuple(
                    session_service.observed_poll_candidate(
                        policy=policy,
                        candidate_date=item,
                    )
                    for item in _inclusive_dates(start_date, end_date)
                )
            except OHLCVCalendarError:
                candidates = None
            observed_cache[policy] = candidates
        if candidates is None:
            return _failed_plan(seeded, stored_dates)
        due = tuple(
            item
            for item in candidates
            if item.is_eligible(now) and item.candidate_date not in stored_dates
        )
        pulls = _build_pulls(
            listing=seeded.target,
            reason=YahooPullReason.DUE_OBSERVED_POLL,
            candidate_dates=tuple(item.candidate_date for item in due),
            ordered_reference=tuple(
                item.candidate_date
                for item in candidates
                if item.is_eligible(now)
            ),
            max_request_days=max_request_days,
        )
        return YahooListingCompletenessPlan(
            listing=seeded.target,
            policy_code=policy.code,
            status=YahooCompletenessStatus.PLANNED,
            stored_session_dates=stored_dates,
            observed_poll_candidates=due,
            pulls=pulls,
        )

    expected = expected_cache.get(policy)
    if policy not in expected_cache:
        try:
            expected = session_service.expected_sessions(
                policy=policy,
                start_date=start_date,
                end_date=end_date,
            )
        except OHLCVCalendarError:
            expected = None
        expected_cache[policy] = expected
    if expected is None:
        return _failed_plan(seeded, stored_dates)
    eligible = tuple(item for item in expected if item.is_eligible(now))
    missing = tuple(
        item for item in eligible if item.session_date not in stored_dates
    )
    pulls = _build_pulls(
        listing=seeded.target,
        reason=YahooPullReason.ELIGIBLE_MISSING_SESSION,
        candidate_dates=tuple(item.session_date for item in missing),
        ordered_reference=tuple(item.session_date for item in eligible),
        max_request_days=max_request_days,
    )
    return YahooListingCompletenessPlan(
        listing=seeded.target,
        policy_code=policy.code,
        status=YahooCompletenessStatus.PLANNED,
        stored_session_dates=stored_dates,
        expected_sessions=expected,
        eligible_sessions=eligible,
        missing_sessions=missing,
        pulls=pulls,
    )


def _failed_plan(
    seeded: SeededYahooListing,
    stored_dates: tuple[date, ...],
) -> YahooListingCompletenessPlan:
    return YahooListingCompletenessPlan(
        listing=seeded.target,
        policy_code=seeded.policy.code,
        status=YahooCompletenessStatus.FAILED,
        stored_session_dates=stored_dates,
        failure_reason=YahooPlanningFailureReason.CALENDAR_POLICY,
    )


def _build_pulls(
    *,
    listing: YahooListingTarget,
    reason: YahooPullReason,
    candidate_dates: tuple[date, ...],
    ordered_reference: tuple[date, ...],
    max_request_days: int,
) -> tuple[YahooDailyPull, ...]:
    selected = set(candidate_dates)
    runs: list[list[date]] = []
    current: list[date] = []
    for item in ordered_reference:
        if item in selected:
            if current:
                request_days = (
                    item + timedelta(days=1) - current[0]
                ).days
                if request_days > max_request_days:
                    runs.append(current)
                    current = []
            current.append(item)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return tuple(
        YahooDailyPull(
            request=YahooAcquisitionRequest(
                listing=listing,
                start_date=run[0],
                end_date_exclusive=run[-1] + timedelta(days=1),
                mode=YahooRequestMode.DAILY,
            ),
            reason=reason,
            planned_dates=tuple(run),
        )
        for run in runs
    )


def _select_listings(
    enumerated: tuple[SeededYahooListing, ...],
    tickers: tuple[str, ...],
) -> tuple[SeededYahooListing, ...]:
    if not enumerated:
        raise OHLCVConfigError("No active seeded Yahoo listings were found.")
    known = {item.target.ticker for item in enumerated}
    if set(tickers) - known:
        raise OHLCVConfigError("Requested Yahoo ticker is not an active seed.")
    selected = tuple(
        item for item in enumerated if not tickers or item.target.ticker in tickers
    )
    if not selected:
        raise OHLCVConfigError("Yahoo completeness scope selected no listings.")
    return selected


def _validated_tickers(values: object) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError("tickers must be a tuple.")
    for item in values:
        _required_text("ticker", item)
    if len(values) != len(set(values)):
        raise ValueError("tickers must be unique.")
    return tuple(sorted(values))


def _validated_dates(field_name: str, values: object) -> tuple[date, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple.")
    if any(type(item) is not date for item in values):
        raise TypeError(f"{field_name} must contain date values.")
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique ordered dates.")
    return values


def _validated_values(
    field_name: str,
    values: object,
    value_type: type,
) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple.")
    if any(not isinstance(item, value_type) for item in values):
        raise TypeError(f"{field_name} contains an invalid value.")


def _session_dates(values: tuple[ExpectedSession, ...]) -> tuple[date, ...]:
    dates = tuple(item.session_date for item in values)
    return _validated_dates("sessions", dates)


def _inclusive_dates(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _date_range(start_date: object, end_date: object) -> None:
    if type(start_date) is not date or type(end_date) is not date:
        raise TypeError("start_date and end_date must be dates.")
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date.")


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("now must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware.")
    return value.astimezone(UTC)


def _positive_integer(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")


def _required_text(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty and trimmed.")
