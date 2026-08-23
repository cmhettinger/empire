from __future__ import annotations

import json
from datetime import date
from uuid import UUID

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    BenchmarkConfig,
    EODDATA_DAILY_JOB_NAME,
    SourceReadinessDecision,
    TechIndicatorsScope,
    YAHOO_DAILY_JOB_NAME,
    decide_source_readiness,
)
from empire_stonks_tech_indicators import readiness as readiness_module


EODDATA_ID = UUID("00000000-0000-4000-8000-000000000001")
STOOQ_ID = UUID("00000000-0000-4000-8000-000000000002")
SPX_ID = UUID("00000000-0000-4000-8000-000000000003")
EODDATA_RUN_ID = UUID("10000000-0000-4000-8000-000000000001")
YAHOO_RUN_ID = UUID("10000000-0000-4000-8000-000000000002")
EFFECTIVE_DATE = date(2026, 8, 3)


class SequencedCursor:
    def __init__(self, responses: list[list[tuple[object, ...]]]) -> None:
        self.responses = responses
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, parameters: tuple[object, ...]) -> None:
        self.executions.append((sql, parameters))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.responses.pop(0)


def _listing_row(
    provider_listing_id: UUID,
    provider_code: str,
    market: str,
    ticker: str,
) -> tuple[object, ...]:
    return (
        provider_listing_id,
        provider_code,
        market,
        ticker,
        "EQUITY_INDEX" if provider_code == "YAHOO" else "UNKNOWN",
        "ACTIVE",
        EFFECTIVE_DATE,
        EFFECTIVE_DATE,
        1,
    )


def _benchmark_row() -> tuple[object, ...]:
    return (
        SPX_ID,
        "YAHOO",
        "XIDX",
        "SPX",
        "EQUITY_INDEX",
        "ACTIVE",
        {"YahooTicker": "^GSPC"},
    )


def _selected_rows(*, include_stooq: bool = True) -> list[tuple[object, ...]]:
    rows = [
        _listing_row(EODDATA_ID, "EODDATA", "NASDAQ", "TEST"),
    ]
    if include_stooq:
        rows.append(_listing_row(STOOQ_ID, "STOOQ", "nasdaq", "TEST.US"))
    rows.append(_listing_row(SPX_ID, "YAHOO", "XIDX", "SPX"))
    return rows


def _evidence_rows() -> list[tuple[object, ...]]:
    return [
        (EODDATA_DAILY_JOB_NAME, EODDATA_RUN_ID),
        (YAHOO_DAILY_JOB_NAME, YAHOO_RUN_ID),
    ]


def test_readiness_api_is_explicitly_exported() -> None:
    assert readiness_module.__all__ == [
        "EODDATA_DAILY_JOB_NAME",
        "SourceReadinessDecision",
        "YAHOO_DAILY_JOB_NAME",
        "decide_source_readiness",
    ]
    assert public_api.EODDATA_DAILY_JOB_NAME == EODDATA_DAILY_JOB_NAME
    assert public_api.SourceReadinessDecision is SourceReadinessDecision
    assert public_api.YAHOO_DAILY_JOB_NAME == YAHOO_DAILY_JOB_NAME
    assert public_api.decide_source_readiness is decide_source_readiness


