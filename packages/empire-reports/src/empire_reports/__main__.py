from __future__ import annotations

import argparse

from empire_reports import __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m empire_reports")
    parser.add_argument("--version", action="store_true", help="Print package version.")
    args = parser.parse_args()

    if args.version:
        print(__version__)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
