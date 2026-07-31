from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest

from empire_stonks_ohlcv import (
    CalendarSchedule,
    CalendarSession,
    EligibilityRule,
    MarketSessionService,
    OHLCVCalendarError,
    ProviderListing,
    SeededYahooListing,
    SessionDateRule,
    SessionPolicy,
    YahooCompletenessStatus,
    YahooListingTarget,
    YahooPullReason,
    build_yahoo_daily_completeness_plan,
    select_yahoo_stored_session_dates,
)


class _CalendarProvider:
    def __init__(self, schedules: dict[str, CalendarSchedule]) -> None:
        self.schedules = schedules
        self.calls: list[tuple[str, date, date]] = []

    def schedule(
        self,
        *,
        calendar_name: str,
        start_date: date,
        end_date: date,
    ) -> CalendarSchedule:
        self.calls.append((calendar_name, start_date, end_date))
        try:
            return self.schedules[calendar_name]
        except KeyError as exc:
            raise OHLCVCalendarError("unknown test calendar") from exc


class _StoredDateCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.query = ""
        self.params: tuple[object, ...] = ()

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.query = query
        self.params = params

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


def _policy(
    *,
    code: str,
    calendar_name: str | None,
    timezone_name: str,
    cutoff: time | None = None,
    delay_minutes: int = 0,
) -> SessionPolicy:
    observed_or_futures = cutoff is not None
    return SessionPolicy(
        code=code,
        calendar_name=calendar_name,
        timezone_name=timezone_name,
        eligibility_rule=(
            EligibilityRule.LOCAL_CUTOFF
            if observed_or_futures
            else EligibilityRule.SESSION_CLOSE
        ),
        cutoff_local_time=cutoff,
        availability_delay_minutes=delay_minutes,
        session_date_rule=(
            SessionDateRule.PROVIDER_DAILY_SETTLEMENT
            if observed_or_futures and calendar_name is not None
            else SessionDateRule.PROVIDER_LOCAL_DATE
            if observed_or_futures
            else SessionDateRule.CALENDAR_SESSION
        ),
    )


def _seed(
    index: int,
    ticker: str,
    policy: SessionPolicy,
) -> SeededYahooListing:
    target = YahooListingTarget(
        provider_listing_id=UUID(int=index),
        ticker=ticker,
        yahoo_ticker=f"^{ticker}",
    )
    return SeededYahooListing(
        target=target,
        listing=ProviderListing(
            provider_code="YAHOO",
            market="XIDX",
            ticker=ticker,
            name=f"{ticker} Test Index",
            instrument_type_code="EQUITY_INDEX",
            metadata={"YahooTicker": f"^{ticker}"},
        ),
        policy=policy,
    )


def _schedule(
    name: str,
    timezone_name: str,
    values: tuple[tuple[date, datetime], ...],
) -> CalendarSchedule:
    return CalendarSchedule(
        calendar_name=name,
        timezone_name=timezone_name,
        sessions=tuple(CalendarSession(*item) for item in values),
    )


def test_plans_only_eligible_missing_sessions_and_completed_rerun_is_noop() -> None:
    policy = _policy(
        code="TEST_XNYS",
        calendar_name="XNYS",
        timezone_name="America/New_York",
        delay_minutes=90,
    )
    seed = _seed(1, "SPX", policy)
    provider = _CalendarProvider(
        {
            "XNYS": _schedule(
                "XNYS",
                "America/New_York",
                (
                    (
                        date(2026, 1, 2),
                        datetime(2026, 1, 2, 21, tzinfo=UTC),
                    ),
                    (
                        date(2026, 1, 5),
                        datetime(2026, 1, 5, 21, tzinfo=UTC),
                    ),
                    (
                        date(2026, 1, 6),
                        datetime(2026, 1, 6, 21, tzinfo=UTC),
                    ),
                ),
            )
        }
    )
    service = MarketSessionService(provider)
    arguments = {
        "listings": (seed,),
        "start_date": date(2026, 1, 2),
        "end_date": date(2026, 1, 6),
        "now": datetime(2026, 1, 6, 20, tzinfo=UTC),
        "max_request_days": 10,
        "session_service": service,
    }

    missing = build_yahoo_daily_completeness_plan(
        **arguments,
        stored_session_dates={UUID(int=1): (date(2026, 1, 2),)},
    )
    completed = build_yahoo_daily_completeness_plan(
        **arguments,
        stored_session_dates={
            UUID(int=1): (date(2026, 1, 2), date(2026, 1, 5))
        },
    )
    before_eligibility = build_yahoo_daily_completeness_plan(
        **{
            **arguments,
            "now": datetime(2026, 1, 2, 22, 29, tzinfo=UTC),
        },
        stored_session_dates={UUID(int=1): ()},
    )

    listing = missing.listings[0]
    assert tuple(item.session_date for item in listing.expected_sessions) == (
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
    )
    assert tuple(item.session_date for item in listing.eligible_sessions) == (
        date(2026, 1, 2),
        date(2026, 1, 5),
    )
    assert tuple(item.session_date for item in listing.missing_sessions) == (
        date(2026, 1, 5),
    )
    assert listing.ineligible_session_count == 1
    assert listing.pulls[0].reason is (
        YahooPullReason.ELIGIBLE_MISSING_SESSION
    )
    assert listing.pulls[0].planned_dates == (date(2026, 1, 5),)
    assert completed.requests == ()
    assert before_eligibility.requests == ()


