from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from empire_stonks_tech_indicators import BenchmarkConfig, TechIndicatorsScope
from empire_stonks_tech_indicators.inspection import (
    INSPECTION_DISCLOSURE,
    inspect_tech_indicators,
)
from empire_stonks_tech_indicators import inspection as module
from empire_stonks_tech_indicators.published_queries import (
    PublishedFeatureCoverage,
    PublishedFeatureFreshness,
)
from empire_stonks_tech_indicators.readiness import SourceReadinessDecision
from empire_stonks_tech_indicators.state import ListingStateComparison


EFFECTIVE_DATE = date(2026, 8, 24)
FIRST_DATE = date(2026, 8, 20)
LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
SECOND_ID = UUID("00000000-0000-4000-8000-000000000002")
BENCHMARK_ID = UUID("00000000-0000-4000-8000-000000000003")
RUN_ID = UUID("10000000-0000-4000-8000-000000000001")
UPDATED_AT = datetime(2026, 8, 24, 20, 0, tzinfo=UTC)


class Cursor:
    def __init__(self) -> None:
        self.executions: list[str] = []
        self.closed = False

    def execute(self, sql: str) -> None:
        self.executions.append(sql)

    def close(self) -> None:
        self.closed = True


class Connection:
    def __init__(self) -> None:
        self.cursor_value = Cursor()
        self.rollback_count = 0

    def cursor(self) -> Cursor:
        return self.cursor_value

    def rollback(self) -> None:
        self.rollback_count += 1


def _coverage(
    identifier: UUID,
    *,
    published_rows: int,
) -> PublishedFeatureCoverage:
    return PublishedFeatureCoverage(
        provider_listing_id=identifier,
        provider_code="EODDATA",
        market="NASDAQ",
        ticker="AAA" if identifier == LISTING_ID else "BBB",
        status="ACTIVE",
        source_first_trading_date=FIRST_DATE,
        source_last_trading_date=EFFECTIVE_DATE,
        source_row_count=5,
        published_first_trading_date=(
            FIRST_DATE if published_rows else None
        ),
        published_last_trading_date=(
            EFFECTIVE_DATE if published_rows else None
        ),
        published_row_count=published_rows,
        latest_calculated_at=UPDATED_AT if published_rows else None,
        latest_updated_at=UPDATED_AT if published_rows else None,
        calculation_versions=("TECH_INDICATORS_V1",) if published_rows else (),
        benchmark_provider_listing_ids=(BENCHMARK_ID,) if published_rows else (),
    )


def _freshness(
    identifier: UUID,
    *,
    populated: bool,
) -> PublishedFeatureFreshness:
    return PublishedFeatureFreshness(
        provider_listing_id=identifier,
        provider_code="EODDATA",
        market="NASDAQ",
        ticker="AAA" if identifier == LISTING_ID else "BBB",
        as_of_date=EFFECTIVE_DATE,
        latest_trading_date=EFFECTIVE_DATE if populated else None,
        calendar_age_days=0 if populated else None,
        latest_calculated_at=UPDATED_AT if populated else None,
        latest_updated_at=UPDATED_AT if populated else None,
        calculation_versions=("TECH_INDICATORS_V1",) if populated else (),
        benchmark_provider_listing_ids=(BENCHMARK_ID,) if populated else (),
    )


def _comparison(
    identifier: UUID,
    *,
    tail_append_count: int = 0,
) -> ListingStateComparison:
    return ListingStateComparison(
        provider_listing_id=identifier,
        provider_code="EODDATA",
        market="NASDAQ",
        ticker="AAA" if identifier == LISTING_ID else "BBB",
        first_source_date=FIRST_DATE,
        last_source_date=EFFECTIVE_DATE,
        source_observation_count=5,
        last_technical_date=(
            EFFECTIVE_DATE if not tail_append_count else date(2026, 8, 23)
        ),
        tail_append_count=tail_append_count,
        missing_tech_row_count=0,
        source_copy_drift_count=0,
        history_count_drift_count=0,
        version_drift_count=0,
        earliest_tail_append_date=(
            EFFECTIVE_DATE if tail_append_count else None
        ),
        earliest_missing_tech_date=None,
        earliest_source_copy_drift_date=None,
        earliest_history_count_drift_date=None,
        earliest_version_drift_date=None,
    )


