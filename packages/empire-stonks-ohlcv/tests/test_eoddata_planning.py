from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from empire_stonks_ohlcv import (
    EODDataExchangePlanStatus,
    EODDataExchangeSessionPolicy,
    EODDataExchangeStorage,
    EODDataExchangeWorkReason,
    EODDataPlanningFailureReason,
    EODDataStoredSessionCount,
    EligibilityRule,
    ExpectedSession,
    OHLCVCalendarError,
    SessionDateRule,
    SessionPolicy,
    build_eoddata_exchange_plan,
    select_eoddata_exchange_storage,
)


EXCHANGES = ("NYSE", "NASDAQ", "AMEX")


class StaticSessionService:
    def __init__(
        self,
        schedules: dict[str, tuple[ExpectedSession, ...] | Exception],
    ) -> None:
        self.schedules = schedules
        self.calls: list[str] = []

    def expected_sessions(
        self,
        *,
        policy: SessionPolicy,
        start_date: date,
        end_date: date,
    ) -> tuple[ExpectedSession, ...]:
        del start_date, end_date
        assert policy.calendar_name is not None
        self.calls.append(policy.calendar_name)
        result = self.schedules[policy.calendar_name]
        if isinstance(result, Exception):
            raise result
        return result


class RangeAwareSessionService:
    def __init__(self, sessions: tuple[ExpectedSession, ...]) -> None:
        self.sessions = sessions

    def expected_sessions(
        self,
        *,
        policy: SessionPolicy,
        start_date: date,
        end_date: date,
    ) -> tuple[ExpectedSession, ...]:
        del policy
        return tuple(
            item
            for item in self.sessions
            if start_date <= item.session_date <= end_date
        )


