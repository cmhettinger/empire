"""Run weather collection and store normalized output."""

from __future__ import annotations

import argparse

from empire_core import EmpireDatabase, ObjectStore, RunService

from empire_weather import (
    DEFAULT_CONFIG_LOGICAL_NAME,
    WeatherCollectionConfig,
    WeatherCollector,
    load_config_by_logical_name,
    load_config_from_object_id,
    run_weather_collection_to_object_store,
    write_result_to_file,
)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.output_file and args.config_file:
        config = WeatherCollectionConfig.from_file(args.config_file)
        collector = WeatherCollector(config=config)
        result = collector.collect()
        output_path = write_result_to_file(result, args.output_file)
        print(f"location_count: {result.location_count}")
        print(f"raw_response_count: {len(result.raw_responses)}")
        print(f"output_file: {output_path}")
        return

    with EmpireDatabase.connect_from_env() as connection:
        object_store = ObjectStore.from_connection(connection)
        config = load_config(args, object_store)
        collector = WeatherCollector(config=config)

        if args.output_file:
            result = collector.collect()
            output_path = write_result_to_file(result, args.output_file)
            print(f"location_count: {result.location_count}")
            print(f"raw_response_count: {len(result.raw_responses)}")
            print(f"output_file: {output_path}")
            return

        run_service = RunService.from_connection(connection)
        run_result = run_weather_collection_to_object_store(
            config=config,
            collector=collector,
            run_service=run_service,
            object_store=object_store,
            run_type=args.run_type,
            runner=args.runner,
            runner_ref={"command": "bin/weather-collect"},
        )

    print(f"run_id: {run_result.run_context.run_id}")
    print(f"location_count: {run_result.collection_result.location_count}")
    print(f"raw_object_count: {run_result.raw_object_count}")
    print(f"image_object_count: {run_result.image_object_count}")
    print(f"stored_object_id: {run_result.stored_object.object_id}")
    print(f"object_key: {run_result.stored_object.object_key}")
    print(f"filename: {run_result.stored_object.filename}")


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Run weather collection and store normalized output."
    )
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--config-file",
        help="Load weather config from a local YAML file instead of object store.",
    )
    config_group.add_argument(
        "--config-object-id",
        help="Load weather config from a specific object-store object id.",
    )
    config_group.add_argument(
        "--config-logical-name",
        default=DEFAULT_CONFIG_LOGICAL_NAME,
        help=(
            "Object-store logical name for weather config. "
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
        default="bin/weather-collect",
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


def load_config(args, object_store: ObjectStore) -> WeatherCollectionConfig:
    if args.config_file:
        return WeatherCollectionConfig.from_file(args.config_file)
    if args.config_object_id:
        return load_config_from_object_id(object_store, args.config_object_id)
    return load_config_by_logical_name(
        object_store,
        logical_name=args.config_logical_name,
    )


if __name__ == "__main__":
    main()