def test_source_bound_splits_an_expected_session_run() -> None:
    policy = _policy(
        code="TEST_XNYS",
        calendar_name="XNYS",
        timezone_name="America/New_York",
    )
    seed = _seed(1, "SPX", policy)
    provider = _CalendarProvider(
        {
            "XNYS": _schedule(
                "XNYS",
                "America/New_York",
                (
                    (
                        date(2026, 1, 2),
                        datetime(2026, 1, 2, 21, tzinfo=UTC),
                    ),
                    (
                        date(2026, 1, 5),
                        datetime(2026, 1, 5, 21, tzinfo=UTC),
                    ),
                ),
            )
        }
    )

    plan = build_yahoo_daily_completeness_plan(
        listings=(seed,),
        stored_session_dates={},
        start_date=date(2026, 1, 2),
        end_date=date(2026, 1, 5),
        now=datetime(2026, 1, 6, tzinfo=UTC),
        max_request_days=3,
        session_service=MarketSessionService(provider),
    )

    assert [item.planned_dates for item in plan.pulls] == [
        (date(2026, 1, 2),),
        (date(2026, 1, 5),),
    ]
    assert all(item.request.day_count <= 3 for item in plan.pulls)


def test_missing_work_is_deterministic_and_stored_sessions_split_ranges() -> None:
    policy = _policy(
        code="TEST_XNYS",
        calendar_name="XNYS",
        timezone_name="America/New_York",
    )
    seed = _seed(1, "SPX", policy)
    provider = _CalendarProvider(
        {
            "XNYS": _schedule(
                "XNYS",
                "America/New_York",
                (
                    (
                        date(2026, 1, 2),
                        datetime(2026, 1, 2, 21, tzinfo=UTC),
                    ),
                    (
                        date(2026, 1, 5),
                        datetime(2026, 1, 5, 21, tzinfo=UTC),
                    ),
                    (
                        date(2026, 1, 6),
                        datetime(2026, 1, 6, 21, tzinfo=UTC),
                    ),
                ),
            )
        }
    )
    arguments = {
        "listings": (seed,),
        "stored_session_dates": {UUID(int=1): (date(2026, 1, 5),)},
        "start_date": date(2026, 1, 2),
        "end_date": date(2026, 1, 6),
        "now": datetime(2026, 1, 7, tzinfo=UTC),
        "max_request_days": 10,
        "session_service": MarketSessionService(provider),
    }

    first = build_yahoo_daily_completeness_plan(**arguments)
    retry = build_yahoo_daily_completeness_plan(**arguments)

    assert first.pulls == retry.pulls
    assert [item.planned_dates for item in first.pulls] == [
        (date(2026, 1, 2),),
        (date(2026, 1, 6),),
    ]


