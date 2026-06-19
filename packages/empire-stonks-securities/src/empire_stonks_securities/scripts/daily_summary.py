"""Generate the final stonks securities daily refresh summary report."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from empire_core import EmpireDatabase, ObjectStore

from empire_stonks_securities.daily_summary import (
    default_daily_summary_report_path,
    generate_daily_refresh_summary_report,
    write_daily_summary_report_to_console,
    write_daily_summary_report_to_file,
    write_daily_summary_report_to_object_store,
)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    generated_at = datetime.now(UTC)
    with EmpireDatabase.connect_from_env() as connection:
        object_store = ObjectStore.from_connection(connection)
        report = generate_daily_refresh_summary_report(
            connection=connection,
            object_store=object_store,
            source_run_id=args.source_run_id,
            validation_report_object_id=args.validation_report_object_id,
            conflict_report_object_id=args.conflict_report_object_id,
            generated_at=generated_at,
            stale_warn_hours=args.stale_warn_hours,
            stale_fail_hours=args.stale_fail_hours,
        )
        if args.output == "console":
            write_daily_summary_report_to_console(report, json_output=args.json)
        elif args.output == "temp":
            path = default_daily_summary_report_path(
                temp_dir=args.temp_dir,
                generated_at=generated_at,
            )
            write_daily_summary_report_to_file(report, path)
            print(f"daily_summary_report_path: {path}")
        else:
            path = write_daily_summary_report_to_file(report, args.output)
            print(f"daily_summary_report_path: {path}")

        if args.object_store:
            stored = write_daily_summary_report_to_object_store(
                report=report,
                object_store=object_store,
                storage_root=args.storage_root,
                storage_key=args.storage_key,
                generated_at=generated_at,
            )
            print(f"daily_summary_report_object_id: {stored.object_id}")


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Generate the stonks securities daily refresh summary report."
    )
    parser.add_argument(
        "--output",
        default="console",
        help="Output destination: console, temp, or a JSON file path. Defaults to console.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON when --output console is used.",
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
        "--validation-report-object-id",
        help="Use this stored validation report object for summary linkage.",
    )
    parser.add_argument(
        "--conflict-report-object-id",
        help="Use this stored conflict report object for summary linkage.",
    )
    parser.add_argument(
        "--stale-warn-hours",
        type=int,
        default=36,
        help="Warn when source objects are at least this old. Defaults to 36.",
    )
    parser.add_argument(
        "--stale-fail-hours",
        type=int,
        default=96,
        help="Fail when source objects are at least this old. Defaults to 96.",
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