def test_source_readiness_accepts_exact_coverage_and_same_date_evidence() -> None:
    cursor = SequencedCursor(
        [
            _selected_rows(),
            [_benchmark_row()],
            [(EODDATA_ID,), (STOOQ_ID,), (SPX_ID,)],
            _evidence_rows(),
        ]
    )

    decision = decide_source_readiness(
        cursor=cursor,
        scope=TechIndicatorsScope(
            start_date=EFFECTIVE_DATE,
            end_date=EFFECTIVE_DATE,
        ),
        effective_date=EFFECTIVE_DATE,
        benchmark_config=BenchmarkConfig(),
    )

    assert decision.ready is True
    assert decision.selected_listing_count == 3
    assert decision.eoddata_listing_count == 1
    assert decision.stooq_listing_count == 1
    assert decision.yahoo_listing_count == 1
    assert decision.effective_date_bar_count == 3
    assert decision.supported_subject_bar_count == 2
    assert decision.benchmark_identity_required is True
    assert decision.spx_bar_required is True
    assert decision.benchmark_provider_listing_id == SPX_ID
    assert decision.benchmark_bar_present is True
    assert decision.eoddata_source_run_id == EODDATA_RUN_ID
    assert decision.yahoo_source_run_id == YAHOO_RUN_ID
    assert decision.reasons == ()
    json.dumps(decision.to_dict())

    coverage_sql, coverage_parameters = cursor.executions[2]
    assert "trading_date = %s" in coverage_sql
    assert coverage_parameters == (
        [EODDATA_ID, STOOQ_ID, SPX_ID],
        EFFECTIVE_DATE,
    )
    evidence_sql, evidence_parameters = cursor.executions[3]
    assert "run.effective_date = %s" in evidence_sql
    assert "run.status = 'succeeded'" in evidence_sql
    assert "missing_session_count' = '0'" in evidence_sql
    assert "{scope,effective_date}" in evidence_sql
    assert "{scope,tickers}" in evidence_sql
    assert "? 'SPX'" in evidence_sql
    assert evidence_parameters == (
        EFFECTIVE_DATE,
        [EODDATA_DAILY_JOB_NAME, YAHOO_DAILY_JOB_NAME],
        EFFECTIVE_DATE.isoformat(),
        EFFECTIVE_DATE.isoformat(),
    )


def test_source_readiness_reuses_pre_resolved_listing_scope() -> None:
    listing = readiness_module.EligibleListing(
        provider_listing_id=EODDATA_ID,
        provider_code="EODDATA",
        market="NASDAQ",
        ticker="TEST",
        instrument_type_code="COMMON_STOCK",
        status="ACTIVE",
        first_trading_date=None,
        last_trading_date=None,
        source_observation_count=0,
    )
    cursor = SequencedCursor(
        [
            [_benchmark_row()],
            [],
            [(EODDATA_DAILY_JOB_NAME, EODDATA_RUN_ID)],
        ]
    )

    decision = decide_source_readiness(
        cursor=cursor,
        scope=TechIndicatorsScope(),
        effective_date=EFFECTIVE_DATE,
        benchmark_config=BenchmarkConfig(),
        resolved_listings=(listing,),
    )

    assert decision.ready is True
    assert len(cursor.executions) == 3
    assert "FROM stonks.provider_listing AS listing" not in "".join(
        sql for sql, _ in cursor.executions
    )


def test_source_readiness_reports_evidence_and_spx_coverage_failures() -> None:
    cursor = SequencedCursor(
        [
            _selected_rows(include_stooq=False),
            [_benchmark_row()],
            [(EODDATA_ID,)],
            [],
        ]
    )

    decision = decide_source_readiness(
        cursor=cursor,
        scope=TechIndicatorsScope(),
        effective_date=EFFECTIVE_DATE,
        benchmark_config=BenchmarkConfig(),
    )

    assert decision.ready is False
    assert decision.spx_bar_required is True
    assert decision.benchmark_bar_present is False
    assert decision.reasons == (
        "EODDATA_SOURCE_EVIDENCE_MISSING",
        "YAHOO_SOURCE_EVIDENCE_MISSING",
        "SPX_COVERAGE_INCOMPLETE",
    )


def test_eoddata_no_bar_date_needs_only_successful_eoddata_evidence() -> None:
    cursor = SequencedCursor(
        [
            [_listing_row(EODDATA_ID, "EODDATA", "NASDAQ", "TEST")],
            [_benchmark_row()],
            [],
            [(EODDATA_DAILY_JOB_NAME, EODDATA_RUN_ID)],
        ]
    )

    decision = decide_source_readiness(
        cursor=cursor,
        scope=TechIndicatorsScope(),
        effective_date=EFFECTIVE_DATE,
        benchmark_config=BenchmarkConfig(),
    )

    assert decision.ready is True
    assert decision.benchmark_identity_required is True
    assert decision.spx_bar_required is False
    assert decision.yahoo_evidence_required is False
    assert decision.yahoo_source_run_id is None


