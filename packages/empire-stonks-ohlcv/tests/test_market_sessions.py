from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, time

import pytest

from empire_stonks_ohlcv import (
    CalendarSchedule,
    CalendarSession,
    EligibilityRule,
    ExpectedSession,
    MarketSessionService,
    OHLCVCalendarError,
    PandasMarketCalendarProvider,
    SessionDateRule,
    SessionPolicy,
)


def _close_policy(
    *,
    code: str = "US_CASH",
    calendar_name: str = "XNYS",
    timezone_name: str = "America/New_York",
    delay_minutes: int = 90,
) -> SessionPolicy:
    return SessionPolicy(
        code=code,
        calendar_name=calendar_name,
        timezone_name=timezone_name,
        eligibility_rule=EligibilityRule.SESSION_CLOSE,
        cutoff_local_time=None,
        availability_delay_minutes=delay_minutes,
        session_date_rule=SessionDateRule.CALENDAR_SESSION,
    )


def _cutoff_policy(
    *,
    code: str = "YAHOO_FUTURES",
    calendar_name: str | None = "CME_Equity",
    timezone_name: str = "America/New_York",
    cutoff_local_time: time = time(22),
    delay_minutes: int = 0,
    date_rule: SessionDateRule = SessionDateRule.PROVIDER_DAILY_SETTLEMENT,
) -> SessionPolicy:
    return SessionPolicy(
        code=code,
        calendar_name=calendar_name,
        timezone_name=timezone_name,
        eligibility_rule=EligibilityRule.LOCAL_CUTOFF,
        cutoff_local_time=cutoff_local_time,
        availability_delay_minutes=delay_minutes,
        session_date_rule=date_rule,
    )


class _FakeCalendarProvider:
    def __init__(self, schedule: CalendarSchedule) -> None:
        self.schedule_result = schedule
        self.calls: list[tuple[str, date, date]] = []

    def schedule(
        self,
        *,
        calendar_name: str,
        start_date: date,
        end_date: date,
    ) -> CalendarSchedule:
        self.calls.append((calendar_name, start_date, end_date))
        return self.schedule_result


def test_policy_and_session_values_are_immutable_and_normalize_to_utc() -> None:
    policy = _close_policy()
    session = CalendarSession(
        session_date=date(2026, 1, 2),
        close_at=datetime(2026, 1, 2, 16, tzinfo=UTC),
    )

    with pytest.raises(FrozenInstanceError):
        policy.code = "OTHER"  # type: ignore[misc]

    assert session.close_at == datetime(2026, 1, 2, 16, tzinfo=UTC)
    assert policy.availability_delay.total_seconds() == 90 * 60


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"code": "lower"}, "uppercase"),
        ({"calendar_name": None}, "requires calendar_name"),
        ({"cutoff_local_time": time(17)}, "forbids cutoff_local_time"),
        (
            {"session_date_rule": SessionDateRule.PROVIDER_LOCAL_DATE},
            "requires CALENDAR_SESSION",
        ),
        ({"availability_delay_minutes": -1}, "from 0 through"),
        ({"timezone_name": "Mars/Olympus"}, "Unknown IANA"),
    ],
)
def test_session_close_policy_rejects_invalid_configuration(
    changes: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "code": "US_CASH",
        "calendar_name": "XNYS",
        "timezone_name": "America/New_York",
        "eligibility_rule": EligibilityRule.SESSION_CLOSE,
        "cutoff_local_time": None,
        "availability_delay_minutes": 90,
        "session_date_rule": SessionDateRule.CALENDAR_SESSION,
    }
    values.update(changes)

    with pytest.raises((TypeError, ValueError), match=message):
        SessionPolicy(**values)  # type: ignore[arg-type]


