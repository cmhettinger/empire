"""Stage one YouTube video as a local Jellyfin movie folder."""

from __future__ import annotations

import argparse

from empire_youtube.stager import stage_youtube_video


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result = stage_youtube_video(url=args.url, temp_dir=args.temp_dir)

    print(f"video_id: {result.video_id}")
    print(f"title: {result.title}")
    print(f"output_dir: {result.output_dir}")
    print("files:")
    for filename in result.files:
        print(f"  {filename}")


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Stage one YouTube URL as a local Jellyfin movie folder."
    )
    parser.add_argument("url", help="YouTube video URL to stage.")
    parser.add_argument(
        "--temp-dir",
        help="Directory to stage into. Defaults to EMPIRE_TEMP_DIR.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
