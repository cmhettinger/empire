from __future__ import annotations

from datetime import datetime
import logging
import os
import time
from uuid import UUID

from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_youtube.downloader import (
    DOWNLOAD_REPORT_FILENAME,
    DOWNLOAD_REPORT_OBJECT_KIND,
    YouTubeDownloadError,
    download_entry_to_object_store,
    find_download_entry,
    iter_download_entries,
    load_library_plan_from_object_id,
    load_library_plan_from_run_id,
)

log = logging.getLogger(__name__)


@dag(
    dag_id="youtube_download_plan",
    start_date=datetime(2026, 5, 24),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["youtube", "downloader", "manual"],
)
def youtube_download_plan():
    @task(task_id="list_download_video_ids")
    def list_download_video_ids() -> list[str]:
        context = get_current_context()
        conf = context["dag_run"].conf or {}

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            plan = _load_plan_from_conf(conf, object_store)

        video_ids = [entry.video_id for entry in iter_download_entries(plan)]
        requested_video_ids = conf.get("video_ids")
        if requested_video_ids:
            requested = {str(video_id) for video_id in requested_video_ids}
            video_ids = [video_id for video_id in video_ids if video_id in requested]
        single_video_id = conf.get("video_id")
        if single_video_id:
            video_ids = [video_id for video_id in video_ids if video_id == single_video_id]

        log.info("Prepared %s YouTube download task(s)", len(video_ids))
        return video_ids

    @task(task_id="download_one_video", pool="youtube_download")
    def download_one_video(video_id: str) -> dict[str, str | bool | int | None]:
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        delay_seconds = int(
            os.environ.get("EMPIRE_YOUTUBE_DOWNLOAD_TASK_DELAY_SECONDS", "0")
        )
        cleanup_on_failure = bool(conf.get("cleanup_on_failure", False))
        if delay_seconds > 0:
            log.info("Sleeping %s seconds before downloading %s", delay_seconds, video_id)
            time.sleep(delay_seconds)

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            run_service = RunService.from_connection(conn)
            plan = _load_plan_from_conf(conf, object_store)
            entry = find_download_entry(plan, video_id=video_id)
            ctx = run_service.start_run(
                domain="youtube",
                job_name="youtube_download",
                subject_key=entry.video_id,
                effective_date=None,
                run_type="airflow",
                runner="airflow",
                runner_ref={
                    "dag_id": "youtube_download_plan",
                    "task_id": "download_one_video",
                },
                params={
                    "video_id": entry.video_id,
                    "source_url": entry.source_url,
                    "object_key": entry.object_key,
                    "cleanup_on_failure": cleanup_on_failure,
                },
            )

            try:
                result = download_entry_to_object_store(
                    entry=entry,
                    object_store=object_store,
                    run_context=ctx,
                    cleanup_on_failure=cleanup_on_failure,
                )
                report = _write_report(object_store, ctx, result.to_dict())
                run_service.complete_run(
                    ctx.run_id,
                    summary={**result.to_dict(), "report_object_id": str(report.object_id)},
                )
                log.info("Completed YouTube download for %s: %s", video_id, result.status)
                return {
                    **result.to_dict(),
                    "run_id": str(ctx.run_id),
                    "report_object_id": str(report.object_id),
                }
            except YouTubeDownloadError as exc:
                result = exc.result
                report = _write_report(object_store, ctx, result.to_dict())
                run_service.fail_run(
                    ctx.run_id,
                    error_message=result.error_message or str(exc),
                    summary={**result.to_dict(), "report_object_id": str(report.object_id)},
                )
                log.exception("Failed YouTube download for %s", video_id)
                raise

    download_one_video.expand(video_id=list_download_video_ids())


def _load_plan_from_conf(conf: dict, object_store: ObjectStore) -> dict:
    plan_object_id = conf.get("plan_object_id")
    plan_run_id = conf.get("plan_run_id")
    provided = [value for value in (plan_object_id, plan_run_id) if value]
    if len(provided) != 1:
        raise RuntimeError(
            "Provide exactly one of plan_object_id or plan_run_id in dag_run.conf."
        )
    if plan_object_id:
        UUID(str(plan_object_id))
        return load_library_plan_from_object_id(object_store, plan_object_id)
    UUID(str(plan_run_id))
    return load_library_plan_from_run_id(object_store, plan_run_id)


def _write_report(object_store: ObjectStore, ctx, result: dict):
    import json

    data = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode(
        "utf-8"
    )
    return object_store.put_bytes(
        run_context=ctx,
        storage_root="global",
        object_key=f"scraper/youtube/download/{ctx.run_id}",
        filename=DOWNLOAD_REPORT_FILENAME,
        data=data,
        content_type="application/json",
        object_kind=DOWNLOAD_REPORT_OBJECT_KIND,
        metadata={
            "video_id": result["video_id"],
            "status": result["status"],
            "skipped": result["skipped"],
        },
    )


youtube_download_plan_dag = youtube_download_plan()
