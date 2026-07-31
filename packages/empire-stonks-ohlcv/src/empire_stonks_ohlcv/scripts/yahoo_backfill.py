"""Run the seeded Yahoo historical backfill from an operator shell."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from empire_core import EmpireDatabase, ObjectStore, RunService

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.yahoo_backfill import (
    YahooBackfillScope,
    run_yahoo_backfill,
)


RUNNER_NAME = "bin/stonks-ohlcv-yahoo-backfill"
SAFE_CLI_FAILURE = "ERROR: Yahoo historical backfill failed."


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded Yahoo historical backfill parser."""

    parser = argparse.ArgumentParser(
        prog="stonks-ohlcv-yahoo-backfill",
        description=(
            "Backfill active seeded Yahoo OHLCV listings through Empire."
        ),
    )
    parser.add_argument(
        "--effective-date",
        required=True,
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Execution/evidence date recorded on the Core run.",
    )
    parser.add_argument(
        "--start-date",
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help=(
            "Inclusive provider date; defaults to the configured Yahoo "
            "backfill start date."
        ),
    )
    parser.add_argument(
        "--end-date-exclusive",
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help=(
            "Exclusive provider date; defaults to effective-date plus one day."
        ),
    )
    parser.add_argument(
        "--ticker",
        action="append",
        type=_ticker,
        metavar="EMPIRE_TICKER",
        help=(
            "Exact seeded Empire ticker to include; repeat as needed. "
            "Defaults to every active Yahoo seed."
        ),
    )
    parser.add_argument(
        "--resume-from",
        type=_ticker,
        metavar="EMPIRE_TICKER",
        help=(
            "Resume inclusively at this active Empire ticker in seed order."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the package workflow and print one compact secret-safe JSON result."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = OHLCVConfig.from_env()
    except Exception:
        print(SAFE_CLI_FAILURE, file=sys.stderr)
        return 1
    try:
        scope = YahooBackfillScope(
            effective_date=args.effective_date,
            start_date=(
                args.start_date
                or date.fromisoformat(config.yahoo_backfill_start_date)
            ),
            end_date_exclusive=(
                args.end_date_exclusive
                or args.effective_date + timedelta(days=1)
            ),
            tickers=tuple(args.ticker or ()),
            resume_from_ticker=args.resume_from,
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    try:
        with EmpireDatabase.connect_from_env() as connection:
            result = run_yahoo_backfill(
                run_service=RunService.from_connection(connection),
                connection=connection,
                object_store=ObjectStore.from_connection(connection),
                config=config,
                scope=scope,
                run_type="cli",
                runner=RUNNER_NAME,
                runner_ref={"command": RUNNER_NAME},
                progress_sink=_print_progress,
            )
        final_json = json.dumps(
            result.to_dict(),
            sort_keys=True,
            allow_nan=False,
        )
    except Exception:
        print(SAFE_CLI_FAILURE, file=sys.stderr)
        return 1

    print(final_json)
    return 0


def _iso_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "dates must use YYYY-MM-DD."
        ) from None
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("dates must use YYYY-MM-DD.")
    return parsed


def _ticker(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or value != value.upper()
    ):
        raise argparse.ArgumentTypeError(
            "ticker must be an exact trimmed uppercase Empire ticker."
        )
    return value


def _print_progress(payload: dict[str, Any]) -> None:
    progress = {"event": "yahoo_backfill_progress", **payload}
    print(
        json.dumps(progress, sort_keys=True, allow_nan=False),
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
