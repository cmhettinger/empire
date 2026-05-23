from __future__ import annotations

from datetime import datetime
import logging
from uuid import UUID

from airflow.sdk import dag, task
from empire_core import EmpireDatabase, ObjectStore, RunService

log = logging.getLogger(__name__)


@dag(
    dag_id="verify_core_execution",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags=["verify", "smoke", "core"],
)
def verify_core_execution():
    @task(task_id="verify_core_run_and_object_store")
    def verify_core_run_and_object_store() -> dict[str, str]:
        run_id: UUID | None = None

        with EmpireDatabase.connect_from_env() as conn:
            run_service = RunService.from_connection(conn)
            object_store = ObjectStore.from_connection(conn)

            ctx = run_service.start_run(
                domain="verify",
                job_name="verify_core_execution",
                subject_key="airflow-smoke",
                effective_date=datetime.utcnow().date(),
                run_type="airflow",
                runner="airflow",
                runner_ref={"dag_id": "verify_core_execution"},
                heartbeat_timeout_seconds=300,
                params={"purpose": "core smoke test"},
            )
            run_id = ctx.run_id

            try:
                timestamp = datetime.utcnow().isoformat(timespec="seconds")
                object_key = f"verify/core/{timestamp}/{ctx.run_id}"

                global_object = object_store.put_bytes(
                    run_context=ctx,
                    storage_root="global",
                    object_key=object_key,
                    filename="global-smoke.txt",
                    data=(
                        "Empire core smoke test\n"
                        f"storage_root=global\n"
                        f"run_id={ctx.run_id}\n"
                        f"created_at={timestamp}Z\n"
                    ).encode("utf-8"),
                    content_type="text/plain",
                    object_kind="smoke_test",
                    metadata={"storage_root": "global"},
                )

                jellyfin_object = object_store.put_bytes(
                    run_context=ctx,
                    storage_root="jellyfin",
                    object_key=object_key,
                    filename="jellyfin-smoke.txt",
                    data=(
                        "Empire core smoke test\n"
                        f"storage_root=jellyfin\n"
                        f"run_id={ctx.run_id}\n"
                        f"created_at={timestamp}Z\n"
                    ).encode("utf-8"),
                    content_type="text/plain",
                    object_kind="smoke_test",
                    metadata={"storage_root": "jellyfin"},
                )

                completed = run_service.complete_run(
                    ctx.run_id,
                    summary={
                        "stored_object_count": 2,
                        "global_object_id": str(global_object.object_id),
                        "jellyfin_object_id": str(jellyfin_object.object_id),
                    },
                )

                log.info("Completed empire-core smoke run %s", completed.run_id)
                return {
                    "run_id": str(completed.run_id),
                    "global_object_id": str(global_object.object_id),
                    "jellyfin_object_id": str(jellyfin_object.object_id),
                }
            except Exception as exc:
                run_service.fail_run(ctx.run_id, error_message=str(exc))
                raise

        raise RuntimeError(f"Unable to verify empire-core run {run_id}")

    verify_core_run_and_object_store()


verify_core_execution_dag = verify_core_execution()