def test_calendar_schedule_rejects_duplicate_or_unordered_labels() -> None:
    first = CalendarSession(date(2026, 1, 2), datetime(2026, 1, 2, 21, tzinfo=UTC))
    second = CalendarSession(
        date(2026, 1, 5),
        datetime(2026, 1, 5, 21, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="ordered"):
        CalendarSchedule("XNYS", "America/New_York", (second, first))
    with pytest.raises(ValueError, match="unique"):
        CalendarSchedule("XNYS", "America/New_York", (first, first))


def test_expected_sessions_apply_close_delay_and_early_close() -> None:
    service = MarketSessionService()

    sessions = service.expected_sessions(
        policy=_close_policy(),
        start_date=date(2024, 7, 3),
        end_date=date(2024, 7, 5),
    )

    assert sessions == (
        ExpectedSession(
            date(2024, 7, 3),
            datetime(2024, 7, 3, 18, 30, tzinfo=UTC),
        ),
        ExpectedSession(
            date(2024, 7, 5),
            datetime(2024, 7, 5, 21, 30, tzinfo=UTC),
        ),
    )


def test_calendars_honor_disjoint_country_holidays() -> None:
    adapter = PandasMarketCalendarProvider()

    us_independence_day = adapter.schedule(
        calendar_name="XNYS",
        start_date=date(2024, 7, 4),
        end_date=date(2024, 7, 4),
    )
    london_on_us_holiday = adapter.schedule(
        calendar_name="XLON",
        start_date=date(2024, 7, 4),
        end_date=date(2024, 7, 4),
    )
    london_boxing_day = adapter.schedule(
        calendar_name="XLON",
        start_date=date(2024, 12, 26),
        end_date=date(2024, 12, 26),
    )
    us_on_boxing_day = adapter.schedule(
        calendar_name="XNYS",
        start_date=date(2024, 12, 26),
        end_date=date(2024, 12, 26),
    )
    tokyo_on_christmas = adapter.schedule(
        calendar_name="XTKS",
        start_date=date(2024, 12, 25),
        end_date=date(2024, 12, 25),
    )

    assert us_independence_day.sessions == ()
    assert tuple(item.session_date for item in london_on_us_holiday.sessions) == (
        date(2024, 7, 4),
    )
    assert london_boxing_day.sessions == ()
    assert tuple(item.session_date for item in us_on_boxing_day.sessions) == (
        date(2024, 12, 26),
    )
    assert tuple(item.session_date for item in tokyo_on_christmas.sessions) == (
        date(2024, 12, 25),
    )


def test_session_close_tracks_both_sides_of_us_dst_change() -> None:
    sessions = MarketSessionService().expected_sessions(
        policy=_close_policy(delay_minutes=0),
        start_date=date(2026, 3, 6),
        end_date=date(2026, 3, 9),
    )

    assert sessions == (
        ExpectedSession(
            date(2026, 3, 6),
            datetime(2026, 3, 6, 21, tzinfo=UTC),
        ),
        ExpectedSession(
            date(2026, 3, 9),
            datetime(2026, 3, 9, 20, tzinfo=UTC),
        ),
    )


def test_eligible_missing_sessions_are_ordered_idempotent_and_due_only() -> None:
    provider = _FakeCalendarProvider(
        CalendarSchedule(
            "XNYS",
            "America/New_York",
            (
                CalendarSession(
                    date(2026, 1, 2),
                    datetime(2026, 1, 2, 21, tzinfo=UTC),
                ),
                CalendarSession(
                    date(2026, 1, 5),
                    datetime(2026, 1, 5, 21, tzinfo=UTC),
                ),
                CalendarSession(
                    date(2026, 1, 6),
                    datetime(2026, 1, 6, 21, tzinfo=UTC),
                ),
            ),
        )
    )
    service = MarketSessionService(provider)
    arguments = {
        "policy": _close_policy(),
        "start_date": date(2026, 1, 2),
        "end_date": date(2026, 1, 6),
        "now": datetime(2026, 1, 6, 20, tzinfo=UTC),
    }

    first_run = service.eligible_missing_sessions(
        **arguments,
        stored_session_dates=(date(2026, 1, 2),),
    )
    completed_rerun = service.eligible_missing_sessions(
        **arguments,
        stored_session_dates=(date(2026, 1, 2), date(2026, 1, 5)),
    )

    assert tuple(item.session_date for item in first_run) == (date(2026, 1, 5),)
    assert completed_rerun == ()


def test_observed_only_publisher_cutoff_never_fabricates_expected_sessions() -> None:
    policy = _cutoff_policy(
        code="YAHOO_PUBLISHER",
        calendar_name=None,
        cutoff_local_time=time(17),
        delay_minutes=240,
        date_rule=SessionDateRule.PROVIDER_LOCAL_DATE,
    )
    service = MarketSessionService()

    assert service.expected_sessions(
        policy=policy,
        start_date=date(2026, 7, 3),
        end_date=date(2026, 7, 5),
    ) == ()
    assert service.eligible_missing_sessions(
        policy=policy,
        start_date=date(2026, 7, 3),
        end_date=date(2026, 7, 5),
        stored_session_dates=(),
        now=datetime(2026, 7, 6, tzinfo=UTC),
    ) == ()

    weekend_candidate = service.observed_poll_candidate(
        policy=policy,
        candidate_date=date(2026, 7, 4),
    )
    assert weekend_candidate.poll_at == datetime(
        2026,
        7,
        5,
        1,
        tzinfo=UTC,
    )
    assert not weekend_candidate.is_eligible(
        datetime(2026, 7, 5, 0, 59, tzinfo=UTC)
    )
    assert weekend_candidate.is_eligible(
        datetime(2026, 7, 5, 1, tzinfo=UTC)
    )


def test_dxy_cutoff_crosses_utc_date_without_creating_a_session() -> None:
    policy = _cutoff_policy(
        code="YAHOO_DXY",
        calendar_name=None,
        cutoff_local_time=time(17),
        delay_minutes=120,
        date_rule=SessionDateRule.PROVIDER_LOCAL_DATE,
    )

    candidate = MarketSessionService().observed_poll_candidate(
        policy=policy,
        candidate_date=date(2026, 1, 5),
    )

    assert candidate.candidate_date == date(2026, 1, 5)
    assert candidate.poll_at == datetime(2026, 1, 6, tzinfo=UTC)


def test_futures_cutoff_uses_session_label_and_daily_settlement_rule() -> None:
    provider = _FakeCalendarProvider(
        CalendarSchedule(
            "CME_Equity",
            "America/Chicago",
            (
                CalendarSession(
                    date(2026, 7, 6),
                    datetime(2026, 7, 6, 21, tzinfo=UTC),
                ),
            ),
        )
    )
    service = MarketSessionService(provider)
    policy = _cutoff_policy()

    assert service.expected_sessions(
        policy=policy,
        start_date=date(2026, 7, 6),
        end_date=date(2026, 7, 6),
    ) == (
        ExpectedSession(
            date(2026, 7, 6),
            datetime(2026, 7, 7, 2, tzinfo=UTC),
        ),
    )
    assert service.provider_session_date(
        policy=policy,
        provider_timestamp=datetime(2026, 7, 7, 2, tzinfo=UTC),
        expected_session_dates=(date(2026, 7, 6),),
    ) == date(2026, 7, 6)

    with pytest.raises(OHLCVCalendarError, match="expected session"):
        service.provider_session_date(
            policy=policy,
            provider_timestamp=datetime(2026, 7, 8, 2, tzinfo=UTC),
            expected_session_dates=(date(2026, 7, 6),),
        )


@pytest.mark.parametrize(
    ("candidate_date", "cutoff"),
    [
        (date(2026, 3, 8), time(2, 30)),
        (date(2026, 11, 1), time(1, 30)),
    ],
)
def test_local_cutoff_rejects_nonexistent_or_ambiguous_wall_time(
    candidate_date: date,
    cutoff: time,
) -> None:
    policy = _cutoff_policy(
        calendar_name=None,
        cutoff_local_time=cutoff,
    )

    with pytest.raises(OHLCVCalendarError, match="ambiguous or nonexistent"):
        MarketSessionService().observed_poll_candidate(
            policy=policy,
            candidate_date=candidate_date,
        )


def test_unknown_calendar_fails_closed() -> None:
    with pytest.raises(OHLCVCalendarError, match="could not be resolved"):
        MarketSessionService().expected_sessions(
            policy=_close_policy(calendar_name="NOT_A_REAL_CALENDAR"),
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 2),
        )


