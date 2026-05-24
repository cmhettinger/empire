"""Reusable YouTube metadata scraper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from empire_youtube.client import YouTubeClient
from empire_youtube.config import YouTubeScraperConfig
from empire_youtube.models import MatchedChannel, NormalizedVideo, YouTubeScrapeResult
from empire_youtube.normalize import merge_video_match, normalize_video
from empire_youtube.resolver import YouTubeChannelResolver


class YouTubeScraper:
    """Scrape and normalize YouTube metadata using API-key auth."""

    def __init__(
        self,
        *,
        client: YouTubeClient | None = None,
        config: YouTubeScraperConfig,
    ) -> None:
        self.client = client or YouTubeClient()
        self.config = config
        self.channel_resolver = YouTubeChannelResolver(self.client)

    def scrape(
        self,
        *,
        generated_at: datetime | None = None,
        run_id: str | None = None,
    ) -> YouTubeScrapeResult:
        generated_at = generated_at or datetime.now(UTC)
        published_after_dt = generated_at - timedelta(hours=self.config.lookback_hours)
        published_after = _format_utc(published_after_dt)
        videos_by_id: dict[str, NormalizedVideo] = {}

        for section in self.config.topic_sections:
            if not section.enabled:
                continue
            for topic in section.topics:
                if not topic.enabled:
                    continue
                for query in topic.queries:
                    search_response = self.client.search_videos(
                        query,
                        max_results=self.config.max_results_per_query,
                        published_after=published_after,
                        relevance_language=self.config.filters.language,
                    )
                    video_ids = _video_ids_from_search(search_response)
                    self._hydrate_and_merge(
                        videos_by_id,
                        video_ids,
                        discovery_source="topic_search",
                        section_key=section.key,
                        topic_key=topic.key,
                        query=query,
                    )

        for followed in self.config.followed_channels:
            if not followed.enabled:
                continue
            channel_id = followed.channel_id
            channel_name = followed.channel_name
            if channel_id is None and followed.handle:
                resolved = self.resolve_channel(followed.handle)
                channel_id = resolved.channel_id
                channel_name = resolved.channel_name
            if channel_id is None:
                continue

            uploads_playlist_id = self.client.get_channel_uploads_playlist(channel_id)
            playlist_response = self.client.get_playlist_items(
                uploads_playlist_id,
                max_results=self.config.max_results_per_query,
            )
            video_ids = _video_ids_from_playlist_items(playlist_response)
            self._hydrate_and_merge(
                videos_by_id,
                video_ids,
                discovery_source="channel_watch",
                published_after=published_after_dt,
                channel=MatchedChannel(
                    channel_name=channel_name,
                    channel_id=channel_id,
                ),
            )

        videos = [
            video
            for video in videos_by_id.values()
            if self._passes_filters(video)
        ]
        videos.sort(key=lambda item: item.published_at or "", reverse=True)

        return YouTubeScrapeResult(
            source="youtube",
            generated_at=generated_at,
            window_hours=self.config.lookback_hours,
            run_id=run_id,
            config_name=self.config.name,
            config_version=self.config.version,
            videos=videos,
        )

    def resolve_channel(self, value: str) -> MatchedChannel:
        """Resolve a channel handle or id to name and id."""

        resolved = self.channel_resolver.resolve(value)
        return MatchedChannel(
            channel_name=resolved.channel_name,
            channel_id=resolved.channel_id,
        )

    def _hydrate_and_merge(
        self,
        videos_by_id: dict[str, NormalizedVideo],
        video_ids: list[str],
        *,
        discovery_source: str,
        section_key: str | None = None,
        topic_key: str | None = None,
        query: str | None = None,
        channel: MatchedChannel | None = None,
        published_after: datetime | None = None,
    ) -> None:
        for chunk in _chunks(video_ids, 50):
            response = self.client.get_videos(
                chunk,
                parts=self.config.hydration.parts,
            )
            for item in response.get("items", []):
                video_id = item.get("id")
                if not video_id:
                    continue
                video = videos_by_id.get(video_id)
                if video is None:
                    video = normalize_video(
                        item,
                        thumbnail_preference=self.config.thumbnail_preference,
                    )
                    if published_after and not _is_published_at_or_after(
                        video.published_at,
                        published_after,
                    ):
                        continue
                    videos_by_id[video_id] = video
                merge_video_match(
                    video,
                    discovery_source=discovery_source,
                    section_key=section_key,
                    topic_key=topic_key,
                    query=query,
                    channel=channel,
                )

    def _passes_filters(self, video: NormalizedVideo) -> bool:
        min_seconds = self.config.filters.min_duration_minutes * 60
        duration = video.content.get("duration_seconds")
        if isinstance(duration, int) and duration < min_seconds:
            return False
        if self.config.filters.exclude_shorts and isinstance(duration, int):
            if duration <= 60:
                return False
        if not self._passes_language_filter(video):
            return False
        return True

    def _passes_language_filter(self, video: NormalizedVideo) -> bool:
        expected = self.config.filters.language
        if not expected:
            return True
        declared_languages = [
            value
            for value in [video.default_language, video.default_audio_language]
            if value
        ]
        if not declared_languages:
            return True
        expected = expected.lower()
        return any(_language_matches(value, expected) for value in declared_languages)


def _video_ids_from_search(payload: dict) -> list[str]:
    ids: list[str] = []
    for item in payload.get("items", []):
        item_id = item.get("id") or {}
        video_id = item_id.get("videoId")
        if video_id:
            ids.append(video_id)
    return ids


def _video_ids_from_playlist_items(payload: dict) -> list[str]:
    ids: list[str] = []
    for item in payload.get("items", []):
        content_details = item.get("contentDetails") or {}
        video_id = content_details.get("videoId")
        if video_id:
            ids.append(video_id)
            continue
        resource_id = (item.get("snippet") or {}).get("resourceId") or {}
        video_id = resource_id.get("videoId")
        if video_id:
            ids.append(video_id)
    return ids


def _chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _language_matches(value: str, expected: str) -> bool:
    normalized = value.lower()
    return normalized == expected or normalized.startswith(f"{expected}-")


def _is_published_at_or_after(value: str | None, cutoff: datetime) -> bool:
    if not value:
        return True
    try:
        published_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    return published_at.astimezone(UTC) >= cutoff.astimezone(UTC)
