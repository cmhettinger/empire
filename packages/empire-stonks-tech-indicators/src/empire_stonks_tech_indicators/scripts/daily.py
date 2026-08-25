"""Run the package-owned daily technical-indicator workflow."""

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

from empire_stonks_tech_indicators.config import (
    DEFAULT_CALCULATION_VERSION,
    TechIndicatorsConfig,
)
from empire_stonks_tech_indicators.daily_runner import (
    TechIndicatorsDailyRunResult,
    run_tech_indicators_daily,
)
from empire_stonks_tech_indicators.daily_scope import TechIndicatorsDailyScope
from empire_stonks_tech_indicators.writer_lock import (
    TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE,
)


RUNNER_NAME = "bin/stonks-tech-indicators-daily"
SAFE_DAILY_FAILURE = "ERROR: Technical-indicator daily run failed."


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded daily operator parser."""

    parser = argparse.ArgumentParser(
        prog="stonks-tech-indicators-daily",
        description="Run one Empire technical-indicator daily refresh.",
    )
    parser.add_argument(
        "--effective-date",
        required=True,
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Exact source-readiness and publication date.",
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
            "Exact provider-listing UUID to include; repeat as needed and do "
            "not combine with provider or market filters."
        ),
    )
    parser.add_argument(
        "--calculation-version",
        default=DEFAULT_CALCULATION_VERSION,
        metavar="VERSION",
        help=f"Calculation profile; currently {DEFAULT_CALCULATION_VERSION}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate and report without publishing feature state.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Explicitly rebuild the resolved daily scope.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    connect_from_env: Callable[[], Any] = EmpireDatabase.connect_from_env,
    runner: Callable[..., TechIndicatorsDailyRunResult] = (
        run_tech_indicators_daily
    ),
) -> int:
    """Run the daily workflow and preserve stdout for its compact result."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        scope = TechIndicatorsDailyScope(
            effective_date=args.effective_date,
            provider_codes=tuple(args.provider_code or ()),
            markets=tuple(args.market or ()),
            provider_listing_ids=tuple(args.provider_listing_id or ()),
            calculation_version=args.calculation_version,
            dry_run=args.dry_run,
            force=args.force,
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
            )
        result_json = _compact_json(result.to_dict())
    except Exception:
        print(SAFE_DAILY_FAILURE, file=sys.stderr)
        return 1

    if result.status == "contended":
        print(result_json, file=sys.stderr)
        return TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE
    print(result_json)
    return 0


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
            "effective date must use YYYY-MM-DD."
        ) from None
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError(
            "effective date must use YYYY-MM-DD."
        )
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
            "provider listing ID must be a UUID."
        ) from None
    if str(parsed) != value:
        raise argparse.ArgumentTypeError(
            "provider listing ID must use canonical lowercase UUID text."
        )
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
