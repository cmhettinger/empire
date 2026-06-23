from __future__ import annotations

from datetime import datetime

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase
from empire_stonks_securities import (
    input_run_id_from_conf,
    pass_through_conf,
    upsert_sec_issuers_from_provider_observations,
)


@dag(
    dag_id="stonks_securities_daily_issuers",
    start_date=datetime(2026, 6, 18),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "securities", "sec", "issuers", "manual"],
)
def stonks_securities_daily_issuers():
    @task(task_id="upsert_sec_issuers")
    def upsert_sec_issuers() -> dict:
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        input_run_id = input_run_id_from_conf(conf)

        with EmpireDatabase.connect_from_env() as conn:
            result = upsert_sec_issuers_from_provider_observations(
                connection=conn,
                source_run_id=input_run_id,
            )

        return result.to_dict()

    issuer_result = upsert_sec_issuers()
    trigger_securities = TriggerDagRunOperator(
        task_id="trigger_stonks_securities_daily_securities",
        trigger_dag_id="stonks_securities_daily_securities",
        conf=pass_through_conf(),
    )

    issuer_result >> trigger_securities

stonks_securities_daily_issuers_dag = stonks_securities_daily_issuers()
