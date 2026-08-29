from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date, datetime, timedelta
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
    YahooDailyScope,
    build_tech_indicators_dispatch,
    run_yahoo_daily,
)


DAG_ID = "stonks_ohlcv_yahoo_daily_scrape"
MARKET_TIMEZONE = ZoneInfo("America/New_York")

log = logging.getLogger(__name__)


def _dag_run_conf(context: Mapping[str, object]) -> Mapping[str, object]:
    dag_run = context.get("dag_run")
    conf = getattr(dag_run, "conf", None) or {}
    if not isinstance(conf, Mapping):
        raise ValueError("Airflow dag_run.conf must be a JSON object.")
    return conf


def _effective_date_from_context(context: Mapping[str, object]) -> date:
    """Return an explicit override or the New York data-interval date."""

    configured_date = _optional_date(
        _dag_run_conf(context),
        "effective_date",
    )
    if configured_date is not None:
        return configured_date

    data_interval_end = context.get("data_interval_end")
    if not isinstance(data_interval_end, datetime):
        raise ValueError("Airflow data_interval_end is required.")
    if data_interval_end.tzinfo is None:
        raise ValueError("Airflow data_interval_end must be timezone-aware.")
    return data_interval_end.astimezone(MARKET_TIMEZONE).date()


def _scope_from_context(
    context: Mapping[str, object],
    config: OHLCVConfig,
) -> YahooDailyScope:
    """Build the bounded package scope from optional manual-run overrides."""

    conf = _dag_run_conf(context)
    effective_date = _effective_date_from_context(context)
    end_date = _optional_date(conf, "end_date") or effective_date
    start_date = _optional_date(conf, "start_date") or (
        end_date - timedelta(days=config.yahoo_daily_lookback_days - 1)
    )
    return YahooDailyScope(
        effective_date=effective_date,
        start_date=start_date,
        end_date=end_date,
        tickers=_optional_tickers(conf),
    )


def _optional_date(conf: Mapping[str, object], key: str) -> date | None:
    value = conf.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must use YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{key} must use YYYY-MM-DD.") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{key} must use YYYY-MM-DD.")
    return parsed


def _optional_tickers(conf: Mapping[str, object]) -> tuple[str, ...]:
    value = conf.get("tickers")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("tickers must be a JSON array of Empire tickers.")
    tickers: list[str] = []
    for ticker in value:
        if (
            not isinstance(ticker, str)
            or not ticker
            or ticker != ticker.strip()
            or ticker != ticker.upper()
        ):
            raise ValueError(
                "tickers must contain exact trimmed uppercase Empire tickers."
            )
        tickers.append(ticker)
    return tuple(tickers)


# V10.10 rollout decision: keep this DAG manual and the deployed DAG paused so
# an 83-listing provider run never starts merely because Airflow is running.
# Y8.15 proved bounded backfill, reconciliation, and rerun behavior, but Yahoo's
# selected endpoint has no published quota or availability contract. The
# approved cadence is therefore no automatic cadence (`schedule=None`). Revisit
# scheduling only after an explicit operator decision and provider-access
# review. Roll back any temporary schedule by restoring `schedule=None` and
# pausing the DAG.
@dag(
    dag_id=DAG_ID,
    start_date=datetime(2026, 8, 1, tzinfo=MARKET_TIMEZONE),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "ohlcv", "yahoo", "manual"],
)
def stonks_ohlcv_yahoo_daily_scrape():
    @task(task_id="run_yahoo_daily")
    def run_daily() -> dict[str, object]:
        context = get_current_context()
        dag_run = context["dag_run"]
        config = OHLCVConfig.from_env()
        scope = _scope_from_context(context, config)

        with EmpireDatabase.connect_from_env() as connection:
            result = run_yahoo_daily(
                run_service=RunService.from_connection(connection),
                connection=connection,
                object_store=ObjectStore.from_connection(connection),
                config=config,
                scope=scope,
                run_type="airflow",
                runner="airflow",
                runner_ref={
                    "dag_id": DAG_ID,
                    "dag_run_id": str(dag_run.run_id),
                },
            )

        payload = result.to_dict()
        log.info(
            "Completed Yahoo daily run %s for %s with JSON report %s and "
            "health PDF %s, benchmark PDF %s (%s)",
            payload["run_id"],
            payload["scope"]["effective_date"],
            payload["report_object_id"],
            payload["pdf_report_object_id"],
            payload["benchmark_pdf_report_object_id"],
            payload["report_outcome"],
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
                "Yahoo daily result has no qualifying technical-indicator "
                "completion signal; dispatch skipped"
            )
            raise AirflowSkipException(
                "No qualifying technical-indicator completion signal."
            )
        log.info(
            "Prepared technical-indicator dispatch for Yahoo run %s and %s",
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


stonks_ohlcv_yahoo_daily_scrape_dag = stonks_ohlcv_yahoo_daily_scrape()
