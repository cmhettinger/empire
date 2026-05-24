"""Resolve a YouTube channel id, handle, or search query."""

from __future__ import annotations

import argparse

import yaml

from empire_youtube.resolver import resolve_channel


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve a YouTube channel id, handle, or search query."
    )
    parser.add_argument("channel", help="Channel id, handle, or search query.")
    args = parser.parse_args()

    channel = resolve_channel(args.channel)
    print(
        yaml.safe_dump(
            {
                "channel_name": channel.channel_name,
                "channel_id": channel.channel_id,
                "handle": channel.handle,
                "enabled": True,
            },
            sort_keys=False,
        ).strip()
    )


if __name__ == "__main__":
    main()
