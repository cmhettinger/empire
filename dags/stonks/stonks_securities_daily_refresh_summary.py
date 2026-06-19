from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore
from empire_stonks_securities import (
    DailySummaryRunContext,
    generate_daily_refresh_summary_report,
    write_daily_summary_report_to_object_store,
)


log = logging.getLogger(__name__)


@dag(
    dag_id="stonks_securities_daily_refresh_summary",
    start_date=datetime(2026, 6, 19),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "securities", "sec", "summary", "manual"],
)
def stonks_securities_daily_refresh_summary():
    @task(task_id="generate_daily_refresh_summary")
    def generate_daily_refresh_summary() -> dict:
        context = get_current_context()
        dag_run = context["dag_run"]
        conf = dag_run.conf or {}
        input_run_id = _input_run_id_from_conf(conf)
        generated_at = datetime.now(UTC)
        run_context = DailySummaryRunContext(
            dag_id=dag_run.dag_id,
            run_id=dag_run.run_id,
            source_run_id=str(input_run_id),
            logical_date=str(context.get("logical_date")),
            environment="airflow",
        )

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            report = generate_daily_refresh_summary_report(
                connection=conn,
                object_store=object_store,
                run_context=run_context,
                source_run_id=str(input_run_id),
                validation_report_object_id=_optional_object_id(
                    conf.get("validation_report_object_id")
                ),
                conflict_report_object_id=_optional_object_id(
                    conf.get("conflict_report_object_id")
                ),
                generated_at=generated_at,
            )
            stored = write_daily_summary_report_to_object_store(
                report=report,
                object_store=object_store,
                generated_at=generated_at,
            )

        summary = report["summary"]
        log.info(
            "Stonks securities daily summary status=%s inputs_seen=%s inputs_missing=%s "
            "inputs_unchanged=%s validation_status=%s conflict_status=%s warnings=%s "
            "failures=%s path=%s object_id=%s",
            summary["status"],
            summary["inputs_seen"],
            summary["inputs_missing"],
            summary["inputs_unchanged"],
            summary["validation_status"],
            summary["conflict_status"],
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

    generate_daily_refresh_summary()


def _input_run_id_from_conf(conf: dict) -> UUID:
    input_run_id = conf.get("input_run_id")
    if not input_run_id:
        raise RuntimeError("Provide input_run_id in dag_run.conf.")
    return UUID(str(input_run_id))


def _optional_object_id(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    return text


stonks_securities_daily_refresh_summary_dag = stonks_securities_daily_refresh_summary()
