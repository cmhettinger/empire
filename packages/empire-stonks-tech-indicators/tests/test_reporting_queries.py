from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    EligibleListing,
    REPORT_FEATURE_FIELDS,
    ReportFeatureCoverage,
    TechIndicatorsScope,
    select_report_database_summary,
)
from empire_stonks_tech_indicators import reporting_queries as module


LISTING_ID = UUID("91111111-1111-4111-8111-111111111111")
BENCHMARK_ID = UUID("92222222-2222-4222-8222-222222222222")
PUBLICATION_ID = UUID("93333333-3333-4333-8333-333333333333")
FIRST_DATE = date(2026, 8, 20)
EFFECTIVE_DATE = date(2026, 8, 21)


class SequencedCursor:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.current: object = None
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> None:
        self.executions.append((sql, parameters))
        self.current = self.responses.pop(0)

    def fetchall(self) -> object:
        return self.current

    def fetchone(self) -> object:
        return self.current


def _listing(
    provider_listing_id: UUID,
    *,
    provider_code: str,
    market: str,
    ticker: str,
    instrument_type_code: str,
    row_count: int,
) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=provider_listing_id,
        provider_code=provider_code,
        market=market,
        ticker=ticker,
        instrument_type_code=instrument_type_code,
        status="ACTIVE",
        first_trading_date=FIRST_DATE,
        last_trading_date=EFFECTIVE_DATE,
        source_observation_count=row_count,
    )


def _feature_aggregate_row(total: int = 4) -> tuple[int, ...]:
    values = [total]
    for field in REPORT_FEATURE_FIELDS:
        minimum = module._MINIMUM_OBSERVATIONS[field]
        if field == "rel_spx":
            populated = 1
        elif field in module._SPX_FIELDS:
            populated = total - 2 - (minimum > 1)
        else:
            populated = total - 2 * (minimum > 1)
        values.append(populated)
        if field in module._GUARANTEED_AFTER_WARMUP:
            values.append(0)
    return tuple(values)


def _all_populated_feature_aggregate_row(total: int) -> tuple[int, ...]:
    values = [total]
    for field in REPORT_FEATURE_FIELDS:
        values.append(total)
        if field in module._GUARANTEED_AFTER_WARMUP:
            values.append(0)
    return tuple(values)


def test_report_query_api_and_feature_inventory_are_explicit() -> None:
    assert len(REPORT_FEATURE_FIELDS) == 76
    assert len(set(REPORT_FEATURE_FIELDS)) == 76
    assert set(module._MINIMUM_OBSERVATIONS) == set(REPORT_FEATURE_FIELDS)
    for name in (
        "REPORT_FEATURE_FIELDS",
        "ReportBenchmarkCoverage",
        "ReportDatabaseSummary",
        "ReportDateCoverage",
        "ReportDimensionCoverage",
        "ReportFeatureCoverage",
        "ReportVersionCoverage",
        "select_report_database_summary",
    ):
        assert name in public_api.__all__
        assert getattr(public_api, name) is not None


def test_feature_coverage_rejects_broken_count_equations() -> None:
    with pytest.raises(ValueError, match="populated and null"):
        ReportFeatureCoverage(
            feature_name="rsi_14",
            eligible_row_count=2,
            populated_count=2,
            null_count=1,
            warmup_null_count=1,
            dependency_null_count=0,
            unsupported_null_count=0,
            unexpected_null_count=0,
        )


def test_empty_scope_returns_all_zero_feature_facts_without_payload_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "select_eligible_listings", lambda **_: ())
    cursor = SequencedCursor([])

    summary = select_report_database_summary(
        cursor=cursor,
        scope=TechIndicatorsScope(),
    )

    assert summary.selected_listing_count == 0
    assert len(summary.features) == 76
    assert all(item.eligible_row_count == 0 for item in summary.features)
    assert cursor.executions == []


