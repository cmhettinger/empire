from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime

from airflow.sdk import dag, get_current_context, task
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_youtube import (
    YouTubeScrapeProcessor,
    YouTubeScraper,
    load_config_by_logical_name,
    run_youtube_processor_to_object_store,
    run_youtube_scraper_to_object_store,
)
from empire_youtube.downloader import (
    DOWNLOAD_REPORT_FILENAME,
    DOWNLOAD_REPORT_OBJECT_KIND,
    YouTubeDownloadError,
    download_entry_to_object_store,
    find_download_entry,
    iter_download_entries,
    load_library_plan_from_object_id,
)
from empire_youtube.retention import youtube_expires_at
from empire_youtube.runner import DEFAULT_STORAGE_KEY, youtube_run_object_key
from empire_youtube.scripts.process import load_scrape_payload, parse_args


log = logging.getLogger(__name__)

YOUTUBE_DAILY_SCRAPE_DAG_ID = "youtube_daily_scrape"
MINIMUM_DOWNLOAD_SUCCESS_RATE = 0.60


@dag(
    dag_id=YOUTUBE_DAILY_SCRAPE_DAG_ID,
    start_date=datetime(2026, 5, 24),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["youtube", "jellyfin", "manual"],
)
def youtube_daily_scrape():
    @task(task_id="scrape_youtube_metadata")
    def scrape_youtube_metadata() -> dict[str, str | int]:
        with EmpireDatabase.connect_from_env() as conn:
            run_service = RunService.from_connection(conn)
            object_store = ObjectStore.from_connection(conn)
            config = load_config_by_logical_name(object_store)
            scraper = YouTubeScraper(config=config)
            result = run_youtube_scraper_to_object_store(
                config=config,
                scraper=scraper,
                run_service=run_service,
                object_store=object_store,
                run_type="airflow",
                runner="airflow",
                runner_ref={"dag_id": YOUTUBE_DAILY_SCRAPE_DAG_ID},
            )

        log.info(
            "Completed YouTube daily scrape run %s with %s videos",
            result.run_context.run_id,
            len(result.scrape_result.videos),
        )
        return {
            "run_id": str(result.run_context.run_id),
            "video_count": len(result.scrape_result.videos),
            "stored_object_id": str(result.stored_object.object_id),
            "object_key": result.stored_object.object_key,
            "filename": result.stored_object.filename,
        }

    @task(task_id="process_youtube_library_plan")
    def process_youtube_library_plan(
        scrape_result: dict[str, str | int],
    ) -> dict[str, str | int | list[str]]:
        scrape_run_id = str(scrape_result["run_id"])
        args = parse_args(["--input-run-id", scrape_run_id])

        with EmpireDatabase.connect_from_env() as conn:
            object_store = ObjectStore.from_connection(conn)
            run_service = RunService.from_connection(conn)
            scrape_payload = load_scrape_payload(args, object_store)
            result = run_youtube_processor_to_object_store(
                scrape_payload=scrape_payload,
                processor=YouTubeScrapeProcessor(),
                run_service=run_service,
                object_store=object_store,
                run_type="airflow",
                runner="airflow",
                runner_ref={"dag_id": YOUTUBE_DAILY_SCRAPE_DAG_ID},
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

    @task(task_id="list_download_video_ids")
    def list_download_video_ids(plan_result: dict[str, str | int | list[str]]) -> list[str]:
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        plan_object_id = str(plan_result["stored_object_id"])

        with EmpireDatabase.connect_from_env() as conn:
            plan = load_library_plan_from_object_id(
                ObjectStore.from_connection(conn), plan_object_id
            )

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
    def download_one_video(
        video_id: str, plan_result: dict[str, str | int | list[str]]
    ) -> dict[str, str | bool | int | None]:
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
            plan = load_library_plan_from_object_id(
                object_store, str(plan_result["stored_object_id"])
            )
            entry = find_download_entry(plan, video_id=video_id)
            run_context = run_service.start_run(
                domain="youtube",
                job_name="youtube_download",
                subject_key=entry.video_id,
                effective_date=datetime.now(UTC).date(),
                run_type="airflow",
                runner="airflow",
                runner_ref={
                    "dag_id": YOUTUBE_DAILY_SCRAPE_DAG_ID,
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
                    run_context=run_context,
                    cleanup_on_failure=cleanup_on_failure,
                )
                report = _write_report(object_store, run_context, result.to_dict())
                run_service.complete_run(
                    run_context.run_id,
                    summary={**result.to_dict(), "report_object_id": str(report.object_id)},
                )
            except YouTubeDownloadError as exc:
                result = exc.result
                report = _write_report(object_store, run_context, result.to_dict())
                run_service.fail_run(
                    run_context.run_id,
                    error_message=result.error_message or str(exc),
                    summary={**result.to_dict(), "report_object_id": str(report.object_id)},
                )
                log.exception("Failed YouTube download for %s", video_id)
                return {
                    **result.to_dict(),
                    "run_id": str(run_context.run_id),
                    "report_object_id": str(report.object_id),
                }

        log.info("Completed YouTube download for %s: %s", video_id, result.status)
        return {
            **result.to_dict(),
            "run_id": str(run_context.run_id),
            "report_object_id": str(report.object_id),
        }

    @task(task_id="finalize_downloads", trigger_rule="all_done")
    def finalize_downloads(
        download_results: list[dict[str, str | bool | int | None]],
    ) -> dict[str, object]:
        summary = _summarize_download_results(download_results)
        log.info(
            "YouTube download summary: %s/%s successful (%.1f%%), %s failed",
            summary["successful_count"],
            summary["total_count"],
            summary["success_rate"] * 100,
            summary["failed_count"],
        )
        if summary["success_rate"] < MINIMUM_DOWNLOAD_SUCCESS_RATE:
            raise RuntimeError(
                "YouTube download success rate "
                f"{summary['success_rate']:.1%} is below the required "
                f"{MINIMUM_DOWNLOAD_SUCCESS_RATE:.1%}. Failed videos: "
                f"{summary['failed_video_ids']}"
            )
        return summary

    scrape_result = scrape_youtube_metadata()
    plan_result = process_youtube_library_plan(scrape_result)
    video_ids = list_download_video_ids(plan_result)
    download_results = download_one_video.partial(plan_result=plan_result).expand(
        video_id=video_ids
    )
    finalize_downloads(download_results)


def _summarize_download_results(
    download_results: list[dict[str, str | bool | int | None]],
) -> dict[str, object]:
    successful_results = [
        result
        for result in download_results
        if result.get("status") in {"downloaded", "skipped"}
    ]
    failed_video_ids = [
        str(result["video_id"])
        for result in download_results
        if result.get("status") not in {"downloaded", "skipped"}
    ]
    total_count = len(download_results)
    success_rate = len(successful_results) / total_count if total_count else 1.0
    return {
        "total_count": total_count,
        "successful_count": len(successful_results),
        "failed_count": len(failed_video_ids),
        "success_rate": success_rate,
        "minimum_success_rate": MINIMUM_DOWNLOAD_SUCCESS_RATE,
        "failed_video_ids": failed_video_ids,
    }


def _write_report(object_store: ObjectStore, run_context, result: dict):
    import json

    data = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    return object_store.put_bytes(
        run_context=run_context,
        storage_root="global",
        object_key=youtube_run_object_key(
            storage_key_prefix=os.environ.get("EMPIRE_STORAGE_KEY_YOUTUBE", DEFAULT_STORAGE_KEY),
            effective_date=run_context.effective_date,
            run_id=str(run_context.run_id),
        ),
        filename=DOWNLOAD_REPORT_FILENAME,
        data=data,
        content_type="application/json",
        object_kind=DOWNLOAD_REPORT_OBJECT_KIND,
        expires_at=youtube_expires_at(),
        metadata={
            "video_id": result["video_id"],
            "status": result["status"],
            "skipped": result["skipped"],
        },
    )


youtube_daily_scrape_dag = youtube_daily_scrape()
