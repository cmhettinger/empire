"""Generate the Phase 2A stonks securities validation report."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from empire_core import EmpireDatabase, ObjectStore

from empire_stonks_securities.validation import (
    default_validation_report_path,
    generate_phase_2a_validation_report,
    write_validation_report_to_console,
    write_validation_report_to_file,
    write_validation_report_to_object_store,
)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    generated_at = datetime.now(UTC)
    with EmpireDatabase.connect_from_env() as connection:
        report = generate_phase_2a_validation_report(
            connection=connection,
            source_run_id=args.source_run_id,
            generated_at=generated_at,
        )
        if args.output == "console":
            write_validation_report_to_console(report)
        elif args.output == "temp":
            path = default_validation_report_path(
                temp_dir=args.temp_dir,
                generated_at=generated_at,
            )
            write_validation_report_to_file(report, path)
            print(f"validation_report_path: {path}")
        else:
            path = write_validation_report_to_file(report, args.output)
            print(f"validation_report_path: {path}")

        if args.object_store:
            object_store = ObjectStore.from_connection(connection)
            stored = write_validation_report_to_object_store(
                report=report,
                object_store=object_store,
                storage_root=args.storage_root,
                storage_key=args.storage_key,
                generated_at=generated_at,
            )
            print(f"validation_report_object_id: {stored.object_id}")


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Generate the stonks securities validation report."
    )
    parser.add_argument(
        "--output",
        default="console",
        help="Output destination: console, temp, or a JSON file path. Defaults to console.",
    )
    parser.add_argument(
        "--temp-dir",
        help="Temp directory for --output temp. Defaults to EMPIRE_TEMP_DIR or /tmp.",
    )
    parser.add_argument(
        "--source-run-id",
        help="Limit source/evidence metrics to observations from a specific core run id.",
    )
    parser.add_argument(
        "--object-store",
        action="store_true",
        help="Also store the report in the Empire object store.",
    )
    parser.add_argument(
        "--storage-root",
        default="global",
        help="Object-store root for --object-store. Defaults to global.",
    )
    parser.add_argument(
        "--storage-key",
        help="Object-store key prefix. Defaults to EMPIRE_STORAGE_KEY_STONKS_SECURITIES.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
