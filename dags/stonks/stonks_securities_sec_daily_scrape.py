from __future__ import annotations

import logging
from datetime import UTC, datetime

from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_securities import (
    DEFAULT_DAILY_REFRESH_DAG_ID,
    DEFAULT_DAILY_SOURCE_KEYS,
    DailyRefreshRunContext,
    SecDownloader,
    collect_sec_sources_stage,
    generate_conflict_report_stage,
    generate_daily_refresh_summary_stage,
    generate_validation_report_stage,
    load_config_by_logical_name,
    upsert_sec_issuers_stage,
    upsert_sec_listings_stage,
    upsert_sec_securities_stage,
    verify_sec_sources_stage,
    write_sec_observations_stage,
)


log = logging.getLogger(__name__)


def _airflow_run_context() -> DailyRefreshRunContext:
    context = get_current_context()
    dag_run = context["dag_run"]
    return DailyRefreshRunContext(
        workflow_id=dag_run.dag_id,
        run_id=dag_run.run_id,
        logical_date=str(context.get("logical_date")),
        environment="airflow",
    )


@dag(
    dag_id=DEFAULT_DAILY_REFRESH_DAG_ID,
    start_date=datetime(2026, 7, 2),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "securities", "sec", "manual"],
)
def stonks_securities_sec_daily_scrape():
    @task(task_id="collect_sec_sources")
    def collect_sec_sources() -> dict[str, object]:
        with EmpireDatabase.connect_from_env() as conn:
            run_service = RunService.from_connection(conn)
            object_store = ObjectStore.from_connection(conn)
            config = load_config_by_logical_name(object_store)
            downloader = SecDownloader(config=config)

            result = collect_sec_sources_stage(
                config=config,
                downloader=downloader,
                run_service=run_service,
                object_store=object_store,
                run_type="airflow",
                runner="airflow",
                runner_ref={"dag_id": DEFAULT_DAILY_REFRESH_DAG_ID},
                source_keys=DEFAULT_DAILY_SOURCE_KEYS,
            )

        payload = result.to_dict()
        log.info(
            "Completed stonks securities SEC daily scrape run %s with %s downloads "
            "and %s skips",
            payload["source_run_id"],
            payload["downloaded_count"],
            payload["skipped_count"],
        )
        return payload

    @task(task_id="verify_sec_sources")
    def verify_sec_sources(scrape_result: dict[str, object]) -> dict[str, object]:
        source_run_id = str(scrape_result["source_run_id"])
        generated_at = datetime.now(UTC)
        run_context = _airflow_run_context()

        with EmpireDatabase.connect_from_env() as conn:
            result = verify_sec_sources_stage(
                object_store=ObjectStore.from_connection(conn),
                run_service=RunService.from_connection(conn),
                source_run_id=source_run_id,
                run_context=run_context,
                generated_at=generated_at,
            )

        payload = result.to_dict()
        summary = payload["summary"]
        log.info(
            "Stonks securities verify status=%s inputs_checked=%s warnings=%s "
            "failures=%s object_id=%s",
            summary["status"],
            summary["inputs_checked"],
            summary["warnings_total"],
            summary["failures_total"],
            payload["object_id"],
        )
        return payload

    @task(task_id="write_sec_observations")
    def write_sec_observations(verify_result: dict[str, object]) -> dict[str, object]:
        source_run_id = str(verify_result["source_run_id"])

        with EmpireDatabase.connect_from_env() as conn:
            result = write_sec_observations_stage(
                connection=conn,
                object_store=ObjectStore.from_connection(conn),
                source_run_id=source_run_id,
            )

        return result.to_dict()

    @task(task_id="upsert_sec_issuers")
    def upsert_sec_issuers(
        observations_result: dict[str, object],
    ) -> dict[str, object]:
        source_run_id = str(observations_result["source_run_id"])

        with EmpireDatabase.connect_from_env() as conn:
            result = upsert_sec_issuers_stage(
                connection=conn,
                source_run_id=source_run_id,
            )

        return result.to_dict()

    @task(task_id="upsert_sec_securities")
    def upsert_sec_securities(issuers_result: dict[str, object]) -> dict[str, object]:
        source_run_id = str(issuers_result["source_run_id"])

        with EmpireDatabase.connect_from_env() as conn:
            result = upsert_sec_securities_stage(
                connection=conn,
                source_run_id=source_run_id,
            )

        return result.to_dict()

    @task(task_id="upsert_sec_listings")
    def upsert_sec_listings(
        securities_result: dict[str, object],
    ) -> dict[str, object]:
        source_run_id = str(securities_result["source_run_id"])

        with EmpireDatabase.connect_from_env() as conn:
            result = upsert_sec_listings_stage(
                connection=conn,
                source_run_id=source_run_id,
            )

        return result.to_dict()

    @task(task_id="generate_validation_report")
    def generate_validation_report(
        listings_result: dict[str, object],
    ) -> dict[str, object]:
        source_run_id = str(listings_result["source_run_id"])
        generated_at = datetime.now(UTC)
        run_context = _airflow_run_context()

        with EmpireDatabase.connect_from_env() as conn:
            result = generate_validation_report_stage(
                connection=conn,
                object_store=ObjectStore.from_connection(conn),
                run_service=RunService.from_connection(conn),
                source_run_id=source_run_id,
                run_context=run_context,
                generated_at=generated_at,
            )

        return result.to_dict()

    @task(task_id="generate_conflict_report")
    def generate_conflict_report(
        validation_result: dict[str, object],
    ) -> dict[str, object]:
        source_run_id = str(validation_result["source_run_id"])
        generated_at = datetime.now(UTC)
        run_context = _airflow_run_context()

        with EmpireDatabase.connect_from_env() as conn:
            result = generate_conflict_report_stage(
                connection=conn,
                object_store=ObjectStore.from_connection(conn),
                run_service=RunService.from_connection(conn),
                source_run_id=source_run_id,
                run_context=run_context,
                generated_at=generated_at,
            )

        return result.to_dict()

    @task(task_id="generate_daily_refresh_summary")
    def generate_daily_refresh_summary(
        verify_result: dict[str, object],
        validation_result: dict[str, object],
        conflict_result: dict[str, object],
    ) -> dict[str, object]:
        source_run_id = str(conflict_result["source_run_id"])
        generated_at = datetime.now(UTC)
        run_context = _airflow_run_context()

        with EmpireDatabase.connect_from_env() as conn:
            result = generate_daily_refresh_summary_stage(
                connection=conn,
                object_store=ObjectStore.from_connection(conn),
                run_service=RunService.from_connection(conn),
                source_run_id=source_run_id,
                run_context=run_context,
                verify_report_object_id=verify_result.get("object_id"),
                validation_report_object_id=validation_result.get("object_id"),
                conflict_report_object_id=conflict_result.get("object_id"),
                generated_at=generated_at,
            )

        return result.to_dict()

    scrape_result = collect_sec_sources()
    verify_result = verify_sec_sources(scrape_result)
    observations_result = write_sec_observations(verify_result)
    issuers_result = upsert_sec_issuers(observations_result)
    securities_result = upsert_sec_securities(issuers_result)
    listings_result = upsert_sec_listings(securities_result)
    validation_result = generate_validation_report(listings_result)
    conflict_result = generate_conflict_report(validation_result)
    summary_result = generate_daily_refresh_summary(
        verify_result,
        validation_result,
        conflict_result,
    )

    (
        scrape_result
        >> verify_result
        >> observations_result
        >> issuers_result
        >> securities_result
        >> listings_result
        >> validation_result
        >> conflict_result
        >> summary_result
    )


stonks_securities_sec_daily_scrape_dag = stonks_securities_sec_daily_scrape()
