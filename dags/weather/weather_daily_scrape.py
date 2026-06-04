from __future__ import annotations

import logging
from datetime import datetime

from airflow.sdk import dag, task
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_weather import (
    WeatherCollector,
    load_config_by_logical_name,
    run_weather_collection_to_object_store,
)

log = logging.getLogger(__name__)


@dag(
    dag_id="weather_daily_scrape",
    start_date=datetime(2026, 6, 4),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["weather", "scraper", "manual"],
)
def weather_daily_scrape():
    @task(task_id="collect_weather")
    def collect_weather() -> dict[str, str | int]:
        with EmpireDatabase.connect_from_env() as conn:
            run_service = RunService.from_connection(conn)
            object_store = ObjectStore.from_connection(conn)
            config = load_config_by_logical_name(object_store)
            collector = WeatherCollector(config=config)

            result = run_weather_collection_to_object_store(
                config=config,
                collector=collector,
                run_service=run_service,
                object_store=object_store,
                run_type="airflow",
                runner="airflow",
                runner_ref={"dag_id": "weather_daily_scrape"},
            )

        log.info(
            "Completed weather collection run %s with %s locations and %s raw responses",
            result.run_context.run_id,
            result.collection_result.location_count,
            result.raw_object_count,
        )
        return {
            "run_id": str(result.run_context.run_id),
            "location_count": result.collection_result.location_count,
            "raw_object_count": result.raw_object_count,
            "stored_object_id": str(result.stored_object.object_id),
            "object_key": result.stored_object.object_key,
            "filename": result.stored_object.filename,
        }

    collect_weather()


weather_daily_scrape_dag = weather_daily_scrape()
