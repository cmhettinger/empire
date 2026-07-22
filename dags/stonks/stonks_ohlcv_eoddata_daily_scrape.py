from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_ohlcv import OHLCVConfig, run_eoddata_daily


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
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "ohlcv", "eoddata", "manual"],
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
            "run PDF %s, and market PDF %s (%s)",
            payload["run_id"],
            payload["effective_date"],
            payload["report_object_id"],
            payload["pdf_report_object_id"],
            payload["market_pdf_report_object_id"],
            payload["report_outcome"],
        )
        return payload

    run_daily()


stonks_ohlcv_eoddata_daily_scrape_dag = (
    stonks_ohlcv_eoddata_daily_scrape()
)
