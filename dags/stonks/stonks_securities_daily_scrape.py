from __future__ import annotations

import logging
from datetime import datetime

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import dag, task
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_securities import (
    DEFAULT_DAILY_SOURCE_KEYS,
    SecDownloader,
    load_config_by_logical_name,
)

log = logging.getLogger(__name__)

try:
    from empire_stonks_securities import run_stonks_securities_daily_to_object_store
except ImportError:
    from empire_stonks_securities import (
        run_stonks_security_daily_to_object_store as run_stonks_securities_daily_to_object_store,
    )


@dag(
    dag_id="stonks_securities_daily_scrape",
    start_date=datetime(2026, 6, 11),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "securities", "sec", "manual"],
)
def stonks_securities_daily_scrape():
    @task(task_id="collect_sec_sources")
    def collect_sec_sources() -> dict[str, object]:
        with EmpireDatabase.connect_from_env() as conn:
            run_service = RunService.from_connection(conn)
            object_store = ObjectStore.from_connection(conn)
            config = load_config_by_logical_name(object_store)
            downloader = SecDownloader(config=config)

            result = run_stonks_securities_daily_to_object_store(
                config=config,
                downloader=downloader,
                run_service=run_service,
                object_store=object_store,
                run_type="airflow",
                runner="airflow",
                runner_ref={"dag_id": "stonks_securities_daily_scrape"},
                source_keys=DEFAULT_DAILY_SOURCE_KEYS,
            )

        log.info(
            "Completed stonks securities daily run %s with %s downloads and %s skips",
            result.run_context.run_id,
            result.downloaded_count,
            result.skipped_count,
        )
        return {
            "run_id": str(result.run_context.run_id),
            "downloaded_count": result.downloaded_count,
            "skipped_count": result.skipped_count,
            "source_count": len(result.results),
            "sources": [
                {
                    "source_code": item.source_code,
                    "status": item.status,
                    "object_key": item.object_key,
                    "filename": item.filename,
                    "metadata_filename": item.metadata_filename,
                    "object_id": item.object_id,
                    "metadata_object_id": item.metadata_object_id,
                }
                for item in result.results
            ],
        }

    scrape_result = collect_sec_sources()
    trigger_verify = TriggerDagRunOperator(
        task_id="trigger_stonks_securities_daily_verify",
        trigger_dag_id="stonks_securities_daily_verify",
        conf={
            "input_run_id": "{{ ti.xcom_pull(task_ids='collect_sec_sources')['run_id'] }}"
        },
    )

    scrape_result >> trigger_verify


stonks_securities_daily_scrape_dag = stonks_securities_daily_scrape()