def _readiness() -> SourceReadinessDecision:
    return SourceReadinessDecision(
        effective_date=EFFECTIVE_DATE,
        selected_listing_count=2,
        eoddata_listing_count=2,
        stooq_listing_count=0,
        yahoo_listing_count=0,
        effective_date_bar_count=2,
        supported_subject_bar_count=2,
        benchmark_identity_required=True,
        spx_bar_required=True,
        benchmark_provider_listing_id=BENCHMARK_ID,
        benchmark_bar_present=True,
        eoddata_evidence_required=True,
        yahoo_evidence_required=True,
        eoddata_source_run_id=RUN_ID,
        yahoo_source_run_id=RUN_ID,
        reasons=(),
    )


def test_inspection_combines_read_only_facts_and_bounds_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Connection()
    coverage_summary = SimpleNamespace(
        selected_listing_count=2,
        to_dict=lambda: {"selected_listing_count": 2},
    )
    monkeypatch.setattr(
        module,
        "select_report_database_summary",
        lambda **_: coverage_summary,
    )
    monkeypatch.setattr(
        module,
        "select_published_feature_coverage",
        lambda **_: (
            _coverage(LISTING_ID, published_rows=5),
            _coverage(SECOND_ID, published_rows=0),
        ),
    )
    monkeypatch.setattr(
        module,
        "select_published_feature_freshness",
        lambda **_: (
            _freshness(LISTING_ID, populated=True),
            _freshness(SECOND_ID, populated=False),
        ),
    )
    monkeypatch.setattr(module, "decide_source_readiness", lambda **_: _readiness())
    monkeypatch.setattr(
        module,
        "iter_state_comparison_pages",
        lambda **_: iter(
            ((_comparison(LISTING_ID), _comparison(SECOND_ID, tail_append_count=1)),)
        ),
    )

    result = inspect_tech_indicators(
        connection=connection,
        scope=TechIndicatorsScope(
            provider_listing_ids=(LISTING_ID, SECOND_ID),
            start_date=FIRST_DATE,
            end_date=EFFECTIVE_DATE,
        ),
        effective_date=EFFECTIVE_DATE,
        benchmark_config=BenchmarkConfig(),
        sample_limit=1,
        page_size=1000,
    )

    payload = result.to_dict()
    assert connection.cursor_value.executions == [
        "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    ]
    assert connection.cursor_value.closed is True
    assert connection.rollback_count == 1
    assert payload["coverage_listing_facts"][
        "source_and_published_key_mismatch_count"
    ] == 1
    assert len(payload["coverage_listing_facts"]["samples"]) == 1
    assert payload["freshness"]["no_published_data_count"] == 1
    assert len(payload["freshness"]["samples"]) == 1
    assert payload["drift"]["drifted_listing_count"] == 1
    assert payload["drift"]["reason_row_counts"] == [
        {"code": "TAIL_APPEND", "count": 1}
    ]
    assert len(payload["drift"]["samples"]) == 1
    assert payload["spx_readiness"]["ready"] is True
    assert payload["disclosure"] == INSPECTION_DISCLOSURE
    assert "recommendations" in payload["disclosure"]
    assert "feature_value" not in str(payload)


def test_inspection_rolls_back_and_closes_after_query_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Connection()
    monkeypatch.setattr(
        module,
        "select_report_database_summary",
        lambda **_: (_ for _ in ()).throw(RuntimeError("database secret")),
    )

    with pytest.raises(RuntimeError, match="database secret"):
        inspect_tech_indicators(
            connection=connection,
            scope=TechIndicatorsScope(),
            effective_date=EFFECTIVE_DATE,
            benchmark_config=BenchmarkConfig(),
        )

    assert connection.cursor_value.closed is True
    assert connection.rollback_count == 1


def test_inspection_rejects_invalid_bounds_before_opening_cursor() -> None:
    connection = Connection()
    with pytest.raises(ValueError, match="sample_limit"):
        inspect_tech_indicators(
            connection=connection,
            scope=TechIndicatorsScope(),
            effective_date=EFFECTIVE_DATE,
            benchmark_config=BenchmarkConfig(),
            sample_limit=101,
        )
    assert connection.cursor_value.executions == []
