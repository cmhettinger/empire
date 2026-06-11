"""Collect SEC source files into the Empire object store."""

from __future__ import annotations

import argparse
from datetime import date

from empire_core import EmpireDatabase, ObjectStore

from empire_stonks_securities.acquisition import (
    DEFAULT_STORAGE_ROOT,
    SecDownloader,
    build_configured_source_targets,
    build_quarterly_master_index_targets,
    default_storage_key,
)
from empire_stonks_securities.config import StonksSecuritiesConfig
from empire_stonks_securities.object_store import (
    DEFAULT_CONFIG_LOGICAL_NAME,
    load_config_by_logical_name,
    load_config_from_object_id,
)


DEFAULT_LOCAL_CONFIG_FILE = "object-store/config/stonks-securities/config.yml"


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    acquisition_date = date.fromisoformat(args.acquisition_date) if args.acquisition_date else date.today()
    acquisition_id = args.acquisition_id or "manual"
    storage_key = (args.storage_key or default_storage_key()).strip("/")

    with EmpireDatabase.connect_from_env() as connection:
        object_store = ObjectStore.from_connection(connection)
        config = load_config(args, object_store)
        if args.command == "source":
            targets = build_configured_source_targets(
                config=config,
                storage_key=storage_key,
                acquisition_date=acquisition_date,
                acquisition_id=acquisition_id,
                source_keys=args.source,
            )
        elif args.command == "quarterly":
            targets = build_quarterly_master_index_targets(
                config=config,
                storage_key=storage_key,
                acquisition_date=acquisition_date,
                acquisition_id=acquisition_id,
                start_year=args.start_year,
                end_year=args.end_year,
                quarters=args.quarter,
            )
        else:
            raise RuntimeError(f"Unknown command: {args.command}")

        if not targets:
            raise RuntimeError("No SEC download targets matched the requested options.")

        downloader = SecDownloader(config)
        results = [
            downloader.download_target(
                target=target,
                object_store=object_store,
                storage_root=args.storage_root,
                force=args.force,
                temp_dir=args.temp_dir,
            )
            for target in targets
        ]

    downloaded_count = sum(1 for result in results if result.status == "downloaded")
    skipped_count = sum(1 for result in results if result.skipped)
    print(f"downloaded_count: {downloaded_count}")
    print(f"skipped_count: {skipped_count}")
    print(f"storage_root: {args.storage_root}")
    print(f"storage_key: {storage_key}")
    print(f"acquisition_date: {acquisition_date.isoformat()}")
    print(f"acquisition_id: {acquisition_id}")
    for result in results:
        print(
            "result: "
            f"{result.status} "
            f"source_code={result.source_code} "
            f"object_key={result.object_key} "
            f"filename={result.filename} "
            f"metadata={result.metadata_filename}"
        )


def load_config(args, object_store: ObjectStore) -> StonksSecuritiesConfig:
    if args.config_file:
        return StonksSecuritiesConfig.from_file(args.config_file)
    if args.config_object_id:
        return load_config_from_object_id(object_store, args.config_object_id)
    return load_config_by_logical_name(object_store, logical_name=args.config_logical_name)


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Collect configured SEC source files into the Empire object store."
    )
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--config-file",
        help=(
            "Local config YAML. If omitted, loads the published stonks securities "
            "config from the object store."
        ),
    )
    config_group.add_argument(
        "--config-object-id",
        help="Load stonks securities config from a specific object-store object id.",
    )
    config_group.add_argument(
        "--config-logical-name",
        default=DEFAULT_CONFIG_LOGICAL_NAME,
        help="Published config logical name. Defaults to stonks-securities-config.",
    )
    parser.add_argument(
        "--storage-root",
        default=DEFAULT_STORAGE_ROOT,
        help=f"Object-store storage root. Defaults to {DEFAULT_STORAGE_ROOT}.",
    )
    parser.add_argument(
        "--storage-key",
        help="Object key prefix. Defaults to EMPIRE_STORAGE_KEY_STONKS_SECURITIES or stonks/securities.",
    )
    parser.add_argument(
        "--acquisition-date",
        help="Acquisition date for deterministic object keys, YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "--acquisition-id",
        help="Acquisition folder name for deterministic object keys. Defaults to manual.",
    )
    parser.add_argument(
        "--temp-dir",
        help="Temporary working directory. Defaults to EMPIRE_TEMP_DIR.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Download even when the final file and metadata sidecar already exist.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    source = subparsers.add_parser("source", help="Download one or more named fixed-URL sources.")
    source.add_argument(
        "source",
        nargs="+",
        help="Provider key or provider_code, for example sec_submissions_zip.",
    )

    quarterly = subparsers.add_parser("quarterly", help="Download quarterly EDGAR master.zip files.")
    quarterly.add_argument("--start-year", type=int, help="First year to download.")
    quarterly.add_argument("--end-year", type=int, help="Last year to download.")
    quarterly.add_argument(
        "--quarter",
        type=int,
        action="append",
        help="Quarter to download. May be repeated. Defaults to config quarters.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
