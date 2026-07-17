"""Run the EODData daily workflow from an operator shell."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date

from empire_core import EmpireDatabase, ObjectStore, RunService

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.eoddata_runner import run_eoddata_daily


RUNNER_NAME = "bin/stonks-ohlcv-eoddata-daily"
SAFE_CLI_FAILURE = "ERROR: EODData daily run failed."


def build_parser() -> argparse.ArgumentParser:
    """Build the operator CLI parser."""

    parser = argparse.ArgumentParser(
        prog="stonks-ohlcv-eoddata-daily",
        description="Run the Empire EODData daily OHLCV workflow.",
    )
    parser.add_argument(
        "--effective-date",
        required=True,
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Provider Quote List date to acquire and import.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the package workflow and print only its compact JSON result."""

    args = build_parser().parse_args(argv)
    try:
        config = OHLCVConfig.from_env()
        with EmpireDatabase.connect_from_env() as connection:
            result = run_eoddata_daily(
                run_service=RunService.from_connection(connection),
                connection=connection,
                object_store=ObjectStore.from_connection(connection),
                config=config,
                effective_date=args.effective_date,
                run_type="cli",
                runner=RUNNER_NAME,
                runner_ref={"command": RUNNER_NAME},
            )
    except Exception:
        print(SAFE_CLI_FAILURE, file=sys.stderr)
        return 1

    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


def _iso_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "effective date must use YYYY-MM-DD."
        ) from None
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError(
            "effective date must use YYYY-MM-DD."
        )
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