class StorageCursor:
    def __init__(
        self,
        listing_rows: list[tuple[object, ...]],
        bar_rows: list[tuple[object, ...]],
    ) -> None:
        self.results = [listing_rows, bar_rows]
        self.queries: list[str] = []
        self.params: list[tuple[object, ...]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.queries.append(query)
        self.params.append(params)

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.results.pop(0)


def _policy(
    exchange: str,
    code: str,
    calendar_name: str,
) -> EODDataExchangeSessionPolicy:
    return EODDataExchangeSessionPolicy(
        exchange=exchange,
        policy=SessionPolicy(
            code=code,
            calendar_name=calendar_name,
            timezone_name="America/New_York",
            eligibility_rule=EligibilityRule.LOCAL_CUTOFF,
            cutoff_local_time=time(19),
            availability_delay_minutes=60,
            session_date_rule=SessionDateRule.PROVIDER_LOCAL_DATE,
        ),
    )


def _policies() -> tuple[EODDataExchangeSessionPolicy, ...]:
    return (
        _policy("NYSE", "ED_XNYS_1900_60M", "XNYS"),
        _policy("NASDAQ", "ED_XNAS_1900_60M", "NASDAQ"),
        _policy("AMEX", "ED_XNYS_1900_60M", "XNYS"),
    )


def _session(day: int, *, eligible_hour: int = 0) -> ExpectedSession:
    session_date = date(2026, 7, day)
    return ExpectedSession(
        session_date=session_date,
        eligible_at=datetime(
            2026,
            7,
            day + 1,
            eligible_hour,
            tzinfo=UTC,
        ),
    )


def _stored(
    exchange: str,
    counts: dict[int, int],
    *,
    total: int = 10,
    active: int = 9,
) -> EODDataExchangeStorage:
    return EODDataExchangeStorage(
        exchange=exchange,
        total_listing_count=total,
        active_listing_count=active,
        stored_sessions=tuple(
            EODDataStoredSessionCount(
                session_date=date(2026, 7, day),
                bar_count=count,
            )
            for day, count in sorted(counts.items())
        ),
    )


def test_skips_old_complete_and_plans_missing_plus_recent_reconciliation() -> None:
    sessions = tuple(_session(day) for day in range(1, 6))
    service = StaticSessionService({"XNYS": sessions, "NASDAQ": sessions})
    storage = (
        _stored("NYSE", {1: 100, 2: 101, 3: 102, 4: 103, 5: 104}),
        _stored("NASDAQ", {1: 200, 4: 203, 5: 204}),
        _stored("AMEX", {}, total=3, active=0),
    )

    first = build_eoddata_exchange_plan(
        policies=_policies(),
        storage=storage,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
        now=datetime(2026, 7, 7, tzinfo=UTC),
        reconciliation_sessions=2,
        session_service=service,  # type: ignore[arg-type]
    )
    second = build_eoddata_exchange_plan(
        policies=_policies(),
        storage=storage,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
        now=datetime(2026, 7, 7, tzinfo=UTC),
        reconciliation_sessions=2,
        session_service=service,  # type: ignore[arg-type]
    )

    assert first == second
    nyse, nasdaq, amex = first.exchanges
    assert tuple(item.effective_date for item in nyse.work) == (
        date(2026, 7, 4),
        date(2026, 7, 5),
    )
    assert all(
        item.reason is EODDataExchangeWorkReason.RECENT_RECONCILIATION
        for item in nyse.work
    )
    assert tuple(item.session_date for item in nasdaq.missing_sessions) == (
        date(2026, 7, 2),
        date(2026, 7, 3),
    )
    assert tuple(
        (item.effective_date, item.reason) for item in nasdaq.work
    ) == (
        (
            date(2026, 7, 2),
            EODDataExchangeWorkReason.ELIGIBLE_MISSING_SESSION,
        ),
        (
            date(2026, 7, 3),
            EODDataExchangeWorkReason.ELIGIBLE_MISSING_SESSION,
        ),
        (
            date(2026, 7, 4),
            EODDataExchangeWorkReason.RECENT_RECONCILIATION,
        ),
        (
            date(2026, 7, 5),
            EODDataExchangeWorkReason.RECENT_RECONCILIATION,
        ),
    )
    assert amex.status is EODDataExchangePlanStatus.INACTIVE
    assert amex.work == ()
    assert nyse.latest_expected_is_eligible
    assert nyse.latest_expected_is_complete
    assert nyse.latest_eligible_is_complete
    assert first.inactive_exchange_count == 1
    assert first.failed_exchange_count == 0


def test_ineligible_latest_session_is_never_missing_or_requested() -> None:
    sessions = (_session(1), _session(2, eligible_hour=1))
    service = StaticSessionService({"XNYS": sessions, "NASDAQ": sessions})
    storage = tuple(_stored(exchange, {1: 5}) for exchange in EXCHANGES)

    plan = build_eoddata_exchange_plan(
        policies=_policies(),
        storage=storage,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        now=datetime(2026, 7, 3, 0, 30, tzinfo=UTC),
        reconciliation_sessions=1,
        session_service=service,  # type: ignore[arg-type]
    )

    for exchange in plan.exchanges:
        assert not exchange.latest_expected_is_eligible
        assert not exchange.latest_expected_is_complete
        assert exchange.ineligible_session_count == 1
        assert exchange.missing_sessions == ()
        assert tuple(item.effective_date for item in exchange.work) == (
            date(2026, 7, 1),
        )


def test_completed_historical_sessions_outside_recent_window_are_skipped() -> None:
    service = RangeAwareSessionService(
        tuple(_session(day) for day in (1, 2, 8, 9))
    )
    storage = (
        _stored("NYSE", {1: 5, 2: 5}),
        _stored("NASDAQ", {2: 5}),
        _stored("AMEX", {1: 5, 2: 5}),
    )

    plan = build_eoddata_exchange_plan(
        policies=_policies(),
        storage=storage,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        now=datetime(2026, 7, 10, 2, tzinfo=UTC),
        reconciliation_sessions=2,
        session_service=service,  # type: ignore[arg-type]
    )

    assert plan.exchanges[0].work == ()
    assert tuple(item.effective_date for item in plan.exchanges[1].work) == (
        date(2026, 7, 1),
    )
    assert plan.exchanges[1].work[0].reason is (
        EODDataExchangeWorkReason.ELIGIBLE_MISSING_SESSION
    )
    assert plan.exchanges[2].work == ()


def test_different_calendars_can_disagree_on_the_same_date() -> None:
    only_nasdaq = (_session(3),)
    service = StaticSessionService({"XNYS": (), "NASDAQ": only_nasdaq})
    storage = tuple(_stored(exchange, {}) for exchange in EXCHANGES)

    plan = build_eoddata_exchange_plan(
        policies=_policies(),
        storage=storage,
        start_date=date(2026, 7, 3),
        end_date=date(2026, 7, 3),
        now=datetime(2026, 7, 5, tzinfo=UTC),
        reconciliation_sessions=1,
        session_service=service,  # type: ignore[arg-type]
    )

    assert plan.exchanges[0].work == ()
    assert tuple(item.effective_date for item in plan.exchanges[1].work) == (
        date(2026, 7, 3),
    )
    assert plan.exchanges[2].work == ()


def test_calendar_failure_is_isolated_to_affected_policy() -> None:
    service = StaticSessionService(
        {
            "XNYS": (_session(1),),
            "NASDAQ": OHLCVCalendarError("unsafe calendar"),
        }
    )
    storage = tuple(_stored(exchange, {}) for exchange in EXCHANGES)

    plan = build_eoddata_exchange_plan(
        policies=_policies(),
        storage=storage,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
        now=datetime(2026, 7, 3, tzinfo=UTC),
        reconciliation_sessions=1,
        session_service=service,  # type: ignore[arg-type]
    )

    assert plan.failed_exchange_count == 1
    assert plan.exchanges[1].status is EODDataExchangePlanStatus.FAILED
    assert plan.exchanges[1].failure_reason is (
        EODDataPlanningFailureReason.CALENDAR_POLICY
    )
    assert plan.exchanges[0].work
    assert plan.exchanges[2].work


def test_real_calendars_preserve_dst_holiday_and_early_close_eligibility() -> None:
    empty_storage = tuple(_stored(exchange, {}) for exchange in EXCHANGES)
    dst = build_eoddata_exchange_plan(
        policies=_policies(),
        storage=empty_storage,
        start_date=date(2026, 3, 6),
        end_date=date(2026, 3, 9),
        now=datetime(2026, 3, 9, 23, 59, tzinfo=UTC),
        reconciliation_sessions=2,
    )

    assert all(
        tuple(item.effective_date for item in exchange.work)
        == (date(2026, 3, 6),)
        for exchange in dst.exchanges
    )
    assert all(exchange.ineligible_session_count == 1 for exchange in dst.exchanges)

    holiday = build_eoddata_exchange_plan(
        policies=_policies(),
        storage=empty_storage,
        start_date=date(2026, 11, 26),
        end_date=date(2026, 11, 27),
        now=datetime(2026, 11, 28, 2, tzinfo=UTC),
        reconciliation_sessions=2,
    )

    assert all(
        tuple(item.session_date for item in exchange.expected_sessions)
        == (date(2026, 11, 27),)
        for exchange in holiday.exchanges
    )
    assert all(
        exchange.expected_sessions[0].eligible_at.isoformat()
        == "2026-11-28T01:00:00+00:00"
        for exchange in holiday.exchanges
    )


def test_storage_query_returns_zero_state_and_active_bar_counts() -> None:
    cursor = StorageCursor(
        listing_rows=[
            ("NASDAQ", 12, 10),
            ("NYSE", 8, 8),
        ],
        bar_rows=[
            ("NASDAQ", date(2026, 7, 1), 9),
            ("NYSE", date(2026, 7, 1), 8),
        ],
    )

    result = select_eoddata_exchange_storage(
        cursor=cursor,
        exchanges=EXCHANGES,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
    )

    assert tuple(item.exchange for item in result) == EXCHANGES
    assert result[0].total_listing_count == 8
    assert result[1].active_listing_count == 10
    assert result[2].total_listing_count == 0
    assert result[2].active_listing_count == 0
    assert result[2].stored_sessions == ()
    assert cursor.params == [
        ("EODDATA", ["NYSE", "NASDAQ", "AMEX"]),
        (
            "EODDATA",
            ["NYSE", "NASDAQ", "AMEX"],
            date(2026, 7, 1),
            date(2026, 7, 2),
        ),
    ]


@pytest.mark.parametrize("value", (0, 31, True))
def test_reconciliation_window_is_bounded(value: object) -> None:
    with pytest.raises(ValueError, match="between 1 and 30"):
        build_eoddata_exchange_plan(
            policies=_policies(),
            storage=tuple(_stored(exchange, {}) for exchange in EXCHANGES),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            now=datetime(2026, 7, 3, tzinfo=UTC),
            reconciliation_sessions=value,  # type: ignore[arg-type]
        )