def test_source_readiness_fails_closed_on_unavailable_benchmark() -> None:
    cursor = SequencedCursor(
        [
            [_listing_row(EODDATA_ID, "EODDATA", "NASDAQ", "TEST")],
            [],
            [(EODDATA_ID,)],
            _evidence_rows(),
        ]
    )

    decision = decide_source_readiness(
        cursor=cursor,
        scope=TechIndicatorsScope(),
        effective_date=EFFECTIVE_DATE,
        benchmark_config=BenchmarkConfig(),
    )

    assert decision.ready is False
    assert decision.benchmark_provider_listing_id is None
    assert decision.spx_bar_required is True
    assert decision.reasons == ("BENCHMARK_UNAVAILABLE",)


def test_source_readiness_rejects_empty_selection() -> None:
    cursor = SequencedCursor([[]])

    decision = decide_source_readiness(
        cursor=cursor,
        scope=TechIndicatorsScope(),
        effective_date=EFFECTIVE_DATE,
        benchmark_config=BenchmarkConfig(),
    )

    assert decision.ready is False
    assert decision.selected_listing_count == 0
    assert decision.reasons == ("NO_ELIGIBLE_LISTINGS",)
    assert len(cursor.executions) == 1


def test_source_readiness_rejects_ambiguous_or_invalid_boundaries() -> None:
    cursor = SequencedCursor([])
    with pytest.raises(ValueError, match="must both equal"):
        decide_source_readiness(
            cursor=cursor,
            scope=TechIndicatorsScope(
                start_date=date(2026, 8, 1),
                end_date=EFFECTIVE_DATE,
            ),
            effective_date=EFFECTIVE_DATE,
            benchmark_config=BenchmarkConfig(),
        )
    assert cursor.executions == []

    with pytest.raises(TypeError, match="effective_date"):
        decide_source_readiness(
            cursor=cursor,
            scope=TechIndicatorsScope(),
            effective_date="2026-08-03",  # type: ignore[arg-type]
            benchmark_config=BenchmarkConfig(),
        )
    with pytest.raises(TypeError, match="benchmark_config"):
        decide_source_readiness(
            cursor=cursor,
            scope=TechIndicatorsScope(),
            effective_date=EFFECTIVE_DATE,
            benchmark_config=object(),  # type: ignore[arg-type]
        )


def test_source_readiness_rejects_query_identity_drift() -> None:
    other_id = UUID("00000000-0000-4000-8000-000000000099")
    coverage_cursor = SequencedCursor(
        [
            [_listing_row(EODDATA_ID, "EODDATA", "NASDAQ", "TEST")],
            [_benchmark_row()],
            [(other_id,)],
        ]
    )
    with pytest.raises(ValueError, match="identity drift"):
        decide_source_readiness(
            cursor=coverage_cursor,
            scope=TechIndicatorsScope(),
            effective_date=EFFECTIVE_DATE,
            benchmark_config=BenchmarkConfig(),
        )

    evidence_cursor = SequencedCursor(
        [
            [_listing_row(EODDATA_ID, "EODDATA", "NASDAQ", "TEST")],
            [_benchmark_row()],
            [(EODDATA_ID,), (SPX_ID,)],
            [("unexpected_job", EODDATA_RUN_ID)],
        ]
    )
    with pytest.raises(ValueError, match="identity drift"):
        decide_source_readiness(
            cursor=evidence_cursor,
            scope=TechIndicatorsScope(),
            effective_date=EFFECTIVE_DATE,
            benchmark_config=BenchmarkConfig(),
        )
