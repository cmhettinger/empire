from __future__ import annotations

from datetime import datetime

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import dag, task
from empire_core import EmpireDatabase
from empire_stonks_securities import upsert_sec_securities_from_provider_observations


@dag(
    dag_id="stonks_securities_daily_securities",
    start_date=datetime(2026, 6, 18),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "securities", "sec", "security-master", "manual"],
)
def stonks_securities_daily_securities():
    @task(task_id="upsert_sec_securities")
    def upsert_sec_securities() -> dict:
        with EmpireDatabase.connect_from_env() as conn:
            result = upsert_sec_securities_from_provider_observations(connection=conn)

        return result.to_dict()

    security_result = upsert_sec_securities()
    trigger_listings = TriggerDagRunOperator(
        task_id="trigger_stonks_securities_daily_listings",
        trigger_dag_id="stonks_securities_daily_listings",
        conf={
            "input_run_id": "{{ dag_run.conf.get('input_run_id') }}"
        },
    )

    security_result >> trigger_listings


stonks_securities_daily_securities_dag = stonks_securities_daily_securities()
