"""Stage one YouTube video as a local Jellyfin movie folder."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from empire_youtube.downloader import YtDlpCommand
from empire_youtube.processor import (
    MOVIE_FILENAME,
    YouTubeLibraryEntry,
    YouTubeScrapeProcessor,
    jellyfin_friendly_name,
)


@dataclass(frozen=True)
class YouTubeStageResult:
    """Result of staging one video for Jellyfin debugging."""

    video_id: str
    title: str
    output_dir: Path
    files: list[str]


class YtDlpInfoExtractor:
    """Shell out to yt-dlp for one video's metadata."""

    def __init__(self, executable: str = "yt-dlp") -> None:
        self.executable = executable

    def extract(self, url: str) -> dict[str, Any]:
        command = [
            self.executable,
            "--no-playlist",
            "--dump-single-json",
            "--skip-download",
            url,
        ]
        completed = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        payload = json.loads(completed.stdout)
        if not isinstance(payload, dict):
            raise RuntimeError("yt-dlp metadata output must be a JSON object.")
        return payload


def stage_youtube_video(
    *,
    url: str,
    temp_dir: str | Path | None = None,
    info_extractor: YtDlpInfoExtractor | None = None,
    downloader: YtDlpCommand | None = None,
) -> YouTubeStageResult:
    """Download one URL and sidecars into ``EMPIRE_TEMP_DIR/{video_id}``."""

    requested_video_id = parse_youtube_video_id(url)
    info_extractor = info_extractor or YtDlpInfoExtractor()
    metadata = info_extractor.extract(url)
    video = build_video_from_ytdlp_metadata(
        metadata,
        source_url=url,
        requested_video_id=requested_video_id,
    )
    processor = YouTubeScrapeProcessor()
    plan = processor.process(_scrape_payload(video))
    video_id = str(video["video_id"])
    if len(plan.entries) != 1:
        raise RuntimeError(f"Video is not download-ready: {video_id}")
    entry = plan.entries[0]
    root_dir = Path(temp_dir) if temp_dir is not None else default_stage_temp_dir()
    output_dir = root_dir / stage_folder_name(entry)
    output_dir.mkdir(parents=True, exist_ok=True)

    for planned_file in entry.files:
        (output_dir / planned_file.filename).write_bytes(planned_file.data)

    work_dir = output_dir / ".download"
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        downloader = downloader or YtDlpCommand()
        downloader.download(
            url=entry.source_url,
            output_template=work_dir / "movie.%(ext)s",
        )
        staged_movie = work_dir / MOVIE_FILENAME
        if not staged_movie.is_file() or staged_movie.stat().st_size <= 0:
            raise RuntimeError(f"yt-dlp did not create a non-empty {MOVIE_FILENAME}")
        shutil.move(str(staged_movie), output_dir / MOVIE_FILENAME)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    files = sorted(path.name for path in output_dir.iterdir() if path.is_file())
    return YouTubeStageResult(
        video_id=video_id,
        title=entry.title,
        output_dir=output_dir,
        files=files,
    )


def parse_youtube_video_id(url: str) -> str | None:
    """Return a video id from common YouTube URL shapes when one is present."""

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.endswith("youtu.be"):
        candidate = parsed.path.strip("/").split("/", 1)[0]
        return candidate or None
    if "youtube.com" in host:
        query_id = parse_qs(parsed.query).get("v", [None])[0]
        if query_id:
            return query_id
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live"}:
            return parts[1]
    return None


def stage_folder_name(entry: YouTubeLibraryEntry) -> str:
    """Build a local Jellyfin-style folder name for one staged video."""

    title = jellyfin_friendly_name(entry.title)
    return f"{title} [{entry.video_id}]"


def build_video_from_ytdlp_metadata(
    metadata: dict[str, Any],
    *,
    source_url: str,
    requested_video_id: str | None = None,
) -> dict[str, Any]:
    """Convert yt-dlp metadata into the processor's normalized video shape."""

    video_id = _text_or_default(metadata.get("id"), requested_video_id)
    if not video_id:
        raise RuntimeError("Could not determine YouTube video id.")

    channel_name = _text_or_default(
        metadata.get("channel"),
        _text_or_default(metadata.get("uploader"), "Unknown Channel"),
    )
    thumbnail_url = _best_thumbnail_url(metadata)
    thumbnails = (
        {
            "maxres": {
                "url": thumbnail_url,
            }
        }
        if thumbnail_url
        else {}
    )
    return {
        "video_id": video_id,
        "url": _text_or_default(metadata.get("webpage_url"), source_url),
        "title": _text_or_default(metadata.get("title"), video_id),
        "description": metadata.get("description"),
        "channel": {
            "channel_id": metadata.get("channel_id") or metadata.get("uploader_id"),
            "channel_name": channel_name,
        },
        "published_at": _published_at_from_ytdlp(metadata),
        "content": {
            "duration_seconds": _optional_int(metadata.get("duration")),
        },
        "statistics": {
            "view_count": _optional_int(metadata.get("view_count")),
            "like_count": _optional_int(metadata.get("like_count")),
            "comment_count": _optional_int(metadata.get("comment_count")),
        },
        "live_stream": {
            "live_broadcast_content": _live_broadcast_content(metadata),
        },
        "thumbnails": thumbnails,
        "preferred_thumbnail_url": thumbnail_url,
        "tags": [
            str(tag)
            for tag in metadata.get("tags", [])
            if tag is not None and str(tag).strip()
        ],
        "discovery_sources": ["youtube_stage"],
        "raw": {"yt_dlp": metadata},
    }


def default_stage_temp_dir() -> Path:
    value = os.environ.get("EMPIRE_TEMP_DIR")
    if not value:
        raise RuntimeError("Missing required environment variable: EMPIRE_TEMP_DIR")
    return Path(value)


def _scrape_payload(video: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "youtube",
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "run_id": None,
        "videos": [video],
    }


def _published_at_from_ytdlp(metadata: dict[str, Any]) -> str | None:
    timestamp = metadata.get("timestamp") or metadata.get("release_timestamp")
    if isinstance(timestamp, (int, float)):
        return (
            datetime.fromtimestamp(timestamp, UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )

    upload_date = metadata.get("upload_date") or metadata.get("release_date")
    if isinstance(upload_date, str) and re.match(r"^\d{8}$", upload_date):
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}T00:00:00Z"
    return None


def _best_thumbnail_url(metadata: dict[str, Any]) -> str | None:
    thumbnails = metadata.get("thumbnails")
    if isinstance(thumbnails, list):
        candidates = [
            item
            for item in thumbnails
            if isinstance(item, dict) and isinstance(item.get("url"), str)
        ]
        if candidates:
            best = max(
                candidates,
                key=lambda item: (
                    _optional_int(item.get("width")) or 0,
                    _optional_int(item.get("height")) or 0,
                ),
            )
            return str(best["url"])
    thumbnail = metadata.get("thumbnail")
    if isinstance(thumbnail, str) and thumbnail.strip():
        return str(thumbnail)
    return None


def _live_broadcast_content(metadata: dict[str, Any]) -> str:
    live_status = str(metadata.get("live_status") or "").lower()
    if live_status in {"is_live", "is_upcoming"}:
        return "live" if live_status == "is_live" else "upcoming"
    return "none"


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text_or_default(value: Any, default: str | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default
