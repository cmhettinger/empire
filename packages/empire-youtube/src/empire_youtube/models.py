"""Public data models for YouTube metadata scraping."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


OUTPUT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Thumbnail:
    """A YouTube thumbnail rendition."""

    url: str
    width: int | None = None
    height: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class MatchedChannel:
    """A followed channel that matched a video."""

    channel_name: str
    channel_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "channel_name": self.channel_name,
            "channel_id": self.channel_id,
        }


@dataclass(frozen=True)
class YouTubeChannel:
    """Resolved public YouTube channel metadata."""

    channel_id: str
    channel_name: str
    description: str | None = None
    custom_url: str | None = None
    handle: str | None = None
    published_at: str | None = None
    thumbnail_url: str | None = None
    uploads_playlist_id: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "channel_name": self.channel_name,
            "channel_id": self.channel_id,
            "handle": self.handle,
            "custom_url": self.custom_url,
            "description": self.description,
            "published_at": self.published_at,
            "thumbnail_url": self.thumbnail_url,
            "uploads_playlist_id": self.uploads_playlist_id,
        }


@dataclass
class NormalizedVideo:
    """Normalized video metadata for downstream reporting."""

    video_id: str
    url: str
    title: str | None
    description: str | None
    channel_id: str | None
    channel_name: str | None
    published_at: str | None
    content: dict[str, Any] = field(default_factory=dict)
    statistics: dict[str, int | None] = field(default_factory=dict)
    status: dict[str, Any] = field(default_factory=dict)
    topics: dict[str, Any] = field(default_factory=dict)
    recording: dict[str, Any] = field(default_factory=dict)
    live_stream: dict[str, Any] = field(default_factory=dict)
    thumbnails: dict[str, Thumbnail] = field(default_factory=dict)
    preferred_thumbnail_url: str | None = None
    tags: list[str] = field(default_factory=list)
    default_language: str | None = None
    default_audio_language: str | None = None
    matched_sections: list[str] = field(default_factory=list)
    matched_topics: list[str] = field(default_factory=list)
    matched_queries: list[str] = field(default_factory=list)
    matched_channels: list[MatchedChannel] = field(default_factory=list)
    discovery_sources: list[str] = field(default_factory=list)
    youtube: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "video_id": self.video_id,
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "channel": {
                "channel_id": self.channel_id,
                "channel_name": self.channel_name,
            },
            "published_at": self.published_at,
            "content": self.content,
            "statistics": self.statistics,
            "status": self.status,
            "topics": self.topics,
            "recording": self.recording,
            "live_stream": self.live_stream,
            "thumbnails": {
                name: thumbnail.to_dict()
                for name, thumbnail in self.thumbnails.items()
            },
            "preferred_thumbnail_url": self.preferred_thumbnail_url,
            "tags": self.tags,
            "default_language": self.default_language,
            "default_audio_language": self.default_audio_language,
            "matched_sections": self.matched_sections,
            "matched_topics": self.matched_topics,
            "matched_queries": self.matched_queries,
            "matched_channels": [
                channel.to_dict() for channel in self.matched_channels
            ],
            "discovery_sources": self.discovery_sources,
            "youtube": self.youtube,
        }
        if self.raw is not None:
            data["raw"] = self.raw
        return data


@dataclass(frozen=True)
class YouTubeScrapeResult:
    """Consolidated daily YouTube scraper output."""

    source: str
    generated_at: datetime
    window_hours: int
    run_id: str | None
    config_name: str
    config_version: int
    videos: list[NormalizedVideo]
    schema_version: int = OUTPUT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        generated_at = self.generated_at.astimezone(UTC).isoformat()
        return {
            "source": self.source,
            "schema_version": self.schema_version,
            "generated_at": generated_at.replace("+00:00", "Z"),
            "window_hours": self.window_hours,
            "run_id": self.run_id,
            "config": {
                "name": self.config_name,
                "version": self.config_version,
            },
            "videos": [video.to_dict() for video in self.videos],
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the normalized result as stable JSON."""

        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=False,
        )
