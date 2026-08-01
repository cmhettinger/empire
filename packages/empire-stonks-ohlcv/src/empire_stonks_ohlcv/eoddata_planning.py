"""Calendar-aware EODData exchange-bulk work planning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from empire_stonks_ohlcv.config import (
    DEFAULT_EODDATA_EXCHANGES,
    MAX_EODDATA_RECONCILIATION_SESSIONS,
)
from empire_stonks_ohlcv.eoddata import EODDATA_PROVIDER_CODE
from empire_stonks_ohlcv.eoddata_policies import (
    EODDataExchangeSessionPolicy,
    resolve_eoddata_exchange_policies,
)
from empire_stonks_ohlcv.exceptions import OHLCVCalendarError
from empire_stonks_ohlcv.market_sessions import (
    ExpectedSession,
    MarketSessionService,
    SessionPolicy,
)


class EODDataExchangePlanStatus(StrEnum):
    """Outcome of planning one configured exchange."""

    PLANNED = "planned"
    INACTIVE = "inactive"
    FAILED = "failed"


class EODDataExchangeWorkReason(StrEnum):
    """Why one exchange/date needs a bulk provider request."""

    ELIGIBLE_MISSING_SESSION = "eligible_missing_session"
    RECENT_RECONCILIATION = "recent_reconciliation"


class EODDataPlanningFailureReason(StrEnum):
    """Stable secret-safe planning failure categories."""

    CALENDAR_POLICY = "calendar_policy"


@dataclass(frozen=True)
class EODDataStoredSessionCount:
    """Stored active-listing bar evidence for one exchange session."""

    session_date: date
    bar_count: int

    def __post_init__(self) -> None:
        _date("session_date", self.session_date)
        _nonnegative_integer("bar_count", self.bar_count)
        if self.bar_count == 0:
            raise ValueError("bar_count must be greater than zero.")


@dataclass(frozen=True)
class EODDataExchangeStorage:
    """Current listing and bar state for one configured exchange."""

    exchange: str
    total_listing_count: int
    active_listing_count: int
    stored_sessions: tuple[EODDataStoredSessionCount, ...]

    def __post_init__(self) -> None:
        _required_text("exchange", self.exchange)
        _nonnegative_integer("total_listing_count", self.total_listing_count)
        _nonnegative_integer("active_listing_count", self.active_listing_count)
        if self.active_listing_count > self.total_listing_count:
            raise ValueError(
                "active_listing_count cannot exceed total_listing_count."
            )
        _values(
            "stored_sessions",
            self.stored_sessions,
            EODDataStoredSessionCount,
        )
        dates = tuple(item.session_date for item in self.stored_sessions)
        if dates != tuple(sorted(dates)) or len(dates) != len(set(dates)):
            raise ValueError("stored_sessions must have unique ordered dates.")
        if self.active_listing_count == 0 and self.stored_sessions:
            raise ValueError(
                "An exchange without active listings cannot have active bars."
            )

    @property
    def is_inactive(self) -> bool:
        """Whether discovered listings exist but all are operator-disabled."""

        return self.total_listing_count > 0 and self.active_listing_count == 0

    def bar_count_for(self, session_date: date) -> int:
        """Return stored active-listing bars for an exact provider date."""

        _date("session_date", session_date)
        return next(
            (
                item.bar_count
                for item in self.stored_sessions
                if item.session_date == session_date
            ),
            0,
        )


@dataclass(frozen=True)
class EODDataExchangeWork:
    """One bounded exchange/date request selected by the planner."""

    exchange: str
    effective_date: date
    reason: EODDataExchangeWorkReason
    stored_bar_count: int

    def __post_init__(self) -> None:
        _required_text("exchange", self.exchange)
        _date("effective_date", self.effective_date)
        if not isinstance(self.reason, EODDataExchangeWorkReason):
            raise TypeError("reason must be an EODDataExchangeWorkReason.")
        _nonnegative_integer("stored_bar_count", self.stored_bar_count)
        if (
            self.reason
            is EODDataExchangeWorkReason.ELIGIBLE_MISSING_SESSION
            and self.stored_bar_count != 0
        ):
            raise ValueError("Missing-session work cannot have stored bars.")
        if (
            self.reason
            is EODDataExchangeWorkReason.RECENT_RECONCILIATION
            and self.stored_bar_count == 0
        ):
            raise ValueError("Reconciliation work requires stored bars.")

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "exchange": self.exchange,
            "effective_date": self.effective_date.isoformat(),
            "reason": self.reason.value,
            "stored_bar_count": self.stored_bar_count,
        }


@dataclass(frozen=True)
class EODDataExchangeDailyPlan:
    """Eligibility, completeness, and reconciliation for one exchange."""

    exchange: str
    policy_code: str
    status: EODDataExchangePlanStatus
    total_listing_count: int
    active_listing_count: int
    expected_sessions: tuple[ExpectedSession, ...] = ()
    eligible_sessions: tuple[ExpectedSession, ...] = ()
    missing_sessions: tuple[ExpectedSession, ...] = ()
    reconciliation_sessions: tuple[ExpectedSession, ...] = ()
    work: tuple[EODDataExchangeWork, ...] = ()
    failure_reason: EODDataPlanningFailureReason | None = None

    def __post_init__(self) -> None:
        _required_text("exchange", self.exchange)
        _required_text("policy_code", self.policy_code)
        if not isinstance(self.status, EODDataExchangePlanStatus):
            raise TypeError("status must be an EODDataExchangePlanStatus.")
        _nonnegative_integer("total_listing_count", self.total_listing_count)
        _nonnegative_integer("active_listing_count", self.active_listing_count)
        if self.active_listing_count > self.total_listing_count:
            raise ValueError(
                "active_listing_count cannot exceed total_listing_count."
            )
        for field_name, values in (
            ("expected_sessions", self.expected_sessions),
            ("eligible_sessions", self.eligible_sessions),
            ("missing_sessions", self.missing_sessions),
            ("reconciliation_sessions", self.reconciliation_sessions),
        ):
            _values(field_name, values, ExpectedSession)
            _ordered_session_dates(field_name, values)
        _values("work", self.work, EODDataExchangeWork)
        if any(item.exchange != self.exchange for item in self.work):
            raise ValueError("Every work item must match the plan exchange.")
        work_dates = tuple(item.effective_date for item in self.work)
        if work_dates != tuple(sorted(work_dates)) or len(work_dates) != len(
            set(work_dates)
        ):
            raise ValueError("work must have unique ordered dates.")
        expected_dates = _session_dates(self.expected_sessions)
        eligible_dates = _session_dates(self.eligible_sessions)
        missing_dates = _session_dates(self.missing_sessions)
        reconciliation_dates = _session_dates(self.reconciliation_sessions)
        if not set(eligible_dates) <= set(expected_dates):
            raise ValueError("eligible_sessions must be expected sessions.")
        if not set(missing_dates) <= set(eligible_dates):
            raise ValueError("missing_sessions must be eligible sessions.")
        if not set(reconciliation_dates) <= set(eligible_dates):
            raise ValueError(
                "reconciliation_sessions must be eligible sessions."
            )
        missing_date_set = set(missing_dates)
        expected_work = tuple(
            (
                session_date,
                EODDataExchangeWorkReason.ELIGIBLE_MISSING_SESSION
                if session_date in missing_date_set
                else EODDataExchangeWorkReason.RECENT_RECONCILIATION,
            )
            for session_date in eligible_dates
            if session_date in missing_date_set
            or session_date in set(reconciliation_dates)
        )
        actual_work = tuple(
            (item.effective_date, item.reason) for item in self.work
        )
        if actual_work != expected_work:
            raise ValueError(
                "work must exactly cover missing and recent complete sessions."
            )
        if self.failure_reason is not None and not isinstance(
            self.failure_reason,
            EODDataPlanningFailureReason,
        ):
            raise TypeError(
                "failure_reason must be an EODDataPlanningFailureReason."
            )
        if self.status is EODDataExchangePlanStatus.FAILED:
            if (
                self.failure_reason is None
                or self.expected_sessions
                or self.eligible_sessions
                or self.missing_sessions
                or self.reconciliation_sessions
                or self.work
            ):
                raise ValueError("FAILED requires a reason and forbids work.")
        elif self.failure_reason is not None:
            raise ValueError("Non-failed plans forbid failure_reason.")
        if self.status is EODDataExchangePlanStatus.INACTIVE and (
            self.active_listing_count != 0
            or self.total_listing_count == 0
            or self.missing_sessions
            or self.reconciliation_sessions
            or self.work
        ):
            raise ValueError(
                "INACTIVE requires disabled listings and forbids due work."
            )

    @property
    def latest_expected_session(self) -> ExpectedSession | None:
        return self.expected_sessions[-1] if self.expected_sessions else None

    @property
    def latest_eligible_session(self) -> ExpectedSession | None:
        return self.eligible_sessions[-1] if self.eligible_sessions else None

    @property
    def latest_expected_is_eligible(self) -> bool:
        latest = self.latest_expected_session
        return latest is not None and latest in self.eligible_sessions

    @property
    def latest_expected_is_complete(self) -> bool:
        latest = self.latest_expected_session
        return (
            latest is not None
            and latest in self.eligible_sessions
            and latest not in self.missing_sessions
        )

    @property
    def latest_eligible_is_complete(self) -> bool:
        latest = self.latest_eligible_session
        return latest is not None and latest not in self.missing_sessions

    @property
    def ineligible_session_count(self) -> int:
        return len(self.expected_sessions) - len(self.eligible_sessions)

    def to_safe_dict(self) -> dict[str, object]:
        latest_expected = self.latest_expected_session
        latest_eligible = self.latest_eligible_session
        return {
            "exchange": self.exchange,
            "policy_code": self.policy_code,
            "status": self.status.value,
            "total_listing_count": self.total_listing_count,
            "active_listing_count": self.active_listing_count,
            "expected_session_count": len(self.expected_sessions),
            "eligible_session_count": len(self.eligible_sessions),
            "ineligible_session_count": self.ineligible_session_count,
            "missing_session_count": len(self.missing_sessions),
            "reconciliation_session_count": len(
                self.reconciliation_sessions
            ),
            "latest_expected_session": (
                None
                if latest_expected is None
                else latest_expected.session_date.isoformat()
            ),
            "latest_expected_is_eligible": self.latest_expected_is_eligible,
            "latest_expected_is_complete": self.latest_expected_is_complete,
            "latest_eligible_session": (
                None
                if latest_eligible is None
                else latest_eligible.session_date.isoformat()
            ),
            "latest_eligible_is_complete": (
                self.latest_eligible_is_complete
            ),
            "work": [item.to_safe_dict() for item in self.work],
            "failure_reason": (
                None
                if self.failure_reason is None
                else self.failure_reason.value
            ),
        }


@dataclass(frozen=True)
class EODDataDailyPlan:
    """Deterministic bounded work across configured EODData exchanges."""

    start_date: date
    end_date: date
    planned_at: datetime
    reconciliation_sessions: int
    exchanges: tuple[EODDataExchangeDailyPlan, ...]

    def __post_init__(self) -> None:
        _date_range(self.start_date, self.end_date)
        object.__setattr__(self, "planned_at", _aware_utc(self.planned_at))
        _reconciliation_sessions(self.reconciliation_sessions)
        _values("exchanges", self.exchanges, EODDataExchangeDailyPlan)
        names = tuple(item.exchange for item in self.exchanges)
        if names != DEFAULT_EODDATA_EXCHANGES:
            raise ValueError(
                "exchanges must use configured EODData exchange order."
            )

    @property
    def work(self) -> tuple[EODDataExchangeWork, ...]:
        return tuple(item for plan in self.exchanges for item in plan.work)

    @property
    def failed_exchange_count(self) -> int:
        return sum(
            item.status is EODDataExchangePlanStatus.FAILED
            for item in self.exchanges
        )

    @property
    def inactive_exchange_count(self) -> int:
        return sum(
            item.status is EODDataExchangePlanStatus.INACTIVE
            for item in self.exchanges
        )

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "planned_at": self.planned_at.isoformat(),
            "reconciliation_sessions": self.reconciliation_sessions,
            "exchange_count": len(self.exchanges),
            "failed_exchange_count": self.failed_exchange_count,
            "inactive_exchange_count": self.inactive_exchange_count,
            "work_count": len(self.work),
            "exchanges": [item.to_safe_dict() for item in self.exchanges],
        }


def plan_eoddata_exchange_work(
    *,
    cursor: Any,
    start_date: date,
    end_date: date,
    now: datetime,
    reconciliation_sessions: int,
    exchanges: tuple[str, ...] = DEFAULT_EODDATA_EXCHANGES,
    session_service: MarketSessionService | None = None,
) -> EODDataDailyPlan:
    """Resolve policies and stored rows, then build bounded exchange work."""

    _date_range(start_date, end_date)
    current = _aware_utc(now)
    _reconciliation_sessions(reconciliation_sessions)
    _exchanges(exchanges)
    policies = resolve_eoddata_exchange_policies(
        cursor=cursor,
        exchanges=exchanges,
    )
    storage = select_eoddata_exchange_storage(
        cursor=cursor,
        exchanges=exchanges,
        start_date=start_date,
        end_date=end_date,
    )
    return build_eoddata_exchange_plan(
        policies=policies,
        storage=storage,
        start_date=start_date,
        end_date=end_date,
        now=current,
        reconciliation_sessions=reconciliation_sessions,
        session_service=session_service,
    )


def select_eoddata_exchange_storage(
    *,
    cursor: Any,
    exchanges: tuple[str, ...],
    start_date: date,
    end_date: date,
) -> tuple[EODDataExchangeStorage, ...]:
    """Read active listing totals and per-session bar counts by exchange."""

    if not callable(getattr(cursor, "execute", None)) or not callable(
        getattr(cursor, "fetchall", None)
    ):
        raise TypeError("cursor must provide execute and fetchall methods.")
    _exchanges(exchanges)
    _date_range(start_date, end_date)
    cursor.execute(
        """
        SELECT
            market,
            count(*) AS total_listing_count,
            count(*) FILTER (WHERE status = 'ACTIVE')
                AS active_listing_count
        FROM stonks.provider_listing
        WHERE provider_code = %s
          AND market = ANY(%s)
        GROUP BY market
        ORDER BY market
        """,
        (EODDATA_PROVIDER_CODE, list(exchanges)),
    )
    listing_counts = {item: (0, 0) for item in exchanges}
    for row in cursor.fetchall():
        if not isinstance(row, (tuple, list)) or len(row) != 3:
            raise ValueError("EODData listing-count query returned invalid data.")
        exchange, total_count, active_count = row
        if exchange not in listing_counts:
            raise ValueError("EODData listing-count query returned an exchange.")
        if listing_counts[exchange] != (0, 0):
            raise ValueError("EODData listing-count query returned duplicates.")
        _nonnegative_integer("total_listing_count", total_count)
        _nonnegative_integer("active_listing_count", active_count)
        listing_counts[exchange] = (total_count, active_count)

    cursor.execute(
        """
        SELECT
            listing.market,
            daily.trading_date,
            count(*) AS bar_count
        FROM stonks.provider_listing AS listing
        JOIN stonks.ohlcv_daily AS daily
          ON daily.provider_listing_id = listing.provider_listing_id
        WHERE listing.provider_code = %s
          AND listing.market = ANY(%s)
          AND listing.status = 'ACTIVE'
          AND daily.trading_date BETWEEN %s AND %s
        GROUP BY listing.market, daily.trading_date
        ORDER BY listing.market, daily.trading_date
        """,
        (EODDATA_PROVIDER_CODE, list(exchanges), start_date, end_date),
    )
    stored: dict[str, list[EODDataStoredSessionCount]] = {
        item: [] for item in exchanges
    }
    for row in cursor.fetchall():
        if not isinstance(row, (tuple, list)) or len(row) != 3:
            raise ValueError("EODData stored-bar query returned invalid data.")
        exchange, session_date, bar_count = row
        if exchange not in stored:
            raise ValueError("EODData stored-bar query returned an exchange.")
        stored[exchange].append(
            EODDataStoredSessionCount(
                session_date=session_date,
                bar_count=bar_count,
            )
        )
    return tuple(
        EODDataExchangeStorage(
            exchange=exchange,
            total_listing_count=listing_counts[exchange][0],
            active_listing_count=listing_counts[exchange][1],
            stored_sessions=tuple(stored[exchange]),
        )
        for exchange in exchanges
    )


def build_eoddata_exchange_plan(
    *,
    policies: tuple[EODDataExchangeSessionPolicy, ...],
    storage: tuple[EODDataExchangeStorage, ...],
    start_date: date,
    end_date: date,
    now: datetime,
    reconciliation_sessions: int,
    session_service: MarketSessionService | None = None,
) -> EODDataDailyPlan:
    """Build a pure plan from resolved policy and stored exchange state."""

    _date_range(start_date, end_date)
    current = _aware_utc(now)
    _reconciliation_sessions(reconciliation_sessions)
    _values("policies", policies, EODDataExchangeSessionPolicy)
    _values("storage", storage, EODDataExchangeStorage)
    policy_exchanges = tuple(item.exchange for item in policies)
    storage_exchanges = tuple(item.exchange for item in storage)
    if (
        policy_exchanges != DEFAULT_EODDATA_EXCHANGES
        or storage_exchanges != DEFAULT_EODDATA_EXCHANGES
    ):
        raise ValueError(
            "Policies and storage must use configured EODData exchange order."
        )
    service = session_service or MarketSessionService()
    expected_cache: dict[SessionPolicy, tuple[ExpectedSession, ...] | None] = {}
    plans = tuple(
        _plan_exchange(
            resolved_policy=resolved_policy,
            storage_state=storage_state,
            start_date=start_date,
            end_date=end_date,
            now=current,
            reconciliation_sessions=reconciliation_sessions,
            session_service=service,
            expected_cache=expected_cache,
        )
        for resolved_policy, storage_state in zip(policies, storage, strict=True)
    )
    return EODDataDailyPlan(
        start_date=start_date,
        end_date=end_date,
        planned_at=current,
        reconciliation_sessions=reconciliation_sessions,
        exchanges=plans,
    )


def _plan_exchange(
    *,
    resolved_policy: EODDataExchangeSessionPolicy,
    storage_state: EODDataExchangeStorage,
    start_date: date,
    end_date: date,
    now: datetime,
    reconciliation_sessions: int,
    session_service: MarketSessionService,
    expected_cache: dict[SessionPolicy, tuple[ExpectedSession, ...] | None],
) -> EODDataExchangeDailyPlan:
    if storage_state.exchange != resolved_policy.exchange:
        raise ValueError("Policy and storage exchange must match.")
    policy = resolved_policy.policy
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
        return EODDataExchangeDailyPlan(
            exchange=resolved_policy.exchange,
            policy_code=policy.code,
            status=EODDataExchangePlanStatus.FAILED,
            total_listing_count=storage_state.total_listing_count,
            active_listing_count=storage_state.active_listing_count,
            failure_reason=EODDataPlanningFailureReason.CALENDAR_POLICY,
        )
    eligible = tuple(item for item in expected if item.is_eligible(now))
    if storage_state.is_inactive:
        return EODDataExchangeDailyPlan(
            exchange=resolved_policy.exchange,
            policy_code=policy.code,
            status=EODDataExchangePlanStatus.INACTIVE,
            total_listing_count=storage_state.total_listing_count,
            active_listing_count=storage_state.active_listing_count,
            expected_sessions=expected,
            eligible_sessions=eligible,
        )
    missing = tuple(
        item
        for item in eligible
        if storage_state.bar_count_for(item.session_date) == 0
    )
    reconciliation = eligible[-reconciliation_sessions:]
    reconciliation_dates = set(_session_dates(reconciliation))
    work = tuple(
        EODDataExchangeWork(
            exchange=resolved_policy.exchange,
            effective_date=item.session_date,
            reason=(
                EODDataExchangeWorkReason.ELIGIBLE_MISSING_SESSION
                if storage_state.bar_count_for(item.session_date) == 0
                else EODDataExchangeWorkReason.RECENT_RECONCILIATION
            ),
            stored_bar_count=storage_state.bar_count_for(item.session_date),
        )
        for item in eligible
        if storage_state.bar_count_for(item.session_date) == 0
        or item.session_date in reconciliation_dates
    )
    return EODDataExchangeDailyPlan(
        exchange=resolved_policy.exchange,
        policy_code=policy.code,
        status=EODDataExchangePlanStatus.PLANNED,
        total_listing_count=storage_state.total_listing_count,
        active_listing_count=storage_state.active_listing_count,
        expected_sessions=expected,
        eligible_sessions=eligible,
        missing_sessions=missing,
        reconciliation_sessions=reconciliation,
        work=work,
    )


def _exchanges(values: object) -> None:
    if values != DEFAULT_EODDATA_EXCHANGES:
        raise ValueError("exchanges must use configured EODData exchange order.")


def _reconciliation_sessions(value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_EODDATA_RECONCILIATION_SESSIONS
    ):
        raise ValueError("reconciliation_sessions must be between 1 and 30.")


def _date_range(start_date: date, end_date: date) -> None:
    _date("start_date", start_date)
    _date("end_date", end_date)
    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date.")


def _date(field_name: str, value: object) -> None:
    if type(value) is not date:
        raise TypeError(f"{field_name} must be a date.")


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("now must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware.")
    return value.astimezone(UTC)


def _required_text(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty trimmed text.")


def _nonnegative_integer(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")


def _values(field_name: str, values: object, value_type: type[object]) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(item, value_type) for item in values
    ):
        raise TypeError(f"{field_name} contains invalid values.")


def _ordered_session_dates(
    field_name: str,
    sessions: tuple[ExpectedSession, ...],
) -> None:
    dates = _session_dates(sessions)
    if dates != tuple(sorted(dates)) or len(dates) != len(set(dates)):
        raise ValueError(f"{field_name} must have unique ordered dates.")


def _session_dates(sessions: tuple[ExpectedSession, ...]) -> tuple[date, ...]:
    return tuple(item.session_date for item in sessions)
