from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from uuid import UUID

import pytest

import empire_stonks_ohlcv.tech_indicators_completion as completion_module
from empire_stonks_ohlcv import (
    TECH_INDICATORS_BENCHMARK_TICKER,
    TECH_INDICATORS_COMPLETION_SCHEMA_VERSION,
    TECH_INDICATORS_COMPLETION_SIGNAL_TYPE,
    EODDataDailyRunResult,
    PersistenceCounts,
    TechIndicatorsSourceCompletionSignal,
    YahooDailyRunResult,
    YahooDailyScope,
    YahooReportPhase,
    empty_yahoo_report_phase,
)


EFFECTIVE_DATE = date(2026, 8, 28)
EODDATA_RUN_ID = UUID("10000000-0000-4000-8000-000000000001")
YAHOO_RUN_ID = UUID("20000000-0000-4000-8000-000000000002")


def _eoddata_result() -> EODDataDailyRunResult:
    return EODDataDailyRunResult(
        run_id=EODDATA_RUN_ID,
        status="succeeded",
        effective_date=EFFECTIVE_DATE,
        report_object_id=UUID(int=11),
        pdf_report_object_id=UUID(int=12),
        market_pdf_report_object_id=UUID(int=13),
        report_outcome="WARN",
        listing_counts=PersistenceCounts(inserted=3),
        bar_counts=PersistenceCounts(inserted=2, updated=1),
        skipped_inactive_bars=0,
        row_rejection_count=1,
        row_rejection_row_count=1,
        failure_count=0,
        warning_count=1,
        expected_session_count=3,
        eligible_session_count=3,
        missing_session_count=0,
        ineligible_exchange_count=0,
        planned_exchange_count=3,
        retry_count=1,
        corrected_current_rows=1,
    )


def _yahoo_result(*, tickers: tuple[str, ...] = ()) -> YahooDailyRunResult:
    return YahooDailyRunResult(
        run_id=YAHOO_RUN_ID,
        status="succeeded",
        scope=YahooDailyScope(
            effective_date=EFFECTIVE_DATE,
            start_date=EFFECTIVE_DATE,
            end_date=EFFECTIVE_DATE,
            tickers=tickers,
        ),
        enumerated_listing_count=2,
        selected_listing_count=1,
        calendar_policy_error_count=0,
        ingestion=empty_yahoo_report_phase(
            YahooReportPhase.DAILY_INGESTION
        ),
        reconciliation=empty_yahoo_report_phase(
            YahooReportPhase.RECONCILIATION
        ),
        report_object_id=UUID(int=21),
        pdf_report_object_id=UUID(int=22),
        benchmark_pdf_report_object_id=UUID(int=23),
        report_outcome="PASS",
    )


def test_completion_contract_is_explicit_and_json_safe() -> None:
    signal = TechIndicatorsSourceCompletionSignal(
        provider_code="EODDATA",
        source_code="eoddata_daily",
        job_name="stonks_ohlcv_eoddata_daily",
        effective_date=EFFECTIVE_DATE,
        source_run_id=EODDATA_RUN_ID,
        report_outcome="WARN",
    )

    assert TECH_INDICATORS_COMPLETION_SCHEMA_VERSION == 1
    assert TECH_INDICATORS_COMPLETION_SIGNAL_TYPE == (
        "stonks_ohlcv_daily_completion"
    )
    assert TECH_INDICATORS_BENCHMARK_TICKER == "SPX"
    assert completion_module.__all__ == [
        "TECH_INDICATORS_BENCHMARK_TICKER",
        "TECH_INDICATORS_COMPLETION_SCHEMA_VERSION",
        "TECH_INDICATORS_COMPLETION_SIGNAL_TYPE",
        "TechIndicatorsSourceCompletionSignal",
    ]
    assert signal.source_dag_id == "stonks_ohlcv_eoddata_daily_scrape"
    assert signal.trigger_run_id == (
        "source__eoddata__10000000-0000-4000-8000-000000000001"
    )
    assert signal.to_dict() == {
        "schema_version": 1,
        "signal_type": "stonks_ohlcv_daily_completion",
        "provider_code": "EODDATA",
        "source_code": "eoddata_daily",
        "job_name": "stonks_ohlcv_eoddata_daily",
        "effective_date": "2026-08-28",
        "source_run_id": str(EODDATA_RUN_ID),
        "report_outcome": "WARN",
        "trigger_run_id": signal.trigger_run_id,
    }
    assert json.loads(json.dumps(signal.to_dict())) == signal.to_dict()