def test_session_close_rejects_calendar_timezone_mismatch() -> None:
    provider = _FakeCalendarProvider(
        CalendarSchedule(
            "XNYS",
            "Asia/Tokyo",
            (
                CalendarSession(
                    date(2026, 1, 2),
                    datetime(2026, 1, 2, 21, tzinfo=UTC),
                ),
            ),
        )
    )

    with pytest.raises(OHLCVCalendarError, match="timezone does not match"):
        MarketSessionService(provider).expected_sessions(
            policy=_close_policy(),
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 2),
        )


def test_calendar_provider_cannot_substitute_another_calendar() -> None:
    provider = _FakeCalendarProvider(
        CalendarSchedule("XLON", "Europe/London", ())
    )

    with pytest.raises(OHLCVCalendarError, match="different calendar identity"):
        MarketSessionService(provider).expected_sessions(
            policy=_close_policy(),
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 2),
        )


def test_calendar_adapter_rejects_unreviewed_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _WarningCalendar:
        tz = "UTC"

        def schedule(self, **_: object) -> object:
            import warnings

            warnings.warn("calendar behavior changed", UserWarning)
            return _EmptyFrame()

    class _EmptyFrame:
        columns = ("market_close",)

        @staticmethod
        def iterrows() -> tuple[()]:
            return ()

    monkeypatch.setattr(
        "empire_stonks_ohlcv.market_sessions.market_calendars.get_calendar",
        lambda _: _WarningCalendar(),
    )

    with pytest.raises(OHLCVCalendarError, match="unsafe warning"):
        PandasMarketCalendarProvider().schedule(
            calendar_name="TEST",
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 2),
        )


def test_calendar_adapter_allows_reviewed_library_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _WarningCalendar:
        tz = "UTC"

        def schedule(self, **_: object) -> object:
            import warnings

            warnings.warn(
                "['break_start', 'break_end'] are discontinued",
                UserWarning,
            )
            return _EmptyFrame()

    class _EmptyFrame:
        columns = ("market_close",)

        @staticmethod
        def iterrows() -> tuple[()]:
            return ()

    monkeypatch.setattr(
        "empire_stonks_ohlcv.market_sessions.market_calendars.get_calendar",
        lambda _: _WarningCalendar(),
    )

    schedule = PandasMarketCalendarProvider().schedule(
        calendar_name="TEST",
        start_date=date(2026, 1, 2),
        end_date=date(2026, 1, 2),
    )

    assert schedule == CalendarSchedule("TEST", "UTC", ())


def test_naive_now_and_provider_timestamp_are_rejected() -> None:
    service = MarketSessionService(
        _FakeCalendarProvider(
            CalendarSchedule("XNYS", "America/New_York", ())
        )
    )
    policy = _close_policy()

    with pytest.raises(ValueError, match="timezone-aware"):
        service.eligible_sessions(
            policy=policy,
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 2),
            now=datetime(2026, 1, 2),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        service.provider_session_date(
            policy=policy,
            provider_timestamp=datetime(2026, 1, 2),
            expected_session_dates=(),
        )