def test_candidate_summary_is_count_only_scoped_and_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listings = (
        _listing(
            LISTING_ID,
            provider_code="EODDATA",
            market="NYSE",
            ticker="SUBJECT",
            instrument_type_code="UNKNOWN",
            row_count=3,
        ),
        _listing(
            BENCHMARK_ID,
            provider_code="YAHOO",
            market="XIDX",
            ticker="SPX",
            instrument_type_code="EQUITY_INDEX",
            row_count=2,
        ),
    )
    monkeypatch.setattr(
        module,
        "select_eligible_listings",
        lambda **_: listings,
    )
    cursor = SequencedCursor(
        [
            [
                (
                    LISTING_ID,
                    "TECH_INDICATORS_V1",
                    FIRST_DATE,
                    EFFECTIVE_DATE,
                    2,
                    1,
                    2,
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                ),
                (
                    BENCHMARK_ID,
                    "TECH_INDICATORS_V1",
                    FIRST_DATE,
                    EFFECTIVE_DATE,
                    2,
                    1,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                ),
            ],
            [(LISTING_ID, 1, 0), (BENCHMARK_ID, 2, 1)],
            [(1, 2, 1), (300, 2, 1)],
            _feature_aggregate_row(),
            (2,),
        ]
    )
    scope = TechIndicatorsScope(
        provider_listing_ids=(LISTING_ID, BENCHMARK_ID),
        start_date=FIRST_DATE,
        end_date=EFFECTIVE_DATE,
    )

    summary = select_report_database_summary(
        cursor=cursor,
        scope=scope,
        effective_date=EFFECTIVE_DATE,
        publication_id=PUBLICATION_ID,
    )

    assert summary.selected_listing_count == 2
    assert summary.source_row_count == 5
    assert summary.payload_row_count == 4
    assert summary.published_row_count == 3
    assert summary.dates.effective_date_source_rows == 2
    assert summary.dates.effective_date_payload_rows == 2
    assert summary.versions[0].row_count == 4
    assert summary.providers[0].code == "EODDATA"
    assert summary.providers[0].payload_row_count == 2
    assert summary.providers[1].code == "YAHOO"
    assert summary.benchmark.supported_listing_count == 1
    assert summary.benchmark.unsupported_listing_count == 1
    assert summary.benchmark.benchmark_linked_row_count == 2
    assert summary.benchmark.aligned_row_count == 1
    assert summary.benchmark.complete_20_count == 1
    rel_spx = next(
        item for item in summary.features if item.feature_name == "rel_spx"
    )
    assert rel_spx.to_dict() == {
        "feature_name": "rel_spx",
        "eligible_row_count": 4,
        "populated_count": 1,
        "null_count": 3,
        "warmup_null_count": 0,
        "dependency_null_count": 1,
        "unsupported_null_count": 2,
        "unexpected_null_count": 0,
    }
    payload_sql, payload_parameters = cursor.executions[0]
    assert "ohlcv_daily_tech_indicators_a" in payload_sql
    assert "ohlcv_daily_tech_indicators_b" in payload_sql
    assert "membership.publication_id = %s" in payload_sql
    assert "payload.*" in payload_sql
    assert payload_parameters == (
        PUBLICATION_ID,
        [LISTING_ID, BENCHMARK_ID],
        FIRST_DATE,
        EFFECTIVE_DATE,
        PUBLICATION_ID,
        [LISTING_ID, BENCHMARK_ID],
        FIRST_DATE,
        EFFECTIVE_DATE,
        EFFECTIVE_DATE,
        EFFECTIVE_DATE,
    )
    history_sql, _parameters = cursor.executions[2]
    assert "GROUP BY history_observation_count" in history_sql
    assert "ORDER BY history_observation_count" not in history_sql
    feature_sql, _parameters = cursor.executions[3]
    assert "count(rsi_14)" in feature_sql
    assert "SELECT rsi_14" not in feature_sql
    assert "ORDER BY" not in feature_sql
    assert len(summary.to_dict()["features"]) == 76


def test_published_summary_uses_only_the_view_for_payload_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listings = (
        _listing(
            LISTING_ID,
            provider_code="EODDATA",
            market="NYSE",
            ticker="SUBJECT",
            instrument_type_code="UNKNOWN",
            row_count=1,
        ),
    )
    monkeypatch.setattr(
        module,
        "select_eligible_listings",
        lambda **_: listings,
    )
    cursor = SequencedCursor(
        [
            [
                (
                    LISTING_ID,
                    "TECH_INDICATORS_V1",
                    EFFECTIVE_DATE,
                    EFFECTIVE_DATE,
                    1,
                    1,
                    1,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                )
            ],
            [(300, 1, 1)],
            _all_populated_feature_aggregate_row(total=1),
            (1,),
        ]
    )

    summary = select_report_database_summary(
        cursor=cursor,
        scope=TechIndicatorsScope(
            provider_listing_ids=(LISTING_ID,),
            start_date=EFFECTIVE_DATE,
            end_date=EFFECTIVE_DATE,
        ),
        effective_date=EFFECTIVE_DATE,
    )

    payload_sql, _parameters = cursor.executions[0]
    assert "FROM stonks.ohlcv_daily_tech_indicators" in payload_sql
    assert "ohlcv_daily_tech_indicators_a" not in payload_sql
    assert "ohlcv_daily_tech_indicators_b" not in payload_sql
    assert summary.payload_row_count == 1
    assert summary.published_row_count == 1
    assert summary.features[0].populated_count == 1
    assert len(cursor.executions) == 4
