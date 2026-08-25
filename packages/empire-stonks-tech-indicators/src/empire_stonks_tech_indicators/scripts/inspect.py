"""Inspect technical-indicator operational state without mutation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any
from uuid import UUID

from empire_core import EmpireDatabase

from empire_stonks_tech_indicators.config import (
    DEFAULT_CALCULATION_VERSION,
    MAX_DIAGNOSTIC_SAMPLE_LIMIT,
    TechIndicatorsConfig,
)
from empire_stonks_tech_indicators.inspection import (
    TechIndicatorsInspection,
    inspect_tech_indicators,
)
from empire_stonks_tech_indicators.models import TechIndicatorsScope


SAFE_INSPECTION_FAILURE = "ERROR: Technical-indicator inspection failed."


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded read-only inspection parser."""

    parser = argparse.ArgumentParser(
        prog="stonks-tech-indicators-inspect",
        description=(
            "Inspect threshold-free technical-indicator operational state."
        ),
    )
    parser.add_argument(
        "--effective-date",
        required=True,
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Exact freshness and SPX/source-readiness date.",
    )
    parser.add_argument(
        "--start-date",
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Optional inclusive first coverage/drift date.",
    )
    parser.add_argument(
        "--end-date",
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="Optional inclusive last coverage/drift date.",
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
        "--calculation-version",
        default=DEFAULT_CALCULATION_VERSION,
        metavar="VERSION",
        help=f"Expected calculation profile; currently {DEFAULT_CALCULATION_VERSION}.",
    )
    parser.add_argument(
        "--sample-limit",
        type=_sample_limit,
        metavar="COUNT",
        help=(
            "Maximum listings per operational sample; defaults to the "
            "configured diagnostic limit."
        ),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    connect_from_env: Callable[[], Any] = EmpireDatabase.connect_from_env,
    inspector: Callable[..., TechIndicatorsInspection] = inspect_tech_indicators,
) -> int:
    """Run one read-only inspection and emit a compact JSON object."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if (args.start_date is None) != (args.end_date is None):
        parser.error("--start-date and --end-date must be supplied together.")
    if args.provider_listing_id and (args.provider_code or args.market):
        parser.error(
            "--provider-listing-id cannot be combined with provider or "
            "market filters."
        )
    try:
        scope = TechIndicatorsScope(
            provider_codes=tuple(args.provider_code or ()),
            markets=tuple(args.market or ()),
            provider_listing_ids=tuple(args.provider_listing_id or ()),
            start_date=args.start_date,
            end_date=args.end_date,
            include_inactive=args.include_inactive,
        )
        if scope.start_date is not None and not (
            scope.start_date <= args.effective_date <= scope.end_date
        ):
            raise ValueError(
                "effective date must be inside the requested date range."
            )
        if args.calculation_version != DEFAULT_CALCULATION_VERSION:
            raise ValueError(
                "calculation version must be "
                f"{DEFAULT_CALCULATION_VERSION}."
            )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    try:
        config = TechIndicatorsConfig.from_env()
        with connect_from_env() as connection:
            result = inspector(
                connection=connection,
                scope=scope,
                effective_date=args.effective_date,
                benchmark_config=config.benchmark,
                calculation_version=args.calculation_version,
                sample_limit=(
                    config.diagnostic_sample_limit
                    if args.sample_limit is None
                    else args.sample_limit
                ),
                page_size=config.source_read_page_size,
            )
        payload = json.dumps(
            result.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except Exception:
        print(SAFE_INSPECTION_FAILURE, file=sys.stderr)
        return 1

    print(payload)
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


def _sample_limit(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "sample limit must be a positive integer."
        ) from None
    if not 1 <= parsed <= MAX_DIAGNOSTIC_SAMPLE_LIMIT or str(parsed) != value:
        raise argparse.ArgumentTypeError(
            "sample limit must be between 1 and "
            f"{MAX_DIAGNOSTIC_SAMPLE_LIMIT}."
        )
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
