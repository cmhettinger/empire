"""Run the YouTube scraper and store normalized output."""

from __future__ import annotations

import argparse

from empire_core import EmpireDatabase, ObjectStore, RunService

from empire_youtube import (
    DEFAULT_CONFIG_LOGICAL_NAME,
    YouTubeScraper,
    YouTubeScraperConfig,
    load_config_by_logical_name,
    load_config_from_object_id,
    run_youtube_scraper_to_object_store,
    write_result_to_file,
)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    _validate_config_source(args)

    if args.output_file and args.config_file:
        config = YouTubeScraperConfig.from_file(args.config_file)
        scraper = YouTubeScraper(config=config)
        scrape_result = scraper.scrape()
        output_path = write_result_to_file(scrape_result, args.output_file)
        print(f"video_count: {len(scrape_result.videos)}")
        print(f"output_file: {output_path}")
        return

    with EmpireDatabase.connect_from_env() as connection:
        object_store = ObjectStore.from_connection(connection)
        config = load_config(args, object_store)
        run_service = RunService.from_connection(connection)
        scraper = YouTubeScraper(config=config)

        if args.output_file:
            scrape_result = scraper.scrape()
            output_path = write_result_to_file(scrape_result, args.output_file)
            print(f"video_count: {len(scrape_result.videos)}")
            print(f"output_file: {output_path}")
            return

        result = run_youtube_scraper_to_object_store(
            config=config,
            scraper=scraper,
            run_service=run_service,
            object_store=object_store,
            run_type=args.run_type,
            runner=args.runner,
            runner_ref={"command": "bin/youtube-scrape"},
        )

    print(f"run_id: {result.run_context.run_id}")
    print(f"video_count: {len(result.scrape_result.videos)}")
    print(f"stored_object_id: {result.stored_object.object_id}")
    print(f"object_key: {result.stored_object.object_key}")
    print(f"filename: {result.stored_object.filename}")


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Run the YouTube scraper and store normalized output."
    )
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--config-file",
        help="Load scraper config from a local YAML file instead of object store.",
    )
    config_group.add_argument(
        "--config-object-id",
        help="Load scraper config from a specific object-store object id.",
    )
    config_group.add_argument(
        "--config-logical-name",
        default=DEFAULT_CONFIG_LOGICAL_NAME,
        help=(
            "Object-store logical name for scraper config. "
            f"Defaults to {DEFAULT_CONFIG_LOGICAL_NAME}."
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
        default="bin/youtube-scrape",
        help="Runner name recorded in Empire run context.",
    )
    parser.add_argument(
        "--output-file",
        help=(
            "Write normalized JSON to this filesystem path instead of Empire "
            "object store. Useful for local debugging."
        ),
    )
    return parser.parse_args(argv)


def load_config(args, object_store: ObjectStore) -> YouTubeScraperConfig:
    if args.config_file:
        return YouTubeScraperConfig.from_file(args.config_file)
    if args.config_object_id:
        return load_config_from_object_id(object_store, args.config_object_id)
    return load_config_by_logical_name(
        object_store,
        logical_name=args.config_logical_name,
    )


def _validate_config_source(args) -> None:
    # argparse handles mutual exclusion. This function exists as a small seam for tests
    # and future config-source validation.
    return None


if __name__ == "__main__":
    main()
