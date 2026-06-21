from __future__ import annotations

from datetime import datetime
from uuid import UUID

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore
from empire_stonks_securities import run_stonks_securities_daily_observation_writer


@dag(
    dag_id="stonks_securities_daily_observations",
    start_date=datetime(2026, 6, 18),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "securities", "sec", "observations", "manual"],
)
def stonks_securities_daily_observations():
    @task(task_id="write_sec_observations")
    def write_sec_observations() -> dict:
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        input_run_id = _input_run_id_from_conf(conf)

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            result = run_stonks_securities_daily_observation_writer(
                connection=conn,
                object_store=object_store,
                input_run_id=input_run_id,
            )

        return result.to_dict()

    observation_result = write_sec_observations()
    trigger_issuers = TriggerDagRunOperator(
        task_id="trigger_stonks_securities_daily_issuers",
        trigger_dag_id="stonks_securities_daily_issuers",
        conf={
            "input_run_id": "{{ dag_run.conf['input_run_id'] }}",
            "verify_report_object_id": "{{ dag_run.conf.get('verify_report_object_id') }}",
        },
    )

    observation_result >> trigger_issuers


def _input_run_id_from_conf(conf: dict) -> UUID:
    input_run_id = conf.get("input_run_id")
    if not input_run_id:
        raise RuntimeError("Provide input_run_id in dag_run.conf.")
    return UUID(str(input_run_id))


stonks_securities_daily_observations_dag = stonks_securities_daily_observations()
