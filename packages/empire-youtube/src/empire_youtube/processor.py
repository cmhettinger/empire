"""Process YouTube scrape output into Jellyfin sidecar artifacts."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

import requests


PROCESSOR_SCHEMA_VERSION = 1
DEFAULT_TITLE_MAX_LENGTH = 70
DEFAULT_CHANNEL_MAX_LENGTH = 80
EMPIRE_METADATA_FILENAME = "empire.json"
MOVIE_NFO_FILENAME = "movie.nfo"
FANART_FILENAME = "fanart.jpg"
MOVIE_FILENAME = "movie.mp4"
EMPIRE_METADATA_OBJECT_KIND = "youtube_empire_metadata"
MOVIE_NFO_OBJECT_KIND = "jellyfin_movie_nfo"
FANART_OBJECT_KIND = "jellyfin_fanart"

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


@dataclass(frozen=True)
class PlannedFile:
    """One object-store file that stage 2 should write."""

    filename: str
    data: bytes
    content_type: str
    object_kind: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "content_type": self.content_type,
            "object_kind": self.object_kind,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class YouTubeLibraryEntry:
    """Planned Jellyfin location and sidecars for one YouTube video."""

    video_id: str
    title: str
    channel_name: str
    published_date: str
    year: str
    object_key: str
    source_url: str
    empire_metadata_uri: str
    thumbnail_url: str | None
    movie_filename: str
    files: list[PlannedFile] = field(default_factory=list)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "channel_name": self.channel_name,
            "published_date": self.published_date,
            "year": self.year,
            "object_key": self.object_key,
            "source_url": self.source_url,
            "empire_metadata_uri": self.empire_metadata_uri,
            "thumbnail_url": self.thumbnail_url,
            "movie_filename": self.movie_filename,
            "files": [file.to_manifest() for file in self.files],
        }


@dataclass(frozen=True)
class YouTubeLibraryPlan:
    """Planned Jellyfin object-store outputs derived from a scrape payload."""

    source: str
    schema_version: int
    source_schema_version: int | None
    source_run_id: str | None
    source_video_count: int
    entries: list[YouTubeLibraryEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "schema_version": self.schema_version,
            "source_schema_version": self.source_schema_version,
            "source_run_id": self.source_run_id,
            "source_video_count": self.source_video_count,
            "entries": [entry.to_manifest() for entry in self.entries],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=False,
        )


@dataclass(frozen=True)
class ThumbnailAsset:
    """Downloaded thumbnail bytes."""

    data: bytes
    content_type: str = "image/jpeg"


class ThumbnailFetcher:
    """Fetch thumbnail bytes from URLs discovered by the YouTube scraper."""

    def fetch(self, url: str) -> ThumbnailAsset:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return ThumbnailAsset(
            data=response.content,
            content_type=response.headers.get("content-type", "image/jpeg"),
        )


class YouTubeScrapeProcessor:
    """Build Jellyfin sidecar artifacts from scrape JSON."""

    def __init__(
        self,
        *,
        storage_key_prefix: str = "media/youtube",
        thumbnail_fetcher: ThumbnailFetcher | None = None,
    ) -> None:
        self.storage_key_prefix = storage_key_prefix
        self.thumbnail_fetcher = thumbnail_fetcher or ThumbnailFetcher()

    def process(self, scrape_payload: dict[str, Any]) -> YouTubeLibraryPlan:
        """Return a Jellyfin library plan with per-video sidecar files."""

        videos = scrape_payload.get("videos")
        source_videos = videos if isinstance(videos, list) else []
        source_schema_version = scrape_payload.get("schema_version")
        if not isinstance(source_schema_version, int):
            source_schema_version = None
        source_run_id = scrape_payload.get("run_id")
        if source_run_id is not None:
            source_run_id = str(source_run_id)

        entries = [
            self._build_entry(video)
            for video in source_videos
            if isinstance(video, dict) and video.get("video_id")
        ]

        return YouTubeLibraryPlan(
            source="youtube",
            schema_version=PROCESSOR_SCHEMA_VERSION,
            source_schema_version=source_schema_version,
            source_run_id=source_run_id,
            source_video_count=len(source_videos),
            entries=entries,
        )

    def _build_entry(self, video: dict[str, Any]) -> YouTubeLibraryEntry:
        video_id = str(video["video_id"])
        title = _text_or_default(video.get("title"), "Untitled")
        channel_name = _channel_name(video)
        published_date = _published_date(video.get("published_at"))
        year = published_date[:4] if published_date[:4].isdigit() else "unknown-year"
        source_url = _text_or_default(
            video.get("url"),
            f"https://www.youtube.com/watch?v={video_id}",
        )
        empire_metadata_uri = f"empire://youtube/videos/{video_id}/metadata.json"
        object_key = build_jellyfin_object_key(
            storage_key_prefix=self.storage_key_prefix,
            channel_name=channel_name,
            published_date=published_date,
            title=title,
            video_id=video_id,
        )
        thumbnail_url = select_thumbnail_url(video)
        files = [
            _empire_metadata_file(video),
            _movie_nfo_file(
                video=video,
                title=title,
                channel_name=channel_name,
                published_date=published_date,
                year=year,
            ),
        ]
        if thumbnail_url:
            thumbnail = self.thumbnail_fetcher.fetch(thumbnail_url)
            files.append(
                PlannedFile(
                    filename=FANART_FILENAME,
                    data=thumbnail.data,
                    content_type=thumbnail.content_type,
                    object_kind=FANART_OBJECT_KIND,
                    metadata={
                        "source": "youtube",
                        "youtube_video_id": video_id,
                        "thumbnail_url": thumbnail_url,
                    },
                )
            )

        return YouTubeLibraryEntry(
            video_id=video_id,
            title=title,
            channel_name=channel_name,
            published_date=published_date,
            year=year,
            object_key=object_key,
            source_url=source_url,
            empire_metadata_uri=empire_metadata_uri,
            thumbnail_url=thumbnail_url,
            movie_filename=MOVIE_FILENAME,
            files=files,
        )


def build_jellyfin_object_key(
    *,
    storage_key_prefix: str,
    channel_name: str,
    published_date: str,
    title: str,
    video_id: str,
) -> str:
    """Build the relative object key for one Jellyfin movie folder."""

    prefix = storage_key_prefix.strip("/")
    channel = jellyfin_friendly_name(
        channel_name,
        max_length=DEFAULT_CHANNEL_MAX_LENGTH,
    )
    clean_title = jellyfin_friendly_name(title, max_length=DEFAULT_TITLE_MAX_LENGTH)
    folder = f"{published_date} - {clean_title} [{video_id}]"
    return "/".join(part for part in [prefix, channel, folder] if part)


def jellyfin_friendly_name(title: str, max_length: int = 70) -> str:
    """Convert a title into a Jellyfin/filesystem-friendly path segment."""

    if not title or not title.strip():
        return "untitled"

    value = unicodedata.normalize("NFKD", title)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[-_/|]+", " ", value)
    value = re.sub(r'[<>:"/\\|?*]', "", value)
    value = re.sub(r"[^\w\s()\[\].'-]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.strip(" .-_")
    if not value:
        return "untitled"

    if len(value) > max_length:
        truncated = value[:max_length].rstrip()
        last_space = truncated.rfind(" ")
        if last_space >= max(20, max_length // 2):
            truncated = truncated[:last_space]
        value = truncated.strip(" .-_")

    if value.upper() in _WINDOWS_RESERVED_NAMES:
        value = f"{value}_video"

    return value or "untitled"


def select_thumbnail_url(video: dict[str, Any]) -> str | None:
    """Select the best thumbnail URL captured by the scraper."""

    thumbnails = video.get("thumbnails")
    if isinstance(thumbnails, dict):
        for name in ("maxres", "standard", "high", "medium", "default"):
            item = thumbnails.get(name)
            if isinstance(item, dict) and item.get("url"):
                return str(item["url"])
    preferred = video.get("preferred_thumbnail_url")
    return str(preferred) if preferred else None


def _empire_metadata_file(video: dict[str, Any]) -> PlannedFile:
    video_id = str(video["video_id"])
    data = json.dumps(
        video,
        ensure_ascii=False,
        indent=2,
        sort_keys=False,
    ).encode("utf-8")
    return PlannedFile(
        filename=EMPIRE_METADATA_FILENAME,
        data=data,
        content_type="application/json",
        object_kind=EMPIRE_METADATA_OBJECT_KIND,
        metadata={"source": "youtube", "youtube_video_id": video_id},
    )


def _movie_nfo_file(
    *,
    video: dict[str, Any],
    title: str,
    channel_name: str,
    published_date: str,
    year: str,
) -> PlannedFile:
    video_id = str(video["video_id"])
    root = ElementTree.Element("movie")
    _sub(root, "title", title)
    _sub(root, "originaltitle", title)
    _sub(root, "sorttitle", jellyfin_friendly_name(title))
    _sub(root, "premiered", published_date)
    _sub(root, "releasedate", published_date)
    if year != "unknown-year":
        _sub(root, "year", year)
    runtime = _runtime_minutes(video)
    if runtime is not None:
        _sub(root, "runtime", str(runtime))
    _sub(root, "studio", channel_name)
    description = video.get("description")
    if isinstance(description, str) and description.strip():
        _sub(root, "plot", description.strip())
    unique_id = ElementTree.SubElement(root, "uniqueid", type="youtube", default="true")
    unique_id.text = _xml_text(video_id)
    _sub(root, "tag", "youtube")
    _sub(root, "tag", channel_name)
    _sub(
        root,
        "trailer",
        f"plugin://plugin.video.youtube/?action=play_video&videoid={video_id}",
    )
    ElementTree.indent(root, space="  ")
    data = ElementTree.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
    return PlannedFile(
        filename=MOVIE_NFO_FILENAME,
        data=data,
        content_type="application/xml",
        object_kind=MOVIE_NFO_OBJECT_KIND,
        metadata={"source": "youtube", "youtube_video_id": video_id},
    )


def _sub(root: ElementTree.Element, tag: str, text: str) -> None:
    child = ElementTree.SubElement(root, tag)
    child.text = _xml_text(text)


def _xml_text(value: str) -> str:
    """Remove characters that are not legal in XML 1.0 text nodes."""

    return "".join(character for character in value if _is_xml_character(character))


def _is_xml_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        codepoint == 0x09
        or codepoint == 0x0A
        or codepoint == 0x0D
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def _runtime_minutes(video: dict[str, Any]) -> int | None:
    content = video.get("content")
    if not isinstance(content, dict):
        return None
    seconds = content.get("duration_seconds")
    if not isinstance(seconds, int) or seconds <= 0:
        return None
    return max(1, round(seconds / 60))


def _channel_name(video: dict[str, Any]) -> str:
    channel = video.get("channel")
    if isinstance(channel, dict):
        return _text_or_default(channel.get("channel_name"), "Unknown Channel")
    return _text_or_default(video.get("channel_name"), "Unknown Channel")


def _published_date(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "unknown-date"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", value) else "unknown-date"
    return parsed.astimezone(UTC).date().isoformat()


def _text_or_default(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default
