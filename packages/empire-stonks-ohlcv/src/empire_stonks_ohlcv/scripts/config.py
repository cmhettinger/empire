"""Inspect the secret-safe OHLCV runtime configuration."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from empire_stonks_ohlcv.config import OHLCVConfig


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    return argparse.ArgumentParser(
        prog="stonks-ohlcv-config",
        description="Print the secret-safe Empire stonks OHLCV configuration.",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Print configuration loaded from the process environment."""

    parser = build_parser()
    parser.parse_args(argv)
    print(json.dumps(OHLCVConfig.from_env().to_safe_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
