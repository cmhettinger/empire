from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from empire_stonks_ohlcv import (
    ExpectedSession,
    ObservedPollCandidate,
    YahooAcquisitionRequest,
    YahooCompletenessStatus,
    YahooDailyCompletenessPlan,
    YahooDailyPull,
    YahooListingCompletenessPlan,
    YahooListingTarget,
    YahooPullReason,
    YahooRequestMode,
    build_yahoo_recent_reconciliation_plan,
)


def _target(index: int, ticker: str) -> YahooListingTarget:
    return YahooListingTarget(
        provider_listing_id=UUID(int=index),
        ticker=ticker,
        yahoo_ticker=f"^{ticker}",
    )


def _expected(day: int, eligible_hour: int = 21) -> ExpectedSession:
    return ExpectedSession(
        session_date=date(2026, 7, day),
        eligible_at=datetime(2026, 7, day, eligible_hour, tzinfo=UTC),
    )


def _pull(
    target: YahooListingTarget,
    day: int,
    reason: YahooPullReason,
) -> YahooDailyPull:
    return YahooDailyPull(
        request=YahooAcquisitionRequest(
            listing=target,
            start_date=date(2026, 7, day),
            end_date_exclusive=date(2026, 7, day + 1),
            mode=YahooRequestMode.DAILY,
        ),
        reason=reason,
        planned_dates=(date(2026, 7, day),),
    )


def _completeness_plan() -> YahooDailyCompletenessPlan:
    dxy_target = _target(1, "DXY")
    dxy = YahooListingCompletenessPlan(
        listing=dxy_target,
        policy_code="YH_DXY_CUTOFF_120M",
        status=YahooCompletenessStatus.PLANNED,
        observed_only=True,
        stored_session_dates=(
            date(2026, 7, 1),
            date(2026, 7, 2),
            date(2026, 7, 3),
        ),
        observed_poll_candidates=(
            ObservedPollCandidate(
                candidate_date=date(2026, 7, 4),
                poll_at=datetime(2026, 7, 5, 1, tzinfo=UTC),
            ),
        ),
        pulls=(
            _pull(dxy_target, 4, YahooPullReason.DUE_OBSERVED_POLL),
        ),
    )
    expected = tuple(_expected(day) for day in range(1, 6))
    eligible = expected[:4]
    spx_target = _target(2, "SPX")
    spx = YahooListingCompletenessPlan(
        listing=spx_target,
        policy_code="YH_XNYS_CLOSE_90M",
        status=YahooCompletenessStatus.PLANNED,
        observed_only=False,
        stored_session_dates=(
            date(2026, 7, 1),
            date(2026, 7, 2),
            date(2026, 7, 4),
        ),
        expected_sessions=expected,
        eligible_sessions=eligible,
        missing_sessions=(_expected(3),),
        pulls=(
            _pull(
                spx_target,
                3,
                YahooPullReason.ELIGIBLE_MISSING_SESSION,
            ),
        ),
    )
    return YahooDailyCompletenessPlan(
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
        planned_at=datetime(2026, 7, 5, tzinfo=UTC),
        enumerated_listing_count=93,
        listings=(dxy, spx),
    )


def test_reconciliation_selects_recent_sessions_including_stored_and_missing() -> None:
    plan = build_yahoo_recent_reconciliation_plan(
        completeness_plan=_completeness_plan(),
        session_count=3,
        max_request_days=10,
    )

    assert plan.listings[1].selected_dates == (
        date(2026, 7, 2),
        date(2026, 7, 3),
        date(2026, 7, 4),
    )
    assert plan.listings[1].pulls[0].reason is (
        YahooPullReason.RECENT_RECONCILIATION
    )
    assert plan.listings[1].pulls[0].request.start_date == date(2026, 7, 2)
    assert plan.listings[1].pulls[0].request.end_date_exclusive == date(
        2026, 7, 5
    )
    assert date(2026, 7, 5) not in plan.listings[1].selected_dates


def test_observed_reconciliation_uses_recent_stored_dates_plus_due_poll() -> None:
    plan = build_yahoo_recent_reconciliation_plan(
        completeness_plan=_completeness_plan(),
        session_count=2,
        max_request_days=10,
    )

    observed = plan.listings[0]
    assert observed.observed_only
    assert observed.selected_dates == (
        date(2026, 7, 2),
        date(2026, 7, 3),
        date(2026, 7, 4),
    )
    assert observed.pulls[0].planned_dates == observed.selected_dates


def test_reconciliation_respects_source_request_bound() -> None:
    plan = build_yahoo_recent_reconciliation_plan(
        completeness_plan=_completeness_plan(),
        session_count=4,
        max_request_days=2,
    )

    spx = plan.listings[1]
    assert [item.planned_dates for item in spx.pulls] == [
        (date(2026, 7, 1), date(2026, 7, 2)),
        (date(2026, 7, 3), date(2026, 7, 4)),
    ]
    assert all(item.request.day_count <= 2 for item in spx.pulls)


def test_reconciliation_session_count_obeys_operator_safety_bound() -> None:
    with pytest.raises(ValueError, match="safety bound"):
        build_yahoo_recent_reconciliation_plan(
            completeness_plan=_completeness_plan(),
            session_count=31,
            max_request_days=10,
        )