def test_trigger_configuration_has_exact_secret_safe_provenance() -> None:
    signal = _yahoo_result(tickers=("SPX",)).tech_indicators_completion_signal

    assert signal is not None
    assert signal.to_trigger_conf(
        source_dag_run_id="scheduled__2026-08-28T23:15:00+00:00"
    ) == {
        "coordination_schema_version": 1,
        "effective_date": "2026-08-28",
        "source_provider_code": "YAHOO",
        "source_code": "yahoo_daily",
        "source_job_name": "stonks_ohlcv_yahoo_daily",
        "source_core_run_id": str(YAHOO_RUN_ID),
        "source_dag_id": "stonks_ohlcv_yahoo_daily_scrape",
        "source_dag_run_id": "scheduled__2026-08-28T23:15:00+00:00",
    }


@pytest.mark.parametrize(
    "values, expected_error",
    [
        ({"provider_code": "STOOQ"}, ValueError),
        ({"report_outcome": "FAIL"}, ValueError),
        ({"schema_version": 2}, ValueError),
        ({"signal_type": "other"}, ValueError),
        ({"effective_date": "2026-08-28"}, TypeError),
        ({"source_run_id": "not-a-uuid"}, TypeError),
    ],
)
def test_completion_signal_rejects_ambiguous_values(
    values: dict[str, object],
    expected_error: type[Exception],
) -> None:
    arguments: dict[str, object] = {
        "provider_code": "EODDATA",
        "source_code": "eoddata_daily",
        "job_name": "stonks_ohlcv_eoddata_daily",
        "effective_date": EFFECTIVE_DATE,
        "source_run_id": EODDATA_RUN_ID,
        "report_outcome": "PASS",
    }
    arguments.update(values)

    with pytest.raises(expected_error):
        TechIndicatorsSourceCompletionSignal(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "source_dag_run_id",
    ["", " has-space", "manual/run", "x" * 251],
)
def test_trigger_configuration_rejects_unsafe_airflow_run_ids(
    source_dag_run_id: str,
) -> None:
    signal = _eoddata_result().tech_indicators_completion_signal

    assert signal is not None
    with pytest.raises(ValueError, match="safe Airflow run ID"):
        signal.to_trigger_conf(source_dag_run_id=source_dag_run_id)


@pytest.mark.parametrize("report_outcome", ["PASS", "WARN"])
def test_eoddata_result_emits_completion_only_for_ready_success(
    report_outcome: str,
) -> None:
    result = replace(_eoddata_result(), report_outcome=report_outcome)

    signal = result.tech_indicators_completion_signal
    assert signal is not None
    assert signal.effective_date == EFFECTIVE_DATE
    assert signal.source_run_id == EODDATA_RUN_ID
    assert result.to_dict()["tech_indicators_completion_signal"] == (
        signal.to_dict()
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"failure_count": 1},
        {"missing_session_count": 1},
        {"report_outcome": "FAIL"},
    ],
)
def test_eoddata_result_omits_incomplete_source_signal(
    changes: dict[str, object],
) -> None:
    result = replace(_eoddata_result(), **changes)

    assert result.tech_indicators_completion_signal is None
    assert result.to_dict()["tech_indicators_completion_signal"] is None


@pytest.mark.parametrize("tickers", [(), ("SPX",), ("DOW", "SPX")])
def test_yahoo_result_emits_completion_for_full_or_spx_scope(
    tickers: tuple[str, ...],
) -> None:
    result = _yahoo_result(tickers=tickers)

    signal = result.tech_indicators_completion_signal
    assert signal is not None
    assert signal.effective_date == EFFECTIVE_DATE
    assert signal.source_run_id == YAHOO_RUN_ID
    assert result.to_dict()["tech_indicators_completion_signal"] == (
        signal.to_dict()
    )


def test_yahoo_result_omits_completion_without_spx_scope() -> None:
    result = _yahoo_result(tickers=("DOW",))

    assert result.tech_indicators_completion_signal is None
    assert result.to_dict()["tech_indicators_completion_signal"] is None


def test_completion_signal_is_stable_for_one_source_run() -> None:
    result = _eoddata_result()
    first_signal = result.tech_indicators_completion_signal
    second_signal = _eoddata_result().tech_indicators_completion_signal

    assert first_signal is not None
    assert second_signal is not None
    assert first_signal == result.tech_indicators_completion_signal
    assert first_signal.trigger_run_id == second_signal.trigger_run_id
