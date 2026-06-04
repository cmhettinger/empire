"""Download one planned YouTube video into the Empire object store."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime

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
from empire_youtube.retention import youtube_expires_at
from empire_youtube.runner import (
    DEFAULT_DOMAIN,
    DEFAULT_STORAGE_KEY,
    youtube_run_object_key,
)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    with EmpireDatabase.connect_from_env() as connection:
        object_store = ObjectStore.from_connection(connection)
        plan = load_library_plan(args, object_store)

        if args.list:
            for entry in iter_download_entries(plan):
                print(f"{entry.video_id}\t{entry.title}")
            return

        if not args.video_id:
            raise RuntimeError("--video-id is required unless --list is provided.")

        run_service = RunService.from_connection(connection)
        entry = find_download_entry(plan, video_id=args.video_id)
        ctx = run_service.start_run(
            domain=DEFAULT_DOMAIN,
            job_name="youtube_download",
            subject_key=entry.video_id,
            effective_date=datetime.now(UTC).date(),
            run_type=args.run_type,
            runner=args.runner,
            runner_ref={"command": "bin/youtube-download"},
            params={
                "video_id": entry.video_id,
                "source_url": entry.source_url,
                "object_key": entry.object_key,
                "plan_source": args.plan_source,
                "cleanup_on_failure": args.cleanup_on_failure,
            },
        )

        try:
            result = download_entry_to_object_store(
                entry=entry,
                object_store=object_store,
                run_context=ctx,
                cleanup_on_failure=args.cleanup_on_failure,
            )
            stored_report = _write_report(object_store, ctx, result.to_dict())
            run_service.complete_run(
                ctx.run_id,
                summary={
                    **result.to_dict(),
                    "report_object_id": str(stored_report.object_id),
                },
            )
        except YouTubeDownloadError as exc:
            result = exc.result
            stored_report = _write_report(object_store, ctx, result.to_dict())
            run_service.fail_run(
                ctx.run_id,
                error_message=result.error_message or str(exc),
                summary={
                    **result.to_dict(),
                    "report_object_id": str(stored_report.object_id),
                },
            )
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            raise

    print(f"run_id: {ctx.run_id}")
    print(f"video_id: {result.video_id}")
    print(f"status: {result.status}")
    print(f"skipped: {result.skipped}")
    print(f"object_id: {result.object_id}")
    print(f"object_key: {result.object_key}")
    print(f"filename: {result.filename}")
    print(f"cleanup_count: {result.cleanup_count}")
    print(f"report_object_id: {stored_report.object_id}")


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Download one planned YouTube video into Empire object storage."
    )
    plan_group = parser.add_mutually_exclusive_group(required=True)
    plan_group.add_argument(
        "--plan-object-id",
        help="Read youtube-library-plan.json from a specific stored object id.",
    )
    plan_group.add_argument(
        "--plan-run-id",
        help="Read youtube-library-plan.json from a processor run id.",
    )
    parser.add_argument("--video-id", help="Download this YouTube video id.")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List video ids available in the plan and exit.",
    )
    parser.add_argument(
        "--cleanup-on-failure",
        action="store_true",
        help="Delete the planned video folder sidecars if the download fails.",
    )
    parser.add_argument(
        "--run-type",
        default="cli",
        choices=["airflow", "cli", "api", "manual", "agent"],
        help="Empire run type. Defaults to cli.",
    )
    parser.add_argument(
        "--runner",
        default="bin/youtube-download",
        help="Runner name recorded in Empire run context.",
    )
    args = parser.parse_args(argv)
    args.plan_source = _plan_source(args)
    return args


def load_library_plan(args, object_store: ObjectStore) -> dict:
    if args.plan_object_id:
        return load_library_plan_from_object_id(object_store, args.plan_object_id)
    return load_library_plan_from_run_id(object_store, args.plan_run_id)


def _write_report(object_store: ObjectStore, ctx, result: dict):
    data = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode(
        "utf-8"
    )
    return object_store.put_bytes(
        run_context=ctx,
        storage_root="global",
        object_key=youtube_run_object_key(
            storage_key_prefix=os.environ.get(
                "EMPIRE_STORAGE_KEY_YOUTUBE",
                DEFAULT_STORAGE_KEY,
            ),
            effective_date=ctx.effective_date,
            run_id=str(ctx.run_id),
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


def _plan_source(args) -> dict[str, str]:
    if args.plan_object_id:
        return {"type": "object", "object_id": args.plan_object_id}
    return {"type": "run", "run_id": args.plan_run_id}


if __name__ == "__main__":
    main()
