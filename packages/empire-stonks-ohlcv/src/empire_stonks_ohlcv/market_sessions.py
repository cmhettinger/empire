"""Provider-neutral market-session eligibility services."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Iterable, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas_market_calendars as market_calendars

from empire_stonks_ohlcv.exceptions import OHLCVCalendarError


_MAX_DELAY_MINUTES = 7 * 24 * 60
_MAX_POLICY_CODE_LENGTH = 32


class EligibilityRule(StrEnum):
    """How a completed session becomes eligible for provider acquisition."""

    SESSION_CLOSE = "SESSION_CLOSE"
    LOCAL_CUTOFF = "LOCAL_CUTOFF"


class SessionDateRule(StrEnum):
    """How a provider daily timestamp maps to a stored session date."""

    CALENDAR_SESSION = "CALENDAR_SESSION"
    PROVIDER_LOCAL_DATE = "PROVIDER_LOCAL_DATE"
    PROVIDER_DAILY_SETTLEMENT = "PROVIDER_DAILY_SETTLEMENT"


@dataclass(frozen=True)
class SessionPolicy:
    """Validated scheduling policy assigned to one or more provider listings."""

    code: str
    calendar_name: str | None
    timezone_name: str
    eligibility_rule: EligibilityRule
    cutoff_local_time: time | None
    availability_delay_minutes: int
    session_date_rule: SessionDateRule

    def __post_init__(self) -> None:
        _validate_policy_code(self.code)
        _validate_optional_text("calendar_name", self.calendar_name)
        _timezone(self.timezone_name)

        if not isinstance(self.eligibility_rule, EligibilityRule):
            raise TypeError("eligibility_rule must be an EligibilityRule.")
        if not isinstance(self.session_date_rule, SessionDateRule):
            raise TypeError("session_date_rule must be a SessionDateRule.")
        if (
            not isinstance(self.availability_delay_minutes, int)
            or isinstance(self.availability_delay_minutes, bool)
        ):
            raise TypeError("availability_delay_minutes must be an integer.")
        if not 0 <= self.availability_delay_minutes <= _MAX_DELAY_MINUTES:
            raise ValueError(
                "availability_delay_minutes must be from 0 through 10080."
            )
        if self.cutoff_local_time is not None:
            if type(self.cutoff_local_time) is not time:
                raise TypeError("cutoff_local_time must be a time or None.")
            if self.cutoff_local_time.tzinfo is not None:
                raise ValueError("cutoff_local_time must be a naive local time.")

        if self.eligibility_rule is EligibilityRule.SESSION_CLOSE:
            if self.calendar_name is None:
                raise ValueError("SESSION_CLOSE requires calendar_name.")
            if self.cutoff_local_time is not None:
                raise ValueError("SESSION_CLOSE forbids cutoff_local_time.")
            if self.session_date_rule is not SessionDateRule.CALENDAR_SESSION:
                raise ValueError(
                    "SESSION_CLOSE requires CALENDAR_SESSION date handling."
                )
        elif self.cutoff_local_time is None:
            raise ValueError("LOCAL_CUTOFF requires cutoff_local_time.")

        if (
            self.eligibility_rule is EligibilityRule.LOCAL_CUTOFF
            and self.session_date_rule is SessionDateRule.CALENDAR_SESSION
        ):
            raise ValueError(
                "LOCAL_CUTOFF requires a provider-derived session date rule."
            )

    @property
    def availability_delay(self) -> timedelta:
        """Return the configured availability delay."""

        return timedelta(minutes=self.availability_delay_minutes)

    @property
    def is_observed_only(self) -> bool:
        """Whether the policy deliberately lacks an authoritative calendar."""

        return self.calendar_name is None


@dataclass(frozen=True)
class CalendarSession:
    """One authoritative calendar label and its aware close instant."""

    session_date: date
    close_at: datetime

    def __post_init__(self) -> None:
        _validate_date("session_date", self.session_date)
        object.__setattr__(
            self,
            "close_at",
            _aware_utc("close_at", self.close_at),
        )


@dataclass(frozen=True)
class CalendarSchedule:
    """Resolved calendar identity, time zone, and ordered sessions."""

    calendar_name: str
    timezone_name: str
    sessions: tuple[CalendarSession, ...]

    def __post_init__(self) -> None:
        _validate_required_text("calendar_name", self.calendar_name)
        _timezone(self.timezone_name)
        if not isinstance(self.sessions, tuple):
            raise TypeError("sessions must be a tuple.")
        if any(not isinstance(item, CalendarSession) for item in self.sessions):
            raise TypeError("sessions must contain CalendarSession values.")
        session_dates = tuple(item.session_date for item in self.sessions)
        if session_dates != tuple(sorted(session_dates)):
            raise ValueError("sessions must be ordered by session_date.")
        if len(session_dates) != len(set(session_dates)):
            raise ValueError("sessions must have unique session_date values.")


@dataclass(frozen=True)
class ExpectedSession:
    """One expected provider session and its first eligible acquisition time."""

    session_date: date
    eligible_at: datetime

    def __post_init__(self) -> None:
        _validate_date("session_date", self.session_date)
        object.__setattr__(
            self,
            "eligible_at",
            _aware_utc("eligible_at", self.eligible_at),
        )

    def is_eligible(self, now: datetime) -> bool:
        """Return whether this session is eligible at the supplied instant."""

        return self.eligible_at <= _aware_utc("now", now)


@dataclass(frozen=True)
class ObservedPollCandidate:
    """A due time that makes no claim that a provider session must exist."""

    candidate_date: date
    poll_at: datetime

    def __post_init__(self) -> None:
        _validate_date("candidate_date", self.candidate_date)
        object.__setattr__(
            self,
            "poll_at",
            _aware_utc("poll_at", self.poll_at),
        )

    def is_eligible(self, now: datetime) -> bool:
        """Return whether the observed-only range may be polled."""

        return self.poll_at <= _aware_utc("now", now)


class MarketCalendarProvider(Protocol):
    """Injected adapter for authoritative calendar schedules."""

    def schedule(
        self,
        *,
        calendar_name: str,
        start_date: date,
        end_date: date,
    ) -> CalendarSchedule:
        """Return an inclusive schedule for a registered calendar."""


class PandasMarketCalendarProvider:
    """Narrow adapter around pandas_market_calendars."""

    def schedule(
        self,
        *,
        calendar_name: str,
        start_date: date,
        end_date: date,
    ) -> CalendarSchedule:
        _validate_required_text("calendar_name", calendar_name)
        _validate_date_range(start_date, end_date)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                calendar = market_calendars.get_calendar(calendar_name)
                frame = calendar.schedule(
                    start_date=start_date,
                    end_date=end_date,
                    tz="UTC",
                    market_times=("market_open", "market_close"),
                )
            except Exception as exc:
                raise OHLCVCalendarError(
                    f"Market calendar {calendar_name!r} could not be resolved."
                ) from exc

        unsafe_warnings = [
            item for item in caught if not _is_known_safe_calendar_warning(item)
        ]
        if unsafe_warnings:
            raise OHLCVCalendarError(
                f"Market calendar {calendar_name!r} emitted an unsafe warning."
            )
        if "market_close" not in frame.columns:
            raise OHLCVCalendarError(
                f"Market calendar {calendar_name!r} has no market_close."
            )

        sessions: list[CalendarSession] = []
        for session_label, row in frame.iterrows():
            try:
                session_date = session_label.date()
                close_at = row["market_close"].to_pydatetime()
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise OHLCVCalendarError(
                    f"Market calendar {calendar_name!r} returned invalid data."
                ) from exc
            sessions.append(
                CalendarSession(
                    session_date=session_date,
                    close_at=close_at,
                )
            )

        return CalendarSchedule(
            calendar_name=calendar_name,
            timezone_name=str(calendar.tz),
            sessions=tuple(sessions),
        )


class MarketSessionService:
    """Calculate expected, eligible, and provider-labeled daily sessions."""

    def __init__(
        self,
        calendar_provider: MarketCalendarProvider | None = None,
    ) -> None:
        self._calendar_provider = (
            calendar_provider
            if calendar_provider is not None
            else PandasMarketCalendarProvider()
        )

    def expected_sessions(
        self,
        *,
        policy: SessionPolicy,
        start_date: date,
        end_date: date,
    ) -> tuple[ExpectedSession, ...]:
        """Return authoritative expected sessions for an inclusive date range."""

        _validate_policy(policy)
        _validate_date_range(start_date, end_date)
        if policy.calendar_name is None:
            return ()

        schedule = self._calendar_provider.schedule(
            calendar_name=policy.calendar_name,
            start_date=start_date,
            end_date=end_date,
        )
        if schedule.calendar_name != policy.calendar_name:
            raise OHLCVCalendarError(
                "Market calendar returned a different calendar identity."
            )
        if policy.eligibility_rule is EligibilityRule.SESSION_CLOSE:
            _require_equivalent_timezones(
                policy.timezone_name,
                schedule.timezone_name,
                start_date,
            )

        expected: list[ExpectedSession] = []
        for session in schedule.sessions:
            if not start_date <= session.session_date <= end_date:
                raise OHLCVCalendarError(
                    "Market calendar returned a session outside the requested range."
                )
            eligible_at = self._eligible_at(
                policy=policy,
                session=session,
            )
            expected.append(
                ExpectedSession(
                    session_date=session.session_date,
                    eligible_at=eligible_at,
                )
            )
        return tuple(expected)

    def eligible_sessions(
        self,
        *,
        policy: SessionPolicy,
        start_date: date,
        end_date: date,
        now: datetime,
    ) -> tuple[ExpectedSession, ...]:
        """Return only expected sessions whose eligibility time has passed."""

        current = _aware_utc("now", now)
        return tuple(
            session
            for session in self.expected_sessions(
                policy=policy,
                start_date=start_date,
                end_date=end_date,
            )
            if session.eligible_at <= current
        )

    def eligible_missing_sessions(
        self,
        *,
        policy: SessionPolicy,
        start_date: date,
        end_date: date,
        stored_session_dates: Iterable[date],
        now: datetime,
    ) -> tuple[ExpectedSession, ...]:
        """Return eligible calendar sessions without a stored provider bar."""

        stored = _validated_date_set(
            "stored_session_dates",
            stored_session_dates,
        )
        return tuple(
            session
            for session in self.eligible_sessions(
                policy=policy,
                start_date=start_date,
                end_date=end_date,
                now=now,
            )
            if session.session_date not in stored
        )

    def observed_poll_candidate(
        self,
        *,
        policy: SessionPolicy,
        candidate_date: date,
    ) -> ObservedPollCandidate:
        """Return a due time for an explicit observed-only cutoff policy."""

        _validate_policy(policy)
        _validate_date("candidate_date", candidate_date)
        if not policy.is_observed_only:
            raise OHLCVCalendarError(
                "Observed polling requires a policy without calendar_name."
            )
        if (
            policy.eligibility_rule is not EligibilityRule.LOCAL_CUTOFF
            or policy.cutoff_local_time is None
        ):
            raise OHLCVCalendarError(
                "Observed polling requires a LOCAL_CUTOFF policy."
            )
        return ObservedPollCandidate(
            candidate_date=candidate_date,
            poll_at=_cutoff_utc(
                session_date=candidate_date,
                cutoff_local_time=policy.cutoff_local_time,
                timezone_name=policy.timezone_name,
                delay=policy.availability_delay,
            ),
        )

    def provider_session_date(
        self,
        *,
        policy: SessionPolicy,
        provider_timestamp: datetime,
        provider_timezone_name: str,
        expected_session_dates: Iterable[date] | None = None,
    ) -> date:
        """Map an aware timestamp in the provider-declared time zone."""

        _validate_policy(policy)
        timestamp = _aware_utc("provider_timestamp", provider_timestamp)
        session_date = timestamp.astimezone(
            _timezone(provider_timezone_name)
        ).date()

        if policy.calendar_name is None:
            return session_date
        if expected_session_dates is None:
            raise OHLCVCalendarError(
                "Calendar-backed provider dates require expected session labels."
            )
        expected = _validated_date_set(
            "expected_session_dates",
            expected_session_dates,
        )
        if session_date not in expected:
            raise OHLCVCalendarError(
                "Provider timestamp does not match an expected session label."
            )
        return session_date

    @staticmethod
    def _eligible_at(
        *,
        policy: SessionPolicy,
        session: CalendarSession,
    ) -> datetime:
        if policy.eligibility_rule is EligibilityRule.SESSION_CLOSE:
            return session.close_at + policy.availability_delay
        if policy.cutoff_local_time is None:
            raise OHLCVCalendarError(
                "LOCAL_CUTOFF policy is missing cutoff_local_time."
            )
        return _cutoff_utc(
            session_date=session.session_date,
            cutoff_local_time=policy.cutoff_local_time,
            timezone_name=policy.timezone_name,
            delay=policy.availability_delay,
        )


def _validate_policy(policy: object) -> None:
    if not isinstance(policy, SessionPolicy):
        raise TypeError("policy must be a SessionPolicy.")


def _validate_policy_code(value: object) -> None:
    _validate_required_text("code", value)
    assert isinstance(value, str)
    if len(value) > _MAX_POLICY_CODE_LENGTH:
        raise ValueError("code must be at most 32 characters.")
    if value != value.upper():
        raise ValueError("code must be uppercase.")


def _validate_required_text(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value:
        raise ValueError(f"{field_name} is required.")
    if value != value.strip():
        raise ValueError(
            f"{field_name} must not contain leading or trailing whitespace."
        )


def _validate_optional_text(field_name: str, value: object) -> None:
    if value is None:
        return
    _validate_required_text(field_name, value)


def _validate_date(field_name: str, value: object) -> None:
    if type(value) is not date:
        raise TypeError(f"{field_name} must be a date.")


def _validate_date_range(start_date: object, end_date: object) -> None:
    _validate_date("start_date", start_date)
    _validate_date("end_date", end_date)
    assert isinstance(start_date, date)
    assert isinstance(end_date, date)
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date.")


def _aware_utc(field_name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _timezone(timezone_name: object) -> ZoneInfo:
    _validate_required_text("timezone_name", timezone_name)
    assert isinstance(timezone_name, str)
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone_name {timezone_name!r}.") from exc


def _strict_local_datetime(
    *,
    local_date: date,
    local_time: time,
    timezone_name: str,
) -> datetime:
    timezone = _timezone(timezone_name)
    naive = datetime.combine(local_date, local_time)
    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=timezone, fold=fold)
        utc_candidate = candidate.astimezone(UTC)
        round_trip = utc_candidate.astimezone(timezone)
        if round_trip.replace(tzinfo=None) == naive:
            candidates[utc_candidate] = candidate
    if len(candidates) != 1:
        raise OHLCVCalendarError(
            "Local cutoff is ambiguous or nonexistent in its configured timezone."
        )
    return next(iter(candidates.values()))


def _cutoff_utc(
    *,
    session_date: date,
    cutoff_local_time: time,
    timezone_name: str,
    delay: timedelta,
) -> datetime:
    cutoff = _strict_local_datetime(
        local_date=session_date,
        local_time=cutoff_local_time,
        timezone_name=timezone_name,
    )
    return cutoff.astimezone(UTC) + delay


def _validated_date_set(
    field_name: str,
    values: Iterable[date],
) -> frozenset[date]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of dates.")
    try:
        result = frozenset(values)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an iterable of dates.") from exc
    for value in result:
        _validate_date(field_name, value)
    return result


def _require_equivalent_timezones(
    policy_timezone_name: str,
    calendar_timezone_name: str,
    reference_date: date,
) -> None:
    policy_timezone = _timezone(policy_timezone_name)
    calendar_timezone = _timezone(calendar_timezone_name)
    for month in (1, 7):
        instant = datetime(reference_date.year, month, 1, 12, tzinfo=UTC)
        if (
            instant.astimezone(policy_timezone).utcoffset()
            != instant.astimezone(calendar_timezone).utcoffset()
        ):
            raise OHLCVCalendarError(
                "SESSION_CLOSE policy timezone does not match its calendar."
            )


def _is_known_safe_calendar_warning(
    warning: warnings.WarningMessage,
) -> bool:
    message = str(warning.message)
    if issubclass(warning.category, DeprecationWarning):
        return "generic' unit for NumPy timedelta is deprecated" in message
    return (
        issubclass(warning.category, UserWarning)
        and "['break_start', 'break_end'] are discontinued" in message
    )
