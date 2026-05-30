from __future__ import annotations

from datetime import datetime
import logging
from uuid import UUID

from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_youtube import YouTubeScrapeProcessor, run_youtube_processor_to_object_store
from empire_youtube.scripts.process import load_scrape_payload, parse_args

log = logging.getLogger(__name__)


@dag(
    dag_id="youtube_process_plan",
    start_date=datetime(2026, 5, 24),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["youtube", "processor", "manual"],
)
def youtube_process_plan():
    @task(task_id="process_youtube_library_plan")
    def process_youtube_library_plan() -> dict[str, str | int | list[str]]:
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        args = _processor_args_from_conf(conf)

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            run_service = RunService.from_connection(conn)
            scrape_payload = load_scrape_payload(args, object_store)
            processor = YouTubeScrapeProcessor()

            result = run_youtube_processor_to_object_store(
                scrape_payload=scrape_payload,
                processor=processor,
                run_service=run_service,
                object_store=object_store,
                run_type="airflow",
                runner="airflow",
                runner_ref={"dag_id": "youtube_process_plan"},
                source=args.input_source,
            )

        video_ids = [entry.video_id for entry in result.library_plan.entries]
        log.info(
            "Completed YouTube processor run %s with %s entries, %s sidecars, %s skips",
            result.run_context.run_id,
            len(result.library_plan.entries),
            result.sidecar_object_count,
            result.skipped_sidecar_count,
        )
        return {
            "run_id": str(result.run_context.run_id),
            "source_video_count": result.library_plan.source_video_count,
            "plan_entry_count": len(result.library_plan.entries),
            "sidecar_object_count": result.sidecar_object_count,
            "skipped_sidecar_count": result.skipped_sidecar_count,
            "stored_object_id": str(result.stored_object.object_id),
            "object_key": result.stored_object.object_key,
            "filename": result.stored_object.filename,
            "video_ids": video_ids,
        }

    process_youtube_library_plan()


def _processor_args_from_conf(conf: dict):
    input_file = conf.get("input_file")
    input_object_id = conf.get("input_object_id") or conf.get("scraper_object_id")
    input_run_id = conf.get("input_run_id") or conf.get("scraper_run_id")
    provided = [
        value
        for value in (input_file, input_object_id, input_run_id)
        if value
    ]
    if len(provided) != 1:
        raise RuntimeError(
            "Provide exactly one of input_file, input_object_id/scraper_object_id, "
            "or input_run_id/scraper_run_id in dag_run.conf."
        )

    argv = []
    if input_file:
        argv.extend(["--input-file", str(input_file)])
    elif input_object_id:
        UUID(str(input_object_id))
        argv.extend(["--input-object-id", str(input_object_id)])
    else:
        UUID(str(input_run_id))
        argv.extend(["--input-run-id", str(input_run_id)])
    return parse_args(argv)


youtube_process_plan_dag = youtube_process_plan()
