from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from airflow.providers.standard.operators.trigger_dagrun import (
    TriggerDagRunOperator,
)
from airflow.sdk import dag, get_current_context, task
from airflow.sdk.exceptions import AirflowSkipException
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_ohlcv import (
    TECH_INDICATORS_COORDINATOR_DAG_ID,
    OHLCVConfig,
    build_tech_indicators_dispatch,
    run_eoddata_daily,
)


DAG_ID = "stonks_ohlcv_eoddata_daily_scrape"
MARKET_TIMEZONE = ZoneInfo("America/New_York")

log = logging.getLogger(__name__)


def _effective_date_from_context(context: dict[str, object]) -> date:
    """Return an explicit override or the scheduled New York trading date."""

    dag_run = context.get("dag_run")
    conf = getattr(dag_run, "conf", None) or {}
    configured_date = conf.get("effective_date")
    if configured_date is not None:
        if not isinstance(configured_date, str):
            raise ValueError("effective_date must use YYYY-MM-DD.")
        try:
            parsed_date = date.fromisoformat(configured_date)
        except ValueError:
            raise ValueError("effective_date must use YYYY-MM-DD.") from None
        if parsed_date.isoformat() != configured_date:
            raise ValueError("effective_date must use YYYY-MM-DD.")
        return parsed_date

    data_interval_end = context.get("data_interval_end")
    if not isinstance(data_interval_end, datetime):
        raise ValueError("Airflow data_interval_end is required.")
    if data_interval_end.tzinfo is None:
        raise ValueError("Airflow data_interval_end must be timezone-aware.")
    return data_interval_end.astimezone(MARKET_TIMEZONE).date()


@dag(
    dag_id=DAG_ID,
    start_date=datetime(2026, 7, 17, tzinfo=MARKET_TIMEZONE),
    schedule="15 20,23 * * 1-5",
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "ohlcv", "eoddata", "scheduled"],
)
def stonks_ohlcv_eoddata_daily_scrape():
    @task(task_id="run_eoddata_daily")
    def run_daily() -> dict[str, object]:
        context = get_current_context()
        dag_run = context["dag_run"]
        effective_date = _effective_date_from_context(context)
        config = OHLCVConfig.from_env()

        with EmpireDatabase.connect_from_env() as connection:
            result = run_eoddata_daily(
                run_service=RunService.from_connection(connection),
                connection=connection,
                object_store=ObjectStore.from_connection(connection),
                config=config,
                effective_date=effective_date,
                run_type="airflow",
                runner="airflow",
                runner_ref={
                    "dag_id": DAG_ID,
                    "dag_run_id": str(dag_run.run_id),
                },
            )

        payload = result.to_dict()
        log.info(
            "Completed EODData daily run %s for %s with JSON report %s, "
            "run PDF %s, and market PDF %s (%s); planned exchanges=%s, "
            "missing sessions=%s, ineligible exchanges=%s, retries=%s, "
            "corrected rows=%s",
            payload["run_id"],
            payload["effective_date"],
            payload["report_object_id"],
            payload["pdf_report_object_id"],
            payload["market_pdf_report_object_id"],
            payload["report_outcome"],
            payload["planned_exchange_count"],
            payload["missing_session_count"],
            payload["ineligible_exchange_count"],
            payload["retry_count"],
            payload["corrected_current_rows"],
        )
        return payload

    @task(task_id="prepare_tech_indicators_dispatch")
    def prepare_dispatch(
        source_result: dict[str, object],
    ) -> dict[str, object]:
        context = get_current_context()
        dag_run = context["dag_run"]
        dispatch = build_tech_indicators_dispatch(
            source_result,
            source_dag_id=DAG_ID,
            source_dag_run_id=str(dag_run.run_id),
        )
        if dispatch is None:
            log.info(
                "EODData daily result has no qualifying technical-indicator "
                "completion signal; dispatch skipped"
            )
            raise AirflowSkipException(
                "No qualifying technical-indicator completion signal."
            )
        log.info(
            "Prepared technical-indicator dispatch for EODData run %s and %s",
            dispatch["conf"]["source_core_run_id"],
            dispatch["conf"]["effective_date"],
        )
        return dispatch

    source_result = run_daily()
    dispatch = prepare_dispatch(source_result)
    TriggerDagRunOperator(
        task_id="trigger_tech_indicators_refresh",
        trigger_dag_id=TECH_INDICATORS_COORDINATOR_DAG_ID,
        trigger_run_id=dispatch["trigger_run_id"],
        conf=dispatch["conf"],
        reset_dag_run=False,
        wait_for_completion=False,
        skip_when_already_exists=True,
    )


stonks_ohlcv_eoddata_daily_scrape_dag = (
    stonks_ohlcv_eoddata_daily_scrape()
)

# V10.8 rollout decision: run at 20:15 and 23:15 ET each weekday. The first
# run follows the reviewed 20:00 eligibility cutoff; the second provides a
# same-date retry and recent-session reconciliation opportunity. The bounded
# 2026-07-31 run completed all three markets but needed 13 recovered retries,
# so this two-run cadence limits provider pressure. Pause this DAG and restore
# schedule=None if scheduled runs repeatedly show similar retry pressure or
# provider failures. The package planner keeps holidays and completed work as
# no-ops.
