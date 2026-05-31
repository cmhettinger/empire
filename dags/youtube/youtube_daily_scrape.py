from __future__ import annotations

from datetime import datetime
import logging

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import dag, task
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_youtube import (
    YouTubeScraper,
    load_config_by_logical_name,
    run_youtube_scraper_to_object_store,
)

log = logging.getLogger(__name__)


@dag(
    dag_id="youtube_daily_scrape",
    start_date=datetime(2026, 5, 24),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["youtube", "scraper", "manual"],
)
def youtube_daily_scrape():
    @task(task_id="scrape_youtube_metadata")
    def scrape_youtube_metadata() -> dict[str, str | int]:
        with EmpireDatabase.connect_from_env() as conn:
            run_service = RunService.from_connection(conn)
            object_store = ObjectStore.from_connection(conn)
            config = load_config_by_logical_name(object_store)
            scraper = YouTubeScraper(config=config)

            result = run_youtube_scraper_to_object_store(
                config=config,
                scraper=scraper,
                run_service=run_service,
                object_store=object_store,
                run_type="airflow",
                runner="airflow",
                runner_ref={"dag_id": "youtube_daily_scrape"},
            )

        log.info(
            "Completed YouTube daily scrape run %s with %s videos",
            result.run_context.run_id,
            len(result.scrape_result.videos),
        )
        return {
            "run_id": str(result.run_context.run_id),
            "video_count": len(result.scrape_result.videos),
            "stored_object_id": str(result.stored_object.object_id),
            "object_key": result.stored_object.object_key,
            "filename": result.stored_object.filename,
        }

    scrape_result = scrape_youtube_metadata()
    trigger_process_plan = TriggerDagRunOperator(
        task_id="trigger_youtube_process_plan",
        trigger_dag_id="youtube_process_plan",
        conf={
            "input_run_id": "{{ ti.xcom_pull(task_ids='scrape_youtube_metadata')['run_id'] }}"
        },
    )

    scrape_result >> trigger_process_plan


youtube_daily_scrape_dag = youtube_daily_scrape()
