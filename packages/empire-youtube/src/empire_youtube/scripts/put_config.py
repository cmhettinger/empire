"""Publish a local YouTube scraper config file to the Empire object store."""

from __future__ import annotations

import argparse
from pathlib import Path

from empire_core import EmpireDatabase, ObjectStore

from empire_youtube.config import YouTubeScraperConfig
from empire_youtube.object_store import (
    DEFAULT_CONFIG_DOMAIN,
    DEFAULT_CONFIG_LOGICAL_NAME,
    DEFAULT_CONFIG_OBJECT_KIND,
    DEFAULT_CONFIG_OBJECT_SCOPE,
)


DEFAULT_CONFIG_FILENAME = "config.yml"
DEFAULT_CONFIG_CONTENT_TYPE = "text/yaml"
DEFAULT_STORAGE_ROOT = "config"
DEFAULT_STORAGE_KEY = "youtube"
DEFAULT_LOCAL_CONFIG_FILE = "object-store/config/youtube/config.yml"


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    path = Path(args.config_file or DEFAULT_LOCAL_CONFIG_FILE)
    data = path.read_bytes()
    YouTubeScraperConfig.from_yaml(data.decode("utf-8"))

    storage_root = args.storage_root or DEFAULT_STORAGE_ROOT
    storage_key = (args.storage_key or DEFAULT_STORAGE_KEY).strip("/")

    with EmpireDatabase.connect_from_env() as connection:
        object_store = ObjectStore.from_connection(connection)
        stored = object_store.put_bytes(
            run_context=None,
            object_scope=DEFAULT_CONFIG_OBJECT_SCOPE,
            domain=DEFAULT_CONFIG_DOMAIN,
            logical_name=args.logical_name,
            storage_root=storage_root,
            object_key=storage_key,
            filename=args.filename,
            data=data,
            content_type=DEFAULT_CONFIG_CONTENT_TYPE,
            object_kind=DEFAULT_CONFIG_OBJECT_KIND,
            overwrite=True,
            metadata={
                "source_path": str(path),
                "config_logical_name": args.logical_name,
            },
        )

    print(f"stored_object_id: {stored.object_id}")
    print(f"logical_name: {stored.logical_name}")
    print(f"object_key: {stored.object_key}")
    print(f"filename: {stored.filename}")


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Publish a local YouTube scraper config to object store."
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        help="Local YouTube scraper YAML config file.",
    )
    parser.add_argument(
        "--logical-name",
        default=DEFAULT_CONFIG_LOGICAL_NAME,
        help=(
            "Object-store logical name for this config. "
            f"Defaults to {DEFAULT_CONFIG_LOGICAL_NAME}."
        ),
    )
    parser.add_argument(
        "--filename",
        default=DEFAULT_CONFIG_FILENAME,
        help=f"Stored filename. Defaults to {DEFAULT_CONFIG_FILENAME}.",
    )
    parser.add_argument(
        "--storage-root",
        help="Object-store root name. Defaults to config.",
    )
    parser.add_argument(
        "--storage-key",
        help="Object key prefix. Defaults to youtube.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
