from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore
from empire_stonks_securities import (
    ValidationRunContext,
    generate_phase_2a_validation_report,
    write_validation_report_to_object_store,
)


log = logging.getLogger(__name__)


@dag(
    dag_id="stonks_securities_daily_validation",
    start_date=datetime(2026, 6, 19),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "securities", "sec", "validation", "manual"],
)
def stonks_securities_daily_validation():
    @task(task_id="generate_validation_report")
    def generate_validation_report() -> dict:
        context = get_current_context()
        dag_run = context["dag_run"]
        conf = dag_run.conf or {}
        input_run_id = _input_run_id_from_conf(conf)
        generated_at = datetime.now(UTC)
        run_context = ValidationRunContext(
            dag_id=dag_run.dag_id,
            run_id=dag_run.run_id,
            source_run_id=str(input_run_id),
            logical_date=str(context.get("logical_date")),
            environment="airflow",
        )

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            report = generate_phase_2a_validation_report(
                connection=conn,
                run_context=run_context,
                source_run_id=str(input_run_id),
                generated_at=generated_at,
            )
            stored = write_validation_report_to_object_store(
                report=report,
                object_store=object_store,
                generated_at=generated_at,
            )

        summary = report["summary"]
        log.info(
            "Stonks securities validation status=%s observations=%s issuers=%s "
            "securities=%s listings=%s warnings=%s failures=%s path=%s object_id=%s",
            summary["status"],
            summary["observations_total"],
            summary["issuers_total"],
            summary["securities_total"],
            summary["listings_total"],
            summary["warnings_total"],
            summary["failures_total"],
            f"{stored.object_key}/{stored.filename}",
            stored.object_id,
        )
        return {
            "summary": summary,
            "object_key": stored.object_key,
            "filename": stored.filename,
            "object_id": str(stored.object_id),
        }

    generate_validation_report()


def _input_run_id_from_conf(conf: dict) -> UUID:
    input_run_id = conf.get("input_run_id")
    if not input_run_id:
        raise RuntimeError("Provide input_run_id in dag_run.conf.")
    return UUID(str(input_run_id))


stonks_securities_daily_validation_dag = stonks_securities_daily_validation()
