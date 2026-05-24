"""Normalization helpers for YouTube API payloads."""

from __future__ import annotations

import re
from typing import Any

from empire_youtube.models import MatchedChannel, NormalizedVideo, Thumbnail


_DURATION_RE = re.compile(
    r"^P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r")?$"
)


def build_video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def parse_iso8601_duration_seconds(value: str | None) -> int | None:
    """Parse a YouTube ISO 8601 duration into seconds."""

    if not value:
        return None
    match = _DURATION_RE.match(value)
    if not match:
        return None
    parts = {name: int(raw or 0) for name, raw in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def normalize_thumbnails(data: dict[str, Any] | None) -> dict[str, Thumbnail]:
    """Normalize YouTube thumbnail entries while preserving rendition names."""

    if not data:
        return {}
    thumbnails: dict[str, Thumbnail] = {}
    for name, raw in data.items():
        if not isinstance(raw, dict) or not raw.get("url"):
            continue
        thumbnails[name] = Thumbnail(
            url=str(raw["url"]),
            width=_optional_int(raw.get("width")),
            height=_optional_int(raw.get("height")),
        )
    return thumbnails


def choose_preferred_thumbnail_url(
    thumbnails: dict[str, Thumbnail],
    preference: list[str],
) -> str | None:
    for name in preference:
        thumbnail = thumbnails.get(name)
        if thumbnail:
            return thumbnail.url
    for thumbnail in thumbnails.values():
        return thumbnail.url
    return None


def normalize_video(
    payload: dict[str, Any],
    *,
    thumbnail_preference: list[str],
    include_description: bool = True,
    include_tags: bool = True,
    include_raw_payload: bool = False,
) -> NormalizedVideo:
    """Normalize a YouTube video resource."""

    video_id = str(payload.get("id") or "")
    snippet = payload.get("snippet") or {}
    content_details = payload.get("contentDetails") or {}
    statistics = payload.get("statistics") or {}
    status = payload.get("status") or {}
    topic_details = payload.get("topicDetails") or {}
    recording_details = payload.get("recordingDetails") or {}
    live_streaming_details = payload.get("liveStreamingDetails") or {}
    player = payload.get("player") or {}
    paid_product = payload.get("paidProductPlacementDetails") or {}

    thumbnails = normalize_thumbnails(snippet.get("thumbnails"))
    duration = content_details.get("duration")
    live_content = snippet.get("liveBroadcastContent")

    return NormalizedVideo(
        video_id=video_id,
        url=build_video_url(video_id),
        title=snippet.get("title"),
        description=snippet.get("description") if include_description else None,
        channel_id=snippet.get("channelId"),
        channel_name=snippet.get("channelTitle"),
        published_at=snippet.get("publishedAt"),
        content={
            "duration_iso8601": duration,
            "duration_seconds": parse_iso8601_duration_seconds(duration),
            "definition": content_details.get("definition"),
            "caption": _optional_bool_text(content_details.get("caption")),
            "licensed_content": content_details.get("licensedContent"),
            "projection": content_details.get("projection"),
        },
        statistics={
            "view_count": _optional_int(statistics.get("viewCount")),
            "like_count": _optional_int(statistics.get("likeCount")),
            "comment_count": _optional_int(statistics.get("commentCount")),
        },
        status={
            "privacy_status": status.get("privacyStatus"),
            "embeddable": status.get("embeddable"),
            "made_for_kids": status.get("madeForKids"),
        },
        topics={
            "youtube_topic_categories": topic_details.get("topicCategories", []),
        },
        recording={
            "recording_date": recording_details.get("recordingDate"),
        },
        live_stream={
            "live_broadcast_content": live_content,
            "actual_start_time": live_streaming_details.get("actualStartTime"),
            "actual_end_time": live_streaming_details.get("actualEndTime"),
        },
        thumbnails=thumbnails,
        preferred_thumbnail_url=choose_preferred_thumbnail_url(
            thumbnails,
            thumbnail_preference,
        ),
        tags=list(snippet.get("tags", [])) if include_tags else [],
        default_language=snippet.get("defaultLanguage"),
        default_audio_language=snippet.get("defaultAudioLanguage"),
        youtube={
            "category_id": snippet.get("categoryId"),
            "embed_html": player.get("embedHtml"),
            "contains_paid_product_placement": paid_product.get(
                "hasPaidProductPlacement"
            ),
        },
        raw={"video": payload} if include_raw_payload else None,
    )


def merge_video_match(
    video: NormalizedVideo,
    *,
    discovery_source: str,
    section_key: str | None = None,
    topic_key: str | None = None,
    query: str | None = None,
    channel: MatchedChannel | None = None,
) -> None:
    """Merge provenance into an existing normalized video."""

    _append_unique(video.discovery_sources, discovery_source)
    if section_key:
        _append_unique(video.matched_sections, section_key)
    if topic_key:
        _append_unique(video.matched_topics, topic_key)
    if query:
        _append_unique(video.matched_queries, query)
    if channel and channel.channel_id not in {
        item.channel_id for item in video.matched_channels
    }:
        video.matched_channels.append(channel)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool_text(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return None
