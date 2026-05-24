"""Configuration loading for YouTube metadata scraping."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from empire_youtube.exceptions import YouTubeConfigError


DEFAULT_VIDEO_PARTS = [
    "snippet",
    "contentDetails",
    "statistics",
    "status",
    "topicDetails",
    "recordingDetails",
    "liveStreamingDetails",
    "player",
    "paidProductPlacementDetails",
]

DEFAULT_THUMBNAIL_PREFERENCE = ["maxres", "standard", "high", "medium", "default"]
ALLOWED_THUMBNAIL_NAMES = {"default", "medium", "high", "standard", "maxres"}


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise YouTubeConfigError(f"Missing required environment variable: {name}")
    return value


def _as_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise YouTubeConfigError(f"{field_name} must be a boolean.")


def _as_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise YouTubeConfigError(f"{field_name} must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise YouTubeConfigError(f"{field_name} must be an integer.") from exc


def _as_str(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise YouTubeConfigError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _as_str_list(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise YouTubeConfigError(f"{field_name} must be a list.")
    return [_as_str(item, field_name=field_name) for item in value]


def _validate_positive(value: int, *, field_name: str) -> None:
    if value <= 0:
        raise YouTubeConfigError(f"{field_name} must be greater than zero.")


def _validate_max_results(value: int, *, field_name: str) -> None:
    if value < 1 or value > 50:
        raise YouTubeConfigError(f"{field_name} must be between 1 and 50.")


def _validate_unique(values: list[str], *, field_name: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise YouTubeConfigError(
            f"{field_name} must be unique. Duplicate value(s): {', '.join(duplicates)}"
        )


@dataclass(frozen=True)
class YouTubeAPIConfig:
    """YouTube Data API connection settings."""

    api_key: str
    base_url: str = "https://www.googleapis.com/youtube/v3"
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "YouTubeAPIConfig":
        return cls(api_key=_required_env("EMPIRE_YOUTUBE_API_KEY"))


@dataclass(frozen=True)
class YouTubeScraperFilters:
    """Global filters for the daily scraper."""

    exclude_shorts: bool = False
    min_duration_minutes: int = 0
    language: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "YouTubeScraperFilters":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise YouTubeConfigError("youtube.filters must be a mapping.")
        language = data.get("language")
        min_duration_minutes = _as_int(
            data.get("min_duration_minutes", 0),
            field_name="youtube.filters.min_duration_minutes",
        )
        if min_duration_minutes < 0:
            raise YouTubeConfigError(
                "youtube.filters.min_duration_minutes must be zero or greater."
            )
        return cls(
            exclude_shorts=_as_bool(
                data.get("exclude_shorts", False),
                field_name="youtube.filters.exclude_shorts",
            ),
            min_duration_minutes=min_duration_minutes,
            language=str(language).strip() if language else None,
        )


@dataclass(frozen=True)
class YouTubeScraperHydration:
    """Controls which video resource parts are hydrated."""

    parts: list[str] = field(default_factory=lambda: list(DEFAULT_VIDEO_PARTS))

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "YouTubeScraperHydration":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise YouTubeConfigError("youtube.hydration must be a mapping.")
        return cls(
            parts=_as_str_list(
                data.get("parts", DEFAULT_VIDEO_PARTS),
                field_name="youtube.hydration.parts",
            )
        )


@dataclass(frozen=True)
class YouTubeTopic:
    """A searchable topic inside a broader interest section."""

    key: str
    name: str
    queries: list[str]
    enabled: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "YouTubeTopic":
        if not isinstance(data, dict):
            raise YouTubeConfigError("youtube.topic_sections[].topics[] must be a mapping.")
        queries = _as_str_list(data.get("queries", []), field_name="topic.queries")
        if not queries:
            raise YouTubeConfigError("topic.queries must include at least one query.")
        _validate_unique(queries, field_name="topic.queries")
        return cls(
            key=_as_str(data.get("key"), field_name="topic.key"),
            name=_as_str(data.get("name"), field_name="topic.name"),
            queries=queries,
            enabled=_as_bool(data.get("enabled", True), field_name="topic.enabled"),
        )


@dataclass(frozen=True)
class YouTubeTopicSection:
    """A group of related search topics."""

    key: str
    name: str
    topics: list[YouTubeTopic]
    enabled: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "YouTubeTopicSection":
        if not isinstance(data, dict):
            raise YouTubeConfigError("youtube.topic_sections[] must be a mapping.")
        topics_data = data.get("topics", [])
        if not isinstance(topics_data, list):
            raise YouTubeConfigError("youtube.topic_sections[].topics must be a list.")
        topics = [YouTubeTopic.from_mapping(item) for item in topics_data]
        if not topics:
            raise YouTubeConfigError("youtube.topic_sections[].topics cannot be empty.")
        _validate_unique(
            [topic.key for topic in topics],
            field_name="topic keys within a section",
        )
        return cls(
            key=_as_str(data.get("key"), field_name="topic_section.key"),
            name=_as_str(data.get("name"), field_name="topic_section.name"),
            enabled=_as_bool(
                data.get("enabled", True),
                field_name="topic_section.enabled",
            ),
            topics=topics,
        )


@dataclass(frozen=True)
class YouTubeFollowedChannel:
    """A channel explicitly followed by the daily scraper."""

    channel_name: str
    channel_id: str | None = None
    handle: str | None = None
    enabled: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "YouTubeFollowedChannel":
        if not isinstance(data, dict):
            raise YouTubeConfigError("youtube.followed_channels[] must be a mapping.")
        channel_id = data.get("channel_id")
        handle = data.get("handle")
        if not channel_id:
            raise YouTubeConfigError("followed channel must define channel_id.")
        return cls(
            channel_name=_as_str(data.get("channel_name"), field_name="channel_name"),
            channel_id=_as_str(channel_id, field_name="channel.channel_id"),
            handle=str(handle).strip() if handle else None,
            enabled=_as_bool(data.get("enabled", True), field_name="channel.enabled"),
        )


@dataclass(frozen=True)
class YouTubeScraperConfig:
    """Daily YouTube scraper job configuration."""

    name: str
    version: int
    lookback_hours: int
    max_results_per_query: int
    filters: YouTubeScraperFilters = field(default_factory=YouTubeScraperFilters)
    hydration: YouTubeScraperHydration = field(default_factory=YouTubeScraperHydration)
    thumbnail_preference: list[str] = field(
        default_factory=lambda: list(DEFAULT_THUMBNAIL_PREFERENCE)
    )
    topic_sections: list[YouTubeTopicSection] = field(default_factory=list)
    followed_channels: list[YouTubeFollowedChannel] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: str | Path) -> "YouTubeScraperConfig":
        return cls.from_yaml(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def from_yaml(cls, text: str) -> "YouTubeScraperConfig":
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise YouTubeConfigError(f"Invalid YouTube scraper YAML: {exc}") from exc
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "YouTubeScraperConfig":
        if not isinstance(data, dict):
            raise YouTubeConfigError("YouTube scraper config must be a mapping.")
        youtube = data.get("youtube")
        if not isinstance(youtube, dict):
            raise YouTubeConfigError("YouTube scraper config requires a youtube mapping.")

        sections_data = youtube.get("topic_sections", [])
        channels_data = youtube.get("followed_channels", [])
        if not isinstance(sections_data, list):
            raise YouTubeConfigError("youtube.topic_sections must be a list.")
        if not isinstance(channels_data, list):
            raise YouTubeConfigError("youtube.followed_channels must be a list.")
        if "hydration" in youtube:
            raise YouTubeConfigError(
                "youtube.hydration is not part of the v1 config contract; "
                "video hydration parts are managed by empire-youtube."
            )

        lookback_hours = _as_int(
            youtube.get("lookback_hours", 24),
            field_name="youtube.lookback_hours",
        )
        _validate_positive(lookback_hours, field_name="youtube.lookback_hours")

        max_results_per_query = _as_int(
            youtube.get("max_results_per_query", 10),
            field_name="youtube.max_results_per_query",
        )
        _validate_max_results(
            max_results_per_query,
            field_name="youtube.max_results_per_query",
        )

        thumbnail_preference = _as_str_list(
            youtube.get("thumbnail_preference", DEFAULT_THUMBNAIL_PREFERENCE),
            field_name="youtube.thumbnail_preference",
        )
        if not thumbnail_preference:
            raise YouTubeConfigError("youtube.thumbnail_preference cannot be empty.")
        unknown_thumbnails = [
            item for item in thumbnail_preference if item not in ALLOWED_THUMBNAIL_NAMES
        ]
        if unknown_thumbnails:
            raise YouTubeConfigError(
                "youtube.thumbnail_preference contains unknown value(s): "
                + ", ".join(unknown_thumbnails)
            )
        _validate_unique(
            thumbnail_preference,
            field_name="youtube.thumbnail_preference",
        )

        topic_sections = [
            YouTubeTopicSection.from_mapping(item) for item in sections_data
        ]
        followed_channels = [
            YouTubeFollowedChannel.from_mapping(item) for item in channels_data
        ]
        _validate_unique(
            [section.key for section in topic_sections],
            field_name="youtube.topic_sections[].key",
        )
        _validate_unique(
            [
                f"{section.key}.{topic.key}"
                for section in topic_sections
                for topic in section.topics
            ],
            field_name="topic keys",
        )
        _validate_unique(
            [channel.channel_id for channel in followed_channels if channel.channel_id],
            field_name="youtube.followed_channels[].channel_id",
        )

        return cls(
            name=_as_str(youtube.get("name"), field_name="youtube.name"),
            version=_as_int(youtube.get("version", 1), field_name="youtube.version"),
            lookback_hours=lookback_hours,
            max_results_per_query=max_results_per_query,
            filters=YouTubeScraperFilters.from_mapping(youtube.get("filters")),
            hydration=YouTubeScraperHydration(),
            thumbnail_preference=thumbnail_preference,
            topic_sections=topic_sections,
            followed_channels=followed_channels,
        )
