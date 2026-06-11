from __future__ import annotations

from datetime import datetime
from uuid import UUID

from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore
from empire_stonks_securities import verify_stonks_securities_daily_sources


@dag(
    dag_id="stonks_securities_daily_verify",
    start_date=datetime(2026, 6, 11),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "securities", "sec", "verify", "manual"],
)
def stonks_securities_daily_verify():
    @task(task_id="verify_sec_sources")
    def verify_sec_sources() -> dict:
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        input_run_id = _input_run_id_from_conf(conf)

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            result = verify_stonks_securities_daily_sources(
                object_store=object_store,
                input_run_id=input_run_id,
            )

        return result.to_dict()

    verify_sec_sources()


def _input_run_id_from_conf(conf: dict) -> UUID:
    input_run_id = conf.get("input_run_id")
    if not input_run_id:
        raise RuntimeError("Provide input_run_id in dag_run.conf.")
    return UUID(str(input_run_id))


stonks_securities_daily_verify_dag = stonks_securities_daily_verify()
