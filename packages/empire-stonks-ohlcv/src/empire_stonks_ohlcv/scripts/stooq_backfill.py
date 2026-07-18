"""Run the manual Stooq historical backfill from an operator shell."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from empire_core import EmpireDatabase, ObjectStore, RunService

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.stooq_history import (
    STOOQ_HISTORY_ARCHIVE_NAME,
    STOOQ_HISTORY_MARKETS,
    StooqHistoryScope,
)
from empire_stonks_ohlcv.stooq_history_runner import (
    run_stooq_history_backfill,
)


RUNNER_NAME = "bin/stonks-ohlcv-stooq-backfill"
SAFE_CLI_FAILURE = "ERROR: Stooq historical backfill failed."
DEFAULT_CHUNK_SIZE = 50_000
MAX_CHUNK_SIZE = 100_000


def build_parser() -> argparse.ArgumentParser:
    """Build the one-shot historical backfill parser."""

    parser = argparse.ArgumentParser(
        prog="stonks-ohlcv-stooq-backfill",
        description=(
            "Import an operator-supplied Stooq d_us_txt.zip archive. "
            "This command does not download the archive."
        ),
    )
    parser.add_argument(
        "--input-path",
        required=True,
        type=_input_path,
        metavar="PATH",
        help=f"Existing local {STOOQ_HISTORY_ARCHIVE_NAME} archive.",
    )
    parser.add_argument(
        "--effective-date",
        required=True,
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Date on which the operator acquired the archive.",
    )
    parser.add_argument(
        "--start-date",
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Optional inclusive earliest trading date.",
    )
    parser.add_argument(
        "--end-date",
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Optional inclusive latest trading date.",
    )
    parser.add_argument(
        "--market",
        action="append",
        choices=STOOQ_HISTORY_MARKETS,
        metavar="MARKET",
        help=(
            "Provider market to include; repeat for multiple markets. "
            "Defaults to nasdaq, nyse, and nysemkt."
        ),
    )
    parser.add_argument(
        "--ticker",
        action="append",
        type=_ticker,
        metavar="TICKER.US",
        help=(
            "Exact uppercase Stooq ticker to include; repeat for multiple "
            "tickers. Defaults to every ticker in the selected markets."
        ),
    )
    parser.add_argument(
        "--chunk-size",
        type=_chunk_size,
        default=DEFAULT_CHUNK_SIZE,
        metavar="ROWS",
        help=(
            "Maximum bars per database transaction "
            f"(default: {DEFAULT_CHUNK_SIZE}; max: {MAX_CHUNK_SIZE})."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the package workflow and print its final JSON result to stdout."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        scope = StooqHistoryScope(
            effective_date=args.effective_date,
            start_date=args.start_date,
            end_date=args.end_date,
            markets=(
                tuple(args.market)
                if args.market is not None
                else STOOQ_HISTORY_MARKETS
            ),
            tickers=tuple(args.ticker or ()),
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    try:
        config = OHLCVConfig.from_env()
        with EmpireDatabase.connect_from_env() as connection:
            result = run_stooq_history_backfill(
                run_service=RunService.from_connection(connection),
                connection=connection,
                object_store=ObjectStore.from_connection(connection),
                config=config,
                input_path=args.input_path,
                scope=scope,
                chunk_size=args.chunk_size,
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


def _input_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path.name != STOOQ_HISTORY_ARCHIVE_NAME:
        raise argparse.ArgumentTypeError(
            f"input path filename must be {STOOQ_HISTORY_ARCHIVE_NAME}."
        )
    if not path.is_file():
        raise argparse.ArgumentTypeError(
            "input path must be an existing regular file."
        )
    return path


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
        or not value.endswith(".US")
    ):
        raise argparse.ArgumentTypeError(
            "ticker must be an exact uppercase Stooq value ending in .US."
        )
    return value


def _chunk_size(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "chunk size must be an integer."
        ) from None
    if parsed <= 0 or parsed > MAX_CHUNK_SIZE:
        raise argparse.ArgumentTypeError(
            f"chunk size must be between 1 and {MAX_CHUNK_SIZE}."
        )
    return parsed


def _print_progress(payload: dict[str, Any]) -> None:
    progress = {"event": "stooq_history_progress", **payload}
    print(
        json.dumps(progress, sort_keys=True, allow_nan=False),
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
