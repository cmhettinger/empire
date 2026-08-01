from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from empire_stonks_ohlcv import (
    YahooDailyRunResult,
    YahooDailyScope,
    YahooReportPhase,
    empty_yahoo_report_phase,
)


def test_daily_scope_is_explicit_ordered_and_json_safe() -> None:
    scope = YahooDailyScope(
        effective_date=date(2026, 7, 31),
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 30),
        tickers=("SPX", "DOW"),
    )

    assert scope.tickers == ("DOW", "SPX")
    assert scope.to_dict() == {
        "effective_date": "2026-07-31",
        "start_date": "2026-07-01",
        "end_date": "2026-07-30",
        "tickers": ["DOW", "SPX"],
    }


@pytest.mark.parametrize(
    "values",
    [
        {
            "effective_date": date(2026, 7, 31),
            "start_date": date(2026, 8, 1),
            "end_date": date(2026, 7, 31),
        },
        {
            "effective_date": date(2026, 7, 31),
            "start_date": date(2026, 7, 1),
            "end_date": date(2026, 8, 1),
        },
    ],
)
def test_daily_scope_rejects_invalid_date_bounds(
    values: dict[str, date],
) -> None:
    with pytest.raises(ValueError):
        YahooDailyScope(**values)


def test_compact_run_result_distinguishes_noop_phases() -> None:
    result = YahooDailyRunResult(
        run_id=UUID(int=1),
        status="succeeded",
        scope=YahooDailyScope(
            effective_date=date(2026, 7, 31),
            start_date=date(2026, 7, 31),
            end_date=date(2026, 7, 31),
        ),
        enumerated_listing_count=84,
        selected_listing_count=84,
        calendar_policy_error_count=0,
        ingestion=empty_yahoo_report_phase(
            YahooReportPhase.DAILY_INGESTION
        ),
        reconciliation=empty_yahoo_report_phase(
            YahooReportPhase.RECONCILIATION
        ),
        report_object_id=UUID(int=2),
        pdf_report_object_id=UUID(int=3),
        report_outcome="PASS",
    )

    payload = result.to_dict()
    assert payload["ingestion"]["request_count"] == 0
    assert payload["reconciliation"]["request_count"] == 0
    assert payload["bar_counts"]["inserted"] == 0
    assert payload["corrected_reconciliation_bars"] == 0
    assert payload["pdf_report_object_id"] == str(UUID(int=3))
