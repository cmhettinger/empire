from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from empire_stonks_ohlcv.market_sessions import (
    EligibilityRule,
    ExpectedSession,
    ObservedPollCandidate,
    SessionDateRule,
    SessionPolicy,
)
from empire_stonks_ohlcv.models import ProviderListing
from empire_stonks_ohlcv.reports.yahoo_daily_benchmark_pdf import (
    YAHOO_DAILY_BENCHMARK_PDF_REPORT_ID,
    render_yahoo_daily_benchmark_pdf,
)
from empire_stonks_ohlcv.yahoo import YahooListingTarget
from empire_stonks_ohlcv.yahoo_benchmark_reporting import (
    YahooBenchmarkStatus,
    build_yahoo_daily_benchmark_report,
)
from empire_stonks_ohlcv.yahoo_listings import SeededYahooListing


TRADING_DATE = date(2026, 7, 30)
GENERATED_AT = datetime(2026, 7, 31, 3, 0, tzinfo=UTC)


class _Cursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.query = ""
        self.params: tuple[object, ...] = ()

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.query = query
        self.params = params

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class _SessionService:
    def expected_sessions(
        self,
        *,
        policy: SessionPolicy,
        start_date: date,
        end_date: date,
    ) -> tuple[ExpectedSession, ...]:
        assert start_date == end_date == TRADING_DATE
        if policy.code == "CLOSED":
            return ()
        return (
            ExpectedSession(
                session_date=TRADING_DATE,
                eligible_at=datetime(2026, 7, 30, 22, tzinfo=UTC),
            ),
        )

    def observed_poll_candidate(
        self,
        *,
        policy: SessionPolicy,
        candidate_date: date,
    ) -> ObservedPollCandidate:
        assert candidate_date == TRADING_DATE
        return ObservedPollCandidate(
            candidate_date=candidate_date,
            poll_at=datetime(2026, 7, 31, 4, tzinfo=UTC),
        )


def test_builds_active_exact_date_report_with_explicit_missing_states(
    monkeypatch,
) -> None:
    seeds = (
        _seed(1, "DAX", "CLOSED"),
        _seed(2, "DXY", "OBSERVED", observed_only=True),
        _seed(3, "SPX", "OPEN"),
        _seed(4, "VIX", "OPEN"),
    )
    monkeypatch.setattr(
        "empire_stonks_ohlcv.yahoo_benchmark_reporting.select_active_yahoo_listings",
        lambda **_values: seeds,
    )
    cursor = _Cursor(
        [
            (UUID(int=1), None, None, date(2026, 7, 29), Decimal("100"), None, None, None),
            (UUID(int=2), None, None, date(2026, 7, 29), Decimal("90"), None, None, None),
            (
                UUID(int=3),
                Decimal("105"),
                Decimal("10"),
                date(2026, 7, 29),
                Decimal("100"),
                Decimal("101"),
                Decimal("106"),
                Decimal("100"),
            ),
            (UUID(int=4), None, None, date(2026, 7, 29), Decimal("20"), None, None, None),
        ]
    )

    report = build_yahoo_daily_benchmark_report(
        cursor=cursor,
        trading_date=TRADING_DATE,
        generated_at=GENERATED_AT,
        session_service=_SessionService(),  # type: ignore[arg-type]
    )

    rows = {
        row.ticker: row for section in report.sections for row in section.rows
    }
    assert report.active_listing_count == 4
    assert report.reported_count == 1
    assert rows["SPX"].change == Decimal("5")
    assert rows["SPX"].changepct == Decimal("0.05")
    assert rows["DAX"].status is YahooBenchmarkStatus.MARKET_CLOSED
    assert rows["DXY"].status is YahooBenchmarkStatus.NOT_YET_ELIGIBLE
    assert rows["VIX"].status is YahooBenchmarkStatus.NO_DATA
    assert "listing.status = 'ACTIVE'" in cursor.query
    assert cursor.params[0:2] == (TRADING_DATE, TRADING_DATE)


def test_renders_benchmark_report_with_neutral_unavailable_tiles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seeds = (_seed(1, "SPX", "CLOSED"),)
    monkeypatch.setattr(
        "empire_stonks_ohlcv.yahoo_benchmark_reporting.select_active_yahoo_listings",
        lambda **_values: seeds,
    )
    report = build_yahoo_daily_benchmark_report(
        cursor=_Cursor(
            [
                (UUID(int=1), None, None, None, None, None, None, None),
            ]
        ),
        trading_date=TRADING_DATE,
        generated_at=GENERATED_AT,
        session_service=_SessionService(),  # type: ignore[arg-type]
    )

    result = render_yahoo_daily_benchmark_pdf(
        report=report,
        output_dir=tmp_path,
    )

    path = result.primary_artifact.resolved_path()
    assert YAHOO_DAILY_BENCHMARK_PDF_REPORT_ID == (
        "stonks.ohlcv.yahoo-daily-benchmark"
    )
    assert path.name == "daily-benchmark-report.pdf"
    assert path.stat().st_size > 10_000


def _seed(
    index: int,
    ticker: str,
    policy_code: str,
    *,
    observed_only: bool = False,
) -> SeededYahooListing:
    policy = SessionPolicy(
        code=policy_code,
        calendar_name=None if observed_only else "TEST",
        timezone_name="UTC",
        eligibility_rule=(
            EligibilityRule.LOCAL_CUTOFF
            if observed_only
            else EligibilityRule.SESSION_CLOSE
        ),
        cutoff_local_time=time(20) if observed_only else None,
        availability_delay_minutes=0,
        session_date_rule=(
            SessionDateRule.PROVIDER_LOCAL_DATE
            if observed_only
            else SessionDateRule.CALENDAR_SESSION
        ),
    )
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
            name=f"{ticker} Benchmark",
            instrument_type_code="EQUITY_INDEX",
            metadata={"YahooTicker": f"^{ticker}"},
        ),
        policy=policy,
    )
