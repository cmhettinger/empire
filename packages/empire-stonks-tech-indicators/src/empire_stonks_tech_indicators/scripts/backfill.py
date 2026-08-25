"""Run the package-owned resumable technical-indicator backfill."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from datetime import date
from typing import Any
from uuid import UUID

from empire_core import EmpireDatabase, ObjectStore, RunService

from empire_stonks_tech_indicators.backfill_runner import (
    TechIndicatorsBackfillRunResult,
    run_tech_indicators_backfill,
)
from empire_stonks_tech_indicators.backfill_scope import (
    TechIndicatorsBackfillCursor,
    TechIndicatorsBackfillScope,
)
from empire_stonks_tech_indicators.config import (
    DEFAULT_CALCULATION_VERSION,
    DEFAULT_WRITE_BATCH_SIZE,
    TechIndicatorsConfig,
)
from empire_stonks_tech_indicators.writer_lock import (
    TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE,
)


RUNNER_NAME = "bin/stonks-tech-indicators-backfill"
SAFE_BACKFILL_FAILURE = "ERROR: Technical-indicator backfill failed."


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded historical-backfill operator parser."""

    parser = argparse.ArgumentParser(
        prog="stonks-tech-indicators-backfill",
        description="Run one resumable Empire technical-indicator backfill.",
    )
    parser.add_argument(
        "--effective-date",
        required=True,
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Core execution and benchmark evidence date.",
    )
    parser.add_argument(
        "--start-date",
        required=True,
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Inclusive earliest requested trading date.",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Inclusive latest requested trading date.",
    )
    parser.add_argument(
        "--provider-code",
        action="append",
        type=_provider_code,
        metavar="CODE",
        help="Exact provider code to include; repeat as needed.",
    )
    parser.add_argument(
        "--market",
        action="append",
        type=_trimmed_text,
        metavar="MARKET",
        help="Exact provider-native market to include; repeat as needed.",
    )
    parser.add_argument(
        "--provider-listing-id",
        action="append",
        type=_uuid,
        metavar="UUID",
        help=(
            "Exact listing UUID to include; repeat and do not combine with "
            "provider or market filters."
        ),
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include inactive rows in an exact-listing scope.",
    )
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=DEFAULT_WRITE_BATCH_SIZE,
        metavar="ROWS",
        help="Rows per staged transaction; accepted range is 1000-10000.",
    )
    parser.add_argument(
        "--batch-limit",
        type=_positive_int,
        metavar="BATCHES",
        help=(
            "Stop after this many newly committed batches and return an "
            "exact resume cursor."
        ),
    )
    parser.add_argument(
        "--resume-provider-listing-id",
        type=_uuid,
        metavar="UUID",
        help="Provider-listing UUID from the last completed cursor.",
    )
    parser.add_argument(
        "--resume-trading-date",
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Trading date from the last completed cursor.",
    )
    parser.add_argument(
        "--resume-batch-number",
        type=_positive_int,
        metavar="NUMBER",
        help="Batch number from the last completed cursor.",
    )
    parser.add_argument(
        "--calculation-version",
        default=DEFAULT_CALCULATION_VERSION,
        metavar="VERSION",
        help=f"Calculation profile; currently {DEFAULT_CALCULATION_VERSION}.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Recalculate complete selected listing images.",
    )
    parser.add_argument(
        "--confirm-rebuild",
        action="store_true",
        help="Required explicit acknowledgement for --rebuild.",
    )
    parser.add_argument(
        "--confirm-broad-scope",
        action="store_true",
        help="Required for provider, market, unfiltered, or broad scopes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate and report, then roll back all staged feature state.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    connect_from_env: Callable[[], Any] = EmpireDatabase.connect_from_env,
    runner: Callable[..., TechIndicatorsBackfillRunResult] = (
        run_tech_indicators_backfill
    ),
) -> int:
    """Run a backfill with JSON-line progress and one final compact result."""

    parser = build_parser()
    args = parser.parse_args(argv)
    resume_cursor = _build_resume_cursor(parser, args)
    if args.rebuild != args.confirm_rebuild:
        parser.error(
            "--rebuild and --confirm-rebuild must be supplied together."
        )
    if args.dry_run and (resume_cursor is not None or args.batch_limit is not None):
        parser.error("--dry-run cannot be combined with resume or --batch-limit.")
    try:
        scope = TechIndicatorsBackfillScope(
            effective_date=args.effective_date,
            start_date=args.start_date,
            end_date=args.end_date,
            provider_codes=tuple(args.provider_code or ()),
            markets=tuple(args.market or ()),
            provider_listing_ids=tuple(args.provider_listing_id or ()),
            include_inactive=args.include_inactive,
            batch_size=args.batch_size,
            resume_cursor=resume_cursor,
            calculation_version=args.calculation_version,
            rebuild=args.rebuild,
            dry_run=args.dry_run,
            confirm_broad_scope=args.confirm_broad_scope,
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    try:
        config = TechIndicatorsConfig.from_env()
        with ExitStack() as stack:
            work_connection = stack.enter_context(connect_from_env())
            core_connection = stack.enter_context(connect_from_env())
            object_connection = stack.enter_context(connect_from_env())
            result = runner(
                run_service=RunService.from_connection(core_connection),
                connection=work_connection,
                lock_connection_factory=connect_from_env,
                object_store=ObjectStore.from_connection(object_connection),
                config=config,
                scope=scope,
                run_type="cli",
                runner=RUNNER_NAME,
                batch_limit=args.batch_limit,
                progress_sink=_print_progress,
            )
        result_json = _compact_json(result.to_dict())
    except Exception:
        print(SAFE_BACKFILL_FAILURE, file=sys.stderr)
        return 1

    if result.status == "contended":
        print(result_json, file=sys.stderr)
        return TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE
    print(result_json)
    return 0


def _build_resume_cursor(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> TechIndicatorsBackfillCursor | None:
    identifier = args.resume_provider_listing_id
    trading_date = args.resume_trading_date
    batch_number = args.resume_batch_number
    if identifier is None and trading_date is None and batch_number is None:
        return None
    if identifier is None or batch_number is None:
        parser.error(
            "resume requires --resume-provider-listing-id and "
            "--resume-batch-number; include --resume-trading-date when the "
            "cursor contains one."
        )
    return TechIndicatorsBackfillCursor(
        provider_listing_id=identifier,
        trading_date=trading_date,
        batch_number=batch_number,
    )


def _print_progress(payload: dict[str, object]) -> None:
    print(
        _compact_json(
            {"event": "tech_indicators_backfill_progress", **payload}
        ),
        file=sys.stderr,
        flush=True,
    )


def _compact_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


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


def _provider_code(value: str) -> str:
    parsed = _trimmed_text(value)
    if parsed != parsed.upper():
        raise argparse.ArgumentTypeError(
            "provider code must be an exact uppercase identifier."
        )
    return parsed


def _trimmed_text(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise argparse.ArgumentTypeError(
            "scope values must be non-empty, trimmed text."
        )
    return value


def _uuid(value: str) -> UUID:
    try:
        parsed = UUID(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "listing IDs must be UUIDs."
        ) from None
    if str(parsed) != value:
        raise argparse.ArgumentTypeError(
            "listing IDs must use canonical lowercase UUID text."
        )
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("values must be positive integers.")
    if parsed < 1 or str(parsed) != value:
        raise argparse.ArgumentTypeError("values must be positive integers.")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
