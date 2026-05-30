"""Process YouTube scraper output and store a Jellyfin library plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from empire_core import EmpireDatabase, ObjectStore, RunService

from empire_youtube.processor import YouTubeScrapeProcessor
from empire_youtube.runner import (
    DEFAULT_OUTPUT_FILENAME,
    run_youtube_processor_to_object_store,
)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    with EmpireDatabase.connect_from_env() as connection:
        object_store = ObjectStore.from_connection(connection)
        run_service = RunService.from_connection(connection)
        scrape_payload = load_scrape_payload(args, object_store)
        processor = YouTubeScrapeProcessor()

        result = run_youtube_processor_to_object_store(
            scrape_payload=scrape_payload,
            processor=processor,
            run_service=run_service,
            object_store=object_store,
            run_type=args.run_type,
            runner=args.runner,
            runner_ref={"command": "bin/youtube-process"},
            source=args.input_source,
        )

    print(f"run_id: {result.run_context.run_id}")
    print(f"source_video_count: {result.library_plan.source_video_count}")
    print(f"plan_entry_count: {len(result.library_plan.entries)}")
    print(f"sidecar_object_count: {result.sidecar_object_count}")
    print(f"skipped_sidecar_count: {result.skipped_sidecar_count}")
    print(f"stored_object_id: {result.stored_object.object_id}")
    print(f"object_key: {result.stored_object.object_key}")
    print(f"filename: {result.stored_object.filename}")


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Process YouTube scraper output into a Jellyfin library plan."
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input-file",
        help="Read scraper JSON from an explicit filesystem path.",
    )
    input_group.add_argument(
        "--input-object-id",
        help="Read scraper JSON from a specific object-store object id.",
    )
    input_group.add_argument(
        "--input-run-id",
        help=(
            "Read youtube-scraper.json from a prior run using object_kind "
            "normalized_payload."
        ),
    )
    parser.add_argument(
        "--run-type",
        default="cli",
        choices=["airflow", "cli", "api", "manual", "agent"],
        help="Empire run type. Defaults to cli.",
    )
    parser.add_argument(
        "--runner",
        default="bin/youtube-process",
        help="Runner name recorded in Empire run context.",
    )
    args = parser.parse_args(argv)
    args.input_source = _input_source(args)
    return args


def load_scrape_payload(args, object_store: ObjectStore) -> dict:
    if args.input_file:
        return _read_json_file(args.input_file)
    if args.input_object_id:
        return _read_json_object(object_store, UUID(str(args.input_object_id)))
    stored = object_store.find_one(
        run_id=UUID(str(args.input_run_id)),
        object_kind="normalized_payload",
        filename=DEFAULT_OUTPUT_FILENAME,
    )
    if stored is None:
        raise RuntimeError(
            "No YouTube scraper output found for run: "
            f"{args.input_run_id}"
        )
    return _read_json_object(object_store, stored.object_id)


def _read_json_file(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError("YouTube scraper input must be a JSON object.")
    return payload


def _read_json_object(object_store: ObjectStore, object_id: UUID) -> dict:
    payload = json.loads(object_store.get_bytes(object_id).decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("YouTube scraper input must be a JSON object.")
    return payload


def _input_source(args) -> dict[str, str]:
    if args.input_file:
        return {"type": "file", "path": args.input_file}
    if args.input_object_id:
        return {"type": "object", "object_id": args.input_object_id}
    return {"type": "run", "run_id": args.input_run_id}


if __name__ == "__main__":
    main()