def test_observed_only_due_dates_are_poll_candidates_not_missing_sessions() -> None:
    policy = _policy(
        code="TEST_DXY",
        calendar_name=None,
        timezone_name="America/New_York",
        cutoff=time(17),
        delay_minutes=120,
    )
    seed = _seed(1, "DXY", policy)

    plan = build_yahoo_daily_completeness_plan(
        listings=(seed,),
        stored_session_dates={UUID(int=1): (date(2026, 7, 3),)},
        start_date=date(2026, 7, 3),
        end_date=date(2026, 7, 5),
        now=datetime(2026, 7, 6, 1, tzinfo=UTC),
        max_request_days=10,
    )

    listing = plan.listings[0]
    assert listing.expected_sessions == ()
    assert listing.missing_sessions == ()
    assert tuple(
        item.candidate_date for item in listing.observed_poll_candidates
    ) == (date(2026, 7, 4), date(2026, 7, 5))
    assert listing.pulls[0].reason is YahooPullReason.DUE_OBSERVED_POLL
    assert listing.pulls[0].planned_dates == (
        date(2026, 7, 4),
        date(2026, 7, 5),
    )


def test_calendar_failure_is_isolated_to_one_listing() -> None:
    bad = _seed(
        1,
        "BAD",
        _policy(
            code="TEST_BAD",
            calendar_name="BAD",
            timezone_name="UTC",
        ),
    )
    good = _seed(
        2,
        "GOOD",
        _policy(
            code="TEST_GOOD",
            calendar_name="GOOD",
            timezone_name="UTC",
        ),
    )
    provider = _CalendarProvider(
        {
            "GOOD": _schedule(
                "GOOD",
                "UTC",
                (
                    (
                        date(2026, 1, 2),
                        datetime(2026, 1, 2, 16, tzinfo=UTC),
                    ),
                ),
            )
        }
    )

    plan = build_yahoo_daily_completeness_plan(
        listings=(bad, good),
        stored_session_dates={},
        start_date=date(2026, 1, 2),
        end_date=date(2026, 1, 2),
        now=datetime(2026, 1, 3, tzinfo=UTC),
        max_request_days=10,
        session_service=MarketSessionService(provider),
    )

    assert plan.listings[0].status is YahooCompletenessStatus.FAILED
    assert plan.listings[0].pulls == ()
    assert plan.listings[1].status is YahooCompletenessStatus.PLANNED
    assert plan.listings[1].pulls[0].planned_dates == (date(2026, 1, 2),)
    assert plan.failed_listing_count == 1


@pytest.mark.parametrize(
    ("ticker", "policy", "session_date"),
    [
        (
            "SPX",
            _policy(
                code="TEST_US",
                calendar_name="XNYS",
                timezone_name="America/New_York",
                delay_minutes=90,
            ),
            date(2024, 7, 5),
        ),
        (
            "FTSE",
            _policy(
                code="TEST_EU",
                calendar_name="XLON",
                timezone_name="Europe/London",
                delay_minutes=120,
            ),
            date(2024, 7, 4),
        ),
        (
            "N225",
            _policy(
                code="TEST_ASIA",
                calendar_name="XTKS",
                timezone_name="Asia/Tokyo",
                delay_minutes=180,
            ),
            date(2024, 12, 25),
        ),
        (
            "ES",
            _policy(
                code="TEST_FUTURES",
                calendar_name="CME_Equity",
                timezone_name="America/New_York",
                cutoff=time(22),
            ),
            date(2026, 7, 6),
        ),
    ],
)
def test_real_calendars_plan_one_pull_per_real_session(
    ticker: str,
    policy: SessionPolicy,
    session_date: date,
) -> None:
    seed = _seed(1, ticker, policy)

    plan = build_yahoo_daily_completeness_plan(
        listings=(seed,),
        stored_session_dates={},
        start_date=session_date,
        end_date=session_date,
        now=datetime(2026, 12, 31, tzinfo=UTC),
        max_request_days=10,
    )

    assert tuple(
        item.session_date for item in plan.listings[0].expected_sessions
    ) == (session_date,)
    assert plan.pulls[0].planned_dates == (session_date,)


def test_stored_date_reader_is_exact_bounded_and_preserves_empty_listings() -> None:
    first = UUID(int=1)
    second = UUID(int=2)
    cursor = _StoredDateCursor(
        [(first, date(2026, 7, 1)), (first, date(2026, 7, 2))]
    )

    result = select_yahoo_stored_session_dates(
        cursor=cursor,
        provider_listing_ids=(first, second),
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
    )

    assert "provider_listing_id = ANY" in cursor.query
    assert cursor.params == (
        [first, second],
        date(2026, 7, 1),
        date(2026, 7, 2),
    )
    assert result == {
        first: (date(2026, 7, 1), date(2026, 7, 2)),
        second: (),
    }
