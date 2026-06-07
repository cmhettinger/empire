from __future__ import annotations

import logging
from datetime import datetime

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore

log = logging.getLogger(__name__)

DEFAULT_CLEANUP_BATCH_SIZE = 100


@dag(
    dag_id="util_daily_clean",
    start_date=datetime(2026, 6, 7),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["utils", "object-store", "manual"],
)
def util_daily_clean():
    @task(task_id="cleanup_expired_objects")
    def cleanup_expired_objects() -> dict:
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        batch_size = _batch_size_from_conf(conf)

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            result = object_store.cleanup_expired_objects(batch_size=batch_size)

        log.info(
            "Completed object-store cleanup with batch_size=%s cleaned_count=%s "
            "cleaned_bytes=%s",
            batch_size,
            result.cleaned_count,
            _format_bytes(result.cleaned_bytes),
        )
        for root_stat in result.root_stats:
            log.info(
                "Object-store cleanup root=%s cleaned_count=%s cleaned_bytes=%s",
                root_stat.storage_root_name,
                root_stat.cleaned_count,
                _format_bytes(root_stat.cleaned_bytes),
            )
        if not result.root_stats:
            log.info("Object-store cleanup found no expired objects to clean.")

        return {
            "batch_size": batch_size,
            "cleaned_count": result.cleaned_count,
            "cleaned_bytes": result.cleaned_bytes,
            "cleaned_bytes_human": _format_bytes(result.cleaned_bytes),
            "root_stats": [
                {
                    "storage_root_name": root_stat.storage_root_name,
                    "cleaned_count": root_stat.cleaned_count,
                    "cleaned_bytes": root_stat.cleaned_bytes,
                    "cleaned_bytes_human": _format_bytes(root_stat.cleaned_bytes),
                }
                for root_stat in result.root_stats
            ],
        }

    cleanup_result = cleanup_expired_objects()
    trigger_purge = TriggerDagRunOperator(
        task_id="trigger_util_daily_purge",
        trigger_dag_id="util_daily_purge",
        conf={
            "batch_size": (
                "{{ (dag_run.conf or {}).get("
                "'purge_batch_size', (dag_run.conf or {}).get('batch_size', 100)"
                ") }}"
            )
        },
    )

    cleanup_result >> trigger_purge


def _batch_size_from_conf(conf: dict) -> int:
    raw_batch_size = conf.get("batch_size", DEFAULT_CLEANUP_BATCH_SIZE)
    batch_size = int(raw_batch_size)
    if batch_size <= 0:
        raise RuntimeError("dag_run.conf batch_size must be positive")
    return batch_size


def _format_bytes(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024


util_daily_clean_dag = util_daily_clean()
