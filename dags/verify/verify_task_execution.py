from __future__ import annotations

from datetime import datetime
import logging

from airflow.sdk import dag, task

log = logging.getLogger(__name__)


@dag(
    dag_id="verify_task_execution",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags=["verify", "smoke"],
)
def verify_task_execution():
    @task(task_id="hello_world")
    def hello_world() -> str:
        print("HELLO_STDOUT: hello world")
        log.warning("HELLO_LOGGER: hello world")
        logging.getLogger("airflow.task").warning("HELLO_AIRFLOW_TASK_LOGGER: hello world")
        return "ok"

    hello_world()


verify_task_execution_dag = verify_task_execution()