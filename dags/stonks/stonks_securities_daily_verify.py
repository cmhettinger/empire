from __future__ import annotations

import logging
from datetime import UTC, datetime

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_securities import (
    VerifyRunContext,
    generate_verify_report,
    input_run_id_from_conf,
    verify_stonks_securities_daily_sources,
    verify_to_observations_conf,
    write_verify_report_to_object_store,
)


log = logging.getLogger(__name__)


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
        dag_run = context["dag_run"]
        conf = dag_run.conf or {}
        input_run_id = input_run_id_from_conf(conf)
        generated_at = datetime.now(UTC)
        logical_date = str(context.get("logical_date"))
        run_context = VerifyRunContext(
            dag_id=dag_run.dag_id,
            run_id=dag_run.run_id,
            source_run_id=str(input_run_id),
            logical_date=logical_date,
            environment="airflow",
        )

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            storage_run_context = RunService.from_connection(conn).get_run_context(
                input_run_id
            )
            result = verify_stonks_securities_daily_sources(
                object_store=object_store,
                input_run_id=input_run_id,
            )
            report = generate_verify_report(
                result=result,
                run_context=run_context,
                generated_at=generated_at,
            )
            stored = write_verify_report_to_object_store(
                report=report,
                object_store=object_store,
                generated_at=generated_at,
                logical_date=logical_date,
                storage_run_context=storage_run_context,
            )

        summary = report["summary"]
        log.info(
            "Stonks securities verify status=%s healthy=%s inputs_checked=%s "
            "inputs_missing=%s warnings=%s failures=%s path=%s object_id=%s",
            summary["status"],
            report["healthy"],
            summary["inputs_checked"],
            summary["inputs_missing"],
            summary["warnings_total"],
            summary["failures_total"],
            f"{stored.object_key}/{stored.filename}",
            stored.object_id,
        )
        return {
            **result.to_dict(),
            "summary": report["summary"],
            "object_key": stored.object_key,
            "filename": stored.filename,
            "object_id": str(stored.object_id),
        }

    verify_result = verify_sec_sources()
    trigger_observations = TriggerDagRunOperator(
        task_id="trigger_stonks_securities_daily_observations",
        trigger_dag_id="stonks_securities_daily_observations",
        conf=verify_to_observations_conf(),
    )

    verify_result >> trigger_observations

stonks_securities_daily_verify_dag = stonks_securities_daily_verify()
