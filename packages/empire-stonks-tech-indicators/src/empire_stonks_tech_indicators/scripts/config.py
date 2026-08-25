"""Validate the secret-safe technical-indicator runtime configuration."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from typing import Any

from empire_core import EmpireDatabase

from empire_stonks_tech_indicators.config import TechIndicatorsConfig
from empire_stonks_tech_indicators.config_readiness import (
    TechIndicatorsConfigReadinessError,
    check_tech_indicators_config_readiness,
)


SAFE_CONFIG_FAILURE = "ERROR: Technical-indicator configuration check failed."


def build_parser() -> argparse.ArgumentParser:
    """Build the operator command parser."""

    return argparse.ArgumentParser(
        prog="stonks-tech-indicators-config",
        description=(
            "Validate the secret-safe Empire technical-indicator configuration "
            "and runtime readiness."
        ),
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    connect_from_env: Callable[[], Any] = EmpireDatabase.connect_from_env,
) -> int:
    """Print one compact readiness result without exposing runtime secrets."""

    build_parser().parse_args(argv)
    try:
        config = TechIndicatorsConfig.from_env()
        with connect_from_env() as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                result = check_tech_indicators_config_readiness(
                    cursor=cursor,
                    config=config,
                )
    except TechIndicatorsConfigReadinessError as exc:
        print(
            json.dumps(
                {"ready": False, "failure_stage": exc.stage},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        print(SAFE_CONFIG_FAILURE, file=sys.stderr)
        return 1
    except Exception:
        print(SAFE_CONFIG_FAILURE, file=sys.stderr)
        return 1

    print(
        json.dumps(
            result.to_safe_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
