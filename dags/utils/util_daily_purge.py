from __future__ import annotations

import logging
from datetime import datetime

from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore

log = logging.getLogger(__name__)

DEFAULT_PURGE_BATCH_SIZE = 100


@dag(
    dag_id="util_daily_purge",
    start_date=datetime(2026, 6, 7),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["utils", "object-store", "manual"],
)
def util_daily_purge():
    @task(task_id="purge_deleted_objects")
    def purge_deleted_objects() -> dict:
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        batch_size = _batch_size_from_conf(conf)

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            result = object_store.purge_deleted_objects_all(batch_size=batch_size)

        log.info(
            "Completed object-store purge with batch_size=%s purged_count=%s",
            batch_size,
            result.purged_count,
        )
        for root_stat in result.root_stats:
            log.info(
                "Object-store purge root=%s purged_count=%s",
                root_stat.storage_root_name,
                root_stat.purged_count,
            )
        if not result.root_stats:
            log.info("Object-store purge found no tombstoned records to purge.")

        return {
            "batch_size": batch_size,
            "purged_count": result.purged_count,
            "root_stats": [
                {
                    "storage_root_name": root_stat.storage_root_name,
                    "purged_count": root_stat.purged_count,
                }
                for root_stat in result.root_stats
            ],
        }

    purge_deleted_objects()


def _batch_size_from_conf(conf: dict) -> int:
    raw_batch_size = conf.get("batch_size", DEFAULT_PURGE_BATCH_SIZE)
    batch_size = int(raw_batch_size)
    if batch_size <= 0:
        raise RuntimeError("dag_run.conf batch_size must be positive")
    return batch_size


util_daily_purge_dag = util_daily_purge()
